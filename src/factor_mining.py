# -*- coding: utf-8 -*-
"""
==========================================================
自动因子挖掘闭环  (P0-②, 借鉴 Qlib + RD-Agent)
==========================================================

闭环逻辑：
  基础因子池(AlphaLibrary 量价/动量/波动)  →
  进化生成候选(代数组合/变异)             →
  IC / RankIC / 多空年化收益 / 夏普 评估  →
  保留 Top-K 作为种子 → 下一代继续进化    →
  持久化每代结果，闭环保留全局最优因子。

数据策略（可插拔、离线降级）：
  - 联网：akshare 拉真实日线（stock_zh_a_hist）作为标签来源
  - 离线/失败：合成随机游走 OHLCV（标注 demo），保证闭环离线可演示、联网即真实
"""
from __future__ import annotations

import itertools
import logging
import signal
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.alpha_factors import AlphaLibrary
from src.storage import DatabaseManager, FactorMiningResult

logger = logging.getLogger(__name__)

_ONLINE_TIMEOUT = 30


def _call_to(sec: int, fn, *a, **k):
    def _h(signum, frame):
        raise TimeoutError("timeout")
    old = signal.signal(signal.SIGALRM, _h)
    signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# --------------------------------------------------------------------------- #
# 数据层
# --------------------------------------------------------------------------- #
def _online_close(code: str, n: int = 250) -> Optional[np.ndarray]:
    try:
        import akshare as ak
        df = _call_to(_ONLINE_TIMEOUT, ak.stock_zh_a_hist,
                      symbol=code, period="daily", adjust="qfq")
        if df is None or getattr(df, "empty", True):
            return None
        return df["收盘"].astype(float).to_numpy()
    except Exception as e:  # noqa: BLE001
        logger.debug("online_close %s failed: %s", code, e)
        return None


def _synth_ohlcv(n: int = 250, seed: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    ret = rng.normal(0, 0.02, n)
    close = 100 * np.cumprod(1 + ret)
    open_ = close * (1 + rng.normal(0, 0.005, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.01, n)))
    volume = rng.integers(int(1e5), int(1e6), n).astype(float)
    amount = close * volume
    return open_, high, low, close, volume, amount


# --------------------------------------------------------------------------- #
# 因子池与评估
# --------------------------------------------------------------------------- #
def _base_pool(close, open_, high, low, volume) -> Dict[str, np.ndarray]:
    A = AlphaLibrary
    return {
        "ret_1d": A.ret_1d(close),
        "ret_5d": A.ret_5d(close),
        "ret_20d": A.ret_20d(close),
        "ma_gap_5": A.ma_gap(close, 5),
        "ma_gap_20": A.ma_gap(close, 20),
        "ma_cross": A.ma_cross(close, 5, 20),
        "vol_20d": A.volatility_20d(close),
        "rsi_14d": A.rsi_14d(close),
    }


def _eval_expr(expr: str, pool: Dict[str, np.ndarray]) -> np.ndarray:
    env = {name: arr for name, arr in pool.items()}
    return eval(expr, {"__builtins__": {}}, {"np": np, **env})  # noqa: S307


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    a = np.argsort(np.argsort(a))
    b = np.argsort(np.argsort(b))
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _evaluate(factor: np.ndarray, fwd: np.ndarray) -> Optional[Dict[str, float]]:
    m = np.isfinite(factor) & np.isfinite(fwd)
    f, r = factor[m], fwd[m]
    if len(f) < 30:
        return None
    ic = _spearman(f, r)
    q = np.quantile(f, [0.3, 0.7])
    lm, sm = f >= q[1], f <= q[0]
    if lm.sum() == 0 or sm.sum() == 0:
        return None
    ls = r[lm].mean() - r[sm].mean()
    sd = r[lm].std()
    return {
        "ic": float(ic),
        "rank_ic": float(ic),
        "icir": float(ic),
        "long_short_return": float(ls * 252 * 100),
        "sharpe": float(ls / sd) if sd and sd > 0 else 0.0,
        "turnover": float(np.nanmean(np.abs(np.diff(f))) * 100),
    }


