<template>
  <div class="dsa-dark-theme industry-chain-view">
    <!-- 页面标题区 -->
    <div class="dsa-page-header">
      <div class="dsa-logo">
        <span class="dsa-logo-icon">🔗</span>
        <span>产业链全景可视化</span>
      </div>
      <span class="dsa-header-tag">申万2021 · 31L1 / 122L2 / 252L3</span>
      <div class="dsa-header-spacer"></div>
      <button class="dsa-header-btn" @click="refreshAll">⟳ 刷新</button>
      <button class="dsa-header-btn primary" @click="exportData">⬇ 导出</button>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" type="border-card" class="chain-tabs dsa-chain-tabs" @tab-change="onTabChange">
      <!-- Tab 1: 传导推演引擎 (ECharts) -->
      <el-tab-pane label="传导推演引擎" name="engine">
        <IndustryChainPanel v-if="loadedTabs.engine" ref="panelRef" />
      </el-tab-pane>

      <!-- Tab 2: 产业图谱沙盘 (ECharts) -->
      <el-tab-pane label="产业图谱沙盘" name="graph">
        <IndustryGraph v-if="loadedTabs.graph" />
      </el-tab-pane>

      <!-- Tab 3: G6 全景沙盘 -->
      <el-tab-pane label="G6 全景沙盘" name="g6">
        <div v-if="loadedTabs.g6" class="g6-wrapper">
          <IndustryChainG6 />
        </div>
      </el-tab-pane>

      <!-- Tab 3.5: 产业链沙盘（数据驱动版，对接底层产业链数据） -->
      <el-tab-pane label="产业链沙盘" name="sandbox">
        <IndustryChainSandbox v-if="loadedTabs.sandbox" />
      </el-tab-pane>

      <!-- Tab 4: 申万产业链台账 -->
      <el-tab-pane label="申万产业链台账" name="ledger">
        <div v-if="loadedTabs.ledger" class="ledger-view">
          <div class="ledger-toolbar">
            <el-select v-model="selectedL1" placeholder="选择一级行业" clearable filterable
                       style="width:240px" @change="loadLedger">
              <el-option v-for="l1 in l1List" :key="l1" :label="l1" :value="l1" />
            </el-select>
            <el-input v-model="searchKeyword" placeholder="搜索行业/公司名称" clearable
                      style="width:240px;margin-left:12px" @input="filterLedger" />
            <el-button type="primary" size="small" style="margin-left:12px" @click="loadLedger">刷新数据</el-button>
          </div>
          <el-table :data="filteredLedger" border stripe size="small" max-height="560"
                    v-loading="ledgerLoading" element-loading-text="加载产业链台账...">
            <el-table-column prop="code" label="行业代码" width="90" align="center" />
            <el-table-column prop="l1_name" label="一级行业" width="100" />
            <el-table-column prop="l2_name" label="二级行业" width="120" />
            <el-table-column prop="l3_name" label="三级行业" width="120" />
            <el-table-column prop="leaders" label="龙头公司" min-width="200" show-overflow-tooltip />
            <el-table-column prop="factors" label="核心影响因素" min-width="180" show-overflow-tooltip />
            <el-table-column label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewChainPath(row)">查路径</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="ledger-stats" v-if="ledgerData.length">
            <el-tag size="small">共 {{ ledgerData.length }} 条记录</el-tag>
            <el-tag size="small" type="success" style="margin-left:8px">{{ l1List.length }} 个一级行业</el-tag>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Share, Refresh, Download } from '@element-plus/icons-vue'
import IndustryChainPanel from './IndustryChainPanel.vue'
import IndustryGraph from './IndustryGraph.vue'
import IndustryChainG6 from './IndustryChainG6.vue'
import IndustryChainSandbox from './IndustryChainSandbox.vue'
import { getSwChain, getChainPath } from '@/api/chain'

const activeTab = ref('engine')
const panelRef = ref(null)

