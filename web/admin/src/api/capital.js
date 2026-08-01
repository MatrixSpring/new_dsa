import request from './request'

/** 获取个股每日资金流向 */
export function getCapitalDaily(code, startDate, endDate, accumulateDays = 0, useCache = true) {
  return request.get('/api/v1/capital/daily', {
    params: {
      code,
      start_date: startDate,
      end_date: endDate,
      accumulate_days: accumulateDays,
      use_cache: useCache,
    },
  })
}
