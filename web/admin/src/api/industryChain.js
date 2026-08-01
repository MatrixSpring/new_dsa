/**
 * 产业链全景可视化 API 模块
 * 对接后端 /api/v1/industry-chains/* 接口（内置沙盘富数据 + 新质生产力 xzsc 底层数据）
 */
import request from './request'

/** 产业链目录：内置沙盘链 + 新质生产力(xzsc) 58 条 */
export function listIndustryChains() {
  return request.get('/api/v1/industry-chains')
}

/** 单条产业链完整图谱（nodes/edges/companies/news） */
export function getIndustryChain(id) {
  return request.get(`/api/v1/industry-chains/${id}`)
}

/** 外部冲击事件库 */
export function listShocks() {
  return request.get('/api/v1/industry-chains/shocks')
}
