# -*- coding: utf-8 -*-
"""反向归因回溯子系统端点（DSA-BACKTRACE-V1.0，外挂，不改动 DSA 内核）。

端点：
- POST /api/v1/backtrace/screen              运行大涨个股筛选（落库回溯池）
- GET  /api/v1/backtrace/screen-pool         查询筛选池
- POST /api/v1/backtrace/backtrack           回溯单只个股拉升前历史资讯
- GET  /api/v1/backtrace/news                查询回溯资讯
- POST /api/v1/backtrace/attribute           单只个股反向归因全链路（回溯→归因→输出）
- GET  /api/v1/backtrace/attributions        查询归因结果
- POST /api/v1/backtrace/link                归因结果联动 DSA 系统
- GET  /api/v1/backtrace/linkages            查询联动记录
- POST /api/v1/backtrace/backtest            归因有效性回测校验（§3.7）
- GET  /api/v1/backtrace/backtests           查询归因回测校验记录
- POST /api/v1/backtrace/agent-dig           Agent 自主深挖小众突发事件（增强模块）
- GET  /api/v1/backtrace/agent-signals       查询 Agent 深挖信号
- POST /api/v1/backtrace/factor-mine         高频上涨因子自动沉淀（构建因子库）
- GET  /api/v1/backtrace/factor-library      查询沉淀因子库
- GET  /api/v1/backtrace/factor-library/stats 因子库累积统计（预设基线 vs 生产真实归因累积，#24）
- POST /api/v1/backtrace/factor-predict      正向预判：早期信号 → 上涨概率
- POST /api/v1/backtrace/closed-loop          一键闭环：深挖 → 预判 → 内核传导（收尾闭环）
- POST /api/v1/backtrace/closed-loop/scan     自动化闭环预警扫描：批量跑闭环并分级预警（#20）
- GET  /api/v1/backtrace/closed-loop/alerts   查询最近一次扫描批次的预警结果（#20）
- POST /api/v1/backtrace/closed-loop/scan/run     调度触发：手动/定时/事件跑闭环预警并落批次聚合（#21）
- GET  /api/v1/backtrace/closed-loop/scan/history 查询扫描批次历史（#21）
- GET  /api/v1/backtrace/closed-loop/scan/schedule 读取调度配置（cron）（#21）
- PUT  /api/v1/backtrace/closed-loop/scan/schedule 更新调度配置（cron/enabled）（#21）
- GET  /api/v1/backtrace/closed-loop/disclosure/source  查询当前活跃公开披露源（cninfo/模拟，#25）
- POST /api/v1/backtrace/closed-loop/disclosure/refresh 用活跃披露源重写披露事件池（#25）
- GET  /api/v1/backtrace/closed-loop/disclosures         查询当前披露事件池（#25）
- GET  /api/v1/backtrace/closed-loop/opinion/source     查询当前活跃公开舆情源（头条/模拟，#28）
- POST /api/v1/backtrace/closed-loop/opinion/refresh    用活跃舆情源重写舆情事件池（#28）
- GET  /api/v1/backtrace/closed-loop/opinions           查询当前舆情事件池（#28）
- GET  /api/v1/backtrace/closed-loop/wechat/source     查询当前活跃微信舆情源（公众号/视频号/模拟，#31）
- POST /api/v1/backtrace/closed-loop/wechat/refresh    用活跃微信舆情源重写微信舆情事件池（#31）
- GET  /api/v1/backtrace/closed-loop/wechats           查询当前微信舆情事件池（#31）
- GET  /api/v1/backtrace/closed-loop/flash/source     查询当前活跃短线快讯源（财联社/华尔街见闻/金十/模拟，#34）
- POST /api/v1/backtrace/closed-loop/flash/refresh    用活跃快讯源重写快讯事件池（#34）
- GET  /api/v1/backtrace/closed-loop/flashes           查询当前快讯事件池（#34）
- GET  /api/v1/backtrace/closed-loop/community/source  查询当前活跃深度社区舆情源（雪球/股吧/淘股吧/模拟，#36）
- POST /api/v1/backtrace/closed-loop/community/refresh 用活跃社区源重写社区讨论事件池（#36）
- GET  /api/v1/backtrace/closed-loop/communities        查询当前社区讨论事件池（#36）
- GET  /api/v1/backtrace/closed-loop/overseas/source   查询当前活跃海外权威舆情源（彭博/路透/WSJ/Seeking Alpha/模拟，#37）
- POST /api/v1/backtrace/closed-loop/overseas/refresh  用活跃海外源重写海外权威资讯事件池（#37）
- GET  /api/v1/backtrace/closed-loop/overseas           查询当前海外权威资讯事件池（#37）
- GET  /api/v1/backtrace/closed-loop/kronos/source    查询当前活跃 Kronos 技术面底座（NeoQuasar/模拟，#35）
- POST /api/v1/backtrace/closed-loop/kronos/refresh   用 Kronos 批量技术分析（重写信号表，#35）
- GET  /api/v1/backtrace/closed-loop/kronos/signals   查询当前 Kronos 技术面信号（#35）
- GET  /api/v1/backtrace/closed-loop/kronos/pools     查询三类选股池（短线强势/趋势反转/风险预警，#35）
- GET  /api/v1/backtrace/closed-loop/info-layers       查询六层信息圈层定义（L0~L5 + 源映射 + §4 可信度阈值，#38）
- GET  /api/v1/backtrace/closed-loop/cross-validation  查询多源交叉验证摘要（圈层命中/共识/冲突/谣言，#38）
- GET  /api/v1/backtrace/closed-loop/sentiment-backtest 查询各平台情绪因子历史胜率回测（六路源胜率/IC/可靠性，#39）
- GET  /api/v1/backtrace/closed-loop/inflection-warnings 查询拐点预警摘要（见顶/启动/情绪反转/技术背离分级，#39）
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body

from src.services.agent_signal_service import (
    agent_dig,
    list_agent_signals,
)
from src.services.closed_loop_scheduler_service import (
    get_scan_history,
    get_schedule_config,
    run_scheduled_scan,
    set_schedule_config,
)
from src.services.closed_loop_scan_service import list_scan_alerts, scan_alerts
from src.services.closed_loop_service import run_closed_loop
from src.services.market_data_provider import describe_source, refresh_screen_pool
from src.services.disclosure_provider import (
    describe_disclosure_source,
    list_disclosure_pool,
    refresh_disclosure_pool,
)
from src.services.opinion_provider import (
    describe_opinion_source,
    list_opinion_pool,
    refresh_opinion_pool,
)
from src.services.wechat_provider import (
    describe_wechat_source,
    list_wechat_pool,
    refresh_wechat_pool,
)
from src.services.flash_provider import (
    describe_flash_source,
    list_flash_pool,
    refresh_flash_pool,
)
from src.services.community_provider import (
    describe_community_source,
    list_community_pool,
    refresh_community_pool,
)
from src.services.overseas_provider import (
    describe_overseas_source,
    list_overseas_pool,
    refresh_overseas_pool,
)
from src.services.kronos_service import (
    describe_kronos_source,
    kronos_pools,
    list_kronos,
    refresh_kronos,
)
from src.services.opinion_info_layers import describe_info_layers
from src.services.opinion_cross_validation import summarize_over_pools
from src.services.opinion_backtest import (
    sentiment_backtest_over_pools,
    summarize_inflection_over_pools,
)
from src.storage import DatabaseManager
from src.services.factor_library_service import (
    factor_library_stats,
    list_factor_library,
    mine_factors,
    predict_with_factors,
)
from src.services.backtrace_service import (
    attribute,
    backtest_attribution,
    backtrack_news,
    batch_sector_review,
    link_to_dsa,
    list_attributions,
    list_backtests,
    list_linkages,
    list_news,
    list_screen_pool,
    list_sector_reviews,
    screen_big_rise,
)

router = APIRouter()


@router.post('/screen')
def post_screen(date: Optional[str] = Body(None, embed=True)) -> Dict[str, Any]:
    """模块 1：运行大涨个股筛选，落库回溯池。"""
    return screen_big_rise(date)


@router.get('/screen-pool')
def get_screen_pool(date: Optional[str] = None) -> Dict[str, Any]:
    """查询当日（或指定日期）大涨回溯池。"""
    return list_screen_pool(date)


@router.post('/backtrack')
def post_backtrack(
    stock_code: str = Body(..., embed=True),
    rise_start_date: Optional[str] = Body(None, embed=True),
    window_days: int = Body(30, embed=True),
) -> Dict[str, Any]:
    """模块 2：回溯单只个股拉升前历史资讯（严格时间过滤）。"""
    return backtrack_news(stock_code, rise_start_date, window_days=window_days)


@router.get('/news')
def get_news(stock_code: str, prior_only: bool = True) -> Dict[str, Any]:
    """查询回溯资讯（默认仅拉升前采用文档）。"""
    return list_news(stock_code, prior_only=prior_only)


@router.post('/attribute')
def post_attribute(
    stock_code: str = Body(..., embed=True),
    rise_start_date: Optional[str] = Body(None, embed=True),
    window_days: int = Body(30, embed=True),
    use_llm: bool = Body(False, embed=True),
) -> Dict[str, Any]:
    """模块 3+4：单只个股反向归因全链路（回溯 → 归因 → 标准化输出）。"""
    return attribute(stock_code, rise_start_date, window_days=window_days, use_llm=use_llm)


@router.get('/attributions')
def get_attributions(stock_code: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """查询归因结果（§3.4 结构化）。"""
    return list_attributions(stock_code=stock_code, limit=limit)


@router.post('/link')
def post_link(attribution_id: int = Body(..., embed=True)) -> Dict[str, Any]:
    """模块 5：归因结果联动 DSA 系统（事件库/权重/产业链系数/预测重算/案例沉淀）。"""
    return link_to_dsa(attribution_id)


@router.get('/linkages')
def get_linkages(stock_code: Optional[str] = None) -> Dict[str, Any]:
    """查询 DSA 联动记录。"""
    return list_linkages(stock_code=stock_code)


@router.post('/sector-review')
def post_sector_review(
    sector: str = Body(..., embed=True),
    rise_date: Optional[str] = Body(None, embed=True),
) -> Dict[str, Any]:
    """模块 6：批量板块复盘（§3.6）——批量回溯板块内个股共同前置事件，
    输出板块景气判断 / 轮动逻辑 / 上下游传导链 / 共同催化分布 / 个股归因画像。"""
    return batch_sector_review(sector, rise_date)


@router.get('/sector-reviews')
def get_sector_reviews(sector: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """查询批量板块复盘记录。"""
    return list_sector_reviews(sector_name=sector, limit=limit)


@router.post('/backtest')
def post_backtest(attribution_id: int = Body(..., embed=True)) -> Dict[str, Any]:
    """模块 7：归因有效性回测校验（§3.7）——将某次归因逻辑放入历史同类行情回测，
    统计历史胜率 / 平均涨幅 / 期望收益，并据此反向修正置信度。"""
    return backtest_attribution(attribution_id)


@router.get('/backtests')
def get_backtests(attribution_id: Optional[int] = None, limit: int = 50) -> Dict[str, Any]:
    """查询归因回测校验记录。"""
    return list_backtests(attribution_id=attribution_id, limit=limit)


@router.post('/agent-dig')
def post_agent_dig(
    stock_code: str = Body(..., embed=True),
    rise_start_date: Optional[str] = Body(None, embed=True),
    window_days: int = Body(30, embed=True),
) -> Dict[str, Any]:
    """增强模块：Agent 自主深挖小众突发事件（拉升前隐藏早期信号扫描与综合打分）。"""
    return agent_dig(stock_code, rise_start_date, window_days=window_days)


@router.get('/agent-signals')
def get_agent_signals(stock_code: str) -> Dict[str, Any]:
    """查询某标的的 Agent 深挖信号。"""
    return list_agent_signals(stock_code)


# ----------------------------------------------------------------------------
# 增强模块：高频上涨因子自动沉淀（因子库 + 正向预判）
# ----------------------------------------------------------------------------
@router.post('/factor-mine')
def post_factor_mine(recompute: bool = Body(True, embed=True)) -> Dict[str, Any]:
    """高频上涨因子自动沉淀：聚合预设基线 + DB 已验证归因，构建标准化上涨因子库。"""
    return mine_factors(recompute=recompute)


@router.get('/factor-library')
def get_factor_library(sort_by: str = 'heat') -> Dict[str, Any]:
    """查询沉淀因子库。sort_by: heat(高频优先) | win(胜率优先) | expectancy(期望优先)。"""
    return list_factor_library(sort_by=sort_by)


@router.get('/factor-library/stats')
def get_factor_library_stats() -> Dict[str, Any]:
    """因子库累积统计（#24 数据驱动）：对比预设基线因子与生产真实归因累积体量。"""
    return factor_library_stats()


