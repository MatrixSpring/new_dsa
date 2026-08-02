import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  ReviewResponse,
  ReviewScoreRequest,
} from '../types/review';

export const reviewApi = {
  /**
   * 单条预测（多周期）打分 + 持久化
   * POST /api/v1/review/score
   */
  score: async (req: ReviewScoreRequest): Promise<ReviewResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/review/score',
      req
    );
    return toCamelCase<ReviewResponse>(response.data);
  },

  /**
   * 聚合统计报告
   * GET /api/v1/review/report
   */
  report: async (): Promise<ReviewResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/review/report');
    return toCamelCase<ReviewResponse>(response.data);
  },
};
