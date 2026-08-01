import request from './request'

/** 运行回测 */
export function runBacktest(data) {
  return request.post('/api/v1/backtest/run', data)
}

/** 获取回测任务列表 */
export function getBacktestTaskList(code = null) {
  const params = {}
  if (code) params.code = code
  return request.get('/api/v1/backtest/task/list', { params })
}
