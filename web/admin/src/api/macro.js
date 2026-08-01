/**
 * 资金全球动态可视化 API 模块
 * 对接后端 /api/v1/macro/* 接口
 */
import request from './request'

/** 默认监测经济体 */
export const DEFAULT_COUNTRIES = ['USA', 'CN', 'JP', 'DE', 'IN']

/**
 * 获取全球经济体列表
 * @returns {Promise<Array>} 国家列表 (含脆弱性得分、宏观指标)
 */
export function getCountries() {
  return request.get('/api/v1/macro/countries')
}

/**
 * 获取单个经济体详情
 * @param {string} countryId - 国家代码 (如 USA, CN, JP)
 */
export function getCountryDetail(countryId) {
  return request.get(`/api/v1/macro/country/${countryId}`)
}

/**
 * 获取宏观时序数据 (债务/GDP, CDS, 利率等)
 * @param {string} countryId
 * @param {string} indicator - 指标名
 * @param {string} [startDate]
 * @param {string} [endDate]
 */
export function getMacroTimeSeries(countryId, indicator, startDate, endDate) {
  return request.get('/api/v1/macro/timeseries', {
    params: { country_id: countryId, indicator, start_date: startDate, end_date: endDate },
  })
}

/**
 * 获取全球资本流动数据
 * @param {string} [period] - 时间周期 (如 '2024Q4', '2025M01')
 */
export function getCapitalFlow(period) {
  return request.get('/api/v1/macro/capital_flow', {
    params: period ? { period } : {},
  })
}

/**
 * 获取宏观冲击事件列表 (用于沙盘推演)
 * @returns {Promise<Array>}
 */
export function getSimEvents() {
  return request.get('/api/v1/macro/sim/events')
}

/**
 * 获取宏观传导图谱 (G6/ECharts 格式)
 * @returns {Promise<{nodes: Array, edges: Array}>}
 */
export function getSimGraph() {
  return request.get('/api/v1/macro/sim/graph')
}

/**
 * 计算宏观传导路径 (BFS)
 * @param {Object} payload - { rootNodeId, baseStrength, minCoeffFilter, maxLevel }
 */
export function calcSimPath(payload) {
  return request.post('/api/v1/macro/sim/calcPath', payload)
}

/**
 * AI 宏观研判报告
 * @param {Object} payload - { country_id, scenario, indicators }
 */
export function getAiMacroReport(payload) {
  return request.post('/api/v1/macro/ai_report', payload)
}

/**
 * 获取各国政策利率对比数据
 */
export function getRateCompare() {
  return request.get('/api/v1/macro/rate_compare')
}

/**
 * 获取全球贸易差额数据
 */
export function getTradeBalance() {
  return request.get('/api/v1/macro/trade_balance')
}
