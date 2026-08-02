# -*- coding: utf-8 -*-
"""自动化闭环预警扫描（DSA-BACKTRACE-V1.0 #20，外挂，不改动 DSA 内核）。

把 #19 一键闭环编排为批量扫描服务：对大涨回溯池（或显式 watchlist）逐只跑
闭环（Agent 自主深挖 → 因子正向预判 → 因子内核传导），综合「上涨概率 / 内核增益
/ 小众早期信号 / 最强单信号评分」四项数学指标给出 0~1 综合预警评分，按评分分级
（强信号·重点关注 / 中性·持续观察 / 弱信号·低关注），落库后供预警看板查询。

设计原则（对齐 §7 决策权坚守）：
  - 全部数学编排，不依赖 LLM 主观臆断；
  - 沙箱无外网 / 无 LLM key，信号源与因子统计走确定性 mock，接口契约不变；
  - DSA 内核 propagate_shock 零改动，闭环传导增益经由既有幅度放大通道注入。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from src.services.backtrace_service import list_screen_pool
from src.services.closed_loop_service import run_closed_loop
from src.services.market_data_provider import refresh_screen_pool
from src.services.disclosure_provider import refresh_disclosure_pool
from src.services.opinion_provider import refresh_opinion_pool
from src.services.wechat_provider import refresh_wechat_pool
from src.services.flash_provider import refresh_flash_pool
from src.services.community_provider import refresh_community_pool
from src.services.overseas_provider import refresh_overseas_pool
from src.services.vertical_media_provider import refresh_vertical_media_pool
from src.services.kronos_service import analyze_stock
from src.services.opinion_cross_validation import (
    build_source_index,
    cross_validate_alert,
    cross_validate_scan,
)
from src.services.opinion_backtest import (
    run_sentiment_backtest,
    detect_inflection_for_alert,
    summarize_inflection,
)
from src.storage import (
    BacktraceDisclosure,
    BacktraceOpinion,
    BacktraceScanAlert,
    BacktraceScreenPool,
    BacktraceWechatOpinion,
    BacktraceFlashOpinion,
    BacktraceCommunityOpinion,
    BacktraceOverseasOpinion,
    BacktraceVerticalMediaOpinion,
    BacktraceKronosSignal,
    DatabaseManager,
)

logger = logging.getLogger(__name__)

# 综合评分权重（四项归一化后加权，合计 1.0）
_ALERT_WEIGHTS: Dict[str, float] = {
    'prob': 0.40,     # 正向预判上涨概率
    'boost': 0.20,    # 内核传导幅度增益（归一化到 [0,1]）
    'early': 0.20,    # 小众早期信号密度（封顶 3 条）
    'topscore': 0.20, # 最强单条隐藏信号评分（/100）
}
_BOOST_CLAMP = 0.5  # 与 forecast_with_factors 增益钳制上界一致
_EARLY_CLAMP = 3.0  # 早期信号封顶条数

_LEVEL_STRONG = '强信号·重点关注'
_LEVEL_NEUTRAL = '中性·持续观察'
_LEVEL_WEAK = '弱信号·低关注'
_LEVEL_THRESHOLDS = (0.55, 0.35)  # (强, 中性)；低于下界为弱


def _level(composite: float) -> str:
    """综合评分 → 预警级别。"""
    if composite >= _LEVEL_THRESHOLDS[0]:
        return _LEVEL_STRONG
    if composite >= _LEVEL_THRESHOLDS[1]:
        return _LEVEL_NEUTRAL
    return _LEVEL_WEAK


def _composite(dig: Dict[str, Any], pred: Dict[str, Any], prop: Dict[str, Any]) -> float:
    """四项指标归一化加权 → 综合预警评分（钳制 [0,1]）。"""
    prob = float(pred.get('predictedProb') or 0.0)
    boost = float(prop.get('boost') or 0.0)
    early = int(dig.get('earlyCount') or 0)
    scores = [float(s.get('score', 0.0)) for s in (dig.get('signals') or [])]
    top = (max(scores) / 100.0) if scores else 0.0

    boost_n = min(max(boost / _BOOST_CLAMP, 0.0), 1.0) if boost else 0.0
    early_n = min(early / _EARLY_CLAMP, 1.0)

    comp = (
        _ALERT_WEIGHTS['prob'] * prob
        + _ALERT_WEIGHTS['boost'] * boost_n
        + _ALERT_WEIGHTS['early'] * early_n
        + _ALERT_WEIGHTS['topscore'] * top
    )
    return round(min(max(comp, 0.0), 1.0), 4)


def _resolve_watchlist(watchlist: Optional[List[str]]) -> List[str]:
    """watchlist 为 None 时回退到当日大涨回溯池；空列表视为显式空（调用方拒绝）。"""
    if watchlist is None:
        pool = list_screen_pool()
        items = (pool.get('data') or {}).get('items') or []
        return [str(p['stockCode']) for p in items]
    return [str(c).strip() for c in watchlist if str(c).strip()]


def _resolve_disclosure_codes() -> List[str]:
    """#25 真实环境适配：读取（惰性刷新）公开披露事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由 cninfo 引入 fresh 小市值披露标的。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceDisclosure).count()
    if cnt == 0:
        try:
            refresh_disclosure_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('披露池刷新失败（将忽略披露叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceDisclosure).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceDisclosure).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_opinion_codes() -> List[str]:
    """#28 公开舆情子系统：读取（惰性刷新）舆情事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由头条爬虫引入 fresh 情绪催化标的。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceOpinion).count()
    if cnt == 0:
        try:
            refresh_opinion_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('舆情池刷新失败（将忽略舆情叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_wechat_codes() -> List[str]:
    """#31 微信私域舆情子系统：读取（惰性刷新）微信舆情事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由公众号/视频号爬虫引入 fresh 私域催化标的。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceWechatOpinion).count()
    if cnt == 0:
        try:
            refresh_wechat_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('微信舆情池刷新失败（将忽略微信叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceWechatOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceWechatOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_flash_codes() -> List[str]:
    """#34 短线快讯舆情子系统：读取（惰性刷新）快讯事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由财联社/华尔街见闻/金十爬虫
    引入 fresh 短线催化标的（如盘中突发利空砸盘小票）。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceFlashOpinion).count()
    if cnt == 0:
        try:
            refresh_flash_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('快讯池刷新失败（将忽略快讯叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceFlashOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceFlashOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_community_codes() -> List[str]:
    """#36 深度社区舆情子系统：读取（惰性刷新）社区讨论事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由雪球/东财股吧/淘股吧爬虫
    引入 fresh 散户情绪催化标的（如社区热帖刷屏的小票）。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceCommunityOpinion).count()
    if cnt == 0:
        try:
            refresh_community_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('社区池刷新失败（将忽略社区叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceCommunityOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceCommunityOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_overseas_codes() -> List[str]:
    """#37 海外权威舆情子系统：读取（惰性刷新）海外权威资讯事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由彭博/路透/WSJ/Seeking Alpha 抓取
    引入 fresh 海外机构评级/外资流向催化标的（如外资增持的蓝筹）。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceOverseasOpinion).count()
    if cnt == 0:
        try:
            refresh_overseas_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('海外池刷新失败（将忽略海外叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceOverseasOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceOverseasOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _resolve_vertical_media_codes() -> List[str]:
    """#40 垂直专业媒体舆情子系统：读取（惰性刷新）垂直专业媒体报道事件池中的标的代码集合。

    沙箱确定性 mock 仅引用大涨池内标的；真实环境可由财新/证券时报/e公司/上海证券报/第一财经
    等抓取引入 fresh 专业媒体催化标的（如深度调研覆盖的细分龙头）。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        cnt = s.query(BacktraceVerticalMediaOpinion).count()
    if cnt == 0:
        try:
            refresh_vertical_media_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('垂直专业媒体池刷新失败（将忽略垂直媒体叠加）：%s', e)
            return []
        with m.session_scope() as s:
            cnt = s.query(BacktraceVerticalMediaOpinion).count()
    codes: set[str] = set()
    with m.session_scope() as s:
        for r in s.query(BacktraceVerticalMediaOpinion).all():
            if r.stock_code:
                codes.add(str(r.stock_code))
    return sorted(codes)


def _kronos_signal_for(stock_code: str, stock_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """#35 Kronos 技术面算力底座：取该标的已缓存的技术面信号；未命中则惰性实时分析（mock 确定性）。

    Kronos 不做 union 候选池叠加，而是对每只已扫描 alert **富化技术面信号**（趋势 / 拐点 /
    三态概率 / 波动率 / 量能 / 持续性 / Alpha 因子）。DSA 内核决策权不变（蓝图 §七）。
    """
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        row = s.query(BacktraceKronosSignal).filter_by(stock_code=str(stock_code)).first()
        if row:
            return row.to_dict()
    # 缓存未命中（如尚未 refresh_kronos）：实时分析，保证富化在任意环境都不缺失。
    try:
        return analyze_stock(str(stock_code), stock_name)
    except Exception as e:  # noqa: BLE001
        logger.warning('Kronos 实时分析失败（跳过富化）：%s', e)
        return None


def _ensure_screen_pool(codes: List[str], gain_type: str = '披露催化') -> None:
    """把外部源引入但不在大涨池的标的轻量登记进 BacktraceScreenPool，使 agent_dig 可解析。

    stock_name 优先取同源（披露 / 舆情）记录中的名称（缺失时回退为代码），满足 NOT NULL 约束。
    gain_type 区分触发来源：披露催化 / 舆情催化。
    """
    if not codes:
        return
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        existing = {r.stock_code for r in s.query(BacktraceScreenPool).all()}
        disc_names: Dict[str, Optional[str]] = {}
        for r in s.query(BacktraceDisclosure).all():
            disc_names.setdefault(str(r.stock_code), r.stock_name)
        for r in s.query(BacktraceOpinion).all():
            disc_names.setdefault(str(r.stock_code), r.stock_name)
        for r in s.query(BacktraceWechatOpinion).all():
            disc_names.setdefault(str(r.stock_code), r.stock_name)
        for r in s.query(BacktraceFlashOpinion).all():
            disc_names.setdefault(str(r.stock_code), r.stock_name)
        for r in s.query(BacktraceCommunityOpinion).all():
            disc_names.setdefault(str(r.stock_code), r.stock_name)
        today = datetime.now().strftime('%Y-%m-%d')
        for c in codes:
            if c in existing:
                continue
            s.add(BacktraceScreenPool(
                screen_date=today, stock_code=c, stock_name=disc_names.get(c) or c,
                daily_gain=0.0, amount_yi=0.0, industry='—', rise_start_date=today,
                gain_type=gain_type, consecutive_days=1,
            ))
        s.flush()


def _persist(scan_batch: str, alerts: List[Dict[str, Any]]) -> None:
    """把一批扫描结果落库（外挂伴随表）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        for a in alerts:
            row = BacktraceScanAlert(
                scan_batch=scan_batch,
                stock_code=a['stockCode'],
                stock_name=a.get('stockName'),
                chain_id=a.get('chainId'),
                predicted_prob=float(a.get('predictedProb') or 0.0),
                boost=float(a.get('boost') or 0.0),
                signal_count=int(a.get('signalCount') or 0),
                early_count=int(a.get('earlyCount') or 0),
                top_signal_score=float(a.get('topSignalScore') or 0.0),
                composite_score=float(a.get('compositeScore') or 0.0),
                level=a.get('level', _LEVEL_WEAK),
            )
            s.add(row)


def scan_alerts(
    watchlist: Optional[List[str]] = None,
    limit: Optional[int] = None,
    scan_batch: Optional[str] = None,
) -> Dict[str, Any]:
    """自动化闭环预警扫描：批量跑闭环并给出分级预警。

    Args:
      watchlist: 待扫描标的代码列表；为 None 时回退到当日大涨回溯池；为显式空列表时拒绝。
      limit:     返回条数上限（扫描全部，截断返回）。
      scan_batch: 批次标识（默认自动生成）。

    Returns: {code, msg, data:{ scanBatch, totalScanned, engine, generatedAt, alerts[] }}
      alerts[]: { stockCode, stockName, chainId, signalCount, earlyCount, topSignalScore,
                  predictedProb, boost, matchedFactors, compositeScore, level }
    """
    codes = _resolve_watchlist(watchlist)
    if not codes and watchlist is None:
        # 真实环境：回溯池为空时尝试从活跃数据源（AkShare / mock）刷新后重解析
        try:
            refresh_screen_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning('回溯池刷新失败（将回退到已有池）：%s', e)
        codes = _resolve_watchlist(None)
    if not codes:
        return {'code': 4, 'msg': 'watchlist 为空或回溯池无标的，无可扫描对象', 'data': None}

    # #25 真实环境适配：把公开披露事件池标的作为基本面筛选叠加（union）。
    # 沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境可扩展至 fresh 披露小市值标的。
    disclosure_codes: List[str] = []
    if watchlist is None:
        disclosure_codes = _resolve_disclosure_codes()
        extra = [c for c in disclosure_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra)
            codes = codes + extra
    disclosure_set = set(disclosure_codes)

    # #28 公开舆情子系统：把舆情事件池标的作为情绪面筛选叠加（union），与披露源正交。
    # 沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境可扩展至 fresh 舆情标的。
    opinion_codes: List[str] = []
    if watchlist is None:
        opinion_codes = _resolve_opinion_codes()
        extra = [c for c in opinion_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='舆情催化')
            codes = codes + extra
    opinion_set = set(opinion_codes)

    # #31 微信私域舆情子系统：把微信舆情事件池标的作为私域情绪面筛选叠加（union），
    # 与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#23 行情（大涨）正交。微信私域
    # 对题材 / 小票 / 突发利空影响力 > 头条，权重更高（短线 0.20 / 长线 0.08）。
    # 沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境可扩展至 fresh 私域标的。
    wechat_codes: List[str] = []
    if watchlist is None:
        wechat_codes = _resolve_wechat_codes()
        extra = [c for c in wechat_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='微信舆情')
            codes = codes + extra
    wechat_set = set(wechat_codes)

    # #34 短线快讯舆情子系统：把快讯事件池标的作为短线情绪面筛选叠加（union），
    # 与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#23 行情（大涨）正交。
    # 财联社为 A 股短线第一舆情平台，对短线题材、盘中催化影响力极强（短线权重 0.22）。
    # 沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境可扩展至 fresh 快讯标的。
    flash_codes: List[str] = []
    if watchlist is None:
        flash_codes = _resolve_flash_codes()
        extra = [c for c in flash_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='快讯催化')
            codes = codes + extra
    flash_set = set(flash_codes)

    # #36 深度社区舆情子系统：把社区讨论事件池标的作为情绪面筛选叠加（union），
    # 与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    # （盘中催化）、#23 行情（大涨）正交互补。社区平台（雪球/股吧/淘股吧）对散户情绪、短线题材、
    # 追涨杀跌、谣言发酵影响力极强（短线权重 0.13）。沙箱确定性 mock 仅引用大涨池内标的 →
    # 叠加不新增代码；真实环境可扩展至 fresh 社区热帖刷屏标的。
    community_codes: List[str] = []
    if watchlist is None:
        community_codes = _resolve_community_codes()
        extra = [c for c in community_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='社区热议')
            codes = codes + extra
    community_set = set(community_codes)

    # #37 海外权威舆情子系统：把海外权威资讯事件池标的作为情绪面筛选叠加（union），
    # 与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    # （盘中催化）、#36 社区舆情（散户情绪）、#23 行情（大涨）正交互补。海外权威源（彭博/路透/
    # WSJ/Seeking Alpha）对 A 股**外资流向、机构评级、长线基本面预期**影响力极强（外资定价权、
    # 北向资金风向标），主要作用于长线外资维度（权重 0.18，§五.2 保留彭博/路透系）；短线偏慢、
    # 对题材催化弱（短线 0.14）。沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境
    # 可扩展至 fresh 海外机构评级/外资流向催化标的。
    overseas_codes: List[str] = []
    if watchlist is None:
        overseas_codes = _resolve_overseas_codes()
        extra = [c for c in overseas_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='海外权威')
            codes = codes + extra
    overseas_set = set(overseas_codes)

    # #40 垂直专业媒体舆情子系统：把垂直专业媒体报道事件池标的作为情绪面筛选叠加（union），
    # 与 #25 披露（基本面）、#28 头条舆情（公域情绪）、#31 微信舆情（私域情绪）、#34 短线快讯
    # （盘中催化）、#36 社区舆情（散户情绪）、#37 海外权威（外资/机构）、#23 行情（大涨）正交互补。
    # 垂直专业媒体（财新/券商中国/e公司/证券时报/上海证券报/第一财经）对 A 股**官方指定信披
    # 媒体公信力、深度调研、监管追踪、行业权威解读**影响力强（证券时报/e公司/上海证券报为法定
    # 信披媒体），在 #38 六层信息圈层交叉验证中归 L1 权威圈层（权重 0.12~0.15）；短线偏慢、
    # 对题材催化弱。沙箱确定性 mock 仅引用大涨池内标的 → 叠加不新增代码；真实环境
    # 可扩展至 fresh 专业媒体深度调研覆盖的细分龙头。
    vertical_media_codes: List[str] = []
    if watchlist is None:
        vertical_media_codes = _resolve_vertical_media_codes()
        extra = [c for c in vertical_media_codes if c not in set(codes)]
        if extra:
            _ensure_screen_pool(extra, gain_type='垂直媒体')
            codes = codes + extra
    vertical_media_set = set(vertical_media_codes)

    batch = scan_batch or (datetime.now().strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:6])

    alerts: List[Dict[str, Any]] = []
    for code in codes:
        res = run_closed_loop(code)
        if res.get('code') != 0:
            logger.warning('闭环扫描跳过 %s：%s', code, res.get('msg'))
            continue
        d = res['data']
        dig = d.get('dig', {})
        pred = d.get('predict', {})
        prop = d.get('propagate', {})
        comp = _composite(dig, pred, prop)
        scores = [float(s.get('score', 0.0)) for s in (dig.get('signals') or [])]
        alerts.append({
            'stockCode': d.get('stockCode'),
            'stockName': d.get('stockName'),
            'chainId': d.get('chainId'),
            'signalCount': int(dig.get('signalCount') or 0),
            'earlyCount': int(dig.get('earlyCount') or 0),
            'topSignalScore': max(scores) if scores else 0.0,
            'predictedProb': float(pred.get('predictedProb') or 0.0),
            'boost': float(prop.get('boost') or 0.0),
            'matchedFactors': len(pred.get('matched') or []),
            'compositeScore': comp,
            'level': _level(comp),
            'hasDisclosure': code in disclosure_set,
            'hasOpinion': code in opinion_set,
            'hasWechat': code in wechat_set,
            'hasFlash': code in flash_set,
            'hasCommunity': code in community_set,
            'hasOverseas': code in overseas_set,
            'hasVerticalMedia': code in vertical_media_set,
            'kronosInfo': _kronos_signal_for(code, d.get('stockName')),
        })

    # 按综合评分降序（高分优先预警）
    alerts.sort(key=lambda a: a['compositeScore'], reverse=True)
    if limit is not None and limit > 0:
        alerts = alerts[:limit]

    # #38 六层信息圈层 + 多源交叉验证（P1，蓝图 §四 / §五.1）：元分析层，消费七路源
    # per-stock 情感 / 可信度 / 谣言，归入 L0~L5 圈层并计算共识 / 可信度 / 冲突 / 谣言。
    # 不改变内核决策权、不扩张候选池；一次性建索引，逐 alert 纯函数计算（确定性、可验证）。
    _bt = None
    with DatabaseManager.get_instance().session_scope() as _s:
        _idx = build_source_index(_s)
        # #39 舆情回测（P2，蓝图）：确定性模拟六路源历史情绪序列 + 真实计算胜率/IC，
        # 供拐点预警按源可靠性分级（不改变内核决策权、不扩张候选池）。
        _bt = run_sentiment_backtest(list(_idx.keys()))
    for _a in alerts:
        _a['crossValidation'] = cross_validate_alert(_a['stockCode'], _idx)
        # #39 拐点预警：消费 #38 交叉验证 + 回测可靠性 + #35 Kronos 技术面，判定见顶/启动/情绪反转/背离。
        _a['inflectionWarning'] = detect_inflection_for_alert(_a, _bt)
    cv_summary = cross_validate_scan(alerts)
    inflection_summary = summarize_inflection(alerts)

    if alerts:
        _persist(batch, alerts)

    data = {
        'scanBatch': batch,
        'totalScanned': len(alerts),
        'disclosureCandidates': len(disclosure_codes),
        'opinionCandidates': len(opinion_codes),
        'wechatCandidates': len(wechat_codes),
        'flashCandidates': len(flash_codes),
        'communityCandidates': len(community_codes),
        'overseasCandidates': len(overseas_codes),
        'verticalMediaCandidates': len(vertical_media_codes),
        'kronosAnalyzed': len(alerts),   # #35 Kronos 技术面算力底座：对每只 alert 富化 kronosInfo 的标的数
        'crossValidationSummary': cv_summary,  # #38 六层圈层命中 / 共识分布 / 冲突 / 谣言
        'inflectionSummary': inflection_summary,  # #39 拐点预警摘要（见顶/启动/情绪反转/背离分级）
        'engine': 'backtrace-closed-loop-scan',
        'generatedAt': datetime.now().isoformat(timespec='seconds'),
        'alerts': alerts,
    }
    return {'code': 0, 'msg': 'ok', 'data': data}


def list_scan_alerts(limit: int = 50) -> Dict[str, Any]:
    """查询最近一次扫描批次的预警结果（按综合评分降序）。"""
    m = DatabaseManager.get_instance()
    with m.session_scope() as s:
        latest = s.query(func.max(BacktraceScanAlert.scan_batch)).scalar()
        if not latest:
            return {'code': 0, 'msg': 'ok', 'data': {'batch': None, 'total': 0, 'items': []}}
        rows = (
            s.query(BacktraceScanAlert)
            .filter_by(scan_batch=latest)
            .order_by(BacktraceScanAlert.composite_score.desc())
            .limit(limit)
            .all()
        )
        items = [r.to_dict() for r in rows]
    return {'code': 0, 'msg': 'ok', 'data': {'batch': latest, 'total': len(items), 'items': items}}
