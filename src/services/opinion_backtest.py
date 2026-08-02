"""舆情回测 + 拐点预警（蓝图 P2，#39）—— 元分析层（与 #38 同构，非信号源）。

两部分能力，均不改变内核决策权、不扩张候选池：

1. 舆情回测（各平台情绪因子历史胜率）：
   对六路可插拔舆情源（#25 披露 / #28 头条 / #31 微信 / #34 快讯 / #36 社区 / #37 海外）
   构造**确定性**的历史情绪序列 + 共享隐藏「真实涨跌因子」f，回测其情绪因子的：
   - 方向胜率（directionalWinRate：信号日情绪方向与次日均值的同向占比）
   - 多头胜率（longWinRate）/ 空头胜率（shortWinRate）
   - 信息系数 IC（情绪与次日均值的秩相关，衡量预测力）
   - 样本量 / 覆盖率 / 可靠性分级
   模型自觉地体现出「权威性越高耦合越强→胜率/IC 越高；散户噪声越大→弱相关甚至反向」，
   但胜率/IC 均由模拟序列**真实计算**得出，而非硬编码答案。

   说明：沙箱无真实历史行情，此处为**确定性模拟回测基线**（mock）；真实环境应替换为
   各源历史情绪 + 真实后验收益率的滚动回测。接口形态保持对齐，便于后续替换数据源。

2. 拐点预警（消费 #38 交叉验证 + 回测可靠性 + #35 Kronos 技术面）：
   对单只 alert 判定四类拐点信号：
   - 见顶拐点：散户集中看多（L3/L4）但无权威印证 → 高位狂热减仓
   - 启动拐点：权威（L0/L1）提前看多、散户尚未跟进 → 拉升初期逢低布局
   - 情绪反转：主导散户源历史 IC 偏弱/为负，当前一致看多 → 疑似反向指标
   - 技术·情绪背离：Kronos 技术面与舆情方向背离 → 警惕诱多/诱空
   输出 {level, types, reasons, confidence, suggestedAction} 与扫描级摘要。

复用 #38 的 `build_source_index` / `cross_validate_alert`，保证与既有元分析层一致。
"""
from __future__ import annotations

import hashlib
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from src.services.opinion_cross_validation import (
    build_source_index,
    cross_validate_alert,
)
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

# ---- 六路舆情源回测元数据（tier / 耦合强度 coupling / 噪声噪声噪声尺度 noise）----
# coupling / noise 仅决定模拟序列形态；胜率与 IC 由 simulate + backtest 真实计算。
SOURCE_META: Dict[str, Dict[str, Any]] = {
    'disclosure': {'label': '法定披露（巨潮/交易所）', 'tier': 'authoritative', 'coupling': 0.66, 'noise': 1.00},
    'overseas':   {'label': '海外权威（彭博/路透/WSJ/SeekingAlpha）', 'tier': 'authoritative', 'coupling': 0.58, 'noise': 1.00},
    'flash':      {'label': '短线快讯（财联社/华尔街见闻/金十）', 'tier': 'professional', 'coupling': 0.41, 'noise': 1.00},
    'community':  {'label': '深度社区（雪球/股吧/淘股吧）', 'tier': 'professional', 'coupling': 0.31, 'noise': 1.00},
    'wechat':     {'label': '微信私域（公众号/视频号）', 'tier': 'retail', 'coupling': 0.25, 'noise': 1.00},
    'opinion':    {'label': '公域散户（头条/抖音/小红书）', 'tier': 'retail', 'coupling': 0.10, 'noise': 1.00},
}

SIGNAL_THRESHOLD = 0.18  # 情绪绝对值 ≥ 此值记为「信号日」，参与方向胜率统计


# ---------------------------------------------------------------------------
# 确定性随机：以 (code, source, day) 派生的稳定种子，保证沙箱可复现
# ---------------------------------------------------------------------------
def _seed_int(*parts: str) -> int:
    h = hashlib.md5(('|'.join(parts)).encode('utf-8')).digest()
    return int.from_bytes(h[:8], 'big')


def _hidden_move(stock_code: str, day: int) -> float:
    """共享隐藏「真实次日均値涨跌因子」f（源无关），决定各源情绪应追踪的真实方向。"""
    rng = random.Random(_seed_int(stock_code, '__market__', str(day)))
    return rng.gauss(0.0, 1.0)


