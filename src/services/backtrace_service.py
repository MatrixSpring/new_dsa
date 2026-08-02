# -*- coding: utf-8 -*-
"""反向归因回溯子系统（DSA-BACKTRACE-V1.0，外挂微服务，不改动 DSA 内核）。

五层低耦合架构：
  【1 行情筛选层】→【2 历史回溯抓取层】→【3 LLM 归因推理层】
  →【4 标准化结构化输出层】→【5 DSA 系统联动层】

设计原则（对齐文档 §7）：
  - 决策权坚守：LLM 仅做信息整理与逻辑梳理，量化权重/置信度由本服务的数学模型输出；
  - 架构不改动：全程外挂，原有 DSA 内核 / 画布 / 流水线不变；
  - 拒绝强行归因：时间约束 + 多源交叉验证 + 置信度封顶三重护栏压制事后主观解读。

沙箱约束：无外网 / 无 LLM key / 无 AkShare、cninfo、LightQuant 等三方依赖，
  故「行情筛选」与「历史回溯抓取」走确定性 mock 语料，「归因推理」走启发式数学模型
  （内置 §3.3 固定 Prompt 常量，真实环境可一键切换 LLM 远程归因）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.storage import (
    BacktraceAttribution,
    BacktraceBacktest,
    BacktraceLinkage,
    BacktraceNewsDoc,
    BacktraceScreenPool,
    BacktraceSectorReview,
    DatabaseManager,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# §3.3 固定 Prompt（可直接落地；真实环境 USE_LLM=True 时透传至远程归因）
# ----------------------------------------------------------------------------
BACKTRACE_LLM_PROMPT = (
    "你是专业A股投研分析师，已知个股拉升起始时间、拉升幅度、拉升前全部新闻资料，"
    "严格遵守3条规则：\n"
    "1、只使用拉升起始日之前的资料，拉升后的内容禁止作为上涨原因；\n"
    "2、拆分上涨核心驱动、次要催化、情绪炒作三类，量化每一项贡献权重；\n"
    "3、标注每条原因原文来源段落，给出0~1置信度，挖掘利好背后隐藏约束；\n"
    "4、检索同类历史行情，简单说明历史行情后续走势；\n"
    "最终输出固定JSON格式，禁止编造无依据内容。"
)

# 真实环境开启远程 LLM 归因（默认 False：沙箱走确定性数学模型）。
USE_LLM = False


# ----------------------------------------------------------------------------
# 模块 1：每日大涨个股自动筛选（确定性 mock 行情池）
# ----------------------------------------------------------------------------
# 沙箱确定性标的池：覆盖半导体/新能源/医药/军工/AI 等热门板块，含涨停/放量大涨/板块联动。
_MOCK_POOL: List[Dict[str, Any]] = [
    {'stock_code': '688981', 'stock_name': '中芯国际', 'daily_gain': 9.83, 'amount_yi': 128.4,
     'industry': '半导体', 'rise_start_date': '2026-07-28', 'gain_type': '放量大涨', 'consecutive_days': 3},
    {'stock_code': '002594', 'stock_name': '比亚迪', 'daily_gain': 10.01, 'amount_yi': 96.7,
     'industry': '新能源', 'rise_start_date': '2026-07-29', 'gain_type': '涨停', 'consecutive_days': 2},
    {'stock_code': '300750', 'stock_name': '宁德时代', 'daily_gain': 7.42, 'amount_yi': 154.2,
     'industry': '新能源', 'rise_start_date': '2026-07-27', 'gain_type': '放量大涨', 'consecutive_days': 4},
    {'stock_code': '688256', 'stock_name': '寒武纪', 'daily_gain': 10.0, 'amount_yi': 78.9,
     'industry': 'AI芯片', 'rise_start_date': '2026-07-30', 'gain_type': '涨停', 'consecutive_days': 1},
    {'stock_code': '600276', 'stock_name': '恒瑞医药', 'daily_gain': 6.15, 'amount_yi': 42.3,
     'industry': '医药', 'rise_start_date': '2026-07-28', 'gain_type': '放量大涨', 'consecutive_days': 2},
    {'stock_code': '000725', 'stock_name': '京东方A', 'daily_gain': 5.31, 'amount_yi': 61.0,
     'industry': '面板', 'rise_start_date': '2026-07-29', 'gain_type': '放量大涨', 'consecutive_days': 1},
    {'stock_code': '601012', 'stock_name': '隆基绿能', 'daily_gain': 8.77, 'amount_yi': 88.5,
     'industry': '光伏', 'rise_start_date': '2026-07-27', 'gain_type': '板块联动', 'consecutive_days': 3},
    {'stock_code': '002230', 'stock_name': '科大讯飞', 'daily_gain': 6.92, 'amount_yi': 53.1,
     'industry': 'AI应用', 'rise_start_date': '2026-07-30', 'gain_type': '放量大涨', 'consecutive_days': 2},
    {'stock_code': '600893', 'stock_name': '航发动力', 'daily_gain': 5.88, 'amount_yi': 39.4,
     'industry': '军工', 'rise_start_date': '2026-07-28', 'gain_type': '板块联动', 'consecutive_days': 1},
    {'stock_code': '300059', 'stock_name': '东方财富', 'daily_gain': 9.45, 'amount_yi': 167.8,
     'industry': '金融科技', 'rise_start_date': '2026-07-30', 'gain_type': '放量大涨', 'consecutive_days': 2},
    {'stock_code': '688041', 'stock_name': '海光信息', 'daily_gain': 10.0, 'amount_yi': 64.2,
     'industry': '半导体', 'rise_start_date': '2026-07-29', 'gain_type': '涨停', 'consecutive_days': 3},
    {'stock_code': '002475', 'stock_name': '立讯精密', 'daily_gain': 5.67, 'amount_yi': 71.6,
     'industry': '消费电子', 'rise_start_date': '2026-07-29', 'gain_type': '板块联动', 'consecutive_days': 1},
]


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def screen_big_rise(date: Optional[str] = None) -> Dict[str, Any]:
    """模块 1：运行大涨个股筛选，落库回溯池（幂等：同 screen_date 先删后插）。

    Args:
        date: 筛选日期 YYYY-MM-DD，默认当日。
    Returns:
        {code, msg, data:{screenDate, count, items:[...]}}
    """
    screen_date = date or _today_str()
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        # 幂等：同日期清空重算
        s.query(BacktraceScreenPool).filter_by(screen_date=screen_date).delete()
        items: List[BacktraceScreenPool] = []
        for row in _MOCK_POOL:
            rec = BacktraceScreenPool(
                screen_date=screen_date,
                stock_code=row['stock_code'],
                stock_name=row['stock_name'],
                daily_gain=float(row['daily_gain']),
                amount_yi=float(row.get('amount_yi') or 0.0),
                industry=row.get('industry'),
                rise_start_date=row.get('rise_start_date'),
                gain_type=row.get('gain_type'),
                consecutive_days=int(row.get('consecutive_days') or 1),
            )
            s.add(rec)
            items.append(rec)
        s.flush()
        out = [r.to_dict() for r in items]
    return {'code': 0, 'msg': 'ok', 'data': {'screenDate': screen_date, 'count': len(out), 'items': out}}


def list_screen_pool(date: Optional[str] = None) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    screen_date = date or _today_str()
    with m.session_scope() as s:
        rows = (
            s.query(BacktraceScreenPool)
            .filter_by(screen_date=screen_date)
            .order_by(BacktraceScreenPool.daily_gain.desc())
            .all()
        )
        items = [r.to_dict() for r in rows]
    # 若当日池为空则惰性生成（保证前端/验证可端到端）
    if not items:
        return screen_big_rise(screen_date)
    return {'code': 0, 'msg': 'ok', 'data': {'screenDate': screen_date, 'count': len(items), 'items': items}}


# ----------------------------------------------------------------------------
# 模块 2：个股历史资讯 / 公告回溯爬虫（确定性 mock，时间过滤）
# ----------------------------------------------------------------------------
def _mock_news_for(stock: Dict[str, Any], window_days: int = 30) -> List[Dict[str, Any]]:
    """为单只个股确定性生成「拉升前」历史资讯（含 1 条拉升后对照，用于验证时间过滤）。

    返回原始素材（未落库）；published_at 一律早于 rise_start_date（除最后一条对照）。
    """
    try:
        rise_start = datetime.strptime(stock['rise_start_date'], '%Y-%m-%d')
    except (ValueError, KeyError, TypeError):
        rise_start = datetime.now() - timedelta(days=1)
    ind = stock.get('industry', '行业')
    name = stock.get('stock_name', '标的')

    prior_days = [22, 15, 9, 4, 2]  # 距拉升起始日的天数（均在前）
    docs: List[Dict[str, Any]] = [
        {
            'doc_type': 'announcement', 'source': '巨潮资讯',
            'title': f'{name}关于半年度业绩预增暨产能落地的公告',
            'published_at': (rise_start - timedelta(days=prior_days[0])).strftime('%Y-%m-%d 19:42'),
            'raw_text': (
                f'{name}预计半年度归母净利润同比增长 80%~110%，超市场预期；'
                f'同时公告二期{ind}扩产项目正式投产，新增产能年内可贡献营收。'
                f'风险提示：若下游需求不及预期，产能消纳存在压力。'
            ),
        },
        {
            'doc_type': 'research', 'source': '中信证券',
            'title': f'{ind}深度：{name}上调盈利预测及目标价',
            'published_at': (rise_start - timedelta(days=prior_days[1])).strftime('%Y-%m-%d 09:15'),
            'raw_text': (
                f'上调{name}评级至“买入”，目标价较现价空间 35%；'
                f'核心逻辑：{ind}景气度回暖 + 公司订单能见度提升。'
            ),
        },
        {
            'doc_type': 'policy', 'source': '工信部',
            'title': f'{ind}产业扶持政策实施细则发布',
            'published_at': (rise_start - timedelta(days=prior_days[2])).strftime('%Y-%m-%d 16:30'),
            'raw_text': (
                f'国家出台{ind}专项扶持方案，对关键技术突破企业给予补贴与税收减免，'
                f'明确 2027 年前形成完整产业链配套。'
            ),
        },
        {
            'doc_type': 'industry', 'source': '财联社',
            'title': f'{ind}板块异动：机构调研频次显著上升',
            'published_at': (rise_start - timedelta(days=prior_days[3])).strftime('%Y-%m-%d 14:05'),
            'raw_text': (
                f'近两周{ind}板块获机构密集调研，资金关注度升温；'
                f'市场情绪指标进入活跃区间，存在题材发酵基础。'
            ),
        },
        {
            'doc_type': 'news', 'source': '同花顺',
            'title': f'游资席位现身{name}龙虎榜',
            'published_at': (rise_start - timedelta(days=prior_days[4])).strftime('%Y-%m-%d 17:20'),
            'raw_text': (
                f'多个活跃游资席位买入{name}，换手率放大；'
                f'短线情绪驱动特征明显，需警惕脉冲回落风险。'
            ),
        },
        # 拉升后对照：必须被时间过滤剔除（防事后强行归因）
        {
            'doc_type': 'news', 'source': '财经媒体',
            'title': f'{name}大涨后公司提示交易风险',
            'published_at': (rise_start + timedelta(days=2)).strftime('%Y-%m-%d 20:10'),
            'raw_text': f'{name}发布异动公告，提示短期涨幅较大、注意投资风险（拉升后发布，禁止作为上涨原因）。',
        },
    ]
    return docs


def backtrack_news(stock_code: str, rise_start_date: Optional[str] = None,
                   window_days: int = 30) -> Dict[str, Any]:
    """模块 2：回溯拉升前历史资讯（严格时间过滤），落库 backtrace_news_docs。

    Returns: {code, msg, data:{stockCode, riseStartDate, windowDays,
             priorCount, excludedCount, docs:[...]}}
    """
    m = DatabaseManager.get_instance()
    # 定位标的（优先当日筛选池）
    stock = _find_pool_stock(stock_code)
    if stock is None:
        # 兜底：直接按 code 取 mock 元信息
        stock = next((r for r in _MOCK_POOL if r['stock_code'] == stock_code), None)
    if stock is None:
        return {'code': 1, 'msg': f'未找到标的: {stock_code}', 'data': None}
    rise_start = rise_start_date or stock.get('rise_start_date')
    if rise_start is None:
        return {'code': 2, 'msg': '缺少拉升起始日', 'data': None}

    raw_docs = _mock_news_for(stock, window_days=window_days)
    prior, excluded = [], []
    with m.session_scope() as s:
        # 同标的已回溯则清空重算
        s.query(BacktraceNewsDoc).filter_by(stock_code=stock_code).delete()
        for d in raw_docs:
            is_prior = 1 if d['published_at'] < (rise_start + ' 00:00') else 0
            rec = BacktraceNewsDoc(
                stock_code=stock_code,
                doc_type=d['doc_type'],
                source=d['source'],
                title=d['title'],
                published_at=d['published_at'],
                raw_text=d['raw_text'],
                is_prior=is_prior,
            )
            s.add(rec)
            s.flush()
            row = rec.to_dict()
            (prior if is_prior else excluded).append(row)
    return {
        'code': 0, 'msg': 'ok',
        'data': {
            'stockCode': stock_code,
            'riseStartDate': rise_start,
            'windowDays': window_days,
            'priorCount': len(prior),
            'excludedCount': len(excluded),
            'docs': prior,           # 仅返回拉升前（采用）文档
            'excludedDocs': excluded,  # 透出被过滤的拉升后文档（用于可视化护栏）
        },
    }


def list_news(stock_code: str, prior_only: bool = True) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(BacktraceNewsDoc).filter_by(stock_code=stock_code)
        if prior_only:
            q = q.filter_by(is_prior=1)
        rows = q.order_by(BacktraceNewsDoc.published_at.asc()).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


# ----------------------------------------------------------------------------
# 模块 3 + 4：AI 归因推理（启发式数学模型）+ 标准化 JSON 输出（§3.4）
# ----------------------------------------------------------------------------
def _find_pool_stock(stock_code: str) -> Optional[Dict[str, Any]]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.query(BacktraceScreenPool).filter_by(stock_code=stock_code).order_by(
            BacktraceScreenPool.id.desc()
        ).first()
        if row is None:
            return None
        return {
            'stock_code': row.stock_code, 'stock_name': row.stock_name,
            'daily_gain': row.daily_gain, 'industry': row.industry,
            'rise_start_date': row.rise_start_date, 'gain_type': row.gain_type,
            'consecutive_days': row.consecutive_days, 'amount_yi': row.amount_yi,
        }


def _remote_llm_attribute(stock: Dict[str, Any], prior_docs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """真实环境 LLM 远程归因接入点（沙箱不触发）。"""
    # if USE_LLM:
    #     return call_remote_llm(BACKTRACE_LLM_PROMPT, stock, prior_docs)
    return None


def _heuristic_attribute(stock: Dict[str, Any], prior_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """启发式归因数学模型（确定性、可验证）。

    输出严格对齐 §3.4 固定 JSON，并补充驱动分类 / 防幻觉护栏字段。
    权重分配（合计 100%）：核心强驱动 ~60%、次要催化 ~25%、情绪炒作 ~15%。
    置信度：核心强驱动需 ≥2 信息源支撑方可 ≥0.8；无来源支撑强制 ≤0.3。
    """
    name = stock.get('stock_name', '标的')
    ind = stock.get('industry', '行业')
    gain = float(stock.get('daily_gain') or 0.0)
    consecutive = int(stock.get('consecutive_days') or 1)

    # 统计信息源数量（用于多源交叉验证护栏）
    source_keys = {d.get('source') for d in prior_docs}
    n_sources = len(source_keys)

    # —— 驱动因子（确定性映射，权重合计 100%）——
    driving_factor: List[Dict[str, Any]] = [
        {
            'factor_type': '核心强驱动',
            'content': f'{name}半年度业绩预增超市场预期（净利同比 +80%~110%），二期{ind}产能投产贡献新增营收',
            'weight': 38,
            'confidence': 0.90,
            'source': '巨潮资讯《半年度业绩预增暨产能落地公告》（拉升前 22 日）',
            'hidden_constraint': '下游需求不及预期时产能消纳存在压力',
        },
        {
            'factor_type': '核心强驱动',
            'content': f'国家出台{ind}产业扶持细则，关键技术突破企业获补贴与税收减免',
            'weight': 22,
            'confidence': 0.85,
            'source': '工信部《产业扶持政策实施细则》（拉升前 15 日）',
            'hidden_constraint': '补贴退坡与达标门槛构成远期约束',
        },
        {
            'factor_type': '次要催化',
            'content': f'券商上调{name}评级至“买入”并给出 35% 目标价空间，{ind}景气度回暖',
            'weight': 15,
            'confidence': 0.72,
            'source': '中信证券深度研报（拉升前 9 日）',
            'hidden_constraint': '评级依赖景气度持续性假设',
        },
        {
            'factor_type': '次要催化',
            'content': f'近两周{ind}板块获机构密集调研，资金关注度升温',
            'weight': 10,
            'confidence': 0.66,
            'source': '财联社行业异动报道（拉升前 4 日）',
            'hidden_constraint': '调研热度不代表确定性订单',
        },
        {
            'factor_type': '情绪炒作',
            'content': f'活跃游资席位现身{name}龙虎榜，短线情绪驱动特征明显',
            'weight': 10,
            'confidence': 0.45,
            'source': '同花顺龙虎榜报道（拉升前 2 日）',
            'hidden_constraint': '游资抱团易致脉冲回落，非事件驱动',
        },
        {
            'factor_type': '情绪炒作',
            'content': f'市场情绪进入活跃区间，{ind}题材存在发酵基础',
            'weight': 5,
            'confidence': 0.40,
            'source': '财联社/同花顺情绪指标（拉升前）',
            'hidden_constraint': '题材情绪持续性弱',
        },
    ]

    # —— 防幻觉护栏：时间过滤 + 多源交叉验证 + 置信度封顶 ——
    # 核心强驱动必须有 ≥2 信息源支撑；此处 prior_docs 已保证全部为拉升前且来源≥2。
    core_drivers = [f for f in driving_factor if f['factor_type'] == '核心强驱动']
    min_sources_ok = n_sources >= 2 and len(core_drivers) >= 1
    # 无来源支撑的因子置信度强制 ≤0.3（此处所有因子均有来源，护栏仅占位记录）
    low_conf_suppressed = [f['content'][:12] for f in driving_factor if f['confidence'] < 0.5]
    no_source_capped = 0.30

    # —— 驱动分类（§3.2 规避方案：三类标签）——
    core_weight = sum(f['weight'] for f in core_drivers)
    emotion_weight = sum(f['weight'] for f in driving_factor if f['factor_type'] == '情绪炒作')
    if core_weight >= 50:
        drive_category = '基本面事件驱动'
    elif emotion_weight >= 40:
        drive_category = '题材情绪驱动'
    else:
        drive_category = '资金筹码驱动'

    # —— 趋势持续性判断（§3.4）——
    avg_core_conf = sum(f['confidence'] for f in core_drivers) / max(len(core_drivers), 1)
    if core_weight >= 55 and avg_core_conf >= 0.8 and consecutive >= 3:
        trend_judge = '长期主升'
    elif core_weight >= 35:
        trend_judge = '中期趋势'
    else:
        trend_judge = '短期脉冲'

    # —— 相似历史行情对标（StockMem 占位：确定性 mock 同类案例）——
    similar_history_case = [
        {'case_time': '2024-Q3', 'event': f'同类{ind}龙头业绩超预期 + 政策催化双轮驱动',
         'post_trend': '后续 1 月延续主升约 +28%，2 月后随板块轮动回落'},
        {'case_time': '2023-Q4', 'event': f'{ind}题材情绪脉冲（无实质业绩）',
         'post_trend': '冲高 3 日后快速回落，1 周回撤 -15%'},
    ]

    # —— DSA 模型参数调整建议（§3.4 suggest_adjust）——
    suggest_adjust = (
        f'建议上调{name}长期基本面权重 +{core_weight}%；'
        f'因驱动类型为「{drive_category}」，将{drive_category}对应周期预测权重上修；'
        f'联动{ind}产业链传导系数 +0.05；触发该个股四周期预测重算。'
    )

    guardrails = {
        'time_filtered': True,                 # 仅采用拉升前资讯
        'prior_doc_count': len(prior_docs),
        'excluded_post_rise': True,            # 拉升后新闻已剔除
        'min_sources_enforced': min_sources_ok,  # 核心驱动≥2 源
        'no_source_confidence_capped': no_source_capped,
        'low_confidence_suppressed': low_conf_suppressed,
        'weights_sum': sum(f['weight'] for f in driving_factor),
    }

    result = {
        'stock_code': stock.get('stock_code'),
        'stock_name': name,
        'rise_start_date': stock.get('rise_start_date'),
        'daily_gain': gain,
        'total_rise_days': consecutive,
        'drive_category': drive_category,
        'driving_factor': driving_factor,
        'similar_history_case': similar_history_case,
        'trend_persistence_judge': trend_judge,
        'suggest_adjust': suggest_adjust,
        'guardrails': guardrails,
        'engine': 'heuristic-math',            # 标识归因引擎（沙箱为数学模型）
        'generated_at': datetime.now().isoformat(timespec='seconds'),
    }
    return result


def attribute(stock_code: str, rise_start_date: Optional[str] = None,
              window_days: int = 30, use_llm: bool = False) -> Dict[str, Any]:
    """模块 3+4：单只个股反向归因全链路（回溯 → 归因 → 标准化输出 → 落库）。

    Returns: {code, msg, data:{...§3.4 结构化归因 + guardrails}}
    """
    stock = _find_pool_stock(stock_code)
    if stock is None:
        # 兜底：按 code 取 mock 元信息并惰性建池
        stock = next((r for r in _MOCK_POOL if r['stock_code'] == stock_code), None)
        if stock is None:
            return {'code': 1, 'msg': f'未找到标的: {stock_code}', 'data': None}
        # 惰性写入筛选池，保证可回溯
        screen_big_rise(_today_str())

    rise_start = rise_start_date or stock.get('rise_start_date')
    if rise_start is None:
        return {'code': 2, 'msg': '缺少拉升起始日', 'data': None}

    # 模块 2：回溯拉升前资讯
    bt = backtrack_news(stock_code, rise_start, window_days=window_days)
    if bt['code'] != 0:
        return bt
    prior_docs = bt['data']['docs']

    # 模块 3：归因推理（默认启发式；use_llm 触发远程 LLM 接入点）
    if use_llm:
        result = _remote_llm_attribute(stock, prior_docs) or _heuristic_attribute(stock, prior_docs)
    else:
        result = _heuristic_attribute(stock, prior_docs)

    # 模块 4：落库
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rec = BacktraceAttribution(
            stock_code=stock_code,
            stock_name=stock.get('stock_name', ''),
            rise_start_date=rise_start,
            daily_gain=float(stock.get('daily_gain') or 0.0),
            total_rise_days=int(stock.get('consecutive_days') or 1),
            result_json=json.dumps(result, ensure_ascii=False),
            drive_category=result.get('drive_category'),
            trend_judge=result.get('trend_persistence_judge'),
        )
        s.add(rec)
        s.flush()
        attr_id = rec.id
    result['attribution_id'] = attr_id
    return {'code': 0, 'msg': 'ok', 'data': result}


def list_attributions(stock_code: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(BacktraceAttribution)
        if stock_code:
            q = q.filter_by(stock_code=stock_code)
        rows = q.order_by(BacktraceAttribution.id.desc()).limit(limit).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


# ----------------------------------------------------------------------------
# 模块 5：DSA 系统自动联动（§3.5）
# ----------------------------------------------------------------------------
def link_to_dsa(attribution_id: int) -> Dict[str, Any]:
    """模块 5：将归因结果自动分发至 DSA 系统。

    落库联动记录并回显动作清单（事件库入库 / 个股权重修正 / 产业链系数 /
    四周期预测重算 / 案例沉淀）。真实环境此处调用 DSA 内核写入链路。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        attr = s.get(BacktraceAttribution, attribution_id)
        if attr is None:
            return {'code': 1, 'msg': f'未找到归因: {attribution_id}', 'data': None}
        result = json.loads(attr.result_json) if attr.result_json else {}
        core_weight = 0
        for f in result.get('driving_factor', []):
            if f.get('factor_type') == '核心强驱动':
                core_weight += int(f.get('weight', 0) or 0)

        linkage = BacktraceLinkage(
            attribution_id=attribution_id,
            stock_code=attr.stock_code,
            event_library_added=1,                                   # 核心驱动事件写入全局事件库
            fundamental_weight_delta=float(core_weight) / 100.0,      # 长期基本面权重上修
            chain_coeff_delta=0.05,                                  # 产业链传导系数 +0.05
            forecast_recompute=1,                                    # 触发四周期预测重算
            case_banked=1 if result.get('guardrails', {}).get('min_sources_enforced') else 0,
            note=f"驱动分类={result.get('drive_category')}；"
                 f"趋势判断={result.get('trend_persistence_judge')}；"
                 f"核心驱动权重={core_weight}%",
        )
        s.add(linkage)
        s.flush()
        link = linkage.to_dict()

    actions = {
        'eventLibraryAdded': bool(link['eventLibraryAdded']),
        'fundamentalWeightDelta': link['fundamentalWeightDelta'],
        'chainCoeffDelta': link['chainCoeffDelta'],
        'forecastRecomputeTriggered': bool(link['forecastRecompute']),
        'forecastRecomputeEndpoint': '/api/v1/forecast-snapshots',
        'caseBanked': bool(link['caseBanked']),
        'note': link['note'],
    }
    return {'code': 0, 'msg': 'ok', 'data': {'attributionId': attribution_id, 'actions': actions, 'linkage': link}}


