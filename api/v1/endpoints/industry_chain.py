# -*- coding: utf-8 -*-
"""
========================================================
产业链全景可视化 — 数据接口
========================================================

职责：
1. 提供产业链目录（GET /api/v1/industry-chains）：
   - 内置沙盘富数据（锂电池 / 半导体 / 光伏），来自产业链沙盘原型，
     含完整 nodes / edges / companies / news 传导图谱；
   - 新质生产力(xzsc)底层持久化数据（data/stock_analysis.db 表 xzsc_industry_chain），
     共 58 条，按 L1 赛道分组，由 segments（上游/中游/下游/核心环节/应用）推导结构化图谱。
2. 提供单条产业链完整图谱（GET /api/v1/industry-chains/{chain_id}）。
3. 提供外部冲击事件库（GET /api/v1/industry-chains/shocks）。

前端 IndustryChainSandbox.vue 通过对接以上接口，从"硬编码原型"升级为"底层数据驱动"。
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from src.storage import DatabaseManager, XzscIndustryChain
from src.data.industry_chain_fusion import build_xzsc_shenwan_fusion
from src.industry_chain_propagation import propagate_shock, chain_exposure_from_holdings

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# 数据来源
# ---------------------------------------------------------------------------
_DATA_PATH = Path(__file__).resolve().parents[3] / 'src' / 'data' / 'industry_chain_sandbox_data.json'

# 内置沙盘链（顺序即目录展示顺序）
_BUILTIN_IDS = ['lithium', 'semiconductor', 'photovoltaic']
_BUILTIN_ICON = {'lithium': '🔋', 'semiconductor': '💻', 'photovoltaic': '☀️'}
_BUILTIN_COLOR = {'lithium': '190 100% 50%', 'semiconductor': '220 80% 60%', 'photovoltaic': '38 100% 55%'}
_BUILTIN_SUMMARY = {
    'lithium': '覆盖锂矿→材料→电芯→新能源车/储能/消费电子的全产业链，支持成本/需求/替代/供给四类传导与冲击推演。',
    'semiconductor': '覆盖硅片/设备/EDA→晶圆代工/设计/封测→手机/汽车电子/AI服务器的半导体自主可控全景。',
    'photovoltaic': '覆盖多晶硅→硅片→电池片→组件→逆变器的光伏产业链，含电价/装机/出口政策传导。',
}

# 新质生产力 L1 赛道 → 图标/配色（用于目录展示与图谱着色）
_L1_STYLE = {
    '数字经济与信息技术': ('💻', '220 80% 60%'),
    '新能源与新型储能': ('🔋', '150 80% 50%'),
    '高端装备与智能制造': ('🛠️', '30 90% 55%'),
    '生物医药与大健康': ('💊', '340 80% 60%'),
    '新材料与化工': ('🧪', '280 70% 60%'),
    '汽车与智能交通': ('🚗', '200 90% 55%'),
    '消费与传统产业智能化': ('🛒', '20 90% 55%'),
    '绿色环保与公用事业': ('♻️', '140 70% 50%'),
    '国防军工': ('🛡️', '0 70% 55%'),
    '新基建': ('🏗️', '250 70% 60%'),
}


def _load_sandbox() -> Dict[str, Any]:
    with open(_DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _layer_for_stage(stage: str) -> float:
    s = (stage or '').strip()
    if s.startswith('上游'):
        return 0.0
    if s.startswith('中游') or s == '核心环节':
        return 1.0
    if s.startswith('下游') or s == '应用':
        return 2.0
    return 1.0


def _theme_style(l1: str):
    return _L1_STYLE.get(l1, ('🔗', '190 100% 50%'))


# ---------------------------------------------------------------------------
# 产业链融合（xzsc ↔ 申万）：lazy 构建并缓存
# ---------------------------------------------------------------------------
_FUSION_CACHE: Optional[Dict[str, Any]] = None


def _get_fusion() -> Dict[str, Any]:
    """构建并缓存 xzsc↔申万 融合映射（公司增强）。"""
    global _FUSION_CACHE
    if _FUSION_CACHE is None:
        try:
            rows = _xzsc_rows()
            _FUSION_CACHE = build_xzsc_shenwan_fusion(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning('构建产业链融合映射失败: %s', exc)
            _FUSION_CACHE = {'chains': {}, 'shenwan_xzsc': {}}
    return _FUSION_CACHE


def _fusion_company(comp: Dict[str, Any], biz: str) -> Dict[str, Any]:
    """把融合出的 {name,code} 补齐为前端公司卡片所需字段。"""
    return {
        'code': comp.get('code') or '',
        'name': comp.get('name'),
        'mkt': 'cn',
        'revPct': 50,
        'selfSuff': 0,
        'overseas': 0,
        'sensitivity': 0.6,
        'biz': biz,
    }


def _xzsc_rows() -> List[XzscIndustryChain]:
    db = DatabaseManager.get_instance()
    with db.session_scope() as session:
        rows = session.query(XzscIndustryChain).order_by(XzscIndustryChain.no).all()
        # 脱离 session：把需要的字段复制出来
        return [
            {
                'no': r.no,
                'name': r.name,
                'l1': r.l1,
                'l2': r.l2,
                'summary': r.summary,
                'segments': r.segments,
            }
            for r in rows
        ]


def _build_xzsc_graph(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row['segments']
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    nodes: List[Dict[str, Any]] = []
    by_layer: Dict[float, List[str]] = {}
    label_of: Dict[str, str] = {}

    for stage, items in raw.items():
        if not isinstance(items, list):
            continue
        layer = _layer_for_stage(stage)
        for i, name in enumerate(items):
            nid = f"{row['no']}_{stage}_{i}"
            nodes.append({
                'id': nid,
                'label': name,
                'sub': stage,
                'layer': layer,
                'type': 'industry',
                'size': 'medium',
                'pricingPower': 50,
                'barrier': 'medium',
                'supplyDemand': 'balanced',
                'costSensitivity': 50,
                'profitElasticity': 50,
            })
            by_layer.setdefault(layer, []).append(nid)
            label_of[nid] = name

    edges: List[Dict[str, Any]] = []
    layer_keys = sorted(by_layer.keys())
    for li in range(len(layer_keys) - 1):
        a = by_layer[layer_keys[li]]
        b = by_layer[layer_keys[li + 1]]
        if not a or not b:
            continue
        if len(a) * len(b) > 24:
            # 环节过多：顺序相连，避免边数爆炸
            for i in range(min(len(a), len(b))):
                edges.append({
                    'source': a[i], 'target': b[i], 'type': 'cost',
                    'coeff': 0.6, 'lag': 5,
                    'desc': f"{label_of.get(a[i], a[i])} → {label_of.get(b[i], b[i])}",
                })
        else:
            for sa in a:
                for tb in b:
                    edges.append({
                        'source': sa, 'target': tb, 'type': 'cost',
                        'coeff': 0.6, 'lag': 5,
                        'desc': f"{label_of.get(sa, sa)} → {label_of.get(tb, tb)}",
                    })

    icon, color = _theme_style(row['l1'])

    # ---- 融合：把申万龙头公司挂到 label 匹配的节点 ----
    companies: Dict[str, List[Dict[str, Any]]] = {}
    fc: Dict[str, Any] = {}
    try:
        fusion = _get_fusion()
        fc = fusion['chains'].get(str(row['no']), {})
        label2id: Dict[str, str] = {}
        for n in nodes:
            label2id.setdefault(n['label'], n['id'])
        for m in fc.get('matches', []):
            if not m.get('companies'):
                continue
            targets: set = set()
            for term in m.get('terms', []):
                if len(term) < 2:
                    continue
                for label, nid in label2id.items():
                    if term in label or label in term:
                        targets.add(nid)
            if not targets and nodes:
                targets = {nodes[0]['id']}  # 兜底：挂到首个节点保证可见
            for comp in m['companies']:
                if not comp.get('code'):
                    continue
                obj = _fusion_company(comp, m['l3'])
                for nid in targets:
                    if obj['code'] not in {c['code'] for c in companies.get(nid, [])}:
                        companies.setdefault(nid, []).append(obj)
    except Exception as exc:  # noqa: BLE001
        logger.warning('xzsc 链 %s 公司融合失败: %s', row.get('no'), exc)

    return {
        'id': str(row['no']),
        'name': row['name'],
        'icon': icon,
        'color': color,
        'category': row['l1'],
        'source': 'xzsc',
        'summary': row.get('summary') or '',
        'nodes': nodes,
        'edges': edges,
        'companies': companies,
        'news': [],
        'fusion': {
            'shenwanRefs': fc.get('shenwanRefs', []),
            'curatedRefs': fc.get('curatedRefs', []),
            'companyCount': sum(len(v) for v in companies.values()),
            'curatedCount': fc.get('curatedCount', 0),
        },
    }


def _builtin_graph(sandbox: Dict[str, Any], chain_id: str) -> Dict[str, Any]:
    c = sandbox['INDUSTRY_CHAINS'][chain_id]
    return {
        'id': chain_id,
        'name': c['name'],
        'icon': _BUILTIN_ICON.get(chain_id, '🔗'),
        'color': _BUILTIN_COLOR.get(chain_id, '190 100% 50%'),
        'category': '内置 · 产业链沙盘',
        'source': 'sandbox',
        'summary': _BUILTIN_SUMMARY.get(chain_id, ''),
        'nodes': c['nodes'],
        'edges': c['edges'],
        'companies': c.get('companies', {}),
        'news': c.get('news', []),
    }


# ===========================================================================
# 接口
# ===========================================================================
@router.get('/industry-chains')
def list_industry_chains() -> Dict[str, Any]:
    """产业链目录：内置沙盘链 + 新质生产力(xzsc)底层数据。"""
    sandbox = _load_sandbox()
    items: List[Dict[str, Any]] = []

    # 1) 内置沙盘链
    for cid in _BUILTIN_IDS:
        c = sandbox['INDUSTRY_CHAINS'].get(cid)
        if not c:
            continue
        items.append({
            'id': cid,
            'name': c['name'],
            'icon': _BUILTIN_ICON.get(cid, '🔗'),
            'color': _BUILTIN_COLOR.get(cid, '190 100% 50%'),
            'category': '内置 · 产业链沙盘',
            'l1': '内置 · 产业链沙盘',
            'l2': '',
            'summary': _BUILTIN_SUMMARY.get(cid, ''),
            'source': 'sandbox',
            'nodeCount': len(c['nodes']),
        })

    # 2) 新质生产力(xzsc)底层持久化数据
    try:
        rows = _xzsc_rows()
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取 xzsc 产业链数据失败: %s', exc)
        rows = []

    fusion = _get_fusion()
    for r in rows:
        segs = r['segments']
        if isinstance(segs, str):
            try:
                segs = json.loads(segs)
            except (ValueError, TypeError):
                segs = {}
        node_count = sum(len(v) for v in segs.values() if isinstance(v, list)) if isinstance(segs, dict) else 0
        icon, color = _theme_style(r['l1'])
        fc = fusion['chains'].get(str(r['no']), {})
        items.append({
            'id': str(r['no']),
            'name': r['name'],
            'icon': icon,
            'color': color,
            'category': r['l1'],
            'l1': r['l1'],
            'l2': r['l2'],
            'summary': r.get('summary') or '',
            'source': 'xzsc',
            'nodeCount': node_count,
            'companyCount': len(fc.get('allCompanies', [])),
        })

    return {
        'total': len(items),
        'sources': {
            'sandbox': sum(1 for i in items if i['source'] == 'sandbox'),
            'xzsc': sum(1 for i in items if i['source'] == 'xzsc'),
        },
        'items': items,
    }


@router.get('/industry-chains/shocks')
def list_shocks() -> Dict[str, Any]:
    """外部冲击事件库（推演沙盘使用）。"""
    sandbox = _load_sandbox()
    return {'total': len(sandbox.get('SHOCK_EVENTS', [])), 'items': sandbox.get('SHOCK_EVENTS', [])}


@router.get('/industry-chains/{chain_id}')
def get_industry_chain(chain_id: str) -> Dict[str, Any]:
    """单条产业链完整图谱（nodes/edges/companies/news）。"""
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')
    return graph


def _get_chain_graph(chain_id: str) -> Optional[Dict[str, Any]]:
    """按 id 返回产业链完整图谱(dict)，不存在返回 None。"""
    sandbox = _load_sandbox()
    # 内置沙盘链（按 id 匹配）
    if chain_id in sandbox.get('INDUSTRY_CHAINS', {}):
        return _builtin_graph(sandbox, chain_id)
    # 新质生产力(xzsc)链（按 no 匹配）
    try:
        rows = _xzsc_rows()
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取 xzsc 产业链数据失败: %s', exc)
        rows = []
    for r in rows:
        if str(r['no']) == str(chain_id):
            return _build_xzsc_graph(r)
    return None


@router.post('/industry-chains/{chain_id}/propagate')
def propagate_chain_shock(chain_id: str, shock: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """产业链冲击传导推演 (P1-③ 深化)。

    请求体: {node(环节名或id), magnitude(相对冲击, -0.2=跌20%/成本+20%), kind}
    返回各环节/各公司受影响程度与链级汇总。
    """
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')
    return propagate_shock(graph, shock)


def _chain_companies_map() -> Dict[str, List[Dict[str, Any]]]:
    """构建 {链id: 成分股[{code,name}]} 映射（xzsc 融合 + 内置沙盘）。"""
    out: Dict[str, List[Dict[str, Any]]] = {}
    # 1) xzsc 融合成分股
    try:
        fusion = _get_fusion()
        for no, v in fusion['chains'].items():
            out[str(no)] = v.get('allCompanies', [])
    except Exception as exc:  # noqa: BLE001
        logger.warning('构建 xzsc 成分股映射失败: %s', exc)
    # 2) 内置沙盘成分股
    try:
        sandbox = _load_sandbox()
        for cid in _BUILTIN_IDS:
            c = sandbox['INDUSTRY_CHAINS'].get(cid)
            if not c:
                continue
            comps: List[Dict[str, Any]] = []
            for clist in (c.get('companies', {}) or {}).values():
                for comp in clist:
                    comps.append({'code': comp.get('code'), 'name': comp.get('name')})
            out[cid] = comps
    except Exception as exc:  # noqa: BLE001
        logger.warning('构建沙盘成分股映射失败: %s', exc)
    return out


@router.post('/industry-chains/portfolio-exposure')
def portfolio_chain_exposure(holdings: List[Dict[str, Any]] = Body(...)) -> Dict[str, Any]:
    """持仓 → 产业链暴露映射 (P1-③ 深化, 衔接组合风险)。

    请求体: [{code, weight}, ...]  (weight 为 0-1 或 0-100，自动归一)
    返回各产业链暴露权重、HHI 集中度与高集中预警。
    """
    if not holdings:
        raise HTTPException(status_code=400, detail='holdings 不能为空')
    cmap = _chain_companies_map()
    return chain_exposure_from_holdings(holdings, cmap)
