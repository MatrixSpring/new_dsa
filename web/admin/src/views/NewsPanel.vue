<template>
  <div class="news-page dsa-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left-area">
        <h2 class="page-title">资讯舆情面板</h2>
        <div class="stat-chips" v-if="newsList.length">
          <span class="stat-chip">
            <el-icon><Document /></el-icon>
            {{ newsList.length }} 条
          </span>
          <span class="stat-chip up" v-if="positiveCount > 0">
            <el-icon><Top /></el-icon>
            正面 {{ positiveCount }}
          </span>
          <span class="stat-chip down" v-if="negativeCount > 0">
            <el-icon><Bottom /></el-icon>
            负面 {{ negativeCount }}
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="dsa-card filter-bar">
      <div class="filter-row">
        <el-radio-group v-model="queryType" @change="onTypeChange">
          <el-radio-button label="stock">个股资讯</el-radio-button>
          <el-radio-button label="industry">行业资讯</el-radio-button>
        </el-radio-group>

        <el-input
          v-if="queryType === 'stock'"
          v-model="stockCode"
          placeholder="股票代码，如 000001"
          style="width: 180px"
          @keyup.enter="loadNews"
        />
        <el-input
          v-else
          v-model="industryName"
          placeholder="行业名称，如 银行"
          style="width: 180px"
          @keyup.enter="loadNews"
        />

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
        <el-button type="primary" :loading="loading" @click="loadNews">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </div>

    <!-- 三栏布局：情感饼图 + 情感趋势 + 来源统计 -->
    <div v-if="newsList.length" class="charts-row">
      <!-- 舆情情感分布饼图 -->
      <div class="dsa-card chart-card">
        <span class="chart-title">舆情情感分布</span>
        <div ref="pieChartRef" class="chart-container-sm"></div>
      </div>

      <!-- 情感趋势时间线 -->
      <div class="dsa-card chart-card">
        <span class="chart-title">情感趋势时间线</span>
        <div ref="trendChartRef" class="chart-container-sm"></div>
      </div>

      <!-- 资讯来源统计 -->
      <div class="dsa-card chart-card">
        <span class="chart-title">资讯来源统计</span>
        <div ref="sourceChartRef" class="chart-container-sm"></div>
      </div>
    </div>

    <!-- 热词标签云 -->
    <div v-if="hotWords.length" class="dsa-card chart-card">
      <span class="chart-title">热词标签云</span>
      <div class="word-cloud">
        <span
          v-for="(word, idx) in hotWords"
          :key="idx"
          class="word-tag"
          :style="{
            fontSize: word.size + 'px',
            color: word.color,
            opacity: 0.6 + word.weight * 0.4,
          }"
        >
          {{ word.text }}
        </span>
      </div>
    </div>

    <!-- 情感统计表格 + 资讯列表 -->
    <div class="content-layout">
      <!-- 左侧: 情感统计 -->
      <div v-if="sentimentStat" class="dsa-card sentiment-card">
        <span class="chart-title">情感统计</span>
        <el-descriptions :column="1" border size="small" style="margin-top: 8px">
          <el-descriptions-item
            v-for="(val, key) in sentimentStat"
            :key="key"
            :label="sentimentLabel(key)"
          >
            <span :style="{ color: sentimentColor(key), fontWeight: 600 }">
              {{ val }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 右侧: 资讯列表 -->
      <div class="dsa-card news-list-card">
        <div class="chart-header">
          <span class="chart-title">资讯列表 ({{ filteredNews.length }} / {{ newsList.length }} 条)</span>
          <el-select v-model="sentimentFilter" placeholder="情感筛选" clearable size="small" style="width: 120px">
            <el-option label="全部" value="" />
            <el-option label="正面" value="positive" />
            <el-option label="中性" value="neutral" />
            <el-option label="负面" value="negative" />
          </el-select>
        </div>

        <div v-loading="loading" class="news-list-container">
          <div
            v-for="(item, idx) in filteredNews"
            :key="idx"
            class="news-item"
          >
            <div class="news-item-header">
              <el-tag
                :type="sentimentTagType(item)"
                size="small"
                effect="dark"
              >
                {{ sentimentText(item) }}
              </el-tag>
              <span class="news-source">{{ pickField(item, 'source', 'media') || '未知来源' }}</span>
              <span class="news-date">{{ formatDate(pickField(item, 'date', 'publish_date', 'pub_date', 'time')) }}</span>
            </div>
            <div class="news-title">{{ pickField(item, 'title', 'headline') || '无标题' }}</div>
            <div v-if="pickField(item, 'summary', 'content', 'desc')" class="news-summary">
              {{ truncate(pickField(item, 'summary', 'content', 'desc'), 150) }}
            </div>
          </div>

          <div v-if="!loading && !filteredNews.length" class="empty-tip">
            暂无资讯数据
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { useAppStore } from '@/stores/app'
import { getStockNews, getIndustryNews } from '@/api/news'

const appStore = useAppStore()

const queryType = ref('stock')
const stockCode = ref(appStore.currentStockCode || '000001')
const industryName = ref('')
const dateRange = ref([
  dayjs().subtract(30, 'day').format('YYYY-MM-DD'),
  dayjs().format('YYYY-MM-DD'),
])
const loading = ref(false)
const sentimentFilter = ref('')

const newsList = ref([])
const sentimentStat = ref(null)
const pieChartRef = ref(null)
const trendChartRef = ref(null)
const sourceChartRef = ref(null)
let pieChart = null
let trendChart = null
let sourceChart = null

const darkText = '#c8d0e0'
const darkAxis = {
  axisLine: { lineStyle: { color: 'hsl(215 16% 40%)' } },
  axisLabel: { color: 'hsl(215 16% 65%)' },
  splitLine: { lineStyle: { color: 'hsl(220 20% 18%)' } },
}
const UP_COLOR = '#e6382e'
const DOWN_COLOR = '#2ba84a'
const NEU_COLOR = '#909399'

const dateShortcuts = [
  { text: '近7天', value: () => { const e = dayjs(); return [e.subtract(7, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近30天', value: () => { const e = dayjs(); return [e.subtract(30, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
  { text: '近90天', value: () => { const e = dayjs(); return [e.subtract(90, 'day').format('YYYY-MM-DD'), e.format('YYYY-MM-DD')] } },
]

function pickField(obj, ...keys) {
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k]
  }
  return ''
}
function formatDate(d) {
  if (!d) return ''
  return dayjs(String(d)).format('YYYY-MM-DD')
}
function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}
function onTypeChange() {
  newsList.value = []
  sentimentStat.value = null
}

const positiveCount = computed(() => newsList.value.filter(i => sentimentText(i) === '正面').length)
const negativeCount = computed(() => newsList.value.filter(i => sentimentText(i) === '负面').length)

const filteredNews = computed(() => {
  if (!sentimentFilter.value) return newsList.value
  return newsList.value.filter(item => {
    const s = (pickField(item, 'sentiment', 'emotion', 'label') || '').toLowerCase()
    return s.includes(sentimentFilter.value)
  })
})

// 热词标签云
const hotWords = computed(() => {
  if (!newsList.value.length) return []
  const freq = {}
  const stopWords = new Set(['的', '了', '在', '是', '对', '与', '和', '为', '及', '或', '该', '此', '其', '至', '于', '将', '被', '由', '从', '按', '以', '据', '一', '中', '上', '下', '不', '有', '无', '可', '已', '也', '而'])

  newsList.value.forEach(item => {
    const title = pickField(item, 'title', 'headline') || ''
    const summary = pickField(item, 'summary', 'content', 'desc') || ''
    const text = title + ' ' + summary

    // 提取2-4字中文词
    const matches = text.match(/[\u4e00-\u9fa5]{2,4}/g) || []
    matches.forEach(w => {
      if (!stopWords.has(w)) {
        freq[w] = (freq[w] || 0) + 1
      }
    })
  })

  const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 30)
  const maxFreq = sorted[0]?.[1] || 1

  return sorted.map(([text, count]) => {
    const weight = count / maxFreq
    const size = 12 + weight * 16
    const colors = [UP_COLOR, DOWN_COLOR, NEU_COLOR, '#00d4ff', '#e6a23c', '#a855f7']
    return {
      text,
      size,
      weight,
      color: colors[Math.floor(Math.random() * colors.length)],
    }
  })
})

function sentimentText(item) {
  const s = (pickField(item, 'sentiment', 'emotion', 'label') || '').toLowerCase()
  if (s.includes('pos') || s.includes('正面') || s === '1' || s === 'good') return '正面'
  if (s.includes('neg') || s.includes('负面') || s === '-1' || s === 'bad') return '负面'
  return '中性'
}
function sentimentTagType(item) {
  const s = sentimentText(item)
  if (s === '正面') return 'danger'
  if (s === '负面') return 'success'
  return 'info'
}
function sentimentLabel(key) {
  const map = { positive: '正面', negative: '负面', neutral: '中性', total: '总计', pos: '正面', neg: '负面', neu: '中性' }
  const lk = String(key).toLowerCase()
  return map[lk] || key
}
function sentimentColor(key) {
  const lk = String(key).toLowerCase()
  if (lk.includes('pos')) return UP_COLOR
  if (lk.includes('neg')) return DOWN_COLOR
  if (lk.includes('neu')) return NEU_COLOR
  return '#c8d0e0'
}

async function loadNews() {
  const [startDate, endDate] = dateRange.value || []
  if (!startDate || !endDate) return

  let key, apiCall
  if (queryType.value === 'stock') {
    key = stockCode.value.trim()
    if (!key) return
    appStore.setStock(key)
    apiCall = () => getStockNews(key, startDate, endDate, true)
  } else {
    key = industryName.value.trim()
    if (!key) return
    apiCall = () => getIndustryNews(key, startDate, endDate, true)
  }

  loading.value = true
  try {
    const data = await apiCall()
    newsList.value = data?.list || []
    sentimentStat.value = data?.sentiment_stat || null
    await nextTick()
    renderPieChart()
    renderTrendChart()
    renderSourceChart()
  } catch {
    newsList.value = []
    sentimentStat.value = null
  } finally {
    loading.value = false
  }
}

function renderPieChart() {
  if (!pieChartRef.value) return
  if (!pieChart) pieChart = echarts.init(pieChartRef.value)
  if (!sentimentStat.value) { pieChart.clear(); return }

  const pieData = []
  const entries = Object.entries(sentimentStat.value)
  for (const [key, val] of entries) {
    const lk = String(key).toLowerCase()
    if (lk.includes('total') || lk.includes('count')) continue
    const numVal = typeof val === 'number' ? val : parseFloat(val) || 0
    if (numVal <= 0) continue
    let name, color
    if (lk.includes('pos')) { name = '正面'; color = UP_COLOR }
    else if (lk.includes('neg')) { name = '负面'; color = DOWN_COLOR }
    else if (lk.includes('neu')) { name = '中性'; color = NEU_COLOR }
    else continue
    pieData.push({ value: numVal, name, itemStyle: { color } })
  }

  if (!pieData.length) { pieChart.clear(); return }

  pieChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    legend: { bottom: 0, left: 'center', textStyle: { color: darkText } },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: 'hsl(224 25% 13%)', borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{d}%', color: darkText },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: pieData,
    }],
  }, true)
}

