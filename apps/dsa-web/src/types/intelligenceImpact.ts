export type ImpactLevel = '高' | '中' | '低';
export type ImpactCycle = '1w' | '2w' | '1m' | '6m';
export type ImpactDirection = '利好' | '利空' | '中性';

export interface IntelligenceImpact {
  id: number;
  itemId: string;
  impactLevel: ImpactLevel | null;
  impactCycle: ImpactCycle | null;
  impactIndustry: string | null;
  impactDirection: ImpactDirection | null;
  transmitWeight: number | null;
  gradedAt: string | null;
  title?: string;
}

export interface IntelligenceImpactResponse {
  code: number;
  total: number;
  items: IntelligenceImpact[];
}

export const CYCLE_LABELS: Record<ImpactCycle, string> = {
  '1w': '一周',
  '2w': '半月',
  '1m': '一月',
  '6m': '半年',
};

export const DIRECTION_COLORS: Record<ImpactDirection, string> = {
  利好: '#f87171',
  利空: '#34d399',
  中性: '#94a3b8',
};
