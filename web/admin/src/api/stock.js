import request from './request'

/** 获取股票基础信息 */
export function getStockInfo(code) {
  return request.get('/api/v1/stock/info', { params: { code } })
}

/** 获取日K线数据 */
export function getStockKline(code, startDate, endDate, useCache = true) {
  return request.get('/api/v1/stock/kline', {
    params: { code, start_date: startDate, end_date: endDate, use_cache: useCache },
  })
}
