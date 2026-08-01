<template>
  <div class="dsa-dark-theme macro-capital-view">
    <!-- 页面标题区 -->
    <div class="dsa-page-header">
      <div class="dsa-logo">
        <span class="dsa-logo-icon">🌐</span>
        <span>资金全球动态可视化</span>
      </div>
      <span class="dsa-header-tag">10国经济体 · 实时监测 + 情景推演</span>
      <div class="dsa-header-spacer"></div>
      <button class="dsa-header-btn" @click="refreshAll">⟳ 刷新全球数据</button>
      <button class="dsa-header-btn primary" @click="aiMacroReport">🤖 AI 宏观研判</button>
    </div>

    <!-- KPI 指标行 -->
    <div class="kpi-row">
      <div class="dsa-kpi-card" v-for="kpi in kpiList" :key="kpi.label">
        <div class="dsa-kpi-icon" :style="{ background: kpi.bg, color: kpi.color }">
          <el-icon size="20"><component :is="kpi.icon" /></el-icon>
        </div>
        <div class="dsa-kpi-body">
          <div class="dsa-kpi-label">{{ kpi.label }}</div>
          <div class="dsa-kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
          <div class="dsa-kpi-sub">{{ kpi.sub }}</div>
        </div>
      </div>
    </div>

    <!-- 主内容区：双 Tab -->
    <el-tabs v-model="activeTab" type="border-card" class="macro-tabs">
      <!-- Tab 1: 实时监测看板 -->
      <el-tab-pane label="实时监测看板" name="monitor">
        <div class="monitor-row">
          <!-- 全球货币脆弱性热力图 -->
          <div class="chart-card flex-2">
            <div class="card-title">全球货币脆弱性热力监测</div>
            <WorldMap @country-dblclick="jumpToSim" />
          </div>
          <!-- 资本流动柱状图 -->
          <div class="chart-card flex-1">
            <div class="card-title">全球资本净流入/流出 (亿美元)</div>
            <div ref="capitalFlowRef" class="chart-container"></div>
          </div>
        </div>
        <div class="monitor-row">
          <!-- 各国政策利率对比 -->
          <div class="chart-card flex-1">
            <div class="card-title">各国政策利率对比 (%)</div>
            <div ref="rateCompareRef" class="chart-container"></div>
          </div>
          <!-- 债务/GDP 趋势 -->
          <div class="chart-card flex-1">
            <div class="card-title">政府债务/GDP 趋势 (%)</div>
            <div ref="debtGdpRef" class="chart-container"></div>
          </div>
          <!-- 外汇储备对比 -->
          <div class="chart-card flex-1">
            <div class="card-title">外汇储备总量 (十亿美元)</div>
            <div ref="fxReserveRef" class="chart-container"></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 宏观情景推演沙盘 -->
      <el-tab-pane label="宏观情景推演沙盘" name="simulation">
        <div class="sim-container">
          <!-- 左侧事件 + 控制 -->
          <div class="sim-left">
            <div class="panel-title">可投放宏观冲击事件</div>
            <div class="drag-event-item" v-for="ev in macroEvents" :key="ev.id"
                 draggable="true" @dragstart="onDragEvent($event, ev)"
                 :style="{ borderLeft: '4px solid ' + (ev.direction === 'positive' ? '#22c55e' : '#ef4444') }">
              <div class="event-header">
                <el-tag :type="ev.direction === 'positive' ? 'success' : 'danger'" size="small">
                  {{ ev.direction === 'positive' ? '利好' : '利空' }}
                </el-tag>
                <span class="event-title">{{ ev.title }}</span>
              </div>
              <div class="event-desc">{{ ev.desc }}</div>
            </div>

            <el-divider />
            <div class="panel-title">沙盘控制</div>
            <el-button type="primary" @click="startSim" :disabled="!simRootId || simRunning" style="width:100%">
              ▶ 开始推演
            </el-button>
            <el-button @click="stopSim" :disabled="!simRunning" style="width:100%;margin-top:6px">
              ⏸ 暂停
            </el-button>
            <el-button type="danger" @click="resetSim" style="width:100%;margin-top:6px">
              🗑 清空推演
            </el-button>

            <el-divider />
            <div class="panel-title">时间轴 ({{ simProgress }}/{{ simTotalStep }})</div>
            <el-slider v-model="simProgress" :max="simTotalStep" :step="1" @change="seekStep" size="small" />
            <div v-if="simRootId" class="tip">冲击源: {{ simRootId }}</div>

            <el-divider />
            <div class="panel-title">传导路径日志</div>
            <TransmissionLog :steps="transmissionSteps" />
          </div>

          <!-- 中央国家网络图 -->
          <div class="sim-center">
            <div ref="networkRef" class="network-chart"></div>
          </div>

          <!-- 右侧国家详情 -->
          <div class="sim-right">
            <CountryDetail
              :entity-data="currentEntity"
              :is-simulation-mode="true"
              :impact-data="simImpactResult"
              @ai-analysis="handleAiCall"
              @refresh="reloadEntity"
            />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { Money, Refresh, MagicStick, TrendCharts, DataAnalysis, Coin, Histogram } from '@element-plus/icons-vue'
