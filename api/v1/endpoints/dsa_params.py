# -*- coding: utf-8 -*-
"""
==================================================
DSA 全局模型参数管控 — api/v1/endpoints/dsa_params.py
==================================================
设计文档 §5.3：DSA 全局参数（递归深度 / 系数阈值 / 风险衰减）统一管控。

端点（统一前缀 /api/v1/dsa-params）:
  GET  /          列出全部全局参数
  PUT  /{key}     设置单个参数（create-or-update）
  POST /seed      写入默认种子参数（首次部署）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body

from src.storage import DatabaseManager, DsaGlobalParam

logger = logging.getLogger(__name__)

router = APIRouter()

# 默认种子参数（设计 §3.1 建议值）
_SEED: List[Dict[str, Any]] = [
    {'param_key': 'recursion_depth', 'param_value': 20.0, 'param_desc': 'DSA 传导递归深度上限'},
    {'param_key': 'coeff_threshold', 'param_value': 0.85, 'param_desc': '双向传导系数阈值'},
    {'param_key': 'bearish_weight', 'param_value': 0.7, 'param_desc': '利空情景权重'},
    {'param_key': 'risk_decay', 'param_value': 0.6, 'param_desc': '风险随时间衰减系数'},
    {'param_key': 'shock_magnitude', 'param_value': 0.2, 'param_desc': '默认冲击幅度(±20%)'},
]


def _envelope(data: Dict[str, Any]) -> Dict[str, Any]:
    return data


@router.get('/')
def list_dsa_params() -> Dict[str, Any]:
    """列出全部 DSA 全局参数。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.query(DsaGlobalParam).order_by(DsaGlobalParam.id).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


@router.post('/seed')
def seed_dsa_params() -> Dict[str, Any]:
    """写入默认种子参数（已存在则跳过）。"""
    m = DatabaseManager.get_instance()
    created = 0
    with m.session_scope() as s:
        for item in _SEED:
            exists = s.query(DsaGlobalParam).filter_by(param_key=item['param_key']).first()
            if exists:
                continue
            s.add(DsaGlobalParam(
                param_key=item['param_key'],
                param_value=item['param_value'],
                param_desc=item['param_desc'],
            ))
            created += 1
    return {'code': 0, 'msg': 'ok', 'data': {'created': created, 'seed': len(_SEED)}}


@router.put('/{key}')
def set_dsa_param(key: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """设置单个全局参数（create-or-update）。

    请求体: {paramValue: float, paramDesc?: string}
    """
    try:
        value = float(payload.get('paramValue'))
    except (TypeError, ValueError):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail='paramValue 必须为数字')
    desc = payload.get('paramDesc')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.query(DsaGlobalParam).filter_by(param_key=key).first()
        if row:
            row.param_value = value
            if desc is not None:
                row.param_desc = desc
        else:
            row = DsaGlobalParam(param_key=key, param_value=value, param_desc=desc)
            s.add(row)
            s.flush()
        return {'code': 0, 'msg': 'ok', 'data': row.to_dict()}
