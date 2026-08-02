import apiClient from './index';
import { toCamelCase } from './utils';
import type { DsaParam } from '../types/dsaParams';

export const dsaParamsApi = {
  /** GET /api/v1/dsa-params 列出全部全局参数 */
  list: async (): Promise<{ code: number; total: number; items: DsaParam[] }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/dsa-params');
    return toCamelCase(response.data);
  },

  /** POST /api/v1/dsa-params/seed 写入默认种子参数 */
  seed: async (): Promise<{ code: number; msg: string; data: { created: number; seed: number } }> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/dsa-params/seed');
    return toCamelCase(response.data);
  },

  /** PUT /api/v1/dsa-params/{key} 设置单个参数 */
  set: async (key: string, paramValue: number, paramDesc?: string) => {
    const body: Record<string, unknown> = { paramValue };
    if (paramDesc !== undefined) body.paramDesc = paramDesc;
    const response = await apiClient.put<Record<string, unknown>>(`/api/v1/dsa-params/${key}`, body);
    return toCamelCase(response.data);
  },
};
