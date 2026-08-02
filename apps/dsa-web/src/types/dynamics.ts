/**
 * 动态聚合页（设计 §2.1/§2.2/§2.3：全球动态 / 国内动态 / 单日动态）
 * 复用现有 dashboard + intelligence 接口，类型对齐后端 snake_case（经 toCamelCase 映射）。
 */

/* ============ 情报条目（intelligence/items，裸响应，无 {code,data} 包裹） ============ */

export type IntelligenceMarket =
  | 'cn'
  | 'hk'
  | 'us'
  | 'jp'
  | 'kr'
  | 'tw'
  | 'global';

export type IntelligenceScopeType = 'symbol' | 'market' | 'sector';

export interface IntelligenceItem {
  id: number;
  sourceId?: number | null;
  sourceName?: string | null;
  sourceType: string;
  title: string;
  summary?: string | null;
  url: string;
  source?: string | null;
  publishedAt?: string | null;
  fetchedAt?: string | null;
  scopeType: string;
  scopeValue?: string | null;
  market: string;
}

export interface IntelligenceItemList {
  items: IntelligenceItem[];
  total: number;
  page: number;
  pageSize: number;
}

/* ============ 仪表盘端点（{code,msg,data} 包裹，取 data） ============ */

export interface MarketTrendData {
  indexList: { name: string; code: string; trend: number[]; changePct: number }[];
  trendScore: number;
  trendStatus: string;
  industryHotList: { name: string; boomScore: number; rankDesc: string }[];
  abnormalTip: string;
}

export interface PolicyTrackItem {
  trackName: string;
  policyDesc: string;
  policyLevel: string;
  trendScore: number;
  financeScore: number;
  fundScore: number;
  boomScore: number;
  rankDesc: string;
  topStockList: unknown[];
}

export interface PolicyTrackData {
  tracks: PolicyTrackItem[];
}

export interface StockRecentItem {
  stockCode: string;
  stockName: string;
  price: number;
  changeRate: number;
  volumeRatio: number;
  rsi: number;
  mainNetIn: number;
  riskLevel: string;
  totalScore: number;
  industry: string;
  filterReason: string;
  isAbnormal: boolean;
}

export interface StockRecentData {
  type: string;
  stocks: StockRecentItem[];
}

export interface GameShortData {
  mainFundList: { code: string; name: string; mainNetIn: number; turnover: number }[];
  northFundList: { code: string; name: string; northNetIn: number }[];
  gameScore: number;
  abnormalStockList: unknown[];
}

export interface GameLongItem {
  name: string;
  boomScore: number;
  fundScore: number;
  rankDesc: string;
}

export interface GameLongData {
  industryRotateList: GameLongItem[];
  institutionTrackList: unknown[];
  baseGameScore: number;
}

export interface RiskOverviewData {
  riskStat: Record<string, number>;
  riskStockList: unknown[];
  systemRisk: {
    interfaceFailRate: number;
    cacheHitRate: number;
    reconnectCount: number;
  };
  blackListCount: number;
}

/* ============ 聚合页 variant 配置 ============ */

export type DynamicsVariant = 'global' | 'domestic' | 'daily';

export type DynamicsPanelKey =
  | 'marketTrend'
  | 'policyTrack'
  | 'stockRecent'
  | 'gameShort'
  | 'gameLong'
  | 'riskOverview';

export interface DynamicsVariantConfig {
  title: string;
  subtitle: string;
  /** 若设置，则展示情报信息流并按该 market 过滤 */
  intelligenceMarket?: IntelligenceMarket;
  /** 中间区依次渲染的仪表盘面板 */
  panels: DynamicsPanelKey[];
}
