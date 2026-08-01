# -*- coding: utf-8 -*-
"""人格化投资 Agent 决策层接口 (P1-①)。

POST /api/v1/persona-analysis?code=  触发多角色 Agent(估值/基本面/技术/情绪/风控)
并行研判 + PM 汇总，返回加权共识、最终建议与风险等级。
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict

from fastapi import APIRouter, Query

from src.persona_agents import analyze_personas
from src.storage import CompanyProfile, DatabaseManager, FactorMiningResult

router = APIRouter()


def _cr_to_dict(cr) -> Dict[str, Any]:
    return {
        "stock_code": cr.stock_code,
        "consensus": cr.consensus,
        "consensus_score": cr.consensus_score,
        "agreement_ratio": cr.agreement_ratio,
        "key_contradictions": cr.key_contradictions,
        "final_recommendation": cr.final_recommendation,
        "risk_level": cr.risk_level,
        "total_duration_ms": cr.total_duration_ms,
        "agents": {k: dataclasses.asdict(v) for k, v in cr.agents.items()},
    }


@router.post("/persona-analysis")
def persona_analysis(code: str = Query("600519", description="6 位股票代码")) -> Dict[str, Any]:
    """人格化 Agent 决策层：5 角色并行研判 + PM 汇总。"""
    m = DatabaseManager.get_instance()
    ctx: Dict[str, Any] = {}
    with m.session_scope() as s:
        row = s.get(CompanyProfile, code)
        if row:
            ctx = row.to_dict()
        fm = (s.query(FactorMiningResult)
              .filter_by(is_active=1)
              .order_by(FactorMiningResult.ic.desc())
              .first())
        if fm:
            ctx["factor_lsr"] = fm.long_short_return
    rep = analyze_personas(code, ctx)
    return _cr_to_dict(rep)
