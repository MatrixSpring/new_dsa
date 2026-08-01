# -*- coding: utf-8 -*-
"""
========================================================
组合优化与风险归因 (P1-④)

纯 numpy 实现，无 scipy 依赖：
  1. estimate_returns_cov : 估计资产预期收益与协方差矩阵
        - 在线(online=True): akshare 真实日线 → 日收益 → 年化
        - 离线(默认)      : 确定性合成相关收益(市场因子+特质噪声), 可复现
  2. mean_variance        : 均值-方差优化(min_variance / max_sharpe), 闭式解
  3. risk_parity          : 风险平价权重(等边际风险贡献, 迭代法)
  4. risk_attribution     : 风险归因(边际/成分/百分比贡献)

所有函数对缺失/异常数据做降级，绝不编造结论。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


def estimate_returns_cov(
    symbols: List[str],
    window: int = 120,
    online: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """估计预期年化收益向量与年化协方差矩阵。

    Returns:
        (exp_returns[n], cov[n,n])  n = len(symbols)
    """
    n = len(symbols)
    if n == 0:
        return np.array([]), np.zeros((0, 0))

    if online:
        try:
            returns = _online_returns(symbols, window)
            if returns is not None and returns.shape[0] >= 2:
                mu = returns.mean(axis=0) * _TRADING_DAYS
                cov = np.cov(returns, rowvar=False) * _TRADING_DAYS
                if cov.ndim == 0:
                    cov = cov.reshape(1, 1)
                return mu, cov
        except Exception as exc:  # noqa: BLE001
            logger.warning("在线收益估计失败，降级合成: %s", exc)

    return _synthetic_returns_cov(symbols, window)


def _online_returns(symbols: List[str], window: int) -> Optional[np.ndarray]:
    """用 akshare 拉取日线并计算日收益矩阵(在线)。"""
    try:
        import akshare as ak
    except Exception:  # noqa: BLE001
        return None
    series: List[np.ndarray] = []
    for s in symbols:
        try:
            df = ak.stock_zh_a_hist(symbol=s, period="daily",
                                    end_date="20500101",
                                    start_date="", adjust="qfq")
            close = df["收盘"].astype(float).values
            ret = np.diff(np.log(close[-(window + 1):]))
            series.append(ret)
        except Exception as exc:  # noqa: BLE001
            logger.debug("在线收益获取失败 %s: %s", s, exc)
            series.append(np.zeros(window))
    arr = np.array(series, dtype=float).T  # [T, n]
    return arr


def _synthetic_returns_cov(symbols: List[str], window: int) -> Tuple[np.ndarray, np.ndarray]:
    """确定性合成相关日收益 → 年化 mu/cov(市场因子+特质噪声)。"""
    n = len(symbols)
    # 以标的序列做种子，保证可复现
    seed = abs(hash("|".join(symbols))) % (2 ** 32)
    rng = np.random.default_rng(seed)
    # 市场因子
    market = rng.normal(0.0003, 0.012, size=window)
    betas = rng.uniform(0.6, 1.4, size=n)
    idio = rng.normal(0.0, 0.010, size=(window, n))
    daily = market[:, None] * betas[None, :] + idio  # [window, n]
    mu = daily.mean(axis=0) * _TRADING_DAYS
    cov = np.cov(daily, rowvar=False) * _TRADING_DAYS
    if cov.ndim == 0:
        cov = cov.reshape(1, 1)
    return mu, cov


def _regularize(cov: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """保证协方差正定(加对角扰动)。"""
    cov = np.asarray(cov, dtype=float)
    if cov.ndim == 0:
        cov = cov.reshape(1, 1)
    cov = (cov + cov.T) / 2.0
    cov += np.eye(cov.shape[0]) * eps
    return cov


def mean_variance(
    exp_returns: np.ndarray,
    cov: np.ndarray,
    objective: str = "max_sharpe",
    rf: float = 0.0,
    bounds: Tuple[float, float] = (0.0, 1.0),
) -> Dict[str, Any]:
    """均值-方差优化(闭式解)。

    objective: 'max_sharpe' | 'min_variance'
    Returns: {weights, exp_return, volatility, sharpe}
    """
    cov = _regularize(cov)
    n = len(exp_returns)
    inv = np.linalg.inv(cov)
    ones = np.ones(n)

    if objective == "min_variance":
        raw = inv @ ones / (ones @ inv @ ones)
    else:  # max_sharpe: 经典变换 y = Σ⁻¹(μ-rf), w = y / Σy
        excess = exp_returns - rf
        excess = np.where(np.abs(excess) < 1e-9, 1e-9, excess)
        y = inv @ excess
        denom = ones @ y
        if abs(denom) < 1e-12:
            y = inv @ ones
            denom = ones @ y
        raw = y / denom

    # 约束到 [lo, hi] 并归一
    lo, hi = bounds
    w = np.clip(raw, lo, hi)
    s = w.sum()
    if s <= 1e-12:
        w = ones / n
    else:
        w = w / s

    port_var = float(w @ cov @ w)
    vol = float(np.sqrt(max(port_var, 0.0)))
    exp_ret = float(w @ exp_returns)
    sharpe = float((exp_ret - rf) / vol) if vol > 1e-9 else 0.0
    return {
        "weights": [round(float(x), 4) for x in w],
        "exp_return": round(exp_ret, 4),
        "volatility": round(vol, 4),
        "sharpe": round(sharpe, 4),
        "objective": objective,
    }


def risk_parity(
    cov: np.ndarray,
    max_iter: int = 2000,
    tol: float = 1e-10,
) -> Dict[str, Any]:
    """风险平价权重(等边际/等方差贡献, Gauss-Seidel 坐标下降)。

    在风险平价解处，每个资产的方差贡献 w_i·(Σw)_i 相等(=组合方差/n)。
    逐坐标求解 a·w_i² + c_i·w_i − K = 0 的正根(K=当前组合方差/n)，原地更新。

    Returns: {weights, iterations, converged}
    """
    cov = _regularize(cov)
    n = cov.shape[0]
    w = np.ones(n) / n
    for it in range(max_iter):
        var = float(w @ cov @ w)
        K = var / n
        w_new = w.copy()
        for i in range(n):
            c_i = float((cov[i] @ w) - cov[i, i] * w[i])  # Σ_{j≠i} Σ_ij w_j
            a = float(cov[i, i])
            disc = c_i * c_i + 4.0 * a * K
            if disc < 0:
                disc = 0.0
            w_i = (-c_i + np.sqrt(disc)) / (2.0 * a)
            if w_i < 0:
                w_i = 0.0
            w[i] = w_i
        s = w.sum()
        if s <= 1e-12:
            w = np.ones(n) / n
            return {"weights": [round(1.0 / n, 4)] * n,
                    "iterations": it + 1, "converged": True}
        w = w / s
        if np.max(np.abs(w - w_new)) < tol:
            return {"weights": [round(float(x), 4) for x in w],
                    "iterations": it + 1, "converged": True}
    return {"weights": [round(float(x), 4) for x in w],
            "iterations": max_iter, "converged": False}


def risk_attribution(
    weights: np.ndarray,
    cov: np.ndarray,
) -> Dict[str, Any]:
    """风险归因：边际/成分/百分比贡献。

    Returns: {portfolio_vol, per_asset:[{weight, mcr, ccr, pct}], hhi_risk}
    """
    cov = _regularize(cov)
    w = np.asarray(weights, dtype=float)
    s = w.sum()
    if s > 1e-12:
        w = w / s
    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(max(port_var, 0.0)))
    if port_vol < 1e-9:
        n = len(w)
        return {
            "portfolio_vol": 0.0,
            "per_asset": [
                {"weight": round(float(w[i]), 4), "mcr": 0.0,
                 "ccr": 0.0, "pct": 0.0}
                for i in range(n)
            ],
            "hhi_risk": 0.0,
        }
    sigma_w = cov @ w
    mcr = sigma_w / port_vol            # 边际风险贡献
    ccr = w * mcr                       # 成分风险贡献
    pct = ccr / port_vol                # 百分比贡献(Σ=1)

    per = [
        {
            "weight": round(float(w[i]), 4),
            "mcr": round(float(mcr[i]), 4),
            "ccr": round(float(ccr[i]), 4),
            "pct": round(float(pct[i]), 4),
        }
        for i in range(len(w))
    ]
    hhi = float(sum(float(p) ** 2 for p in pct))  # 风险集中度
    return {
        "portfolio_vol": round(port_vol, 4),
        "per_asset": per,
        "hhi_risk": round(hhi, 4),
    }


def optimize_portfolio(
    symbols: List[str],
    objective: str = "max_sharpe",
    online: bool = False,
    rf: float = 0.0,
    window: int = 120,
    risk_parity_mode: bool = False,
) -> Dict[str, Any]:
    """组合优化主入口。

    risk_parity_mode=True 时返回风险平价权重(忽略 objective)。
    """
    mu, cov = estimate_returns_cov(symbols, window=window, online=online)
    if len(symbols) == 0:
        return {"error": "symbols 为空", "symbols": symbols}
    if risk_parity_mode:
        rp = risk_parity(cov)
        w = np.array(rp["weights"], dtype=float)
        port_var = float(w @ cov @ w)
        vol = float(np.sqrt(max(port_var, 0.0)))
        exp_ret = float(w @ mu)
        attr = risk_attribution(w, cov)
        return {
            "symbols": symbols,
            "method": "risk_parity",
            "weights": rp["weights"],
            "exp_return": round(exp_ret, 4),
            "volatility": round(vol, 4),
            "sharpe": round((exp_ret - rf) / vol, 4) if vol > 1e-9 else 0.0,
            "risk_attribution": attr,
            "converged": rp["converged"],
        }
    mv = mean_variance(mu, cov, objective=objective, rf=rf)
    w = np.array(mv["weights"], dtype=float)
    attr = risk_attribution(w, cov)
    return {
        "symbols": symbols,
        "method": objective,
        "weights": mv["weights"],
        "exp_return": mv["exp_return"],
        "volatility": mv["volatility"],
        "sharpe": mv["sharpe"],
        "risk_attribution": attr,
    }
