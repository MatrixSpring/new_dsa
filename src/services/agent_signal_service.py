# -*- coding: utf-8 -*-
"""Agent 自主深挖小众突发事件（DSA-BACKTRACE-V1.0 增强模块，外挂微服务，不改动 DSA 内核）。

在反向回溯（§3.1~§3.7）基础上，让 Agent 主动扫描股价异动前窗口内的隐蔽早期信号：
  1) 机构调研   —— 调研纪要 / 电话会提前透露的订单与产能线索
  2) 产业链异动 —— 上下游订单 / 产能 / 价格异动（比公开公告更早）
  3) 舆情小道消息 —— 未公开的题材发酵 / 社群传闻
  4) 游资动向   —— 活跃席位 / 龙虎榜提前埋伏

设计原则（对齐 §7 决策权坚守）：
  - 全部数学打分（时间临近度 + 来源可信度 + 相关度），不依赖 LLM 主观臆断；
  - 沙箱无外网 / 无 LLM key，信号源走确定性 mock，真实环境替换为调研平台 /
    舆情监控系统 / 龙虎榜接口，接口契约不变；
  - 早期信号（lead_days ≥ 阈值）标识为「小众突发事件」，反哺归因 driving_factor
    的早期佐证强度（可在 §3.4 归因中作为隐藏证据的置信度加权项）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.storage import BacktraceAgentSignal, BacktraceScreenPool, DatabaseManager

logger = logging.getLogger(__name__)

# 提前天数阈值：距拉升起始日 ≥ 该值的信号视为「小众早期信号」（隐藏性高、可提前预警）。
EARLY_LEAD_DAYS = 10

# Agent 主动扫描的四大隐藏信号源（确定性模板；真实环境替换为各渠道实时检索）。
_SIGNAL_TEMPLATES: List[Dict[str, Any]] = [
    {
        'signal_type': '机构调研',
        'lead_days': 19,
        'source': '进门财经 / 私下调研纪要',
        'credibility': 0.82,
        'summary_tpl': '{name}近期接待{ind}主题机构密集调研，交流中透露订单能见度提升与产能爬坡进度',
    },
    {
        'signal_type': '产业链异动',
        'lead_days': 13,
        'source': '产业链上下游情报',
        'credibility': 0.78,
        'summary_tpl': '{ind}上游环节出现订单与价格异动，下游客户提前锁定产能，供需缺口扩大',
    },
    {
        'signal_type': '舆情小道消息',
        'lead_days': 8,
        'source': '社群 / 雪球 / 韭研社',
        'credibility': 0.48,
        'summary_tpl': '{ind}题材在投资社群开始发酵，出现未公开合作与政策预期的小道消息',
    },
    {
        'signal_type': '游资动向',
        'lead_days': 3,
        'source': '龙虎榜 / 活跃席位监控',
        'credibility': 0.56,
        'summary_tpl': '多个活跃游资席位提前埋伏{name}，换手率与量比异动，短线情绪升温',
    },
]

# 各信号源与该股拉升主题的相关度（确定性；真实环境按命中关键词动态计算）。
_RELEVANCE: Dict[str, float] = {
    '机构调研': 0.72,
    '产业链异动': 0.88,
    '舆情小道消息': 0.58,
    '游资动向': 0.66,
}


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _score(lead_days: int, window_days: int, credibility: float, relevance: float) -> float:
    """综合打分（0~100）：时间临近度 0.5 + 来源可信度 0.3 + 相关度 0.2。

    lead_days 越大（出现越早），归一化后得分越高 —— 越早期的隐藏信号越具提前预警价值。
    """
    norm_lead = min(1.0, max(0.0, float(lead_days) / max(window_days, 1)))
    score = (0.5 * norm_lead + 0.3 * credibility + 0.2 * relevance) * 100.0
    return round(score, 1)


def _find_pool_stock(stock_code: str) -> Optional[Dict[str, Any]]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = (
            s.query(BacktraceScreenPool)
            .filter_by(stock_code=stock_code)
            .order_by(BacktraceScreenPool.id.desc())
            .first()
        )
        if row is None:
            return None
        return {
            'stock_code': row.stock_code, 'stock_name': row.stock_name,
            'daily_gain': row.daily_gain, 'industry': row.industry,
            'rise_start_date': row.rise_start_date, 'gain_type': row.gain_type,
            'consecutive_days': row.consecutive_days, 'amount_yi': row.amount_yi,
        }


def _resolve_stock(stock_code: str, rise_start_date: Optional[str]) -> Optional[Dict[str, Any]]:
    """定位标的：优先筛选池；缺失则惰性建池；最终兜底取 mock 元信息。"""
    stock = _find_pool_stock(stock_code)
    if stock is None:
        from src.services import backtrace_service
        backtrace_service.screen_big_rise(_today_str())
        stock = _find_pool_stock(stock_code)
    if stock is None:
        from src.services import backtrace_service
        stock = next((r for r in backtrace_service._MOCK_POOL if r['stock_code'] == stock_code), None)
    if stock is None:
        return None
    if rise_start_date:
        stock = {**stock, 'rise_start_date': rise_start_date}
    return stock


def _mock_signals_for(stock: Dict[str, Any], window_days: int) -> List[Dict[str, Any]]:
    """为单只个股确定性生成「拉升前」隐藏早期信号（均早于拉升起始日）。"""
    try:
        rise_start = datetime.strptime(stock['rise_start_date'], '%Y-%m-%d')
    except (ValueError, KeyError, TypeError):
        rise_start = datetime.now() - timedelta(days=1)
    name = stock.get('stock_name', '标的')
    ind = stock.get('industry', '行业')

    out: List[Dict[str, Any]] = []
    for t in _SIGNAL_TEMPLATES:
        lead = t['lead_days']
        if lead > window_days:
            lead = window_days  # 收敛进窗口
        sig_date = (rise_start - timedelta(days=lead)).strftime('%Y-%m-%d')
        relevance = _RELEVANCE.get(t['signal_type'], 0.6)
        score = _score(lead, window_days, t['credibility'], relevance)
        out.append({
            'signal_type': t['signal_type'],
            'signal_date': sig_date,
            'lead_days': lead,
            'source': t['source'],
            'summary': t['summary_tpl'].format(name=name, ind=ind),
            'credibility': t['credibility'],
            'relevance': relevance,
            'score': score,
            'is_early': 1 if lead >= EARLY_LEAD_DAYS else 0,
        })
    return out


def agent_dig(stock_code: str, rise_start_date: Optional[str] = None,
              window_days: int = 30) -> Dict[str, Any]:
    """增强模块：Agent 自主深挖小众突发事件（拉升前隐藏早期信号扫描与打分）。

    Returns: {code, msg, data:{ stockCode, stockName, riseStartDate, windowDays,
              signalCount, earlyCount, typeDistribution, signals(ranked),
              timeline(date-asc), engine, generatedAt }}
    """
    stock = _resolve_stock(stock_code, rise_start_date)
    if stock is None:
        return {'code': 1, 'msg': f'未找到标的: {stock_code}', 'data': None}
    rise_start = stock.get('rise_start_date')
    if rise_start is None:
        return {'code': 2, 'msg': '缺少拉升起始日', 'data': None}

    raw_signals = _mock_signals_for(stock, window_days)
    # 按综合得分降序（突出高价值早期信号）
    ranked = sorted(raw_signals, key=lambda x: x['score'], reverse=True)
    early_count = sum(1 for s in ranked if s['is_early'])

    # 分类统计
    type_dist: Dict[str, int] = {}
    for s in ranked:
        type_dist[s['signal_type']] = type_dist.get(s['signal_type'], 0) + 1

    # 时间线（按日期升序，供可视化）
    timeline = [
        {
            'signalDate': t['signal_date'],
            'signalType': t['signal_type'],
            'leadDays': t['lead_days'],
            'score': t['score'],
            'isEarly': bool(t['is_early']),
        }
        for t in sorted(raw_signals, key=lambda x: x['signal_date'])
    ]

    # 落库（幂等：同标的先清后插）
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        s.query(BacktraceAgentSignal).filter_by(stock_code=stock_code).delete()
        for sig in ranked:
            rec = BacktraceAgentSignal(
                stock_code=stock_code,
                stock_name=stock.get('stock_name'),
                signal_type=sig['signal_type'],
                signal_date=sig['signal_date'],
                lead_days=sig['lead_days'],
                source=sig['source'],
                summary=sig['summary'],
                credibility=sig['credibility'],
                relevance=sig['relevance'],
                score=sig['score'],
                is_early=sig['is_early'],
            )
            s.add(rec)
        s.flush()

    result = {
        'stockCode': stock_code,
        'stockName': stock.get('stock_name'),
        'riseStartDate': rise_start,
        'windowDays': window_days,
        'signalCount': len(ranked),
        'earlyCount': early_count,
        'typeDistribution': type_dist,
        'signals': ranked,
        'timeline': timeline,
        'engine': 'agent-heuristic-dig',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
    }
    return {'code': 0, 'msg': 'ok', 'data': result}


def list_agent_signals(stock_code: str) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceAgentSignal)
            .filter_by(stock_code=stock_code)
            .order_by(BacktraceAgentSignal.score.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}
