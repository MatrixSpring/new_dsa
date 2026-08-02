# -*- coding: utf-8 -*-
"""
==================================================
情报结构化 5 字段 + AI 分级 — api/v1/endpoints/intelligence_impact.py
==================================================
设计 §2.2 / §5.2：intelligence_items 结构化 5 字段（impact_level / impact_cycle /
impact_industry / impact_direction / transmit_weight）+ AI 分级。

以**外挂伴随表**实现（不改 intelligence_items 宽表）：按 item_id 关联，缺失即启发式补齐。
无 LLM key 时走确定性启发式降级（关键词匹配方向 / 标题长度估等级 / 默认周期），
保证结构正确、可验证。

端点（统一前缀 /api/v1/intelligence-impact）:
  POST /grade    接受 items 列表，计算 5 字段并 upsert，返回分级结果
  GET  /impacts  按方向/等级过滤读取已分级条目
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.storage import DatabaseManager, IntelligenceItemImpact

logger = logging.getLogger(__name__)

router = APIRouter()

# 方向关键词（利好/利空）
_BULL = ['利好', '增长', '上调', '扩产', '中标', '超预期', '回暖', '复苏', '补贴', '支持', '突破']
_BEAR = ['利空', '下滑', '下调', '减产', '风险', '处罚', '亏损', '制裁', '减持', '违约', '暴雷']

# 周期关键词
_CYCLE_SHORT = ['日内', '本周', '短期', '盘前', '盘中']
_CYCLE_MID = ['半月', '月度', '季报', '半月报']
_CYCLE_LONG = ['半年', '年度', '长期', '产能周期', '战略']

_LEVEL_HIGH = ['重大', '重磅', '紧急', '突发', '央行', '监管', '关税', '制裁']
_LEVEL_LOW = ['小幅', '边际', '日常', '常规', '惯例']


def _grade_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """确定性启发式分级（无 LLM 时降级路径）。"""
    text = ' '.join(str(item.get(k, '')) for k in ('title', 'summary', 'content', 'body'))
    # 方向
    bull = sum(text.count(w) for w in _BULL)
    bear = sum(text.count(w) for w in _BEAR)
    if bull > bear:
        direction = '利好'
    elif bear > bull:
        direction = '利空'
    else:
        direction = '中性'
    # 周期
    if any(w in text for w in _CYCLE_LONG):
        cycle = '6m'
    elif any(w in text for w in _CYCLE_MID):
        cycle = '1m'
    elif any(w in text for w in _CYCLE_SHORT):
        cycle = '1w'
    else:
        cycle = '2w'
    # 等级
    if any(w in text for w in _LEVEL_HIGH):
        level = '高'
    elif any(w in text for w in _LEVEL_LOW):
        level = '低'
    else:
        level = '中'
    # 传导权重：方向越明确、等级越高 → 权重越高
    base = 0.5
    if direction != '中性':
        base += 0.15
    if level == '高':
        base += 0.2
    elif level == '低':
        base -= 0.15
    weight = round(max(0.05, min(0.95, base)), 2)
    return {
        'impactLevel': level,
        'impactCycle': cycle,
        'impactIndustry': item.get('industry') or item.get('impactIndustry'),
        'impactDirection': direction,
        'transmitWeight': weight,
    }


@router.post('/grade')
def grade_items(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """对传入的情报条目计算结构化 5 字段并 upsert 到伴随表。

    请求体: {items: [{id, title, summary, industry?}, ...]}
    返回: {code, data:{graded: int, items:[{itemId, ...5字段}]}}
    """
    items = payload.get('items') or []
    if not isinstance(items, list) or not items:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail='items 不能为空')

    m = DatabaseManager.get_instance()
    graded: List[Dict[str, Any]] = []
    with m.session_scope() as s:
        for it in items:
            item_id = str(it.get('id') or it.get('itemId') or '')
            if not item_id:
                continue
            res = _grade_item(it)
            row = s.query(IntelligenceItemImpact).filter_by(item_id=item_id).first()
            if row is None:
                row = IntelligenceItemImpact(item_id=item_id)
                s.add(row)
            row.impact_level = res['impactLevel']
            row.impact_cycle = res['impactCycle']
            row.impact_industry = res['impactIndustry']
            row.impact_direction = res['impactDirection']
            row.transmit_weight = res['transmitWeight']
            s.flush()
            d = row.to_dict()
            d['title'] = it.get('title')
            graded.append(d)
    return {'code': 0, 'msg': 'ok', 'data': {'graded': len(graded), 'items': graded}}


@router.get('/impacts')
def list_impacts(
    direction: Optional[str] = Query(None, description='利好/利空/中性'),
    level: Optional[str] = Query(None, description='高/中/低'),
) -> Dict[str, Any]:
    """读取已分级情报（按方向/等级过滤）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(IntelligenceItemImpact)
        if direction:
            q = q.filter(IntelligenceItemImpact.impact_direction == direction)
        if level:
            q = q.filter(IntelligenceItemImpact.impact_level == level)
        rows = q.order_by(IntelligenceItemImpact.id.desc()).limit(200).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}
