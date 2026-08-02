// 长文本深度解析模块类型（对齐 core/llm_parse_service.py 标准化 JSON，经 toCamelCase 映射）
export type LlmParseDocType =
  | 'policy'
  | 'broker_report'
  | 'prospectus'
  | 'meeting_minutes'
  | 'industry_white_paper'
  | 'other';

export type LlmParseMode = 'fast' | 'deep';

export interface ShortTermBlock {
  effect: string;
  scope: string;
  triggerTime: string;
}

export interface MidTermBlock {
  industryChange: string;
  profitImpact: string;
}

export interface LongTermBlock {
  industryPlan: string;
  macroOrientation: string;
}

export interface HiddenConstraint {
  content: string;
  riskLevel: string; // 高/中/低
  cycle: string;
  sourceOrigin?: string;
}

export interface ParseDocumentData {
  docId: string;
  docType: LlmParseDocType;
  mode?: LlmParseMode;
  shortTerm1w: ShortTermBlock;
  midTerm1m: MidTermBlock;
  longTermHalfyear: LongTermBlock;
  hiddenConstraint: HiddenConstraint[];
  potentialRisk: string[];
  reliability: number;
  source: string; // llm / heuristic
}

export interface CompareData {
  docCount: number;
  docTitles: string[];
  consensus: string;
  conflict: string;
  optimisticView: string;
  pessimisticView: string;
  source: string;
}

export interface ConstraintData {
  hiddenConstraint: HiddenConstraint[];
  source: string;
}

export interface LongTermData {
  industryPlan: string;
  macroOrientation: string;
  source: string;
}

export interface LlmParseResponse {
  code: number;
  msg: string;
  data: ParseDocumentData | CompareData | ConstraintData | LongTermData | null;
}

export interface ParseDocumentRequest {
  text: string;
  docType?: LlmParseDocType;
  mode?: LlmParseMode;
}

export interface CompareItem {
  title: string;
  text: string;
}

export interface CompareRequest {
  documents: CompareItem[];
}