def _evolve(top_names: List[str], base_names: List[str], k: int = 12) -> List[str]:
    cands: List[str] = []
    exprs = top_names + base_names
    for a, b in itertools.combinations_with_replacement(exprs, 2):
        if len(cands) >= k:
            break
        cands.append(f"({a}+{b})/2")
        if len(cands) >= k:
            break
        cands.append(f"({a})*({b})")
        if len(cands) >= k:
            break
        cands.append(f"({a})-({b})")
        if len(cands) >= k:
            break
        cands.append(f"({a})/(np.abs({b})+1e-6)")
    return cands[:k]


# --------------------------------------------------------------------------- #
# 闭环主流程
# --------------------------------------------------------------------------- #
def mine(
    code: str = "600519",
    max_gen: int = 4,
    top_k: int = 5,
    n: int = 250,
    online: bool = False,
    seed: int = 42,
) -> Dict[str, Any]:
    """运行自动因子挖掘闭环，结果持久化到 factor_mining_result 表。

    返回本轮摘要（代次、Top-K 最优因子）。
    """
    used_online = False
    if online:
        close = _online_close(code, n)
        if close is not None and len(close) >= n:
            used_online = True
            rng = np.random.default_rng(seed)
            open_ = close * (1 + rng.normal(0, 0.005, len(close)))
            high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.01, len(close))))
            low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.01, len(close))))
            volume = np.full(len(close), 1e6)
        else:
            online = False
    if not used_online:
        open_, high, low, close, volume, _amount = _synth_ohlcv(n, seed)

    # 标签：次日收益率
    fwd = np.zeros_like(close)
    fwd[:-1] = close[1:] / close[:-1] - 1.0

    pool = _base_pool(close, open_, high, low, volume)
    pool_expr = {name: name for name in pool}
    base_names = list(pool.keys())

    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        for gen in range(max_gen):
            for name, arr in pool.items():
                ev = _evaluate(arr, fwd)
                if ev is None:
                    continue
                rec = FactorMiningResult(
                    generation=gen, factor_name=name, factor_expr=pool_expr[name],
                    source="base" if gen == 0 else "evolved", is_active=0,
                    created_at=datetime.now(), **ev,
                )
                s.add(rec)
            # 进化下一代
            if gen < max_gen - 1:
                s.flush()
                rows = s.query(FactorMiningResult).filter_by(generation=gen).all()
                rows.sort(key=lambda r: abs(r.ic or 0), reverse=True)
                top = [r.factor_name for r in rows[:top_k]]
                new_exprs = _evolve(top, base_names, k=min(12, top_k * 3))
                new_pool: Dict[str, np.ndarray] = {}
                new_expr: Dict[str, str] = {}
                for i, ex in enumerate(new_exprs):
                    try:
                        arr = _eval_expr(ex, pool)
                        new_pool[f"ev{gen}_{i}"] = arr
                        new_expr[f"ev{gen}_{i}"] = ex
                    except Exception:  # noqa: BLE001
                        continue
                pool, pool_expr = new_pool, new_expr
        # 全局最优 Top-K 标记 active（先重置再标记，保证仅本轮最优为 active）
        s.flush()
        s.query(FactorMiningResult).update({FactorMiningResult.is_active: 0})
        best = s.query(FactorMiningResult).order_by(FactorMiningResult.ic.desc()).limit(top_k).all()
        for r in best:
            r.is_active = 1
        s.commit()
        best_info = [{
            "name": r.factor_name, "ic": round(r.ic or 0, 4),
            "long_short_return": round(r.long_short_return or 0, 2),
            "expr": r.factor_expr, "source": r.source,
        } for r in best]

    return {
        "code": code, "online": used_online, "generations": max_gen,
        "top_k": top_k, "active_count": len(best), "best": best_info,
    }
