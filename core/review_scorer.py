# -*- coding: utf-8 -*-
"""
==================================================
预测复盘归因自动打分 — core/review_scorer.py
==================================================
设计文档: DSA-CRAWL-LLM-MERGE-V1.0 §四「预测复盘归因自动打分」
          （升级原有【预测复盘模块】：事件因果归档 + 三层复盘）

输入：单个多周期预测快照（来自 core/dsa_daily_pipeline 的 forecast 输出）
      + 实际观测（方向 / 区间收益）。
输出：逐周期 方向命中 / 区间命中 / 准确率 评分 + 三层归因
      （数据层 / 模型层 / 逻辑层），以及聚合统计。

三层归因定义：
  ① 数据层：数据采集缺失/错误 → 以 consensus_score / up_probability 极端度代理
  ② 模型层：DSA 传导系数不合理 → 以 confidence + 方向是否正确代理
  ③ 逻辑层：事件传导路径预判错误 → 方向对但区间错 → 传导路径部分偏差

设计原则：纯逻辑、无 DB 依赖，便于沙箱验证；持久化由 endpoint 层负责。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_RECORDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "review_records.json",
)

# 预测方向 → 期望实际方向
_DIRECTION_EXPECT: Dict[str, str] = {"up": "up", "down": "down", "oscillation": "oscillation"}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _direction_hit(predicted: str, actual: str) -> bool:
    if predicted == actual:
        return True
    # oscillation 视为温和双向，实际小幅涨跌也算命中
    if predicted == "oscillation" and actual in ("up", "down"):
        return True
    if actual == "oscillation" and predicted in ("up", "down"):
        return True
    return False


def _range_hit(actual_return_pct: float, band: Dict[str, float]) -> bool:
    low = float(band.get("low", -1e9))
    high = float(band.get("high", 1e9))
    return low <= actual_return_pct <= high


def score_cycle(cycle_input: Dict[str, Any]) -> Dict[str, Any]:
    """对单个周期打分 + 三层归因。"""
    cycle = cycle_input.get("cycle", "unknown")
    predicted = cycle_input.get("direction", "oscillation")
    consensus = float(cycle_input.get("consensus_score", 0.5))
    up_prob = float(cycle_input.get("up_probability", 50.0))
    confidence = float(cycle_input.get("confidence", 0.5))
    band = cycle_input.get("volatility_range_pct", {}) or {}
    actual = cycle_input.get("actual_direction", "oscillation")
    actual_return = float(cycle_input.get("actual_return_pct", 0.0))

    dhit = _direction_hit(predicted, actual)
    rhit = _range_hit(actual_return, band)
    if dhit and rhit:
        accuracy = 1.0
    elif dhit and not rhit:
        accuracy = 0.5
    else:
        accuracy = 0.0

    # ① 数据层健康度：共识分越高、涨跌概率不过度极端 → 数据更可信
    extremeness = abs(up_prob - 50) / 50.0  # 0~1
    data_health = _clamp(consensus - 0.25 * extremeness * (1 - consensus))
    data_note = (
        "共识分充足、概率不过度极端" if data_health >= 0.6
        else "共识分偏低或概率极端，数据采集/交叉验证不足"
    )

    # ② 模型层健康度：方向正确且置信度高 → 模型稳定
    if dhit:
        model_health = _clamp(confidence)
        model_note = "方向命中，DSA 传导系数稳定"
    else:
        model_health = _clamp(confidence * 0.3)
        model_note = "方向判错，DSA 传导系数或权重需复盘"

    # ③ 逻辑层健康度：方向对但区间错 → 传导路径部分偏差
    if dhit and rhit:
        logic_health = 1.0
        logic_note = "传导路径与区间判断一致"
    elif dhit and not rhit:
        logic_health = 0.5
        logic_note = "方向正确但波动区间偏差，事件传导幅度预判不足"
    else:
        logic_health = 0.2
        logic_note = "传导方向与行情背离，事件-传导-行情链路需重梳"

    return {
        "cycle": cycle,
        "predicted_direction": predicted,
        "actual_direction": actual,
        "actual_return_pct": round(actual_return, 4),
        "direction_hit": dhit,
        "range_hit": rhit,
        "accuracy_score": accuracy,
        "attribution": {
            "data_layer": {"score": round(data_health, 3), "note": data_note},
            "model_layer": {"score": round(model_health, 3), "note": model_note},
            "logic_layer": {"score": round(logic_health, 3), "note": logic_note},
        },
    }


def score_forecast(symbol: str, name: str, cycles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对一条预测（多个周期）打分并聚合。"""
    scored = [score_cycle(c) for c in cycles]
    n = len(scored) or 1
    accuracy_rate = sum(s["accuracy_score"] for s in scored) / n
    avg_layers = {
        "data_layer": sum(s["attribution"]["data_layer"]["score"] for s in scored) / n,
        "model_layer": sum(s["attribution"]["model_layer"]["score"] for s in scored) / n,
        "logic_layer": sum(s["attribution"]["logic_layer"]["score"] for s in scored) / n,
    }
    weakest = min(avg_layers, key=lambda k: avg_layers[k])
    return {
        "symbol": symbol,
        "name": name,
        "scored_at": time.time(),
        "cycles": scored,
        "accuracy_rate": round(accuracy_rate, 4),
        "avg_layer_health": {k: round(v, 3) for k, v in avg_layers.items()},
        "weakest_layer": weakest,
        "sample_size": len(scored),
    }


