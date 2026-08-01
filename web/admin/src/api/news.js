import request from './request'

/** 获取个股资讯列表 */
export function getStockNews(code, startDate, endDate, stat = true, useCache = true) {
  return request.get('/api/v1/news/stock', {
    params: { code, start_date: startDate, end_date: endDate, stat, use_cache: useCache },
  })
}

/** 获取行业资讯列表 */
export function getIndustryNews(industry, startDate, endDate, stat = true, useCache = true) {
  return request.get('/api/v1/news/industry', {
    params: { industry, start_date: startDate, end_date: endDate, stat, use_cache: useCache },
  })
}