@router.post('/factor-predict')
def post_factor_predict(
    detected_factors: list = Body(..., embed=True),
    stock_code: Optional[str] = Body(None, embed=True),
) -> Dict[str, Any]:
    """正向预判：输入早期信号（因子名 / 信号类型 / 任意文本），匹配因子库输出上涨概率。"""
    return predict_with_factors(detected_factors, stock_code=stock_code)


@router.post('/closed-loop')
def post_closed_loop(
    stock_code: str = Body(..., embed=True),
    chain_id: Optional[str] = Body(None, embed=True),
) -> Dict[str, Any]:
    """收尾闭环：一键编排 Agent 深挖（#16）→ 因子正向预判（#17）→ 因子内核传导（#18）。

    内核零改动：传导增益经由既有幅度放大通道注入；决策权全部数学编排，不依赖 LLM。
    请求体：{ stock_code, chain_id? }（chain_id 缺省时按标的行业关键词推断产业链）。
    返回 {code, data:{ stockCode, stockName, chainId, shockNode, dig, predict, propagate, engine }}
    """
    if not stock_code or not str(stock_code).strip():
        return {'code': 1, 'msg': 'stock_code 不能为空', 'data': None}
    return run_closed_loop(str(stock_code).strip(), chain_id=chain_id)


# ----------------------------------------------------------------------------
# #20 自动化闭环预警扫描：把一键闭环编排为批量分级预警服务
# ----------------------------------------------------------------------------
@router.post('/closed-loop/scan')
def post_closed_loop_scan(
    watchlist: Optional[list] = Body(None, embed=True),
    limit: Optional[int] = Body(None, embed=True),
) -> Dict[str, Any]:
    """自动化闭环预警扫描：对大涨回溯池（或指定 watchlist）逐只跑闭环，按综合评分分级预警。

    watchlist 为 None 时回退到当日大涨回溯池；为显式空列表时拒绝。
    返回 {code, data:{ scanBatch, totalScanned, engine, generatedAt, alerts[] }}，alerts 按综合评分降序。
    """
    return scan_alerts(watchlist=watchlist, limit=limit)


