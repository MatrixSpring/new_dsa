import { useEffect, useState } from 'react';
import { backtraceApi } from '../api/backtrace';
import type {
  AgentDigResult,
  AlertScanResult,
  AttributionResult,
  AttributionSummary,
  BacktestResult,
  BacktraceNewsDoc,
  ClosedLoopResult,
  DataSourceInfo,
  DisclosureItem,
  DisclosureSourceInfo,
  OpinionItem,
  OpinionSourceInfo,
  WechatOpinionItem,
  WechatSourceInfo,
  FlashOpinionItem,
  FlashSourceInfo,
  CommunityOpinionItem,
  CommunitySourceInfo,
  OverseasNewsItem,
  OverseasSourceInfo,
  KronosSignal,
  CrossValidation,
  CrossValidationSummary,
  InfoLayers,
  SentimentBacktestReport,
  InflectionSummary,
  KronosSourceInfo,
  KronosPools,
  FactorForecastResult,
  FactorLibraryItem,
  FactorLibraryStats,
  FactorPredictResult,
  LinkageActions,
  ScanBatch,
  ScheduleConfig,
  ScreenPoolItem,
  SectorReviewResult,
} from '../types/backtrace';

const FACTOR_COLOR: Record<string, string> = {
  核心强驱动: '#34d399',
  次要催化: '#fbbf24',
  情绪炒作: '#f87171',
};

const CATEGORY_COLOR: Record<string, string> = {
  基本面事件驱动: '#34d399',
  题材情绪驱动: '#fbbf24',
  资金筹码驱动: '#60a5fa',
};

const TREND_COLOR: Record<string, string> = {
  短期脉冲: '#f87171',
  中期趋势: '#fbbf24',
  长期主升: '#34d399',
};

const PROSPERITY_COLOR: Record<string, string> = {
  景气主升: '#34d399',
  '景气上行（分化）': '#fbbf24',
  '情绪脉冲 / 板块退潮': '#f87171',
};

const VERDICT_COLOR: Record<string, string> = {
  '归因逻辑历史有效（可纳入因子库）': '#34d399',
  '历史有效性中性（建议结合其它信号）': '#fbbf24',
  '历史有效性不足（建议审慎，弱化该归因权重）': '#f87171',
};

const SIGNAL_COLOR: Record<string, string> = {
  机构调研: '#60a5fa',
  产业链异动: '#34d399',
  舆情小道消息: '#fbbf24',
  游资动向: '#f87171',
};

// 因子库 / 正向预判配色
const PREDICT_COLOR: Record<string, string> = {
  强信号: '#34d399',
  中性偏多: '#fbbf24',
  审慎: '#f87171',
};

// 因子传导 → DSA 内核：提升幅度配色
const LIFT_COLOR: Record<string, string> = {
  正向增益: '#34d399',
  基准: '#64748b',
};

// #20 自动化闭环预警扫描：预警级别配色
const ALERT_LEVEL_COLOR: Record<string, string> = {
  '强信号·重点关注': '#34d399',
  '中性·持续观察': '#fbbf24',
  '弱信号·低关注': '#64748b',
};

const SECTORS = ['新能源', '半导体', 'AI'];

