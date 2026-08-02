# -*- coding: utf-8 -*-
"""反向归因回溯子系统验证（request -> data）：外挂微服务全链路。

用 importlib 加载 storage + backtrace 端点，绕开包 __init__ 级联导入，
验证 §3.1 筛选 → §3.2 回溯(时间过滤) → §3.3/§3.4 归因 → §3.5 DSA 联动。
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load(modname: str, path: str):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


storage = _load('src_storage_bt', os.path.join(ROOT, 'src', 'storage.py'))
bt_ep = _load('api_v1_endpoints_backtrace_bt', os.path.join(ROOT, 'api', 'v1', 'endpoints', 'backtrace.py'))
ic_ep = _load('api_v1_endpoints_industry_chain_bt', os.path.join(ROOT, 'api', 'v1', 'endpoints', 'industry_chain.py'))

app = FastAPI()
app.include_router(bt_ep.router, prefix='/api/v1/backtrace')
app.include_router(ic_ep.router, prefix='/api/v1')
client = TestClient(app)


def _reset_db() -> None:
    m = storage.DatabaseManager.get_instance()
    with m.session_scope() as s:
        for tbl in (
            storage.BacktraceLinkage,
            storage.BacktraceAttribution,
            storage.BacktraceNewsDoc,
            storage.BacktraceScreenPool,
            storage.BacktraceSectorReview,
            storage.BacktraceBacktest,
            storage.BacktraceAgentSignal,
            storage.BacktraceFactorLibrary,
            storage.BacktraceScanAlert,
            storage.BacktraceScanBatch,
            storage.BacktraceScanSchedule,
            storage.BacktraceDisclosure,
            storage.BacktraceOpinion,
            storage.BacktraceWechatOpinion,
            storage.BacktraceFlashOpinion,
            storage.BacktraceCommunityOpinion,
            storage.BacktraceOverseasOpinion,
            storage.BacktraceKronosSignal,
        ):
            s.query(tbl).delete()


def main() -> None:
    _reset_db()

    # 1) 模块 1：运行大涨个股筛选
    r = client.post('/api/v1/backtrace/screen')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['code'] == 0 and body['data'] is not None, body
    pool = body['data']['items']
    print('screen pool count:', body['data']['count'], 'sample:', pool[0]['stockName'], pool[0]['dailyGain'])
    assert body['data']['count'] == 12, body['data']
    assert all(p['dailyGain'] >= 5.0 for p in pool), '默认规则：涨幅≥5%'

    # 2) 筛选池查询
    r = client.get('/api/v1/backtrace/screen-pool')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == 12

    # 3) 模块 2：回溯单只个股拉升前历史资讯（时间过滤护栏）
    target = pool[0]
    code = target['stockCode']
    r = client.post('/api/v1/backtrace/backtrack', json={'stock_code': code, 'window_days': 30})
    assert r.status_code == 200, r.text
    bt = r.json()
    assert bt['code'] == 0 and bt['data'] is not None, bt
    d = bt['data']
    print('backtrack:', code, 'priorCount=', d['priorCount'], 'excludedCount=', d['excludedCount'])
    assert d['priorCount'] >= 5, d           # 含多源拉升前资讯
    assert d['excludedCount'] >= 1, d         # 拉升后新闻被剔除（防事后归因）
    assert all(doc['isPrior'] for doc in d['docs']), d   # 仅返回拉升前文档

    # 4) 模块 3+4：反向归因全链路（回溯 → 归因 → 标准化输出）
    r = client.post('/api/v1/backtrace/attribute', json={'stock_code': code})
    assert r.status_code == 200, r.text
    attr = r.json()
    assert attr['code'] == 0 and attr['data'] is not None, attr
    res = attr['data']
    print('attribution drive_category=', res['drive_category'], 'trend=', res['trend_persistence_judge'])
    # §3.4 字段齐备
    for k in ('stock_code', 'stock_name', 'rise_start_date', 'daily_gain', 'total_rise_days',
              'driving_factor', 'similar_history_case', 'trend_persistence_judge', 'suggest_adjust'):
        assert k in res, f'missing {k}'
    # 权重合计 100
    wsum = sum(f['weight'] for f in res['driving_factor'])
    print('weights sum=', wsum, 'factors=', len(res['driving_factor']))
    assert wsum == 100, wsum
    # 三类驱动齐备
    types = {f['factor_type'] for f in res['driving_factor']}
    assert {'核心强驱动', '次要催化', '情绪炒作'} <= types, types
    # 防幻觉护栏
    g = res['guardrails']
    assert g['time_filtered'] is True, g
    assert g['min_sources_enforced'] is True, g
    assert g['weights_sum'] == 100, g
    assert res['attribution_id'] is not None

    # 5) 模块 5：DSA 联动
    r = client.post('/api/v1/backtrace/link', json={'attribution_id': res['attribution_id']})
    assert r.status_code == 200, r.text
    link = r.json()
    assert link['code'] == 0 and link['data'] is not None, link
    acts = link['data']['actions']
    print('linkage actions:', {k: acts[k] for k in ('eventLibraryAdded', 'forecastRecomputeTriggered', 'caseBanked')})
    assert acts['eventLibraryAdded'] is True, acts
    assert acts['forecastRecomputeTriggered'] is True, acts
    assert acts['forecastRecomputeEndpoint'] == '/api/v1/forecast-snapshots', acts

    # 6) 列表查询
    r = client.get('/api/v1/backtrace/attributions', params={'stock_code': code})
    assert r.status_code == 200 and r.json()['total'] >= 1, r.text
    r = client.get('/api/v1/backtrace/linkages', params={'stock_code': code})
    assert r.status_code == 200 and r.json()['total'] >= 1, r.text

    # 7) 模块 6：批量板块复盘（§3.6）
    r = client.post('/api/v1/backtrace/sector-review', json={'sector': '新能源'})
    assert r.status_code == 200, r.text
    sr = r.json()
    assert sr['code'] == 0 and sr['data'] is not None, sr
    sdata = sr['data']
    print('sector review:', sdata['sector'], 'prosperity=', sdata['prosperity'],
          'members=', sdata['memberCount'])
    assert sdata['memberCount'] >= 2, sdata           # 板块集体大涨成分股
    assert sdata['prosperity'] in ('景气主升', '景气上行（分化）', '情绪脉冲 / 板块退潮'), sdata
    assert len(sdata['conductionChain']) >= 3, sdata  # 上下游传导链
    assert len(sdata['commonDrivers']) >= 3, sdata    # 共同前置事件分布
    assert len(sdata['perStock']) == sdata['memberCount'], sdata
    # 聚合字段齐备
    agg = sdata['aggregate']
    for k in ('memberCount', 'strongRate', 'avgCoreWeight', 'categoryDistribution', 'trendDistribution'):
        assert k in agg, f'missing {k}'
    # 未知板块应被拒绝
    r = client.post('/api/v1/backtrace/sector-review', json={'sector': '不存在的板块'})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text

    # 8) 板块复盘列表查询
    r = client.get('/api/v1/backtrace/sector-reviews', params={'sector': '新能源'})
    assert r.status_code == 200 and r.json()['total'] >= 1, r.text

    # 9) 模块 7：归因有效性回测校验（§3.7）
    r = client.post('/api/v1/backtrace/backtest', json={'attribution_id': res['attribution_id']})
    assert r.status_code == 200, r.text
    bw = r.json()
    assert bw['code'] == 0 and bw['data'] is not None, bw
    bdata = bw['data']
    print('backtest win_rate=', bdata['winRate'], 'samples=', bdata['samples'],
          'adj_conf=', bdata['confidenceAdjusted'], 'verdict=', bdata['verdict'])
    assert 0.0 <= bdata['winRate'] <= 1.0, bdata
    assert bdata['samples'] >= 30, bdata                    # 历史样本覆盖充足
    assert bdata['expectancy1m'] is not None, bdata
    assert 0.0 <= bdata['confidenceAdjusted'] <= 1.0, bdata
    assert bdata['verdict'] in (
        '归因逻辑历史有效（可纳入因子库）',
        '历史有效性中性（建议结合其它信号）',
        '历史有效性不足（建议审慎，弱化该归因权重）',
    ), bdata
    assert len(bdata['matchedBuckets']) >= 1, bdata        # 至少匹配到一个历史样本桶
    # 回测修正后落入 [原置信度, 1] 的合理区间（上调或维持或下调但不失真）
    assert bdata['confidenceAdjusted'] <= 0.95 + 1e-9, bdata
    assert bdata['confidenceAdjusted'] >= 0.30 - 1e-9, bdata

    # 10) 回测列表查询
    r = client.get('/api/v1/backtrace/backtests', params={'attribution_id': res['attribution_id']})
    assert r.status_code == 200 and r.json()['total'] >= 1, r.text
    # 未知归因应被拒
    r = client.post('/api/v1/backtrace/backtest', json={'attribution_id': 999999})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text

    # 11) 增强模块：Agent 自主深挖小众突发事件
    r = client.post('/api/v1/backtrace/agent-dig', json={'stock_code': code, 'window_days': 30})
    assert r.status_code == 200, r.text
    ag = r.json()
    assert ag['code'] == 0 and ag['data'] is not None, ag
    adata = ag['data']
    print('agent dig:', adata['stockCode'], 'signalCount=', adata['signalCount'],
          'earlyCount=', adata['earlyCount'], 'engine=', adata['engine'])
    assert adata['signalCount'] >= 4, adata                 # 四类隐藏信号源齐备
    assert adata['earlyCount'] >= 1, adata                  # 至少 1 条小众早期信号
    assert len(adata['timeline']) == adata['signalCount'], adata
    # 信号按评分降序（端点返回 snake_case 键，前端经 toCamelCase 转为 camelCase）
    scores = [s['score'] for s in adata['signals']]
    assert scores == sorted(scores, reverse=True), scores
    # 全部信号位于拉升前（lead_days > 0 且 signal_date < rise_start_date）
    assert all(s['lead_days'] > 0 for s in adata['signals']), adata
    # 评分在 0~100
    assert all(0.0 <= s['score'] <= 100.0 for s in adata['signals']), adata

    # 12) Agent 信号列表查询
    r = client.get('/api/v1/backtrace/agent-signals', params={'stock_code': code})
    assert r.status_code == 200 and r.json()['total'] >= 4, r.text

    # 13) 增强模块：高频上涨因子自动沉淀（因子库 + 正向预判）
    r = client.post('/api/v1/backtrace/factor-mine', json={'recompute': True})
    assert r.status_code == 200, r.text
    fm = r.json()
    assert fm['code'] == 0 and fm['data'] is not None, fm
    fdata = fm['data']
    print('factor-mine total=', fdata['total'], 'minedFromDb=', fdata['minedFromDb'], 'reinforced=', fdata['reinforced'])
    assert fdata['total'] >= 8, fdata                    # 预设基线 + DB 强化
    assert all(0.0 <= it['avgWinRate'] <= 1.0 for it in fdata['items']), fdata
    assert all(0.0 <= it['confidence'] <= 1.0 for it in fdata['items']), fdata
    assert all(it['occurCount'] >= 1 for it in fdata['items']), fdata
    # 排序：高频优先（出现次数降序）
    occur = [it['occurCount'] for it in fdata['items']]
    assert occur == sorted(occur, reverse=True), occur

    # 因子库查询（三种排序）
    r = client.get('/api/v1/backtrace/factor-library', params={'sort_by': 'heat'})
    assert r.status_code == 200 and r.json()['total'] >= 8, r.text
    r = client.get('/api/v1/backtrace/factor-library', params={'sort_by': 'win'})
    assert r.status_code == 200 and r.json()['total'] >= 8, r.text
    r = client.get('/api/v1/backtrace/factor-library', params={'sort_by': 'expectancy'})
    assert r.status_code == 200 and r.json()['total'] >= 8, r.text

    # 正向预判：早期信号 → 上涨概率
    r = client.post('/api/v1/backtrace/factor-predict',
                    json={'detected_factors': ['机构调研', '产业链异动'], 'stock_code': code})
    assert r.status_code == 200, r.text
    fp = r.json()
    assert fp['code'] == 0 and fp['data'] is not None, fp
    pdata = fp['data']
    print('factor-predict prob=', pdata['predictedProb'], 'exp=', pdata['avgExpectancy'],
          'matched=', len(pdata['matched']), 'suggestion=', pdata['suggestion'])
    assert 0.0 <= pdata['predictedProb'] <= 1.0, pdata
    assert len(pdata['matched']) >= 1, pdata
    assert pdata['suggestion'] in ('强信号：历史有效性高，建议上调正向因子评分并纳入观察',
                                    '中性偏多：建议结合其它信号综合判断',
                                    '审慎：历史有效性不足或样本偏少，弱化该预判权重'), pdata
    # 置信度加权概率应落在命中因子胜率区间内
    wr = [m['avgWinRate'] for m in pdata['matched']]
    assert min(wr) <= pdata['predictedProb'] <= max(wr), pdata

    # 空信号应被拒
    r = client.post('/api/v1/backtrace/factor-predict', json={'detected_factors': []})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text

    # 14) 闭环增强：因子库 → DSA 内核正向传导桥接（内核零改动）
    r = client.post('/api/v1/industry-chains/lithium/factor-forecast',
                    json={'shock': {'node': '锂矿', 'magnitude': 0.3, 'kind': 'demand'},
                          'top_n': 6, 'min_confidence': 0.6})
    assert r.status_code == 200, r.text
    fc = r.json()
    assert fc['code'] == 0 and fc['data'] is not None, fc
    cdata = fc['data']
    print('factor-forecast chain=', cdata['chainId'], 'boost=', cdata['boost'],
          'factors=', len(cdata['factors']), 'engine=', cdata['engine'])
    assert cdata['factors'], cdata                       # 注入至少 1 个沉淀因子
    assert 0.0 <= cdata['boost'] <= 0.5, cdata          # 因子增益钳制 [0, 0.5]
    assert cdata['enhanced']['maxImpactPct'] >= cdata['baseline']['maxImpactPct'], cdata  # 增强≥基线
    assert len(cdata['forward4']['periods']) == 4, cdata  # 四周期预测
    assert len(cdata['forward4']['baseline']) == 4 and len(cdata['forward4']['enhanced']) == 4, cdata
    assert all(0.0 <= w <= 1.0 for w in cdata['factorWeights'].values()), cdata
    # 提升幅度：结构化注入（包络幅度增益 + 边系数覆盖）仅增不减，故 lift ≥ boost×基线（容忍四舍五入）
    assert cdata['liftPct']['maxImpact'] >= cdata['boost'] * cdata['baseline']['maxImpactPct'] - 0.1, cdata

    # #22 结构化边注入：按因子类别差异化增强对应边系数（内核 use_overrides 通道，零改动）
    assert cdata['structuredBoost'] is not None and 0.0 <= cdata['structuredBoost'] <= 0.5, cdata
    assert isinstance(cdata['edgeOverrides'], list) and len(cdata['edgeOverrides']) >= 1, cdata
    assert isinstance(cdata['categoryEdgeContrib'], list) and len(cdata['categoryEdgeContrib']) >= 1, cdata
    for o in cdata['edgeOverrides']:
        assert o['overrideCoeff'] >= o['baseCoeff'] - 1e-9, o          # 仅增不减
        assert o['edgeType'] in ('cost', 'demand', 'supply', 'subst'), o
        assert isinstance(o.get('categories'), list) and len(o['categories']) >= 1, o
    assert any(c['edgeType'] in ('cost', 'demand', 'supply', 'subst') for c in cdata['categoryEdgeContrib']), cdata
    print('  #22 structured inject: edges=', len(cdata['edgeOverrides']),
          'catEdgeContrib=', len(cdata['categoryEdgeContrib']), 'structuredBoost=', cdata['structuredBoost'])

    # 未知产业链应被拒
    r = client.post('/api/v1/industry-chains/unknown_chain/factor-forecast',
                    json={'shock': {'node': 'x', 'magnitude': 0.3}})
    assert r.status_code == 404, r.text

    # 15) 收尾闭环：一键闭环（深挖 → 预判 → 内核传导）
    r = client.post('/api/v1/backtrace/closed-loop', json={'stock_code': code})
    assert r.status_code == 200, r.text
    cl = r.json()
    assert cl['code'] == 0 and cl['data'] is not None, cl
    cld = cl['data']
    print('closed-loop:', cld['stockCode'], 'chain=', cld['chainId'], 'shockNode=', cld['shockNode'],
          'digSignals=', cld['dig']['signalCount'], 'predProb=', cld['predict']['predictedProb'],
          'boost=', cld['propagate']['boost'])
    assert cld['dig']['signalCount'] >= 4, cld                 # 阶段一：深挖信号齐备
    assert cld['predict']['predictedProb'] > 0, cld            # 阶段二：预判有效
    assert len(cld['predict']['matched']) >= 1, cld            # 命中因子库
    assert 0.0 <= cld['propagate']['boost'] <= 0.5, cld        # 阶段三：增益钳制
    assert cld['propagate']['enhanced']['maxImpactPct'] >= cld['propagate']['baseline']['maxImpactPct'], cld
    assert len(cld['propagate']['forward4']['periods']) == 4, cld
    assert cld['propagate']['factors'], cld                     # 闭环联动注入因子
    # #24 数据驱动：闭环默认把真实反向归因落库（喂给因子库）
    assert cld['attribution'] is not None, cld
    assert cld['attribution']['attribution_id'] is not None, cld
    assert cld['attribution']['drive_category'] in (
        '基本面事件驱动', '题材情绪驱动', '资金筹码驱动'), cld['attribution']

    # 空 stock_code 应被拒
    r = client.post('/api/v1/backtrace/closed-loop', json={'stock_code': ''})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text

    # 16) #20 自动化闭环预警扫描：对大增回溯池批量跑闭环，输出分级预警
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200, r.text
    scan = r.json()
    assert scan['code'] == 0 and scan['data'] is not None, scan
    sdata = scan['data']
    print('closed-loop scan total=', sdata['totalScanned'], 'batch=', sdata['scanBatch'])
    assert sdata['totalScanned'] >= 5, sdata                     # 回溯池 12 只，全部扫描
    assert len(sdata['alerts']) == sdata['totalScanned'], sdata
    # 综合评分区间与降序
    comps = [a['compositeScore'] for a in sdata['alerts']]
    assert all(0.0 <= c <= 1.0 for c in comps), sdata
    assert comps == sorted(comps, reverse=True), comps
    # 预警级别取值合法
    valid_levels = ('强信号·重点关注', '中性·持续观察', '弱信号·低关注')
    assert all(a['level'] in valid_levels for a in sdata['alerts']), sdata
    # 字段齐备
    for a in sdata['alerts']:
        for k in ('stockCode', 'chainId', 'signalCount', 'earlyCount', 'topSignalScore',
                  'predictedProb', 'boost', 'matchedFactors', 'compositeScore', 'level'):
            assert k in a, (k, a)
    # 至少一个强 / 中性预警（池内多只半导体/新能源应命中）
    assert any(a['level'] != '弱信号·低关注' for a in sdata['alerts']), sdata

    # 查询最近一次扫描批次
    r = client.get('/api/v1/backtrace/closed-loop/alerts')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    adata = r.json()['data']
    print('alerts query batch=', adata['batch'], 'total=', adata['total'])
    assert adata['total'] == sdata['totalScanned'], adata
    assert adata['items'][0]['stockCode'] == sdata['alerts'][0]['stockCode'], adata

    # 显式空 watchlist 应被拒（而非回退到池）
    r = client.post('/api/v1/backtrace/closed-loop/scan', json={'watchlist': [], 'limit': None})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text

    # 17) #21 闭环预警自动化调度：调度触发（落批次）+ 历史 + 调度配置
    # 17a) 读取默认调度配置
    r = client.get('/api/v1/backtrace/closed-loop/scan/schedule')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sched = r.json()['data']
    print('schedule default cron=', sched['cron'], 'enabled=', sched['enabled'])
    assert sched['cron'] == '30 15 * * 1-5', sched
    assert sched['enabled'] is True, sched

    # 17b) 调度触发入口：手动跑一次闭环预警并落批次聚合
    r = client.post('/api/v1/backtrace/closed-loop/scan/run', json={'run_type': 'manual'})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run['code'] == 0 and run['data'] is not None, run
    rd = run['data']
    print('scan/run batch=', rd['batch']['batchId'], 'runType=', rd['batch']['runType'],
          'total=', rd['batch']['totalScanned'], 'strong=', rd['batch']['strongCount'])
    assert rd['batch']['runType'] == 'manual', rd
    assert rd['batch']['totalScanned'] >= 5, rd
    # batch 分级计数合计 = total
    assert rd['batch']['strongCount'] + rd['batch']['neutralCount'] + rd['batch']['weakCount'] == rd['batch']['totalScanned'], rd
    # batch 聚合的 Top 标的应与本轮 Top 预警一致
    assert rd['batch']['topStock'] == rd['scan']['alerts'][0]['stockCode'], rd
    assert abs(rd['batch']['topComposite'] - rd['scan']['alerts'][0]['compositeScore']) < 1e-6, rd

    # 17c) 再跑一次（定时类型）以验证历史倒序
    r = client.post('/api/v1/backtrace/closed-loop/scan/run', json={'run_type': 'schedule'})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text

    # 17d) 批次历史：应包含 2 条且按时间倒序（最新 schedule 在前）
    r = client.get('/api/v1/backtrace/closed-loop/scan/history')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    hdata = r.json()['data']
    print('scan history total=', hdata['total'])
    assert hdata['total'] >= 2, hdata
    items = hdata['items']
    assert items[0]['runType'] == 'schedule', items[0]   # 最新的在前
    assert items[1]['runType'] == 'manual', items[1]

    # 17e) 更新调度配置（cron 校验 + 落库）
    r = client.put('/api/v1/backtrace/closed-loop/scan/schedule', json={'cron': '0 16 * * 1-5', 'enabled': True})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['cron'] == '0 16 * * 1-5', r.json()
    # 非法 cron（非 5 段）应被拒
    r = client.put('/api/v1/backtrace/closed-loop/scan/schedule', json={'cron': 'bad-cron'})
    assert r.status_code == 200 and r.json()['code'] != 0, r.text
    # 恢复默认
    r = client.put('/api/v1/backtrace/closed-loop/scan/schedule', json={'cron': '30 15 * * 1-5', 'enabled': True})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text

    # 18) #23 可插拔数据源适配：沙箱默认 mock，真实环境(DSA_REALTIME_MARKET=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/scan/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    src = r.json()['data']
    print('data source mode=', src['mode'], 'provider=', src['provider'], 'surgingCount=', src['surgingCount'])
    assert src['mode'] in ('real', 'mock'), src
    assert src['provider'], src
    # #23 设计：沙箱无 DSA_REALTIME_MARKET → 必为 mock；真实环境为 AkShare 或回退 mock
    assert src['mode'] == 'mock', src
    assert src['surgingCount'] > 0, src                     # mock 确定性池非空

    # 18b) 用活跃数据源刷新当日回溯池（真实环境拉取涨幅榜；mock 重写确定性池）
    r = client.post('/api/v1/backtrace/closed-loop/scan/refresh-pool', params={'limit': 200})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    rp = r.json()['data']
    print('refresh-pool mode=', rp['mode'], 'count=', rp['count'])
    assert rp['count'] > 0, rp
    assert rp['mode'] == 'mock', rp

    # 18c) #25 可插拔公开披露源：沙箱默认 mock，真实环境(DSA_REALTIME_DISCLOSURE=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/disclosure/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    dsrc = r.json()['data']
    print('disclosure source mode=', dsrc['mode'], 'provider=', dsrc['provider'],
          'disclosureCount=', dsrc['disclosureCount'], 'financialCount=', dsrc['financialCount'],
          'researchCount=', dsrc['researchCount'])
    assert dsrc['mode'] in ('real', 'mock'), dsrc
    assert dsrc['provider'], dsrc
    # #25 设计：沙箱无 DSA_REALTIME_DISCLOSURE → 必为 mock；真实环境为 cninfo 或回退 mock
    assert dsrc['mode'] == 'mock', dsrc
    assert dsrc['disclosureCount'] > 0, dsrc               # mock 确定性披露事件非空

    # 18d) 用活跃披露源刷新披露事件池（真实环境拉取 cninfo/财报/研报；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/disclosure/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    drp = r.json()['data']
    print('disclosure refresh mode=', drp['mode'], 'count=', drp['count'],
          'financial=', drp['financialCount'], 'research=', drp['researchCount'])
    assert drp['count'] > 0, drp
    assert drp['mode'] == 'mock', drp
    # 披露事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/disclosures')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == drp['count'], r.json()

    # 18e) #25 扫描叠加：闭环预警扫描应把披露事件池标的作为基本面筛选叠加（disclosureCandidates≥1）
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sdata2 = r.json()['data']
    print('scan(overlay) total=', sdata2['totalScanned'], 'disclosureCandidates=', sdata2['disclosureCandidates'])
    assert sdata2['disclosureCandidates'] >= 1, sdata2      # 沙箱 mock 披露覆盖大涨池内标的
    assert all('hasDisclosure' in a for a in sdata2['alerts']), sdata2

    # 18f) #28 可插拔公开舆情源：沙箱默认 mock，真实环境(DSA_REALTIME_OPINION=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/opinion/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    osrc = r.json()['data']
    print('opinion source mode=', osrc['mode'], 'provider=', osrc['provider'],
          'opinionCount=', osrc['opinionCount'], 'rumorCount=', osrc['rumorCount'],
          'weightSuggest=', osrc['weightSuggest'])
    assert osrc['mode'] in ('real', 'mock'), osrc
    assert osrc['provider'], osrc
    # #28 设计：沙箱无 DSA_REALTIME_OPINION → 必为 mock；真实环境为头条爬虫或回退 mock
    assert osrc['mode'] == 'mock', osrc
    assert osrc['opinionCount'] > 0, osrc               # mock 确定性舆情事件非空

    # 18g) 用活跃舆情源刷新舆情事件池（真实环境头条爬虫 / FinBERT；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/opinion/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    orp = r.json()['data']
    print('opinion refresh mode=', orp['mode'], 'count=', orp['count'], 'rumorCount=', orp['rumorCount'])
    assert orp['count'] > 0, orp
    assert orp['mode'] == 'mock', orp
    # 舆情事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/opinions')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == orp['count'], r.json()

    # 18h) #28 扫描叠加：闭环预警扫描应把舆情事件池标的作为情绪面筛选叠加（opinionCandidates≥1）
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sdata3 = r.json()['data']
    print('scan(overlay) total=', sdata3['totalScanned'], 'disclosureCandidates=',
          sdata3['disclosureCandidates'], 'opinionCandidates=', sdata3['opinionCandidates'],
          'wechatCandidates=', sdata3['wechatCandidates'])
    assert sdata3['opinionCandidates'] >= 1, sdata3      # 沙箱 mock 舆情覆盖大涨池内标的
    assert sdata3['wechatCandidates'] >= 1, sdata3       # 沙箱 mock 微信舆情覆盖大涨池内标的
    assert all('hasOpinion' in a for a in sdata3['alerts']), sdata3
    assert all('hasWechat' in a for a in sdata3['alerts']), sdata3

    # 18i) #31 可插拔微信私域舆情源：沙箱默认 mock，真实环境(DSA_REALTIME_WECHAT=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/wechat/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    wsrc = r.json()['data']
    print('wechat source mode=', wsrc['mode'], 'provider=', wsrc['provider'],
          'wechatCount=', wsrc['wechatCount'], 'rumorCount=', wsrc['rumorCount'],
          'lowCredibilityCount=', wsrc['lowCredibilityCount'],
          'weightShort=', wsrc['weightShortSuggest'], 'weightLong=', wsrc['weightLongSuggest'])
    assert wsrc['mode'] in ('real', 'mock'), wsrc
    assert wsrc['provider'], wsrc
    # #31 设计：沙箱无 DSA_REALTIME_WECHAT → 必为 mock；真实环境为公众号/视频号爬虫或回退 mock
    assert wsrc['mode'] == 'mock', wsrc
    assert wsrc['wechatCount'] > 0, wsrc               # mock 确定性微信舆情事件非空
    # 文档 §二/§五：微信权重高于头条（短线 0.20 > 0.15，长线 0.08 > 0.05）
    assert wsrc['weightShortSuggest'] > 0.15, wsrc
    assert wsrc['weightLongSuggest'] > 0.05, wsrc

    # 18j) 用活跃微信舆情源刷新微信舆情事件池（真实环境公众号/视频号爬虫；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/wechat/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    wrp = r.json()['data']
    print('wechat refresh mode=', wrp['mode'], 'count=', wrp['count'], 'rumorCount=', wrp['rumorCount'],
          'lowCredibilityCount=', wrp['lowCredibilityCount'])
    assert wrp['count'] > 0, wrp
    assert wrp['mode'] == 'mock', wrp
    # 微信舆情事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/wechats')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == wrp['count'], r.json()

    # 18k) #34 可插拔短线快讯舆情源：沙箱默认 mock，真实环境(DSA_REALTIME_FLASH=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/flash/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    fsrc = r.json()['data']
    print('flash source mode=', fsrc['mode'], 'provider=', fsrc['provider'],
          'flashCount=', fsrc['flashCount'], 'rumorCount=', fsrc['rumorCount'],
          'breakingCount=', fsrc['breakingCount'],
          'weightShort=', fsrc['weightShortSuggest'], 'weightLong=', fsrc['weightLongSuggest'])
    assert fsrc['mode'] in ('real', 'mock'), fsrc
    assert fsrc['provider'], fsrc
    # #34 设计：沙箱无 DSA_REALTIME_FLASH → 必为 mock；真实环境为财联社/华尔街见闻/金十爬虫或回退 mock
    assert fsrc['mode'] == 'mock', fsrc
    assert fsrc['flashCount'] > 0, fsrc               # mock 确定性快讯事件非空
    # 文档 §一.2 / §五.2：财联社短线权重 0.22（短线合并模型维度，仅次于圈内前瞻 0.20 与公告落地 0.25）
    assert fsrc['weightShortSuggest'] == 0.22, fsrc
    # 长线参考值 0.09（未纳入 §五.2 长线合并模型，仅作展示）
    assert fsrc['weightLongSuggest'] == 0.09, fsrc

    # 18l) 用活跃快讯源刷新快讯事件池（真实环境财联社/华尔街见闻/金十爬虫；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/flash/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    frp = r.json()['data']
    print('flash refresh mode=', frp['mode'], 'count=', frp['count'], 'rumorCount=', frp['rumorCount'],
          'breakingCount=', frp['breakingCount'])
    assert frp['count'] > 0, frp
    assert frp['mode'] == 'mock', frp
    # 快讯事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/flashes')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == frp['count'], r.json()

    # 18m) #34 扫描叠加：闭环预警扫描应把快讯事件池标的作为短线情绪面筛选叠加（flashCandidates≥1）
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sdata4 = r.json()['data']
    print('scan(overlay) total=', sdata4['totalScanned'], 'disclosureCandidates=',
          sdata4['disclosureCandidates'], 'opinionCandidates=', sdata4['opinionCandidates'],
          'wechatCandidates=', sdata4['wechatCandidates'], 'flashCandidates=', sdata4['flashCandidates'])
    assert sdata4['flashCandidates'] >= 1, sdata4      # 沙箱 mock 快讯覆盖大涨池内标的
    assert all('hasFlash' in a for a in sdata4['alerts']), sdata4

    # 18m2) #36 可插拔深度社区舆情源：沙箱默认 mock，真实环境(DSA_REALTIME_COMMUNITY=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/community/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    csrc = r.json()['data']
    print('community source mode=', csrc['mode'], 'provider=', csrc['provider'],
          'communityCount=', csrc['communityCount'], 'rumorCount=', csrc['rumorCount'],
          'hotCount=', csrc['hotCount'],
          'weightShort=', csrc['weightShortSuggest'], 'weightLong=', csrc['weightLongSuggest'])
    assert csrc['mode'] in ('real', 'mock'), csrc
    assert csrc['provider'], csrc
    # #36 设计：沙箱无 DSA_REALTIME_COMMUNITY → 必为 mock；真实环境为雪球/股吧/淘股吧爬虫或回退 mock
    assert csrc['mode'] == 'mock', csrc
    assert csrc['communityCount'] > 0, csrc           # mock 确定性社区讨论非空
    # 文档 §一.2：社区讨论短线权重 0.13；长线参考值 0.05（社区对中长线影响弱）
    assert csrc['weightShortSuggest'] == 0.13, csrc
    assert csrc['weightLongSuggest'] == 0.05, csrc

    # 18m3) 用活跃社区源刷新社区讨论事件池（真实环境雪球/股吧/淘股吧爬虫；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/community/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    crp = r.json()['data']
    print('community refresh mode=', crp['mode'], 'count=', crp['count'], 'rumorCount=', crp['rumorCount'],
          'hotCount=', crp['hotCount'])
    assert crp['count'] > 0, crp
    assert crp['mode'] == 'mock', crp
    # 社区讨论事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/communities')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == crp['count'], r.json()

    # 18m4) #36 扫描叠加：闭环预警扫描应把社区讨论事件池标的作为社区情绪面筛选叠加（communityCandidates≥1）
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sdata5 = r.json()['data']
    print('scan(overlay) total=', sdata5['totalScanned'], 'communityCandidates=', sdata5['communityCandidates'])
    assert sdata5['communityCandidates'] >= 1, sdata5  # 沙箱 mock 社区覆盖大涨池内标的
    assert all('hasCommunity' in a for a in sdata5['alerts']), sdata5

    # 18m5) #37 可插拔海外权威舆情源：沙箱默认 mock，真实环境(DSA_REALTIME_OVERSEAS=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/overseas/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    osrc = r.json()['data']
    print('overseas source mode=', osrc['mode'], 'provider=', osrc['provider'],
          'overseasCount=', osrc['overseasCount'], 'institutionCount=', osrc['institutionCount'],
          'ratingUpCount=', osrc['ratingUpCount'],
          'weightShort=', osrc['weightShortSuggest'], 'weightLong=', osrc['weightLongSuggest'])
    assert osrc['mode'] in ('real', 'mock'), osrc
    assert osrc['provider'], osrc
    # #37 设计：沙箱无 DSA_REALTIME_OVERSEAS → 必为 mock；真实环境为彭博/路透/WSJ/Seeking Alpha 抓取或回退 mock
    assert osrc['mode'] == 'mock', osrc
    assert osrc['overseasCount'] > 0, osrc           # mock 确定性海外资讯非空
    # 文档 §一.6 / §五.2：海外短线权重 0.14；长线外资维度 0.18（§五.2 保留彭博/路透系）
    assert osrc['weightShortSuggest'] == 0.14, osrc
    assert osrc['weightLongSuggest'] == 0.18, osrc

    # 18m6) 用活跃海外源刷新海外权威资讯事件池（真实环境彭博/路透/WSJ/Seeking Alpha 抓取；mock 写入确定性模板）
    r = client.post('/api/v1/backtrace/closed-loop/overseas/refresh', json={'days': 7})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    orp = r.json()['data']
    print('overseas refresh mode=', orp['mode'], 'count=', orp['count'], 'institutionCount=', orp['institutionCount'],
          'ratingUpCount=', orp['ratingUpCount'])
    assert orp['count'] > 0, orp
    assert orp['mode'] == 'mock', orp
    # 海外权威资讯事件池可查询
    r = client.get('/api/v1/backtrace/closed-loop/overseas')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    assert r.json()['data']['count'] == orp['count'], r.json()

    # 18m7) #37 扫描叠加：闭环预警扫描应把海外权威资讯事件池标的作为海外权威情绪面筛选叠加（overseasCandidates≥1）
    # 注：闭环扫描在 watchlist=None 时惰性刷新各事件池后统一叠加；sdata5 已是含海外叠加的同一批次结果
    assert sdata5['overseasCandidates'] >= 1, sdata5  # 沙箱 mock 海外覆盖大涨池内标的
    assert all('hasOverseas' in a for a in sdata5['alerts']), sdata5

    # 18n) #35 可插拔 Kronos 技术面算力底座：沙箱默认 mock，真实环境(DSA_REALTIME_KRONOS=1)优雅回退
    r = client.get('/api/v1/backtrace/closed-loop/kronos/source')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    ksrc = r.json()['data']
    print('kronos source mode=', ksrc['mode'], 'provider=', ksrc['provider'],
          'analyzedCount=', ksrc['analyzedCount'], 'modelSpec=', ksrc.get('modelSpec'),
          'shortCap=', ksrc['weightShortCap'], 'longCap=', ksrc['weightLongCap'])
    assert ksrc['mode'] in ('mock', 'real'), ksrc
    assert ksrc['analyzedCount'] >= 0, ksrc
    assert abs(ksrc['weightShortCap'] - 0.35) < 1e-9, ksrc      # §七 短线权重硬上限 0.35
    assert abs(ksrc['weightLongCap'] - 0.15) < 1e-9, ksrc       # §七 长线权重硬上限 0.15

    # 18o) #35 刷新 Kronos 技术面信号（千股并行预测的单体入口）
    r = client.post('/api/v1/backtrace/closed-loop/kronos/refresh', json={'codes': None, 'days': 30})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    krp = r.json()['data']
    print('kronos refresh mode=', krp['mode'], 'analyzed=', krp['analyzed'], 'provider=', krp['provider'])
    assert krp['analyzed'] >= 1, krp

    # 18p) #35 三类选股池（强势/反转/风险）+ 信号列表
    r = client.get('/api/v1/backtrace/closed-loop/kronos/pools')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    kp = r.json()['data']
    print('kronos pools strongShort=', len(kp['shortTermStrong']), 'reversal=', len(kp['reversal']), 'riskWarn=', len(kp['riskWarning']))
    assert set(['shortTermStrong', 'reversal', 'riskWarning']) <= set(kp.keys()), kp
    assert (len(kp['shortTermStrong']) + len(kp['reversal']) + len(kp['riskWarning'])) >= 1, kp

    # 18q) #35 闭环预警扫描应逐 alert 富化 kronosInfo（技术面底座，不做候选池叠加）
    r = client.post('/api/v1/backtrace/closed-loop/scan')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    sdata5 = r.json()['data']
    assert 'kronosAnalyzed' in sdata5, sdata5
    assert sdata5['kronosAnalyzed'] >= 1, sdata5
    # 每个 alert 必须携带结构化 kronosInfo（趋势/拐点/三类概率）
    for a in sdata5['alerts']:
        ki = a.get('kronosInfo')
        assert ki and {'trend', 'inflectionPoint', 'riseProb', 'sidewayProb', 'downProb', 'volatility'} <= set(ki.keys()), (a, ki)
    print('scan(kronos) total=', sdata5['totalScanned'], 'kronosAnalyzed=', sdata5['kronosAnalyzed'])

    # 18r) #38 六层信息圈层 + 多源交叉验证（元分析层）：扫描结果应携带 crossValidationSummary，
    # 且每只 alert 携带 crossValidation（共识等级 / 可信度 / 冲突 / 谣言）。
    assert 'crossValidationSummary' in sdata5, sdata5
    cvs = sdata5['crossValidationSummary']
    assert set(cvs['layerDistribution'].keys()) == {'L0', 'L1', 'L2', 'L3', 'L4', 'L5'}, cvs
    assert set(cvs['consensusDistribution'].keys()) == {'strong', 'moderate', 'weak', 'none'}, cvs
    assert cvs['multiSourceConfirmed'] >= 1, cvs          # 沙箱多源覆盖 → 至少 1 只多源确认
    for a in sdata5['alerts']:
        cv = a.get('crossValidation')
        assert cv and {'layersHit', 'consensusLevel', 'credibilityScore', 'conflictFlag', 'rumorFlag'} <= set(cv.keys()), (a, cv)
        assert 0.0 <= cv['credibilityScore'] <= 1.0, cv
    print('cross-validation multiSourceConfirmed=', cvs['multiSourceConfirmed'],
          'consensus=', cvs['consensusDistribution'], 'conflict=', cvs['conflictAlerts'], 'rumor=', cvs['rumorAlerts'])

    # 18r2) #39 拐点预警（P2）：扫描结果应携带 inflectionSummary，且每只 alert 携带 inflectionWarning
    # （见顶/启动/情绪反转/技术背离分级 + 建议动作）。
    assert 'inflectionSummary' in sdata5, sdata5
    ifs = sdata5['inflectionSummary']
    assert set(ifs['levelDistribution'].keys()) == {'high', 'medium', 'low', 'none'}, ifs
    assert set(ifs.keys()) >= {'totalAlerts', 'typeDistribution', 'highInflectionAlerts'}, ifs
    for a in sdata5['alerts']:
        iw = a.get('inflectionWarning')
        assert iw and {'level', 'types', 'reasons', 'confidence', 'suggestedAction'} <= set(iw.keys()), (a, iw)
        assert 0.0 <= iw['confidence'] <= 1.0, iw
    print('inflection levelDist=', ifs['levelDistribution'], 'types=', ifs['typeDistribution'])

    # 18s) #38 独立端点：圈层定义 + 跨池交叉验证摘要（describe 类端点返回原始 dict，由真实 server 包装；
    # 本验证 app 无包装中间件，故直接断言原始 payload，与 overseas/community 等 describe 端点一致）
    r = client.get('/api/v1/backtrace/closed-loop/info-layers')
    assert r.status_code == 200, r.text
    il = r.json()
    assert set(il['layers'].keys()) == {'L0', 'L1', 'L2', 'L3', 'L4', 'L5'}, il
    assert il['credibilityThresholds']['singleRetailCap'] == 0.3, il
    r = client.get('/api/v1/backtrace/closed-loop/cross-validation')
    assert r.status_code == 200, r.text
    cvp = r.json()
    assert cvp['totalAlerts'] >= 1, cvp

    # 18t) #39 舆情回测（P2）：各平台情绪因子历史胜率回测报告（确定性模拟基线）。
    # 端点返回原始 dict（与 overseas/community/info-layers/cross-validation 等 describe 端点一致）。
    r = client.get('/api/v1/backtrace/closed-loop/sentiment-backtest')
    assert r.status_code == 200, r.text
    sb = r.json()
    expected_sources = {'disclosure', 'overseas', 'flash', 'community', 'wechat', 'opinion'}
    assert set(sb['bySource'].keys()) == expected_sources, sb
    for sk, m in sb['bySource'].items():
        assert 0.0 <= m['directionalWinRate'] <= 1.0, (sk, m)
        assert -1.0 <= m['ic'] <= 1.0, (sk, m)
        assert m['samples'] > 0, (sk, m)                     # 沙箱覆盖标的非空 → 样本 > 0
        assert m['reliability'] in ('高', '中', '低'), (sk, m)
        assert m['signalDirection'] in ('同向(正预测)', '反向(反向指标)', '弱相关'), (sk, m)
    assert set(sb['summary'].keys()) >= {'bestSource', 'bestIc', 'worstSource', 'worstIc', 'authoritativeAvgIc', 'retailAvgIc'}, sb
    assert sb['summary']['bestIc'] >= sb['summary']['worstIc'], sb   # 最强源 IC ≥ 最弱源
    print('sentiment-backtest best=', sb['summary']['bestSource'], 'bestIc=', sb['summary']['bestIc'],
          'worst=', sb['summary']['worstSource'], 'worstIc=', sb['summary']['worstIc'],
          'authIc=', sb['summary']['authoritativeAvgIc'], 'retailIc=', sb['summary']['retailAvgIc'])

    # 18u) #39 拐点预警摘要（独立端点，跨池不跑 run_closed_loop）
    r = client.get('/api/v1/backtrace/closed-loop/inflection-warnings')
    assert r.status_code == 200, r.text
    iwp = r.json()
    assert set(iwp['levelDistribution'].keys()) == {'high', 'medium', 'low', 'none'}, iwp
    assert iwp['totalAlerts'] >= 1, iwp
    assert set(iwp.keys()) >= {'typeDistribution', 'highInflectionAlerts'}, iwp
    print('inflection-warnings levelDist=', iwp['levelDistribution'], 'types=', iwp['typeDistribution'])

    # 19) #24 因子库累积统计（数据驱动可视化）：闭环扫描落库的归因应被因子库统计进 DB 来源
    # 19a) 累积统计端点
    r = client.get('/api/v1/backtrace/factor-library/stats')
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    st = r.json()['data']
    print('factor-library/stats preset=', st['presetCount'], 'dbAttr=', st['dbAttributionCount'],
          'minedFromDb=', st['minedFromDb'], 'reinforced=', st['reinforced'], 'total=', st['libraryTotal'])
    assert st['presetCount'] >= 8, st                         # 基线预设因子齐备
    assert st['dbAttributionCount'] >= 1, st                  # 闭环扫描已落库真实归因
    assert st['libraryTotal'] >= st['presetCount'], st       # 因子库 = 基线 + 新发现
    for k in ('presetCount', 'dbAttributionCount', 'minedFromDb', 'reinforced', 'libraryTotal'):
        assert k in st, (k, st)

    # 19b) 因子库重新沉淀：此时应能从 DB 真实归因中挖掘出新因子（闭环前 minedFromDb=0，闭环后 ≥1）
    r = client.post('/api/v1/backtrace/factor-mine', json={'recompute': True})
    assert r.status_code == 200 and r.json()['code'] == 0, r.text
    fm2 = r.json()['data']
    print('  factor-mine after scan: total=', fm2['total'], 'minedFromDb=', fm2['minedFromDb'],
          'reinforced=', fm2['reinforced'])
    assert fm2['minedFromDb'] >= 1, fm2                       # 真实归因已反哺因子库
    assert fm2['total'] >= st['presetCount'], fm2             # 库未收缩

    print('\nALL_REQUEST_DATA_OK')


if __name__ == '__main__':
    main()