@router.get('/closed-loop/alerts')
def get_closed_loop_alerts(limit: int = 50) -> Dict[str, Any]:
    """查询最近一次扫描批次的预警结果（按综合评分降序）。"""
    return list_scan_alerts(limit=limit)


@router.get('/closed-loop/scan/source')
def get_closed_loop_scan_source() -> Dict[str, Any]:
    """查询当前活跃数据源（实时 AkShare / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_source()}


@router.post('/closed-loop/scan/refresh-pool')
def post_closed_loop_refresh_pool(limit: int = 200) -> Dict[str, Any]:
    """用活跃数据源重写当日大涨回溯池（真实环境拉取涨幅榜；模拟环境重写确定性池）。"""
    return refresh_screen_pool(limit=limit)


# ----------------------------------------------------------------------------
# #21 闭环预警自动化调度：把 #20 扫描包装为可调度任务（手动/定时/事件）
# ----------------------------------------------------------------------------
@router.post('/closed-loop/scan/run')
def post_closed_loop_scan_run(
    run_type: str = Body('manual', embed=True),
    watchlist: Optional[list] = Body(None, embed=True),
) -> Dict[str, Any]:
    """调度触发入口：手动/定时/事件跑闭环预警扫描，并落「批次聚合」记录。

    run_type: manual(手动，默认) | schedule(定时) | event(事件)；
    watchlist 为 None 时回退到当日大涨回溯池；显式空列表由 scan_alerts 拒绝。
    返回 {code, data:{ batch:ScanBatchSummary, scan:AlertScanResult }}。
    """
    if run_type not in ('manual', 'schedule', 'event'):
        return {'code': 2, 'msg': 'run_type 仅支持 manual/schedule/event', 'data': None}
    return run_scheduled_scan(run_type=run_type, watchlist=watchlist)


@router.get('/closed-loop/scan/history')
def get_closed_loop_scan_history(limit: int = 20) -> Dict[str, Any]:
    """查询扫描批次历史（按时间倒序，含分级计数与 Top 标的）。"""
    return get_scan_history(limit=limit)


@router.get('/closed-loop/scan/schedule')
def get_closed_loop_scan_schedule() -> Dict[str, Any]:
    """读取闭环预警扫描调度配置（cron 表达式与是否启用）。"""
    return get_schedule_config()


@router.put('/closed-loop/scan/schedule')
def put_closed_loop_scan_schedule(
    cron: Optional[str] = Body(None, embed=True),
    enabled: Optional[bool] = Body(None, embed=True),
) -> Dict[str, Any]:
    """更新闭环预警扫描调度配置。

    cron: 5 段标准表达式（分 时 日 月 周），如 '30 15 * * 1-5'；
    enabled: 是否启用定时触发。任一参数为 None 时保留原值。
    """
    return set_schedule_config(cron=cron, enabled=enabled)


# ----------------------------------------------------------------------------
# #25 可插拔公开披露数据源：把「基本面催化信号源」从 mock 升级为 cninfo / 财报 / 研报
# ----------------------------------------------------------------------------
@router.get('/closed-loop/disclosure/source')
def get_closed_loop_disclosure_source() -> Dict[str, Any]:
    """查询当前活跃公开披露源（实时 cninfo / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_disclosure_source()}