/** 大涨个股反向新闻归因回溯中心（DSA-BACKTRACE-V1.0）：筛选 → 回溯 → 归因 → 联动 + 板块复盘 + 回测校验 + Agent 深挖 + 因子库沉淀 + 因子传导内核。 */
const BacktracePage: React.FC<{
  seed?: {
    pool: ScreenPoolItem[];
    attribution: AttributionResult | null;
    news: BacktraceNewsDoc[];
    linkage: LinkageActions | null;
    sectorReview?: SectorReviewResult | null;
    attributionList?: AttributionSummary[];
    backtest?: BacktestResult | null;
    agentDig?: AgentDigResult | null;
    factorLibrary?: FactorLibraryItem[] | null;
    factorStats?: FactorLibraryStats | null;
    factorPredict?: FactorPredictResult | null;
    factorForecast?: FactorForecastResult | null;
    closedLoop?: ClosedLoopResult | null;
    alertScan?: AlertScanResult | null;
    scanSchedule?: ScheduleConfig | null;
    scanHistory?: ScanBatch[] | null;
    dataSource?: DataSourceInfo | null;
    disclosures?: DisclosureItem[] | null;
    disclosureSource?: DisclosureSourceInfo | null;
    opinions?: OpinionItem[] | null;
    opinionSource?: OpinionSourceInfo | null;
    wechats?: WechatOpinionItem[] | null;
    wechatSource?: WechatSourceInfo | null;
    flashes?: FlashOpinionItem[] | null;
    flashSource?: FlashSourceInfo | null;
    kronosSource?: KronosSourceInfo | null;
    kronosPools?: KronosPools | null;
  };
  initialTab?: 'stock' | 'sector' | 'backtest' | 'agent' | 'factor' | 'propagate' | 'loop' | 'alert';
}> = ({ seed, initialTab }) => {
  const hasBacktest = Boolean(seed?.backtest);
  const hasAgent = Boolean(seed?.agentDig);
  const hasFactor = Boolean(seed?.factorLibrary);
  const hasPropagate = Boolean(seed?.factorForecast);
  const hasAlert = Boolean(seed?.alertScan);
  const [tab, setTab] = useState<'stock' | 'sector' | 'backtest' | 'agent' | 'factor' | 'propagate' | 'loop' | 'alert'>(
    initialTab ?? (hasAlert ? 'alert' : hasPropagate ? 'propagate' : hasFactor ? 'factor' : hasAgent ? 'agent' : hasBacktest ? 'backtest' : seed?.sectorReview ? 'sector' : 'stock')
  );

  // —— 个股复盘态 ——
  const [pool, setPool] = useState<ScreenPoolItem[]>(seed?.pool ?? []);
  const [selected, setSelected] = useState<ScreenPoolItem | null>(seed?.pool?.[0] ?? null);
  const [attribution, setAttribution] = useState<AttributionResult | null>(seed?.attribution ?? null);
  const [news, setNews] = useState<BacktraceNewsDoc[]>(seed?.news ?? []);
  const [linkage, setLinkage] = useState<LinkageActions | null>(seed?.linkage ?? null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // —— 板块复盘态 ——
  const [sector, setSector] = useState<string>(seed?.sectorReview?.sector ?? '新能源');
  const [sectorReview, setSectorReview] = useState<SectorReviewResult | null>(seed?.sectorReview ?? null);

  // —— 回测校验态（§3.7）——
  const [attrList, setAttrList] = useState<AttributionSummary[]>(seed?.attributionList ?? []);
  const [selAttrId, setSelAttrId] = useState<number | null>(seed?.backtest?.attributionId ?? null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(seed?.backtest ?? null);

  // —— Agent 自主深挖态（增强模块）——
  const [agentCode, setAgentCode] = useState<string>(seed?.agentDig?.stockCode ?? seed?.pool?.[0]?.stockCode ?? '');
  const [agentDig, setAgentDig] = useState<AgentDigResult | null>(seed?.agentDig ?? null);

  // —— 高频上涨因子沉淀态（增强模块）——
  const [factorLibrary, setFactorLibrary] = useState<FactorLibraryItem[]>(seed?.factorLibrary ?? []);
  const [factorStats, setFactorStats] = useState<FactorLibraryStats | null>(seed?.factorStats ?? null);
  const [factorPredict, setFactorPredict] = useState<FactorPredictResult | null>(seed?.factorPredict ?? null);
  const [factorInput, setFactorInput] = useState<string>(
    seed?.agentDig ? Object.keys(seed.agentDig.typeDistribution).join('、') : '机构调研、产业链异动'
  );

  // —— 因子库 → DSA 内核正向传导态（闭环增强，内核零改动）——
  const [propChain, setPropChain] = useState<string>(seed?.factorForecast?.chainId ?? 'lithium');
  const [propNode, setPropNode] = useState<string>(seed?.factorForecast?.shockNode ?? '锂矿');
  const [propMag, setPropMag] = useState<number>(seed?.factorForecast?.baseMagnitude ?? 0.3);
  const [factorForecast, setFactorForecast] = useState<FactorForecastResult | null>(seed?.factorForecast ?? null);

  // —— 一键闭环态（收尾闭环：深挖 → 预判 → 内核传导）——
  const [loopCode, setLoopCode] = useState<string>(seed?.closedLoop?.stockCode ?? seed?.pool?.[0]?.stockCode ?? '');
  const [closedLoop, setClosedLoop] = useState<ClosedLoopResult | null>(seed?.closedLoop ?? null);

  // —— 自动化闭环预警扫描态（#20：批量跑闭环并分级预警）——
  const [alertScan, setAlertScan] = useState<AlertScanResult | null>(seed?.alertScan ?? null);
  // —— 闭环预警调度态（#21：定时/事件触发 + 批次历史）——
  const [scanSchedule, setScanSchedule] = useState<ScheduleConfig | null>(seed?.scanSchedule ?? null);
  const [scanHistory, setScanHistory] = useState<ScanBatch[]>(seed?.scanHistory ?? []);
  const [lastBatch, setLastBatch] = useState<ScanBatch | null>(null);
  // —— 可插拔数据源态（#23：实时 AkShare / 模拟，前端标识）——
  const [dataSource, setDataSource] = useState<DataSourceInfo | null>(seed?.dataSource ?? null);
  // —— 可插拔公开披露源态（#25：cninfo / 财报 / 研报，前端标识与面板）——
  const [disclosureSource, setDisclosureSource] = useState<DisclosureSourceInfo | null>(seed?.disclosureSource ?? null);
  const [disclosures, setDisclosures] = useState<DisclosureItem[]>(seed?.disclosures ?? []);
  const [opinionSource, setOpinionSource] = useState<OpinionSourceInfo | null>(seed?.opinionSource ?? null);
  const [opinions, setOpinions] = useState<OpinionItem[]>(seed?.opinions ?? []);
  const [wechatSource, setWechatSource] = useState<WechatSourceInfo | null>(seed?.wechatSource ?? null);
  const [wechats, setWechats] = useState<WechatOpinionItem[]>(seed?.wechats ?? []);
  const [flashSource, setFlashSource] = useState<FlashSourceInfo | null>(seed?.flashSource ?? null);
  const [flashes, setFlashes] = useState<FlashOpinionItem[]>(seed?.flashes ?? []);
  const [communitySource, setCommunitySource] = useState<CommunitySourceInfo | null>(seed?.communitySource ?? null);
  const [communities, setCommunities] = useState<CommunityOpinionItem[]>(seed?.communities ?? []);
  const [overseasSource, setOverseasSource] = useState<OverseasSourceInfo | null>(seed?.overseasSource ?? null);
  const [overseas, setOverseas] = useState<OverseasNewsItem[]>(seed?.overseas ?? []);
  const [infoLayers, setInfoLayers] = useState<InfoLayers | null>(seed?.infoLayers ?? null); // #38 六层信息圈层定义
  const [crossValidationSummary, setCrossValidationSummary] = useState<CrossValidationSummary | null>(
    seed?.crossValidationSummary ?? alertScan?.crossValidationSummary ?? null,
  ); // #38 扫描级交叉验证摘要
  // —— #39 舆情回测 + 拐点预警（P2）：情绪因子历史胜率回测报告 + 扫描级拐点摘要 ——
  const [sentimentBacktest, setSentimentBacktest] = useState<SentimentBacktestReport | null>(seed?.sentimentBacktest ?? null);
  const [inflectionSummary, setInflectionSummary] = useState<InflectionSummary | null>(
    seed?.inflectionSummary ?? alertScan?.inflectionSummary ?? null,
  );
  const [kronosSource, setKronosSource] = useState<KronosSourceInfo | null>(seed?.kronosSource ?? null);
  const [kronosPools, setKronosPools] = useState<KronosPools | null>(seed?.kronosPools ?? null);

  const loadPool = () => {
    backtraceApi
      .screenPool()
      .then((r) => setPool(r.data?.items ?? []))
      .catch(() => setErr('回溯池加载失败'));
  };

  const loadAttrList = () => {
    backtraceApi
      .attributions()
      .then((r) => {
        const items = r.data?.items ?? [];
        setAttrList(items);
        if (selAttrId === null && items.length > 0) setSelAttrId(items[0].attributionId);
      })
      .catch(() => setErr('归因列表加载失败'));
  };

  useEffect(() => {
    if (seed) {
      if (hasBacktest && selAttrId === null) setSelAttrId(seed.backtest?.attributionId ?? null);
      return;
    }
    loadPool();
    loadAttrList();
    backtraceApi
      .getSchedule()
      .then((r) => setScanSchedule(r.data ?? null))
      .catch(() => setErr('调度配置加载失败'));
    backtraceApi
      .scanHistory()
      .then((r) => setScanHistory(r.data?.items ?? []))
      .catch(() => setErr('扫描历史加载失败'));
    backtraceApi
      .dataSource()
      .then((r) => setDataSource(r.data ?? null))
      .catch(() => setErr('数据源信息加载失败'));
    backtraceApi
      .factorLibraryStats()
      .then((r) => setFactorStats(r.data ?? null))
      .catch(() => setErr('因子库统计加载失败'));
    backtraceApi
      .disclosureSource()
      .then((r) => setDisclosureSource(r.data ?? null))
      .catch(() => setErr('公开披露源信息加载失败'));
    backtraceApi
      .disclosures()
      .then((r) => setDisclosures(r.data?.items ?? []))
      .catch(() => setErr('披露事件池加载失败'));
    backtraceApi
      .opinionSource()
      .then((r) => setOpinionSource(r.data ?? null))
      .catch(() => setErr('公开舆情源信息加载失败'));
    backtraceApi
      .opinions()
      .then((r) => setOpinions(r.data?.items ?? []))
      .catch(() => setErr('舆情事件池加载失败'));
    backtraceApi
      .wechatSource()
      .then((r) => setWechatSource(r.data ?? null))
      .catch(() => setErr('微信舆情源信息加载失败'));
    backtraceApi
      .wechats()
      .then((r) => setWechats(r.data?.items ?? []))
      .catch(() => setErr('微信舆情事件池加载失败'));
    backtraceApi
      .flashSource()
      .then((r) => setFlashSource(r.data ?? null))
      .catch(() => setErr('短线快讯源信息加载失败'));
    backtraceApi
      .flashes()
      .then((r) => setFlashes(r.data?.items ?? []))
      .catch(() => setErr('快讯事件池加载失败'));
    backtraceApi
      .communitySource()
      .then((r) => setCommunitySource(r.data ?? null))
      .catch(() => setErr('深度社区舆情源信息加载失败'));
    backtraceApi
      .communities()
      .then((r) => setCommunities(r.data?.items ?? []))
      .catch(() => setErr('社区讨论事件池加载失败'));
    backtraceApi
      .overseasSource()
      .then((r) => setOverseasSource(r.data ?? null))
      .catch(() => setErr('海外权威舆情源信息加载失败'));
    backtraceApi
      .overseas()
      .then((r) => setOverseas(r.data?.items ?? []))
      .catch(() => setErr('海外权威资讯事件池加载失败'));
    backtraceApi
      .kronosSource()
      .then((r) => setKronosSource(r.data ?? null))
      .catch(() => setErr('Kronos 技术面底座信息加载失败'));
    backtraceApi
      .kronosPools()
      .then((r) => setKronosPools(r.data ?? null))
      .catch(() => setErr('Kronos 选股池加载失败'));
    backtraceApi
      .infoLayers()
      .then((r) => setInfoLayers(r.data ?? null))
      .catch(() => setErr('六层信息圈层定义加载失败'));
    backtraceApi
      .sentimentBacktest()
      .then((r) => setSentimentBacktest(r.data ?? null))
      .catch(() => setErr('舆情回测报告加载失败'));
    backtraceApi
      .inflectionWarnings()
      .then((r) => setInflectionSummary(r.data ?? null))
      .catch(() => setErr('拐点预警摘要加载失败'));
  }, [seed]);

  const runAttribute = (item: ScreenPoolItem) => {
    setSelected(item);
    setBusy(item.stockCode);
    setMsg(null);
    setErr(null);
    setLinkage(null);
    backtraceApi
      .attribute(item.stockCode)
      .then((r) => {
        setAttribution(r.data ?? null);
        setMsg(`已对 ${item.stockName} 完成反向归因（${r.data?.driveCategory ?? ''}）`);
      })
      .catch(() => setErr('归因失败'))
      .finally(() => setBusy(null));
  };

  const runLink = () => {
    if (!attribution?.attributionId) return;
    setBusy('link');
    backtraceApi
      .link(attribution.attributionId)
      .then((r) => {
        setLinkage(r.data?.actions ?? null);
        setMsg('已联动 DSA 系统：事件库入库 / 权重修正 / 预测重算 / 案例沉淀');
      })
      .catch(() => setErr('联动失败'))
      .finally(() => setBusy(null));
  };

  const runSectorReview = () => {
    setBusy('sector');
    setErr(null);
    backtraceApi
      .sectorReview(sector)
      .then((r) => {
        setSectorReview(r.data ?? null);
        setMsg(`已完成「${sector}」板块批量复盘（${r.data?.prosperity ?? ''}）`);
      })
      .catch(() => setErr('板块复盘失败'))
      .finally(() => setBusy(null));
  };

  const runBacktest = () => {
    if (selAttrId === null) {
      setErr('请先选择一条归因记录');
      return;
    }
    setBusy('backtest');
    setErr(null);
    backtraceApi
      .backtest(selAttrId)
      .then((r) => {
        setBacktest(r.data ?? null);
        setMsg(`已完成归因回测校验（历史胜率 ${(r.data?.winRate * 100).toFixed(0)}%，置信度 ${(r.data?.confidenceAdjusted * 100).toFixed(0)}%）`);
      })
      .catch(() => setErr('回测校验失败'))
      .finally(() => setBusy(null));
  };

  const runAgentDig = () => {
    if (!agentCode) {
      setErr('请先选择一只深挖标的');
      return;
    }
    setBusy('agent');
    setErr(null);
    backtraceApi
      .agentDig(agentCode)
      .then((r) => {
        setAgentDig(r.data ?? null);
        setMsg(`Agent 已完成深挖（${r.data?.stockName ?? agentCode}）：发现 ${r.data?.signalCount} 条隐藏信号，其中 ${r.data?.earlyCount} 条为小众早期信号`);
      })
      .catch(() => setErr('Agent 深挖失败'))
      .finally(() => setBusy(null));
  };

  const runFactorMine = () => {
    setBusy('factor-mine');
    setErr(null);
    backtraceApi
      .factorMine()
      .then((r) => {
        setFactorLibrary(r.data?.items ?? []);
        setMsg(`已完成高频上涨因子自动沉淀：沉淀因子 ${r.data?.total} 条（DB 新增 ${r.data?.minedFromDb}，强化 ${r.data?.reinforced}）`);
      })
      .catch(() => setErr('因子沉淀失败'))
      .finally(() => setBusy(null));
  };

  const runFactorPredict = () => {
    const detected = factorInput.split(/[，,、\s]+/).map((x) => x.trim()).filter(Boolean);
    if (detected.length === 0) {
      setErr('请至少输入一个早期信号');
      return;
    }
    setBusy('factor-predict');
    setErr(null);
    backtraceApi
      .factorPredict(detected, agentCode || undefined)
      .then((r) => {
        setFactorPredict(r.data ?? null);
        setMsg(`正向预判完成：命中因子 ${(r.data?.matched ?? []).length} 个，预测上涨概率 ${((r.data?.predictedProb ?? 0) * 100).toFixed(0)}%`);
      })
      .catch(() => setErr('正向预判失败'))
      .finally(() => setBusy(null));
  };

  const runFactorForecast = () => {
    if (!propChain) {
      setErr('请选择产业链');
      return;
    }
    setBusy('propagate');
    setErr(null);
    backtraceApi
      .factorForecast({
        chainId: propChain,
        shock: { node: propNode, magnitude: propMag, kind: 'demand' },
        topN: 6,
        minConfidence: 0.6,
      })
      .then((r) => {
        setFactorForecast(r.data ?? null);
        setMsg(`因子传导桥接完成：注入 ${r.data?.factors?.length ?? 0} 个沉淀因子，冲击幅度增益 +${((r.data?.boost ?? 0) * 100).toFixed(1)}%`);
      })
      .catch(() => setErr('因子传导桥接失败'))
      .finally(() => setBusy(null));
  };

  const runClosedLoop = () => {
    if (!loopCode) {
      setErr('请先选择一只闭环标的');
      return;
    }
    setBusy('loop');
    setErr(null);
    backtraceApi
      .closedLoop(loopCode)
      .then((r) => {
        setClosedLoop(r.data ?? null);
        const d = r.data;
        setMsg(
          `一键闭环完成：${d?.dig?.signalCount ?? 0} 条隐藏信号 → 预测上涨概率 ${((d?.predict?.predictedProb ?? 0) * 100).toFixed(0)}% → 内核传导增益 +${((d?.propagate?.boost ?? 0) * 100).toFixed(1)}%`
        );
      })
      .catch(() => setErr('一键闭环失败'))
      .finally(() => setBusy(null));
  };

  const runAlertScan = () => {
    setBusy('alert-scan');
    setErr(null);
    backtraceApi
      .closedLoopScanRun('manual')
      .then((r) => {
        const d = r.data;
        setAlertScan(d?.scan ?? null);
        setLastBatch(d?.batch ?? null);
        setScanHistory((prev) => [d?.batch ?? ({} as ScanBatch), ...prev].filter(Boolean));
        const a = d?.scan;
        const strong = (a?.alerts ?? []).filter((x) => x.level.startsWith('强信号')).length;
        setMsg(
          `闭环预警扫描完成（手动触发）：扫描 ${a?.totalScanned ?? 0} 只大涨标的，其中 ${strong} 只「强信号·重点关注」（批次 ${a?.scanBatch ?? '-'}）`
        );
      })
      .catch(() => setErr('闭环预警扫描失败'))
      .finally(() => setBusy(null));
  };

  const g = attribution?.guardrails;

  return (
    <div style={{ padding: 24, color: '#e5e7eb', maxWidth: 1180, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>大涨个股反向新闻归因回溯中心</h1>
      <p style={{ color: '#94a3b8', marginTop: 0, marginBottom: 16 }}>
        DSA-BACKTRACE-V1.0 · 正向事件预判 + 反向涨跌复盘双引擎 · 外挂微服务，不改动 DSA 内核
      </p>

      {/* Tab 切换 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <TabBtn active={tab === 'stock'} onClick={() => setTab('stock')} label="① 个股反向归因" />
        <TabBtn active={tab === 'sector'} onClick={() => setTab('sector')} label="② 批量板块复盘 (§3.6)" />
        <TabBtn active={tab === 'backtest'} onClick={() => setTab('backtest')} label="③ 归因回测校验 (§3.7)" />
        <TabBtn active={tab === 'agent'} onClick={() => setTab('agent')} label="④ Agent 深挖信号" />
        <TabBtn active={tab === 'factor'} onClick={() => setTab('factor')} label="⑤ 上涨因子库" />
        <TabBtn active={tab === 'propagate'} onClick={() => setTab('propagate')} label="⑥ 因子传导 (内核)" />
        <TabBtn active={tab === 'loop'} onClick={() => setTab('loop')} label="⑦ 一键闭环" />
        <TabBtn active={tab === 'alert'} onClick={() => setTab('alert')} label="⑧ 自动化闭环预警" />
      </div>

      {msg && <div style={{ color: '#34d399', marginBottom: 10 }}>{msg}</div>}
      {err && <div style={{ color: '#f87171', marginBottom: 10 }}>{err}</div>}

      {tab === 'stock' && (
        <StockReviewTab
          pool={pool}
          selected={selected}
          attribution={attribution}
          news={news}
          linkage={linkage}
          busy={busy}
          guardrails={g}
          onAttribute={runAttribute}
          onLink={runLink}
        />
      )}

      {tab === 'sector' && (
        <SectorReviewTab
          sectors={SECTORS}
          sector={sector}
          sectorReview={sectorReview}
          busy={busy}
          onSectorChange={setSector}
          onRun={runSectorReview}
        />
      )}

      {tab === 'backtest' && (
        <BacktestTab
          attrList={attrList}
          selAttrId={selAttrId}
          backtest={backtest}
          busy={busy}
          onSelChange={setSelAttrId}
          onRun={runBacktest}
        />
      )}

      {tab === 'agent' && (
        <AgentDigTab
          pool={pool}
          agentCode={agentCode}
          agentDig={agentDig}
          busy={busy}
          onCodeChange={setAgentCode}
          onRun={runAgentDig}
        />
      )}

      {tab === 'factor' && (
        <FactorLibraryTab
          library={factorLibrary}
          factorStats={factorStats}
          predict={factorPredict}
          factorInput={factorInput}
          busy={busy}
          onInputChange={setFactorInput}
          onMine={runFactorMine}
          onPredict={runFactorPredict}
        />
      )}

      {tab === 'propagate' && (
        <FactorPropagateTab
          chain={propChain}
          node={propNode}
          magnitude={propMag}
          forecast={factorForecast}
          busy={busy}
          onChainChange={setPropChain}
          onNodeChange={setPropNode}
          onMagChange={setPropMag}
          onRun={runFactorForecast}
        />
      )}

      {tab === 'loop' && (
        <ClosedLoopTab
          pool={pool}
          loopCode={loopCode}
          closedLoop={closedLoop}
          busy={busy}
          onCodeChange={setLoopCode}
          onRun={runClosedLoop}
        />
      )}

      {tab === 'alert' && (
        <ScanAlertTab
          alertScan={alertScan}
          scanSchedule={scanSchedule}
          scanHistory={scanHistory}
          dataSource={dataSource}
          disclosureSource={disclosureSource}
          disclosures={disclosures}
          opinionSource={opinionSource}
          opinions={opinions}
          wechatSource={wechatSource}
          wechats={wechats}
          flashSource={flashSource}
          flashes={flashes}
          communitySource={communitySource}
          communities={communities}
          overseasSource={overseasSource}
          overseas={overseas}
          infoLayers={infoLayers}
          crossValidationSummary={crossValidationSummary}
          sentimentBacktest={sentimentBacktest}
          inflectionSummary={inflectionSummary}
          kronosSource={kronosSource}
          kronosPools={kronosPools}
          busy={busy}
          onRun={runAlertScan}
        />
      )}
    </div>
  );
};

// ============================ 个股复盘 Tab ============================
const StockReviewTab: React.FC<{
  pool: ScreenPoolItem[];
  selected: ScreenPoolItem | null;
  attribution: AttributionResult | null;
  news: BacktraceNewsDoc[];
  linkage: LinkageActions | null;
  busy: string | null;
  guardrails?: AttributionResult['guardrails'];
  onAttribute: (item: ScreenPoolItem) => void;
  onLink: () => void;
}> = ({ pool, selected, attribution, linkage, busy, guardrails: g, onAttribute, onLink }) => {
  return (
    <>
      {/* 防幻觉三护栏状态条 */}
      <div
        style={{
          display: 'flex', flexWrap: 'wrap', gap: 10, padding: 12, background: '#0f172a',
          border: '1px solid #1e293b', borderRadius: 10, marginBottom: 18,
        }}
      >
        <Chip ok={g?.timeFiltered ?? false} label="时间约束：仅采用拉升前资讯" />
        <Chip ok={g?.minSourcesEnforced ?? false} label="多源交叉验证：核心驱动≥2源" />
        <Chip ok={g?.weightsSum === 100} label={`权重合计校验：${g?.weightsSum ?? 0}/100`} />
        <Chip ok={Boolean(g?.excludedPostRise)} label="事后新闻已剔除" />
      </div>

      {/* 模块 1：大涨回溯池 */}
      <SectionTitle title="① 每日大涨回溯池（涨幅≥5% / 涨停 / 放量大涨）" />
      <div style={{ overflowX: 'auto', marginBottom: 20 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
              <th style={th}>名称</th>
              <th style={th}>代码</th>
              <th style={th}>当日涨幅</th>
              <th style={th}>行业</th>
              <th style={th}>类型</th>
              <th style={th}>连涨</th>
              <th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {pool.map((p) => (
              <tr key={p.id} style={{ borderTop: '1px solid #1e293b' }}>
                <td style={td}>{p.stockName}</td>
                <td style={td}>{p.stockCode}</td>
                <td style={{ ...td, color: '#f87171', fontWeight: 600 }}>+{p.dailyGain.toFixed(2)}%</td>
                <td style={td}>{p.industry}</td>
                <td style={td}>{p.gainType}</td>
                <td style={td}>{p.consecutiveDays}日</td>
                <td style={td}>
                  <button onClick={() => onAttribute(p)} disabled={busy === p.stockCode} style={btn(busy === p.stockCode)}>
                    {busy === p.stockCode ? '归因中…' : '反向归因'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 模块 3+4：归因结果 */}
      {attribution && (
        <>
          <SectionTitle title={`② 反向归因结果 · ${attribution.stockName}（${attribution.stockCode}）`} />
          <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
            <Badge color={CATEGORY_COLOR[attribution.driveCategory] ?? '#94a3b8'} text={`驱动分类：${attribution.driveCategory}`} />
            <Badge color={TREND_COLOR[attribution.trendPersistenceJudge] ?? '#94a3b8'} text={`趋势判断：${attribution.trendPersistenceJudge}`} />
            <Badge color="#60a5fa" text={`引擎：${attribution.engine}`} />
          </div>

          <div style={{ marginBottom: 16 }}>
            {attribution.drivingFactor.map((f, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 6, background: (FACTOR_COLOR[f.factorType] ?? '#94a3b8') + '22', color: FACTOR_COLOR[f.factorType] ?? '#94a3b8' }}>
                    {f.factorType}
                  </span>
                  <span style={{ color: '#e5e7eb', fontWeight: 600 }}>权重 {f.weight}% · 置信 {(f.confidence * 100).toFixed(0)}%</span>
                </div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 4, marginTop: 8, marginBottom: 8 }}>
                  <div style={{ width: `${f.weight}%`, height: '100%', background: FACTOR_COLOR[f.factorType] ?? '#94a3b8', borderRadius: 4 }} />
                </div>
                <div style={{ fontSize: 13, color: '#e5e7eb' }}>{f.content}</div>
                <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 6 }}>来源：{f.source}</div>
                <div style={{ fontSize: 12, color: '#fbbf24', marginTop: 4 }}>隐藏约束 / 远期风险：{f.hiddenConstraint}</div>
              </div>
            ))}
          </div>

          <SectionTitle title="③ 相似历史行情对标" />
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            {attribution.similarHistoryCase.map((c, i) => (
              <div key={i} style={{ flex: 1, minWidth: 260, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12 }}>
                <div style={{ color: '#60a5fa', fontSize: 12 }}>{c.caseTime}</div>
                <div style={{ fontSize: 13, color: '#e5e7eb', margin: '4px 0' }}>{c.event}</div>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>后续：{c.postTrend}</div>
              </div>
            ))}
          </div>

          <SectionTitle title="④ DSA 模型参数调整建议" />
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#e5e7eb', marginBottom: 16 }}>
            {attribution.suggestAdjust}
          </div>

          <button onClick={onLink} disabled={busy === 'link'} style={{ ...btn(busy === 'link'), background: '#2563eb' }}>
            {busy === 'link' ? '联动中…' : '联动 DSA 系统（事件库 / 权重 / 预测重算）'}
          </button>

          {linkage && (
            <div style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Chip ok={linkage.eventLibraryAdded} label="事件库入库" />
              <Chip ok={linkage.forecastRecomputeTriggered} label="四周期预测重算" />
              <Chip ok={linkage.caseBanked} label="高置信案例沉淀" />
              <span style={{ color: '#94a3b8', fontSize: 12, alignSelf: 'center' }}>
                基本面权重 Δ+{((linkage.fundamentalWeightDelta ?? 0) * 100).toFixed(0)}% · 产业链系数 Δ+{((linkage.chainCoeffDelta ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </>
      )}
    </>
  );
};

// ============================ 板块复盘 Tab (§3.6) ============================
const SectorReviewTab: React.FC<{
  sectors: string[];
  sector: string;
  sectorReview: SectorReviewResult | null;
  busy: string | null;
  onSectorChange: (s: string) => void;
  onRun: () => void;
}> = ({ sectors, sector, sectorReview, busy, onSectorChange, onRun }) => {
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>选择板块：</span>
        <select
          value={sector}
          onChange={(e) => onSectorChange(e.target.value)}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13 }}
        >
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button onClick={onRun} disabled={busy === 'sector'} style={{ ...btn(busy === 'sector'), background: '#2563eb' }}>
          {busy === 'sector' ? '复盘计算中…' : '运行板块批量复盘'}
        </button>
      </div>

      {!sectorReview && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          选择板块并点击「运行板块批量复盘」，系统将批量回溯板块内个股的共同前置事件，给出板块景气判断、轮动逻辑与上下游传导链。
        </div>
      )}

      {sectorReview && (
        <>
          {/* 板块景气判断 */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Badge color={PROSPERITY_COLOR[sectorReview.prosperity] ?? '#94a3b8'} text={`板块景气：${sectorReview.prosperity}`} />
            <Badge color="#60a5fa" text={`成分股：${sectorReview.memberCount} 只`} />
            <Badge color="#a78bfa" text={`强势占比：${sectorReview.aggregate.strongRate}%`} />
            <Badge color="#a78bfa" text={`平均核心权重：${sectorReview.aggregate.avgCoreWeight}`} />
          </div>

          {/* 轮动逻辑 */}
          <SectionTitle title="板块轮动逻辑" />
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#e5e7eb', marginBottom: 16 }}>
            {sectorReview.rotationLogic}
          </div>

          {/* 上下游传导链 */}
          <SectionTitle title="上下游传导链" />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
            {sectorReview.conductionChain.map((node, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '6px 12px', fontSize: 13, color: '#e5e7eb' }}>{node}</span>
                {i < sectorReview.conductionChain.length - 1 && <span style={{ color: '#64748b' }}>→</span>}
              </span>
            ))}
          </div>

          {/* 共同前置事件分布 */}
          <SectionTitle title="共同前置事件分布（板块集体大涨共性催化）" />
          <div style={{ marginBottom: 16 }}>
            {sectorReview.commonDrivers.map((d, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb' }}>
                  <span>{d.driver}</span>
                  <span style={{ color: '#94a3b8' }}>{d.hitStocks} 只命中 · {d.share}%</span>
                </div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 4, marginTop: 6 }}>
                  <div style={{ width: `${d.share}%`, height: '100%', background: '#34d399', borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>

          {/* 个股归因画像 */}
          <SectionTitle title="板块内个股归因画像" />
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>名称</th>
                  <th style={th}>代码</th>
                  <th style={th}>涨幅</th>
                  <th style={th}>类型</th>
                  <th style={th}>驱动分类</th>
                  <th style={th}>趋势</th>
                  <th style={th}>核心驱动</th>
                </tr>
              </thead>
              <tbody>
                {sectorReview.perStock.map((p) => (
                  <tr key={p.stockCode} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{p.stockName}</td>
                    <td style={td}>{p.stockCode}</td>
                    <td style={{ ...td, color: '#f87171', fontWeight: 600 }}>+{p.dailyGain.toFixed(2)}%</td>
                    <td style={td}>{p.gainType}</td>
                    <td style={td}><Badge color={CATEGORY_COLOR[p.driveCategory] ?? '#94a3b8'} text={p.driveCategory} /></td>
                    <td style={td}><Badge color={TREND_COLOR[p.trendJudge] ?? '#94a3b8'} text={p.trendJudge} /></td>
                    <td style={{ ...td, maxWidth: 320 }}>{p.topDriver}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
};

// ============================ 归因回测校验 Tab (§3.7) ============================
const BacktestTab: React.FC<{
  attrList: AttributionSummary[];
  selAttrId: number | null;
  backtest: BacktestResult | null;
  busy: string | null;
  onSelChange: (id: number) => void;
  onRun: () => void;
}> = ({ attrList, selAttrId, backtest, busy, onSelChange, onRun }) => {
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>选择归因记录：</span>
        <select
          value={selAttrId ?? ''}
          onChange={(e) => onSelChange(Number(e.target.value))}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13, minWidth: 260 }}
        >
          {attrList.length === 0 && <option value="">（暂无归因记录）</option>}
          {attrList.map((a) => (
            <option key={a.attributionId} value={a.attributionId}>
              #{a.attributionId} · {a.stockName}（{a.stockCode}）· {a.driveCategory}
            </option>
          ))}
        </select>
        <button onClick={onRun} disabled={busy === 'backtest' || selAttrId === null} style={{ ...btn(busy === 'backtest'), background: '#2563eb' }}>
          {busy === 'backtest' ? '回测计算中…' : '运行归因回测校验'}
        </button>
      </div>

      {!backtest && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          选择一条归因记录并点击「运行归因回测校验」，系统将把该次归因逻辑放入历史同类行情回测，统计历史胜率、平均涨幅与期望收益，并据此反向修正置信度，规避事后强行归因。
        </div>
      )}

      {backtest && (
        <>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Badge color={VERDICT_COLOR[backtest.verdict] ?? '#94a3b8'} text={`有效性判定：${backtest.verdict}`} />
            <Badge color="#60a5fa" text={`历史样本：${backtest.samples} 例`} />
            <Badge color="#a78bfa" text={`驱动分类：${backtest.driveCategory ?? '—'}`} />
          </div>

          {/* 核心指标卡 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 18 }}>
            <Metric label="历史胜率" value={`${(backtest.winRate * 100).toFixed(1)}%`} color="#34d399" />
            <Metric label="平均 1 周涨幅" value={`${backtest.avgGain1w >= 0 ? '+' : ''}${backtest.avgGain1w.toFixed(2)}%`} color="#34d399" />
            <Metric label="平均 1 月涨幅" value={`${backtest.avgGain1m >= 0 ? '+' : ''}${backtest.avgGain1m.toFixed(2)}%`} color="#34d399" />
            <Metric label="平均 1 月回撤" value={`${backtest.avgLoss1m.toFixed(2)}%`} color="#f87171" />
            <Metric label="期望 1 月净收益" value={`${backtest.expectancy1m >= 0 ? '+' : ''}${backtest.expectancy1m.toFixed(2)}%`} color={backtest.expectancy1m >= 0 ? '#34d399' : '#f87171'} />
          </div>

          {/* 置信度修正 */}
          <SectionTitle title="置信度回测修正（以历史胜率校准归因原置信度）" />
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Metric label="归因原置信度" value={`${(backtest.confidenceRaw * 100).toFixed(0)}%`} color="#94a3b8" />
            <span style={{ color: '#64748b', fontSize: 20 }}>→</span>
            <Metric label="回测修正后" value={`${(backtest.confidenceAdjusted * 100).toFixed(0)}%`} color="#60a5fa" />
            <Badge color="#fbbf24" text={backtest.adjustment} />
          </div>

          {/* 匹配的历史样本桶 */}
          <SectionTitle title="驱动因子 → 历史样本桶匹配明细" />
          <div style={{ overflowX: 'auto', marginBottom: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>驱动因子</th>
                  <th style={th}>历史样本桶</th>
                  <th style={th}>权重</th>
                  <th style={th}>桶胜率</th>
                  <th style={th}>桶均 1 月涨幅</th>
                  <th style={th}>样本量</th>
                </tr>
              </thead>
              <tbody>
                {backtest.matchedBuckets.map((b, i) => (
                  <tr key={i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={{ ...td, maxWidth: 300 }}>{b.factor}</td>
                    <td style={td}>{b.bucket}</td>
                    <td style={td}>{b.weight}%</td>
                    <td style={{ ...td, color: '#34d399' }}>{(b.winRate * 100).toFixed(1)}%</td>
                    <td style={{ ...td, color: '#34d399' }}>+{b.avgGain1m.toFixed(2)}%</td>
                    <td style={td}>{b.samples}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
};

// ============================ Agent 自主深挖 Tab（增强模块） ============================
const AgentDigTab: React.FC<{
  pool: ScreenPoolItem[];
  agentCode: string;
  agentDig: AgentDigResult | null;
  busy: string | null;
  onCodeChange: (code: string) => void;
  onRun: () => void;
}> = ({ pool, agentCode, agentDig, busy, onCodeChange, onRun }) => {
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>深挖标的：</span>
        <select
          value={agentCode}
          onChange={(e) => onCodeChange(e.target.value)}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13, minWidth: 200 }}
        >
          {pool.length === 0 && <option value="">（暂无标的）</option>}
          {pool.map((p) => (
            <option key={p.stockCode} value={p.stockCode}>
              {p.stockName}（{p.stockCode}）
            </option>
          ))}
        </select>
        <button onClick={onRun} disabled={busy === 'agent'} style={{ ...btn(busy === 'agent'), background: '#2563eb' }}>
          {busy === 'agent' ? 'Agent 深挖中…' : '运行 Agent 自主深挖'}
        </button>
      </div>

      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 18 }}>
        Agent 在反向回溯基础上，主动扫描该股拉升前窗口内的隐藏早期信号（机构调研 / 产业链异动 / 舆情小道消息 / 游资动向），
        按「时间临近度 + 来源可信度 + 相关度」综合打分，标记小众早期信号，反哺 §3.4 归因的早期佐证强度。全部为数学打分，不依赖 LLM 主观臆断。
      </div>

      {!agentDig && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          选择一只大涨标的并点击「运行 Agent 自主深挖」，系统将输出拉升前的隐藏早期信号时间线与综合评分。
        </div>
      )}

      {agentDig && (
        <>
          {/* 概览 badges */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Badge color="#60a5fa" text={`隐藏信号总数：${agentDig.signalCount} 条`} />
            <Badge color="#34d399" text={`小众早期信号：${agentDig.earlyCount} 条`} />
            <Badge color="#a78bfa" text={`引擎：${agentDig.engine}`} />
          </div>

          {/* 信号类型分布 */}
          <SectionTitle title="隐藏信号类型分布" />
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
            {Object.entries(agentDig.typeDistribution).map(([k, v]) => (
              <Chip key={k} label={`${k}：${v} 条`} colorDot={SIGNAL_COLOR[k] ?? '#94a3b8'} />
            ))}
          </div>

          {/* 综合评分排序的隐藏信号 */}
          <SectionTitle title="隐藏早期信号（按综合评分降序）" />
          <div style={{ marginBottom: 16 }}>
            {agentDig.signals.map((s, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 6, background: (SIGNAL_COLOR[s.signalType] ?? '#94a3b8') + '22', color: SIGNAL_COLOR[s.signalType] ?? '#94a3b8' }}>
                    {s.signalType}{s.isEarly && ' · 小众早期'}
                  </span>
                  <span style={{ color: '#e5e7eb', fontWeight: 600 }}>评分 {s.score.toFixed(1)} · 提前 {s.leadDays} 日</span>
                </div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 4, marginTop: 8, marginBottom: 8 }}>
                  <div style={{ width: `${s.score}%`, height: '100%', background: SIGNAL_COLOR[s.signalType] ?? '#94a3b8', borderRadius: 4 }} />
                </div>
                <div style={{ fontSize: 13, color: '#e5e7eb' }}>{s.summary}</div>
                <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 6 }}>
                  来源：{s.source} · 可信度 {(s.credibility * 100).toFixed(0)}% · 相关度 {(s.relevance * 100).toFixed(0)}% · {s.signalDate}
                </div>
              </div>
            ))}
          </div>

          {/* 时间线 */}
          <SectionTitle title="拉升前隐藏信号时间线（按日期升序）" />
          <div style={{ overflowX: 'auto', paddingBottom: 8 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'stretch', minWidth: 640 }}>
              {agentDig.timeline.map((t, i) => (
                <div key={i} style={{ flex: 1, minWidth: 130, background: t.isEarly ? '#0c2a1f' : '#0f172a', border: `1px solid ${t.isEarly ? '#34d399' : '#1e293b'}`, borderRadius: 10, padding: 10 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{t.signalDate}</div>
                  <div style={{ fontSize: 13, color: SIGNAL_COLOR[t.signalType] ?? '#e5e7eb', margin: '4px 0', fontWeight: 600 }}>{t.signalType}</div>
                  <div style={{ fontSize: 12, color: '#94a3b8' }}>提前 {t.leadDays} 日</div>
                  <div style={{ fontSize: 12, color: t.isEarly ? '#34d399' : '#64748b', marginTop: 4 }}>{t.isEarly ? '★ 小众早期信号' : '常规信号'}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
};

// ============================ 上涨因子库 Tab（增强模块） ============================
const FactorLibraryTab: React.FC<{
  library: FactorLibraryItem[];
  factorStats: FactorLibraryStats | null;
  predict: FactorPredictResult | null;
  factorInput: string;
  busy: string | null;
  onInputChange: (v: string) => void;
  onMine: () => void;
  onPredict: () => void;
}> = ({ library, factorStats, predict, factorInput, busy, onInputChange, onMine, onPredict }) => {
  const predictColor = predict
    ? PREDICT_COLOR[predict.suggestion.startsWith('强信号') ? '强信号' : predict.suggestion.startsWith('中性') ? '中性偏多' : '审慎']
    : '#94a3b8';
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <button onClick={onMine} disabled={busy === 'factor-mine'} style={{ ...btn(busy === 'factor-mine'), background: '#2563eb' }}>
          {busy === 'factor-mine' ? '沉淀计算中…' : '① 沉淀上涨因子库'}
        </button>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>已沉淀因子：{library.length} 条</span>
      </div>

      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 18 }}>
        系统将已验证的反向归因（§3.4）与回测（§3.7）结果按月按驱动因子统计，自动沉淀为标准化「上涨因子库」（出现频次 / 历史胜率 / 期望净收益 / 置信度），
        并支持正向预判：输入早期信号（如 Agent 深挖的四类隐藏信号或任意文本），匹配因子库后输出历史上涨概率与建议动作，形成「反向归因 → 因子沉淀 → 正向预判」闭环。
        全部为数学聚合，不依赖 LLM 主观臆断。
      </div>

      {/* #24 数据驱动累积统计面板 */}
      <SectionTitle title="因子库累积统计（预设基线 vs 生产真实归因累积）" />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 18 }}>
        <Metric label="基类预设因子" value={factorStats ? String(factorStats.presetCount) : '—'} color="#60a5fa" />
        <Metric label="真实归因落库" value={factorStats ? String(factorStats.dbAttributionCount) : '—'} color="#34d399" />
        <Metric label="DB 新发掘因子" value={factorStats ? String(factorStats.minedFromDb) : '—'} color="#a78bfa" />
        <Metric label="被强化基线因子" value={factorStats ? String(factorStats.reinforced) : '—'} color="#fbbf24" />
        <Metric label="因子库总数" value={factorStats ? String(factorStats.libraryTotal) : '—'} color="#e5e7eb" />
      </div>
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, fontSize: 12, color: '#94a3b8', marginBottom: 18 }}>
        闭环预警扫描（#20/#21）每次跑闭环都会把真实反向归因沉淀进 <code style={{ color: '#34d399' }}>BacktraceAttribution</code>，因子库据此从「仅预设基线」升级为「预设基线 + 生产真实归因累积」，实现高频因子自动沉淀（反向归因 → 因子沉淀闭环）。扫描次数越多，DB 新发掘 / 强化因子越充实。
      </div>

      {/* 因子库榜单 */}
      <SectionTitle title="标准化上涨因子库（高频优先，频次↑置信度↑）" />
      <div style={{ overflowX: 'auto', marginBottom: 22 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
              <th style={th}>排名</th>
              <th style={th}>因子名</th>
              <th style={th}>分类</th>
              <th style={th}>出现次数</th>
              <th style={th}>历史胜率</th>
              <th style={th}>均 1 月涨幅</th>
              <th style={th}>期望净收益</th>
              <th style={th}>置信度</th>
            </tr>
          </thead>
          <tbody>
            {library.length === 0 && (
              <tr><td style={td} colSpan={8}>点击「沉淀上涨因子库」生成标准化因子榜单</td></tr>
            )}
            {library.map((f) => (
              <tr key={f.factorName} style={{ borderTop: '1px solid #1e293b' }}>
                <td style={td}>{f.rank ?? '-'}</td>
                <td style={{ ...td, color: '#e5e7eb' }}>{f.factorName}</td>
                <td style={td}><Badge color={CATEGORY_COLOR[f.factorCategory] ?? '#94a3b8'} text={f.factorCategory} /></td>
                <td style={{ ...td, color: '#a78bfa', fontWeight: 600 }}>{f.occurCount}</td>
                <td style={{ ...td, color: '#34d399' }}>{(f.avgWinRate * 100).toFixed(1)}%</td>
                <td style={{ ...td, color: '#34d399' }}>+{f.avgGain1m.toFixed(1)}%</td>
                <td style={{ ...td, color: f.expectancy1m >= 0 ? '#34d399' : '#f87171' }}>{f.expectancy1m >= 0 ? '+' : ''}{f.expectancy1m.toFixed(1)}%</td>
                <td style={td}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 60, height: 6, background: '#1e293b', borderRadius: 4 }}>
                      <div style={{ width: `${f.confidence * 100}%`, height: '100%', background: '#60a5fa', borderRadius: 4 }} />
                    </div>
                    <span style={{ color: '#94a3b8' }}>{(f.confidence * 100).toFixed(0)}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 正向预判面板 */}
      <SectionTitle title="② 正向预判：早期信号 → 上涨概率" />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <input
          value={factorInput}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="输入早期信号，用 、或 , 分隔"
          style={{ flex: 1, minWidth: 280, background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '8px 12px', fontSize: 13 }}
        />
        <button onClick={onPredict} disabled={busy === 'factor-predict'} style={{ ...btn(busy === 'factor-predict'), background: '#2563eb' }}>
          {busy === 'factor-predict' ? '预判计算中…' : '运行正向预判'}
        </button>
      </div>

      {predict && (
        <>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Metric label="预测上涨概率" value={`${(predict.predictedProb * 100).toFixed(1)}%`} color={predictColor} />
            <Metric label="加权期望净收益" value={`${predict.avgExpectancy >= 0 ? '+' : ''}${predict.avgExpectancy.toFixed(2)}%`} color={predict.avgExpectancy >= 0 ? '#34d399' : '#f87171'} />
            <Badge color={predictColor} text={`建议：${predict.suggestion}`} />
          </div>

          <SectionTitle title="命中因子明细（置信度加权）" />
          <div style={{ marginBottom: 12 }}>
            {predict.matched.map((m, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb', flexWrap: 'wrap', gap: 6 }}>
                  <span>{m.factorName}</span>
                  <span style={{ color: '#34d399' }}>胜率 {(m.avgWinRate * 100).toFixed(0)}%</span>
                  <span style={{ color: '#94a3b8' }}>置信 {(m.confidence * 100).toFixed(0)}%</span>
                  <span style={{ color: '#a78bfa' }}>沉淀 {m.occurCount} 次</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
};

// ============================ 因子传导 → DSA 内核 Tab（闭环增强，内核零改动） ============================
const CHAINS = [
  { id: 'lithium', name: '锂电池产业链' },
  { id: 'semiconductor', name: '半导体产业链' },
  { id: 'photovoltaic', name: '光伏产业链' },
];

const FactorPropagateTab: React.FC<{
  chain: string;
  node: string;
  magnitude: number;
  forecast: FactorForecastResult | null;
  busy: string | null;
  onChainChange: (v: string) => void;
  onNodeChange: (v: string) => void;
  onMagChange: (v: number) => void;
  onRun: () => void;
}> = ({ chain, node, magnitude, forecast, busy, onChainChange, onNodeChange, onMagChange, onRun }) => {
  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>产业链：</span>
        <select
          value={chain}
          onChange={(e) => onChainChange(e.target.value)}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13 }}
        >
          {CHAINS.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <input
          value={node}
          onChange={(e) => onNodeChange(e.target.value)}
          placeholder="冲击环节（如 锂矿）"
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13, width: 160 }}
        />
        <span style={{ color: '#94a3b8', fontSize: 13 }}>冲击幅度：</span>
        <input
          type="number"
          step="0.05"
          value={magnitude}
          onChange={(e) => onMagChange(Number(e.target.value))}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13, width: 90 }}
        />
        <button onClick={onRun} disabled={busy === 'propagate'} style={{ ...btn(busy === 'propagate'), background: '#2563eb' }}>
          {busy === 'propagate' ? '传导桥接中…' : '运行因子传导桥接'}
        </button>
      </div>

      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 18 }}>
        把 #17 沉淀的标准化上涨因子库（按期望净收益排序、置信度过滤）转为 DSA 引擎 propagate_shock 的因子权重，并以「冲击幅度因子增益」真实注入四周期正向传导，
        输出 基线 vs 因子增强 对比（内核零改动；未来内核若支持 factor_weights 加权传导，可直接消费同一字典，向后兼容）。全部为数学加权，不依赖 LLM。
      </div>

      {!forecast && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          选择产业链与冲击环节并点击「运行因子传导桥接」，系统将把沉淀因子注入 DSA 内核，给出基线 vs 因子增强的四周期正向传导预测。
        </div>
      )}

      {forecast && (
        <>
          {/* 概览 badges */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Badge color="#60a5fa" text={`冲击环节：${forecast.shockNode ?? '-'}`} />
            <Badge color="#a78bfa" text={`注入因子：${forecast.factors.length} 个`} />
            <Badge color={LIFT_COLOR['正向增益']} text={`冲击幅度增益 +${(forecast.boost * 100).toFixed(1)}%`} />
            <Badge color="#34d399" text={`结构化注入边：${(forecast.edgeOverrides?.length ?? 0)} 条`} />
            <Badge color="#64748b" text={`引擎：${forecast.engine}`} />
          </div>

          {/* 基线 vs 增强 指标卡 */}
          <SectionTitle title="基线 vs 因子增强 · 传导强度对比" />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 18 }}>
            <Metric label="基线最大冲击" value={`${forecast.baseline.maxImpactPct.toFixed(2)}%`} color={LIFT_COLOR['基准']} />
            <Metric label="增强最大冲击" value={`${forecast.enhanced.maxImpactPct.toFixed(2)}%`} color={LIFT_COLOR['正向增益']} />
            <Metric label="最大冲击提升" value={`+${forecast.liftPct.maxImpact.toFixed(2)}%`} color={LIFT_COLOR['正向增益']} />
            <Metric label="影响环节变化" value={`${forecast.liftPct.impactedNodes >= 0 ? '+' : ''}${forecast.liftPct.impactedNodes}`} color="#e5e7eb" />
            <Metric label="涉及公司变化" value={`${forecast.liftPct.affectedCompanies >= 0 ? '+' : ''}${forecast.liftPct.affectedCompanies}`} color="#e5e7eb" />
          </div>

          {/* 四周期正向传导预测 */}
          <SectionTitle title="四周期正向传导预测（1 周 / 2 周 / 1 月 / 6 月）" />
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 16, marginBottom: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 12, color: '#94a3b8' }}>
              <span>峰值冲击折算（相对最大冲击幅度）</span>
              <span>基线（灰） vs 因子增强（绿）</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 18, height: 180 }}>
              {forecast.forward4.periods.map((p, i) => (
                <div key={p} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                  <div style={{ fontSize: 11, color: '#64748b', marginBottom: 2 }}>{forecast.forward4.baseline[i].toFixed(2)}%</div>
                  <div style={{ width: 28, background: '#64748b', borderRadius: '4px 4px 0 0', height: `${(forecast.forward4.baseline[i] / 20) * 100}%`, marginBottom: 2 }} />
                  <div style={{ fontSize: 11, color: LIFT_COLOR['正向增益'], marginBottom: 2 }}>{forecast.forward4.enhanced[i].toFixed(2)}%</div>
                  <div style={{ width: 28, background: LIFT_COLOR['正向增益'], borderRadius: '4px 4px 0 0', height: `${(forecast.forward4.enhanced[i] / 20) * 100}%` }} />
                  <div style={{ fontSize: 12, color: '#cbd5e1', marginTop: 6 }}>{p}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 注入的因子权重明细 */}
          <SectionTitle title="注入 DSA 内核的因子权重（归一化）" />
          <div style={{ marginBottom: 12 }}>
            {forecast.factors.map((f, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb', flexWrap: 'wrap', gap: 6 }}>
                  <span>{f.factorName}</span>
                  <span style={{ color: CATEGORY_COLOR[f.factorCategory] ?? '#94a3b8' }}>{f.factorCategory}</span>
                  <span style={{ color: '#34d399' }}>胜率 {(f.avgWinRate * 100).toFixed(0)}%</span>
                  <span style={{ color: '#94a3b8' }}>置信 {(f.confidence * 100).toFixed(0)}%</span>
                  <span style={{ color: '#a78bfa' }}>权重 {(f.weight * 100).toFixed(0)}%</span>
                </div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 4, marginTop: 8 }}>
                  <div style={{ width: `${f.weight * 100}%`, height: '100%', background: '#34d399', borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>

          {/* #22 结构化边注入：按因子类别差异化增强对应产业链边 */}
          <SectionTitle title="结构化边注入（#22 · 按因子类别差异化增强对应产业链边）" />
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 14 }}>
            把命中因子的<span style={{ color: '#e5e7eb' }}>类别</span>映射到对应<span style={{ color: '#e5e7eb' }}>产业链边类型</span>，经由 DSA 内核
            <span style={{ color: '#e5e7eb' }}> use_overrides</span> 通道差异化增强对应边系数（内核零改动）：
            <b style={{ color: '#34d399' }}>基本面事件驱动 → supply / cost</b>、
            <b style={{ color: '#34d399' }}>资金筹码驱动 → demand</b>、
            <b style={{ color: '#34d399' }}>题材情绪驱动 → subst(+demand)</b>。
            匹配边的系数被覆盖后，传导在该类通道上获得更强放大——这正是「全局幅度增益」升级为「结构化注入」的核心。
          </div>

          {/* 类别 → 边 贡献拆解 */}
          <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 8 }}>类别 → 边 贡献拆解（增益越高，该类别对该边类型的结构化注入越强）</div>
          <div style={{ marginBottom: 14 }}>
            {(forecast.categoryEdgeContrib ?? []).map((c, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb', flexWrap: 'wrap', gap: 6 }}>
                  <span style={{ color: CATEGORY_COLOR[c.factorCategory] ?? '#94a3b8' }}>{c.factorCategory}</span>
                  <span style={{ color: '#a78bfa' }}>→ 边类型 {c.edgeType}</span>
                  <span style={{ color: '#34d399' }}>增益 +{(c.boost * 100).toFixed(1)}%</span>
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{c.factors.join('、')}</div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 4, marginTop: 8 }}>
                  <div style={{ width: `${Math.min(100, c.boost * 100)}%`, height: '100%', background: '#34d399', borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>

          {/* 被注入边明细 */}
          <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 8 }}>被注入边明细（基线系数 → 覆盖系数，按边类型分组差异化增强）</div>
          <div style={{ overflowX: 'auto', marginBottom: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>源节点</th>
                  <th style={th}>目标节点</th>
                  <th style={th}>边类型</th>
                  <th style={th}>基线系数</th>
                  <th style={th}>覆盖系数</th>
                  <th style={th}>增益</th>
                  <th style={th}>贡献类别</th>
                </tr>
              </thead>
              <tbody>
                {(forecast.edgeOverrides ?? []).map((o, i) => (
                  <tr key={i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{o.source}</td>
                    <td style={td}>{o.target}</td>
                    <td style={{ ...td, color: '#a78bfa' }}>{o.edgeType}</td>
                    <td style={td}>{o.baseCoeff.toFixed(4)}</td>
                    <td style={{ ...td, color: '#34d399' }}>{o.overrideCoeff.toFixed(4)}</td>
                    <td style={{ ...td, color: '#34d399', fontWeight: 700 }}>+{(o.boost * 100).toFixed(1)}%</td>
                    <td style={td}>{o.categories.join('、')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
};

// ============================ 一键闭环 Tab（收尾闭环：深挖 → 预判 → 内核传导） ============================
const ClosedLoopTab: React.FC<{
  pool: ScreenPoolItem[];
  loopCode: string;
  closedLoop: ClosedLoopResult | null;
  busy: string | null;
  onCodeChange: (code: string) => void;
  onRun: () => void;
}> = ({ pool, loopCode, closedLoop, busy, onCodeChange, onRun }) => {
  const predictColor = closedLoop
    ? PREDICT_COLOR[
        closedLoop.predict.suggestion.startsWith('强信号')
          ? '强信号'
          : closedLoop.predict.suggestion.startsWith('中性')
            ? '中性偏多'
            : '审慎'
      ]
    : '#94a3b8';

  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>闭环标的：</span>
        <select
          value={loopCode}
          onChange={(e) => onCodeChange(e.target.value)}
          style={{ background: '#0f172a', color: '#e5e7eb', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 10px', fontSize: 13, minWidth: 200 }}
        >
          {pool.length === 0 && <option value="">（暂无标的）</option>}
          {pool.map((p) => (
            <option key={p.stockCode} value={p.stockCode}>
              {p.stockName}（{p.stockCode}）
            </option>
          ))}
        </select>
        <button onClick={onRun} disabled={busy === 'loop'} style={{ ...btn(busy === 'loop'), background: '#2563eb' }}>
          {busy === 'loop' ? '一键闭环计算中…' : '▶ 运行一键闭环'}
        </button>
      </div>

      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 18 }}>
        把已完成的增强模块编排为单次调用的一条龙链路：<b style={{ color: '#e5e7eb' }}>① Agent 自主深挖</b>（拉升前隐藏信号）→
        <b style={{ color: '#e5e7eb' }}> ② 因子正向预判</b>（信号对齐因子库、输出上涨概率）→
        <b style={{ color: '#e5e7eb' }}> ③ 因子 → DSA 内核传导</b>（命中因子注入四周期正向传导）。
        全部为数学编排，不依赖 LLM；DSA 内核零改动。
      </div>

      {!closedLoop && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          选择一只大涨标的并点击「运行一键闭环」，系统将自动跑通「隐藏信号深挖 → 上涨概率预判 → 内核四周期传导」全流程，并给出三段式结论。
        </div>
      )}

      {closedLoop && (
        <>
          {/* 阶段流转总览 */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
            <Badge color="#60a5fa" text={`标的：${closedLoop.stockName ?? closedLoop.stockCode}`} />
            <Badge color="#a78bfa" text={`传导产业链：${closedLoop.chainId}`} />
            <Badge color="#64748b" text={`引擎：${closedLoop.engine}`} />
          </div>

          {/* 阶段一：Agent 深耕 */}
          <SectionTitle title="阶段一 · Agent 自主深挖（#16）——拉升前隐藏早期信号" />
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <Badge color="#60a5fa" text={`隐藏信号：${closedLoop.dig.signalCount} 条`} />
            <Badge color="#34d399" text={`小众早期：${closedLoop.dig.earlyCount} 条`} />
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }}>
            {Object.entries(closedLoop.dig.typeDistribution).map(([k, v]) => (
              <Chip key={k} label={`${k}：${v} 条`} colorDot={SIGNAL_COLOR[k] ?? '#94a3b8'} />
            ))}
          </div>

          {/* 阶段二：因子正向预判 */}
          <SectionTitle title="阶段二 · 因子正向预判（#17）——早期信号 → 上涨概率" />
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <Metric label="预测上涨概率" value={`${(closedLoop.predict.predictedProb * 100).toFixed(1)}%`} color={predictColor} />
            <Metric label="加权期望净收益" value={`${closedLoop.predict.avgExpectancy >= 0 ? '+' : ''}${closedLoop.predict.avgExpectancy.toFixed(2)}%`} color={closedLoop.predict.avgExpectancy >= 0 ? '#34d399' : '#f87171'} />
            <Badge color={predictColor} text={`建议：${closedLoop.predict.suggestion}`} />
            <Badge color="#a78bfa" text={`命中因子：${closedLoop.predict.matched.length} 个`} />
          </div>

          {/* 阶段三：因子 → DSA 内核传导 */}
          <SectionTitle title="阶段三 · 因子 → DSA 内核传导（#18）——基线 vs 因子增强" />
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
            <Badge color="#a78bfa" text={`注入因子：${closedLoop.propagate.factors.length} 个`} />
            <Badge color={LIFT_COLOR['正向增益']} text={`冲击幅度增益 +${(closedLoop.propagate.boost * 100).toFixed(1)}%`} />
            <Badge color="#34d399" text={`结构化注入边：${closedLoop.propagate.edgeOverrides?.length ?? 0} 条`} />
            <Badge color="#64748b" text={`冲击环节：${closedLoop.propagate.shockNode ?? '-'}`} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 18 }}>
            <Metric label="基线最大冲击" value={`${closedLoop.propagate.baseline.maxImpactPct.toFixed(2)}%`} color={LIFT_COLOR['基准']} />
            <Metric label="增强最大冲击" value={`${closedLoop.propagate.enhanced.maxImpactPct.toFixed(2)}%`} color={LIFT_COLOR['正向增益']} />
            <Metric label="最大冲击提升" value={`+${closedLoop.propagate.liftPct.maxImpact.toFixed(2)}%`} color={LIFT_COLOR['正向增益']} />
            <Metric label="涉及公司变化" value={`${closedLoop.propagate.liftPct.affectedCompanies >= 0 ? '+' : ''}${closedLoop.propagate.liftPct.affectedCompanies}`} color="#e5e7eb" />
          </div>

          {/* 四周期正向传导预测 */}
          <SectionTitle title="四周期正向传导预测（1 周 / 2 周 / 1 月 / 6 月）" />
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 16, marginBottom: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 12, color: '#94a3b8' }}>
              <span>峰值冲击折算（相对最大冲击幅度）</span>
              <span>基线（灰） vs 因子增强（绿）</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 18, height: 180 }}>
              {closedLoop.propagate.forward4.periods.map((p, i) => (
                <div key={p} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                  <div style={{ fontSize: 11, color: '#64748b', marginBottom: 2 }}>{closedLoop.propagate.forward4.baseline[i].toFixed(2)}%</div>
                  <div style={{ width: 28, background: '#64748b', borderRadius: '4px 4px 0 0', height: `${(closedLoop.propagate.forward4.baseline[i] / 20) * 100}%`, marginBottom: 2 }} />
                  <div style={{ fontSize: 11, color: LIFT_COLOR['正向增益'], marginBottom: 2 }}>{closedLoop.propagate.forward4.enhanced[i].toFixed(2)}%</div>
                  <div style={{ width: 28, background: LIFT_COLOR['正向增益'], borderRadius: '4px 4px 0 0', height: `${(closedLoop.propagate.forward4.enhanced[i] / 20) * 100}%` }} />
                  <div style={{ fontSize: 12, color: '#cbd5e1', marginTop: 6 }}>{p}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 注入的因子权重明细 */}
          <SectionTitle title="注入 DSA 内核的因子权重（闭环联动）" />
          <div style={{ marginBottom: 12 }}>
            {closedLoop.propagate.factors.map((f, i) => (
              <div key={i} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb', flexWrap: 'wrap', gap: 6 }}>
                  <span>{f.factorName}</span>
                  <span style={{ color: CATEGORY_COLOR[f.factorCategory] ?? '#94a3b8' }}>{f.factorCategory}</span>
                  <span style={{ color: '#34d399' }}>胜率 {(f.avgWinRate * 100).toFixed(0)}%</span>
                  <span style={{ color: '#a78bfa' }}>权重 {(f.weight * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
};

// ============================ 自动化闭环预警 Tab（#20 扫描 + #21 调度） ============================
function scheduleHint(cron: string | undefined): string {
  if (!cron) return '未配置';
  // 仅对默认/常见形态给出可读提示，其余直接展示表达式
  if (cron === '30 15 * * 1-5') return '每周一至周五 15:30（收盘后）';
  return cron;
}

const ScanAlertTab: React.FC<{
  alertScan: AlertScanResult | null;
  scanSchedule: ScheduleConfig | null;
  scanHistory: ScanBatch[];
  dataSource: DataSourceInfo | null;
  disclosureSource: DisclosureSourceInfo | null;
  disclosures: DisclosureItem[];
  opinionSource: OpinionSourceInfo | null;
  opinions: OpinionItem[];
  wechatSource: WechatSourceInfo | null;
  wechats: WechatOpinionItem[];
  flashSource: FlashSourceInfo | null;
  flashes: FlashOpinionItem[];
  communitySource: CommunitySourceInfo | null;
  communities: CommunityOpinionItem[];
  overseasSource: OverseasSourceInfo | null;
  overseas: OverseasNewsItem[];
  kronosSource: KronosSourceInfo | null;
  kronosPools: KronosPools | null;
  infoLayers: InfoLayers | null;
  crossValidationSummary: CrossValidationSummary | null;
  sentimentBacktest: SentimentBacktestReport | null;
  inflectionSummary: InflectionSummary | null;
  busy: string | null;
  onRun: () => void;
}> = ({ alertScan, scanSchedule, scanHistory, dataSource, disclosureSource, disclosures, opinionSource, opinions, wechatSource, wechats, flashSource, flashes, communitySource, communities, overseasSource, overseas, kronosSource, kronosPools, infoLayers, crossValidationSummary, sentimentBacktest, inflectionSummary, busy, onRun }) => {
  const alerts = alertScan?.alerts ?? [];
  const strongCount = alerts.filter((a) => a.level.startsWith('强信号')).length;
  const neutralCount = alerts.filter((a) => a.level.startsWith('中性')).length;
  const weakCount = alerts.filter((a) => a.level.startsWith('弱信号')).length;

  return (
    <>
      {/* #21 调度面板：收盘后定时 / 手动触发入口 */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 14, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <Badge color="#a78bfa" text={`调度配置：${scheduleHint(scanSchedule?.cron)}`} />
          <Badge
            color={scanSchedule?.enabled ? '#34d399' : '#f87171'}
            text={scanSchedule?.enabled ? '定时触发：已启用' : '定时触发：已停用'}
          />
          <span style={{ color: '#64748b', fontSize: 12 }}>cron：{scanSchedule?.cron ?? '—'}</span>
          {dataSource && (
            <Badge
              color={dataSource.mode === 'real' ? '#34d399' : '#94a3b8'}
              text={`数据源：${dataSource.mode === 'real' ? '实时（AkShare）' : '模拟'}${dataSource.provider ? ` · ${dataSource.provider}` : ''}`}
            />
          )}
          {disclosureSource && (
            <Badge
              color={disclosureSource.mode === 'real' ? '#34d399' : '#94a3b8'}
              text={`公开披露：${disclosureSource.mode === 'real' ? '实时（cninfo）' : '模拟'}${disclosureSource.provider ? ` · ${disclosureSource.provider}` : ''}`}
            />
          )}
          {opinionSource && (
            <Badge
              color={opinionSource.mode === 'real' ? '#34d399' : '#94a3b8'}
              text={`头条舆情：${opinionSource.mode === 'real' ? '实时（头条爬虫）' : '模拟'}${opinionSource.provider ? ` · ${opinionSource.provider}` : ''}`}
            />
          )}
          {wechatSource && (
            <Badge
              color={wechatSource.mode === 'real' ? '#34d399' : '#94a3b8'}
              text={`微信舆情：${wechatSource.mode === 'real' ? '实时（公众号/视频号）' : '模拟'}${wechatSource.provider ? ` · ${wechatSource.provider}` : ''}`}
            />
          )}
          {flashSource && (
            <Badge
              color={flashSource.mode === 'real' ? '#34d399' : '#fbbf24'}
              text={`财联社快讯：${flashSource.mode === 'real' ? '实时（财联社/华尔街见闻/金十）' : '模拟'}${flashSource.provider ? ` · ${flashSource.provider}` : ''}`}
            />
          )}
          {communitySource && (
            <Badge
              color={communitySource.mode === 'real' ? '#34d399' : '#a78bfa'}
              text={`深度社区舆情：${communitySource.mode === 'real' ? '实时（雪球/股吧/淘股吧）' : '模拟'}${communitySource.provider ? ` · ${communitySource.provider}` : ''}`}
            />
          )}
          {overseasSource && (
            <Badge
              color={overseasSource.mode === 'real' ? '#34d399' : '#a78bfa'}
              text={`海外权威：${overseasSource.mode === 'real' ? '实时（彭博/路透/WSJ/Seeking Alpha）' : '模拟'}${overseasSource.provider ? ` · ${overseasSource.provider}` : ''}`}
            />
          )}
          {kronosSource && (
            <Badge
              color={kronosSource.mode === 'real' ? '#34d399' : '#a78bfa'}
              text={`Kronos 技术面：${kronosSource.mode === 'real' ? `实时（${kronosSource.modelSpec}）` : '模拟'}${kronosSource.provider ? ` · ${kronosSource.provider}` : ''}`}
            />
          )}
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={onRun} disabled={busy === 'alert-scan'} style={{ ...btn(busy === 'alert-scan'), background: '#2563eb' }}>
            {busy === 'alert-scan' ? '扫描计算中…' : '▶ 立即运行闭环预警（调度入口）'}
          </button>
          <span style={{ color: '#94a3b8', fontSize: 13 }}>
            默认扫描当日大涨回溯池，逐只跑通「Agent 深挖 → 因子预判 → 内核传导」并给出分级预警；每次运行落「批次聚合」记录
          </span>
        </div>
      </div>

      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, fontSize: 13, color: '#94a3b8', marginBottom: 18 }}>
        把 #19 一键闭环编排为<b style={{ color: '#e5e7eb' }}> 批量自动化预警</b>：对大涨回溯池（或指定 watchlist）逐只跑闭环，
        综合「上涨概率 / 内核增益 / 小众早期信号 / 最强单信号评分」四项指标给出 0~1 <b style={{ color: '#e5e7eb' }}>综合预警评分</b>，
        并分级为 <b style={{ color: '#34d399' }}>强信号·重点关注</b> / <b style={{ color: '#fbbf24' }}>中性·持续观察</b> / <b style={{ color: '#64748b' }}>弱信号·低关注</b>。
        <b style={{ color: '#e5e7eb' }}> #21 调度</b>：支持收盘后定时（默认周一至周五 15:30）、手动与事件触发，批次历史可回看。
        全部为数学编排，不依赖 LLM；DSA 内核零改动。
      </div>

      {/* #25 可插拔公开披露源：把基本面催化信号源从 mock 升级为 cninfo / 财报 / 研报 */}
      <SectionTitle title="公开披露催化事件池（#25 · 真实环境适配）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            基本面催化源：
            <b style={{ color: disclosureSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {disclosureSource ? (disclosureSource.mode === 'real' ? '实时（cninfo / 财报 / 研报）' : '模拟披露源') : '加载中…'}
            </b>
            {disclosureSource?.provider ? ` · ${disclosureSource.provider}` : ''}
          </span>
          {disclosureSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              公告 {disclosureSource.disclosureCount} · 财报 {disclosureSource.financialCount} · 研报 {disclosureSource.researchCount}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            扫描时作为基本面筛选叠加（union），喂给真实归因累积；沙箱确定性，真实环境可扩展至 fresh 披露小市值标的
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期披露事件（公告 / 业绩预告 / 重大合同 / 股权激励 / 财报 / 研报点评）：
        </div>
        {disclosures.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无披露事件（点击上方「立即运行」将触发披露池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>类别</th>
                  <th style={th}>披露标题</th>
                  <th style={th}>情绪</th>
                </tr>
              </thead>
              <tbody>
                {disclosures.slice(0, 12).map((d, i) => (
                  <tr key={d.id ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{d.stockName ?? d.stockCode}</td>
                    <td style={td}>{d.disclosureDate ?? '—'}</td>
                    <td style={td}>{d.category}</td>
                    <td style={{ ...td, color: '#e5e7eb' }}>{d.title}</td>
                    <td style={{ ...td, color: d.sentiment === '利好' ? '#34d399' : d.sentiment === '利空' ? '#f87171' : '#94a3b8' }}>{d.sentiment ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #28 可插拔公开舆情源：把情绪面催化信号源从 mock 升级为头条爬虫 + FinBERT */}
      <SectionTitle title="头条舆情催化事件池（#28 · DSA-PUBLIC-OPINION-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            情绪面催化源：
            <b style={{ color: opinionSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {opinionSource ? (opinionSource.mode === 'real' ? '实时（头条爬虫 + FinBERT）' : '模拟舆情源') : '加载中…'}
            </b>
            {opinionSource?.provider ? ` · ${opinionSource.provider}` : ''}
          </span>
          {opinionSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              舆情事件 {opinionSource.opinionCount} · 疑似谣言 {opinionSource.rumorCount} · 建议权重 {opinionSource.weightSuggest}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            扫描时作为情绪面筛选叠加（union，与披露源正交）；权重坚守「机构&gt;公告&gt;舆情」，舆情仅短线情绪因子
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期舆情事件（文档 §三 四层信息圈层 · §四 标准化情绪量化：热度 / 情绪 / 扩散阶段 / 谣言降权）：
        </div>
        {opinions.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无舆情事件（点击上方「立即运行」将触发舆情池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>来源</th>
                  <th style={th}>阶段</th>
                  <th style={th}>情绪</th>
                  <th style={th}>热度</th>
                  <th style={th}>谣言</th>
                </tr>
              </thead>
              <tbody>
                {opinions.slice(0, 12).map((o, i) => (
                  <tr key={o.id ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{o.stockName ?? o.stockCode}</td>
                    <td style={td}>{o.opinionDate ?? '—'}</td>
                    <td style={td}>{o.source ?? '—'}</td>
                    <td style={td}>{o.stage ?? '—'}</td>
                    <td style={{ ...td, color: o.sentiment === '利好' ? '#34d399' : o.sentiment === '利空' ? '#f87171' : '#94a3b8' }}>{o.sentiment ?? '—'}</td>
                    <td style={{ ...td, color: (o.heatScore ?? 0) >= 0.7 ? '#fbbf24' : '#94a3b8' }}>{o.heatScore != null ? o.heatScore.toFixed(2) : '—'}</td>
                    <td style={td}>{o.hasRumor ? <span style={{ color: '#f87171' }}>疑似谣言·已降权</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #31 可插拔微信私域舆情源：把私域圈层情绪面催化信号源从 mock 升级为公众号/视频号爬虫 + FinBERT */}
      <SectionTitle title="微信舆情催化事件池（#31 · DSA-WECHAT-OPINION-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            私域情绪面催化源：
            <b style={{ color: wechatSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {wechatSource ? (wechatSource.mode === 'real' ? '实时（公众号/视频号爬虫 + FinBERT）' : '模拟微信舆情源') : '加载中…'}
            </b>
            {wechatSource?.provider ? ` · ${wechatSource.provider}` : ''}
          </span>
          {wechatSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              微信事件 {wechatSource.wechatCount} · 疑似谣言 {wechatSource.rumorCount} · 低可信 {wechatSource.lowCredibilityCount} · 短线权重 {wechatSource.weightShortSuggest} / 长线 {wechatSource.weightLongSuggest}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            仅公众号/视频号可抓取（群聊/朋友圈不可采）；扫描时作为私域情绪面筛选叠加（union，与头条舆情正交）
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期微信私域舆情（文档 §五 可信度分级：券商官方/正规产业号高可信，无来源爆料低可信强制降权）：
        </div>
        {wechats.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无微信舆情事件（点击上方「立即运行」将触发微信舆情池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>载体</th>
                  <th style={th}>可信度</th>
                  <th style={th}>阶段</th>
                  <th style={th}>情绪</th>
                  <th style={th}>热度</th>
                  <th style={th}>谣言</th>
                </tr>
              </thead>
              <tbody>
                {wechats.slice(0, 12).map((w, i) => (
                  <tr key={w.id ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{w.stockName ?? w.stockCode}</td>
                    <td style={td}>{w.pubDate ?? '—'}</td>
                    <td style={td}>{w.carrier ?? '—'}</td>
                    <td style={{ ...td, color: w.credibility === '高' ? '#34d399' : w.credibility === '低' ? '#f87171' : '#fbbf24' }}>{w.credibility ?? '—'}</td>
                    <td style={td}>{w.stage ?? '—'}</td>
                    <td style={{ ...td, color: w.sentiment === '利好' ? '#34d399' : w.sentiment === '利空' ? '#f87171' : '#94a3b8' }}>{w.sentiment ?? '—'}</td>
                    <td style={{ ...td, color: (w.heatScore ?? 0) >= 0.7 ? '#fbbf24' : '#94a3b8' }}>{w.heatScore != null ? w.heatScore.toFixed(2) : '—'}</td>
                    <td style={td}>{w.hasRumor ? <span style={{ color: '#f87171' }}>疑似谣言·已降权</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #34 可插拔短线快讯舆情源：把短线快讯情绪面催化信号源从 mock 升级为财联社/华尔街见闻/金十爬虫 + 垂直媒体 + FinBERT */}
      <SectionTitle title="短线快讯催化事件池（#34 · DSA-FLASH-OPINION-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            短线快讯情绪面催化源：
            <b style={{ color: flashSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {flashSource ? (flashSource.mode === 'real' ? '实时（财联社/华尔街见闻/金十爬虫 + FinBERT）' : '模拟快讯源') : '加载中…'}
            </b>
            {flashSource?.provider ? ` · ${flashSource.provider}` : ''}
          </span>
          {flashSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              快讯事件 {flashSource.flashCount} · 疑似谣言 {flashSource.rumorCount} · 盘中突发 {flashSource.breakingCount} · 短线权重 {flashSource.weightShortSuggest} / 长线 {flashSource.weightLongSuggest}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            财联社为 A 股短线第一舆情平台，游资/量化第一参考；扫描时作为短线情绪面筛选叠加（union，与微信舆情正交）
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期短线快讯（文档 §一.2：财联社/华尔街见闻/金十 电报式推送 + 财新/e公司/券商中国 深度媒体独家爆料）：
        </div>
        {flashes.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无快讯事件（点击上方「立即运行」将触发快讯池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>渠道</th>
                  <th style={th}>类型</th>
                  <th style={th}>突发</th>
                  <th style={th}>阶段</th>
                  <th style={th}>情绪</th>
                  <th style={th}>热度</th>
                  <th style={th}>谣言</th>
                </tr>
              </thead>
              <tbody>
                {flashes.slice(0, 12).map((f, i) => (
                  <tr key={f.id ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{f.stockName ?? f.stockCode}</td>
                    <td style={td}>{f.pubDate ?? '—'}</td>
                    <td style={td}>{f.source ?? '—'}</td>
                    <td style={{ ...td, color: f.mediaType === '深度媒体' ? '#f87171' : '#fbbf24' }}>{f.mediaType ?? '—'}</td>
                    <td style={td}>{f.isBreaking ? <span style={{ color: '#f87171' }}>盘中突发</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                    <td style={td}>{f.stage ?? '—'}</td>
                    <td style={{ ...td, color: f.sentiment === '利好' ? '#34d399' : f.sentiment === '利空' ? '#f87171' : '#94a3b8' }}>{f.sentiment ?? '—'}</td>
                    <td style={{ ...td, color: (f.heatScore ?? 0) >= 0.7 ? '#fbbf24' : '#94a3b8' }}>{f.heatScore != null ? f.heatScore.toFixed(2) : '—'}</td>
                    <td style={td}>{f.hasRumor ? <span style={{ color: '#f87171' }}>疑似谣言·已降权</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #36 可插拔深度社区舆情源：把社区情绪面催化信号源从 mock 升级为雪球/东财股吧/淘股吧爬虫 + 质量分层 + FinBERT + 谣言降权 */}
      <SectionTitle title="深度社区舆情催化事件池（#36 · DSA-COMMUNITY-OPINION-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            深度社区情绪面催化源：
            <b style={{ color: communitySource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {communitySource ? (communitySource.mode === 'real' ? '实时（雪球/东财股吧/淘股吧爬虫 + FinBERT）' : '模拟社区源') : '加载中…'}
            </b>
            {communitySource?.provider ? ` · ${communitySource.provider}` : ''}
          </span>
          {communitySource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              社区讨论 {communitySource.communityCount} · 登热榜 {communitySource.hotCount} · 疑似谣言 {communitySource.rumorCount} · 短线权重 {communitySource.weightShortSuggest} / 长线 {communitySource.weightLongSuggest}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            雪球偏理性中长线、股吧/淘股吧偏情绪化短线；扫描时作为社区情绪面筛选叠加（union，与快讯舆情正交）
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期深度社区讨论（文档 §一.2：雪球 高质量投资者社区 / 东财股吧 散户情绪放大器 / 淘股吧 游资短线风向标）：
        </div>
        {communities.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无社区讨论事件（点击上方「立即运行」将触发社区池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>平台</th>
                  <th style={th}>质量</th>
                  <th style={th}>热榜</th>
                  <th style={th}>情绪</th>
                  <th style={th}>热度</th>
                  <th style={th}>谣言</th>
                </tr>
              </thead>
              <tbody>
                {communities.slice(0, 12).map((c, i) => (
                  <tr key={c.id ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{c.stockName ?? c.stockCode}</td>
                    <td style={td}>{c.pubDate ?? '—'}</td>
                    <td style={td}>{c.platform ?? '—'}</td>
                    <td style={{ ...td, color: c.quality === '高质量' ? '#34d399' : c.quality === '噪音' ? '#f87171' : '#94a3b8' }}>{c.quality ?? '—'}</td>
                    <td style={td}>{c.isHot ? <span style={{ color: '#fbbf24' }}>登热榜</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                    <td style={{ ...td, color: c.sentiment === '看多' ? '#34d399' : c.sentiment === '看空' ? '#f87171' : '#94a3b8' }}>{c.sentiment ?? '—'}</td>
                    <td style={{ ...td, color: (c.discussionHeat ?? 0) >= 0.7 ? '#fbbf24' : '#94a3b8' }}>{c.discussionHeat != null ? c.discussionHeat.toFixed(2) : '—'}</td>
                    <td style={td}>{c.hasRumor ? <span style={{ color: '#f87171' }}>疑似谣言·已降权</span> : <span style={{ color: '#475569' }}>—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #37 可插拔海外权威舆情源：把海外权威情绪面催化信号源从 mock 升级为彭博/路透/WSJ/Seeking Alpha 抓取 + 机构评级 + 外资流向解析 */}
      <SectionTitle title="海外权威资讯催化事件池（#37 · DSA-OVERSEAS-OPINION-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            海外权威情绪面催化源：
            <b style={{ color: overseasSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {overseasSource ? (overseasSource.mode === 'real' ? '实时（彭博/路透/WSJ/Seeking Alpha 抓取 + 机构评级）' : '模拟海外权威源') : '加载中…'}
            </b>
            {overseasSource?.provider ? ` · ${overseasSource.provider}` : ''}
          </span>
          {overseasSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              海外资讯 {overseasSource.overseasCount} · 机构评级 {overseasSource.institutionCount} · 看多/增持 {overseasSource.ratingUpCount} · 短线权重 {overseasSource.weightShortSuggest} / 长线 {overseasSource.weightLongSuggest}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            彭博/路透偏外资流向与机构评级、WSJ 偏基本面、Seeking Alpha 偏多空论点；主要作用于长线外资维度（权重 0.18），扫描时作为海外权威情绪面筛选叠加（union，与社区舆情正交）
          </span>
        </div>
        <div style={{ color: '#cbd5e1', fontSize: 13, marginBottom: 10 }}>
          近期海外权威资讯（文档 §一.6：彭博 外资定价权风向标 / 路透 机构资讯与评级 / WSJ 深度基本面 / Seeking Alpha 众包投研）：
        </div>
        {overseas.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>暂无海外权威资讯事件（点击上方「立即运行」将触发海外池惰性刷新）</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>标的</th>
                  <th style={th}>日期</th>
                  <th style={th}>平台</th>
                  <th style={th}>机构</th>
                  <th style={th}>评级</th>
                  <th style={th}>情绪</th>
                  <th style={th}>催化类型</th>
                </tr>
              </thead>
              <tbody>
                {overseas.map((n) => (
                  <tr key={`${n.stockCode}-${n.id ?? n.title}`} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={{ ...td, color: '#e5e7eb' }}>{n.stockName ?? n.stockCode}（{n.stockCode}）</td>
                    <td style={td}>{n.pubDate ?? '—'}</td>
                    <td style={td}>{n.platform ?? '—'}</td>
                    <td style={td}>{n.isInstitution ? <Badge color="#34d399" text="机构" /> : <span style={{ color: '#475569' }}>—</span>}</td>
                    <td style={td}>{n.rating ?? '—'}</td>
                    <td style={{ ...td, color: n.sentiment === '看多' ? '#34d399' : n.sentiment === '看空' ? '#f87171' : '#94a3b8' }}>{n.sentiment ?? '—'}</td>
                    <td style={td}>{n.impactType ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #38 六层信息圈层 + 多源交叉验证（元分析层，蓝图 §四 / §五.1）：把七路源归入 L0~L5 圈层，
          计算共识等级 / 可信度 / 冲突 / 谣言；不改变内核决策权、不扩张候选池。 */}
      <SectionTitle title="六层信息圈层 + 多源交叉验证（#38 · DSA-OPINION-CROSS-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 10, lineHeight: 1.6 }}>
          元分析层：消费 #25 披露 / #28 头条 / #31 微信 / #34 快讯 / #36 社区 / #37 海外 的 per-stock 情感 / 可信度 / 谣言标记，
          归入六层信息圈层（L0 顶层产业知情 → L5 场外路人）；按蓝图 §四 / §五.1 计算共识可信度：单一自媒体爆料 ≤0.3、
          2+ 独立权威平台同步印证 0.7~0.9、散户言论仅作情绪参考。不改变内核决策权。
        </div>

        {/* 圈层命中矩阵（L0~L5） */}
        <div style={{ color: '#38bdf8', fontSize: 13, margin: '6px 0 8px' }}>① 六层信息圈层命中矩阵（本轮扫描）</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
          {(infoLayers?.layers
            ? Object.keys(infoLayers.layers)
                .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))
                .map((L) => ({ L, def: infoLayers.layers[L] }))
            : ['L0', 'L1', 'L2', 'L3', 'L4', 'L5'].map((L) => ({ L, def: null }))
          ).map(({ L, def }) => {
            const hit = (crossValidationSummary?.layerDistribution ?? {})[L] ?? 0;
            const isAuth = (infoLayers?.authoritativeTiers ?? ['L0', 'L1']).includes(L);
            return (
              <div
                key={L}
                style={{
                  background: hit > 0 ? (isAuth ? '#052e2b' : '#1e293b') : '#0b1220',
                  border: `1px solid ${hit > 0 ? (isAuth ? '#10b981' : '#334155') : '#1e293b'}`,
                  borderRadius: 8,
                  padding: 8,
                }}
              >
                <div style={{ color: isAuth ? '#34d399' : '#94a3b8', fontSize: 12, fontWeight: 600 }}>
                  {L} {def ? def.name : ''}
                </div>
                <div style={{ color: '#cbd5e1', fontSize: 11, marginTop: 2 }}>{def ? def.audience : ''}</div>
                <div style={{ color: hit > 0 ? '#fbbf24' : '#475569', fontSize: 14, marginTop: 6, fontWeight: 700 }}>
                  命中 {hit}
                </div>
              </div>
            );
          })}
        </div>

        {/* 共识分布 + 交叉验证指标 */}
        <div style={{ color: '#38bdf8', fontSize: 13, margin: '14px 0 8px' }}>② 共识分布与交叉验证指标</div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          {[
            { k: 'strong', label: '强共识（2+权威）', c: '#34d399' },
            { k: 'moderate', label: '中等（单权威）', c: '#38bdf8' },
            { k: 'weak', label: '弱（仅散户）', c: '#fbbf24' },
            { k: 'none', label: '无信号', c: '#475569' },
          ].map((x) => (
            <div key={x.k} style={{ background: '#0b1220', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 12px' }}>
              <span style={{ color: x.c, fontSize: 18, fontWeight: 700 }}>{(crossValidationSummary?.consensusDistribution ?? {})[x.k] ?? 0}</span>
              <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 6 }}>{x.label}</span>
            </div>
          ))}
          <div style={{ background: '#0b1220', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ color: '#a78bfa', fontSize: 18, fontWeight: 700 }}>{crossValidationSummary?.multiSourceConfirmed ?? 0}</span>
            <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 6 }}>多源确认(≥2源)</span>
          </div>
          <div style={{ background: '#0b1220', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ color: '#f87171', fontSize: 18, fontWeight: 700 }}>{crossValidationSummary?.conflictAlerts ?? 0}</span>
            <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 6 }}>权威×散户冲突</span>
          </div>
          <div style={{ background: '#0b1220', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ color: '#fb923c', fontSize: 18, fontWeight: 700 }}>{crossValidationSummary?.rumorAlerts ?? 0}</span>
            <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 6 }}>谣言待甄别</span>
          </div>
          <div style={{ background: '#0b1220', border: '1px solid #1e293b', borderRadius: 8, padding: '6px 12px' }}>
            <span style={{ color: '#34d399', fontSize: 18, fontWeight: 700 }}>{crossValidationSummary?.technicalBullConfirmed ?? 0}</span>
            <span style={{ color: '#94a3b8', fontSize: 11, marginLeft: 6 }}>#35 技术面多头确认</span>
          </div>
        </div>
        <div style={{ color: '#64748b', fontSize: 11, marginTop: 8 }}>
          可信度阈值（§4）：单一自媒体/散户爆料 ≤ {infoLayers?.credibilityThresholds?.singleRetailCap ?? 0.3} ·
          单权威 {infoLayers?.credibilityThresholds?.singleAuth ?? 0.5} · 2+ 独立权威{' '}
          {infoLayers?.credibilityThresholds?.multiAuthFloor ?? 0.7}~{infoLayers?.credibilityThresholds?.multiAuthCeil ?? 0.9}。
        </div>
      </div>

      {/* #35 可插拔 Kronos 技术面算力底座：NeoQuasar 权重 + BSQ Tokenizer + 分层因果 Transformer，逐 alert 富化 kronosInfo + 三类选股池 */}
      <SectionTitle title="Kronos 技术面算力底座（#35 · DSA-KRONOS-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            技术面算力底座：
            <b style={{ color: kronosSource?.mode === 'real' ? '#34d399' : '#e5e7eb' }}>
              {kronosSource ? (kronosSource.mode === 'real' ? `实时（${kronosSource.modelSpec}）` : '模拟技术面底座') : '加载中…'}
            </b>
            {kronosSource?.provider ? ` · ${kronosSource.provider}` : ''}
          </span>
          {kronosSource && (
            <span style={{ color: '#64748b', fontSize: 12 }}>
              {kronosSource.modelFamily} · 上下文 {kronosSource.contextWindow} 根 K 线 · 已分析 {kronosSource.analyzedCount} 只 · K线权重上限 短线 {kronosSource.weightShortCap} / 长线 {kronosSource.weightLongCap}
            </span>
          )}
          <span style={{ color: '#475569', fontSize: 12 }}>
            Kronos 仅输出技术参考，最终涨跌量化 / 中长期结论由 DSA 数学模型决定（蓝图 §七）
          </span>
        </div>

        {/* 三类选股池（蓝图 §四 能力1） */}
        {(() => {
          const pools = [
            { key: '短线强势池', items: kronosPools?.shortTermStrong ?? [], color: '#34d399', hint: '未来 1~7 日上涨概率＞70% 的多头结构' },
            { key: '趋势反转池', items: kronosPools?.reversal ?? [], color: '#60a5fa', hint: '下跌末端拐点信号' },
            { key: '风险预警池', items: kronosPools?.riskWarning ?? [], color: '#f87171', hint: '放量破位 / 波动率暴涨 / 大概率回调' },
          ];
          return (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
              {pools.map((p) => (
                <div key={p.key} style={{ background: '#111c33', border: `1px solid ${p.color}33`, borderRadius: 8, padding: 10 }}>
                  <div style={{ color: p.color, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                    {p.key}（{p.items.length}）
                  </div>
                  <div style={{ color: '#64748b', fontSize: 11, marginBottom: 8 }}>{p.hint}</div>
                  {p.items.length === 0 ? (
                    <div style={{ color: '#475569', fontSize: 12 }}>暂无标的</div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                            <th style={th}>标的</th>
                            <th style={th}>趋势</th>
                            <th style={th}>拐点</th>
                            <th style={th}>上涨概率</th>
                          </tr>
                        </thead>
                        <tbody>
                          {p.items.slice(0, 10).map((it, i) => (
                            <tr key={it.stockCode ?? i} style={{ borderTop: '1px solid #1e293b' }}>
                              <td style={td}>{it.stockName ?? it.stockCode}</td>
                              <td style={{ ...td, color: it.trend === '多头趋势' ? '#34d399' : it.trend === '空头趋势' ? '#f87171' : '#94a3b8' }}>{it.trend ?? '—'}</td>
                              <td style={{ ...td, color: (it.inflectionPoint ?? '').includes('顶部') ? '#f87171' : (it.inflectionPoint ?? '').includes('底部') ? '#60a5fa' : '#64748b' }}>{it.inflectionPoint ?? '—'}</td>
                              <td style={td}>{it.riseProb != null ? `${(it.riseProb * 100).toFixed(0)}%` : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* #39 舆情回测 + 拐点预警（P2）：各平台情绪因子历史胜率 + 见顶/启动/情绪反转/技术背离分级 */}
      <SectionTitle title="舆情回测 + 拐点预警（#39 · DSA-OPINION-BACKTEST-V1.0）" />
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12, marginBottom: 18 }}>
        <div style={{ color: '#64748b', fontSize: 11, marginBottom: 10 }}>
          沙箱为<b style={{ color: '#94a3b8' }}>确定性模拟回测基线</b>（各源历史情绪序列 + 隐藏真实涨跌因子，真实计算胜率/IC）；真实环境可替换为各源历史情绪 + 后验收益滚动回测。拐点预警消费 #38 交叉验证 + 本回测可靠性 + #35 Kronos 技术面。
        </div>

        {/* 子面板 A：各平台情绪因子历史胜率回测 */}
        <div style={{ color: '#e5e7eb', fontSize: 13, fontWeight: 700, margin: '4px 0 8px' }}>
          各平台情绪因子历史胜率（回测天数 {sentimentBacktest?.nDays ?? '—'} · 覆盖标的 {sentimentBacktest?.universeSize ?? '—'}）
        </div>
        <div style={{ overflowX: 'auto', marginBottom: 14 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                <th style={th}>平台</th>
                <th style={th}>层级</th>
                <th style={th}>样本</th>
                <th style={th}>方向胜率</th>
                <th style={th}>多头胜率</th>
                <th style={th}>空头胜率</th>
                <th style={th}>IC</th>
                <th style={th}>信号方向</th>
                <th style={th}>可靠性</th>
              </tr>
            </thead>
            <tbody>
              {sentimentBacktest && Object.keys(sentimentBacktest.bySource).length > 0 ? (
                Object.keys(sentimentBacktest.bySource)
                  .map((k) => sentimentBacktest.bySource[k])
                  .sort((a, b) => b.ic - a.ic)
                  .map((m) => (
                    <tr key={m.source} style={{ borderTop: '1px solid #1e293b' }}>
                      <td style={{ ...td, color: '#e5e7eb' }}>{m.label}</td>
                      <td style={td}>{m.tier === 'authoritative' ? '权威' : m.tier === 'professional' ? '专业' : '散户'}</td>
                      <td style={td}>{m.samples}</td>
                      <td style={{ ...td, color: m.directionalWinRate >= 0.58 ? '#34d399' : m.directionalWinRate >= 0.5 ? '#fbbf24' : '#f87171' }}>
                        {(m.directionalWinRate * 100).toFixed(1)}%
                      </td>
                      <td style={td}>{(m.longWinRate * 100).toFixed(1)}%</td>
                      <td style={td}>{(m.shortWinRate * 100).toFixed(1)}%</td>
                      <td style={{ ...td, color: m.ic >= 0.3 ? '#34d399' : m.ic >= 0.12 ? '#38bdf8' : m.ic < 0 ? '#f87171' : '#94a3b8' }}>
                        {m.ic.toFixed(2)}
                      </td>
                      <td style={td}>{m.signalDirection}</td>
                      <td style={{ ...td, color: m.reliability === '高' ? '#34d399' : m.reliability === '中' ? '#38bdf8' : '#f87171' }}>
                        {m.reliability}
                      </td>
                    </tr>
                  ))
              ) : (
                <tr><td style={td} colSpan={9}>暂无回测数据（运行闭环扫描以生成覆盖标的）</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {sentimentBacktest?.summary && (
          <div style={{ color: '#64748b', fontSize: 11, marginBottom: 12 }}>
            最强预测源：<b style={{ color: '#34d399' }}>{sentimentBacktest.summary.bestSource ?? '—'}</b>（IC {sentimentBacktest.summary.bestIc.toFixed(2)}）·
            最弱：<b style={{ color: '#f87171' }}>{sentimentBacktest.summary.worstSource ?? '—'}</b>（IC {sentimentBacktest.summary.worstIc.toFixed(2)}）·
            权威平均 IC {sentimentBacktest.summary.authoritativeAvgIc.toFixed(2)} / 散户平均 IC {sentimentBacktest.summary.retailAvgIc.toFixed(2)}
          </div>
        )}

        {/* 子面板 B：拐点预警摘要 */}
        <div style={{ color: '#e5e7eb', fontSize: 13, fontWeight: 700, margin: '4px 0 8px' }}>
          拐点预警摘要（见顶 / 启动 / 情绪反转 / 技术背离）
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
          {[
            { k: 'high', t: '高危拐点', c: '#f87171' },
            { k: 'medium', t: '中等', c: '#fbbf24' },
            { k: 'low', t: '低', c: '#38bdf8' },
            { k: 'none', t: '无信号', c: '#64748b' },
          ].map((x) => (
            <div key={x.k} style={{ textAlign: 'center' }}>
              <div style={{ color: x.c, fontSize: 20, fontWeight: 700 }}>{inflectionSummary?.levelDistribution?.[x.k] ?? 0}</div>
              <div style={{ color: '#64748b', fontSize: 11 }}>{x.t}</div>
            </div>
          ))}
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: '#a78bfa', fontSize: 20, fontWeight: 700 }}>{inflectionSummary?.totalAlerts ?? 0}</div>
            <div style={{ color: '#64748b', fontSize: 11 }}>扫描标的</div>
          </div>
        </div>
        {inflectionSummary && Object.keys(inflectionSummary.typeDistribution).length > 0 ? (
          <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 8 }}>
            命中类型：
            {Object.keys(inflectionSummary.typeDistribution).map((t) => (
              <span key={t} style={{ marginRight: 10, color: '#e5e7eb' }}>
                {t} <b style={{ color: '#f87171' }}>{inflectionSummary.typeDistribution[t]}</b>
              </span>
            ))}
          </div>
        ) : (
          <div style={{ color: '#64748b', fontSize: 12, marginBottom: 8 }}>当前无显著拐点信号</div>
        )}
        {inflectionSummary && inflectionSummary.highInflectionAlerts.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>高危标的</th>
                  <th style={th}>拐点类型</th>
                  <th style={th}>置信度</th>
                  <th style={th}>建议动作</th>
                </tr>
              </thead>
              <tbody>
                {inflectionSummary.highInflectionAlerts.map((h, i) => (
                  <tr key={(h.stockCode ?? '') + i} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={{ ...td, color: '#e5e7eb' }}>{h.stockName ?? h.stockCode}</td>
                    <td style={td}>{(h.types ?? []).join('、')}</td>
                    <td style={{ ...td, color: '#f87171' }}>{h.confidence != null ? `${(h.confidence * 100).toFixed(0)}%` : '—'}</td>
                    <td style={td}>{h.suggestedAction ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* #21 批次历史 */}
      <SectionTitle title="闭环预警扫描批次历史（#21 · 定时/手动/事件）" />
      <div style={{ overflowX: 'auto', marginBottom: 22 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
              <th style={th}>批次</th>
              <th style={th}>触发方式</th>
              <th style={th}>扫描标的</th>
              <th style={th}>强信号</th>
              <th style={th}>中性</th>
              <th style={th}>弱信号</th>
              <th style={th}>Top 标的</th>
              <th style={th}>Top 综合评分</th>
              <th style={th}>运行时间</th>
            </tr>
          </thead>
          <tbody>
            {scanHistory.length === 0 && (
              <tr><td style={td} colSpan={9}>暂无扫描批次（点击上方「立即运行」生成首个批次）</td></tr>
            )}
            {scanHistory.map((b) => (
              <tr key={b.batchId} style={{ borderTop: '1px solid #1e293b' }}>
                <td style={{ ...td, color: '#e5e7eb' }}>{b.batchId}</td>
                <td style={td}>
                  <Badge
                    color={b.runType === 'schedule' ? '#a78bfa' : b.runType === 'event' ? '#fbbf24' : '#60a5fa'}
                    text={b.runType === 'schedule' ? '定时' : b.runType === 'event' ? '事件' : '手动'}
                  />
                </td>
                <td style={td}>{b.totalScanned}</td>
                <td style={{ ...td, color: ALERT_LEVEL_COLOR['强信号·重点关注'] }}>{b.strongCount}</td>
                <td style={{ ...td, color: ALERT_LEVEL_COLOR['中性·持续观察'] }}>{b.neutralCount}</td>
                <td style={{ ...td, color: ALERT_LEVEL_COLOR['弱信号·低关注'] }}>{b.weakCount}</td>
                <td style={td}>{b.topStockName ?? b.topStock ?? '—'}</td>
                <td style={{ ...td, fontWeight: 700 }}>{(b.topComposite * 100).toFixed(1)}</td>
                <td style={td}>{b.startedAt ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!alertScan && (
        <div style={{ color: '#94a3b8', fontSize: 13, padding: 20, background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10 }}>
          点击「立即运行闭环预警」，系统将对大涨回溯池批量跑闭环，并按综合评分降序输出分级预警看板与评分分布。
        </div>
      )}

      {alertScan && (
        <>
          {/* 概览 badges */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <Badge color="#60a5fa" text={`扫描标的：${alertScan.totalScanned} 只`} />
            <Badge color={ALERT_LEVEL_COLOR['强信号·重点关注']} text={`强信号：${strongCount} 只`} />
            <Badge color={ALERT_LEVEL_COLOR['中性·持续观察']} text={`中性：${neutralCount} 只`} />
            <Badge color={ALERT_LEVEL_COLOR['弱信号·低关注']} text={`弱信号：${weakCount} 只`} />
            <Badge color="#64748b" text={`引擎：${alertScan.engine}`} />
          </div>

          {/* 预警分级看板 */}
          <SectionTitle title="闭环预警分级看板（按综合评分降序）" />
          <div style={{ overflowX: 'auto', marginBottom: 18 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
                  <th style={th}>排名</th>
                  <th style={th}>标的</th>
                  <th style={th}>传导产业链</th>
                  <th style={th}>预警级别</th>
                  <th style={th}>综合评分</th>
                  <th style={th}>上涨概率</th>
                  <th style={th}>内核增益</th>
                  <th style={th}>隐藏信号</th>
                  <th style={th}>小众早期</th>
                  <th style={th}>命中因子</th>
                  <th style={th}>披露催化</th>
                  <th style={th}>舆情催化</th>
                  <th style={th}>微信催化</th>
                  <th style={th}>快讯催化</th>
                  <th style={th}>社区热议</th>
                  <th style={th}>海外权威</th>
                  <th style={th}>共识/可信度</th>
                  <th style={th}>拐点预警</th>
                  <th style={th}>Kronos趋势</th>
                  <th style={th}>拐点</th>
                  <th style={th}>Kronos涨概</th>
                </tr>
              </thead>
              <tbody>
                {alerts.length === 0 && (
                  <tr><td style={td} colSpan={21}>本次扫描无有效预警（回溯池暂无标的或闭环全部跳过）</td></tr>
                )}
                {alerts.map((a, i) => (
                  <tr key={a.stockCode} style={{ borderTop: '1px solid #1e293b' }}>
                    <td style={td}>{i + 1}</td>
                    <td style={{ ...td, color: '#e5e7eb' }}>{a.stockName ?? a.stockCode}（{a.stockCode}）</td>
                    <td style={td}>{a.chainId}</td>
                    <td style={td}>
                      <Badge color={ALERT_LEVEL_COLOR[a.level] ?? '#94a3b8'} text={a.level} />
                    </td>
                    <td style={{ ...td, color: ALERT_LEVEL_COLOR[a.level] ?? '#e5e7eb', fontWeight: 700 }}>
                      {(a.compositeScore * 100).toFixed(1)}
                    </td>
                    <td style={{ ...td, color: '#34d399' }}>{(a.predictedProb * 100).toFixed(1)}%</td>
                    <td style={{ ...td, color: '#a78bfa' }}>+{(a.boost * 100).toFixed(1)}%</td>
                    <td style={td}>{a.signalCount}</td>
                    <td style={{ ...td, color: a.earlyCount > 0 ? '#34d399' : '#64748b' }}>{a.earlyCount}</td>
                    <td style={td}>{a.matchedFactors}</td>
                    <td style={td}>
                      {a.hasDisclosure ? (
                        <Badge color="#34d399" text="披露催化" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.hasOpinion ? (
                        <Badge color="#fbbf24" text="舆情催化" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.hasWechat ? (
                        <Badge color="#22d3ee" text="微信催化" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.hasFlash ? (
                        <Badge color="#fbbf24" text="快讯催化" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.hasCommunity ? (
                        <Badge color="#a78bfa" text="社区热议" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.hasOverseas ? (
                        <Badge color="#38bdf8" text="海外权威" />
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.crossValidation ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <Badge
                            color={
                              a.crossValidation.consensusLevel === 'strong'
                                ? '#34d399'
                                : a.crossValidation.consensusLevel === 'moderate'
                                ? '#38bdf8'
                                : a.crossValidation.consensusLevel === 'weak'
                                ? '#fbbf24'
                                : '#475569'
                            }
                            text={
                              a.crossValidation.consensusLevel === 'strong'
                                ? '强共识'
                                : a.crossValidation.consensusLevel === 'moderate'
                                ? '中等'
                                : a.crossValidation.consensusLevel === 'weak'
                                ? '弱(散户)'
                                : '无'
                            }
                          />
                          <span style={{ color: a.crossValidation.conflictFlag ? '#f87171' : '#64748b', fontSize: 10 }}>
                            可信 {a.crossValidation.credibilityScore.toFixed(2)}
                            {a.crossValidation.conflictFlag ? ' · 冲突' : ''}
                            {a.crossValidation.rumorFlag ? ' · 谣言' : ''}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={td}>
                      {a.inflectionWarning && a.inflectionWarning.level !== 'none' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <Badge
                            color={
                              a.inflectionWarning.level === 'high'
                                ? '#f87171'
                                : a.inflectionWarning.level === 'medium'
                                ? '#fbbf24'
                                : '#38bdf8'
                            }
                            text={
                              a.inflectionWarning.level === 'high'
                                ? '高危拐点'
                                : a.inflectionWarning.level === 'medium'
                                ? '中等'
                                : '低'
                            }
                          />
                          <span style={{ color: '#94a3b8', fontSize: 10 }}>
                            {(a.inflectionWarning.types ?? []).filter((t) => t !== '无').join('/') || '—'}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: '#475569' }}>—</span>
                      )}
                    </td>
                    <td style={{ ...td, color: a.kronosInfo?.trend === '多头趋势' ? '#34d399' : a.kronosInfo?.trend === '空头趋势' ? '#f87171' : '#94a3b8' }}>
                      {a.kronosInfo?.trend ?? '—'}
                    </td>
                    <td style={{ ...td, color: a.kronosInfo ? ((a.kronosInfo.inflectionPoint ?? '').includes('顶部') ? '#f87171' : (a.kronosInfo.inflectionPoint ?? '').includes('底部') ? '#60a5fa' : '#64748b') : '#475569' }}>
                      {a.kronosInfo?.inflectionPoint ?? '—'}
                    </td>
                    <td style={{ ...td, color: '#a78bfa' }}>
                      {a.kronosInfo?.riseProb != null ? `${(a.kronosInfo.riseProb * 100).toFixed(0)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 综合评分分布条 */}
          <SectionTitle title="综合预警评分分布" />
          <div style={{ marginBottom: 12 }}>
            {alerts.map((a) => (
              <div key={a.stockCode} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 10, marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e5e7eb', flexWrap: 'wrap', gap: 6 }}>
                  <span>{a.stockName ?? a.stockCode}（{a.stockCode}）</span>
                  <span style={{ color: ALERT_LEVEL_COLOR[a.level] ?? '#94a3b8' }}>{a.level}</span>
                  <span style={{ color: '#94a3b8' }}>评分 {(a.compositeScore * 100).toFixed(1)}</span>
                </div>
                <div style={{ height: 8, background: '#1e293b', borderRadius: 4, marginTop: 8 }}>
                  <div style={{ width: `${a.compositeScore * 100}%`, height: '100%', background: ALERT_LEVEL_COLOR[a.level] ?? '#64748b', borderRadius: 4 }} />
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
};

// ============================ 公共小组件 ============================
const th: React.CSSProperties = { padding: '8px 10px', fontWeight: 600 };
const td: React.CSSProperties = { padding: '8px 10px', color: '#cbd5e1', verticalAlign: 'top' };

function SectionTitle({ title }: { title: string }) {
  return <h2 style={{ fontSize: 16, fontWeight: 600, margin: '10px 0 12px', borderLeft: '3px solid #2563eb', paddingLeft: 10 }}>{title}</h2>;
}

function TabBtn({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontSize: 13, padding: '8px 16px', borderRadius: 8, border: '1px solid',
        borderColor: active ? '#2563eb' : '#1e293b',
        background: active ? '#1e3a8a' : '#0f172a', color: active ? '#fff' : '#94a3b8', cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );
}

function Chip({ ok, label, colorDot }: { ok?: boolean; label: string; colorDot?: string }) {
  const color = colorDot ?? (ok ? '#34d399' : '#f87171');
  return (
    <span style={{ fontSize: 12, padding: '4px 10px', borderRadius: 8, background: color + '22', color, border: `1px solid ${color}55` }}>
      {colorDot ? '● ' : ok ? '✓ ' : '✗ '}
      {label}
    </span>
  );
}

function Badge({ color, text }: { color: string; text: string }) {
  return <span style={{ fontSize: 12, padding: '4px 10px', borderRadius: 8, background: color + '22', color, border: `1px solid ${color}55` }}>{text}</span>;
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: 12 }}>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

function btn(disabled: boolean): React.CSSProperties {
  return {
    fontSize: 12, padding: '6px 12px', borderRadius: 8, border: 'none', background: '#1e293b', color: '#e5e7eb',
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1,
  };
}

export default BacktracePage;
