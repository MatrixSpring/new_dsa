// 反向归因回溯子系统类型（DSA-BACKTRACE-V1.0，对齐 SRS §3.4）

export interface ScreenPoolItem {
  id: number;
  screenDate: string;
  stockCode: string;
  stockName: string;
  dailyGain: number;
  amountYi: number | null;
  industry: string | null;
  riseStartDate: string | null;
  gainType: string | null;
  consecutiveDays: number | null;
}

export interface BacktraceNewsDoc {
  id: number;
  stockCode: string;
  docType: string;
  source: string;
  title: string;
  publishedAt: string;
  isPrior: boolean;
  rawLength: number;
}

export interface DrivingFactor {
  factorType: string; // 核心强驱动 / 次要催化 / 情绪炒作
  content: string;
  weight: number; // 权重占比 %
  confidence: number; // 置信度 0~1
  source: string;
  hiddenConstraint: string;
}

export interface SimilarHistoryCase {
  caseTime: string;
  event: string;
  postTrend: string;
}

export interface Guardrails {
  timeFiltered: boolean;
  priorDocCount: number;
  excludedPostRise: boolean;
  minSourcesEnforced: boolean;
  noSourceConfidenceCapped: number;
  lowConfidenceSuppressed: string[];
  weightsSum: number;
}

export interface AttributionResult {
  attributionId?: number;
  stockCode: string;
  stockName: string;
  riseStartDate: string | null;
  dailyGain: number;
  totalRiseDays: number;
  driveCategory: string; // 基本面事件驱动 / 题材情绪驱动 / 资金筹码驱动
  drivingFactor: DrivingFactor[];
  similarHistoryCase: SimilarHistoryCase[];
  trendPersistenceJudge: string; // 短期脉冲 / 中期趋势 / 长期主升
  suggestAdjust: string;
  guardrails: Guardrails;
  engine: string;
  generatedAt: string;
}

export interface LinkageActions {
  eventLibraryAdded: boolean;
  fundamentalWeightDelta: number;
  chainCoeffDelta: number;
  forecastRecomputeTriggered: boolean;
  forecastRecomputeEndpoint: string;
  caseBanked: boolean;
  note: string;
}

export interface BacktraceSeed {
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
  communities?: CommunityOpinionItem[] | null;
  communitySource?: CommunitySourceInfo | null;
  overseas?: OverseasNewsItem[] | null;
  overseasSource?: OverseasSourceInfo | null;
  kronosSource?: KronosSourceInfo | null;
  kronosPools?: KronosPools | null;
  crossValidationSummary?: CrossValidationSummary | null; // #38 扫描级交叉验证摘要
  infoLayers?: InfoLayers | null; // #38 六层信息圈层定义（前端圈层矩阵渲染）
  sentimentBacktest?: SentimentBacktestReport | null; // #39 各平台情绪因子历史胜率回测报告
  inflectionSummary?: InflectionSummary | null; // #39 扫描级拐点预警摘要
}

// ---- #38 六层信息圈层 + 多源交叉验证（元分析层，蓝图 §四 / §五.1）----
export interface CrossValidationSource {
  source: string; // disclosure / overseas / flash / community / wechat / opinion
  layer: string; // L0~L5 圈层
  tier: string; // authoritative / professional / retail / technical
  direction: string; // bullish / bearish / neutral
  hasRumor: boolean;
}

export interface CrossValidation {
  layersHit: string[]; // 命中的圈层（L0~L5）
  authoritativeCount: number; // 独立权威源数（披露 1 + 海外去重平台）
  retailCount: number; // 散户圈层源数
  distinctSources: number; // 去重源数
  credibilityScore: number; // §4 可信度（单散户 ≤0.3 / 单权威 0.5 / 2+ 权威 0.7~0.9）
  direction: string; // bullish / bearish / neutral
  consensusLevel: string; // strong / moderate / weak / none
  conflictFlag: boolean; // 权威方向 vs 散户方向背离
  rumorFlag: boolean; // 任一命中源疑似谣言
  sources: CrossValidationSource[];
}

