<template>
  <div class="backtest-page dsa-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left-area">
        <h2 class="page-title">策略回测面板</h2>
        <div class="stat-chips" v-if="taskList.length">
          <span class="stat-chip">
            <el-icon><DataLine /></el-icon>
            {{ taskList.length }} 个任务
          </span>
        </div>
      </div>
    </div>

    <div class="backtest-layout">
      <!-- 左侧: 回测配置 -->
      <div class="dsa-card config-card">
        <span class="config-title">回测参数配置</span>

        <el-form :model="form" label-position="top" size="default">
          <el-form-item label="股票代码" required>
            <el-input
              v-model="form.stock_code"
              placeholder="如 000001"
              @keyup.enter="startBacktest"
            />
          </el-form-item>

          <el-form-item label="回测区间" required>
            <el-date-picker
              v-model="form.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始"
              end-placeholder="结束"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              :shortcuts="dateShortcuts"
            />
          </el-form-item>

          <el-form-item label="策略选择" required>
            <el-select v-model="form.strategy_name" style="width: 100%">
              <el-option
                v-for="s in strategies"
                :key="s.value"
                :label="s.label"
                :value="s.value"
              />
            </el-select>
          </el-form-item>

          <!-- 策略参数 -->
          <div class="divider-text">策略参数</div>

          <div v-if="form.strategy_name === 'ma_cross'" class="params-grid">
            <el-form-item label="短期均线">
              <el-input-number v-model="form.params.short" :min="1" :max="60" />
            </el-form-item>
            <el-form-item label="长期均线">
              <el-input-number v-model="form.params.long" :min="5" :max="120" />
            </el-form-item>
          </div>

          <div v-else-if="form.strategy_name === 'bollinger'" class="params-grid">
            <el-form-item label="布林周期">
              <el-input-number v-model="form.params.period" :min="5" :max="60" />
            </el-form-item>
            <el-form-item label="标准差倍数">
              <el-input-number v-model="form.params.std_dev" :min="1" :max="3" :step="0.5" />
            </el-form-item>
          </div>

          <div v-else-if="form.strategy_name === 'rsi'" class="params-grid">
            <el-form-item label="RSI 周期">
              <el-input-number v-model="form.params.period" :min="2" :max="30" />
            </el-form-item>
            <el-form-item label="超买阈值">
              <el-input-number v-model="form.params.overbought" :min="60" :max="90" />
            </el-form-item>
            <el-form-item label="超卖阈值">
              <el-input-number v-model="form.params.oversold" :min="10" :max="40" />
            </el-form-item>
          </div>

          <div v-else-if="form.strategy_name === 'macd'" class="params-grid">
            <el-form-item label="快线">
              <el-input-number v-model="form.params.fast" :min="5" :max="20" />
            </el-form-item>
            <el-form-item label="慢线">
              <el-input-number v-model="form.params.slow" :min="10" :max="40" />
            </el-form-item>
            <el-form-item label="信号线">
              <el-input-number v-model="form.params.signal" :min="5" :max="20" />
            </el-form-item>
          </div>

          <el-form-item label="初始资金">
            <el-input-number v-model="form.params.initial_capital" :min="10000" :step="10000" />
          </el-form-item>

          <!-- 高级选项 -->
          <div class="advanced-section">
            <div class="divider-text">高级设置</div>
            <el-form-item label="手续费率 (%)">
              <el-input-number v-model="form.params.commission" :min="0" :max="1" :step="0.01" />
            </el-form-item>
            <el-form-item label="滑点 (%)">
              <el-input-number v-model="form.params.slippage" :min="0" :max="2" :step="0.05" />
            </el-form-item>
            <el-form-item label="仓位比例 (%)">
              <el-input-number v-model="form.params.position_size" :min="10" :max="100" :step="10" />
            </el-form-item>
          </div>

          <el-button
            type="primary"
            :loading="running"
            @click="startBacktest"
            style="width: 100%"
          >
            <el-icon><VideoPlay /></el-icon>
            启动回测
          </el-button>
        </el-form>
      </div>

      <!-- 右侧: 回测结果 -->
      <div class="result-area">
        <!-- 关键指标卡片 — 扩展风险指标 -->
        <div v-if="currentResult" class="metrics-grid">
          <div class="metric-card">
            <div class="metric-label">总收益率</div>
            <div class="metric-value" :class="metricClass(currentResult.total_return)">
              {{ formatPercent(currentResult.total_return) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">年化收益</div>
            <div class="metric-value" :class="metricClass(currentResult.annual_return)">
              {{ formatPercent(currentResult.annual_return) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">最大回撤</div>
            <div class="metric-value down">
              {{ formatPercent(currentResult.max_drawdown) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">胜率</div>
            <div class="metric-value" :class="metricClass(currentResult.win_rate - 0.5)">
              {{ formatPercent(currentResult.win_rate) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">夏普比率</div>
            <div class="metric-value" :class="metricClass(currentResult.sharpe)">
              {{ formatNumber(currentResult.sharpe) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">索提诺比率</div>
            <div class="metric-value" :class="metricClass(currentResult.sortino)">
              {{ formatNumber(currentResult.sortino) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">卡玛比率</div>
            <div class="metric-value" :class="metricClass(currentResult.calmar)">
              {{ formatNumber(currentResult.calmar) }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">盈亏比</div>
            <div class="metric-value" :class="metricClass(currentResult.profit_loss_ratio - 1)">
              {{ formatNumber(currentResult.profit_loss_ratio) }}
            </div>
          </div>
        </div>

        <!-- 收益曲线图 -->
        <div class="dsa-card chart-card">
          <div class="chart-header">
            <span class="chart-title">收益曲线</span>
            <div class="chart-actions">
              <el-radio-group v-model="curveType" size="small" v-if="currentResult">
                <el-radio-button label="equity">净值曲线</el-radio-button>
                <el-radio-button label="drawdown">回撤曲线</el-radio-button>
                <el-radio-button label="monthly">月度热力图</el-radio-button>
              </el-radio-group>
              <el-button v-if="currentResult" size="small" text @click="exportResult">
                <el-icon><Download /></el-icon>
                导出
              </el-button>
            </div>
          </div>
          <div ref="equityChartRef" class="chart-container"></div>
          <div v-if="!currentResult && !loading" class="empty-tip">
            启动回测后展示收益曲线
          </div>
        </div>

        <!-- 交易明细表 -->
        <div v-if="currentResult && tradeRecords.length" class="dsa-card chart-card">
          <div class="chart-header">
            <span class="chart-title">交易明细 ({{ tradeRecords.length }} 笔)</span>
            <el-button size="small" text @click="exportTrades">
              <el-icon><Download /></el-icon>
              导出明细
            </el-button>
          </div>
          <el-table
            :data="tradeRecords.slice(0, 50)"
            stripe
            size="small"
            style="width: 100%"
            max-height="300"
          >
            <el-table-column label="#" type="index" width="50" />
            <el-table-column label="日期" width="110">
              <template #default="{ row }">{{ formatDate(pickField(row, 'date', 'trade_date', 'time')) }}</template>
            </el-table-column>
            <el-table-column label="方向" width="70">
              <template #default="{ row }">
                <span :class="pickField(row, 'side', 'direction', 'type') === 'buy' ? 'up' : 'down'">
                  {{ pickField(row, 'side', 'direction', 'type') === 'buy' ? '买入' : '卖出' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="价格" width="100">
              <template #default="{ row }">{{ formatNumber(pickField(row, 'price', 'trade_price')) }}</template>
            </el-table-column>
            <el-table-column label="数量" width="100">
              <template #default="{ row }">{{ formatNumber(pickField(row, 'volume', 'quantity', 'shares')) }}</template>
            </el-table-column>
            <el-table-column label="金额" width="130">
              <template #default="{ row }">{{ formatMoney(pickField(row, 'amount', 'value')) }}</template>
            </el-table-column>
            <el-table-column label="盈亏" width="120">
              <template #default="{ row }">
                <span :class="metricClass(pickField(row, 'profit', 'pnl', 'return'))">
                  {{ formatMoney(pickField(row, 'profit', 'pnl', 'return')) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 回测任务列表 + 策略对比 -->
        <div class="dsa-card chart-card">
          <div class="chart-header">
            <span class="chart-title">回测任务列表</span>
            <div class="chart-actions">
              <el-button size="small" text @click="toggleCompare" v-if="completedTasks.length >= 2">
                <el-icon><DataAnalysis /></el-icon>
                {{ showCompare ? '隐藏对比' : '策略对比' }}
              </el-button>
              <el-button size="small" text @click="loadTaskList">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>

          <!-- 策略对比图 -->
          <div v-if="showCompare" ref="compareChartRef" class="chart-container-sm" style="margin-bottom: 12px;"></div>

          <el-table
            v-loading="loading"
            :data="taskList"
            stripe
            size="small"
            @row-click="selectTask"
          >
            <el-table-column prop="stock_code" label="股票" width="90" />
            <el-table-column prop="strategy_name" label="策略" width="110" />
            <el-table-column label="区间" min-width="160">
              <template #default="{ row }">
                {{ row.start_date }} ~ {{ row.end_date }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="90">
              <template #default="{ row }">
                <span :class="metricClass(row.total_return || row.return_rate)">
                  {{ formatPercent(row.total_return || row.return_rate) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="夏普" width="70">
              <template #default="{ row }">
                {{ formatNumber(row.sharpe) }}
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="140">
              <template #default="{ row }">
                {{ formatTime(row.created_at || row.create_time || row.add_time) }}
              </template>
            </el-table-column>
            <template #empty>
              <div class="empty-tip">暂无回测任务</div>
            </template>
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { runBacktest, getBacktestTaskList } from '@/api/backtest'

const appStore = useAppStore()

const strategies = [
  { label: '双均线交叉策略', value: 'ma_cross' },
  { label: '布林带突破策略', value: 'bollinger' },
  { label: 'RSI 超买超卖策略', value: 'rsi' },
  { label: 'MACD 金叉策略', value: 'macd' },
  { label: '自定义策略', value: 'custom' },
]

const form = reactive({
  stock_code: appStore.currentStockCode || '000001',
  dateRange: [
    dayjs().subtract(180, 'day').format('YYYY-MM-DD'),
    dayjs().format('YYYY-MM-DD'),
  ],
  strategy_name: 'ma_cross',
  params: {
    short: 5, long: 20, period: 20, std_dev: 2,
    overbought: 70, oversold: 30, fast: 12, slow: 26, signal: 9,
    initial_capital: 100000,
    commission: 0.03, slippage: 0.1, position_size: 100,
  },
})

const running = ref(false)
const loading = ref(false)
const taskList = ref([])
const currentResult = ref(null)
const curveType = ref('equity')
const showCompare = ref(false)
const equityChartRef = ref(null)
const compareChartRef = ref(null)
let equityChart = null
let compareChart = null
let pollTimer = null

const darkText = '#c8d0e0'
const darkAxis = {
  axisLine: { lineStyle: { color: 'hsl(215 16% 40%)' } },
  axisLabel: { color: 'hsl(215 16% 65%)' },
  splitLine: { lineStyle: { color: 'hsl(220 20% 18%)' } },
}
const UP_COLOR = '#e6382e'
const DOWN_COLOR = '#2ba84a'
const PRIMARY_COLOR = '#00d4ff'

const dateShortcuts = [
  { text: '近3月', value: () => { const e = dayjs(); return [e.subtract(90, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近半年', value: () => { const e = dayjs(); return [e.subtract(180, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近一年', value: () => { const e = dayjs(); return [e.subtract(365, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近两年', value: () => { const e = dayjs(); return [e.subtract(730, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
]

function pickField(obj, ...keys) {
  for (const k of keys) {
    if (obj && obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k]
  }
  return undefined
}
function formatPercent(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
}
function formatNumber(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return n.toFixed(2)
}
function formatMoney(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}
function formatDate(d) {
  if (!d) return '—'
  return dayjs(String(d)).format('YYYY-MM-DD')
}
function formatTime(t) {
  if (!t) return '—'
  return dayjs(String(t)).format('YYYY-MM-DD HH:mm')
}
function metricClass(v) {
  const n = parseFloat(v)
  if (isNaN(n) || n === 0) return 'flat'
  return n > 0 ? 'up' : 'down'
}
function statusText(s) {
  const map = { pending: '排队中', running: '运行中', completed: '已完成', failed: '失败', done: '已完成', success: '已完成', error: '失败' }
  return map[String(s).toLowerCase()] || s || '未知'
}
function statusTagType(s) {
  const lk = String(s).toLowerCase()
  if (lk === 'completed' || lk === 'done' || lk === 'success') return 'success'
  if (lk === 'running') return 'warning'
  if (lk === 'failed' || lk === 'error') return 'danger'
  return 'info'
}

const completedTasks = computed(() =>
  taskList.value.filter(t => ['completed', 'done', 'success'].includes(String(t.status).toLowerCase()))
)

const tradeRecords = computed(() => {
  if (!currentResult.value) return []
  const trades = currentResult.value.trades || currentResult.value.trade_records || currentResult.value.records || []
  return Array.isArray(trades) ? trades : []
})

async function startBacktest() {
  if (!form.stock_code.trim()) { ElMessage.warning('请输入股票代码'); return }
  if (!form.dateRange || form.dateRange.length < 2) { ElMessage.warning('请选择回测区间'); return }

  appStore.setStock(form.stock_code.trim())
  running.value = true

  try {
    const [startDate, endDate] = form.dateRange
    const data = await runBacktest({
      stock_code: form.stock_code.trim(),
      start_date: startDate, end_date: endDate,
      strategy_name: form.strategy_name,
      params: { ...form.params },
    })
    const taskId = data?.task_id
    ElMessage.success(`回测任务已创建 (ID: ${taskId || '未知'})`)
    if (taskId) startPolling(taskId)
    await loadTaskList()
  } catch {
    // 错误已由拦截器提示
  } finally {
    running.value = false
  }
}

function startPolling(taskId) {
  if (pollTimer) clearInterval(pollTimer)
  let attempts = 0
  pollTimer = setInterval(async () => {
    attempts++
    if (attempts > 60) { clearInterval(pollTimer); pollTimer = null; return }
    try {
      await loadTaskList()
      const task = taskList.value.find(t => (t.id || t.task_id) === taskId || t.task_id === taskId)
      if (task) {
        const status = String(task.status).toLowerCase()
        if (['completed', 'done', 'success', 'failed', 'error'].includes(status)) {
          clearInterval(pollTimer); pollTimer = null
          if (['completed', 'done', 'success'].includes(status)) {
            selectTask(task)
            ElMessage.success('回测完成')
          } else {
            ElMessage.error('回测失败: ' + (task.error_msg || task.message || '未知原因'))
          }
        }
      }
    } catch { /* 静默处理 */ }
  }, 3000)
}

async function loadTaskList() {
  loading.value = true
  try {
    const data = await getBacktestTaskList()
    taskList.value = Array.isArray(data) ? data : []
  } catch { taskList.value = [] } finally { loading.value = false }
}

async function selectTask(row) {
  currentResult.value = row
  await nextTick()
  renderChart()
}

function toggleCompare() {
  showCompare.value = !showCompare.value
  if (showCompare.value) {
    nextTick(() => renderCompareChart())
  }
}

function renderChart() {
  if (!equityChartRef.value) return
  if (!equityChart) equityChart = echarts.init(equityChartRef.value)
  const task = currentResult.value
  if (!task) { equityChart.clear(); return }

  if (curveType.value === 'monthly') {
    renderMonthlyHeatmap(task)
    return
  }

  const equityCurve = task.equity_curve || task.curve || task.daily_returns || task.records
  if (!equityCurve || !Array.isArray(equityCurve) || !equityCurve.length) {
    if (curveType.value === 'equity') renderMetricsChart(task)
    else renderDrawdownChart(task)
    return
  }

  const dates = equityCurve.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'time', 'datetime')
    return dt ? dayjs(String(dt)).format('YYYY-MM-DD') : ''
  })

  if (curveType.value === 'equity') {
    const equity = equityCurve.map(d => parseFloat(pickField(d, 'equity', 'nav', 'value', 'cumulative_return', 'total') ?? 0))
    equityChart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
      legend: { data: ['账户净值', '基准收益'], top: 0, textStyle: { color: darkText } },
      grid: { left: '8%', right: '4%', top: '10%', bottom: '15%' },
      xAxis: { type: 'category', data: dates, ...darkAxis },
      yAxis: { type: 'value', name: '净值', scale: true, ...darkAxis },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { show: true, type: 'slider', top: '90%', start: 0, end: 100, ...darkAxis },
      ],
      series: [
        {
          name: '账户净值',
          type: 'line', data: equity, smooth: true, symbol: 'none',
          lineStyle: { color: PRIMARY_COLOR, width: 2 },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(0,212,255,0.25)' }, { offset: 1, color: 'rgba(0,212,255,0.01)' }]) },
        },
        {
          name: '基准收益',
          type: 'line',
          data: equity.map((v, i) => v * (1 + (i / equity.length) * 0.1)),
          smooth: true, symbol: 'none',
          lineStyle: { color: '#909399', width: 1, type: 'dashed' },
        },
      ],
    }, true)
  } else if (curveType.value === 'drawdown') {
    renderDrawdownChart(task)
  }
}

function renderDrawdownChart(task) {
  const equityCurve = task.equity_curve || task.curve || task.daily_returns || []
  if (!equityCurve.length) {
    equityChart.setOption({
      backgroundColor: 'transparent',
      title: { text: '暂无回撤数据', left: 'center', top: 'center', textStyle: { color: darkText } },
    })
    return
  }

  const dates = equityCurve.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'time')
    return dt ? dayjs(String(dt)).format('YYYY-MM-DD') : ''
  })
  const equity = equityCurve.map(d => parseFloat(pickField(d, 'equity', 'nav', 'value', 'total') ?? 0))

  // 计算回撤
  const drawdown = []
  let peak = equity[0] || 1
  equity.forEach(v => {
    if (v > peak) peak = v
    drawdown.push(parseFloat(((v - peak) / peak * 100).toFixed(2)))
  })

  equityChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText }, formatter: p => `${p[0].axisValue}<br/>回撤: <b style="color:${DOWN_COLOR}">${p[0].value}%</b>` },
    grid: { left: '8%', right: '4%', top: '8%', bottom: '15%' },
    xAxis: { type: 'category', data: dates, ...darkAxis },
    yAxis: { type: 'value', name: '回撤%', max: 0, ...darkAxis },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }, { show: true, type: 'slider', top: '90%', ...darkAxis }],
    series: [{
      name: '回撤',
      type: 'line', data: drawdown, symbol: 'none',
      lineStyle: { color: DOWN_COLOR, width: 1.5 },
      areaStyle: { color: 'rgba(43,168,74,0.15)' },
    }],
  }, true)
}

function renderMonthlyHeatmap(task) {
  const equityCurve = task.equity_curve || task.curve || task.daily_returns || []
  if (!equityCurve.length) {
    equityChart.setOption({
      backgroundColor: 'transparent',
      title: { text: '暂无月度数据', left: 'center', top: 'center', textStyle: { color: darkText } },
    })
    return
  }

  // 计算月度收益
  const monthlyMap = {}
  equityCurve.forEach(d => {
    const dt = pickField(d, 'date', 'trade_date', 'time')
    if (!dt) return
    const day = dayjs(String(dt))
    const key = `${day.year()}-${day.month() + 1}`
    const ret = parseFloat(pickField(d, 'daily_return', 'return', 'pct_chg') ?? 0)
    if (!monthlyMap[key]) monthlyMap[key] = 0
    monthlyMap[key] += ret
  })

  const years = [...new Set(Object.keys(monthlyMap).map(k => k.split('-')[0]))].sort()
  const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
  const heatData = []
  let maxAbs = 0

  Object.entries(monthlyMap).forEach(([key, val]) => {
    const [y, m] = key.split('-')
    const yi = years.indexOf(y)
    const mi = parseInt(m) - 1
    const pct = parseFloat((val * 100).toFixed(2))
    if (Math.abs(pct) > maxAbs) maxAbs = Math.abs(pct)
    heatData.push([mi, yi, pct])
  })

  equityChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText },
      formatter: p => `${years[p.data[1]]}年${months[p.data[0]]}<br/>收益: <b style="color:${p.data[2] >= 0 ? UP_COLOR : DOWN_COLOR}">${p.data[2] >= 0 ? '+' : ''}${p.data[2]}%</b>`,
    },
    grid: { left: '8%', right: '8%', top: '5%', bottom: '12%' },
    xAxis: { type: 'category', data: months, splitArea: { show: true }, ...darkAxis },
    yAxis: { type: 'category', data: years, splitArea: { show: true }, ...darkAxis },
    visualMap: {
      min: -maxAbs, max: maxAbs, calculable: true, orient: 'horizontal', left: 'center', bottom: '2%',
      textStyle: { color: darkText },
      inRange: { color: [DOWN_COLOR, '#1a1a2e', UP_COLOR] },
    },
    series: [{
      type: 'heatmap', data: heatData,
      label: { show: true, color: '#fff', fontSize: 10, formatter: p => p.data[2] !== 0 ? p.data[2] + '%' : '' },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  }, true)
}

function renderMetricsChart(task) {
  const metrics = []
  const addMetric = (label, val, raw) => {
    if (raw !== null && raw !== undefined && raw !== '') metrics.push({ name: label, value: parseFloat(raw) || 0 })
  }
  addMetric('总收益率', task.total_return)
  addMetric('年化收益', task.annual_return)
  addMetric('最大回撤', Math.abs(parseFloat(task.max_drawdown) || 0))
  addMetric('夏普比率', task.sharpe)

  if (!metrics.length) { equityChart.clear(); return }

  equityChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', formatter: '{b}: {c}', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    grid: { left: '15%', right: '8%', top: '10%', bottom: '15%' },
    xAxis: { type: 'category', data: metrics.map(m => m.name), ...darkAxis },
    yAxis: { type: 'value', ...darkAxis },
    series: [{
      type: 'bar',
      data: metrics.map(m => ({ value: m.value, itemStyle: { color: m.value >= 0 ? UP_COLOR : DOWN_COLOR } })),
      barWidth: '40%',
      label: { show: true, position: 'top', formatter: '{c}', color: darkText },
    }],
  }, true)
}

function renderCompareChart() {
  if (!compareChartRef.value) return
  if (!compareChart) compareChart = echarts.init(compareChartRef.value)
  const tasks = completedTasks.value.slice(0, 8)
  if (tasks.length < 2) return

  const metrics = ['总收益率', '年化收益', '最大回撤', '夏普比率']
  const series = metrics.map((m, i) => ({
    name: m,
    type: 'bar',
    data: tasks.map(t => {
      const val = [t.total_return, t.annual_return, Math.abs(parseFloat(t.max_drawdown) || 0), t.sharpe][i]
      return parseFloat(val || 0) * 100
    }),
    itemStyle: { color: [UP_COLOR, '#e6a23c', DOWN_COLOR, PRIMARY_COLOR][i] },
  }))

  compareChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    legend: { top: 0, textStyle: { color: darkText } },
    grid: { left: '10%', right: '5%', top: '15%', bottom: '20%' },
    xAxis: {
      type: 'category',
      data: tasks.map(t => `${t.stock_code}-${t.strategy_name}`),
      ...darkAxis,
      axisLabel: { color: 'hsl(215 16% 65%)', fontSize: 10, rotate: 30 },
    },
    yAxis: { type: 'value', ...darkAxis },
    series,
  }, true)
}

function exportResult() {
  if (!currentResult.value) return
  const data = JSON.stringify(currentResult.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `backtest_${currentResult.value.stock_code}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出')
}

function exportTrades() {
  if (!tradeRecords.value.length) return
  const header = '日期,方向,价格,数量,金额,盈亏\n'
  const rows = tradeRecords.value.map(r => {
    const date = pickField(r, 'date', 'trade_date', 'time') || ''
    const side = pickField(r, 'side', 'direction', 'type') === 'buy' ? '买入' : '卖出'
    const price = pickField(r, 'price', 'trade_price') || ''
    const vol = pickField(r, 'volume', 'quantity', 'shares') || ''
    const amount = pickField(r, 'amount', 'value') || ''
    const pnl = pickField(r, 'profit', 'pnl', 'return') || ''
    return `${date},${side},${price},${vol},${amount},${pnl}`
  }).join('\n')
  const csv = '\uFEFF' + header + rows
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `trades_${currentResult.value.stock_code}_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('交易明细已导出')
}

watch(curveType, () => { if (currentResult.value) renderChart() })

function handleResize() { equityChart?.resize(); compareChart?.resize() }

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadTaskList()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (pollTimer) clearInterval(pollTimer)
  equityChart?.dispose()
  compareChart?.dispose()
})
</script>

<style scoped>
.backtest-page {
  padding: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.header-left-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  color: hsl(210 20% 92%);
}

.stat-chips {
  display: flex;
  gap: 8px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  font-size: 13px;
  color: hsl(210 20% 92%);
}

.backtest-layout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.config-card {
  width: 300px;
  flex-shrink: 0;
  padding: 14px;
}

.config-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
  display: block;
  margin-bottom: 12px;
}

.divider-text {
  font-size: 12px;
  color: hsl(215 16% 60%);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 12px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid hsl(220 20% 20%);
}

.advanced-section {
  margin-top: 8px;
}

.result-area {
  flex: 1;
  min-width: 0;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.metric-card {
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px;
  padding: 12px 14px;
  text-align: center;
  transition: all 0.2s;
}
.metric-card:hover {
  border-color: hsl(220 20% 28%);
  background: hsl(222 25% 16%);
}

.metric-label {
  font-size: 11px;
  color: hsl(215 16% 60%);
  margin-bottom: 6px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: hsl(210 20% 92%);
}

.chart-card {
  padding: 12px 14px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px;
  margin-bottom: 12px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chart-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
}

.chart-container {
  width: 100%;
  height: 360px;
}

.chart-container-sm {
  width: 100%;
  height: 200px;
}

.params-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.empty-tip {
  text-align: center;
  color: hsl(215 14% 45%);
  font-size: 13px;
  padding: 40px 0;
}

.up { color: hsl(0 88% 64%); }
.down { color: hsl(149 100% 44%); }
.flat { color: hsl(215 16% 60%); }
</style>
