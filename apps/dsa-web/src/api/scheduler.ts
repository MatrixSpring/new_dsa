import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  SchedulerJobResponse,
  SchedulerJobsResponse,
  SchedulerRunsResponse,
} from '../types/scheduler';

export const schedulerApi = {
  /**
   * 任务清单 + 运行状态
   * GET /api/v1/scheduler/jobs
   */
  getJobs: async (): Promise<SchedulerJobsResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/scheduler/jobs');
    return toCamelCase<SchedulerJobsResponse>(response.data);
  },

  /**
   * 启停任务
   * POST /api/v1/scheduler/jobs/{id}/toggle
   */
  toggleJob: async (id: string, enabled: boolean): Promise<SchedulerJobResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduler/jobs/${id}/toggle`,
      { enabled }
    );
    return toCamelCase<SchedulerJobResponse>(response.data);
  },

  /**
   * 手动触发一次
   * POST /api/v1/scheduler/jobs/{id}/run
   */
  runJob: async (id: string): Promise<SchedulerJobResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduler/jobs/${id}/run`
    );
    return toCamelCase<SchedulerJobResponse>(response.data);
  },

  /**
   * 最近调度运行日志
   * GET /api/v1/scheduler/runs
   */
  getRuns: async (): Promise<SchedulerRunsResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/scheduler/runs');
    return toCamelCase<SchedulerRunsResponse>(response.data);
  },

  /**
   * 记录一次任务运行
   * POST /api/v1/scheduler/jobs/{id}/record
   */
  recordRun: async (id: string, payload: { status: string; summary?: string; error?: string }): Promise<SchedulerJobResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduler/jobs/${id}/record`,
      payload
    );
    return toCamelCase<SchedulerJobResponse>(response.data);
  },
};
