# -*- coding: utf-8 -*-
"""自动爬虫 + 长文本解析流水线（P0）：供料 → 解析 → 入库。

设计依据：docs/crawler-llm-parse-integration.md（DSA-CRAWL-LLM-MERGE-V1.0）P0 快速落地。
- 真实环境：source_key 映射到 cninfo-crawler / a-stock-data / Crawl4AI 适配器抓取原始文本。
- 沙箱环境（无外网/未装抓取依赖）：走确定性 mock 语料，保证「抓取 → 解析 → 入库」全链路可验证。
- 解析层复用 core/llm_parse_service.LLMParseService（启发式降级），不改 DSA 内核。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.storage import CrawledDocument, DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class CrawlSource:
    key: str
    name: str
    doc_type: str          # policy / report / prospectus / minutes
    adapter: str           # 真实适配器标识（cninfo / astock / crawl4ai / mock）
    description: str


# 可配置抓取源注册表（新增源只需在此登记 + 提供 adapter 实现）。
SOURCE_REGISTRY: List[CrawlSource] = [
    CrawlSource(
        key='cninfo_announcement',
        name='交易所官方公告',
        doc_type='policy',
        adapter='cninfo',
        description='巨潮/交易所上市公司公告（政策类、合规强约束）',
    ),
    CrawlSource(
        key='morning_notes',
        name='券商晨会纪要',
        doc_type='minutes',
        adapter='astock',
        description='各大券商每日晨会纪要（时效性高、隐含交易线索）',
    ),
    CrawlSource(
        key='broker_research',
        name='券商深度研报',
        doc_type='report',
        adapter='astock',
        description='个股/行业深度研究报告（长期规划、目标价）',
    ),
]


# 沙箱确定性 mock 语料：保证无外网时可端到端验证。
_MOCK_CORPUS: Dict[str, Dict[str, str]] = {
    'cninfo_announcement': {
        'title': '关于新能源汽车购置补贴实施细则的公告',
        'text': (
            '为推进新能源汽车产业发展，自本通知发布之日起实施购置补贴：\n'
            '一、每辆新能源乘用车补贴 1 万元，实施期至 2027 年底。\n'
            '二、申请企业本地配套率不低于 40%，方可享受补贴。\n'
            '三、建立动态退出机制，能量密度不达标的车型自 2028 年起取消资格。\n'
            '风险提示：若出口限制加码，产业链将面临价格下行压力。'
        ),
    },
    'morning_notes': {
        'title': '晨会纪要：固态电池路线突破与出口扰动',
        'text': (
            '今日关注：某头部电池厂宣布固态电池中试线落地，量产节点提前至 2027 年。\n'
            '乐观情景：固态路线突破带动上游锂资源与设备需求。\n'
            '悲观情景：海外出口管制加码，短期供给受限。\n'
            '共识：新能源长期景气，短期补贴力度存在分歧。'
        ),
    },
    'broker_research': {
        'title': '某锂电龙头深度研报',
        'text': (
            '公司为全球锂电隔膜龙头，预计 2027 年产能达 500GWh。\n'
            '核心驱动：储能需求放量 + 海外建厂规避贸易壁垒。\n'
            '主要风险：产品价格下行、产能消纳不及预期。\n'
            '长期规划：2028 年前完成欧洲二期基地投产。'
        ),
    },
}


def list_sources() -> List[Dict[str, str]]:
    return [
        {
            'key': s.key,
            'name': s.name,
            'docType': s.doc_type,
            'adapter': s.adapter,
            'description': s.description,
        }
        for s in SOURCE_REGISTRY
    ]


def _get_source(source_key: str) -> Optional[CrawlSource]:
    for s in SOURCE_REGISTRY:
        if s.key == source_key:
            return s
    return None


def fetch_source(source_key: str) -> Dict[str, str]:
    """抓取源 -> 原始文本。

    真实环境：根据 source.adapter 调用对应抓取适配器（cninfo/astock/crawl4ai）。
    沙箱环境：返回确定性 mock 语料，保证链路可验证。
    """
    source = _get_source(source_key)
    if source is None:
        raise ValueError(f'未知抓取源: {source_key}')

    # ---- 真实适配器接入点（占位，沙箱不触发）----
    # if source.adapter == 'cninfo':
    #     return _fetch_via_cninfo(source)
    # if source.adapter in ('astock', 'crawl4ai'):
    #     return _fetch_via_adapter(source)

    # ---- 沙箱确定性 mock ----
    mock = _MOCK_CORPUS.get(source_key)
    if mock is None:
        raise ValueError(f'抓取源 {source_key} 暂无 mock 语料（真实环境由适配器提供）')
    return {
        'title': mock['title'],
        'doc_type': source.doc_type,
        'raw_text': mock['text'],
        'fetched_via': 'mock',
    }


def run_crawl_and_parse(source_key: str) -> Dict[str, Any]:
    """全链路：抓取 -> LLM 结构化解析 -> 入库。

    返回 {code, data:{...}}，data 含抓取元信息与解析结果；失败时落库 status=failed。
    """
    source = _get_source(source_key)
    if source is None:
        return {'code': 1, 'msg': f'未知抓取源: {source_key}', 'data': None}

    m = DatabaseManager.get_instance()
    # 先建一条 pending 记录
    rec = CrawledDocument(
        source_key=source_key,
        title='',
        doc_type=source.doc_type,
        status='pending',
    )
    with m.session_scope() as s:
        s.add(rec)
        s.flush()
        doc_id = rec.id

    try:
        fetched = fetch_source(source_key)
        # 复用 LLM 解析层（启发式降级）
        from core.llm_parse_service import LlmParseService

        parsed = LlmParseService().parse_document(
            fetched['raw_text'], doc_type=fetched['doc_type'], doc_id=f'crawl-{source_key}'
        )
        parsed_json = _safe_json(normalize_parsed(parsed))
        with m.session_scope() as s:
            row = s.get(CrawledDocument, doc_id)
            if row is None:  # 并发/清理兜底
                row = CrawledDocument(id=doc_id, source_key=source_key, doc_type=source.doc_type)
                s.add(row)
            row.title = fetched['title']
            row.doc_type = fetched['doc_type']
            row.raw_text = fetched['raw_text']
            row.parsed_json = parsed_json
            row.status = 'parsed'
            from datetime import datetime as _dt
            row.parsed_at = _dt.now()
            s.flush()
            out = row.to_dict()
        return {'code': 0, 'msg': 'ok', 'data': out}
    except Exception as e:  # noqa: BLE001
        logger.exception('crawl_and_parse failed for %s', source_key)
        with m.session_scope() as s:
            row = s.get(CrawledDocument, doc_id)
            if row is None:
                row = CrawledDocument(id=doc_id, source_key=source_key, doc_type=source.doc_type)
                s.add(row)
            row.status = 'failed'
            row.error = str(e)
            s.flush()
            out = row.to_dict()
        return {'code': 2, 'msg': f'crawl failed: {e}', 'data': out}


def list_documents(limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(CrawledDocument)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(CrawledDocument.id.desc()).limit(limit).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


def _safe_json(obj: Any) -> str:
    import json as _json

    try:
        return _json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'


def normalize_parsed(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """将 llm_parse_service 启发式嵌套输出扁平化为前端契约（CrawlParsed）。

    解析服务返回信封 {code,msg,data}，data 为嵌套结构（short_term_1w={...} 等）；
    此处先解包 data，再扁平化为 camelCase 字符串，避免前端与解析层紧耦合。
    """
    if isinstance(parsed, dict) and 'data' in parsed and isinstance(parsed['data'], dict):
        parsed = parsed['data']
    st = parsed.get('short_term_1w') or {}
    mt = parsed.get('mid_term_1m') or {}
    lt = parsed.get('long_term_halfyear') or {}
    hc = parsed.get('hidden_constraint') or []
    pr = parsed.get('potential_risk') or []
    short = ' '.join(str(v) for v in st.values() if v) if isinstance(st, dict) else str(st)
    mid = ' '.join(str(v) for v in mt.values() if v) if isinstance(mt, dict) else str(mt)
    long = ' '.join(str(v) for v in lt.values() if v) if isinstance(lt, dict) else str(lt)
    constraints = '；'.join(
        (c.get('content', '') if isinstance(c, dict) else str(c)) for c in hc
    ) if isinstance(hc, list) else str(hc)
    risks = '；'.join(pr) if isinstance(pr, list) else str(pr)
    rel = parsed.get('reliability')
    rel_str = f'{rel:.0%}' if isinstance(rel, (int, float)) else str(rel or '')
    return {
        'docId': parsed.get('doc_id') or '',
        'docType': parsed.get('doc_type') or '',
        'shortTerm1w': short or '（启发式未识别短期条款）',
        'midTerm1m': mid or '（启发式未识别中期变化）',
        'longTermHalfyear': long or '（启发式未识别长期规划）',
        'hiddenConstraint': constraints or '（无）',
        'potentialRisk': risks or '（无）',
        'reliability': rel_str,
    }
