# -*- coding: utf-8 -*-
"""策略回测接口 (P2-①)。

内置 vector 引擎（默认，零依赖）+ 可选 backtrader 引擎（自动降级）。
策略：ma_cross / momentum / mean_reversion / factor。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.strategy_backtest import list_engines, run_strategy_backtest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["StrategyBacktest"])


@router.get("/engines")
def get_engines() -> Dict[str, Any]:
    """可用回测引擎（vector 始终可用；backtrader 仅安装后可用）。"""
    return list_engines()


@router.post("/run")
def run_backtest(
    code: str = Body(..., description="6 位股票代码"),
    strategy: str = Body("ma_cross", description="ma_cross/momentum/mean_reversion/factor"),
    params: Optional[Dict[str, Any]] = Body(None, description="策略参数(如 fast/slow/lookback/window/threshold)"),
    engine: str = Body("vector", description="vector / backtrader（缺省前者；后者未安装自动降级）"),
    online: bool = Body(False, description="是否用 akshare 真实日线（默认离线合成）"),
    n: int = Body(250, description="回测长度(交易日)"),
) -> Dict[str, Any]:
    """运行策略回测，返回收益曲线、绩效指标与交易明细。"""
    return run_strategy_backtest(
        code=code, strategy=strategy, params=params,
        engine=engine, online=online, n=n,
    )