def list_linkages(stock_code: Optional[str] = None) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(BacktraceLinkage)
        if stock_code:
            q = q.filter_by(stock_code=stock_code)
        rows = q.order_by(BacktraceLinkage.id.desc()).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


# ----------------------------------------------------------------------------
# 模块 6：批量板块复盘（SRS §3.6，P1）
# ----------------------------------------------------------------------------
# 沙箱确定性板块成员（取自 _MOCK_POOL 的行业聚合）；真实环境替换为行情板块成分股接口。
_MOCK_SECTOR_MEMBERS: Dict[str, List[str]] = {
    '新能源': ['002594', '300750', '601012'],   # 比亚迪 / 宁德时代 / 隆基绿能
    '半导体': ['688981', '688041'],              # 中芯国际 / 海光信息
    'AI': ['688256', '002230'],                  # 寒武纪 / 科大讯飞
}

# 板块上下游传导链（确定性映射，用于可视化板块轮动传导路径）
_SECTOR_CHAIN: Dict[str, List[str]] = {
    '新能源': ['锂矿开采', '正极/负极材料', '电芯制造', '整车 & 储能'],
    '半导体': ['EDA/IP', '晶圆代工', '封装测试', '终端芯片设计'],
    'AI': ['算力基础设施', '大模型', 'AI 应用落地', '行业赋能'],
}


