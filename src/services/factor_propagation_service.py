# -*- coding: utf-8 -*-
"""因子库 → DSA 内核正向传导桥接（DSA-BACKTRACE-V1.0 闭环增强，外挂微服务，不改动 DSA 内核）。

把 #17 沉淀的标准化「上涨因子库」转化为 DSA 引擎 propagate_shock 的因子权重，并真实注入
四周期正向传导对比：

  1. 取因子库 top-N（按期望净收益排序、按置信度过滤）→ 归一化权重 → factor_weights 字典；
  2. 按因子类别 → 产业链边类型 映射（#22 结构化注入），差异化增强对应边系数：
     基本面事件驱动 → supply/cost；资金筹码驱动 → demand；题材情绪驱动 → subst(+demand)；
  3. 把匹配边的 coeff 覆盖（use_overrides 通道，无向图双向写入）注入 propagate_shock，
     并给出结构化注入总增益 structuredBoost（包络幅度增益，钳制 [0, 0.5]）；
  4. 输出 基线 vs 增强 的最大冲击 / 影响环节 / 涉及公司、提升幅度，以及四周期正向传导预测，
     并附 edgeOverrides（被注入边明细）与 categoryEdgeContrib（类别→边 贡献拆解）。

设计原则：
  - DSA 内核 propagate_shock 的 factor_weights 当前为「仅回显」，本桥接通过「结构化边系数覆盖
    (use_overrides) + 包络幅度增益」真实影响传导，内核零改动；未来内核若支持 factor_weights
    加权传导，可直接消费同一字典，向后兼容；
  - 全部数学加权，不依赖 LLM；沙箱确定性 mock，真实环境因子库由生产归因累积替代。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.industry_chain_propagation import propagate_shock
from src.services.factor_library_service import list_factor_library

logger = logging.getLogger(__name__)

# 结构化注入（#22）：边系数覆盖缩放与总增益上限（与旧幅度增益上限一致，保证增益合理不失控）
_EDGE_BOOST_SCALE = 0.5       # 单类边增益缩放（叠加进 edge coeff）
_STRUCTURED_BOOST_CAP = 0.5   # 结构化注入总增益（包络幅度增益）上限
# 四周期正向传导衰减档位（1 周 / 2 周 / 1 月 / 6 月），相对峰值冲击的折算系数
_FOUR_PERIOD_SCHEDULE: List[float] = [0.45, 0.70, 1.0, 0.85]
_FOUR_PERIOD_LABELS: List[str] = ['1w', '2w', '1m', '6m']

# 因子类别 → 产业链边类型 结构化注入映射（按因子类别差异化增强对应边，内核零改动）。
# 内核 propagate_shock 把图当无向遍历（overrides 键为 (cur, nb)），故每条边需同时写入
# (source, target) 与 (target, source) 两个方向，确保正/反向遍历都能命中增强系数。
_FACTOR_CATEGORY_EDGE_MAP: Dict[str, List[Tuple[str, float]]] = {
    '基本面事件驱动': [('supply', 1.0), ('cost', 0.8)],
    '资金筹码驱动':   [('demand', 1.0)],
    '题材情绪驱动':   [('subst', 0.9), ('demand', 0.4)],
}
_VALID_EDGE_TYPES = {'cost', 'demand', 'supply', 'subst'}


def _expectancy_score(expectancy: float) -> float:
    """期望净收益 → 0~1 得分（期望区间约 [-7, +9] 线性映射并钳制）。"""
    return max(0.0, min(1.0, (float(expectancy) + 8.0) / 16.0))


def build_factor_weights(
    top_n: int = 6,
    min_confidence: float = 0.6,
    category: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """取因子库 top-N，归一化为桥接权重。

    Returns:
        weights_list: [{factorName, factorCategory, weight(0~1), avgWinRate, confidence, expectancy1m}, ...]
        factor_weights: {factorName: weight}  —— 供 DSA 内核 factor_weights 回显 / 未来消费
    """
    resp = list_factor_library(sort_by='expectancy')
    items = resp.get('items', []) if resp.get('code') == 0 else []
    filtered = [
        it for it in items
        if float(it.get('confidence', 0)) >= min_confidence
        and (category is None or it.get('factorCategory') == category)
    ]
    filtered.sort(key=lambda x: float(x.get('expectancy1m', 0)), reverse=True)
    top = filtered[: max(1, top_n)]

    raw = [max(0.0, float(t.get('expectancy1m', 0))) for t in top]
    s = sum(raw) or 1.0
    weights_list: List[Dict[str, Any]] = []
    factor_weights: Dict[str, float] = {}
    for t, rw in zip(top, raw):
        w = round(rw / s, 4)
        weights_list.append({
            'factorName': t['factorName'],
            'factorCategory': t['factorCategory'],
            'weight': w,
            'avgWinRate': t['avgWinRate'],
            'confidence': t['confidence'],
            'expectancy1m': t['expectancy1m'],
        })
        factor_weights[t['factorName']] = w
    return weights_list, factor_weights


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _build_edge_overrides(
    graph: Dict[str, Any],
    weights_list: List[Dict[str, Any]],
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], float]:
    """按因子类别差异化构建边系数覆盖（结构化注入），内核零改动走 use_overrides 通道。

    把命中因子的类别映射到对应产业链边类型（supply/cost/demand/subst），按权重×期望得分×
    通道权重聚合每类边的增益，并覆盖到图谱对应边上；图被内核当无向遍历，故每条边双向写入。

    Returns:
        overrides: {(source,target): {coeff,lag}, ...}  —— 供内核 propagate_shock 消费
        edge_overrides: [{source,target,edgeType,baseCoeff,overrideCoeff,boost,categories}]  —— 展示用
        category_edge_contrib: [{factorCategory,edgeType,boost,factors}]  —— 类别→边 贡献拆解
        structured_boost: 0~1 聚合标量（整体放大包络，便于闭环 composite / 前端展示）
    """
    edges = graph.get('edges', [])

    # 1) 按 (因子类别, 边类型) 聚合增益贡献，并记录贡献因子
    contrib: Dict[Tuple[str, str], float] = {}
    contrib_factors: Dict[Tuple[str, str], List[str]] = {}
    for w in weights_list:
        cat = w.get('factorCategory') or '综合'
        score = _expectancy_score(float(w.get('expectancy1m', 0)))
        for etype, cw in _FACTOR_CATEGORY_EDGE_MAP.get(cat, []):
            key = (cat, etype)
            contrib[key] = contrib.get(key, 0.0) + w['weight'] * score * cw
            contrib_factors.setdefault(key, []).append(w['factorName'])

    # 2) 按边类型汇总（跨类别）→ 决定每条边的最终增益
    edge_type_boost: Dict[str, float] = {}
    for (_c, etype), v in contrib.items():
        edge_type_boost[etype] = edge_type_boost.get(etype, 0.0) + v

    # 3) 生成边覆盖（无向：双向写入）+ 展示明细
    overrides: Dict[Tuple[str, str], Dict[str, Any]] = {}
    edge_overrides: List[Dict[str, Any]] = []
    for e in edges:
        etype = e.get('type')
        if etype not in edge_type_boost or etype not in _VALID_EDGE_TYPES:
            continue
        base = float(e.get('coeff', 0.6) or 0.6)
        new_coeff = _clamp(base + _EDGE_BOOST_SCALE * edge_type_boost[etype], 0.0, 1.0)
        if abs(new_coeff - base) < 1e-4:
            continue
        s, t = e.get('source'), e.get('target')
        ov = {'coeff': round(new_coeff, 4), 'lag': float(e.get('lag', 0) or 0)}
        overrides[(s, t)] = ov
        overrides[(t, s)] = ov
        cats = sorted({c for (c, et) in contrib if et == etype})
        edge_overrides.append({
            'source': s, 'target': t, 'edgeType': etype,
            'baseCoeff': round(base, 4), 'overrideCoeff': round(new_coeff, 4),
            'boost': round(new_coeff - base, 4), 'categories': cats,
        })

    # 4) 类别→边 贡献拆解（前端展示用）
    category_edge_contrib: List[Dict[str, Any]] = []
    for (cat, etype), v in sorted(contrib.items(), key=lambda x: -x[1]):
        category_edge_contrib.append({
            'factorCategory': cat, 'edgeType': etype,
            'boost': round(_EDGE_BOOST_SCALE * v, 4),
            'factors': sorted(set(contrib_factors[(cat, etype)])),
        })

    # 结构化注入总增益 = 最强被注入通道的系数增益（代表整体放大的包络上限，便于闭环 composite / 前端展示）
    structured_boost = _clamp(
        max((o['boost'] for o in edge_overrides), default=0.0), 0.0, _STRUCTURED_BOOST_CAP
    )
    return overrides, edge_overrides, category_edge_contrib, round(structured_boost, 4)


def forecast_with_factors(
    graph: Dict[str, Any],
    shock: Dict[str, Any],
    weights_list: Optional[List[Dict[str, Any]]] = None,
    top_n: int = 6,
    min_confidence: float = 0.6,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """因子库 → DSA 内核正向传导桥接（基线 vs 增强 + 四周期预测）。

    Args:
        graph: 产业链图谱(dict)，含 nodes/edges/companies（来自 industry_chain 接口）。
        shock: {node, magnitude, kind}。
        weights_list: 显式因子权重（为 None 时由 build_factor_weights 生成）。
        top_n / min_confidence / category: 因子库筛选参数。
    Returns:
        {code, data:{ chainId, shockNode, baseMagnitude, boostedMagnitude, boost,
                      structuredBoost, edgeOverrides, categoryEdgeContrib,
                      factorWeights, baseline, enhanced, liftPct, forward4, factors,
                      engine, generatedAt }}
    """
    from datetime import datetime

    if weights_list is None:
        weights_list, factor_weights = build_factor_weights(
            top_n=top_n, min_confidence=min_confidence, category=category
        )
    else:
        factor_weights = {w['factorName']: w['weight'] for w in weights_list}

    # #22 结构化注入：按因子类别差异化增强对应边系数（内核 use_overrides 通道，零改动）
    overrides, edge_overrides, category_edge_contrib, structured_boost = _build_edge_overrides(
        graph, weights_list
    )
    boost = structured_boost  # 结构化注入总增益（包络幅度增益），语义升级自旧「幅度增益」
    base_mag = float(shock.get('magnitude', 0.0))
    enhanced_mag = base_mag * (1.0 + boost)

    base_opts = {
        'max_depth': 20,
        'bidirectional_decay': 0.85,
        'bearish_decay': 0.7,
        'use_overrides': False,
        'overrides': {},
        'factor_weights': factor_weights,  # 回显：因子已纳入传导考量
    }
    # 增强视图：包络幅度放大 + 结构化边系数覆盖（匹配因子类别的边获得更强传导）
    enhanced_opts = {
        'max_depth': 20,
        'bidirectional_decay': 0.85,
        'bearish_decay': 0.7,
        'use_overrides': True,
        'overrides': overrides,
        'factor_weights': factor_weights,
    }

    baseline = propagate_shock(graph, shock, base_opts)
    enhanced = propagate_shock(
        graph, {**shock, 'magnitude': enhanced_mag}, enhanced_opts
    )

    b_sum = baseline.get('summary', {})
    e_sum = enhanced.get('summary', {})
    b_max = float(b_sum.get('max_impact_pct', 0.0))
    e_max = float(e_sum.get('max_impact_pct', 0.0))
    b_nodes = int(b_sum.get('impacted_nodes', 0))
    e_nodes = int(e_sum.get('impacted_nodes', 0))
    b_comp = int(b_sum.get('affected_companies', 0))
    e_comp = int(e_sum.get('affected_companies', 0))

    forward4 = {
        'periods': list(_FOUR_PERIOD_LABELS),
        'baseline': [round(b_max * k, 2) for k in _FOUR_PERIOD_SCHEDULE],
        'enhanced': [round(e_max * k, 2) for k in _FOUR_PERIOD_SCHEDULE],
    }

    data = {
        'chainId': graph.get('id'),
        'shockNode': baseline.get('shock_label') or shock.get('node'),
        'baseMagnitude': round(base_mag, 4),
        'boostedMagnitude': round(enhanced_mag, 4),
        'boost': round(boost, 4),
        'structuredBoost': round(structured_boost, 4),
        'edgeOverrides': edge_overrides,
        'categoryEdgeContrib': category_edge_contrib,
        'factorWeights': factor_weights,
        'baseline': {
            'maxImpactPct': b_max,
            'impactedNodes': b_nodes,
            'affectedCompanies': b_comp,
        },
        'enhanced': {
            'maxImpactPct': e_max,
            'impactedNodes': e_nodes,
            'affectedCompanies': e_comp,
        },
        'liftPct': {
            'maxImpact': round((e_max - b_max), 2),
            'impactedNodes': e_nodes - b_nodes,
            'affectedCompanies': e_comp - b_comp,
        },
        'forward4': forward4,
        'factors': weights_list,
        'engine': 'factor-library-forward-propagation',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
    }
    return {'code': 0, 'msg': 'ok', 'data': data}
