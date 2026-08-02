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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

from src.storage import DatabaseManager, XzscIndustryChain, ChainEdgeOverride, ChainRiskFlag, DsaGlobalParam
from src.data.industry_chain_fusion import build_xzsc_shenwan_fusion
from src.industry_chain_propagation import propagate_shock, chain_exposure_from_holdings
from src.services.factor_propagation_service import forecast_with_factors

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


def _load_dsa_global_params() -> Dict[str, float]:
    """读取 DSA 全局参数（设计 §3.1 默认值来源），缺表/缺行时退回设计常数。"""
    defaults = {
        'recursion_depth': 20.0,
        'coeff_threshold': 0.85,
        'bearish_weight': 0.7,
    }
    try:
        m = DatabaseManager.get_instance()
        with m.session_scope() as s:
            rows = s.query(DsaGlobalParam).all()
            for r in rows:
                defaults[r.param_key] = float(r.param_value)
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取 DSA 全局参数失败，使用设计常数: %s', exc)
    return defaults


def _build_override_map(chain_id: str) -> Dict[tuple, Dict[str, Any]]:
    """构建 {(source,target):{coeff,lag}}（无向，正反各一份），供传导覆盖系数。"""
    out: Dict[tuple, Dict[str, Any]] = {}
    try:
        m = DatabaseManager.get_instance()
        with m.session_scope() as s:
            rows = s.query(ChainEdgeOverride).filter_by(chain_id=chain_id).all()
            for r in rows:
                out[(r.source_node, r.target_node)] = {'coeff': r.coeff, 'lag': r.lag}
                out[(r.target_node, r.source_node)] = {'coeff': r.coeff, 'lag': r.lag}
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取传导系数覆盖失败: %s', exc)
    return out