function renderTrendChart() {
  if (!trendChartRef.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)
  if (!newsList.value.length) { trendChart.clear(); return }

  // 按日期分组统计情感
  const dailyMap = {}
  newsList.value.forEach(item => {
    const d = formatDate(pickField(item, 'date', 'publish_date', 'pub_date', 'time'))
    if (!d) return
    if (!dailyMap[d]) dailyMap[d] = { positive: 0, negative: 0, neutral: 0 }
    const s = sentimentText(item)
    if (s === '正面') dailyMap[d].positive++
    else if (s === '负面') dailyMap[d].negative++
    else dailyMap[d].neutral++
  })

  const dates = Object.keys(dailyMap).sort()
  const posData = dates.map(d => dailyMap[d].positive)
  const negData = dates.map(d => -dailyMap[d].negative)
  const neuData = dates.map(d => dailyMap[d].neutral)

  trendChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    legend: { data: ['正面', '负面', '中性'], top: 0, textStyle: { color: darkText } },
    grid: { left: '8%', right: '4%', top: '15%', bottom: '10%' },
    xAxis: { type: 'category', data: dates, ...darkAxis, axisLabel: { color: 'hsl(215 16% 65%)', fontSize: 10 } },
    yAxis: { type: 'value', ...darkAxis },
    series: [
      { name: '正面', type: 'bar', stack: 'sentiment', data: posData, itemStyle: { color: UP_COLOR } },
      { name: '负面', type: 'bar', stack: 'sentiment', data: negData, itemStyle: { color: DOWN_COLOR } },
      { name: '中性', type: 'bar', stack: 'sentiment', data: neuData, itemStyle: { color: NEU_COLOR } },
    ],
  }, true)
}

