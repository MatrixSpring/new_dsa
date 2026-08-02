export type Cycle = '1w' | '2w' | '1m' | '6m';
export type Direction = 'up' | 'down' | 'oscillation';
export type ScopeType = 'event' | 'industry' | 'stock' | 'portfolio';

export interface ForecastSnapshot {
  id: number;
  scopeType: ScopeType;
  scopeValue: string | null;
  cycle: Cycle;
  direction: Direction | null;
  lowPct: number | null;
  highPct: number | null;
  upProb: number | null;
  confidence: number | null;
  coreDriver: string | null;
  mainRisk: string | null;
  generatedAt: string | null;
  jobRunId: string | null;
}

export interface CycleOverview {
  cycle: Cycle;
  total: number;
  directionCounts: { up: number; down: number; oscillation: number };
  avgConfidence: number;
}

export interface ForecastSnapshotResponse {
  code: number;
  total: number;
  items: ForecastSnapshot[];
  byCycle: CycleOverview[];
}

export const CYCLE_LABELS: Record<Cycle, string> = {
  '1w': '一周',
  '2w': '半月',
  '1m': '一月',
  '6m': '半年',
};

export const SCOPE_LABELS: Record<ScopeType, string> = {
  event: '事件',
  industry: '产业链',
  stock: '个股',
  portfolio: '组合',
};

export const DIRECTION_LABELS: Record<Direction, string> = {
  up: '看多',
  down: '看空',
  oscillation: '震荡',
};
