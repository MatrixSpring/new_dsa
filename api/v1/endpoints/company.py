# -*- coding: utf-8 -*-
"""上市公司全维度信息只读接口。

GET /api/v1/companies            列表(支持 code/name/pinyin 搜索、source 过滤、分页)
GET /api/v1/companies/{code}     单公司全维度详情
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text as sa_text

from src.storage import CompanyProfile, CompanyRiskTag, DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


def _summary(row: CompanyProfile) -> Dict[str, Any]:
    linked = []
    try:
        linked = json.loads(row.linked_chains) if row.linked_chains else []
    except (ValueError, TypeError):
        linked = []
    sources = []
    try:
        sources = json.loads(row.data_sources) if row.data_sources else []
    except (ValueError, TypeError):
        sources = []
    return {
        'code': row.code,
        'name': row.name,
        'exchange': row.exchange,
        'pe': row.pe,
        'pb': row.pb,
        'ps': row.ps,
        'price': row.price,
        'total_market_cap': row.total_market_cap,
        'float_market_cap': row.float_market_cap,
        'linked_chains_count': len(linked),
        'consensus_rating': row.consensus_rating,
        'consensus_target_price': row.consensus_target_price,
        'consensus_institutes': row.consensus_institutes,
        'consensus_eps': row.consensus_eps,
        'esg_rating': row.esg_rating,
        'esg_score': row.esg_score,
        'data_sources': sources,
    }


@router.get('/companies')
def list_companies(
    q: Optional[str] = Query(None, description='代码/名称/拼音 模糊搜索'),
    source: Optional[str] = Query(None, description='按数据来源过滤，如 industry_chain_fusion'),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """上市公司列表。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        stmt = 'SELECT * FROM company_profile'
        where: List[str] = []
        params: Dict[str, Any] = {}
        if q:
            like = f'%{q}%'
            where.append('(code LIKE :q OR name LIKE :q OR pinyin LIKE :q)')
            params['q'] = like
        if source:
            where.append('data_sources LIKE :src')
            params['src'] = f'%{source}%'
        if where:
            stmt += ' WHERE ' + ' AND '.join(where)
        total = s.execute(sa_text(
            stmt.replace('SELECT *', 'SELECT COUNT(*)')
        ), params).scalar()

        order = ' ORDER BY (pe IS NOT NULL) DESC, name ASC'
        rows = s.execute(sa_text(stmt + order + ' LIMIT :lim OFFSET :off'),
                         {**params, 'lim': page_size, 'off': (page - 1) * page_size}).fetchall()
        cols = [c[1] for c in s.execute(sa_text(
            'PRAGMA table_info(company_profile)')).fetchall()]
        items = []
        for r in rows:
            d = dict(zip(cols, r))
            obj = CompanyProfile(**{k: d[k] for k in d if k in CompanyProfile.__table__.columns.keys()})
            items.append(_summary(obj))
    return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


def _norm_code(c: str) -> str:
    if not c:
        return c
    base = str(c).strip().upper().split('.')[0]
    return base[:6] if base.isdigit() and len(base) >= 6 else c


@router.get('/companies/{code}')
def get_company(code: str) -> Dict[str, Any]:
    """单公司全维度详情。code 支持 6 位或带市场后缀。"""
    n6 = _norm_code(code)
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.get(CompanyProfile, n6)
        if row is None:
            raise HTTPException(status_code=404, detail=f'company {code} not found')
        d = row.to_dict()
        # 合并风险标签（页面5「自动利好/利空识别」）
        d['riskTags'] = _load_risk_tags(s, n6)
        return d


# ---- 页面5 收尾：自动利好/利空风险标签 -------------------------------------
_GOOD_KW = ['增长', '超预期', '扩产', '中标', '回购', '增持', '新高', '突破', '订单', '盈利', '扭亏', '扩产']
_BAD_KW = ['下滑', '亏损', '减持', '诉讼', '处罚', '商誉减值', '质押', '退市', '暴雷', '下调', '问询', '立案']


def _load_risk_tags(s, code: str) -> List[Dict[str, Any]]:
    row = s.query(CompanyRiskTag).filter_by(code=code).first()
    if not row or not row.risk_tags:
        return []
    try:
        return json.loads(row.risk_tags)
    except (ValueError, TypeError):
        return []


def _compute_risk_tags(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """启发式利好/利空识别（无 LLM 时确定性降级）。"""
    text_fields = ['name', 'business_model', 'main_business', 'competitive_edge',
                   'performance_drivers', 'tech_layout', 'revenue_composition',
                   'profit_composition', 'risk_factors']
    blob = ' '.join(str(d.get(f, '') or '') for f in text_fields)
    tags: List[Dict[str, Any]] = []
    for kw in _GOOD_KW:
        if kw in blob:
            tags.append({'tag': kw, 'level': '利好', 'note': f'文本命中关键词「{kw}」', 'source': 'heuristic'})
    for kw in _BAD_KW:
        if kw in blob:
            tags.append({'tag': kw, 'level': '利空', 'note': f'文本命中关键词「{kw}」', 'source': 'heuristic'})
    return tags


@router.get('/companies/{code}/risk-tags')
def get_company_risk_tags(code: str) -> Dict[str, Any]:
    """读取公司风险标签。"""
    n6 = _norm_code(code)
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        tags = _load_risk_tags(s, n6)
    return {'code': 0, 'total': len(tags), 'items': tags}


@router.post('/companies/{code}/risk-tags')
def compute_company_risk_tags(code: str) -> Dict[str, Any]:
    """自动识别并写库利好/利空标签（页面5 收尾）。

    读取 company_profile 全维度文本，启发式抽取命中关键词，持久化到 company_risk_tags。
    """
    n6 = _norm_code(code)
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.get(CompanyProfile, n6)
        if row is None:
            raise HTTPException(status_code=404, detail=f'company {code} not found')
        tags = _compute_risk_tags(row.to_dict())
        existing = s.query(CompanyRiskTag).filter_by(code=n6).first()
        payload = json.dumps(tags, ensure_ascii=False)
        if existing:
            existing.risk_tags = payload
        else:
            s.add(CompanyRiskTag(code=n6, risk_tags=payload))
        return {'code': 0, 'msg': 'ok', 'data': {'code': n6, 'riskTags': tags, 'total': len(tags)}}
