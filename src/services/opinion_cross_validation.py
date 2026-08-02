"""多源交叉验证（蓝图 §五.1，P1 落地）—— 元分析层（#38）。

消费已落地七路源（#23 行情大涨池 / #25 披露 / #28 头条 / #31 微信 / #34 快讯 / #36 社区 /
#37 海外）的 per-stock 情感 / 可信度 / 谣言标记，归入六层信息圈层（opinion_info_layers），计算：
- 圈层命中（layersHit）
- 独立权威源数（authoritativeCount：披露 1 + 海外去重平台数）
- 共识等级（strong / moderate / weak / none，§4）
- 可信度分数（single retail ≤ 0.3；单权威 0.5；2+ 权威 0.7~0.9）
- 方向（加权净情绪）
- 冲突标记（权威方向与散户方向背离）
- 谣言标记（任一命中源 hasRumor）

不改变内核决策权；仅做可信度 / 共识 / 冲突的元标注，供前端圈层矩阵与预警分级参考。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.services.opinion_info_layers import (
    AUTHORITATIVE_TIERS,
    RETAIL_TIERS,
    CRED_SINGLE_RETAIL_CAP,
    CRED_SINGLE_AUTH,
    CRED_MULTI_AUTH_FLOOR,
    CRED_MULTI_AUTH_CEIL,
    TIER_DIRECTION_WEIGHT,
)
from src.storage import (
    BacktraceDisclosure,
    BacktraceOpinion,
    BacktraceWechatOpinion,
    BacktraceFlashOpinion,
    BacktraceCommunityOpinion,
    BacktraceOverseasOpinion,
)

logger = logging.getLogger(__name__)


def _dir(sentiment: Optional[str]) -> int:
    """把情感文案归一为方向整数：利好/看多→+1，利空/看空→-1，其余→0。"""
    if not sentiment:
        return 0
    s = sentiment.strip()
    if s in ('利好', '看多', 'bullish', 'Bullish'):
        return 1
    if s in ('利空', '看空', 'bearish', 'Bearish'):
        return -1
    return 0


def build_source_index(session) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """一次性读取七路源的 per-stock 情感/可信度/谣言，构建内存索引（避免逐 alert 查库）。"""
    idx: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: {'disclosure': [], 'opinion': [], 'wechat': [], 'flash': [], 'community': [], 'overseas': []}
    )
    for r in session.query(BacktraceDisclosure).all():
        idx[str(r.stock_code)]['disclosure'].append(
            {'sentiment': r.sentiment, 'sentimentScore': None, 'hasRumor': False}
        )
    for r in session.query(BacktraceOpinion).all():
        idx[str(r.stock_code)]['opinion'].append(
            {'sentiment': r.sentiment, 'sentimentScore': r.sentiment_score, 'hasRumor': bool(r.has_rumor), 'stage': r.stage}
        )
    for r in session.query(BacktraceWechatOpinion).all():
        idx[str(r.stock_code)]['wechat'].append(
            {'sentiment': r.sentiment, 'sentimentScore': r.sentiment_score, 'hasRumor': bool(r.has_rumor), 'credibility': r.credibility}
        )
    for r in session.query(BacktraceFlashOpinion).all():
        idx[str(r.stock_code)]['flash'].append(
            {'sentiment': r.sentiment, 'sentimentScore': r.sentiment_score, 'hasRumor': bool(r.has_rumor), 'isBreaking': bool(r.is_breaking)}
        )
    for r in session.query(BacktraceCommunityOpinion).all():
        idx[str(r.stock_code)]['community'].append(
            {'sentiment': r.sentiment, 'sentimentScore': r.sentiment_score, 'hasRumor': bool(r.has_rumor), 'quality': r.quality}
        )
    for r in session.query(BacktraceOverseasOpinion).all():
        idx[str(r.stock_code)]['overseas'].append(
            {
                'sentiment': r.sentiment,
                'sentimentScore': r.sentiment_score,
                'hasRumor': False,
                'platform': r.platform,
                'rating': r.rating,
                'isInstitution': bool(r.is_institution),
            }
        )
    return idx


def cross_validate_alert(stock_code: str, idx: Dict[str, Any]) -> Dict[str, Any]:
    """对单只标的执行六层圈层 + 多源交叉验证，返回元标注 dict。"""
    entry = idx.get(str(stock_code)) or {
        'disclosure': [], 'opinion': [], 'wechat': [], 'flash': [], 'community': [], 'overseas': []
    }
    signals: List[Dict[str, Any]] = []

    # 披露 → L0（权威，官方公告）
    for row in entry['disclosure']:
        signals.append({'source': 'disclosure', 'layer': 'L0', 'tier': 'authoritative', 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor'))})
    # 海外 → L1（权威），按平台去重计入独立权威数
    overseas_platforms: set = set()
    for row in entry['overseas']:
        overseas_platforms.add(row.get('platform'))
        signals.append({'source': 'overseas', 'layer': 'L1', 'tier': 'authoritative', 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor'))})
    # 快讯 → L2（专业短线节奏）
    for row in entry['flash']:
        signals.append({'source': 'flash', 'layer': 'L2', 'tier': 'professional', 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor'))})
    # 社区 → 雪球高质量 L2，股吧/淘股吧噪音 L3
    for row in entry['community']:
        layer = 'L2' if (row.get('quality') == '高质量') else 'L3'
        tier = 'professional' if layer == 'L2' else 'retail'
        signals.append({'source': 'community', 'layer': layer, 'tier': tier, 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor'))})
    # 微信 → L3（私域圈层）
    for row in entry['wechat']:
        signals.append({'source': 'wechat', 'layer': 'L3', 'tier': 'retail', 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor')), 'credibility': row.get('credibility')})
    # 头条 → L4（公域散户）
    for row in entry['opinion']:
        signals.append({'source': 'opinion', 'layer': 'L4', 'tier': 'retail', 'direction': _dir(row.get('sentiment')), 'hasRumor': bool(row.get('hasRumor'))})

    layers_hit = sorted({s['layer'] for s in signals}, key=lambda x: int(x[1:]))
    authoritative_signals = [s for s in signals if s['tier'] == 'authoritative']
    retail_signals = [s for s in signals if s['tier'] == 'retail']
    authoritative_count = (1 if entry['disclosure'] else 0) + len(overseas_platforms)
    retail_count = len(retail_signals)
    # 去重源数（海外按平台去重，其余按源类型）
    distinct_sources = len({(s['source'], s.get('platform') if s['source'] == 'overseas' else s['source']) for s in signals})

    # 可信度（§4）
    if authoritative_count == 0 and retail_count > 0:
        credibility = CRED_SINGLE_RETAIL_CAP  # 单一自媒体/散户爆料：≤0.3，大幅降权
    elif authoritative_count == 1:
        credibility = CRED_SINGLE_AUTH  # 单一权威源：中等可信
    elif authoritative_count >= 2:
        credibility = min(CRED_MULTI_AUTH_CEIL, CRED_MULTI_AUTH_FLOOR + 0.05 * (authoritative_count - 2))  # 2+ 权威 0.7~0.9
    else:
        credibility = 0.0

    # 方向（加权净情绪）
    w_sum = 0.0
    d_sum = 0.0
    for s in signals:
        w = TIER_DIRECTION_WEIGHT.get(s['layer'], 0.4)
        w_sum += w
        d_sum += w * s['direction']
    net = (d_sum / w_sum) if w_sum > 0 else 0.0
    direction = 'bullish' if net > 0.05 else ('bearish' if net < -0.05 else 'neutral')

    # 共识等级（§4）
    if authoritative_count >= 2:
        consensus = 'strong'
    elif authoritative_count == 1:
        consensus = 'moderate'
    elif retail_count > 0:
        consensus = 'weak'
    else:
        consensus = 'none'

    # 冲突：权威净方向 vs 散户净方向背离
    auth_net = sum(TIER_DIRECTION_WEIGHT.get(s['layer'], 1.0) * s['direction'] for s in authoritative_signals)
    retail_net = sum(TIER_DIRECTION_WEIGHT.get(s['layer'], 0.4) * s['direction'] for s in retail_signals)
    conflict = (auth_net > 0 and retail_net < 0) or (auth_net < 0 and retail_net > 0)

    rumor_flag = any(s['hasRumor'] for s in signals)

    return {
        'layersHit': layers_hit,
        'authoritativeCount': authoritative_count,
        'retailCount': retail_count,
        'distinctSources': distinct_sources,
        'credibilityScore': round(credibility, 3),
        'direction': direction,
        'consensusLevel': consensus,
        'conflictFlag': bool(conflict),
        'rumorFlag': bool(rumor_flag),
        'sources': [
            {
                'source': s['source'],
                'layer': s['layer'],
                'tier': s['tier'],
                'direction': 'bullish' if s['direction'] > 0 else ('bearish' if s['direction'] < 0 else 'neutral'),
                'hasRumor': s['hasRumor'],
            }
            for s in signals
        ],
    }


def aggregate_summary(per_alert: List[Dict[str, Any]], technical_bull: int = 0) -> Dict[str, Any]:
    """从已附加 crossValidation 的 alerts（或 {'crossValidation': cv} 包裹）聚合扫描级摘要。"""
    layer_dist: Dict[str, int] = {f'L{i}': 0 for i in range(6)}
    consensus_dist: Dict[str, int] = {'strong': 0, 'moderate': 0, 'weak': 0, 'none': 0}
    multi = 0
    auth_confirmed = 0
    conflict = 0
    rumor = 0
    for a in per_alert:
        cv = a.get('crossValidation') or {}
        for L in cv.get('layersHit', []):
            if L in layer_dist:
                layer_dist[L] += 1
        cl = cv.get('consensusLevel', 'none')
        consensus_dist[cl] = consensus_dist.get(cl, 0) + 1
        if cv.get('distinctSources', 0) >= 2:
            multi += 1
        if cv.get('authoritativeCount', 0) >= 1:
            auth_confirmed += 1
        if cv.get('conflictFlag'):
            conflict += 1
        if cv.get('rumorFlag'):
            rumor += 1
    return {
        'totalAlerts': len(per_alert),
        'layerDistribution': layer_dist,
        'consensusDistribution': consensus_dist,
        'multiSourceConfirmed': multi,
        'authoritativeConfirmed': auth_confirmed,
        'conflictAlerts': conflict,
        'rumorAlerts': rumor,
        'technicalBullConfirmed': technical_bull,  # #35 Kronos 技术面多头确认数（补充，非信息圈层）
    }


def cross_validate_scan(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从已附加 crossValidation 的 alerts 聚合扫描级摘要。"""
    tech_bull = sum(1 for a in alerts if (a.get('kronosInfo') or {}).get('trend') == '多头趋势')
    return aggregate_summary(alerts, technical_bull=tech_bull)


def summarize_over_pools(session) -> Dict[str, Any]:
    """独立端点用：跨全部池标的（不跑 run_closed_loop）计算交叉验证摘要。"""
    idx = build_source_index(session)
    per_alert = [{'crossValidation': cross_validate_alert(code, idx)} for code in idx.keys()]
    return aggregate_summary(per_alert)
