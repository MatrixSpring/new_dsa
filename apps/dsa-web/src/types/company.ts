// 公司维护模块类型（对齐 api/v1/endpoints/company.py，经 toCamelCase 映射）
export interface RiskTag {
  tag: string;
  level: string; // 利好 / 利空
  note: string;
  source: string;
}

export interface CompanySummary {
  code: string;
  name: string;
  exchange?: string | null;
  pe?: number | null;
  pb?: number | null;
  ps?: number | null;
  price?: number | null;
  totalMarketCap?: number | null;
  floatMarketCap?: number | null;
  consensusRating?: string | null;
  consensusTargetPrice?: number | null;
  esgRating?: string | null;
  linkedChainsCount?: number;
  dataSources?: string[];
}

export interface CompanyDetail extends CompanySummary {
  riskTags?: RiskTag[];
  [key: string]: unknown;
}