import WorldMap from './macro/WorldMap.vue'
import CountryDetail from './macro/CountryDetail.vue'
import TransmissionLog from './macro/TransmissionLog.vue'
import { getCountries, getSimEvents, calcSimPath, getAiMacroReport } from '@/api/macro'

const activeTab = ref('monitor')
const capitalFlowRef = ref(null)
const rateCompareRef = ref(null)
const debtGdpRef = ref(null)
const fxReserveRef = ref(null)
const networkRef = ref(null)

let capitalChart = null
let rateChart = null
let debtChart = null
let fxChart = null
let networkChart = null

// 国家数据
const countryList = ref([])
const currentEntity = ref(null)

// KPI 指标
const kpiList = ref([
  { label: '监测经济体', value: '10', sub: '全球主要经济体', icon: 'DataAnalysis', color: '#409eff', bg: '#ecf5ff' },
  { label: '高危预警', value: '0', sub: '脆弱性 > 80', icon: 'TrendCharts', color: '#f56c6c', bg: '#fef0f0' },
  { label: '全球平均利率', value: '--', sub: '政策基准利率', icon: 'Coin', color: '#e6a23c', bg: '#fdf6ec' },
  { label: '资本净流动', value: '--', sub: '月度净额(亿美元)', icon: 'Histogram', color: '#67c23a', bg: '#f0f9eb' },
])

// 沙盘变量
const macroEvents = ref([])
const simRunning = ref(false)
const simRootId = ref(null)
const simProgress = ref(0)
const simTotalStep = ref(6)
const simImpactResult = ref({})
const transmissionSteps = ref([])
let simPathList = []
let animTimer = null
let dragEventData = null

// ====== 静态数据 (后端不可用时的降级) ======
const staticCountries = [
  { id: 'USA', name: '美国', flag: '🇺🇸', riskScore: 32, indicators: { debt_gdp: 128, policy_rate: 5.5, cpi: 3.2, fx_reserve: '740B', ca_gdp: -3.5, cds_spread: 18 } },
  { id: 'CN', name: '中国', flag: '🇨🇳', riskScore: 36, indicators: { debt_gdp: 83, policy_rate: 3.45, cpi: 0.2, fx_reserve: '3.2T', ca_gdp: 1.5, cds_spread: 55 } },
  { id: 'JP', name: '日本', flag: '🇯🇵', riskScore: 41, indicators: { debt_gdp: 255, policy_rate: 0.1, cpi: 2.8, fx_reserve: '1.3T', ca_gdp: 3.3, cds_spread: 25 } },
  { id: 'DE', name: '德国', flag: '🇩🇪', riskScore: 44, indicators: { debt_gdp: 67, policy_rate: 4.0, cpi: 2.9, fx_reserve: '70B', ca_gdp: 6.2, cds_spread: 22 } },
  { id: 'IN', name: '印度', flag: '🇮🇳', riskScore: 59, indicators: { debt_gdp: 82, policy_rate: 6.5, cpi: 5.1, fx_reserve: '650B', ca_gdp: -1.8, cds_spread: 75 } },
  { id: 'BR', name: '巴西', flag: '🇧🇷', riskScore: 68, indicators: { debt_gdp: 88, policy_rate: 10.75, cpi: 4.2, fx_reserve: '350B', ca_gdp: -1.2, cds_spread: 120 } },
  { id: 'GB', name: '英国', flag: '🇬🇧', riskScore: 47, indicators: { debt_gdp: 98, policy_rate: 5.25, cpi: 3.4, fx_reserve: '85B', ca_gdp: -2.8, cds_spread: 30 } },
  { id: 'RU', name: '俄罗斯', flag: '🇷🇺', riskScore: 55, indicators: { debt_gdp: 21, policy_rate: 16, cpi: 7.4, fx_reserve: '420B', ca_gdp: 5.1, cds_spread: 200 } },
  { id: 'KR', name: '韩国', flag: '🇰🇷', riskScore: 42, indicators: { debt_gdp: 58, policy_rate: 3.5, cpi: 2.6, fx_reserve: '420B', ca_gdp: 2.2, cds_spread: 28 } },
  { id: 'ZA', name: '南非', flag: '🇿🇦', riskScore: 62, indicators: { debt_gdp: 73, policy_rate: 8.25, cpi: 5.1, fx_reserve: '60B', ca_gdp: -3.0, cds_spread: 180 } },
]

