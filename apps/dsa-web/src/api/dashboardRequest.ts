/**
 * v2.1.0 仪表盘专用请求封装 — 超时兜底 + 空数据容错 + 断网静默降级
 * 解决白屏卡死：任何异常都返回合法空数据，不阻断页面渲染
 */
import axios from 'axios';

const dashService = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE_URL || '/api',
  timeout: 5000, // 5秒超时兜底（仪表盘接口需快速响应）
  withCredentials: true, // 发送 cookie 以通过认证
  headers: { 'Content-Type': 'application/json;charset=UTF-8' },
});

/** 空数据兜底模板 */
function fallbackData() {
  return { code: 200, msg: 'fallback', data: {}, timestamp: Date.now() };
}

// 响应拦截：认证错误透传，其他异常返回空数据兜底
dashService.interceptors.response.use(
  (res) => res.data || fallbackData(),
  (error) => {
    // 401/403 认证失败 → 重定向到登录页，不静默吞掉
    const status = error?.response?.status;
    if (status === 401 || status === 403) {
      const redirect = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?redirect=${redirect}`;
      return Promise.reject(error);
    }
    // 超时/断网/500 → 返回空数据，不阻塞页面渲染
    return Promise.resolve(fallbackData());
  },
);

export async function dashGet<T = any>(url: string, params?: Record<string, any>): Promise<T> {
  return dashService.get(url, { params }) as unknown as T;
}

export default dashService;
