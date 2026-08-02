# -*- coding: utf-8 -*-
"""生成反向归因前端 SSR 验证种子（确定性，复用后端全链路）。

输出 apps/dsa-web/scripts/backtrace_seed.json（camelCase），
供给 verify_backtrace_display.tsx 直接作为 seed prop 渲染。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def _snake_to_camel(s: str) -> str:
    parts = s.split('_')
    if len(parts) == 1:
        return s
    return parts[0] + ''.join(p[:1].upper() + p[1:] for p in parts[1:])


def camelize(obj):
    if isinstance(obj, dict):
        return {_snake_to_camel(k): camelize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [camelize(v) for v in obj]
    return obj


def _load(modname: str, path: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


storage = _load('src_storage_seed', os.path.join(ROOT, 'src', 'storage.py'))
bt = _load('src_services_backtrace_seed', os.path.join(ROOT, 'src', 'services', 'backtrace_service.py'))
bt_agent = _load('src_services_agent_seed', os.path.join(ROOT, 'src', 'services', 'agent_signal_service.py'))
bt_factor = _load('src_services_factor_seed', os.path.join(ROOT, 'src', 'services', 'factor_library_service.py'))
fp = _load('src_services_fp_seed', os.path.join(ROOT, 'src', 'services', 'factor_propagation_service.py'))
cl_svc = _load('src_services_cl_seed', os.path.join(ROOT, 'src', 'services', 'closed_loop_service.py'))
scan_svc = _load('src_services_scan_seed', os.path.join(ROOT, 'src', 'services', 'closed_loop_scan_service.py'))
sched_svc = _load('src_services_sched_seed', os.path.join(ROOT, 'src', 'services', 'closed_loop_scheduler_service.py'))
mdp = _load('src_services_mdp_seed', os.path.join(ROOT, 'src', 'services', 'market_data_provider.py'))
disc = _load('src_services_disc_seed', os.path.join(ROOT, 'src', 'services', 'disclosure_provider.py'))
op = _load('src_services_op_seed', os.path.join(ROOT, 'src', 'services', 'opinion_provider.py'))
wx = _load('src_services_wx_seed', os.path.join(ROOT, 'src', 'services', 'wechat_provider.py'))
fl = _load('src_services_fl_seed', os.path.join(ROOT, 'src', 'services', 'flash_provider.py'))
cm = _load('src_services_cm_seed', os.path.join(ROOT, 'src', 'services', 'community_provider.py'))
ov = _load('src_services_ov_seed', os.path.join(ROOT, 'src', 'services', 'overseas_provider.py'))
kr = _load('src_services_kr_seed', os.path.join(ROOT, 'src', 'services', 'kronos_service.py'))
il = _load('src_services_il_seed', os.path.join(ROOT, 'src', 'services', 'opinion_info_layers.py'))
ob = _load('src_services_ob_seed', os.path.join(ROOT, 'src', 'services', 'opinion_backtest.py'))

m = storage.DatabaseManager.get_instance()
with m.session_scope() as s:
    for tbl in (storage.BacktraceLinkage, storage.BacktraceAttribution, storage.BacktraceNewsDoc,
                storage.BacktraceScreenPool, storage.BacktraceSectorReview, storage.BacktraceBacktest,
                storage.BacktraceAgentSignal, storage.BacktraceFactorLibrary, storage.BacktraceScanAlert,
                storage.BacktraceScanBatch, storage.BacktraceScanSchedule, storage.BacktraceDisclosure,
                storage.BacktraceOpinion, storage.BacktraceWechatOpinion,
                storage.BacktraceFlashOpinion, storage.BacktraceCommunityOpinion, storage.BacktraceOverseasOpinion, storage.BacktraceKronosSignal):
        s.query(tbl).delete()

# 1) 筛选池
screen = bt.screen_big_rise()
pool = screen['data']['items']
first = pool[0]
code = first['stockCode']

# 2) 回溯 + 归因（首只标的）
bt.backtrack_news(code, first['riseStartDate'])
attr = bt.attribute(code)['data']
news_rows = bt.list_news(code)['items']

# 3) 联动
link = bt.link_to_dsa(attr['attribution_id'])['data']['actions']

# 4) 批量板块复盘（§3.6）：新能源板块
sector_review = bt.batch_sector_review('新能源')['data']

# 5) 归因回测校验（§3.7）：对首只标的的归因做历史回测
backtest = bt.backtest_attribution(attr['attribution_id'])['data']

# 归因列表（回测 Tab 下拉）
attr_list = bt.list_attributions()['items']

# 6) 增强模块：Agent 自主深挖小众突发事件（对首只标的扫描拉升前隐藏早期信号）
agent_dig = bt_agent.agent_dig(code)['data']

# 7) 增强模块：高频上涨因子自动沉淀（因子库 + 正向预判）
factor_mine = bt_factor.mine_factors(recompute=True)['data']
factor_library = factor_mine['items']
factor_predict = bt_factor.predict_with_factors(
    list(agent_dig['typeDistribution'].keys()), stock_code=code
)['data']

# 8) 闭环增强：因子库 → DSA 内核正向传导桥接（加载锂电池产业链图谱，内核零改动）
_sandbox_path = os.path.join(ROOT, 'src', 'data', 'industry_chain_sandbox_data.json')
with open(_sandbox_path, 'r', encoding='utf-8') as _f:
    _sb = json.load(_f)
_lithium = dict(_sb['INDUSTRY_CHAINS']['lithium'])
_lithium['id'] = 'lithium'
factor_forecast = fp.forecast_with_factors(
    _lithium, {'node': '锂矿', 'magnitude': 0.3, 'kind': 'demand'}, top_n=6, min_confidence=0.6
)['data']

# 9) 收尾闭环：一键闭环（深挖 → 预判 → 内核传导）
closed_loop = cl_svc.run_closed_loop(code)['data']

# 10) #20 自动化闭环预警扫描：对回溯池批量跑闭环，输出分级预警
alert_scan = scan_svc.scan_alerts()['data']

# 11) #21 闭环预警自动化调度：调度触发落批次 + 读取调度配置 + 历史
scan_run = sched_svc.run_scheduled_scan(run_type='manual')['data']
scan_schedule = sched_svc.get_schedule_config()['data']
scan_history = sched_svc.get_scan_history(limit=20)['data']['items']

# 12) #23 可插拔数据源：探测当前活跃数据源（沙箱默认 mock；真实环境 AkShare 或回退）
data_source = mdp.describe_source()

# 12b) #25 可插拔公开披露源：刷新披露事件池（沙箱确定性 mock；真实环境 cninfo 或回退）+ 描述 + 列表
disc_refresh = disc.refresh_disclosure_pool()['data']
disc_list = disc.list_disclosure_pool()['data']
disclosure_source = disc.describe_disclosure_source()

# 12c) #28 可插拔公开舆情源：刷新舆情事件池（沙箱确定性 mock；真实环境头条爬虫 / FinBERT 或回退）+ 描述 + 列表
op_refresh = op.refresh_opinion_pool()['data']
op_list = op.list_opinion_pool()['data']
opinion_source = op.describe_opinion_source()

# 12d) #31 可插拔微信私域舆情源：刷新微信舆情事件池（沙箱确定性 mock；真实环境公众号/视频号爬虫或回退）+ 描述 + 列表
wx_refresh = wx.refresh_wechat_pool()['data']
wx_list = wx.list_wechat_pool()['data']
wechat_source = wx.describe_wechat_source()

# 12e) #34 可插拔短线快讯舆情源：刷新快讯事件池（沙箱确定性 mock；真实环境财联社/华尔街见闻/金十爬虫或回退）+ 描述 + 列表
fl_refresh = fl.refresh_flash_pool()['data']
fl_list = fl.list_flash_pool()['data']
flash_source = fl.describe_flash_source()

# 12e2) #36 可插拔深度社区舆情源：刷新社区讨论事件池（沙箱确定性 mock；真实环境雪球/股吧/淘股吧爬虫或回退）+ 描述 + 列表
cm_refresh = cm.refresh_community_pool()['data']
cm_list = cm.list_community_pool()['data']
community_source = cm.describe_community_source()

# 12e3) #37 可插拔海外权威舆情源：刷新海外权威资讯事件池（沙箱确定性 mock；真实环境彭博/路透/WSJ/Seeking Alpha 抓取或回退）+ 描述 + 列表
ov_refresh = ov.refresh_overseas_pool()['data']
ov_list = ov.list_overseas_pool()['data']
overseas_source = ov.describe_overseas_source()

# 12f) #35 可插拔 Kronos 技术面算力底座：批量技术分析（沙箱确定性 mock；真实环境 NeoQuasar 模型或回退）+ 描述 + 三类选股池
kr_refresh = kr.refresh_kronos()['data']
kronos_source = kr.describe_kronos_source()
kronos_pools = kr.kronos_pools()['data']

# 12g) #38 六层信息圈层 + 多源交叉验证：圈层定义（静态）+ 扫描级交叉验证摘要（来自 alert_scan.crossValidationSummary）
info_layers = il.describe_info_layers()
cv_summary = alert_scan.get('crossValidationSummary', {})

# 12h) #39 舆情回测 + 拐点预警（P2）：各平台情绪因子历史胜率回测报告（确定性模拟基线）+ 扫描级拐点摘要
sentiment_backtest = ob.sentiment_backtest_over_pools()
inflection_summary = alert_scan.get('inflectionSummary', {})

# 13) #24 因子库累积统计（数据驱动可视化）：闭环扫描落库的真实归因应被统计进 DB 来源
factor_stats = bt_factor.factor_library_stats()['data']

seed = {
    'pool': pool,
    'attribution': camelize(attr),
    'news': news_rows,
    'linkage': camelize(link),
    'sectorReview': camelize(sector_review),
    'attributionList': camelize(attr_list),
    'backtest': camelize(backtest),
    'agentDig': camelize(agent_dig),
    'factorLibrary': camelize(factor_library),
    'factorStats': camelize(factor_stats),
    'factorPredict': camelize(factor_predict),
    'factorForecast': camelize(factor_forecast),
    'closedLoop': camelize(closed_loop),
    'alertScan': camelize(alert_scan),
    'scanSchedule': camelize(scan_schedule),
    'scanHistory': camelize(scan_history),
    'dataSource': camelize(data_source),
    'disclosures': camelize(disc_list['items']),
    'disclosureSource': camelize(disclosure_source),
    'opinions': camelize(op_list['items']),
    'opinionSource': camelize(opinion_source),
    'wechats': camelize(wx_list['items']),
    'wechatSource': camelize(wechat_source),
    'flashes': camelize(fl_list['items']),
    'flashSource': camelize(flash_source),
    'communities': camelize(cm_list['items']),
    'communitySource': camelize(community_source),
    'overseas': camelize(ov_list['items']),
    'overseasSource': camelize(overseas_source),
    'kronosSource': camelize(kronos_source),
    'kronosPools': camelize(kronos_pools),
    'infoLayers': camelize(info_layers),
    'crossValidationSummary': camelize(cv_summary),
    'sentimentBacktest': camelize(sentiment_backtest),
    'inflectionSummary': camelize(inflection_summary),
}

out_path = os.path.join(ROOT, 'apps', 'dsa-web', 'scripts', 'backtrace_seed.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(seed, f, ensure_ascii=False, indent=2)

print('seed written ->', out_path)
print('pool:', len(pool), 'first:', first['stockName'], first['dailyGain'])
print('attribution drive_category:', attr['drive_category'], 'factors:', len(attr['driving_factor']))
print('news prior:', len([n for n in news_rows if n['isPrior']]))
print('linkage forecastRecompute:', link['forecastRecomputeTriggered'])
print('sector review prosperity:', sector_review['prosperity'], 'members:', sector_review['memberCount'])
print('backtest winRate:', backtest['winRate'], 'adjusted:', backtest['confidenceAdjusted'], 'verdict:', backtest['verdict'])
print('agent dig signalCount:', agent_dig['signalCount'], 'earlyCount:', agent_dig['earlyCount'], 'engine:', agent_dig['engine'])
print('factor library total:', factor_mine['total'], 'minedFromDb:', factor_mine['minedFromDb'], 'reinforced:', factor_mine['reinforced'])
print('factor predict prob:', factor_predict['predictedProb'], 'matched:', len(factor_predict['matched']), 'suggestion:', factor_predict['suggestion'])
print('factor forecast boost:', factor_forecast['boost'], 'structuredBoost:', factor_forecast['structuredBoost'],
      'edgeOverrides:', len(factor_forecast['edgeOverrides']), 'catEdgeContrib:', len(factor_forecast['categoryEdgeContrib']),
      'factors:', len(factor_forecast['factors']), 'engine:', factor_forecast['engine'])
print('closed-loop chain:', closed_loop['chainId'], 'shockNode:', closed_loop['shockNode'],
      'digSignals:', closed_loop['dig']['signalCount'], 'predProb:', closed_loop['predict']['predictedProb'],
      'boost:', closed_loop['propagate']['boost'])
print('alert scan total:', alert_scan['totalScanned'], 'batch:', alert_scan['scanBatch'],
      'topComposite:', alert_scan['alerts'][0]['compositeScore'] if alert_scan['alerts'] else None,
      'topLevel:', alert_scan['alerts'][0]['level'] if alert_scan['alerts'] else None)
sb = sentiment_backtest
print('sentiment-backtest universe:', sb['universeSize'], 'nDays:', sb['nDays'],
      'best:', sb['summary']['bestSource'], 'bestIc:', sb['summary']['bestIc'],
      'worst:', sb['summary']['worstSource'], 'worstIc:', sb['summary']['worstIc'])
print('sentiment-backtest bySource ic:',
      {k: sb['bySource'][k]['ic'] for k in sb['bySource']})
print('inflection summary high/medium/low/none:',
      inflection_summary.get('levelDistribution', {}).get('high', 0),
      inflection_summary.get('levelDistribution', {}).get('medium', 0),
      inflection_summary.get('levelDistribution', {}).get('low', 0),
      inflection_summary.get('levelDistribution', {}).get('none', 0),
      'types:', inflection_summary.get('typeDistribution', {}))
print('scan schedule cron:', scan_schedule['cron'], 'enabled:', scan_schedule['enabled'])
print('scan history batches:', len(scan_history), 'topBatch:', scan_history[0]['batchId'] if scan_history else None)
print('data source mode:', data_source['mode'], 'provider:', data_source['provider'], 'surgingCount:', data_source['surgingCount'])
print('disclosure source mode:', disclosure_source['mode'], 'provider:', disclosure_source['provider'],
      'disclosureCount:', disclosure_source['disclosureCount'], 'financialCount:', disclosure_source['financialCount'],
      'researchCount:', disclosure_source['researchCount'])
print('disclosure pool count:', disc_list['count'], 'refresh mode:', disc_refresh['mode'], 'refresh count:', disc_refresh['count'])
print('opinion source mode:', opinion_source['mode'], 'provider:', opinion_source['provider'],
      'opinionCount:', opinion_source['opinionCount'], 'rumorCount:', opinion_source['rumorCount'],
      'weightSuggest:', opinion_source['weightSuggest'])
print('opinion pool count:', op_list['count'], 'refresh mode:', op_refresh['mode'], 'refresh count:', op_refresh['count'])
print('wechat source mode:', wechat_source['mode'], 'provider:', wechat_source['provider'],
      'wechatCount:', wechat_source['wechatCount'], 'rumorCount:', wechat_source['rumorCount'],
      'lowCredibilityCount:', wechat_source['lowCredibilityCount'],
      'weightShort:', wechat_source['weightShortSuggest'], 'weightLong:', wechat_source['weightLongSuggest'])
print('wechat pool count:', wx_list['count'], 'refresh mode:', wx_refresh['mode'], 'refresh count:', wx_refresh['count'])
print('flash source mode:', flash_source['mode'], 'provider:', flash_source['provider'],
      'flashCount:', flash_source['flashCount'], 'rumorCount:', flash_source['rumorCount'],
      'breakingCount:', flash_source['breakingCount'],
      'weightShort:', flash_source['weightShortSuggest'], 'weightLong:', flash_source['weightLongSuggest'])
print('flash pool count:', fl_list['count'], 'refresh mode:', fl_refresh['mode'], 'refresh count:', fl_refresh['count'])
print('community source mode:', community_source['mode'], 'provider:', community_source['provider'],
      'communityCount:', community_source['communityCount'], 'rumorCount:', community_source['rumorCount'],
      'hotCount:', community_source['hotCount'],
      'weightShort:', community_source['weightShortSuggest'], 'weightLong:', community_source['weightLongSuggest'])
print('community pool count:', cm_list['count'], 'refresh mode:', cm_refresh['mode'], 'refresh count:', cm_refresh['count'])
print('overseas source mode:', overseas_source['mode'], 'provider:', overseas_source['provider'],
      'overseasCount:', overseas_source['overseasCount'], 'institutionCount:', overseas_source['institutionCount'],
      'ratingUpCount:', overseas_source['ratingUpCount'],
      'weightShort:', overseas_source['weightShortSuggest'], 'weightLong:', overseas_source['weightLongSuggest'])
print('overseas pool count:', ov_list['count'], 'refresh mode:', ov_refresh['mode'], 'refresh count:', ov_refresh['count'])
print('kronos source mode:', kronos_source['mode'], 'provider:', kronos_source['provider'],
      'analyzedCount:', kronos_source['analyzedCount'], 'modelSpec:', kronos_source['modelSpec'],
      'shortCap:', kronos_source['weightShortCap'], 'longCap:', kronos_source['weightLongCap'])
print('kronos pools strongShort:', kronos_pools['shortTermStrong'], 'reversal:', kronos_pools['reversal'], 'riskWarn:', kronos_pools['riskWarning'])
print('factor library stats preset:', factor_stats['presetCount'], 'dbAttr:', factor_stats['dbAttributionCount'],
      'minedFromDb:', factor_stats['minedFromDb'], 'reinforced:', factor_stats['reinforced'], 'total:', factor_stats['libraryTotal'])