const staticEvents = [
  { id: 'evt01', title: '美联储降息50bp', direction: 'positive', desc: '全球流动性宽松，新兴市场资本回流' },
  { id: 'evt02', title: '美债收益率飙升', direction: 'negative', desc: '美元走强，新兴市场资本外流压力' },
  { id: 'evt03', title: '人民币汇率企稳', direction: 'positive', desc: '中国资本流入预期增强，亚太情绪改善' },
  { id: 'evt04', title: '欧央行维持高利率', direction: 'negative', desc: '欧洲经济承压，欧元区债务风险上升' },
  { id: 'evt05', title: '新兴市场债务危机', direction: 'negative', desc: '高脆弱国家违约风险上升，避险情绪蔓延' },
  { id: 'evt06', title: '大宗商品涨价周期', direction: 'positive', desc: '资源出口国贸易改善，资本流入加速' },
]

// ====== 数据加载 ======
async function loadCountries() {
  try {
    const data = await getCountries()
    countryList.value = Array.isArray(data) ? data : (data?.data || staticCountries)
  } catch {
    countryList.value = staticCountries
  }
  updateKPIs()
}

async function loadEvents() {
  try {
    const data = await getSimEvents()
    macroEvents.value = Array.isArray(data) ? data : (data?.data || staticEvents)
  } catch {
    macroEvents.value = staticEvents
  }
}

function updateKPIs() {
  const countries = countryList.value
  if (!countries.length) return
  const highRisk = countries.filter(c => (c.riskScore || 0) > 60).length
  const avgRate = countries.reduce((s, c) => s + (c.indicators?.policy_rate || 0), 0) / countries.length
  kpiList.value[1].value = String(highRisk)
  kpiList.value[2].value = avgRate.toFixed(2) + '%'
  kpiList.value[3].value = '---'
}

// ====== ECharts 图表 ======
function renderCapitalFlow() {
  if (!capitalFlowRef.value) return
  capitalChart = echarts.init(capitalFlowRef.value)
  const countries = countryList.value.length ? countryList.value : staticCountries
  const flowData = countries.map(c => ({
    name: c.name,
    value: Math.round((Math.random() - 0.3) * 200),
    riskScore: c.riskScore,
  }))
  capitalChart.setOption({
    tooltip: { trigger: 'axis', formatter: p => `${p[0].name}<br/>净流动: ${p[0].value > 0 ? '+' : ''}${p[0].value}亿美元` },
    grid: { left: '8%', right: '5%', bottom: '15%', top: '10%' },
    xAxis: { type: 'category', data: flowData.map(d => d.name), axisLabel: { rotate: 35, fontSize: 10 } },
    yAxis: { name: '亿美元', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar', data: flowData.map(d => ({
        value: d.value,
        itemStyle: { color: d.value > 0 ? '#e6382e' : '#2ba84a' },
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', fontSize: 10, formatter: '{c}' },
    }],
  })
}

function renderRateCompare() {
  if (!rateCompareRef.value) return
  rateChart = echarts.init(rateCompareRef.value)
  const countries = countryList.value.length ? countryList.value : staticCountries
  rateChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '15%', top: '10%' },
    xAxis: { type: 'category', data: countries.map(c => c.name), axisLabel: { rotate: 35, fontSize: 10 } },
    yAxis: { name: '%', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar', data: countries.map(c => ({
        value: c.indicators?.policy_rate || 0,
        itemStyle: { color: '#409eff' },
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', fontSize: 9, formatter: '{c}%' },
    }],
  })
}

