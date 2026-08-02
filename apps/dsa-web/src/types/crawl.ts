/** 自动爬虫 + 长文本解析流水线（P0）前端类型。 */

export type CrawlDocType = 'policy' | 'report' | 'prospectus' | 'minutes';
export type CrawlStatus = 'pending' | 'fetched' | 'parsed' | 'failed';

export interface CrawlSource {
  key: string;
  name: string;
  docType: CrawlDocType;
  adapter: string;
  description: string;
}

export interface CrawlParsed {
  docId: string;
  docType: string;
  shortTerm1w: string;
  midTerm1m: string;
  longTermHalfyear: string;
  hiddenConstraint: string;
  potentialRisk: string;
  reliability: string;
}

export interface CrawlDocument {
  id: number;
  sourceKey: string;
  title: string;
  docType: CrawlDocType;
  status: CrawlStatus;
  error: string | null;
  fetchedAt: string | null;
  parsedAt: string | null;
  rawLength: number;
  parsed: CrawlParsed | null;
}

export interface CrawlSourcesResponse {
  code: number;
  msg: string;
  data: CrawlSource[];
}

export interface CrawlRunResponse {
  code: number;
  msg: string;
  data: CrawlDocument | null;
}

export interface CrawlDocumentsResponse {
  code: number;
  total: number;
  items: CrawlDocument[];
}