// 懒加载控制
const loadedTabs = reactive({ engine: true, graph: false, g6: false, sandbox: false, ledger: false })

// 申万台账数据
const selectedL1 = ref('')
const searchKeyword = ref('')
const ledgerData = ref([])
const filteredLedger = ref([])
const ledgerLoading = ref(false)
const l1List = ref([])

function onTabChange(tab) {
  loadedTabs[tab] = true
  if (tab === 'ledger' && ledgerData.value.length === 0) {
    loadLedger()
  }
}

async function loadLedger() {
  ledgerLoading.value = true
  try {
    const data = await getSwChain(selectedL1.value || undefined)
    const list = Array.isArray(data) ? data : (data?.list || data?.data || [])
    ledgerData.value = list
    filteredLedger.value = list
    // 提取 L1 列表
    const l1Set = new Set(list.map(item => item.l1_name).filter(Boolean))
    l1List.value = [...l1Set].sort()
    ElMessage.success(`加载 ${list.length} 条产业链记录`)
  } catch {
    // 后端不可用时使用静态数据
    ledgerData.value = getStaticLedger()
    filteredLedger.value = ledgerData.value
    const l1Set = new Set(ledgerData.value.map(item => item.l1_name).filter(Boolean))
    l1List.value = [...l1Set].sort()
    ElMessage.info('后端暂不可用，已加载内置产业链数据')
  }
  ledgerLoading.value = false
}

function filterLedger() {
  if (!searchKeyword.value) {
    filteredLedger.value = ledgerData.value
    return
  }
  const kw = searchKeyword.value.toLowerCase()
  filteredLedger.value = ledgerData.value.filter(item =>
    (item.l1_name || '').toLowerCase().includes(kw) ||
    (item.l2_name || '').toLowerCase().includes(kw) ||
    (item.l3_name || '').toLowerCase().includes(kw) ||
    (item.leaders || '').toLowerCase().includes(kw)
  )
}

function viewChainPath(row) {
  ElMessage.info(`查询 ${row.l3_name || row.l1_name} 的产业链路径...`)
  getChainPath(row.code).then(data => {
    ElMessage.success('产业链路径已生成，请切换到图谱查看')
  }).catch(() => {
    ElMessage.warning('路径查询接口暂不可用')
  })
}

function refreshAll() {
  if (activeTab.value === 'engine' && panelRef.value) {
    panelRef.value.resetChart?.()
  }
  ElMessage.success('已刷新当前页面')
}