def simulate_source_series(stock_code: str, source_key: str, n_days: int = 60) -> List[Dict[str, float]]:
    """构造单 (标的, 源) 的 n_days 历史序列：情绪 = coupling·f + noise·e；次日均値 = f。"""
    meta = SOURCE_META[source_key]
    c, n = meta['coupling'], meta['noise']
    series: List[Dict[str, float]] = []
    for day in range(n_days):
        f = _hidden_move(stock_code, day)
        e = random.Random(_seed_int(stock_code, source_key, str(day))).gauss(0.0, 1.0)
        sentiment = max(-1.0, min(1.0, c * f + n * e))
        # 次日均値真实涨跌（源无关）；胜率衡量情绪对该方向的预测力
        forward_return = f * 0.02  # 缩放到 ±2% 日涨跌量级（仅符号参与胜率）
        series.append({'day': day, 'sentiment': round(sentiment, 4), 'forwardReturn': round(forward_return, 5)})
    return series


def _spearman(xs: List[float], ys: List[float]) -> float:
    """秩相关（Spearman），用于信息系数 IC；确定性、无外部依赖。"""
    def _rank(v: List[float]) -> List[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        ranks = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks
    n = len(xs)
    if n < 2:
        return 0.0
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n))
    vy = sum((ry[i] - my) ** 2 for i in range(n))
    if vx == 0 or vy == 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def backtest_series(series: List[Dict[str, float]]) -> Dict[str, Any]:
    """对一系列 (sentiment, forwardReturn) 计算回测指标。"""
    if not series:
        return {
            'samples': 0, 'bullishDays': 0, 'bearishDays': 0, 'neutralDays': 0,
            'directionalWinRate': 0.0, 'longWinRate': 0.0, 'shortWinRate': 0.0,
            'ic': 0.0, 'signalDirection': '弱相关',
        }
    sentiments = [s['sentiment'] for s in series]
    moves = [s['forwardReturn'] for s in series]

    bullish = [s for s in series if s['sentiment'] > SIGNAL_THRESHOLD]
    bearish = [s for s in series if s['sentiment'] < -SIGNAL_THRESHOLD]
    neutral = [s for s in series if abs(s['sentiment']) <= SIGNAL_THRESHOLD]

    # 方向胜率：信号日中情绪方向与次日均値同向的占比
    signal_days = bullish + bearish
    directional_wins = sum(1 for s in signal_days if (s['sentiment'] > 0) == (s['forwardReturn'] > 0))
    directional_win_rate = directional_wins / len(signal_days) if signal_days else 0.0
    # 多头胜率：看多日中次日均値上涨占比；空头胜率：看空日中次日均値下跌占比
    long_wins = sum(1 for s in bullish if s['forwardReturn'] > 0)
    short_wins = sum(1 for s in bearish if s['forwardReturn'] < 0)
    long_win_rate = long_wins / len(bullish) if bullish else 0.0
    short_win_rate = short_wins / len(bearish) if bearish else 0.0

    ic = _spearman(sentiments, moves)
    if ic > 0.20:
        signal_direction = '同向(正预测)'
    elif ic < -0.05:
        signal_direction = '反向(反向指标)'
    else:
        signal_direction = '弱相关'

    return {
        'samples': len(series),
        'bullishDays': len(bullish),
        'bearishDays': len(bearish),
        'neutralDays': len(neutral),
        'directionalWinRate': round(directional_win_rate, 4),
        'longWinRate': round(long_win_rate, 4),
        'shortWinRate': round(short_win_rate, 4),
        'ic': round(ic, 4),
        'signalDirection': signal_direction,
    }


def _reliability(ic: float, directional_win_rate: float) -> str:
    """可靠性分级：综合 IC 与方向胜率。"""
    if ic >= 0.30 and directional_win_rate >= 0.58:
        return '高'
    if ic >= 0.12:
        return '中'
    return '低'


