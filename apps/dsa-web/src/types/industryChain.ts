// 产业链维护模块类型（对齐 api/v1/endpoints/industry_chain.py，经 toCamelCase 映射）
export interface ChainEdgeOverride {
  id: number;
  chainId: string;
  sourceNode: string;
  targetNode: string;
  coeff: number;
  lag: number;
  updatedAt: string | null;
}

export interface ChainRiskFlag {
  id: number;
  chainId: string;
  node: string;
  riskType: string;
  severity: string;
  note: string | null;
  createdAt: string;
}

export interface ChainTemplate {
  meta: { chainId: string; name: string; category: string; exportedAt: string };
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  companies: Record<string, Record<string, unknown>[]>;
}

export interface IndustryChainListItem {
  id: string;
  name: string;
  icon: string;
  color: string;
  category: string;
  l1: string;
  l2: string;
  summary: string;
  source: string;
  nodeCount: number;
  companyCount?: number;
}

export interface IndustryChainListResponse {
  code: number;
  msg: string;
  total: number;
  sources: { sandbox: number; xzsc: number };
  items: IndustryChainListItem[];
}

// ===========================================================================
// #12 DSA 传导引擎（设计 §3.1 引擎规则 + 三情景并行传导）
// ===========================================================================
export interface DsaEngineParams {
  maxDepth: number;
  bidirectionalDecay: number;
  bearishDecay: number;
  usedOverrides: boolean;
  factorWeights?: Record<string, number> | null;
}

export interface PropagateNodeImpact {
  nodeId: string;
  label: string;
  stage?: string;
  layer?: string;
  impact: number;
  impactPct: number;
  direction: 'positive' | 'negative';
}

export interface PropagateCompanyImpact {
  code: string;
  name: string;
  nodes: string[];
  impactPct: number;
  direction: 'positive' | 'negative';
}

export interface PropagateSummary {
  totalNodes: number;
  impactedNodes: number;
  maxImpact: number;
  maxImpactPct: number;
  avgAbsImpact: number;
  affectedCompanies: number;
  params: DsaEngineParams;
}

export interface PropagateResult {
  shockNode: string;
  shockLabel: string;
  magnitude: number;
  magnitudePct: number;
  kind: string;
  params: DsaEngineParams;
  nodeImpacts: PropagateNodeImpact[];
  companyImpacts: PropagateCompanyImpact[];
  summary: PropagateSummary;
}

export interface ScenarioResult {
  base: PropagateResult;
  optimistic: PropagateResult;
  pessimistic: PropagateResult;
  params: Record<string, number>;
}

export interface DsaEngineSeed {
  chains?: IndustryChainListItem[];
  params?: Array<{ paramKey: string; paramValue: number; paramDesc?: string }>;
  propagate?: PropagateResult;
  scenarios?: ScenarioResult;
}