export interface CrossValidationSummary {
  totalAlerts: number;
  layerDistribution: Record<string, number>; // L0~L5 → 命中 alert 数
  consensusDistribution: Record<string, number>; // strong / moderate / weak / none
  multiSourceConfirmed: number; // ≥2 去重源确认
  authoritativeConfirmed: number; // 含权威源
  conflictAlerts: number; // 冲突
  rumorAlerts: number; // 谣言
  technicalBullConfirmed: number; // #35 Kronos 技术面多头确认（补充，非信息圈层）
}

export interface InfoLayerDef {
  name: string;
  audience: string;
  horizon: string;
  stage: string;
  role: string;
  tier: number;
}

export interface InfoLayers {
  layers: Record<string, InfoLayerDef>;
  sourceLayerMap: Record<string, { layer: string | null; label: string; tier: string }>;
  authoritativeTiers: string[];
  retailTiers: string[];
  credibilityThresholds: {
    singleRetailCap: number;
    singleAuth: number;
    multiAuthFloor: number;
    multiAuthCeil: number;
  };
}

// ---- #39 舆情回测（各平台情绪因子历史胜率）----
export interface SentimentBacktestItem {
  source: string; // disclosure / overseas / flash / community / wechat / opinion
  label: string; // 可读平台名
  tier: string; // authoritative / professional / retail
  samples: number; // 回测样本日数（= 覆盖标的数 × 回测天数）
  coverage: number; // 覆盖标的数
  bullishDays: number;
  bearishDays: number;
  neutralDays: number;
  directionalWinRate: number; // 信号日方向胜率（情绪方向与次日均値同向占比）
  longWinRate: number; // 看多日次日均値上涨占比
  shortWinRate: number; // 看空日次日均値下跌占比
  ic: number; // 信息系数：情绪与次日均値的秩相关（预测力）
  signalDirection: string; // 同向(正预测) / 反向(反向指标) / 弱相关
  reliability: string; // 高 / 中 / 低（综合 IC 与方向胜率）
}

export interface SentimentBacktestSummary {
  bestSource: string | null; // IC 最高的源
  bestIc: number;
  worstSource: string | null; // IC 最低的源
  worstIc: number;
  tierAvgDirectionalWinRate: Record<string, number>; // 各 tier 平均方向胜率
  authoritativeAvgIc: number; // 权威源平均 IC
  retailAvgIc: number; // 散户源平均 IC
}

export interface SentimentBacktestReport {
  bySource: Record<string, SentimentBacktestItem>;
  nDays: number;
  universeSize: number;
  summary: SentimentBacktestSummary;
  generatedAt: string;
}

// ---- #39 拐点预警 ----
export interface InflectionWarning {
  level: string; // high / medium / low / none
  types: string[]; // 见顶拐点 / 启动拐点 / 情绪反转 / 技术·情绪背离 / 方向冲突 / 无
  reasons: string[];
  confidence: number; // 0~1
  suggestedAction: string; // 减仓/观望 / 逢低布局 / 中性观察
}

export interface InflectionSummary {
  totalAlerts: number;
  levelDistribution: Record<string, number>; // high / medium / low / none
  typeDistribution: Record<string, number>; // 各拐点类型命中数
  highCount: number;
  mediumCount: number;
  lowCount: number;
  noneCount: number;
  highInflectionAlerts: Array<{
    stockCode: string | null;
    stockName: string | null;
    types: string[] | null;
    confidence: number | null;
    suggestedAction: string | null;
  }>;
}