# ---- 记录持久化（endpoint 层调用） ----
def load_records(path: str = DEFAULT_RECORDS_PATH) -> List[Dict[str, Any]]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[review_scorer] 读取记录失败: %s", exc)
    return []


def append_record(record: Dict[str, Any], path: str = DEFAULT_RECORDS_PATH) -> None:
    records = load_records(path)
    records.append(record)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[review_scorer] 写入记录失败: %s", exc)


def aggregate_report(records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if records is None:
        records = load_records()
    if not records:
        return {
            "total": 0,
            "accuracy_rate": None,
            "avg_layer_health": {"data_layer": None, "model_layer": None, "logic_layer": None},
            "weakest_layer": None,
            "by_cycle": {},
        }
    total = len(records)
    acc = sum(r.get("accuracy_rate", 0) for r in records) / total
    layers = {"data_layer": [], "model_layer": [], "logic_layer": []}
    by_cycle: Dict[str, Dict[str, Any]] = {}
    for r in records:
        for k in layers:
            layers[k].append(r.get("avg_layer_health", {}).get(k, 0))
        for c in r.get("cycles", []):
            cyc = c["cycle"]
            bucket = by_cycle.setdefault(cyc, {"n": 0, "acc_sum": 0.0, "dir_hit": 0, "range_hit": 0})
            bucket["n"] += 1
            bucket["acc_sum"] += c.get("accuracy_score", 0)
            bucket["dir_hit"] += 1 if c.get("direction_hit") else 0
            bucket["range_hit"] += 1 if c.get("range_hit") else 0
    avg_layers = {k: round(sum(v) / len(v), 3) for k, v in layers.items()} if any(layers.values()) else {k: 0 for k in layers}
    weakest = min(avg_layers, key=lambda k: avg_layers[k]) if avg_layers else None
    by_cycle_out = {
        cyc: {
            "n": b["n"],
            "accuracy_rate": round(b["acc_sum"] / b["n"], 3),
            "direction_hit_rate": round(b["dir_hit"] / b["n"], 3),
            "range_hit_rate": round(b["range_hit"] / b["n"], 3),
        }
        for cyc, b in by_cycle.items()
    }
    return {
        "total": total,
        "accuracy_rate": round(acc, 4),
        "avg_layer_health": avg_layers,
        "weakest_layer": weakest,
        "by_cycle": by_cycle_out,
    }


__all__ = [
    "score_cycle",
    "score_forecast",
    "load_records",
    "append_record",
    "aggregate_report",
]
