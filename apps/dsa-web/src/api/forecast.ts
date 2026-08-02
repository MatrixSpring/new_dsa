import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MultiConsensusRequest,
  MultiConsensusResponse,
  MultiCycleRequest,
  MultiCycleResponse,
  DsaPropagationRequest,
  DsaPropagationResponse,
} from '../types/forecast';

export const forecastApi = {
  /**
   * 多模型共识推演 — 同步接口，返回完整推演过程。
   */
  getMultiModelConsensus: async (
    data: MultiConsensusRequest
  ): Promise<MultiConsensusResponse> => {
    const requestData = {
      weight_config: data.weight_config.map((item) => ({
        name: item.name,
        weight: item.weight,
        win_rate: item.win_rate,
      })),
      ...(data.stock_code && { stock_code: data.stock_code }),
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/forecast/consensus',
      requestData
    );

    return toCamelCase<MultiConsensusResponse>(response.data);
  },

  /**
   * 多周期前瞻预测统一接口（设计 §3 / §4.3）
   * POST /api/v1/predict/multi-cycle
   */
  getMultiCycleForecast: async (
    data: MultiCycleRequest
  ): Promise<MultiCycleResponse> => {
    const requestBody: Record<string, unknown> = {
      symbols: data.symbols,
      market: data.market ?? 'A',
      mode: data.mode ?? 'synthetic',
    };
    if (data.cycles && data.cycles.length > 0) {
      requestBody.cycles = data.cycles;
    }
    if (data.seed != null) {
      requestBody.seed = data.seed;
    }

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/predict/multi-cycle',
      requestBody
    );

    return toCamelCase<MultiCycleResponse>(response.data);
  },

  /**
   * DSA 产业链冲击传导（设计 §2 / §4 产业链维护联动）
   * POST /api/v1/predict/dsa-propagation
   */
  runDsaPropagation: async (
    data: DsaPropagationRequest
  ): Promise<DsaPropagationResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/predict/dsa-propagation',
      { graph: data.graph, shock: data.shock }
    );

    return toCamelCase<DsaPropagationResponse>(response.data);
  },
};