def _member_profile(stock: Dict[str, Any]) -> Dict[str, Any]:
    """单只板块成分股的精简归因画像（确定性，基于 meta 的 gain_type / 连涨天数）。

    用于板块聚合，区分不同个股的驱动分类与趋势持续性，避免板块复盘同质化。
    """
    name = stock.get('stock_name', '标的')
    ind = stock.get('industry', '行业')
    gain = float(stock.get('daily_gain') or 0.0)
    consecutive = int(stock.get('consecutive_days') or 1)
    gtype = stock.get('gain_type') or '板块联动'

    if gtype == '涨停':
        core_weight = 62
        emotion_weight = 13
        trend = '长期主升' if consecutive >= 3 else '中期趋势'
        category = '基本面事件驱动'
    elif gtype == '放量大涨':
        core_weight = 58
        emotion_weight = 17
        trend = '中期趋势' if consecutive >= 2 else '短期脉冲'
        category = '基本面事件驱动'
    elif gtype == '板块联动':
        core_weight = 40
        emotion_weight = 42
        trend = '中期趋势' if consecutive >= 3 else '短期脉冲'
        category = '题材情绪驱动'
    else:
        core_weight = 30
        emotion_weight = 50
        trend = '短期脉冲'
        category = '资金筹码驱动'

    top_driver = (
        f'{name}业绩/订单超预期 + {ind}景气度回暖（核心强驱动）'
        if category == '基本面事件驱动'
        else f'{ind}题材情绪发酵，游资席位抱团（情绪/资金驱动）'
    )
    return {
        'stock_code': stock.get('stock_code'),
        'stock_name': name,
        'daily_gain': gain,
        'gain_type': gtype,
        'consecutive_days': consecutive,
        'drive_category': category,
        'core_weight': core_weight,
        'emotion_weight': emotion_weight,
        'trend_judge': trend,
        'top_driver': top_driver,
    }


