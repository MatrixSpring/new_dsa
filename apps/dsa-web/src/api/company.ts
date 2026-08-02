import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  CompanyDetail,
  CompanySummary,
  RiskTag,
} from '../types/company';

export const companyApi = {
  /** GET /api/v1/companies 列表（支持 q 搜索） */
  list: async (q?: string): Promise<{ total: number; items: CompanySummary[] }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/companies', {
      params: q ? { q } : {},
    });
    return toCamelCase(response.data);
  },

  /** GET /api/v1/companies/{code} 详情（已合并 riskTags） */
  get: async (code: string): Promise<CompanyDetail> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/companies/${code}`);
    return toCamelCase(response.data);
  },

  /** GET /api/v1/companies/{code}/risk-tags */
  getRiskTags: async (code: string): Promise<{ code: number; total: number; items: RiskTag[] }> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/companies/${code}/risk-tags`);
    return toCamelCase(response.data);
  },

  /** POST /api/v1/companies/{code}/risk-tags 自动识别并写库 */
  computeRiskTags: async (code: string): Promise<{ code: number; msg: string; data: { code: string; riskTags: RiskTag[]; total: number } }> => {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/companies/${code}/risk-tags`);
    return toCamelCase(response.data);
  },
};
