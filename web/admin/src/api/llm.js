import request from './request'

/** AI 对话 — 支持豆包/DeepSeek 双模型切换 */
export function llmChat(data) {
  return request.post('/api/v1/llm/chat', data)
}

/** LLM 服务健康检查 */
export function llmHealth() {
  return request.get('/api/v1/llm/health')
}
