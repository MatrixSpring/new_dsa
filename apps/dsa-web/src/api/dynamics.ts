/**
 * 动态聚合页 API 层（设计 §2.1/§2.2/§2.3）
 * 复用 apiClient（baseURL 同源 /api...）。注意两种响应契约：
 *  - intelligence/items：裸响应 {items,total,page,pageSize}
 *  - dashboard 端点：{code,msg,data} 包裹，取 .data
 */
import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  GameLongData,
  GameShortData,
  IntelligenceItemList,
  IntelligenceMarket,
  MarketTrendData,
  PolicyTrackData,
  RiskOverviewData,
  StockRecentData,
} from '../types/dynamics';

export interface IntelligenceQuery {
  market?: IntelligenceMarket;
  scopeType?: string;
  scopeValue?: string;
  query?: string;
  days?: number;
  page?: number;
  pageSize?: number;
}

export const dynamicsApi = {
  /** 情报条目列表（裸响应，无 code 包裹） */
  getIntelligenceItems: async (params: IntelligenceQuery = {}): Promise<IntelligenceItemList> => {
    const response = await apiClient.get<IntelligenceItemList>('/api/v1/intelligence/items', {
      params,
    });
    const body = (response.data ?? {}) as Partial<IntelligenceItemList>;
    return toCamelCase<IntelligenceItemList>({
      items: body.items ?? [],
      total: body.total ?? 0,
      page: body.page ?? 1,
      pageSize: body.pageSize ?? 50,
    });
  },

  /** 市场趋势 + 行业热度（{code,msg,data}） */
  getMarketTrend: async (timeRange = '7d'): Promise<MarketTrendData> => {
    const response = await apiClient.get<{ data?: MarketTrendData }>('/api/v1/market/trend', {
      params: { timeRange },
    });
    return toCamelCase<MarketTrendData>(response.data?.data ?? ({} as MarketTrendData));
  },

  /** 国家政策赛道（{code,msg,data}） */
  getPolicyTrack: async (): Promise<PolicyTrackData> => {
    const response = await apiClient.get<{ data?: PolicyTrackData }>('/api/v1/policy/track');
    return toCamelCase<PolicyTrackData>(response.data?.data ?? { tracks: [] });
  },

  /** 个人标的中心（{code,msg,data}） */
  getStockRecent: async (): Promise<StockRecentData> => {
    const response = await apiClient.get<{ data?: StockRecentData }>('/api/v1/stock/recent');
    return toCamelCase<StockRecentData>(response.data?.data ?? { type: 'select', stocks: [] });
  },

  /** 短线资金博弈（{code,msg,data}） */
  getGameShort: async (timeRange = '7d'): Promise<GameShortData> => {
    const response = await apiClient.get<{ data?: GameShortData }>('/api/v1/game/short', {
      params: { timeRange },
    });
    return toCamelCase<GameShortData>(response.data?.data ?? {
      mainFundList: [],
      northFundList: [],
      gameScore: 50,
      abnormalStockList: [],
    });
  },

  /** 长线赛道博弈（{code,msg,data}） */
  getGameLong: async (timeRange = '30d'): Promise<GameLongData> => {
    const response = await apiClient.get<{ data?: GameLongData }>('/api/v1/game/long', {
      params: { timeRange },
    });
    return toCamelCase<GameLongData>(response.data?.data ?? {
      industryRotateList: [],
      institutionTrackList: [],
      baseGameScore: 50,
    });
  },

  /** 全维度风控（{code,msg,data}） */
  getRiskOverview: async (): Promise<RiskOverviewData> => {
    const response = await apiClient.get<{ data?: RiskOverviewData }>('/api/v1/risk/overview');
    return toCamelCase<RiskOverviewData>(response.data?.data ?? {
      riskStat: {},
      riskStockList: [],
      systemRisk: { interfaceFailRate: 0, cacheHitRate: 0, reconnectCount: 0 },
      blackListCount: 0,
    });
  },
};