// ---- #20 自动化闭环预警扫描 ----
export interface ClosedLoopAlert {
  stockCode: string;
  stockName: string | null;
  chainId: string | null;
  signalCount: number; // 深挖隐藏信号总数
  earlyCount: number; // 小众早期信号数
  topSignalScore: number; // 最强单条信号评分 0~100
  predictedProb: number; // 正向预判上涨概率 0~1
  boost: number; // 内核传导幅度增益（钳制[0,0.5]）
  matchedFactors: number; // 命中因子数
  compositeScore: number; // 综合预警评分 0~1
  level: string; // 强信号·重点关注 / 中性·持续观察 / 弱信号·低关注
  hasDisclosure: boolean; // 是否命中公开披露催化事件（#25 基本面叠加）
  hasOpinion: boolean; // 是否命中公开舆情催化事件（#28 情绪面叠加）
  hasWechat: boolean; // 是否命中微信私域舆情催化事件（#31 私域情绪面叠加）
  hasFlash: boolean; // 是否命中短线快讯催化事件（#34 短线情绪面叠加）
  hasCommunity: boolean; // 是否命中深度社区舆情催化事件（#36 社区情绪面叠加）
  hasOverseas: boolean; // 是否命中海外权威催化事件（#37 海外权威叠加）
  kronosInfo: KronosSignal | null; // #35 Kronos 技术面算力底座富化：趋势/拐点/三态概率/波动率/量能/Alpha因子
  crossValidation: CrossValidation | null; // #38 六层圈层 + 多源交叉验证元标注（共识/可信度/冲突/谣言）
  inflectionWarning: InflectionWarning | null; // #39 拐点预警元标注（见顶/启动/情绪反转/背离）
}

export interface AlertScanResult {
  scanBatch: string;
  totalScanned: number;
  disclosureCandidates: number; // #25 披露事件池候选标的数（基本面筛选叠加）
  opinionCandidates: number; // #28 舆情事件池候选标的数（情绪面筛选叠加）
  wechatCandidates: number; // #31 微信舆情事件池候选标的数（私域情绪面筛选叠加）
  flashCandidates: number; // #34 快讯事件池候选标的数（短线情绪面筛选叠加）
  communityCandidates: number; // #36 社区讨论事件池候选标的数（社区情绪面筛选叠加）
  overseasCandidates: number; // #37 海外权威资讯事件池候选标的数（海外权威情绪面筛选叠加）
  kronosAnalyzed: number; // #35 Kronos 技术面算力底座：对每只 alert 富化 kronosInfo 的标的数
  crossValidationSummary: CrossValidationSummary; // #38 六层圈层命中 / 共识分布 / 冲突 / 谣言
  inflectionSummary: InflectionSummary; // #39 拐点预警摘要（见顶/启动/情绪反转/背离分级）
  engine: string;
  generatedAt: string;
  alerts: ClosedLoopAlert[];
}

// ---- #23 可插拔实时数据源（mock / AkShare 真实环境适配）----
export interface DataSourceInfo {
  provider: string; // 数据源实现类名（MockMarketProvider / AkShareMarketProvider）
  label: string; // 可读名
  mode: string; // real | mock
  reason: string; // 模式说明 / 回退原因
  surgingCount: number; // 当前大涨池标的数
  envKey: string; // 切换环境变量名
}

// ---- #21 闭环预警自动化调度（定时/事件触发）----
export interface ScanBatch {
  batchId: string;
  runType: string; // manual | schedule | event
  scheduledAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  totalScanned: number;
  strongCount: number; // 强信号·重点关注
  neutralCount: number; // 中性·持续观察
  weakCount: number; // 弱信号·低关注
  topStock: string | null;
  topStockName: string | null;
  topComposite: number; // Top 标的综合预警评分 0~1
  createdAt: string | null;
}

export interface ScheduleConfig {
  cron: string; // 5 段标准表达式（分 时 日 月 周）
  enabled: boolean;
}

export interface ScanRunResult {
  batch: ScanBatch;
  scan: AlertScanResult;
}

