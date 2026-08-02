import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  CompareRequest,
  LlmParseResponse,
  ParseDocumentRequest,
} from '../types/llmParse';

export const llmParseApi = {
  /**
   * 单文档分层拆解 + 约束挖掘 + 长期规划 + 隐性风险
   * POST /api/v1/llm-parse/document
   */
  parseDocument: async (data: ParseDocumentRequest): Promise<LlmParseResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/llm-parse/document',
      {
        text: data.text,
        doc_type: data.docType ?? 'other',
        mode: data.mode ?? 'deep',
      }
    );
    return toCamelCase<LlmParseResponse>(response.data);
  },

  /**
   * 多文档交叉对比（2~10 份）
   * POST /api/v1/llm-parse/compare
   */
  compareDocuments: async (data: CompareRequest): Promise<LlmParseResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/llm-parse/compare',
      { documents: data.documents.map((d) => ({ title: d.title, text: d.text })) }
    );
    return toCamelCase<LlmParseResponse>(response.data);
  },

  /**
   * 隐藏约束挖掘
   * POST /api/v1/llm-parse/constraints
   */
  mineConstraints: async (text: string): Promise<LlmParseResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/llm-parse/constraints',
      { text }
    );
    return toCamelCase<LlmParseResponse>(response.data);
  },

  /**
   * 长期规划提取
   * POST /api/v1/llm-parse/long-term
   */
  extractLongTerm: async (text: string): Promise<LlmParseResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/llm-parse/long-term',
      { text }
    );
    return toCamelCase<LlmParseResponse>(response.data);
  },
};
