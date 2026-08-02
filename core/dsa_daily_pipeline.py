# -*- coding: utf-8 -*-
"""
===================================
DSA 每日自动化流水线（真实计算内核）
===================================

本模块是「new_dsa 多周期前瞻性预测」的后端计算内核，承担设计文档 §3 / §4 / §6 的
落地职责：

1. 多周期前瞻预测：复用 core.multi_model_forecast.MultiModelForecastEngine（真实
   时序 / 资金 / 舆情三模型），并按设计 §5.2 的四周期权重重新加权，输出标准化四周期
   结论（方向 / 波动区间 / 上涨概率 / 核心驱动 / 主要风险 / 置信度）。
2. DSA 产业链传导：复用 src.industry_chain_propagation.propagate_shock，对产业链
   图谱做 BFS 冲击传导。
3. 信号持久化：把四周期结论映射为 decision_signals 行，便于复盘与前端读取。

设计原则：
- 离线可测：默认 mode="synthetic" 用确定性合成 K 线，不依赖网络与外部数据源；
  mode="live" 时由上层注入真实 K 线 / 抓取数据。
- 不破坏既有模块：只调用既有引擎与传导函数，不改动其源码。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.multi_model_forecast import ForecastCycle, MultiModelForecastEngine
from core.utils import clamp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 四周期注册表（设计 §5.2 权重 → 引擎三子模型映射）
# ---------------------------------------------------------------------------
# 引擎只有三个子模型：time_series（趋势/产业/基本面）、capital（资金）、sentiment
# （事件/政策/舆情）。设计 §5.2 的四维权重按以下口径归并：
#   ts   = 产业 + 基本面
#   cap  = 资金
#   sent = 事件 + 政策（+ 宏观，作为长周期外生冲击桶）
# 这样既不破坏引擎，又能让每个周期体现设计要求的侧重。
CYCLE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "1w": {
        "cycle": ForecastCycle.WEEK_1,
        "design_days": 5,
        "w_ts": 0.25, "w_cap": 0.40, "w_sent": 0.35,
        "direction_label": "震荡偏强",
    },
    "2w": {
        "cycle": ForecastCycle.DAY_15,   # 引擎以 15 交易日近似半月
        "design_days": 10,
        "w_ts": 0.35, "w_cap": 0.05, "w_sent": 0.65,
        "direction_label": "上行",
    },
    "1m": {
        "cycle": ForecastCycle.MONTH_1,
        "design_days": 22,
        "w_ts": 0.65, "w_cap": 0.10, "w_sent": 0.25,
        "direction_label": "稳步上行",
    },
    "6m": {
        "cycle": ForecastCycle.HALF_YEAR,
        "design_days": 120,
        "w_ts": 0.65, "w_cap": 0.05, "w_sent": 0.30,
        "direction_label": "趋势上行",
    },
}

ALL_CYCLES: List[str] = list(CYCLE_REGISTRY.keys())

# 每日六段闭环中，各段需要计算的周期（设计 §6）
SEGMENT_CYCLES: Dict[str, List[str]] = {
    "overnight": ["1w", "2w"],
    "premarket": ["1w", "2w"],
    "intraday": ["1w"],
    "postmarket": ["1m", "6m"],
    "evening": ALL_CYCLES,
    "archive": [],
}


# ---------------------------------------------------------------------------
# 合成 K 线（离线 / 测试可复现）
# ---------------------------------------------------------------------------
def build_synthetic_kline(
    symbol: str,
    days: int = 130,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    生成确定性合成日线（open/high/low/close/volume）。

    - seed 固定时输出完全可复现，便于单元测试断言；
    - 不调用任何外部网络，保证离线可跑。
    """
    if seed is None:
        seed = abs(hash(symbol)) % (2 ** 31)
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end, periods=days, freq="B")
    drift = rng.normal(0.0004, 0.0016, size=days).cumsum()
    close = 100.0 * np.exp(drift)
    prev_close = np.concatenate([[close[0]], close[:-1]])
    ret = close - prev_close
    high = close * (1 + np.abs(rng.normal(0.0, 0.012, days)))
    low = close * (1 - np.abs(rng.normal(0.0, 0.012, days)))
    open_ = prev_close * (1 + rng.normal(0.0, 0.004, days))
    volume = rng.integers(1_000_000, 5_000_000, size=days).astype(float)
    return pd.DataFrame({
        "date": dates,
        "open": np.round(open_, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# 周期加权共识
# ---------------------------------------------------------------------------
def _cycle_score(
    sub_scores: Dict[str, float],
    w_ts: float,
    w_cap: float,
    w_sent: float,
) -> float:
    """按设计 §5.2 的周期权重，把三子模型得分融合为本周期共识分（0~1）。"""
    total = w_ts + w_cap + w_sent
    if total <= 0:
        return 0.5
    score = (
        sub_scores.get("time_series", 0.5) * w_ts
        + sub_scores.get("capital", 0.5) * w_cap
        + sub_scores.get("sentiment", 0.5) * w_sent
    ) / total
    return clamp(score, 0.01, 0.99)


def _direction_label(direction: str, base_label: str) -> str:
    if direction == "down":
        return "下行"
    if direction == "up":
        return base_label
    return "震荡"


def _extract_drivers(sub_scores: Dict[str, float], reg: Dict[str, Any]) -> List[str]:
    """根据子模型得分高低，生成标准化核心驱动描述（设计 §3.5）。"""
    drivers: List[str] = []
    ranked = sorted(sub_scores.items(), key=lambda kv: kv[1], reverse=True)
    name_map = {
        "time_series": "产业链/基本面趋势",
        "capital": "资金面",
        "sentiment": "事件/政策舆情",
    }
    for key, val in ranked:
        if val >= 0.55:
            weight = {"w_ts": reg["w_ts"], "w_cap": reg["w_cap"], "w_sent": reg["w_sent"]}.get(
                "w_" + ("ts" if key == "time_series" else "cap" if key == "capital" else "sent"), 0
            )
            drivers.append(f"{name_map.get(key, key)}偏多(权重{int(weight * 100)}%)")
    return drivers or ["无明显主导驱动"]


# ---------------------------------------------------------------------------
# 流水线主体
# ---------------------------------------------------------------------------
class ForecastPipeline:
    """四周期前瞻预测流水线（无副作用，纯计算 + 可选持久化）。"""

    def __init__(self, engine: Optional[MultiModelForecastEngine] = None):
        self.engine = engine or MultiModelForecastEngine()

    # ---- 单标的四周期预测 ----
    def forecast_symbol(
        self,
        symbol: str,
        name: str = "",
        market: str = "A",
        kline: Optional[pd.DataFrame] = None,
        cycles: Optional[List[str]] = None,
        seed: Optional[int] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        对单个标的做四周期标准化预测。

        Returns:
            { "1w": {...}, "2w": {...}, "1m": {...}, "6m": {...} }
        每个周期字典含：direction / direction_label / consensus_score / up_probability /
        confidence / price_range / volatility_range_pct / core_drivers / main_risks /
        sub_model_scores / cycle_days / design_days。
        """
        cycles = cycles or ALL_CYCLES
        if kline is None:
            kline = build_synthetic_kline(symbol, days=130, seed=seed)

        result: Dict[str, Dict[str, Any]] = {}
        for cyc_label in cycles:
            reg = CYCLE_REGISTRY[cyc_label]
            eng = self.engine.forecast(
                symbol,
                kline,
                cycle=reg["cycle"],
                event_data={"events": events or []},
            )
            sub = {
                k: eng["sub_models"][k]["score"]
                for k in ("time_series", "capital", "sentiment")
            }
            cs = _cycle_score(sub, reg["w_ts"], reg["w_cap"], reg["w_sent"])
            up_prob = int(round(clamp(cs * 100, 1, 99)))
            # 周期越长不确定性越大 → 置信度随周期小幅衰减
            cycle_index = ALL_CYCLES.index(cyc_label)
            conf = clamp(eng["confidence"] * (1 - 0.05 * cycle_index), 0.05, 0.95)
            direction = "up" if cs > 0.55 else ("down" if cs < 0.45 else "oscillation")
            pr = eng.get("price_range", {}) or {}
            base = pr.get("base") or eng.get("current_price") or 0.0
            low_pct = round((pr.get("pessimistic", base) - base) / base * 100, 2) if base else 0.0
            high_pct = round((pr.get("optimistic", base) - base) / base * 100, 2) if base else 0.0

            result[cyc_label] = {
                "cycle": cyc_label,
                "cycle_days": reg["cycle"].days,
                "design_days": reg["design_days"],
                "direction": direction,
                "direction_label": _direction_label(direction, reg["direction_label"]),
                "consensus_score": round(cs, 4),
                "up_probability": up_prob,
                "confidence": round(conf, 4),
                "price_range": pr,
                "volatility_range_pct": {"low": low_pct, "high": high_pct},
                "core_drivers": _extract_drivers(sub, reg),
                "main_risks": eng.get("risk_warnings", []),
                "sub_model_scores": {k: round(v, 4) for k, v in sub.items()},
            }
        return result

    # ---- 映射为 decision_signals 行 ----
    def to_signal_rows(
        self,
        symbol: str,
        name: str,
        market: str,
        forecast_result: Dict[str, Dict[str, Any]],
        segment: str = "overnight",
    ) -> List[Dict[str, Any]]:
        """把四周期预测结果转为 decision_signals 持久化行（与现有表结构对齐）。"""
        rows: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        action_map = {"up": "buy", "down": "sell", "oscillation": "hold"}
        action_label_map = {"buy": "买入", "sell": "卖出", "hold": "持有"}
        for cyc_label, r in forecast_result.items():
            reg = CYCLE_REGISTRY[cyc_label]
            horizon = cyc_label
            expires = now + timedelta(days=reg["design_days"])
            action = action_map[r["direction"]]
            pr = r.get("price_range", {}) or {}
            rows.append({
                "stock_code": str(symbol),
                "stock_name": name or str(symbol),
                "market": market,
                "source_type": "dsa_forecast",
                "trigger_source": f"daily_loop:{segment}",
                "action": action,
                "action_label": action_label_map[action],
                "confidence": r["confidence"],
                "score": int(round(r["consensus_score"] * 100)),
                "horizon": horizon,
                "entry_low": pr.get("pessimistic"),
                "entry_high": pr.get("optimistic"),
                "stop_loss": pr.get("pessimistic"),
                "target_price": pr.get("optimistic"),
                "reason": f"{cyc_label} {r['direction_label']}，上涨概率 {r['up_probability']}%",
                "risk_summary": "; ".join(r["main_risks"]) or "无",
                "catalyst_summary": "; ".join(r["core_drivers"]) or "无",
                "evidence_json": json.dumps(
                    {
                        "sub_model_scores": r["sub_model_scores"],
                        "core_drivers": r["core_drivers"],
                        "volatility_range_pct": r["volatility_range_pct"],
                    },
                    ensure_ascii=False,
                ),
                "status": "active",
                "expires_at": expires,
            })
        return rows

    # ---- 批量预测（用于每日闭环） ----
    def run_batch(
        self,
        symbols: List[str],
        market: str = "A",
        cycles: Optional[List[str]] = None,
        mode: str = "synthetic",
        segment: str = "overnight",
        seed: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        批量生成四周期预测信号行。

        Args:
            mode: "synthetic" 用确定性合成 K 线；"live" 由上层注入真实数据
                  （当前 live 仍回退合成，真实数据源接入见 daily_loop）。
        """
        all_rows: List[Dict[str, Any]] = []
        for i, sym in enumerate(symbols):
            kline = None
            if mode != "synthetic":
                # live 模式：真实数据源接入点（保持接口，默认回退合成保证可用）
                logger.debug("[pipeline] live 模式暂回退合成 K 线: %s", sym)
            kline_seed = (seed + i) if seed is not None else None
            fc = self.forecast_symbol(
                sym, name=sym, market=market, kline=kline,
                cycles=cycles, seed=kline_seed,
            )
            all_rows.extend(self.to_signal_rows(sym, sym, market, fc, segment=segment))
        return all_rows

    # ---- 持久化（与现有 DecisionSignalRecord 对齐，可注入测试用轻量模型） ----
    def persist_signals(
        self,
        signal_rows: List[Dict[str, Any]],
        session: Any,
        model_cls: Optional[Any] = None,
    ) -> int:
        """
        把信号行写入数据库。

        - 生产环境 model_cls 默认取 src.storage.DecisionSignalRecord（懒加载）；
        - 测试可传入自定义轻量 SQLAlchemy 模型 + 内存 sqlite session。
        """
        if model_cls is None:
            from src.storage import DecisionSignalRecord
            model_cls = DecisionSignalRecord
        added = 0
        for row in signal_rows:
            obj = model_cls(**row)
            session.add(obj)
            added += 1
        session.commit()
        return added


# ---------------------------------------------------------------------------
# DSA 产业链传导（复用既有 propagate_shock）
# ---------------------------------------------------------------------------
def run_dsa_propagation(graph: Dict[str, Any], shock: Dict[str, Any]) -> Dict[str, Any]:
    """
    对产业链图谱做冲击传导。

    Args:
        graph: 产业链图谱（同 /industry-chains/{id} 返回：nodes/edges/companies）
        shock: {node, magnitude, kind}
    Returns:
        同 src.industry_chain_propagation.propagate_shock 的返回结构。
    """
    try:
        from src.industry_chain_propagation import propagate_shock
        return propagate_shock(graph, shock)
    except Exception as exc:  # 传导失败不应拖垮主流程
        logger.exception("DSA 产业链传导失败: %s", exc)
        return {
            "error": str(exc),
            "node_impacts": [],
            "company_impacts": [],
            "summary": {"total_nodes": 0, "impacted": 0},
        }


# 全局单例（与多模型引擎风格一致）
_pipeline: Optional[ForecastPipeline] = None


def get_pipeline() -> ForecastPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ForecastPipeline()
    return _pipeline