// ---- 收尾闭环：深挖 → 预判 → 内核传导 一条龙 ----
export interface ClosedLoopResult {
  stockCode: string;
  stockName: string | null;
  chainId: string;
  shockNode: string;
  dig: AgentDigResult;
  predict: FactorPredictResult;
  propagate: FactorForecastResult;
  engine: string;
  generatedAt: string;
}

// ---- 闭环增强：因子库 → DSA 内核正向传导桥接（内核零改动）----
export interface FactorWeightItem {
  factorName: string;
  factorCategory: string;
  weight: number; // 0~1 归一化
  avgWinRate: number; // 0~1
  confidence: number; // 0~1
  expectancy1m: number; // 期望净收益 %
}

// ---- #22 结构化边注入：按因子类别差异化增强对应产业链边 ----
export interface EdgeOverrideItem {
  source: string;
  target: string;
  edgeType: string; // cost / demand / supply / subst
  baseCoeff: number; // 原始边系数 0~1
  overrideCoeff: number; // 注入后边系数 0~1
  boost: number; // overrideCoeff - baseCoeff（仅增不减）
  categories: string[]; // 贡献的因子类别
}

export interface CategoryEdgeContrib {
  factorCategory: string; // 因子类别
  edgeType: string; // 被增强的产业链边类型
  boost: number; // 该 (类别, 边类型) 的增益
  factors: string[]; // 贡献因子
}

export interface FactorForecastResult {
  chainId: string | null;
  shockNode: string | null;
  baseMagnitude: number;
  boostedMagnitude: number;
  boost: number; // 因子增益（结构化注入总增益，包络幅度增量）
  structuredBoost: number; // #22 结构化注入总增益 0~1（最强通道系数增益）
  edgeOverrides: EdgeOverrideItem[]; // #22 被注入的边明细
  categoryEdgeContrib: CategoryEdgeContrib[]; // #22 类别→边 贡献拆解
  factorWeights: Record<string, number>;
  baseline: { maxImpactPct: number; impactedNodes: number; affectedCompanies: number };
  enhanced: { maxImpactPct: number; impactedNodes: number; affectedCompanies: number };
  liftPct: { maxImpact: number; impactedNodes: number; affectedCompanies: number };
  forward4: { periods: string[]; baseline: number[]; enhanced: number[] };
  factors: FactorWeightItem[];
  engine: string;
  generatedAt: string;
}

// ---- 增强模块：高频上涨因子自动沉淀（因子库 + 正向预判）----
export interface FactorLibraryItem {
  rank?: number;
  factorName: string;
  factorCategory: string; // 基本面事件驱动 / 题材情绪驱动 / 资金筹码驱动
  occurCount: number;
  avgWinRate: number; // 0~1
  avgGain1w: number; // %
  avgGain1m: number; // %
  avgLoss1m: number; // %（负号）
  expectancy1m: number; // 期望 1 月净收益 %
  confidence: number; // 0~1
  sampleStocks: string[];
}

export interface FactorPredictMatched {
  factorName: string;
  factorCategory: string;
  avgWinRate: number; // 0~1
  confidence: number; // 0~1
  occurCount: number;
  expectancy1m: number;
}

export interface FactorPredictResult {
  stockCode: string | null;
  detectedFactors: string[];
  predictedProb: number; // 0~1
  avgExpectancy: number; // %
  suggestion: string;
  matched: FactorPredictMatched[];
  engine: string;
  generatedAt: string;
}

// ---- 因子库累积统计（#24 数据驱动可视化）----
export interface FactorLibraryStats {
  presetCount: number;       // 基线预设因子数
  dbAttributionCount: number; // 已落库真实反向归因条数
  minedFromDb: number;       // 从 DB 归因新挖掘出的独立因子数
  reinforced: number;        // 被真实归因强化的基线因子数
  libraryTotal: number;      // 当前因子库总条目数
  engine: string;
  generatedAt: string;
}

