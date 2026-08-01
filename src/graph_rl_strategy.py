# -*- coding: utf-8 -*-
"""图网络 / RL 策略 (P2-②, 对标 graph-learning + reinforcement learning 选股)。

纯 numpy 实现，零外部依赖（networkx/torch 缺失时亦可用）：

  1) 图网络：用多资产日收益相关性构造资产关联图（邻接矩阵），对逐期信号做
     图传播平滑（label propagation），利用邻居信息对单资产信号去噪 —— 即
     "graph network" 思路的轻量落地。
  2) RL 策略：把 momentum / mean_reversion / graph_smoothed 三个基础信号作为
     多臂 Bandit 的 arm，按逐期命中奖励用指数权重(Hedge)更新各 arm 权重，
     自适应选出最优信号组合 —— 即强化学习思路的轻量落地。

数据来源：src.market_data.fetch_returns_matrix（注入共享 market 因子，保证相关性）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from src.market_data import fetch_returns_matrix

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 图网络：相关图构建 + 信号传播平滑
# --------------------------------------------------------------------------- #
def build_correlation_graph(returns: np.ndarray, thr: float = 0.3) -> np.ndarray:
    """由 (T,N) 收益矩阵构造加权相关邻接矩阵（|corr|>thr 保留，对角置 0）。"""
    corr = np.corrcoef(returns.T)
    corr = np.nan_to_num(corr)
    adj = np.where(np.abs(corr) > thr, corr, 0.0)
    np.fill_diagonal(adj, 0.0)
    return adj


def graph_smooth_signals(signals: np.ndarray, adj: np.ndarray,
                         alpha: float = 0.5, iters: int = 3) -> np.ndarray:
    """逐期对信号向量 (T,N) 做图传播平滑（邻居均值加权）。"""
    out = signals.T.astype(float).copy()  # (N,T)
    deg = adj.sum(axis=1)
    for _ in range(iters):
        prop = adj @ out
        prop = np.where(deg[:, None] > 0, prop / np.maximum(deg, 1.0)[:, None], 0.0)
        out = (1 - alpha) * out + alpha * prop
    return out.T  # (T,N)


# --------------------------------------------------------------------------- #
# RL：多臂 Bandit（指数权重 Hedge）
# --------------------------------------------------------------------------- #
class RLBandit:
    def __init__(self, arms: List[str], eta: float = 0.15):
        self.arms = arms
        self.eta = eta
        self.w = np.ones(len(arms), dtype=float)
        self.cum = {a: 0.0 for a in arms}
        self.count = {a: 0 for a in arms}
        self.traj: List[Dict[str, float]] = []

    def _idx(self, arm: str) -> int:
        return self.arms.index(arm)

    def select(self) -> str:
        """按当前权重 softmax 选 arm（确定性取最大权重，便于复现）。"""
        p = np.exp(self.w)
        p = p / p.sum()
        self._last_p = p
        return self.arms[int(np.argmax(p))]

    def reward(self, arm: str, r: float) -> None:
        self.cum[arm] += r
        self.count[arm] += 1
        self.w[self._idx(arm)] += self.eta * r

    def weights(self) -> Dict[str, float]:
        p = np.exp(self.w)
        p = p / p.sum()
        return {a: round(float(x), 4) for a, x in zip(self.arms, p)}

    def snapshot(self) -> None:
        self.traj.append(self.weights())


# --------------------------------------------------------------------------- #
# 统一入口
# --------------------------------------------------------------------------- #
def run_graph_rl(symbols: List[str], online: bool = False,
                 n: int = 250, lookback: int = 20) -> Dict[str, Any]:
    if len(symbols) < 2:
        raise ValueError("图网络/RL 策略至少需要 2 只标的以构造相关图")
    data = fetch_returns_matrix(symbols, n=n, online=online)
    R = data["returns"]          # (T,N)
    close = data["close"]        # (T,N)
    T, N = R.shape

    # 基础方向信号（逐期逐资产）
    mom = np.zeros((T, N))
    mr = np.zeros((T, N))
    for j in range(N):
        c = close[:, j]
        ret_lb = np.zeros(T)
        ret_lb[lookback:] = c[lookback:] / c[:-lookback] - 1.0
        mom[:, j] = np.sign(ret_lb)
        mr[:, j] = -np.sign(ret_lb)  # 反转预期

    # 图网络：相关图 + 对 momentum 信号做图传播平滑
    adj = build_correlation_graph(R)
    graph_sig = graph_smooth_signals(mom, adj, alpha=0.5, iters=3)
    graph_dir = np.sign(graph_sig)

    arms = {"momentum": mom, "mean_reversion": mr, "graph": graph_dir}

    # RL Bandit：逐期评估各 arm 对下一期方向的命中率并更新权重
    start = lookback + 2
    bandit = RLBandit(list(arms.keys()))
    arm_hits: Dict[str, List[float]] = {k: [] for k in arms}
    for t in range(start, T - 1):
        bandit.select()
        actual = np.sign(R[t + 1])  # (N,)
        for k, sig in arms.items():
            pred = np.sign(sig[t])
            r = float(np.mean((pred * actual) > 0))
            arm_hits[k].append(r)
            bandit.reward(k, r)
        bandit.snapshot()

    weights = bandit.weights()
    acc_summary = {
        k: round(float(np.mean(v)) * 100, 2) if v else None
        for k, v in arm_hits.items()
    }

    # 组合回测：加权合成方向信号 → 等权组合 next-day 多空
    combined = np.zeros((T, N))
    for k in arms:
        combined += weights[k] * arms[k]
    port_dir = np.sign(np.mean(combined, axis=1))  # (T,)
    port_ret = np.mean(R, axis=1)
    strat = np.zeros(T)
    strat[1:] = port_dir[:-1] * port_ret[1:]
    equity = np.cumprod(1.0 + strat) * 1_000_000.0
    total = float(equity[-1] / equity[0] - 1.0)
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1.0).min())
    sd = strat[1:].std()
    sharpe = float(strat[1:].mean() / (sd + 1e-12) * np.sqrt(252))
    step = max(1, T // 60)
    eq_curve = [round(float(x), 2) for x in equity[::step].tolist()]

    # 相关图摘要（仅保留显著边，避免大矩阵）
    edges = []
    for i in range(N):
        for j in range(i + 1, N):
            if adj[i, j] != 0:
                edges.append({
                    "a": symbols[i], "b": symbols[j],
                    "corr": round(float(adj[i, j]), 3),
                })
    edges.sort(key=lambda e: abs(e["corr"]), reverse=True)

    return {
        "symbols": symbols,
        "source": data.get("source"),
        "lookback": lookback,
        "corr_edges": edges,
        "rl_weights": weights,
        "rl_weights_trajectory": bandit.traj[-10:],
        "arm_accuracy_pct": acc_summary,
        "portfolio": {
            "total_return_pct": round(total * 100, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown_pct": round(mdd * 100, 2),
            "final_equity": round(float(equity[-1]), 2),
            "bars": T,
            "equity_curve": eq_curve,
        },
    }