@router.post('/closed-loop/disclosure/refresh')
def post_closed_loop_disclosure_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃披露源重写披露事件池（真实环境拉取 cninfo/财报/研报；模拟环境写入确定性模板）。"""
    return refresh_disclosure_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None, days=days
    )


@router.get('/closed-loop/disclosures')
def get_closed_loop_disclosures() -> Dict[str, Any]:
    """查询当前披露事件池（公告 / 财报 / 研报点评，按披露日期倒序）。"""
    return list_disclosure_pool()


# ----------------------------------------------------------------------------
# #28 可插拔公开舆情数据源：把「情绪面信号源」从 mock 升级为头条爬虫 + FinBERT
# ----------------------------------------------------------------------------
@router.get('/closed-loop/opinion/source')
def get_closed_loop_opinion_source() -> Dict[str, Any]:
    """查询当前活跃公开舆情源（实时头条 / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_opinion_source()}


@router.post('/closed-loop/opinion/refresh')
def post_closed_loop_opinion_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃舆情源重写舆情事件池（真实环境拉取头条爬虫；模拟环境写入确定性模板）。"""
    return refresh_opinion_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None, days=days
    )


@router.get('/closed-loop/opinions')
def get_closed_loop_opinions() -> Dict[str, Any]:
    """查询当前舆情事件池（头条 / 雪球 / 股吧情绪事件，按舆情日期倒序）。"""
    return list_opinion_pool()


@router.get('/closed-loop/wechat/source')
def get_closed_loop_wechat_source() -> Dict[str, Any]:
    """查询当前活跃微信舆情源（实时公众号/视频号 / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_wechat_source()}