// ---- #25 可插拔公开披露数据源（cninfo / 财报 / 研报）----
export interface DisclosureItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  disclosureDate: string | null;
  title: string;
  category: string; // 业绩预告/重大合同/股权激励/并购重组/财报/研报点评
  summary: string | null;
  sentiment: string | null; // 利好/中性/利空
  createdAt?: string | null;
}

export interface DisclosureSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  disclosureCount: number;
  financialCount: number;
  researchCount: number;
  envKey: string;
}

// ---- #28 可插拔公开舆情数据源（头条爬虫 + FinBERT）----
export interface OpinionItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  opinionDate: string | null;
  title: string;
  source: string | null; // 头条 / 雪球 / 股吧 / Mock
  heatScore: number | null; // 热度指数 0~1
  sentimentScore: number | null; // 情绪得分 -1~1
  sentiment: string | null; // 利好/中性/利空
  stage: string | null; // 萌芽/发酵/狂热/退潮
  summary: string | null;
  hasRumor: boolean; // 疑似谣言（已降权）
  createdAt?: string | null;
}

export interface OpinionSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  opinionCount: number;
  rumorCount: number;
  weightSuggest: number; // 建议 DSA 模型权重（文档 §三，默认 0.15）
  envKey: string;
}

// ---- #31 可插拔微信私域舆情数据源（公众号爬虫 + 视频号爬虫 + FinBERT + 可信度分级）----
export interface WechatOpinionItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  pubDate: string | null;
  title: string;
  source: string | null; // 具体账号 / 渠道名
  carrier: string | null; // 载体：券商公众号/产业垂直号/财经视频号/付费社群线索/其他自媒体
  credibility: string | null; // 可信度：高/中/低
  heatScore: number | null; // 热度指数 0~1
  sentimentScore: number | null; // 情绪得分 -1~1
  sentiment: string | null; // 利好/中性/利空
  stage: string | null; // 萌芽/发酵/狂热/退潮
  hasRumor: boolean; // 疑似谣言（已降权）
  weightSuggest: number | null; // 建议 DSA 短线权重（默认 0.20）
  summary: string | null;
  createdAt?: string | null;
}

export interface WechatSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  wechatCount: number;
  rumorCount: number;
  lowCredibilityCount: number;
  weightShortSuggest: number; // 建议 DSA 短线权重（文档 §二/§五，默认 0.20）
  weightLongSuggest: number; // 建议 DSA 长线权重（默认 0.08）
  envKey: string;
}

// ---- #34 可插拔短线快讯舆情数据源（财联社/华尔街见闻/金十爬虫 + 垂直媒体 + FinBERT + 谣言降权）----
export interface FlashOpinionItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  pubDate: string | null;
  title: string;
  source: string | null; // 具体渠道名（财联社/华尔街见闻/金十/e公司...）
  mediaType: string | null; // 快讯 / 深度媒体
  isBreaking: boolean; // 盘中/早盘突发催化（短线节奏核心信号）
  heatScore: number | null; // 热度指数 0~1
  sentimentScore: number | null; // 情绪得分 -1~1
  sentiment: string | null; // 利好/中性/利空
  stage: string | null; // 萌芽/发酵/狂热/退潮
  hasRumor: boolean; // 疑似谣言（已降权）
  weightSuggest: number | null; // 建议 DSA 短线权重（默认 0.22）
  summary: string | null;
  createdAt?: string | null;
}

export interface FlashSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  flashCount: number;
  rumorCount: number;
  breakingCount: number; // 盘中/早盘突发催化事件数
  weightShortSuggest: number; // 建议 DSA 短线权重（文档 §一.2/§五.2，默认 0.22）
  weightLongSuggest: number; // 长线参考值（§一.2，未纳入 §五.2 长线合并模型）
  envKey: string;
}