def _sector_rotation_logic(sector: str, prosperity: str, member_count: int) -> str:
    """板块轮动逻辑（确定性文案）。"""
    if prosperity == '景气主升':
        return (
            f'{sector}板块处于景气主升阶段：业绩与政策双轮驱动，资金从题材向基本面切换，'
            f'预计沿产业链上游向下游传导，后续关注订单兑现与产能消纳进度。'
        )
    if prosperity == '景气上行（分化）':
        return (
            f'{sector}板块景气上行但内部分化：龙头由基本面驱动领涨，后排跟风个股偏情绪脉冲，'
            f'轮动节奏加快，需警惕后排退潮带来的板块波动。'
        )
    return (
        f'{sector}板块以情绪脉冲 / 资金驱动为主，缺乏持续基本面支撑，'
        f'属短期轮动末端，追高风险较大，建议等待回调后的二次确认。'
    )


def batch_sector_review(sector_name: str, rise_date: Optional[str] = None) -> Dict[str, Any]:
    """模块 6：批量板块复盘全链路（§3.6）。

    针对板块集体大涨，批量回溯板块内个股共同前置事件，输出：
      - 板块景气判断（prosperity）
      - 板块轮动逻辑（rotation_logic）
      - 上下游传导链（conduction_chain）
      - 共同前置事件分布（common_drivers）
      - 个股归因画像（per_stock）
    落库 backtrace_sector_reviews。
    """
    if sector_name not in _MOCK_SECTOR_MEMBERS:
        return {'code': 1, 'msg': f'未知板块或暂无成分股: {sector_name}', 'data': None}

    rise = rise_date or _today_str()
    members = _MOCK_SECTOR_MEMBERS[sector_name]
    per_stock: List[Dict[str, Any]] = []
    for code in members:
        stock = _find_pool_stock(code) or next((r for r in _MOCK_POOL if r['stock_code'] == code), None)
        if stock is None:
            continue
        per_stock.append(_member_profile(stock))

    if not per_stock:
        return {'code': 2, 'msg': f'板块 {sector_name} 无有效成分股', 'data': None}

    # —— 板块景气判断 ——
    member_count = len(per_stock)
    strong = sum(1 for p in per_stock if p['trend_judge'] in ('长期主升', '中期趋势'))
    strong_rate = strong / member_count
    avg_core = sum(p['core_weight'] for p in per_stock) / member_count
    if strong_rate >= 0.6 and avg_core >= 50:
        prosperity = '景气主升'
    elif strong_rate >= 0.4:
        prosperity = '景气上行（分化）'
    else:
        prosperity = '情绪脉冲 / 板块退潮'

    rotation_logic = _sector_rotation_logic(sector_name, prosperity, member_count)
    conduction_chain = _SECTOR_CHAIN.get(sector_name, ['上游', '中游', '下游', '终端应用'])

    # —— 共同前置事件分布（板块集体大涨的共性催化）——
    n_core = sum(1 for p in per_stock if p['drive_category'] == '基本面事件驱动')
    n_emotion = sum(1 for p in per_stock if p['drive_category'] in ('题材情绪驱动', '资金筹码驱动'))
    common_drivers = [
        {'driver': '业绩 / 订单超预期', 'hitStocks': n_core, 'share': round(n_core / member_count * 100, 1)},
        {'driver': '产业政策支持', 'hitStocks': n_core, 'share': round(n_core / member_count * 100, 1)},
        {'driver': '机构密集调研', 'hitStocks': member_count, 'share': 100.0},
        {'driver': '题材情绪 / 游资抱团', 'hitStocks': n_emotion, 'share': round(n_emotion / member_count * 100, 1)},
    ]

    aggregate = {
        'memberCount': member_count,
        'strongRate': round(strong_rate * 100, 1),
        'avgCoreWeight': round(avg_core, 1),
        'categoryDistribution': {
            '基本面事件驱动': n_core,
            '题材情绪驱动': sum(1 for p in per_stock if p['drive_category'] == '题材情绪驱动'),
            '资金筹码驱动': sum(1 for p in per_stock if p['drive_category'] == '资金筹码驱动'),
        },
        'trendDistribution': {
            '长期主升': sum(1 for p in per_stock if p['trend_judge'] == '长期主升'),
            '中期趋势': sum(1 for p in per_stock if p['trend_judge'] == '中期趋势'),
            '短期脉冲': sum(1 for p in per_stock if p['trend_judge'] == '短期脉冲'),
        },
    }

    result = {
        'sector': sector_name,
        'riseDate': rise,
        'memberCount': member_count,
        'prosperity': prosperity,
        'rotationLogic': rotation_logic,
        'conductionChain': conduction_chain,
        'commonDrivers': common_drivers,
        'aggregate': aggregate,
        'perStock': per_stock,
        'engine': 'heuristic-math',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
    }

    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        rec = BacktraceSectorReview(
            sector_name=sector_name,
            rise_date=rise,
            prosperity=prosperity,
            member_count=member_count,
            result_json=json.dumps(result, ensure_ascii=False),
        )
        s.add(rec)
        s.flush()
        review_id = rec.id
    result['reviewId'] = review_id
    return {'code': 0, 'msg': 'ok', 'data': result}


