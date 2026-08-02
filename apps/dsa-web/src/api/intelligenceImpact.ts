import apiClient from './index';
import type {
  IntelligenceImpact,
  IntelligenceImpactResponse,
} from '../types/intelligenceImpact';

export const intelligenceImpactApi = {
  /** 对一批情报条目计算结构化 5 字段并落库 */
  grade(items: Array<{ id: string | number; title?: string; summary?: string; industry?: string }>) {
    return apiClient
      .post<{ code: number; data: { graded: number; items: IntelligenceImpact[] } }>(
        '/api/v1/intelligence-impact/grade',
        { items }
      )
      .then((r) => r.data);
  },
  /** 读取已分级情报 */
  list(params: { direction?: string; level?: string } = {}) {
    return apiClient
      .get<IntelligenceImpactResponse>('/api/v1/intelligence-impact/impacts', { params })
      .then((r) => r.data);
  },
};
