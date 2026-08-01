# -*- coding: utf-8 -*-
"""组合优化与风险归因接口 (P1-④)。

- POST /portfolio/optimize        均值-方差(max_sharpe/min_variance)或风险平价
- POST /portfolio/risk-attribution 给定权重(或等权)的风险贡献分解
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body

from src.portfolio_optimizer import optimize_portfolio, risk_attribution

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/optimize")
def optimize(
    symbols: List[str] = Body(..., description="标的代码列表"),
    objective: str = Body("max_sharpe", description="max_sharpe / min_variance"),
    risk_parity_mode: bool = Body(False, description="True 时返回风险平价权重"),
    online: bool = Body(False, description="是否用真实日线估计(默认合成可复现)"),
    risk_free: float = Body(0.02, description="无风险利率(年化)"),
    window: int = Body(120, description="收益估计窗口(交易日)"),
) -> Dict[str, Any]:
    """组合优化：返回目标权重 + 预期收益/波动/夏普 + 风险归因。"""
    if not symbols:
        return {"error": "symbols 不能为空"}
    return optimize_portfolio(
        symbols=symbols, objective=objective, online=online,
        rf=risk_free, window=window, risk_parity_mode=risk_parity_mode,
    )


@router.post("/risk-attribution")
def attribution(
    symbols: List[str] = Body(..., description="标的代码列表"),
    weights: Optional[List[float]] = Body(None, description="权重列表(与 symbols 等长);缺省等权"),
    online: bool = Body(False, description="是否用真实日线估计协方差"),
    window: int = Body(120, description="协方差估计窗口"),
) -> Dict[str, Any]:
    """风险归因：把组合波动分解到每个标的(边际/成分/百分比贡献)。"""
    if not symbols:
        return {"error": "symbols 不能为空"}
    from src.portfolio_optimizer import estimate_returns_cov
    mu, cov = estimate_returns_cov(symbols, window=window, online=online)
    if weights is None:
        weights = [1.0 / len(symbols)] * len(symbols)
    if len(weights) != len(symbols):
        return {"error": "weights 与 symbols 长度不一致"}
    attr = risk_attribution(weights, cov)
    return {"symbols": symbols, "weights": weights, **attr}
