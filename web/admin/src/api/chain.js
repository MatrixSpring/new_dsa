/**
 * 产业链全景可视化 API 模块
 * 对接后端 /api/v1/graph/* 和 /api/v1/expert/chain/* 接口
 */
import request from './request'

/** 产业链列表 */
export const CHAIN_LIST = ['AI算力', '机器人', '光伏', '新能源汽车', '半导体', '白酒']

/**
 * 获取产业链图谱数据
 * @param {string} chainName - 产业链名称
 * @returns {Promise<{nodes: Array, edges: Array}>}
 */
export function getChainGraph(chainName) {
  return request.get(`/api/v1/graph/data/${chainName}`)
}

/**
 * 获取产业链事件列表
 * @returns {Promise<Array>}
 */
export function getChainEvents() {
  return request.get('/api/v1/graph/events')
}

/**
 * 投放冲击事件到产业链
 * @param {string} chainName - 产业链名称
 * @param {Object} payload - { title, category, direction, strength, target_nodes }
 */
export function applyChainImpact(chainName, payload) {
  return request.post(`/api/v1/graph/impact/${chainName}`, payload)
}

/**
 * 导出产业链快照
 * @param {string} chainName
 */
export function exportChainSnapshot(chainName) {
  return request.get(`/api/v1/graph/snapshot/${chainName}`)
}

/**
 * 动态事件推演 (多因子博弈)
 * @param {Object} payload - { eventKey, layers }
 */
export function simulateChainEvent(payload) {
  return request.post('/api/v1/expert/chain/sim', payload)
}

/**
 * 传导路径计算 (BFS)
 * @param {Object} payload - { rootNodeId, baseStrength, minCoeffFilter, maxLevel }
 */
export function calcSpreadPath(payload) {
  return request.post('/api/simulation/calcPath', payload)
}

/**
 * 获取申万产业链台账
 * @param {string} [l1] - 一级行业名
 */
export function getSwChain(l1) {
  const params = l1 ? { l1 } : {}
  return request.get('/api/v1/chain/list', { params })
}

/**
 * 获取产业链上下游路径
 * @param {string} code - 行业代码
 */
export function getChainPath(code) {
  return request.get(`/api/v1/chain/path/${code}`)
}

/**
 * 获取产业链图谱 (ECharts/G6 格式)
 * @param {string} chainId - 产业链ID
 */
export function getChainGraphData(chainId) {
  return request.get(`/api/v1/chain/${chainId}/graph`)
}