def run_sentiment_backtest(codes: List[str], n_days: int = 60) -> Dict[str, Any]:
    """对覆盖标的集合跑六路源回测，返回 per-source 指标 + 汇总。

    codes：出现在任一舆情伴随表的标的（来自 build_source_index 的 keys）。
    """
    by_source: Dict[str, Dict[str, Any]] = {}
    for sk, meta in SOURCE_META.items():
        series: List[Dict[str, float]] = []
        for code in codes:
            series.extend(simulate_source_series(code, sk, n_days))
        m = backtest_series(series)
        m['source'] = sk
        m['label'] = meta['label']
        m['tier'] = meta['tier']
        m['coverage'] = len(codes)
        m['reliability'] = _reliability(m['ic'], m['directionalWinRate'])
        by_source[sk] = m

    # 汇总：按 IC 排序的强弱源、各 tier 平均方向胜率
    ranked = sorted(by_source.values(), key=lambda x: x['ic'], reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None
    tier_win: Dict[str, List[float]] = {}
    for m in by_source.values():
        tier_win.setdefault(m['tier'], []).append(m['directionalWinRate'])
    tier_avg = {t: round(sum(v) / len(v), 4) for t, v in tier_win.items()}

    return {
        'bySource': by_source,
        'nDays': n_days,
        'universeSize': len(codes),
        'summary': {
            'bestSource': best['source'] if best else None,
            'bestIc': round(best['ic'], 4) if best else 0.0,
            'worstSource': worst['source'] if worst else None,
            'worstIc': round(worst['ic'], 4) if worst else 0.0,
            'tierAvgDirectionalWinRate': tier_avg,
            'authoritativeAvgIc': round(
                sum(by_source[s]['ic'] for s in ('disclosure', 'overseas') if s in by_source)
                / max(1, sum(1 for s in ('disclosure', 'overseas') if s in by_source)), 4
            ),
            'retailAvgIc': round(
                sum(by_source[s]['ic'] for s in ('wechat', 'opinion') if s in by_source)
                / max(1, sum(1 for s in ('wechat', 'opinion') if s in by_source)), 4
            ),
        },
        'generatedAt': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
    }


def sentiment_backtest_over_pools() -> Dict[str, Any]:
    """独立端点 / 种子脚本用：跨全部池标的（不跑 run_closed_loop）计算舆情回测报告。"""
    with DatabaseManager().session_scope() as s:
        idx = build_source_index(s)
    return run_sentiment_backtest(list(idx.keys()))


# ---------------------------------------------------------------------------
# 拐点预警
# ---------------------------------------------------------------------------
_LEVEL_RANK = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}


def _bump(level: str, candidate: str) -> str:
    return candidate if _LEVEL_RANK.get(candidate, 0) > _LEVEL_RANK.get(level, 0) else level


