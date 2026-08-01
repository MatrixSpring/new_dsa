<template>
  <div class="market-page dsa-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left-area">
        <h2 class="page-title">行情 & 资金看板</h2>
        <div class="stat-chips" v-if="stockInfo">
          <span class="stat-chip">
            <el-icon><DataLine /></el-icon>
            {{ stockInfo.name || stockInfo.stock_name || stockCode }}
          </span>
          <span class="stat-chip" :class="priceClass(stockInfo)">
            {{ stockInfo.price || stockInfo.close || '—' }}
            <small>{{ formatPercent(stockInfo.change || stockInfo.pct_chg) }}</small>
          </span>
        </div>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="klinePeriod" size="small" @change="loadData">
          <el-radio-button label="daily">日线</el-radio-button>
          <el-radio-button label="weekly">周线</el-radio-button>
          <el-radio-button label="monthly">月线</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 搜索与筛选栏 -->
    <div class="dsa-card filter-bar">
      <div class="filter-row">
        <StockSearch v-model="stockCode" @search="loadData" />
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          :shortcuts="dateShortcuts"
          style="width: 280px"
        />
        <el-button type="primary" :loading="loading" @click="loadData">
          <el-icon><Refresh /></el-icon>
          查询
        </el-button>
        <el-checkbox v-model="accumulateEnabled">显示5日累计净额</el-checkbox>
      </div>
    </div>

    <!-- 股票基本信息 -->
    <div v-if="stockInfo" class="dsa-card info-card">
      <el-descriptions :column="5" border size="small">
        <el-descriptions-item label="股票代码">{{ stockInfo.code || stockCode }}</el-descriptions-item>
        <el-descriptions-item label="股票名称">{{ stockInfo.name || stockInfo.stock_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="最新价">
          <span :class="['metric-val', priceClass(stockInfo)]">
            {{ stockInfo.price || stockInfo.close || '—' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="涨跌幅">
          <span :class="['metric-val', priceClass(stockInfo)]">
            {{ formatPercent(stockInfo.change || stockInfo.pct_chg) }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="成交量">
          <span class="metric-val">{{ formatVolume(stockInfo.volume || stockInfo.vol) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 技术指标选择栏 -->
    <div class="dsa-card indicator-bar">
      <div class="indicator-row">
        <span class="indicator-label">技术指标</span>
        <div class="indicator-chips">
          <span
            v-for="ind in indicators"
            :key="ind.key"
            class="indicator-chip"
            :class="{ active: activeIndicators.includes(ind.key) }"
            :style="activeIndicators.includes(ind.key) ? { borderColor: ind.color + '80', background: ind.color + '20', color: ind.color } : {}"
            @click="toggleIndicator(ind.key)"
          >
            {{ ind.label }}
          </span>
        </div>
      </div>
    </div>

    <!-- K 线图 + 技术指标 -->
    <div class="dsa-card chart-card">
      <div class="chart-header">
        <span class="chart-title">K 线走势 {{ activeIndicators.length ? '· ' + activeIndicators.map(k => indicators.find(i => i.key === k)?.label).join(' / ') : '' }}</span>
        <el-radio-group v-model="klineType" size="small">
          <el-radio-button label="candlestick">蜡烛图</el-radio-button>
          <el-radio-button label="line">折线图</el-radio-button>
        </el-radio-group>
      </div>
      <div ref="klineChartRef" class="chart-container"></div>
      <div v-if="!klineData.length && !loading" class="empty-tip">
        请输入股票代码并选择日期范围后查询
      </div>
    </div>

    <!-- MACD 副图 -->
    <div v-if="activeIndicators.includes('macd')" class="dsa-card chart-card">
      <span class="chart-title">MACD 指标</span>
      <div ref="macdChartRef" class="chart-container-sm"></div>
    </div>

    <!-- 资金流向图 -->
    <div class="dsa-card chart-card">
      <span class="chart-title">资金流向</span>
      <div ref="capitalChartRef" class="chart-container"></div>
      <div v-if="!capitalData.length && !loading" class="empty-tip">
        请输入股票代码并选择日期范围后查询
      </div>
    </div>

    <!-- 资金流向明细表 -->
    <div v-if="capitalData.length" class="dsa-card chart-card">
      <div class="chart-header">
        <span class="chart-title">资金流向明细</span>
        <el-radio-group v-model="capitalView" size="small">
          <el-radio-button label="table">表格</el-radio-button>
          <el-radio-button label="heatmap">热力图</el-radio-button>
        </el-radio-group>
      </div>
      <div v-if="capitalView === 'heatmap'" ref="heatmapChartRef" class="chart-container"></div>
      <el-table
        v-else
        :data="capitalData.slice(-20).reverse()"
        stripe
        size="small"
        style="width: 100%"
      >
        <el-table-column label="日期" width="110">
          <template #default="{ row }">{{ formatDate(pickField(row, 'date', 'trade_date', 'time')) }}</template>
        </el-table-column>
        <el-table-column label="主力净额" width="130">
          <template #default="{ row }">
            <span :class="metricClass(pickField(row, 'net_amount', 'main_net', 'net'))">
              {{ formatMoney(pickField(row, 'net_amount', 'main_net', 'net')) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="超大单" width="120">
          <template #default="{ row }">
            <span :class="metricClass(pickField(row, 'super_net', 'super_large_net'))">
              {{ formatMoney(pickField(row, 'super_net', 'super_large_net')) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="大单" width="120">
          <template #default="{ row }">
            <span :class="metricClass(pickField(row, 'big_net', 'large_net'))">
              {{ formatMoney(pickField(row, 'big_net', 'large_net')) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="中单" width="120">
          <template #default="{ row }">
            <span :class="metricClass(pickField(row, 'mid_net', 'medium_net'))">
              {{ formatMoney(pickField(row, 'mid_net', 'medium_net')) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="小单" width="120">
          <template #default="{ row }">
            <span :class="metricClass(pickField(row, 'small_net', 'retail_net'))">
              {{ formatMoney(pickField(row, 'small_net', 'retail_net')) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { useAppStore } from '@/stores/app'
import StockSearch from '@/components/StockSearch.vue'
import { getStockInfo, getStockKline } from '@/api/stock'
import { getCapitalDaily } from '@/api/capital'

const appStore = useAppStore()

const stockCode = ref(appStore.currentStockCode || '000001')
const dateRange = ref([
  dayjs().subtract(120, 'day').format('YYYY-MM-DD'),
  dayjs().format('YYYY-MM-DD'),
])
const loading = ref(false)
const accumulateEnabled = ref(false)
const klineType = ref('candlestick')
const klinePeriod = ref('daily')
const capitalView = ref('table')

const stockInfo = ref(null)
const klineData = ref([])
const capitalData = ref([])

const klineChartRef = ref(null)
const capitalChartRef = ref(null)
const macdChartRef = ref(null)
const heatmapChartRef = ref(null)
let klineChart = null
let capitalChart = null
let macdChart = null
let heatmapChart = null

const indicators = [
  { key: 'ma', label: 'MA均线', color: '#f5a623' },
  { key: 'boll', label: 'BOLL布林', color: '#e6a23c' },
  { key: 'macd', label: 'MACD', color: '#00d4ff' },
  { key: 'vol', label: '成交量', color: '#909399' },
]
const activeIndicators = ref(['ma'])

const dateShortcuts = [
  { text: '近30天', value: () => { const e = dayjs(); return [e.subtract(30, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近60天', value: () => { const e = dayjs(); return [e.subtract(60, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近120天', value: () => { const e = dayjs(); return [e.subtract(120, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近一年', value: () => { const e = dayjs(); return [e.subtract(365, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
]

// 暗色主题 ECharts 通用配置
const darkAxis = {
  axisLine: { lineStyle: { color: 'hsl(215 16% 40%)' } },
  axisLabel: { color: 'hsl(215 16% 65%)' },
  splitLine: { lineStyle: { color: 'hsl(220 20% 18%)' } },
}
const darkText = '#c8d0e0'
const UP_COLOR = '#e6382e'
const DOWN_COLOR = '#2ba84a'
const PRIMARY_COLOR = '#00d4ff'

function priceClass(info) {
  const c = parseFloat(info.change || info.pct_chg || 0)
  if (c > 0) return 'up'
  if (c < 0) return 'down'
  return 'flat'
}
function formatPercent(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}
function formatVolume(v) {
  if (!v) return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toString()
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
  if (!d) return ''
  return dayjs(String(d)).format('YYYY-MM-DD')
}
function metricClass(v) {
  const n = parseFloat(v)
  if (isNaN(n) || n === 0) return 'flat'
  return n > 0 ? 'up' : 'down'
}

function pickField(obj, ...keys) {
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k]
  }
  return undefined
}

function toggleIndicator(key) {
  const idx = activeIndicators.value.indexOf(key)
  if (idx >= 0) {
    activeIndicators.value.splice(idx, 1)
  } else {
    activeIndicators.value.push(key)
  }
  renderKlineChart()
  if (key === 'macd') {
    nextTick(() => renderMacdChart())
  }
}

// 计算MA均线
function calcMA(data, period) {
  const result = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null)
    } else {
      let sum = 0
      for (let j = 0; j < period; j++) {
        sum += parseFloat(pickField(data[i - j], 'close') ?? 0)
      }
      result.push(parseFloat((sum / period).toFixed(2)))
    }
  }
  return result
}

// 计算BOLL
function calcBOLL(data, period = 20, stdDev = 2) {
  const mid = [], upper = [], lower = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      mid.push(null); upper.push(null); lower.push(null)
    } else {
      let sum = 0
      for (let j = 0; j < period; j++) {
        sum += parseFloat(pickField(data[i - j], 'close') ?? 0)
      }
      const ma = sum / period
      let variance = 0
      for (let j = 0; j < period; j++) {
        const c = parseFloat(pickField(data[i - j], 'close') ?? 0)
        variance += (c - ma) ** 2
      }
      const sd = Math.sqrt(variance / period)
      mid.push(parseFloat(ma.toFixed(2)))
      upper.push(parseFloat((ma + stdDev * sd).toFixed(2)))
      lower.push(parseFloat((ma - stdDev * sd).toFixed(2)))
    }
  }
  return { mid, upper, lower }
}

// 计算MACD
function calcMACD(data, fast = 12, slow = 26, signal = 9) {
  const closes = data.map(d => parseFloat(pickField(d, 'close') ?? 0))
  const emaFast = [], emaSlow = [], dif = [], dea = [], macd = []
  let ef = closes[0] || 0, es = closes[0] || 0

  for (let i = 0; i < closes.length; i++) {
    ef = i === 0 ? closes[0] : (closes[i] * (2 / (fast + 1)) + ef * (1 - 2 / (fast + 1)))
    es = i === 0 ? closes[0] : (closes[i] * (2 / (slow + 1)) + es * (1 - 2 / (slow + 1)))
    emaFast.push(ef); emaSlow.push(es)
    dif.push(ef - es)
  }

  let prevDea = dif[0] || 0
  for (let i = 0; i < dif.length; i++) {
    const d = i === 0 ? dif[0] : (dif[i] * (2 / (signal + 1)) + prevDea * (1 - 2 / (signal + 1)))
    dea.push(d)
    macd.push((dif[i] - d) * 2)
    prevDea = d
  }
  return { dif, dea, macd }
}

async function loadData() {
  const code = stockCode.value.trim()
  if (!code) return
  if (!dateRange.value || dateRange.value.length < 2) return

  appStore.setStock(code)
  loading.value = true

  try {
    const [startDate, endDate] = dateRange.value
    const [info, kline, capital] = await Promise.allSettled([
      getStockInfo(code),
      getStockKline(code, startDate, endDate),
      getCapitalDaily(code, startDate, endDate, accumulateEnabled.value ? 5 : 0),
    ])

    stockInfo.value = info.status === 'fulfilled' ? info.value : null
    klineData.value = kline.status === 'fulfilled' ? (Array.isArray(kline.value) ? kline.value : []) : []
    capitalData.value = capital.status === 'fulfilled' ? (Array.isArray(capital.value) ? capital.value : []) : []

    await nextTick()
    renderKlineChart()
    renderCapitalChart()
    if (activeIndicators.value.includes('macd')) {
      renderMacdChart()
    }
    if (capitalView.value === 'heatmap') {
      renderHeatmap()
    }
  } finally {
    loading.value = false
  }
}

function renderKlineChart() {
  if (!klineChartRef.value) return
  if (!klineChart) {
    klineChart = echarts.init(klineChartRef.value)
  }
  if (!klineData.value.length) {
    klineChart.clear()
    return
  }

  const dates = klineData.value.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'datetime', 'time')
    return dt ? dayjs(String(dt)).format('YYYY-MM-DD') : ''
  })

  const hasMA = activeIndicators.value.includes('ma')
  const hasBOLL = activeIndicators.value.includes('boll')
  const showVol = activeIndicators.value.includes('vol')

  if (klineType.value === 'candlestick') {
    const ohlc = klineData.value.map(d => [
      parseFloat(pickField(d, 'open') ?? 0),
      parseFloat(pickField(d, 'close') ?? 0),
      parseFloat(pickField(d, 'low') ?? 0),
      parseFloat(pickField(d, 'high') ?? 0),
    ])
    const volumes = klineData.value.map(d => parseFloat(pickField(d, 'volume', 'vol') ?? 0))

    const series = [
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        itemStyle: {
          color: UP_COLOR, color0: DOWN_COLOR,
          borderColor: UP_COLOR, borderColor0: DOWN_COLOR,
        },
      },
    ]

    if (hasMA) {
      const maColors = ['#f5a623', '#00d4ff', '#e6a23c', '#a855f7']
      const maPeriods = [5, 10, 20, 60]
      maPeriods.forEach((p, i) => {
        const maData = calcMA(klineData.value, p)
        if (maData.some(v => v !== null)) {
          series.push({
            name: `MA${p}`,
            type: 'line',
            data: maData,
            smooth: true,
            symbol: 'none',
            lineStyle: { color: maColors[i], width: 1.2 },
          })
        }
      })
    }

    if (hasBOLL) {
      const boll = calcBOLL(klineData.value)
      series.push(
        { name: 'BOLL上轨', type: 'line', data: boll.upper, symbol: 'none', lineStyle: { color: '#e6a23c', width: 1, type: 'dashed' } },
        { name: 'BOLL中轨', type: 'line', data: boll.mid, symbol: 'none', lineStyle: { color: '#e6a23c', width: 1 } },
        { name: 'BOLL下轨', type: 'line', data: boll.lower, symbol: 'none', lineStyle: { color: '#e6a23c', width: 1, type: 'dashed' } },
      )
    }

    // 成交量副图
    if (showVol) {
      series.push({
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: ohlc[i][1] >= ohlc[i][0] ? UP_COLOR + '88' : DOWN_COLOR + '88' },
        })),
      })
    }

    const gridCount = showVol ? 2 : 1
    const grids = gridCount === 2
      ? [
          { left: '8%', right: '4%', top: '8%', height: '52%' },
          { left: '8%', right: '4%', top: '66%', height: '16%' },
        ]
      : [{ left: '8%', right: '4%', top: '8%', bottom: '15%' }]

    const xAxes = gridCount === 2
      ? [
          { type: 'category', data: dates, scale: true, boundaryGap: false, ...darkAxis },
          { type: 'category', gridIndex: 1, data: dates, axisLabel: { show: false }, ...darkAxis },
        ]
      : [{ type: 'category', data: dates, scale: true, boundaryGap: false, ...darkAxis }]

    const yAxes = gridCount === 2
      ? [
          { scale: true, ...darkAxis },
          { gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, ...darkAxis },
        ]
      : [{ scale: true, ...darkAxis }]

    klineChart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
      legend: { data: series.map(s => s.name), top: 0, textStyle: { color: darkText } },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: 'inside', xAxisIndex: gridCount === 2 ? [0, 1] : [0], start: 60, end: 100 },
        { show: true, type: 'slider', xAxisIndex: gridCount === 2 ? [0, 1] : [0], top: '90%', start: 60, end: 100, ...darkAxis },
      ],
      series,
    }, true)
  } else {
    const closes = klineData.value.map(d => parseFloat(pickField(d, 'close') ?? 0))
    klineChart.setOption({
      backgroundColor: 'transparent',
      animation: false,
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
      grid: { left: '8%', right: '4%', top: '8%', bottom: '18%' },
      xAxis: { type: 'category', data: dates, ...darkAxis },
      yAxis: { scale: true, ...darkAxis },
      dataZoom: [
        { type: 'inside', start: 60, end: 100 },
        { show: true, type: 'slider', top: '90%', start: 60, end: 100, ...darkAxis },
      ],
      series: [{
        name: '收盘价',
        type: 'line',
        data: closes,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: PRIMARY_COLOR, width: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(0,212,255,0.2)' }, { offset: 1, color: 'rgba(0,212,255,0.01)' }]) },
      }],
    }, true)
  }
}

function renderMacdChart() {
  if (!macdChartRef.value) return
  if (!macdChart) {
    macdChart = echarts.init(macdChartRef.value)
  }
  if (!klineData.value.length) {
    macdChart.clear()
    return
  }

  const dates = klineData.value.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'datetime', 'time')
    return dt ? dayjs(String(dt)).format('YYYY-MM-DD') : ''
  })
  const { dif, dea, macd } = calcMACD(klineData.value)

  macdChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    legend: { data: ['DIF', 'DEA', 'MACD'], top: 0, textStyle: { color: darkText } },
    grid: { left: '8%', right: '4%', top: '12%', bottom: '15%' },
    xAxis: { type: 'category', data: dates, ...darkAxis },
    yAxis: { type: 'value', ...darkAxis },
    dataZoom: [
      { type: 'inside', start: 60, end: 100 },
      { show: true, type: 'slider', top: '90%', start: 60, end: 100, ...darkAxis },
    ],
    series: [
      { name: 'DIF', type: 'line', data: dif, smooth: true, symbol: 'none', lineStyle: { color: '#f5a623', width: 1.5 } },
      { name: 'DEA', type: 'line', data: dea, smooth: true, symbol: 'none', lineStyle: { color: '#a855f7', width: 1.5 } },
      {
        name: 'MACD',
        type: 'bar',
        data: macd.map(v => ({
          value: v,
          itemStyle: { color: v >= 0 ? UP_COLOR : DOWN_COLOR },
        })),
        barWidth: '60%',
      },
    ],
  }, true)
}

