# -*- coding: utf-8 -*-
"""自动因子挖掘闭环只读/触发接口 (P0-②)。

GET  /api/v1/factor-mining/results   查看挖掘结果(支持 generation / active_only 过滤)
POST /api/v1/factor-mining/run       触发一轮挖掘(code / max_gen / top_k / online)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.storage import DatabaseManager, FactorMiningResult

router = APIRouter()


@router.get("/factor-mining/results")
def list_results(
    generation: Optional[int] = Query(None, description="按代次过滤"),
    active_only: bool = Query(False, description="仅返回当前保留的最优因子"),
) -> Dict[str, Any]:
    """查看因子挖掘结果。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = select(FactorMiningResult)
        if generation is not None:
            q = q.where(FactorMiningResult.generation == generation)
        if active_only:
            q = q.where(FactorMiningResult.is_active == 1)
        q = q.order_by(FactorMiningResult.ic.desc())
        rows = s.execute(q).scalars().all()
        return {"total": len(rows), "items": [r.to_dict() for r in rows]}


@router.post("/factor-mining/run")
def run_mining(
    code: str = Query("600519", description="股票代码(6位)"),
    max_gen: int = Query(4, ge=1, le=10, description="进化代次"),
    top_k: int = Query(5, ge=1, le=20, description="每代保留 Top-K"),
    online: bool = Query(False, description="联网用真实日线评估(默认离线合成)"),
) -> Dict[str, Any]:
    """触发一轮自动因子挖掘闭环。"""
    from src.factor_mining import mine

    return mine(code=code, online=online, max_gen=max_gen, top_k=top_k)