def detect_inflection_for_alert(alert: Dict[str, Any], backtest_summary: Dict[str, Any]) -> Dict[str, Any]:
    """对单只 alert 判定拐点信号（消费 #38 交叉验证 + 回测可靠性 + #35 Kronos 技术面）。"""
    cv = alert.get('crossValidation') or {}
    kronos = alert.get('kronosInfo') or {}
    types: List[str] = []
    reasons: List[str] = []
    level = 'none'
    confidence = 0.0

    retail_count = int(cv.get('retailCount', 0) or 0)
    auth_count = int(cv.get('authoritativeCount', 0) or 0)
    direction = cv.get('direction', 'neutral')
    conflict = bool(cv.get('conflictFlag', False))

    # 1) 见顶拐点：散户集中看多（L3/L4）但无权威印证 → 高位狂热
    if direction == 'bullish' and auth_count == 0 and retail_count >= 2:
        types.append('见顶拐点')
        reasons.append('散户集中看多(L3/L4)但无权威印证，高位狂热，风险预警减仓')
        level = _bump(level, 'high')
        confidence = max(confidence, min(0.85, 0.55 + 0.10 * retail_count))
    elif direction == 'bullish' and auth_count == 0 and retail_count == 1:
        types.append('见顶拐点')
        reasons.append('散户看多但无权威印证，警惕追高')
        level = _bump(level, 'medium')
        confidence = max(confidence, 0.45)

    # 2) 启动拐点：权威(L0/L1)提前看多、散户尚未跟进 → 拉升初期
    if direction == 'bullish' and auth_count >= 1 and retail_count == 0:
        types.append('启动拐点')
        reasons.append('权威(L0/L1)提前看多，散户尚未跟进，拉升初期可逢低布局')
        level = _bump(level, 'medium')
        confidence = max(confidence, min(0.8, 0.45 + 0.10 * auth_count))

    # 3) 情绪反转：主导散户源历史 IC 偏弱/为负，当前一致看多 → 疑似反向指标
    by_source = (backtest_summary or {}).get('bySource', {}) or {}
    retail_ic = [by_source.get(s, {}).get('ic', 0.0) for s in ('wechat', 'opinion', 'community') if s in by_source]
    retail_ic_avg = sum(retail_ic) / len(retail_ic) if retail_ic else 0.0
    if direction == 'bullish' and auth_count == 0 and retail_count >= 2 and retail_ic_avg <= 0.12:
        types.append('情绪反转')
        reasons.append(f'主导散户源历史 IC 偏弱(均={retail_ic_avg:.2f})，当前一致看多或为反向指标')
        level = _bump(level, 'high')
        confidence = max(confidence, 0.58)

    # 4) 技术·情绪背离：Kronos 技术面与舆情方向背离
    k_trend = kronos.get('trend') if isinstance(kronos, dict) else None
    if k_trend == '多头趋势' and direction == 'bearish':
        types.append('技术·情绪背离')
        reasons.append('技术面多头但舆情偏空，警惕诱多')
        level = _bump(level, 'medium')
        confidence = max(confidence, 0.5)
    elif k_trend == '空头趋势' and direction == 'bullish':
        types.append('技术·情绪背离')
        reasons.append('技术面空头但舆情偏多，警惕诱空')
        level = _bump(level, 'medium')
        confidence = max(confidence, 0.5)

    # 权威×散户冲突本身也是一种拐点前兆
    if conflict and level == 'none':
        types.append('方向冲突')
        reasons.append('权威与散户方向背离，拐点概率上升')
        level = _bump(level, 'low')
        confidence = max(confidence, 0.4)

    if not types:
        return {
            'level': 'none',
            'types': ['无'],
            'reasons': ['暂无显著拐点信号'],
            'confidence': 0.0,
            'suggestedAction': '中性观察',
        }

    # 建议动作：见顶/情绪反转→减仓观望；启动→逢低布局；其余→中性观察
    if '见顶拐点' in types or '情绪反转' in types:
        action = '减仓/观望'
    elif '启动拐点' in types:
        action = '逢低布局'
    else:
        action = '中性观察'

    return {
        'level': level,
        'types': types,
        'reasons': reasons,
        'confidence': round(confidence, 3),
        'suggestedAction': action,
    }


def summarize_inflection(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从已附加 inflectionWarning 的 alerts 聚合扫描级拐点摘要。"""
    level_dist = {'high': 0, 'medium': 0, 'low': 0, 'none': 0}
    type_dist: Dict[str, int] = {}
    high_alerts: List[Dict[str, Any]] = []
    for a in alerts:
        w = a.get('inflectionWarning') or {}
        lvl = w.get('level', 'none')
        level_dist[lvl] = level_dist.get(lvl, 0) + 1
        for t in w.get('types', []):
            if t == '无':
                continue
            type_dist[t] = type_dist.get(t, 0) + 1
        if lvl == 'high':
            high_alerts.append({'stockCode': a.get('stockCode'), 'stockName': a.get('stockName'),
                                'types': w.get('types'), 'confidence': w.get('confidence'),
                                'suggestedAction': w.get('suggestedAction')})
    return {
        'totalAlerts': len(alerts),
        'levelDistribution': level_dist,
        'typeDistribution': type_dist,
        'highCount': level_dist['high'],
        'mediumCount': level_dist['medium'],
        'lowCount': level_dist['low'],
        'noneCount': level_dist['none'],
        'highInflectionAlerts': high_alerts,
    }


def summarize_inflection_over_pools(session) -> Dict[str, Any]:
    """独立端点用：跨全部池标的（不跑 run_closed_loop）计算拐点预警摘要。"""
    idx = build_source_index(session)
    bt = run_sentiment_backtest(list(idx.keys()))
    alerts: List[Dict[str, Any]] = []
    for code in idx.keys():
        cv = cross_validate_alert(code, idx)
        alerts.append({'stockCode': code, 'crossValidation': cv, 'kronosInfo': None})
    for a in alerts:
        a['inflectionWarning'] = detect_inflection_for_alert(a, bt)
    return summarize_inflection(alerts)