function renderCapitalChart() {
  if (!capitalChartRef.value) return
  if (!capitalChart) {
    capitalChart = echarts.init(capitalChartRef.value)
  }
  if (!capitalData.value.length) {
    capitalChart.clear()
    return
  }

  const dates = capitalData.value.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'datetime', 'time')
    return dt ? dayjs(String(dt)).format('YYYY-MM-DD') : ''
  })

  const netAmounts = capitalData.value.map(d =>
    parseFloat(pickField(d, 'net_amount', 'main_net', 'net', 'main_net_amount') ?? 0)
  )
  const accumNet = capitalData.value.map(d =>
    parseFloat(pickField(d, 'accumulate_net', 'rolling_net', 'acc_net') ?? 0)
  )
  const hasAccum = accumulateEnabled.value && accumNet.some(v => v !== 0)

  // 尝试获取超大/大/中/小单
  const superNet = capitalData.value.map(d => parseFloat(pickField(d, 'super_net', 'super_large_net') ?? 0))
  const bigNet = capitalData.value.map(d => parseFloat(pickField(d, 'big_net', 'large_net') ?? 0))
  const midNet = capitalData.value.map(d => parseFloat(pickField(d, 'mid_net', 'medium_net') ?? 0))
  const smallNet = capitalData.value.map(d => parseFloat(pickField(d, 'small_net', 'retail_net') ?? 0))
  const hasDetail = superNet.some(v => v !== 0) || bigNet.some(v => v !== 0)

  const series = [
    {
      name: '主力净流入',
      type: 'bar',
      data: netAmounts.map(v => ({
        value: v,
        itemStyle: { color: v >= 0 ? UP_COLOR : DOWN_COLOR },
      })),
      barWidth: '50%',
    },
  ]

  if (hasDetail) {
    series.push(
      { name: '超大单', type: 'bar', data: superNet, barWidth: '15%', itemStyle: { color: '#e6382e' } },
      { name: '大单', type: 'bar', data: bigNet, barWidth: '15%', itemStyle: { color: '#ff7a45' } },
      { name: '中单', type: 'bar', data: midNet, barWidth: '15%', itemStyle: { color: '#409eff' } },
      { name: '小单', type: 'bar', data: smallNet, barWidth: '15%', itemStyle: { color: '#2ba84a' } },
    )
  }

  if (hasAccum) {
    series.push({
      name: '5日累计净额',
      type: 'line',
      data: accumNet,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      yAxisIndex: 1,
      lineStyle: { color: '#e6a23c', width: 2 },
    })
  }

  const legendData = series.map(s => s.name)
  const yAxes = [{ type: 'value', name: '净额(元)', ...darkAxis }]
  if (hasAccum) {
    yAxes.push({ type: 'value', name: '累计(元)', splitLine: { show: false }, ...darkAxis })
  }

  capitalChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(20,24,32,0.95)',
      borderColor: 'hsl(220 20% 28%)',
      textStyle: { color: darkText },
      formatter: (params) => {
        let html = `<div style="font-weight:600">${params[0].axisValue}</div>`
        params.forEach(p => {
          const val = (p.value / 10000).toFixed(2)
          html += `<div>${p.marker} ${p.seriesName}: <b>${val} 万</b></div>`
        })
        return html
      },
    },
    legend: { top: 0, data: legendData, textStyle: { color: darkText } },
    grid: { left: '10%', right: hasAccum ? '10%' : '4%', top: '10%', bottom: '18%' },
    xAxis: { type: 'category', data: dates, ...darkAxis },
    yAxis: yAxes,
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { show: true, type: 'slider', top: '90%', start: 0, end: 100, ...darkAxis },
    ],
    series,
  }, true)
}