// ---- #36 可插拔深度社区舆情数据源（雪球/东财股吧/淘股吧爬虫 + 质量分层 + FinBERT + 谣言降权）----
export interface CommunityOpinionItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  pubDate: string | null;
  title: string;
  platform: string | null; // 平台（雪球/东财股吧/淘股吧）
  quality: string | null; // 质量分层（高质量/普通/噪音）
  isHot: boolean; // 登社区热榜/热帖榜（短线情绪风向标）
  postCount: number | null; // 讨论/帖子数
  discussionHeat: number | null; // 讨论热度 0~1
  sentimentScore: number | null; // 情绪得分 -1~1
  sentiment: string | null; // 看多/中性/看空
  hasRumor: boolean; // 疑似谣言（已降权）
  weightSuggest: number | null; // 建议 DSA 短线权重（默认 0.13）
  summary: string | null;
  createdAt?: string | null;
}

export interface CommunitySourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  communityCount: number;
  rumorCount: number;
  hotCount: number; // 登社区热榜讨论数
  weightShortSuggest: number; // 建议 DSA 短线权重（文档 §一.2，默认 0.13）
  weightLongSuggest: number; // 长线参考值（社区对中长线影响弱，默认 0.05）
  envKey: string;
}

// ---- #37 可插拔海外权威舆情数据源（彭博/路透/WSJ/Seeking Alpha + 机构评级 + 外资流向）----
export interface OverseasNewsItem {
  id?: number;
  stockCode: string;
  stockName: string | null;
  pubDate: string | null;
  title: string;
  platform: string | null; // 平台（彭博/路透/WSJ/Seeking Alpha）
  region: string | null; // 区域（海外）
  isInstitution: boolean; // 机构评级/研报事件（外资定价权确认）
  rating: string | null; // 增持/中性/减持/无
  sentimentScore: number | null; // 情绪得分 -1~1
  sentiment: string | null; // 看多/中性/看空
  impactType: string | null; // 外资流向/评级调整/基本面/宏观
  weightSuggest: number | null; // 建议 DSA 权重（短线 0.14 / 机构 0.18）
  summary: string | null;
  createdAt?: string | null;
}

export interface OverseasSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  overseasCount: number;
  institutionCount: number; // 机构评级/研报事件数
  ratingUpCount: number; // 看多/增持评级数
  weightShortSuggest: number; // 建议 DSA 短线权重（文档 §一.6，默认 0.14）
  weightLongSuggest: number; // 长线外资维度（§五.2 保留彭博/路透系，默认 0.18）
  envKey: string;
}

// ---- #35 可插拔 Kronos 技术面算力底座（NeoQuasar 权重 + BSQ Tokenizer + 分层因果 Transformer）----
export interface KronosSignal {
  id?: number;
  stockCode: string;
  stockName: string | null;
  trend: string | null; // 多头趋势/空头趋势/震荡
  momentum: number | null; // 趋势强度 0~1
  inflectionPoint: string | null; // 无顶部拐点/顶部拐点·高位见顶/底部拐点·下跌末端反转
  riseProb: number | null; // 上涨概率 0~1
  sidewayProb: number | null; // 横盘概率 0~1
  downProb: number | null; // 下跌概率 0~1
  volatility: number | null; // 波动率 0~1
  volumeScore: number | null; // 量能评分 0~1
  persistence: string | null; // 持续性文本
  factorScores: Array<{ name: string; score: number }> | null; // BSQ Tokenizer 派生候选 Alpha 因子
  createdAt?: string | null;
}

export interface KronosSourceInfo {
  provider: string;
  label: string;
  mode: string; // real | mock
  reason: string;
  modelFamily: string; // NeoQuasar（AAAI2026 金融 K 线基础模型）
  modelSpec: string; // small（P0 轻量化部署）
  contextWindow: number; // 最大上下文窗口（根 K 线）
  weightShortCap: number; // K 线信号短线权重硬上限（蓝图 §七，0.35）
  weightLongCap: number; // K 线信号长线权重硬上限（蓝图 §七，0.15）
  analyzedCount: number;
  envKey: string;
}

