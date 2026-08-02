# -*- coding: utf-8 -*-
"""
==================================================
前瞻预测快照 — api/v1/endpoints/forecast_snapshot.py
==================================================
设计文档 §5.3 表1（forecast_batch_snapshot）+ 前瞻预测中心聚合页数据底座。

端点（统一前缀 /api/v1/forecast-snapshots）:
  GET  /            按 scope_type / scope_value / cycle 过滤，返回快照列表 + 按周期聚合概览
  POST /seed        写入确定性占位四周期快照（沙箱降级；真实环境由 job_batch_forecast 落库）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.storage import DatabaseManager, ForecastBatchSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()

CYCLES = ['1w', '2w', '1m', '6m']
SCOPE_TYPES = ['event', 'industry', 'stock', 'portfolio']

# 沙箱降级用的确定性占位样本（真实环境不写出，由批量推演 job 落库）
_SEED_SCOPES: List[Dict[str, Any]] = [
    {'scope_type': 'stock', 'scope_value': '600519', 'label': '贵州茅台'},
    {'scope_type': 'stock', 'scope_value': '000858', 'label': '五粮液'},
    {'scope_type': 'industry', 'scope_value': 'sw_computers', 'label': '计算机(申万)'},
    {'scope_type': 'industry', 'scope_value': 'sw_power', 'label': '电力设备(申万)'},
    {'scope_type': 'event', 'scope_value': 'evt_rate_cut', 'label': '降息预期事件'},
]

# 每个周期的固定占位方向/区间（确定性，便于演示与验证）
_CYCLE_PRESET = {
    '1w': {'direction': 'up', 'low_pct': 1.2, 'high_pct': 4.5, 'up_prob': 0.62, 'confidence': 0.58,
           'core_driver': '资金博弈短期放量', 'main_risk': '突发地缘扰动'},
    '2w': {'direction': 'up', 'low_pct': 0.5, 'high_pct': 6.0, 'up_prob': 0.60, 'confidence': 0.55,
           'core_driver': '政策边际宽松', 'main_risk': '财报季波动'},
    '1m': {'direction': 'oscillation', 'low_pct': -3.0, 'high_pct': 5.0, 'up_prob': 0.52, 'confidence': 0.50,
           'core_driver': '产业景气分化', 'main_risk': '需求不及预期'},
    '6m': {'direction': 'up', 'low_pct': 2.0, 'high_pct': 18.0, 'up_prob': 0.64, 'confidence': 0.48,
           'core_driver': '产能周期上行', 'main_risk': '宏观外需走弱'},
}


@router.get('/')
def list_forecast_snapshots(
    scope_type: Optional[str] = Query(None, description='event/industry/stock/portfolio'),
    scope_value: Optional[str] = Query(None, description='事件id/产业链id/股票code'),
    cycle: Optional[str] = Query(None, description='1w/2w/1m/6m'),
) -> Dict[str, Any]:
    """列出前瞻预测快照，并按周期聚合概览（up/down/oscillation 计数 + 平均置信度）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(ForecastBatchSnapshot)
        if scope_type:
            q = q.filter(ForecastBatchSnapshot.scope_type == scope_type)
        if scope_value:
            q = q.filter(ForecastBatchSnapshot.scope_value == scope_value)
        if cycle:
            q = q.filter(ForecastBatchSnapshot.cycle == cycle)
        rows = q.order_by(ForecastBatchSnapshot.generated_at.desc()).all()
        items = [r.to_dict() for r in rows]

    # 周期聚合概览（前端用数组 .find 查询，故返回列表）
    by_cycle: List[Dict[str, Any]] = []
    for c in CYCLES:
        subset = [it for it in items if it['cycle'] == c]
        counts = {'up': 0, 'down': 0, 'oscillation': 0}
        conf_sum = 0.0
        for it in subset:
            d = it.get('direction') or 'oscillation'
            counts[d] = counts.get(d, 0) + 1
            conf_sum += (it.get('confidence') or 0.0)
        by_cycle.append({
            'cycle': c,
            'total': len(subset),
            'directionCounts': counts,
            'avgConfidence': round(conf_sum / len(subset), 3) if subset else 0.0,
        })

    return {'code': 0, 'total': len(items), 'items': items, 'byCycle': by_cycle}


@router.post('/seed')
def seed_forecast_snapshots(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """写入确定性占位四周期快照（沙箱演示/首跑；真实环境由 job_batch_forecast 落库）。

    请求体可含 {force: true} 覆盖已存在快照；默认跳过已存在 scope+cycle 组合。
    """
    force = bool(payload.get('force', False))
    m = DatabaseManager.get_instance()
    created = 0
    with m.session_scope() as s:
        for sc in _SEED_SCOPES:
            for c in CYCLES:
                exists = s.query(ForecastBatchSnapshot).filter_by(
                    scope_type=sc['scope_type'], scope_value=sc['scope_value'], cycle=c
                ).first()
                if exists:
                    if not force:
                        continue
                    s.delete(exists)
                preset = _CYCLE_PRESET[c]
                s.add(ForecastBatchSnapshot(
                    scope_type=sc['scope_type'],
                    scope_value=sc['scope_value'],
                    cycle=c,
                    direction=preset['direction'],
                    low_pct=preset['low_pct'],
                    high_pct=preset['high_pct'],
                    up_prob=preset['up_prob'],
                    confidence=preset['confidence'],
                    core_driver=preset['core_driver'],
                    main_risk=preset['main_risk'],
                    job_run_id='seed',
                ))
                created += 1
    return {'code': 0, 'msg': 'ok', 'data': {'created': created, 'scopes': len(_SEED_SCOPES), 'cycles': len(CYCLES)}}