function renderHeatmap() {
  if (!heatmapChartRef.value) return
  if (!heatmapChart) {
    heatmapChart = echarts.init(heatmapChartRef.value)
  }
  if (!capitalData.value.length) {
    heatmapChart.clear()
    return
  }

  const recent = capitalData.value.slice(-20)
  const dates = recent.map(d => {
    const dt = pickField(d, 'date', 'trade_date', 'time')
    return dt ? dayjs(String(dt)).format('MM-DD') : ''
  })

  const fields = ['超大单', '大单', '中单', '小单', '主力净额']
  const fieldKeys = [
    ['super_net', 'super_large_net'],
    ['big_net', 'large_net'],
    ['mid_net', 'medium_net'],
    ['small_net', 'retail_net'],
    ['net_amount', 'main_net', 'net'],
  ]

  const heatData = []
  let maxVal = 0
  for (let f = 0; f < fields.length; f++) {
    for (let d = 0; d < dates.length; d++) {
      const val = parseFloat(pickField(recent[d], ...fieldKeys[f]) ?? 0)
      const absVal = Math.abs(val / 10000)
      if (absVal > maxVal) maxVal = absVal
      heatData.push([d, f, absVal, val])
    }
  }

  heatmapChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      backgroundColor: 'rgba(20,24,32,0.95)',
      borderColor: 'hsl(220 20% 28%)',
      textStyle: { color: darkText },
      formatter: (p) => {
        const val = p.data[3]
        const sign = val > 0 ? '+' : ''
        return `${dates[p.data[0]]}<br/>${fields[p.data[1]]}: <b>${sign}${(val / 10000).toFixed(2)}万</b>`
      },
    },
    grid: { left: '12%', right: '8%', top: '8%', bottom: '15%' },
    xAxis: { type: 'category', data: dates, splitArea: { show: true }, ...darkAxis },
    yAxis: { type: 'category', data: fields, splitArea: { show: true }, ...darkAxis },
    visualMap: {
      min: -maxVal,
      max: maxVal,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '2%',
      textStyle: { color: darkText },
      inRange: { color: ['#2ba84a', '#1a1a2e', '#e6382e'] },
    },
    series: [{
      type: 'heatmap',
      data: heatData,
      label: { show: false },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  }, true)
}

