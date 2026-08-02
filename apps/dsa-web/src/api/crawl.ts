import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  CrawlDocumentsResponse,
  CrawlRunResponse,
  CrawlSourcesResponse,
} from '../types/crawl';

export const crawlApi = {
  listSources: async (): Promise<CrawlSourcesResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/crawl/sources');
    return toCamelCase<CrawlSourcesResponse>(response.data);
  },
  run: async (sourceKey: string): Promise<CrawlRunResponse> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/crawl/run', {
      source_key: sourceKey,
    });
    return toCamelCase<CrawlRunResponse>(response.data);
  },
  listDocuments: async (limit = 50): Promise<CrawlDocumentsResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/crawl/documents', {
      params: { limit },
    });
    return toCamelCase<CrawlDocumentsResponse>(response.data);
  },
};