function exportData() {
  const blob = new Blob([JSON.stringify({
    ledger: ledgerData.value,
    exportTime: new Date().toISOString(),
  }, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `industry_chain_${Date.now()}.json`
  a.click()
  ElMessage.success('产业链数据已导出')
}

// 内置静态台账数据 (后端不可用时的降级)
function getStaticLedger() {
  return [
    { code: '801030', l1_name: '化工', l2_name: '化学原料', l3_name: '无机盐', leaders: '中盐化工,远兴能源', factors: '原材料价格,下游需求,环保政策' },
    { code: '801031', l1_name: '化工', l2_name: '化学原料', l3_name: '纯碱', leaders: '远兴能源,中盐化工', factors: '光伏玻璃需求,日用玻璃,出口' },
    { code: '801032', l1_name: '化工', l2_name: '化学原料', l3_name: '氯碱', leaders: '中泰化学,新疆天业', factors: 'PVC价格,电力成本,房地产需求' },
    { code: '801080', l1_name: '电子', l2_name: '半导体', l3_name: '集成电路封测', leaders: '长电科技,通富微电,华天科技', factors: '晶圆代工产能,封测订单,国产替代' },
    { code: '801081', l1_name: '电子', l2_name: '半导体', l3_name: '集成电路设计', leaders: '韦尔股份,兆易创新,卓胜微', factors: '下游需求,库存周期,国产替代进度' },
    { code: '801082', l1_name: '电子', l2_name: '半导体', l3_name: '半导体设备', leaders: '北方华创,中微公司,拓荆科技', factors: '晶圆厂资本开支,国产化率,技术突破' },
    { code: '801083', l1_name: '电子', l2_name: '半导体', l3_name: '半导体材料', leaders: '沪硅产业,立昂微,安集科技', factors: '晶圆产能扩张,材料国产化,认证进度' },
    { code: '801230', l1_name: '综合', l2_name: '综合', l3_name: '综合', leaders: '中国宝安,中新药业', factors: '多元化经营,资产重估' },
    { code: '801120', l1_name: '食品饮料', l2_name: '白酒', l3_name: '白酒', leaders: '贵州茅台,五粮液,泸州老窖,山西汾酒', factors: '批价,库存,消费场景,高端化趋势' },
    { code: '801121', l1_name: '食品饮料', l2_name: '非白酒', l3_name: '啤酒', leaders: '青岛啤酒,华润啤酒,重庆啤酒', factors: '吨价提升,原材料成本,高端化' },
    { code: '801730', l1_name: '电力设备', l2_name: '光伏设备', l3_name: '硅片', leaders: '隆基绿能,TCL中环,晶澳科技', factors: '硅料价格,电池片效率,装机需求' },
    { code: '801731', l1_name: '电力设备', l2_name: '光伏设备', l3_name: '电池组件', leaders: '晶科能源,天合光能,晶澳科技', factors: '组件价格,出口数据,装机量' },
    { code: '801732', l1_name: '电力设备', l2_name: '光伏设备', l3_name: '逆变器', leaders: '阳光电源,锦浪科技,固德威', factors: '海外需求,芯片供应,毛利率' },
    { code: '801733', l1_name: '电力设备', l2_name: '风电设备', l3_name: '风电零部件', leaders: '金雷股份,日月股份,天顺风能', factors: '装机量,钢材价格,海风需求' },
    { code: '801740', l1_name: '电力设备', l2_name: '电池', l3_name: '锂电池', leaders: '宁德时代,比亚迪,亿纬锂能', factors: '新能源车销量,储能需求,碳酸锂价格' },
    { code: '801741', l1_name: '电力设备', l2_name: '电池', l3_name: '锂电材料', leaders: '璞泰来,杉杉股份,容百科技', factors: '正负极材料价格,产能利用率,技术路线' },
    { code: '801750', l1_name: '机械设备', l2_name: '通用设备', l3_name: '机器人', leaders: '埃斯顿,汇川技术,绿的谐波', factors: '工业自动化需求,核心部件国产化,AI赋能' },
    { code: '801780', l1_name: '银行', l2_name: '银行', l3_name: '国有大型银行', leaders: '工商银行,建设银行,农业银行', factors: '信贷投放,净息差,资产质量,政策利率' },
    { code: '801781', l1_name: '银行', l2_name: '银行', l3_name: '股份制银行', leaders: '招商银行,兴业银行,平安银行', factors: '零售业务,财富管理,息差' },
    { code: '801790', l1_name: '非银金融', l2_name: '证券', l3_name: '证券', leaders: '中信证券,东方财富,华泰证券', factors: '成交量,两融余额,IPO发行,市场情绪' },
  ]
}

onMounted(() => {
  // 默认加载第一个 Tab
  loadedTabs.engine = true
})
</script>

<style scoped>
@import '@/styles/dark-theme.css';

.industry-chain-view {
  width: 100%;
  min-height: calc(100vh - 60px);
}

.dsa-chain-tabs {
  margin: 0 12px 12px;
  border: none !important;
}

.g6-wrapper {
  height: calc(100vh - 200px);
  min-height: 600px;
}

.ledger-view {
  padding: 8px;
}

.ledger-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.ledger-stats {
  margin-top: 8px;
  padding: 4px 0;
}

:deep(.el-tabs__content) {
  padding: 16px;
}

:deep(.el-tab-pane) {
  min-height: 500px;
}
</style>
