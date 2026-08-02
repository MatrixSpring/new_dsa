// DSA 全局参数类型（对齐 api/v1/endpoints/dsa_params.py，经 toCamelCase 映射）
export interface DsaParam {
  id: number;
  paramKey: string;
  paramValue: number;
  paramDesc: string | null;
  updatedAt: string | null;
}
