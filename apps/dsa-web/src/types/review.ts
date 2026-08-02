// 预测复盘归因类型（对齐 core/review_scorer.py，响应经 toCamelCase 映射）
export type ReviewDirection = 'up' | 'down' | 'oscillation';
export type ReviewLayerKey = 'data_layer' | 'model_layer' | 'logic_layer';

export interface LayerScore {
  score: number;
  note: string;
}

// 请求体使用 snake_case（后端 pydantic 直接解析）
export interface ReviewCycleInput {
  cycle: string;
  direction: string;
  consensus_score: number;
  up_probability: number;
  confidence: number;
  volatility_range_pct: { low: number; high: number };
  actual_direction: string;
  actual_return_pct: number;
}

export interface ReviewScoreRequest {
  symbol: string;
  name?: string;
  cycles: ReviewCycleInput[];
}

// 响应（camelCase）
export interface ScoredCycle {
  cycle: string;
  predictedDirection: ReviewDirection;
  actualDirection: ReviewDirection;
  actualReturnPct: number;
  directionHit: boolean;
  rangeHit: boolean;
  accuracyScore: number;
  attribution: {
    dataLayer: LayerScore;
    modelLayer: LayerScore;
    logicLayer: LayerScore;
  };
}

export interface ReviewScoreData {
  symbol: string;
  name: string;
  scoredAt: number;
  cycles: ScoredCycle[];
  accuracyRate: number;
  avgLayerHealth: Record<ReviewLayerKey, number>;
  weakestLayer: ReviewLayerKey;
  sampleSize: number;
}

export interface ByCycleStat {
  n: number;
  accuracyRate: number;
  directionHitRate: number;
  rangeHitRate: number;
}

export interface ReviewReportData {
  total: number;
  accuracyRate: number | null;
  avgLayerHealth: Record<ReviewLayerKey, number | null>;
  weakestLayer: ReviewLayerKey | null;
  byCycle: Record<string, ByCycleStat>;
}

export interface ReviewResponse {
  code: number;
  msg: string;
  data: ReviewScoreData | ReviewReportData | null;
}
