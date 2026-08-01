# -*- coding: utf-8 -*-
"""图网络 / RL 策略接口 (P2-②)。"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Body

from src.graph_rl_strategy import run_graph_rl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph-rl", tags=["GraphRLStrategy"])


@router.post("/run")
def run(
    symbols: List[str] = Body(..., description="至少 2 只股票代码，用于构造相关图"),
    online: bool = Body(False, description="是否用 akshare 真实日线"),
    n: int = Body(250, description="回测长度(交易日)"),
    lookback: int = Body(20, description="动量/反转观察窗口"),
) -> dict:
    """运行图网络信号传播 + RL 多臂 Bandit 组合策略，返回相关图、RL 权重、命中率与组合回测。"""
    return run_graph_rl(symbols=symbols, online=online, n=n, lookback=lookback)