function renderDebtGdp() {
  if (!debtGdpRef.value) return
  debtChart = echarts.init(debtGdpRef.value)
  const countries = countryList.value.length ? countryList.value : staticCountries
  debtChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '5%', bottom: '15%', top: '10%' },
    xAxis: { type: 'category', data: countries.map(c => c.name), axisLabel: { rotate: 35, fontSize: 10 } },
    yAxis: { name: '%', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar', data: countries.map(c => ({
        value: c.indicators?.debt_gdp || 0,
        itemStyle: {
          color: (c.indicators?.debt_gdp || 0) > 100 ? '#f56c6c' : (c.indicators?.debt_gdp || 0) > 60 ? '#e6a23c' : '#67c23a',
        },
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', fontSize: 9, formatter: '{c}%' },
    }],
  })
}

function renderFxReserve() {
  if (!fxReserveRef.value) return
  fxChart = echarts.init(fxReserveRef.value)
  const countries = countryList.value.length ? countryList.value : staticCountries
  const reserveData = countries.map(c => {
    const raw = c.indicators?.fx_reserve || '0'
    const num = parseFloat(raw.replace(/[^\d.]/g, ''))
    const unit = raw.includes('T') ? num * 1000 : num
    return { name: c.name, value: Math.round(unit || 0) }
  })
  fxChart.setOption({
    tooltip: { trigger: 'axis', formatter: p => `${p[0].name}<br/>外储: $${p[0].value}B` },
    grid: { left: '8%', right: '5%', bottom: '15%', top: '10%' },
    xAxis: { type: 'category', data: reserveData.map(d => d.name), axisLabel: { rotate: 35, fontSize: 10 } },
    yAxis: { name: '十亿美元', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar', data: reserveData.map(d => ({ value: d.value, itemStyle: { color: '#9254de' } })),
      barWidth: '50%',
      label: { show: true, position: 'top', fontSize: 9 },
    }],
  })
}

// ====== 推演沙盘 ======
function renderNetwork() {
  if (!networkRef.value) return
  if (networkChart) { networkChart.dispose(); networkChart = null }
  networkChart = echarts.init(networkRef.value)
  const countries = countryList.value.length ? countryList.value : staticCountries

  const nodes = countries.map(c => ({
    id: c.id, name: c.name, symbolSize: 40 + (c.riskScore || 30) / 2,
    category: c.riskScore <= 35 ? 0 : c.riskScore <= 60 ? 1 : 2,
    itemStyle: {
      color: c.riskScore <= 35 ? '#22c55e' : c.riskScore <= 60 ? '#fbbf24' : '#ef4444',
    },
    label: { show: true, fontSize: 11, color: '#e2e8f0' },
  }))

  // 国家间传导关系 (模拟)
  const links = [
    { source: 'USA', target: 'CN', value: '贸易' }, { source: 'USA', target: 'JP', value: '利率' },
    { source: 'USA', target: 'DE', value: '利率' }, { source: 'USA', target: 'IN', value: '资本' },
    { source: 'USA', target: 'BR', value: '资本' }, { source: 'USA', target: 'GB', value: '利率' },
    { source: 'USA', target: 'KR', value: '资本' }, { source: 'CN', target: 'JP', value: '贸易' },
    { source: 'CN', target: 'KR', value: '贸易' }, { source: 'CN', target: 'ZA', value: '资源' },
    { source: 'DE', target: 'RU', value: '能源' }, { source: 'DE', target: 'GB', value: '贸易' },
    { source: 'IN', target: 'RU', value: '能源' }, { source: 'BR', target: 'CN', value: '资源' },
    { source: 'JP', target: 'KR', value: '资本' }, { source: 'GB', target: 'ZA', value: '资本' },
  ].map(l => ({ ...l, lineStyle: { width: 2, curveness: 0.2, color: '#555' } }))

  networkChart.setOption({
    tooltip: { formatter: p => p.dataType === 'node' ? `${p.data.name} (脆弱性:${p.data.symbolSize})` : `${p.data.source} → ${p.data.target}` },
    legend: { data: ['稳定', '中等', '高脆弱'], textStyle: { color: '#94a3b8' }, bottom: 5 },
    series: [{
      type: 'graph', layout: 'force', nodes, links, roam: true, draggable: true,
      force: { repulsion: 300, edgeLength: [100, 200] },
      categories: [
        { name: '稳定', itemStyle: { color: '#22c55e' } },
        { name: '中等', itemStyle: { color: '#fbbf24' } },
        { name: '高脆弱', itemStyle: { color: '#ef4444' } },
      ],
      lineStyle: { opacity: 0.5 },
      edgeLabel: { show: false },
    }],
  })

  networkChart.on('click', p => {
    if (p.dataType === 'node') {
      const country = countryList.value.find(c => c.id === p.data.id)
      if (country) {
        currentEntity.value = country
        if (dragEventData) {
          simRootId.value = p.data.id
          ElMessage.success(`冲击源: ${country.name}`)
          dragEventData = null
        }
      }
    }
  })
}