@router.post('/closed-loop/wechat/refresh')
def post_closed_loop_wechat_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃微信舆情源重写微信舆情事件池（真实环境拉取公众号/视频号；模拟环境写入确定性模板）。"""
    return refresh_wechat_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None, days=days
    )


@router.get('/closed-loop/wechats')
def get_closed_loop_wechats() -> Dict[str, Any]:
    """查询当前微信舆情事件池（公众号 / 视频号 / 付费社群线索，按发布日期倒序）。"""
    return list_wechat_pool()


@router.get('/closed-loop/flash/source')
def get_closed_loop_flash_source() -> Dict[str, Any]:
    """查询当前活跃短线快讯源（实时财联社/华尔街见闻/金十 / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_flash_source()}


@router.post('/closed-loop/flash/refresh')
def post_closed_loop_flash_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃快讯源重写快讯事件池（真实环境拉取财联社/华尔街见闻/金十/垂直媒体；模拟环境写入确定性模板）。"""
    return refresh_flash_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None, days=days
    )


@router.get('/closed-loop/flashes')
def get_closed_loop_flashes() -> Dict[str, Any]:
    """查询当前快讯事件池（财联社/华尔街见闻/金十/财新/e公司，按发布日期倒序）。"""
    return list_flash_pool()


@router.get('/closed-loop/community/source')
def get_closed_loop_community_source() -> Dict[str, Any]:
    """查询当前活跃深度社区舆情源（实时雪球/东财股吧/淘股吧 / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_community_source()}