@router.post('/industry-chains/{chain_id}/propagate')
def propagate_chain_shock(chain_id: str, shock: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """产业链冲击传导推演 (P1-③ 深化)，接入设计 §3.1 引擎规则。

    请求体: {node, magnitude, kind,
             maxDepth?, bidirectionalDecay?, bearishDecay?, useOverrides?}
    - 引擎默认值来自 dsa_global_params（recursion_depth/coeff_threshold/bearish_weight），
      请求体字段可覆盖；useOverrides 默认开启，自动读取 chain_edge_override 覆盖系数。
    返回各环节/各公司受影响程度与链级汇总（含 params 回显生效规则）。
    """
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')

    gp = _load_dsa_global_params()
    max_depth = int(float(gp.get('recursion_depth', 20)))
    bidirectional_decay = float(gp.get('coeff_threshold', 0.85))
    bearish_decay = float(gp.get('bearish_weight', 0.7))

    if 'maxDepth' in shock:
        max_depth = int(shock['maxDepth'])
    if 'bidirectionalDecay' in shock:
        bidirectional_decay = float(shock['bidirectionalDecay'])
    if 'bearishDecay' in shock:
        bearish_decay = float(shock['bearishDecay'])
    use_overrides = bool(shock.get('useOverrides', True))
    overrides = _build_override_map(chain_id) if use_overrides else {}

    opts = {
        'max_depth': max_depth,
        'bidirectional_decay': bidirectional_decay,
        'bearish_decay': bearish_decay,
        'use_overrides': bool(overrides),
        'overrides': overrides,
    }
    return propagate_shock(graph, shock, opts)


@router.post('/industry-chains/{chain_id}/propagate-scenarios')
def propagate_chain_scenarios(chain_id: str, shock: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """三情景并行传导推演（设计 §3.3 / 页面7 三情景）。

    同一冲击在 基准 / 乐观 / 悲观 三种参数下并行传导：
      - base        : 参数取全局默认（或请求体覆盖）
      - optimistic  : 冲击幅度 ×0.6、利空衰减放宽到 1.0（更温和）
      - pessimistic : 冲击幅度 ×1.4、利空衰减收紧到 0.5（更严峻）
    返回 {code:0, data:{base, optimistic, pessimistic, params}}。
    """
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')

    gp = _load_dsa_global_params()
    max_depth = int(float(gp.get('recursion_depth', 20)))
    bidirectional_decay = float(gp.get('coeff_threshold', 0.85))
    bearish_decay = float(gp.get('bearish_weight', 0.7))
    if 'maxDepth' in shock:
        max_depth = int(shock['maxDepth'])
    if 'bidirectionalDecay' in shock:
        bidirectional_decay = float(shock['bidirectionalDecay'])
    if 'bearishDecay' in shock:
        bearish_decay = float(shock['bearishDecay'])

    base_mag = float(shock.get('magnitude', 0.0))
    use_overrides = bool(shock.get('useOverrides', True))
    overrides = _build_override_map(chain_id) if use_overrides else {}

    base_opt = {
        'max_depth': max_depth,
        'bidirectional_decay': bidirectional_decay,
        'bearish_decay': bearish_decay,
        'use_overrides': bool(overrides),
        'overrides': overrides,
    }
    optimistic_opt = dict(base_opt, bearish_decay=1.0)
    pessimistic_opt = dict(base_opt, bearish_decay=0.5)

    base = propagate_shock(graph, {**shock, 'magnitude': base_mag}, base_opt)
    optimistic = propagate_shock(
        graph, {**shock, 'magnitude': base_mag * 0.6}, optimistic_opt
    )
    pessimistic = propagate_shock(
        graph, {**shock, 'magnitude': base_mag * 1.4}, pessimistic_opt
    )

    return {
        'code': 0,
        'msg': 'ok',
        'data': {
            'base': base,
            'optimistic': optimistic,
            'pessimistic': pessimistic,
            'params': {
                'max_depth': max_depth,
                'bidirectional_decay': bidirectional_decay,
                'bearish_decay': bearish_decay,
                'magnitude': base_mag,
                'optimistic_magnitude': base_mag * 0.6,
                'pessimistic_magnitude': base_mag * 1.4,
            },
        },
    }


@router.post('/industry-chains/{chain_id}/factor-forecast')
def factor_forward_forecast(chain_id: str, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """因子库 → DSA 内核正向传导桥接（闭环增强，内核零改动）。

    把沉淀的标准化上涨因子库（#17）转为 DSA 引擎 propagate_shock 的因子权重，并真实注入
    四周期正向传导对比（基线 vs 因子增强），输出最大冲击 / 影响环节 / 涉及公司提升与四周期预测。
    请求体: { shock?{node,magnitude,kind}, topN?(默认6), minConfidence?(默认0.6), category? }
    返回 {code, data:{ chainId, shockNode, baseMagnitude, boostedMagnitude, boost,
                      structuredBoost, edgeOverrides, categoryEdgeContrib,
                      factorWeights, baseline, enhanced, liftPct, forward4, factors, engine }}
    """
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')

    shock = body.get('shock') or {}
    if not shock.get('node'):
        shock['node'] = str(body.get('node') or '锂矿')
    if 'magnitude' not in shock:
        shock['magnitude'] = float(body.get('magnitude', 0.3))
    else:
        shock['magnitude'] = float(shock['magnitude'])
    shock.setdefault('kind', str(body.get('kind') or 'demand'))

    top_n = int(body.get('topN', 6))
    min_confidence = float(body.get('minConfidence', 0.6))
    category = body.get('category')
    return forecast_with_factors(
        graph, shock, top_n=top_n, min_confidence=min_confidence, category=category
    )


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


# ===========================================================================
# 页面4 收尾：自定义传导系数覆盖 / 风险标记 / 画布模板导出
# ===========================================================================
@router.put('/industry-chains/{chain_id}/edge-override')
def upsert_edge_override(
    chain_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """自定义产业链传导系数覆盖（页面4「自定义传导系数默认值」）。

    请求体: {source_node, target_node, coeff(0~1), lag(>=0)}
    覆盖默认 edges.coeff=0.6 / lag=5，写入后前端重调 propagate 刷新预测。
    """
    source_node = str(payload.get('sourceNode') or payload.get('source_node') or '')
    target_node = str(payload.get('targetNode') or payload.get('target_node') or '')
    if not source_node or not target_node:
        raise HTTPException(status_code=400, detail='source_node / target_node 不能为空')
    try:
        coeff = float(payload.get('coeff', 0.6))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='coeff 必须为数字')
    try:
        lag = int(payload.get('lag', 5))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='lag 必须为整数')
    coeff = max(0.0, min(1.0, coeff))  # clamp 0~1
    lag = max(0, lag)

    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        existing = (
            s.query(ChainEdgeOverride)
            .filter_by(chain_id=chain_id, source_node=source_node, target_node=target_node)
            .first()
        )
        if existing:
            existing.coeff = coeff
            existing.lag = lag
            row = existing
        else:
            row = ChainEdgeOverride(
                chain_id=chain_id,
                source_node=source_node,
                target_node=target_node,
                coeff=coeff,
                lag=lag,
            )
            s.add(row)
            s.flush()
        return {'code': 0, 'msg': 'ok', 'data': row.to_dict()}


@router.get('/industry-chains/{chain_id}/edge-overrides')
def list_edge_overrides(chain_id: str) -> Dict[str, Any]:
    """读取某产业链全部自定义传导系数覆盖。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.query(ChainEdgeOverride).filter_by(chain_id=chain_id).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


@router.post('/industry-chains/{chain_id}/risk-flag')
def add_chain_risk_flag(
    chain_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """产业链环节异常风险标记（页面4「行业异常自动标记风险」）。

    请求体: {node, risk_type(price_up|output_cut|oversupply|other), severity(高|中|低), note}
    """
    node = str(payload.get('node') or '')
    if not node:
        raise HTTPException(status_code=400, detail='node 不能为空')
    risk_type = str(payload.get('riskType') or payload.get('risk_type') or 'other')
    severity = str(payload.get('severity') or '中')
    note = payload.get('note')
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = ChainRiskFlag(
            chain_id=chain_id,
            node=node,
            risk_type=risk_type,
            severity=severity,
            note=note,
        )
        s.add(row)
        s.flush()
        return {'code': 0, 'msg': 'ok', 'data': row.to_dict()}


@router.get('/industry-chains/{chain_id}/risk-flags')
def list_chain_risk_flags(chain_id: str) -> Dict[str, Any]:
    """读取某产业链全部风险标记。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = s.query(ChainRiskFlag).filter_by(chain_id=chain_id).order_by(ChainRiskFlag.created_at.desc()).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


@router.get('/industry-chains/{chain_id}/export-template')
def export_chain_template(chain_id: str) -> Dict[str, Any]:
    """一键导出画布模板（页面4「导出模板」）。

    返回结构化 {nodes, edges, companies, meta}，可直接导入画布编辑器。
    """
    graph = _get_chain_graph(chain_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f'未找到产业链: {chain_id}')
    template = {
        'meta': {
            'chainId': graph.get('id'),
            'name': graph.get('name'),
            'category': graph.get('category'),
            'exportedAt': datetime.now().isoformat(),
        },
        'nodes': graph.get('nodes', []),
        'edges': graph.get('edges', []),
        'companies': graph.get('companies', {}),
    }
    return {'code': 0, 'msg': 'ok', 'data': template}