function onDragEvent(_e, ev) {
  dragEventData = ev
  ElMessage.info(`已选择事件「${ev.title}」，点击网络节点设定冲击源`)
}

async function startSim() {
  if (!simRootId.value || simRunning.value) return
  resetSim()
  simRunning.value = true
  simProgress.value = 0
  transmissionSteps.value = []

  const rootCountry = countryList.value.find(c => c.id === simRootId.value)
  transmissionSteps.value.push({
    type: 'event', time: new Date().toLocaleTimeString(),
    title: `${dragEventData?.title || '宏观冲击事件'} → ${rootCountry?.name || simRootId.value}`,
    detail: dragEventData?.desc || '', impact: dragEventData?.direction === 'positive' ? 8 : -8,
  })

  try {
    const data = await calcSimPath({ rootNodeId: simRootId.value, baseStrength: 0.8, minCoeffFilter: 0.1, maxLevel: 5 })
    simPathList = Array.isArray(data) ? data : (data?.data || [])
    simTotalStep.value = simPathList.length ? Math.max(...simPathList.map(s => s.step)) : 3
  } catch {
    // 前端 BFS 降级
    const adj = { USA: ['CN', 'JP', 'DE', 'IN', 'BR', 'GB', 'KR'], CN: ['JP', 'KR', 'ZA', 'BR'],
      JP: ['KR', 'USA'], DE: ['RU', 'GB', 'USA'], IN: ['RU', 'USA'], BR: ['CN', 'USA'],
      GB: ['ZA', 'DE', 'USA'], RU: ['DE', 'IN'], KR: ['JP', 'CN', 'USA'], ZA: ['CN', 'GB'] }
    simPathList = []
    const visited = new Set([simRootId.value])
    let frontier = [simRootId.value]
    for (let step = 1; step <= 4; step++) {
      const next = []
      frontier.forEach(src => {
        (adj[src] || []).forEach(tgt => {
          if (!visited.has(tgt)) {
            visited.add(tgt)
            simPathList.push({ step, source_id: src, target_id: tgt, final_impact: dragEventData?.direction === 'positive' ? step * 2 : -step * 2 })
            next.push(tgt)
          }
        })
      })
      frontier = next
    }
    simTotalStep.value = simPathList.length ? Math.max(...simPathList.map(s => s.step)) : 3
  }

  const loop = () => {
    if (!simRunning.value) return
    simProgress.value += 1
    applyStep(simProgress.value)
    if (simProgress.value >= simTotalStep.value) {
      simRunning.value = false
      transmissionSteps.value.push({
        type: 'event', time: new Date().toLocaleTimeString(),
        title: '推演完成', detail: `共传导 ${simPathList.length} 条路径`, impact: 0,
      })
      return
    }
    animTimer = setTimeout(loop, 1500)
  }
  loop()
}

function applyStep(step) {
  const active = simPathList.filter(p => p.step <= step)
  active.forEach(p => {
    const source = countryList.value.find(c => c.id === p.source_id)
    const target = countryList.value.find(c => c.id === p.target_id)
    if (source && target) {
      transmissionSteps.value.push({
        type: 'node', time: new Date().toLocaleTimeString(),
        title: `${source.name} → ${target.name}`,
        detail: `传导强度: ${Math.abs(p.final_impact || 0).toFixed(1)}`,
        impact: p.final_impact || 0, coeff: 0.5,
      })
    }
  })

  // 更新网络图高亮
  if (networkChart) {
    const opt = networkChart.getOption()
    const activeIds = new Set(active.flatMap(p => [p.source_id, p.target_id]))
    opt.series[0].nodes = opt.series[0].nodes.map(n => ({
      ...n,
      itemStyle: {
        color: activeIds.has(n.id)
          ? (dragEventData?.direction === 'positive' ? '#22c55e' : '#ef4444')
          : n.itemStyle?.color,
        borderColor: activeIds.has(n.id) ? '#fff' : 'transparent',
        borderWidth: activeIds.has(n.id) ? 3 : 0,
      },
      symbolSize: activeIds.has(n.id) ? (n.symbolSize || 40) * 1.3 : n.symbolSize,
    }))
    opt.series[0].links = opt.series[0].links.map(l => {
      const isActive = active.some(p => p.source_id === l.source && p.target_id === l.target)
      return { ...l, lineStyle: { ...l.lineStyle, color: isActive ? (dragEventData?.direction === 'positive' ? '#22c55e' : '#ef4444') : '#555', width: isActive ? 4 : 2 } }
    })
    networkChart.setOption(opt)
  }
}