function renderSourceChart() {
  if (!sourceChartRef.value) return
  if (!sourceChart) sourceChart = echarts.init(sourceChartRef.value)
  if (!newsList.value.length) { sourceChart.clear(); return }

  const sourceMap = {}
  newsList.value.forEach(item => {
    const src = pickField(item, 'source', 'media') || '未知'
    sourceMap[src] = (sourceMap[src] || 0) + 1
  })

  const sorted = Object.entries(sourceMap).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const sources = sorted.map(e => e[0])
  const counts = sorted.map(e => e[1])

  sourceChart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,24,32,0.95)', borderColor: 'hsl(220 20% 28%)', textStyle: { color: darkText } },
    grid: { left: '15%', right: '8%', top: '5%', bottom: '5%' },
    xAxis: { type: 'value', ...darkAxis },
    yAxis: { type: 'category', data: sources, ...darkAxis, axisLabel: { color: 'hsl(215 16% 65%)', fontSize: 11 } },
    series: [{
      type: 'bar',
      data: counts.map((v, i) => ({
        value: v,
        itemStyle: { color: ['#00d4ff', '#e6382e', '#2ba84a', '#e6a23c', '#a855f7', '#ff7a45', '#409eff', '#909399'][i % 8] },
      })),
      barWidth: '60%',
      label: { show: true, position: 'right', color: darkText },
    }],
  }, true)
}

