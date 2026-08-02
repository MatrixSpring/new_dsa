# -*- coding: utf-8 -*-
"""
==================================================
预测复盘归因 API — api/v1/endpoints/review.py
==================================================
设计文档: 预测复盘归因自动打分（三层复盘：数据层/模型层/逻辑层）

端点（统一前缀 /api/v1/review）:
  POST /score   单条预测（多周期）打分 + 持久化
  GET  /report  聚合统计（准确率 / 各层健康度 / 分周期命中率）
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.review_scorer import aggregate_report, append_record, score_forecast

router = APIRouter()


class CycleInput(BaseModel):
    cycle: str = Field(..., description="周期键: 1w/2w/1m/6m")
    direction: str = Field("oscillation", description="预测方向: up/down/oscillation")
    consensus_score: float = 0.5
    up_probability: float = 50.0
    confidence: float = 0.5
    volatility_range_pct: Dict[str, float] = Field(default_factory=dict, description="{low, high}")
    actual_direction: str = Field("oscillation", description="实际方向: up/down/oscillation")
    actual_return_pct: float = 0.0


class ScoreRequest(BaseModel):
    symbol: str
    name: str = ""
    cycles: List[CycleInput] = Field(..., min_length=1)


@router.post("/score")
def score(req: ScoreRequest):
    cycles = [c.model_dump() for c in req.cycles]
    result = score_forecast(req.symbol, req.name, cycles)
    # 持久化用于后续聚合报告
    append_record(result)
    return {"code": 0, "msg": "ok", "data": result}


@router.get("/report")
def report():
    stats = aggregate_report()
    return {"code": 0, "msg": "ok", "data": stats}