function seekStep(v) { if (!simRunning.value) applyStep(v) }
function stopSim() { simRunning.value = false; if (animTimer) clearTimeout(animTimer) }
function resetSim() {
  stopSim(); simProgress.value = 0; simPathList = []; simRootId.value = null
  simImpactResult.value = {}; transmissionSteps.value = []
  if (networkChart) renderNetwork()
}

function jumpToSim(countryName) {
  activeTab.value = 'simulation'
  const country = countryList.value.find(c => c.name === countryName)
  if (country) {
    nextTick(() => {
      simRootId.value = country.id
      currentEntity.value = country
    })
  }
}

function refreshAll() {
  loadCountries().then(() => {
    renderCapitalFlow(); renderRateCompare(); renderDebtGdp(); renderFxReserve()
    if (activeTab.value === 'simulation') renderNetwork()
  })
  ElMessage.success('全球数据已刷新')
}

function aiMacroReport() {
  ElMessage.info('AI 宏观研判中...')
  getAiMacroReport({ scenario: 'global_monitor' }).then(data => {
    ElMessage.success('AI 宏观报告已生成')
  }).catch(() => {
    ElMessage.warning('AI 接口暂不可用，请稍后重试')
  })
}

function handleAiCall(entity) {
  ElMessage.info(`AI 解读 ${entity?.name || ''} 的宏观状况...`)
}

async function reloadEntity(id) {
  const country = countryList.value.find(c => c.id === (id || currentEntity.value?.id))
  if (country) currentEntity.value = country
}

watch(activeTab, v => {
  if (v === 'simulation') {
    nextTick(() => renderNetwork())
  }
})

function handleResize() {
  capitalChart?.resize(); rateChart?.resize(); debtChart?.resize(); fxChart?.resize(); networkChart?.resize()
}

onMounted(async () => {
  await loadCountries()
  await loadEvents()
  nextTick(() => {
    renderCapitalFlow(); renderRateCompare(); renderDebtGdp(); renderFxReserve()
  })
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (animTimer) clearTimeout(animTimer)
  window.removeEventListener('resize', handleResize)
  capitalChart?.dispose(); rateChart?.dispose(); debtChart?.dispose(); fxChart?.dispose(); networkChart?.dispose()
})
</script>

<style scoped>
@import '@/styles/dark-theme.css';

.macro-capital-view { width: 100%; min-height: calc(100vh - 60px); }

.kpi-row {
  display: flex; gap: 16px; margin: 12px 16px;
}

.macro-tabs {
  margin: 0 12px 12px;
  border: none !important;
}
:deep(.el-tabs__content) { padding: 16px; }

.monitor-row {
  display: flex; gap: 16px; margin-bottom: 16px;
}
.chart-card {
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px; padding: 12px;
}
.flex-1 { flex: 1; }
.flex-2 { flex: 2; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: hsl(210 20% 92%); }
.chart-container { width: 100%; height: 300px; }

.sim-container {
  display: flex; gap: 12px; min-height: 600px;
}
.sim-left {
  width: 280px;
  background: hsl(225 28% 11%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px; padding: 14px; overflow-y: auto;
}
.sim-center {
  flex: 1; background: hsl(228 35% 7%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px; min-width: 0;
}
.sim-right {
  width: 360px;
  background: hsl(225 28% 11%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px; padding: 8px; overflow-y: auto;
}
.network-chart { width: 100%; height: 100%; min-height: 580px; }

.panel-title { font-weight: 700; margin: 10px 0 6px; font-size: 13px; color: hsl(210 20% 92%); }
.drag-event-item {
  background: hsl(224 25% 13%);
  padding: 10px; border-radius: 6px;
  border: 1px solid hsl(220 20% 20%);
  margin-bottom: 8px; cursor: grab;
}
.event-header { display: flex; align-items: center; gap: 6px; }
.event-title { font-size: 12px; font-weight: 600; color: hsl(210 20% 92%); }
.event-desc { font-size: 11px; color: hsl(215 14% 45%); margin-top: 4px; }
.tip { font-size: 11px; color: hsl(215 14% 45%); margin-top: 4px; }
</style>