function handleResize() {
  pieChart?.resize()
  trendChart?.resize()
  sourceChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (stockCode.value) loadNews()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  trendChart?.dispose()
  sourceChart?.dispose()
})
</script>

<style scoped>
.news-page {
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

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
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

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
}

.chart-container-sm {
  width: 100%;
  height: 220px;
}

.word-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  padding: 16px;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

.word-tag {
  font-weight: 600;
  cursor: default;
  transition: all 0.2s;
  line-height: 1.8;
}
.word-tag:hover {
  transform: scale(1.15);
}

.content-layout {
  display: flex;
  gap: 12px;
}

.sentiment-card {
  width: 280px;
  flex-shrink: 0;
  padding: 12px 14px;
}

.news-list-card {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
}

.news-list-container {
  min-height: 400px;
  max-height: 600px;
  overflow-y: auto;
}

.news-item {
  padding: 10px 0;
  border-bottom: 1px solid hsl(220 20% 18%);
}
.news-item:last-child {
  border-bottom: none;
}

.news-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.news-source {
  font-size: 12px;
  color: hsl(215 16% 60%);
}

.news-date {
  font-size: 12px;
  color: hsl(215 14% 45%);
  margin-left: auto;
}

.news-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
  line-height: 1.5;
}

.news-summary {
  font-size: 13px;
  color: hsl(215 16% 60%);
  margin-top: 4px;
  line-height: 1.5;
}

.empty-tip {
  text-align: center;
  color: hsl(215 14% 45%);
  font-size: 13px;
  padding: 40px 0;
}

.up { color: hsl(0 88% 64%); }
.down { color: hsl(149 100% 44%); }
</style>