export interface KronosPools {
  shortTermStrong: KronosSignal[]; // 短线强势池（未来 1~7 日上涨概率＞70% 的多头结构）
  reversal: KronosSignal[]; // 趋势反转池（下跌末端拐点信号）
  riskWarning: KronosSignal[]; // 风险预警池（放量破位/波动率暴涨/大概率回调）
}

// ---- 增强模块：Agent 自主深挖小众突发事件 ----
export interface AgentSignal {
  id?: number;
  stockCode: string;
  stockName: string | null;
  signalType: string; // 机构调研 / 产业链异动 / 舆情小道消息 / 游资动向
  signalDate: string; // YYYY-MM-DD（拉升前）
  leadDays: number; // 距拉升起始日的提前天数
  source: string;
  summary: string;
  credibility: number; // 0~1
  relevance: number; // 0~1
  score: number; // 0~100
  isEarly: boolean; // 是否小众早期信号
}

export interface AgentTimelinePoint {
  signalDate: string;
  signalType: string;
  leadDays: number;
  score: number;
  isEarly: boolean;
}

export interface AgentDigResult {
  stockCode: string;
  stockName: string | null;
  riseStartDate: string;
  windowDays: number;
  signalCount: number;
  earlyCount: number; // 小众早期信号数量
  typeDistribution: Record<string, number>;
  signals: AgentSignal[]; // 按综合得分降序
  timeline: AgentTimelinePoint[]; // 按日期升序
  engine: string;
  generatedAt: string;
}

// ---- 模块 6：批量板块复盘（SRS §3.6）----
export interface SectorMemberProfile {
  stockCode: string;
  stockName: string;
  dailyGain: number;
  gainType: string;
  consecutiveDays: number;
  driveCategory: string; // 基本面事件驱动 / 题材情绪驱动 / 资金筹码驱动
  coreWeight: number;
  emotionWeight: number;
  trendJudge: string; // 短期脉冲 / 中期趋势 / 长期主升
  topDriver: string;
}

export interface CommonDriver {
  driver: string;
  hitStocks: number;
  share: number; // %
}

export interface SectorAggregate {
  memberCount: number;
  strongRate: number; // %
  avgCoreWeight: number;
  categoryDistribution: Record<string, number>;
  trendDistribution: Record<string, number>;
}

export interface SectorReviewResult {
  reviewId?: number;
  sector: string;
  riseDate: string | null;
  memberCount: number;
  prosperity: string; // 景气主升 / 景气上行（分化）/ 情绪脉冲 / 板块退潮
  rotationLogic: string;
  conductionChain: string[];
  commonDrivers: CommonDriver[];
  aggregate: SectorAggregate;
  perStock: SectorMemberProfile[];
  engine: string;
  generatedAt: string;
}

// ---- 模块 7：归因有效性回测校验（SRS §3.7）----
export interface MatchedBucket {
  factor: string;
  bucket: string; // 历史样本桶（业绩订单 / 产业政策 / 情绪游资 ...）
  weight: number;
  winRate: number; // 0~1
  avgGain1m: number; // %
  samples: number;
}

export interface BacktestResult {
  backtestId?: number;
  attributionId: number;
  stockCode: string;
  stockName: string;
  driveCategory: string | null;
  samples: number;
  winRate: number; // 0~1
  avgGain1w: number; // %
  avgGain1m: number; // %
  avgLoss1m: number; // %（负号）
  expectancy1m: number; // 期望 1 月净收益 %
  confidenceRaw: number; // 0~1
  confidenceAdjusted: number; // 0~1
  adjustment: string;
  verdict: string;
  matchedBuckets: MatchedBucket[];
  engine: string;
  generatedAt: string;
}

/** 归因列表摘要（回测 Tab 下拉选择用） */
export interface AttributionSummary {
  attributionId: number;
  stockCode: string;
  stockName: string;
  driveCategory: string | null;
  trendJudge: string | null;
}
