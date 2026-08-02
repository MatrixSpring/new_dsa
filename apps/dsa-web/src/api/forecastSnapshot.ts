import apiClient from './index';
import type {
  Cycle,
  ForecastSnapshotResponse,
  ScopeType,
} from '../types/forecastSnapshot';

interface ListParams {
  scopeType?: ScopeType;
  scopeValue?: string;
  cycle?: Cycle;
}

export const forecastSnapshotApi = {
  list(params: ListParams = {}) {
    return apiClient
      .get<ForecastSnapshotResponse>('/api/v1/forecast-snapshots/', { params })
      .then((r) => r.data);
  },
  seed() {
    return apiClient
      .post<{ code: number; data: { created: number; scopes: number; cycles: number } }>(
        '/api/v1/forecast-snapshots/seed'
      )
      .then((r) => r.data);
  },
};