@router.post('/closed-loop/community/refresh')
def post_closed_loop_community_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃社区源重写社区讨论事件池（真实环境拉取雪球/东财股吧/淘股吧；模拟环境写入确定性模板）。"""
    return refresh_community_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None, days=days
    )


@router.get('/closed-loop/communities')
def get_closed_loop_communities() -> Dict[str, Any]:
    """查询当前社区讨论事件池（雪球/东财股吧/淘股吧，按发布日期倒序）。"""
    return list_community_pool()


@router.get('/closed-loop/overseas/source')
def get_closed_loop_overseas_source() -> Dict[str, Any]:
    """查询当前活跃海外权威舆情源（彭博/路透/WSJ/Seeking Alpha/模拟，#37）。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_overseas_source()}


@router.post('/closed-loop/overseas/refresh')
def post_closed_loop_overseas_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
    days: int = Body(7, embed=True),
) -> Dict[str, Any]:
    """用活跃海外源重写海外权威资讯事件池（#37）。"""
    return refresh_overseas_pool(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None,
        days=days,
    )


@router.get('/closed-loop/overseas')
def get_closed_loop_overseas() -> Dict[str, Any]:
    """查询当前海外权威资讯事件池（彭博/路透/WSJ/Seeking Alpha，按发布日期倒序，#37）。"""
    return list_overseas_pool()


@router.get('/closed-loop/kronos/source')
def get_closed_loop_kronos_source() -> Dict[str, Any]:
    """查询当前活跃 Kronos 技术面底座（实时 NeoQuasar 模型 / 模拟），用于前端标识与真实环境适配检查。"""
    return {'code': 0, 'msg': 'ok', 'data': describe_kronos_source()}


@router.post('/closed-loop/kronos/refresh')
def post_closed_loop_kronos_refresh(
    stock_codes: Optional[list] = Body(None, embed=True),
) -> Dict[str, Any]:
    """用 Kronos 批量技术分析（真实环境 NeoQuasar 模型推理；模拟环境确定性 mock），重写技术面信号表。"""
    return refresh_kronos(
        stock_codes=[str(c) for c in stock_codes] if stock_codes else None
    )


@router.get('/closed-loop/kronos/signals')
def get_closed_loop_kronos_signals() -> Dict[str, Any]:
    """查询当前 Kronos 技术面信号（逐只标的趋势/拐点/三态概率/波动率/量能/Alpha 因子，按 id 倒序）。"""
    return list_kronos()


@router.get('/closed-loop/kronos/pools')
def get_closed_loop_kronos_pools() -> Dict[str, Any]:
    """查询三类选股池（蓝图 §四 能力1）：短线强势池 / 趋势反转池 / 风险预警池。"""
    return kronos_pools()


@router.get('/closed-loop/info-layers')
def get_closed_loop_info_layers() -> Dict[str, Any]:
    """查询六层信息圈层定义（蓝图 §四，#38）：L0~L5 圈层 + 各可插拔源→圈层映射 + §4 可信度阈值。"""
    return describe_info_layers()


@router.get('/closed-loop/cross-validation')
def get_closed_loop_cross_validation() -> Dict[str, Any]:
    """查询多源交叉验证摘要（蓝图 §五.1，#38）：跨全部池标的（不跑 run_closed_loop）计算圈层命中 /
    共识分布 / 多源确认 / 冲突 / 谣言；消费七路源 per-stock 情感 / 可信度 / 谣言标记。"""
    with DatabaseManager().session_scope() as s:
        return summarize_over_pools(s)


@router.get('/closed-loop/sentiment-backtest')
def get_closed_loop_sentiment_backtest() -> Dict[str, Any]:
    """查询各平台情绪因子历史胜率回测（蓝图 P2，#39）：跨全部池标的（不跑 run_closed_loop）
    对六路可插拔舆情源构造确定性历史情绪序列，真实计算方向胜率 / 多头胜率 / 空头胜率 / IC /
    覆盖率 / 可靠性分级；沙箱为模拟回测基线，真实环境可替换为各源历史情绪 + 后验收益滚动回测。"""
    return sentiment_backtest_over_pools()


@router.get('/closed-loop/inflection-warnings')
def get_closed_loop_inflection_warnings() -> Dict[str, Any]:
    """查询拐点预警摘要（蓝图 P2，#39）：跨全部池标的（不跑 run_closed_loop）消费 #38 交叉验证 +
    #39 回测可靠性 + #35 Kronos 技术面，判定见顶 / 启动 / 情绪反转 / 技术背离分级及建议动作。"""
    with DatabaseManager().session_scope() as s:
        return summarize_inflection_over_pools(s)
