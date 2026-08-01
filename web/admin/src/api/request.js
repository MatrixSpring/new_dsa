import axios from 'axios'
import { ElMessage, ElLoading } from 'element-plus'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 60000,
})

// 请求拦截器
request.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
)

// 响应拦截器 — 统一处理后端 ApiResp 格式
let loadingInstance = null

request.interceptors.response.use(
  (response) => {
    const res = response.data

    // 非 ApiResp 结构（如直接返回文件流），原样返回
    if (res === null || typeof res !== 'object' || res.success === undefined) {
      return res
    }

    // 统一响应格式: { success, code, msg, data }
    if (res.success === true || res.code === 200) {
      return res.data
    }

    // 业务错误
    const errMsg = res.msg || '请求失败'
    ElMessage.error(errMsg)
    return Promise.reject(new Error(errMsg))
  },
  (error) => {
    // HTTP 错误
    let msg = '网络异常，请稍后重试'
    if (error.response) {
      const status = error.response.status
      const data = error.response.data
      if (data && data.msg) {
        msg = data.msg
      } else if (status === 404) {
        msg = '接口不存在'
      } else if (status === 500) {
        msg = '服务器内部错误'
      } else if (status === 422) {
        msg = '参数校验失败'
      }
    } else if (error.code === 'ECONNABORTED') {
      msg = '请求超时，请稍后重试'
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

/**
 * 带 loading 的请求辅助函数
 * @param {Function} fn - 返回 Promise 的函数
 * @param {string} text - loading 文案
 */
export async function withLoading(fn, text = '加载中...') {
  loadingInstance = ElLoading.service({ text, background: 'rgba(15,18,24,0.8)' })
  try {
    return await fn()
  } finally {
    loadingInstance?.close()
  }
}

export default request
