import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  ChainEdgeOverride,
  ChainRiskFlag,
  ChainTemplate,
  IndustryChainListResponse,
  PropagateResult,
  ScenarioResult,
} from '../types/industryChain';

export const industryChainApi = {
  /** GET /api/v1/industry-chains 产业链目录 */
  list: async (): Promise<IndustryChainListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/industry-chains');
    return toCamelCase<IndustryChainListResponse>(response.data);
  },

  /** PUT /api/v1/industry-chains/{id}/edge-override 自定义传导系数覆盖 */
  upsertEdgeOverride: async (
    chainId: string,
    payload: { sourceNode: string; targetNode: string; coeff: number; lag: number }
  ): Promise<{ code: number; msg: string; data: ChainEdgeOverride }> => {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/edge-override`,
      {
        source_node: payload.sourceNode,
        target_node: payload.targetNode,
        coeff: payload.coeff,
        lag: payload.lag,
      }
    );
    return toCamelCase(response.data);
  },

  /** GET /api/v1/industry-chains/{id}/edge-overrides */
  listEdgeOverrides: async (chainId: string) => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/edge-overrides`
    );
    return toCamelCase(response.data);
  },

  /** POST /api/v1/industry-chains/{id}/risk-flag 产业链环节风险标记 */
  addRiskFlag: async (
    chainId: string,
    payload: { node: string; riskType: string; severity: string; note?: string }
  ) => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/risk-flag`,
      {
        node: payload.node,
        risk_type: payload.riskType,
        severity: payload.severity,
        note: payload.note,
      }
    );
    return toCamelCase(response.data);
  },

  /** GET /api/v1/industry-chains/{id}/risk-flags */
  listRiskFlags: async (chainId: string) => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/risk-flags`
    );
    return toCamelCase(response.data);
  },

  /** GET /api/v1/industry-chains/{id}/export-template 一键导出画布模板 */
  exportTemplate: async (chainId: string): Promise<{ code: number; msg: string; data: ChainTemplate }> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/export-template`
    );
    return toCamelCase(response.data);
  },

  /** POST /api/v1/industry-chains/{id}/propagate 产业链冲击传导推演（设计 §3.1） */
  propagate: async (
    chainId: string,
    payload: {
      node: string;
      magnitude: number;
      kind: string;
      maxDepth?: number;
      bidirectionalDecay?: number;
      bearishDecay?: number;
      useOverrides?: boolean;
    }
  ): Promise<PropagateResult> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/propagate`,
      {
        node: payload.node,
        magnitude: payload.magnitude,
        kind: payload.kind,
        max_depth: payload.maxDepth,
        bidirectional_decay: payload.bidirectionalDecay,
        bearish_decay: payload.bearishDecay,
        use_overrides: payload.useOverrides,
      }
    );
    return toCamelCase<PropagateResult>(response.data);
  },

  /** POST /api/v1/industry-chains/{id}/propagate-scenarios 三情景并行传导 */
  propagateScenarios: async (
    chainId: string,
    payload: {
      node: string;
      magnitude: number;
      kind: string;
      maxDepth?: number;
      bidirectionalDecay?: number;
      bearishDecay?: number;
      useOverrides?: boolean;
    }
  ): Promise<{ code: number; msg: string; data: ScenarioResult }> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/industry-chains/${chainId}/propagate-scenarios`,
      {
        node: payload.node,
        magnitude: payload.magnitude,
        kind: payload.kind,
        max_depth: payload.maxDepth,
        bidirectional_decay: payload.bidirectionalDecay,
        bearish_decay: payload.bearishDecay,
        use_overrides: payload.useOverrides,
      }
    );
    return toCamelCase(response.data);
  },
};
