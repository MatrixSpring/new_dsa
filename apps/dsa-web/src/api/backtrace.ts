import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  AgentDigResult,
  AgentSignal,
  AttributionResult,
  AttributionSummary,
  BacktestResult,
  BacktraceNewsDoc,
  ClosedLoopResult,
  AlertScanResult,
  ClosedLoopAlert,
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
  KronosSourceInfo,
  KronosPools,
  CrossValidation,
  CrossValidationSummary,
  InfoLayers,
  SentimentBacktestReport,
  InflectionSummary,
  ScanBatch,
  ScheduleConfig,
  ScanRunResult,
  FactorForecastResult,
  FactorLibraryItem,
  FactorLibraryStats,
  FactorPredictResult,
  LinkageActions,
  ScreenPoolItem,
  SectorReviewResult,
} from '../types/backtrace';

export const backtraceApi = {
  /** GET /api/v1/backtrace/screen-pool 查询大涨回溯池（§3.1） */
  screenPool: async (
    date?: string
  ): Promise<{ code: number; data: { screenDate: string; count: number; items: ScreenPoolItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/screen-pool', {
      params: { date },
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/backtrack 回溯单只个股拉升前历史资讯（§3.2） */
  backtrack: async (
    stockCode: string,
    windowDays = 30
  ): Promise<{
    code: number;
    data: { stockCode: string; priorCount: number; excludedCount: number; docs: BacktraceNewsDoc[] };
  }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/backtrack', {
      stock_code: stockCode,
      window_days: windowDays,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/attribute 反向归因全链路（§3.3 / §3.4） */
  attribute: async (stockCode: string): Promise<{ code: number; data: AttributionResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/attribute', {
      stock_code: stockCode,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/link 归因结果联动 DSA 系统（§3.5） */
  link: async (
    attributionId: number
  ): Promise<{ code: number; data: { actions: LinkageActions } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/link', {
      attribution_id: attributionId,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/sector-review 批量板块复盘（§3.6） */
  sectorReview: async (
    sector: string
  ): Promise<{ code: number; data: SectorReviewResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/sector-review', {
      sector,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/attributions 归因列表（回测 Tab 选择用） */
  attributions: async (): Promise<{ code: number; data: { total: number; items: AttributionSummary[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/attributions');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/backtest 归因有效性回测校验（§3.7） */
  backtest: async (
    attributionId: number
  ): Promise<{ code: number; data: BacktestResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/backtest', {
      attribution_id: attributionId,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/agent-dig Agent 自主深挖小众突发事件（增强模块） */
  agentDig: async (
    stockCode: string,
    windowDays = 30
  ): Promise<{ code: number; data: AgentDigResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/agent-dig', {
      stock_code: stockCode,
      window_days: windowDays,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/agent-signals 查询 Agent 深挖信号 */
  agentSignals: async (
    stockCode: string
  ): Promise<{ code: number; data: { total: number; items: AgentSignal[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/agent-signals', {
      params: { stock_code: stockCode },
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/factor-mine 高频上涨因子自动沉淀（构建因子库） */
  factorMine: async (): Promise<{ code: number; data: { total: number; items: FactorLibraryItem[]; minedFromDb: number; reinforced: number } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/factor-mine', {
      recompute: true,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/factor-library 查询沉淀因子库 */
  factorLibrary: async (
    sortBy: string = 'heat'
  ): Promise<{ code: number; data: { total: number; items: FactorLibraryItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/factor-library', {
      params: { sort_by: sortBy },
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/factor-library/stats 因子库累积统计（#24 数据驱动） */
  factorLibraryStats: async (): Promise<{ code: number; data: FactorLibraryStats }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/factor-library/stats');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/factor-predict 正向预判：早期信号 → 上涨概率 */
  factorPredict: async (
    detectedFactors: string[],
    stockCode?: string
  ): Promise<{ code: number; data: FactorPredictResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/factor-predict', {
      detected_factors: detectedFactors,
      stock_code: stockCode,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/industry-chains/{chainId}/factor-forecast 因子库 → DSA 内核正向传导桥接 */
  factorForecast: async (payload: {
    chainId: string;
    shock: { node: string; magnitude: number; kind: string };
    topN?: number;
    minConfidence?: number;
    category?: string;
  }): Promise<{ code: number; data: FactorForecastResult }> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/industry-chains/${payload.chainId}/factor-forecast`,
      {
        shock: payload.shock,
        top_n: payload.topN ?? 6,
        min_confidence: payload.minConfidence ?? 0.6,
        category: payload.category,
      }
    );
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop 一键闭环：深挖 → 预判 → 内核传导 */
  closedLoop: async (
    stockCode: string,
    chainId?: string
  ): Promise<{ code: number; data: ClosedLoopResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop', {
      stock_code: stockCode,
      chain_id: chainId,
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/scan 自动化闭环预警扫描：批量跑闭环并分级预警（#20） */
  closedLoopScan: async (
    watchlist?: string[],
    limit?: number
  ): Promise<{ code: number; data: AlertScanResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan', {
      watchlist: watchlist ?? null,
      limit: limit ?? null,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/alerts 查询最近一次扫描批次的预警结果（#20） */
  closedLoopAlerts: async (
    limit: number = 50
  ): Promise<{ code: number; data: { batch: string | null; total: number; items: ClosedLoopAlert[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/alerts', {
      params: { limit },
    });
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/scan/run 调度触发：手动/定时/事件跑闭环预警并落批次（#21） */
  closedLoopScanRun: async (
    runType: string = 'manual',
    watchlist?: string[]
  ): Promise<{ code: number; data: ScanRunResult }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/run', {
      run_type: runType,
      watchlist: watchlist ?? null,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/scan/history 查询扫描批次历史（#21） */
  scanHistory: async (
    limit: number = 20
  ): Promise<{ code: number; data: { total: number; items: ScanBatch[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/history', {
      params: { limit },
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/scan/schedule 读取调度配置（#21） */
  getSchedule: async (): Promise<{ code: number; data: ScheduleConfig }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/schedule');
    return toCamelCase(response.data);
  },

  /** PUT /api/v1/backtrace/closed-loop/scan/schedule 更新调度配置（#21） */
  setSchedule: async (
    cron?: string,
    enabled?: boolean
  ): Promise<{ code: number; data: ScheduleConfig }> => {
    const response = await apiClient.put<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/schedule', {
      cron: cron ?? null,
      enabled: enabled ?? null,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/scan/source 查询当前活跃数据源（#23 真实环境适配） */
  dataSource: async (): Promise<{ code: number; data: DataSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/scan/refresh-pool 用活跃数据源刷新当日大涨回溯池（#23） */
  refreshPool: async (
    limit: number = 200
  ): Promise<{ code: number; data: { mode: string; provider: string; screenDate: string; count: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/scan/refresh-pool', null, {
      params: { limit },
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/disclosure/source 查询当前活跃公开披露源（#25） */
  disclosureSource: async (): Promise<{ code: number; data: DisclosureSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/disclosure/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/disclosure/refresh 用活跃披露源重写披露事件池（#25） */
  disclosureRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; disclosureDate: string; count: number; financialCount: number; researchCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/disclosure/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/disclosures 查询当前披露事件池（#25） */
  disclosures: async (): Promise<{ code: number; data: { count: number; items: DisclosureItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/disclosures');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/opinion/source 查询当前活跃公开舆情源（#28） */
  opinionSource: async (): Promise<{ code: number; data: OpinionSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/opinion/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/opinion/refresh 用活跃舆情源重写舆情事件池（#28） */
  opinionRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; opinionDate: string; count: number; rumorCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/opinion/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/opinions 查询当前舆情事件池（#28） */
  opinions: async (): Promise<{ code: number; data: { count: number; items: OpinionItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/opinions');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/wechat/source 查询当前活跃微信舆情源（#31） */
  wechatSource: async (): Promise<{ code: number; data: WechatSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/wechat/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/wechat/refresh 用活跃微信舆情源重写微信舆情事件池（#31） */
  wechatRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; pubDate: string; count: number; rumorCount: number; lowCredibilityCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/wechat/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/wechats 查询当前微信舆情事件池（#31） */
  wechats: async (): Promise<{ code: number; data: { count: number; items: WechatOpinionItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/wechats');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/flash/source 查询当前活跃短线快讯源（#34） */
  flashSource: async (): Promise<{ code: number; data: FlashSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/flash/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/flash/refresh 用活跃快讯源重写快讯事件池（#34） */
  flashRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; pubDate: string; count: number; rumorCount: number; breakingCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/flash/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/flashes 查询当前快讯事件池（#34） */
  flashes: async (): Promise<{ code: number; data: { count: number; items: FlashOpinionItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/flashes');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/community/source 查询当前活跃深度社区舆情源（#36） */
  communitySource: async (): Promise<{ code: number; data: CommunitySourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/community/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/community/refresh 用活跃社区源重写社区讨论事件池（#36） */
  communityRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; pubDate: string; count: number; rumorCount: number; hotCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/community/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/communities 查询当前社区讨论事件池（#36） */
  communities: async (): Promise<{ code: number; data: { count: number; items: CommunityOpinionItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/communities');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/overseas/source 查询当前活跃海外权威舆情源（#37） */
  overseasSource: async (): Promise<{ code: number; data: OverseasSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/overseas/source');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/overseas/refresh 用活跃海外源重写海外权威资讯事件池（#37） */
  overseasRefresh: async (
    stockCodes?: string[],
    days: number = 7
  ): Promise<{ code: number; data: { mode: string; provider: string; pubDate: string; count: number; institutionCount: number; ratingUpCount: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/overseas/refresh', {
      stock_codes: stockCodes ?? null,
      days,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/overseas 查询当前海外权威资讯事件池（#37） */
  overseas: async (): Promise<{ code: number; data: { count: number; items: OverseasNewsItem[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/overseas');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/kronos/source 查询当前活跃 Kronos 技术面底座（#35） */
  kronosSource: async (): Promise<{ code: number; data: KronosSourceInfo }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/kronos/source');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/info-layers 查询六层信息圈层定义（#38） */
  infoLayers: async (): Promise<{ code: number; data: InfoLayers }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/info-layers');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/cross-validation 查询多源交叉验证摘要（#38） */
  crossValidation: async (): Promise<{ code: number; data: CrossValidationSummary }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/cross-validation');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/sentiment-backtest 查询各平台情绪因子历史胜率回测（#39） */
  sentimentBacktest: async (): Promise<{ code: number; data: SentimentBacktestReport }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/sentiment-backtest');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/inflection-warnings 查询拐点预警摘要（#39） */
  inflectionWarnings: async (): Promise<{ code: number; data: InflectionSummary }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/inflection-warnings');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/backtrace/closed-loop/kronos/refresh 用 Kronos 批量技术分析（#35） */
  kronosRefresh: async (
    stockCodes?: string[]
  ): Promise<{ code: number; data: { mode: string; provider: string; model: string; analyzed: number; shortTermStrong: number; reversal: number; riskWarning: number; reason: string } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/backtrace/closed-loop/kronos/refresh', {
      stock_codes: stockCodes ?? null,
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/kronos/signals 查询当前 Kronos 技术面信号（#35） */
  kronosSignals: async (): Promise<{ code: number; data: { count: number; items: KronosSignal[] } }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/kronos/signals');
    return toCamelCase(response.data);
  },

  /** GET /api/v1/backtrace/closed-loop/kronos/pools 查询三类选股池（#35） */
  kronosPools: async (): Promise<{ code: number; data: KronosPools }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtrace/closed-loop/kronos/pools');
    return toCamelCase(response.data);
  },
};