function handleResize() {
  klineChart?.resize()
  capitalChart?.resize()
  macdChart?.resize()
  heatmapChart?.resize()
}

watch(klineType, () => renderKlineChart())
watch(capitalView, (v) => {
  if (v === 'heatmap') {
    nextTick(() => renderHeatmap())
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (stockCode.value) {
    loadData()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  klineChart?.dispose()
  capitalChart?.dispose()
  macdChart?.dispose()
  heatmapChart?.dispose()
})
</script>

<style scoped>
.market-page {
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
.stat-chip small { font-size: 11px; }
.stat-chip.up { color: hsl(0 88% 64%); border-color: hsl(0 88% 64% / 0.3); }
.stat-chip.down { color: hsl(149 100% 44%); border-color: hsl(149 100% 44% / 0.3); }

.filter-bar {
  margin-bottom: 12px;
  padding: 12px 14px;
}

.filter-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.indicator-bar {
  margin-bottom: 12px;
  padding: 10px 14px;
}

.indicator-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.indicator-label {
  font-size: 13px;
  color: hsl(215 16% 60%);
  white-space: nowrap;
}

.indicator-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.indicator-chip {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 4px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  cursor: pointer;
  color: hsl(215 16% 60%);
  transition: all 0.2s;
}
.indicator-chip:hover {
  border-color: hsl(220 20% 28%);
  color: hsl(210 20% 92%);
}

.chart-card {
  margin-bottom: 12px;
  padding: 12px 14px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
}

.chart-container {
  width: 100%;
  height: 420px;
}

.chart-container-sm {
  width: 100%;
  height: 220px;
}

.info-card {
  margin-bottom: 12px;
  padding: 12px 14px;
}

.empty-tip {
  text-align: center;
  color: hsl(215 14% 45%);
  font-size: 13px;
  padding: 40px 0;
}

.metric-val {
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}
.metric-val.up, .up { color: hsl(0 88% 64%); }
.metric-val.down, .down { color: hsl(149 100% 44%); }
.metric-val.flat, .flat { color: hsl(215 16% 60%); }
</style>