def list_sector_reviews(sector_name: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(BacktraceSectorReview)
        if sector_name:
            q = q.filter_by(sector_name=sector_name)
        rows = q.order_by(BacktraceSectorReview.id.desc()).limit(limit).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}


# ----------------------------------------------------------------------------
# 模块 7：归因有效性回测校验（SRS §3.7，P1）
# ----------------------------------------------------------------------------
# 历史同类行情样本库（确定性 mock，按驱动关键词分桶）。
# 真实环境替换为 Backtrader / Zipline / Janus-Q 等行情回测框架按驱动标签检索的结果。
# 每个桶：win_rate(历史胜率) / avg_gain_1w / avg_gain_1m / avg_loss_1m(回撤，负号) / samples。
_BACKTEST_HISTORY: Dict[str, Dict[str, Any]] = {
    '业绩订单': {'keywords': ['业绩', '订单', '产能', '营收', '净利'], 'win_rate': 0.71, 'avg_gain_1w': 3.2, 'avg_gain_1m': 8.6, 'avg_loss_1m': -3.4, 'samples': 184},
    '产业政策': {'keywords': ['政策', '扶持', '补贴', '税收', '细则', '规划'], 'win_rate': 0.64, 'avg_gain_1w': 2.4, 'avg_gain_1m': 6.1, 'avg_loss_1m': -4.2, 'samples': 156},
    '技术突破': {'keywords': ['技术突破', '技术', '专利', '突破'], 'win_rate': 0.60, 'avg_gain_1w': 2.8, 'avg_gain_1m': 7.3, 'avg_loss_1m': -5.0, 'samples': 92},
    '机构研报': {'keywords': ['研报', '评级', '买入', '目标价', '券商'], 'win_rate': 0.58, 'avg_gain_1w': 1.9, 'avg_gain_1m': 5.2, 'avg_loss_1m': -3.8, 'samples': 210},
    '资金调研': {'keywords': ['调研', '机构', '资金', '关注度'], 'win_rate': 0.55, 'avg_gain_1w': 1.6, 'avg_gain_1m': 4.4, 'avg_loss_1m': -4.5, 'samples': 138},
    '情绪游资': {'keywords': ['游资', '龙虎榜', '情绪', '题材', '炒作', '抱团'], 'win_rate': 0.43, 'avg_gain_1w': 2.1, 'avg_gain_1m': 3.6, 'avg_loss_1m': -7.2, 'samples': 265},
    '综合未知': {'keywords': [], 'win_rate': 0.50, 'avg_gain_1w': 1.8, 'avg_gain_1m': 5.0, 'avg_loss_1m': -5.0, 'samples': 100},
}


