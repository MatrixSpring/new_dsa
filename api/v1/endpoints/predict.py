# -*- coding: utf-8 -*-
"""
===================================
多周期前瞻预测统一接口（设计 §4.3 第三层）
===================================

统一入口：POST /api/v1/predict/multi-cycle
- 对一批标的，输出设计 §3.5 标准化模板的四周期预测
  （方向 / 波动区间 / 上涨概率 / 核心驱动 / 主要风险 / 置信度）。
- 默认 mode="synthetic"：用确定性合成 K 线，离线可用、可复现；
  mode="live"：保留真实数据源接入点（当前回退合成，待数据网关补全）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.dsa_daily_pipeline import ALL_CYCLES, ForecastPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


class MultiCycleRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1, max_length=50, description="标的代码列表")
    market: str = Field("A", description="市场: A / HK / US")
    cycles: Optional[List[str]] = Field(
        None, description=f"指定周期，默认全部 {ALL_CYCLES}"
    )
    mode: str = Field("synthetic", description="synthetic(离线合成) | live(真实数据)")
    seed: Optional[int] = Field(None, description="合成数据随机种子（便于复现）")


class SymbolCycleForecast(BaseModel):
    cycle: str
    cycle_days: int
    design_days: int
    direction: str
    direction_label: str
    consensus_score: float
    up_probability: int
    confidence: float
    price_range: Dict[str, float]
    volatility_range_pct: Dict[str, float]
    core_drivers: List[str]
    main_risks: List[str]
    sub_model_scores: Dict[str, float]


class SymbolForecast(BaseModel):
    symbol: str
    name: str
    market: str
    cycles: Dict[str, SymbolCycleForecast]


class MultiCycleResponse(BaseModel):
    code: int = 200
    msg: str = "ok"
    data: Dict[str, object]


@router.post(
    "/multi-cycle",
    response_model=MultiCycleResponse,
    summary="多周期前瞻预测统一接口",
    description="对一批标的输出 1周/半月/1月/半年 四周期标准化前瞻预测（设计 §3/§4）。",
)
def multi_cycle_predict(req: MultiCycleRequest):
    cycles = req.cycles or ALL_CYCLES
    invalid = [c for c in cycles if c not in ALL_CYCLES]
    if invalid:
        return MultiCycleResponse(
            code=400,
            msg=f"非法周期: {invalid}，可选: {ALL_CYCLES}",
            data={},
        )

    pipeline = ForecastPipeline()
    symbols_out: Dict[str, object] = {}
    for sym in req.symbols:
        fc = pipeline.forecast_symbol(
            sym,
            name=sym,
            market=req.market,
            cycles=cycles,
            seed=req.seed,
        )
        # pydantic 序列化：把内层 dict 转成 SymbolCycleForecast
        symbols_out[sym] = {
            "symbol": sym,
            "name": sym,
            "market": req.market,
            "cycles": {
                cyc: SymbolCycleForecast(**val) for cyc, val in fc.items()
            },
        }

    return MultiCycleResponse(
        code=200,
        msg="ok",
        data={
            "symbols": symbols_out,
            "cycles_requested": cycles,
            "mode": req.mode,
            "generated_at": datetime.now().isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# DSA 产业链传导接口（设计 §2/§4 第一层产业链维护联动）
# ---------------------------------------------------------------------------
class DsaPropagationRequest(BaseModel):
    graph: Dict[str, object] = Field(..., description="产业链图谱 nodes/edges/companies")
    shock: Dict[str, object] = Field(..., description="冲击 {node, magnitude, kind}")


class DsaPropagationResponse(BaseModel):
    code: int = 200
    msg: str = "ok"
    data: Dict[str, object]


@router.post(
    "/dsa-propagation",
    response_model=DsaPropagationResponse,
    summary="DSA 产业链冲击传导",
    description="对产业链图谱做 BFS 冲击传导，返回环节/公司影响与汇总。",
)
def dsa_propagation(req: DsaPropagationRequest):
    from core.dsa_daily_pipeline import run_dsa_propagation

    result = run_dsa_propagation(req.graph, req.shock)
    return DsaPropagationResponse(code=200, msg="ok", data=result)
