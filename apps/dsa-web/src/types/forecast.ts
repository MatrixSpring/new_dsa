/**
 * 多模型共识推演 — 前端类型定义
 * 与后端 api/v1/schemas/forecast.py 对齐
 */

export interface WeightConfigItem {
  name: string;
  weight: number;
  win_rate?: number;
}

export interface ModelDetailItem {
  name: string;
  score: number;
  confidence: number;
  dynamic_weight: number;
  status: 'normal' | 'diverge' | 'error';
  desc: string;
}

export interface ProcessLogItem {
  time: string;
  msg: string;
  type: 'info' | 'success' | 'warn' | 'error';
}

export interface ConsensusResult {
  consensus_score: number;
  trend: 'up' | 'down' | 'oscillation';
  confidence: number;
  valid_model_count: number;
  total_model_count: number;
  diverge_level: number; // 0=无 1=轻微 2=显著
}

export interface ChartModelDataItem {
  name: string;
  score: number;
  confidence: number;
  weight: number;
}

export interface ChartConsensusDataItem {
  label: string;
  consensus_score: number;
}

export interface MultiConsensusData {
  consensus: ConsensusResult;
  model_detail: ModelDetailItem[];
  chart_model_data: ChartModelDataItem[];
  chart_consensus_data: ChartConsensusDataItem[];
  process_logs: ProcessLogItem[];
}

export interface MultiConsensusResponse {
  code: number;
  msg: string;
  data: MultiConsensusData | null;
}

export interface MultiConsensusRequest {
  weight_config: WeightConfigItem[];
  stock_code?: string;
}

/* ------------------------------------------------------------------ *
 * 多周期前瞻预测（设计 §3 / §4.3）
 * 后端返回 snake_case，前端经 toCamelCase 深度转换为 camelCase。
 * ------------------------------------------------------------------ */

export type ForecastCycleKey = '1w' | '2w' | '1m' | '6m';
export type ForecastMarket = 'A' | 'HK' | 'US';
export type ForecastDirection = 'up' | 'down' | 'oscillation';
export type ForecastMode = 'synthetic' | 'live';

/** 单个标的在某一周期下的标准化预测（设计 §3.5 模板） */
export interface SymbolCycleForecast {
  cycle: ForecastCycleKey;
  cycleDays: number;
  designDays: number;
  direction: ForecastDirection;
  directionLabel: string;
  consensusScore: number;
  upProbability: number;
  confidence: number;
  priceRange: { low: number; high: number };
  volatilityRangePct: { low: number; high: number };
  coreDrivers: string[];
  mainRisks: string[];
  subModelScores: Record<string, number>;
}

/** 单个标的的四周期预测聚合 */
export interface SymbolForecast {
  symbol: string;
  name: string;
  market: ForecastMarket;
  cycles: Record<ForecastCycleKey, SymbolCycleForecast>;
}

/** /predict/multi-cycle 请求体 */
export interface MultiCycleRequest {
  symbols: string[];
  market?: ForecastMarket;
  cycles?: ForecastCycleKey[];
  mode?: ForecastMode;
  seed?: number | null;
}

/** /predict/multi-cycle 响应 data 字段 */
export interface MultiCycleData {
  symbols: Record<string, SymbolForecast>;
  cyclesRequested: ForecastCycleKey[];
  mode: ForecastMode;
  generatedAt: string;
}

export interface MultiCycleResponse {
  code: number;
  msg: string;
  data: MultiCycleData;
}

/** /predict/dsa-propagation 请求体 */
export interface DsaPropagationRequest {
  graph: Record<string, unknown>;
  shock: Record<string, unknown>;
}

export interface DsaNodeImpact {
  node: string;
  nodeName?: string;
  depth: number;
  impact: number;
  kind?: string;
}

export interface DsaCompanyImpact {
  symbol: string;
  name?: string;
  totalImpact: number;
  upstreamImpact: number;
  downstreamImpact: number;
}

export interface DsaPropagationData {
  nodeImpacts: DsaNodeImpact[];
  companyImpacts: DsaCompanyImpact[];
  summary: {
    maxAbsImpact: number;
    affectedNodes: number;
    affectedCompanies: number;
  };
}

export interface DsaPropagationResponse {
  code: number;
  msg: string;
  data: DsaPropagationData;
}