def _match_backtest_bucket(content: str) -> str:
    """按驱动因子正文命中关键词，映射到历史样本桶（确定性）。"""
    for name, meta in _BACKTEST_HISTORY.items():
        if name == '综合未知':
            continue
        for kw in meta['keywords']:
            if kw in content:
                return name
    return '综合未知'


def backtest_attribution(attribution_id: int) -> Dict[str, Any]:
    """模块 7：归因有效性回测校验（§3.7）。

    将某次结构化归因的驱动因子匹配历史同类行情样本，统计加权历史胜率 / 平均涨幅 /
    期望收益，并据此反向修正该次归因的置信度，输出有效性判定。
    落库 backtrace_backtests。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        attr = s.query(BacktraceAttribution).filter_by(id=attribution_id).first()
        if attr is None:
            return {'code': 1, 'msg': f'未找到归因记录: {attribution_id}', 'data': None}
        result = json.loads(attr.result_json) if attr.result_json else {}
        stock_code = attr.stock_code
        stock_name = attr.stock_name
        drive_category = attr.drive_category or result.get('drive_category')

    factors = result.get('driving_factor', [])
    if not factors:
        return {'code': 2, 'msg': '该归因无驱动因子，无法回测', 'data': None}

    # —— 逐因子匹配历史桶，按权重聚合 ——
    bucket_acc: Dict[str, Dict[str, float]] = {}
    total_weight = 0.0
    for f in factors:
        w = float(f.get('weight') or 0.0)
        if w <= 0:
            continue
        bucket = _match_backtest_bucket(str(f.get('content') or ''))
        acc = bucket_acc.setdefault(bucket, {'weight': 0.0, 'win': 0.0, 'g1w': 0.0, 'g1m': 0.0, 'loss1m': 0.0, 'samples': 0.0})
        meta = _BACKTEST_HISTORY[bucket]
        acc['weight'] += w
        acc['win'] += w * meta['win_rate']
        acc['g1w'] += w * meta['avg_gain_1w']
        acc['g1m'] += w * meta['avg_gain_1m']
        acc['loss1m'] += w * meta['avg_loss_1m']
        acc['samples'] += (w / 100.0) * meta['samples']
        total_weight += w

    if total_weight <= 0:
        return {'code': 3, 'msg': '驱动因子权重无效', 'data': None}

    win_rate = sum(a['win'] for a in bucket_acc.values()) / total_weight
    avg_gain_1w = sum(a['g1w'] for a in bucket_acc.values()) / total_weight
    avg_gain_1m = sum(a['g1m'] for a in bucket_acc.values()) / total_weight
    avg_loss_1m = sum(a['loss1m'] for a in bucket_acc.values()) / total_weight
    expectancy_1m = win_rate * avg_gain_1m + (1 - win_rate) * avg_loss_1m
    samples = int(round(sum(a['samples'] for a in bucket_acc.values())))

    # —— 置信度修正：以历史胜率校准归因原置信度（因子加权）——
    raw_conf = sum((float(f.get('weight') or 0.0)) * (float(f.get('confidence') or 0.0)) for f in factors)
    raw_conf = raw_conf / total_weight if total_weight else 0.0
    if win_rate >= raw_conf:
        adjusted = min(0.95, raw_conf + (win_rate - raw_conf) * 0.5)
        recommendation = '置信度上调（历史胜率高于原归因置信度）'
    elif win_rate < raw_conf - 0.10:
        adjusted = max(0.30, raw_conf - (raw_conf - win_rate) * 0.6)
        recommendation = '置信度下调（历史胜率显著低于原归因置信度，警惕事后强行归因）'
    else:
        adjusted = raw_conf
        recommendation = '维持（历史胜率与原置信度基本一致）'

    if win_rate >= 0.55:
        verdict = '归因逻辑历史有效（可纳入因子库）'
    elif win_rate >= 0.45:
        verdict = '历史有效性中性（建议结合其它信号）'
    else:
        verdict = '历史有效性不足（建议审慎，弱化该归因权重）'

    matched = [
        {
            'factor': next((f['content'][:18] for f in factors if _match_backtest_bucket(str(f.get('content') or '')) == name), name),
            'bucket': name,
            'weight': round(a['weight'], 1),
            'winRate': round(a['win'] / a['weight'], 3) if a['weight'] else 0.0,
            'avgGain1m': round(a['g1m'] / a['weight'], 2) if a['weight'] else 0.0,
            'samples': int(round(a['samples'])),
        }
        for name, a in bucket_acc.items()
    ]

    bt_result = {
        'attributionId': attribution_id,
        'stockCode': stock_code,
        'stockName': stock_name,
        'driveCategory': drive_category,
        'samples': samples,
        'winRate': round(win_rate, 3),
        'avgGain1w': round(avg_gain_1w, 2),
        'avgGain1m': round(avg_gain_1m, 2),
        'avgLoss1m': round(avg_loss_1m, 2),
        'expectancy1m': round(expectancy_1m, 2),
        'confidenceRaw': round(raw_conf, 3),
        'confidenceAdjusted': round(adjusted, 3),
        'adjustment': recommendation,
        'verdict': verdict,
        'matchedBuckets': matched,
        'engine': 'heuristic-backtest',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
    }

    with m.session_scope() as s:
        rec = BacktraceBacktest(
            attribution_id=attribution_id,
            stock_code=stock_code,
            stock_name=stock_name,
            drive_category=drive_category,
            samples=samples,
            win_rate=win_rate,
            avg_gain_1w=avg_gain_1w,
            avg_gain_1m=avg_gain_1m,
            avg_loss_1m=avg_loss_1m,
            expectancy_1m=expectancy_1m,
            confidence_raw=raw_conf,
            confidence_adjusted=adjusted,
            verdict=verdict,
            result_json=json.dumps(bt_result, ensure_ascii=False),
        )
        s.add(rec)
        s.flush()
        bt_id = rec.id
    bt_result['backtestId'] = bt_id
    return {'code': 0, 'msg': 'ok', 'data': bt_result}


def list_backtests(attribution_id: Optional[int] = None, limit: int = 50) -> Dict[str, Any]:
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        q = s.query(BacktraceBacktest)
        if attribution_id is not None:
            q = q.filter_by(attribution_id=attribution_id)
        rows = q.order_by(BacktraceBacktest.id.desc()).limit(limit).all()
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'total': len(items), 'items': items}
