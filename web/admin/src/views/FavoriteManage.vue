<template>
  <div class="favorite-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left-area">
        <h2 class="page-title">自选股管理</h2>
        <div class="stat-chips">
          <span class="stat-chip">
            <el-icon><Star /></el-icon>
            {{ tableData.length }} 只
          </span>
          <span class="stat-chip up" v-if="upCount > 0">
            <el-icon><Top /></el-icon>
            {{ upCount }} 涨
          </span>
          <span class="stat-chip down" v-if="downCount > 0">
            <el-icon><Bottom /></el-icon>
            {{ downCount }} 跌
          </span>
        </div>
      </div>
      <div class="header-actions">
        <el-button @click="showImportDialog = true" size="small">
          <el-icon><Upload /></el-icon>
          批量导入
        </el-button>
        <el-button @click="toggleBatchMode" size="small" :type="batchMode ? 'warning' : 'default'">
          <el-icon><Operation /></el-icon>
          {{ batchMode ? '退出批量' : '批量管理' }}
        </el-button>
        <el-button type="primary" @click="showAddDialog = true" size="small">
          <el-icon><Plus /></el-icon>
          添加自选
        </el-button>
      </div>
    </div>

    <!-- 分组标签栏 -->
    <div class="group-tabs">
      <div
        class="group-tab"
        :class="{ active: activeGroup === 'all' }"
        @click="activeGroup = 'all'"
      >
        <el-icon><Grid /></el-icon>
        全部
        <span class="group-count">{{ tableData.length }}</span>
      </div>
      <div
        v-for="g in groups"
        :key="g.name"
        class="group-tab"
        :class="{ active: activeGroup === g.name }"
        @click="activeGroup = g.name"
      >
        <el-icon><CollectionTag /></el-icon>
        {{ g.name }}
        <span class="group-count">{{ g.count }}</span>
      </div>
      <div class="group-tab add-group" @click="showGroupDialog = true">
        <el-icon><Plus /></el-icon>
        新建分组
      </div>
    </div>

    <!-- 自选股列表 -->
    <div class="table-card">
      <el-table
        v-loading="loading"
        :data="filteredData"
        stripe
        style="width: 100%"
        @row-click="handleRowClick"
        @selection-change="handleSelectionChange"
        :row-class-name="rowClassName"
      >
        <el-table-column v-if="batchMode" type="selection" width="45" />
        <el-table-column type="index" label="#" width="50" />

        <el-table-column prop="code" label="代码" width="100">
          <template #default="{ row }">
            <span class="stock-code">{{ row.code || row.stock_code }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="name" label="名称" width="130">
          <template #default="{ row }">
            <div class="stock-name-cell">
              <span class="stock-name">{{ row.name || row.stock_name || '—' }}</span>
              <el-tag
                v-if="row.group"
                size="small"
                type="info"
                effect="plain"
                class="group-tag"
              >{{ row.group }}</el-tag>
            </div>
          </template>
        </el-table-column>

        <!-- 实时行情迷你展示 -->
        <el-table-column label="最新价" width="100" align="right">
          <template #default="{ row }">
            <span class="quote-text" :class="priceClass(row)">
              {{ row.price != null ? formatPrice(row.price) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="涨跌幅" width="90" align="right">
          <template #default="{ row }">
            <span class="quote-text" :class="priceClass(row)">
              {{ formatPercent(row.change || row.pct_chg) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="涨跌额" width="90" align="right">
          <template #default="{ row }">
            <span class="quote-text sm" :class="priceClass(row)">
              {{ row.change_amount != null ? formatPrice(row.change_amount) : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 资金流向指标 -->
        <el-table-column label="主力净流入" width="120" align="right">
          <template #default="{ row }">
            <div v-if="row.net_amount != null" class="capital-cell">
              <span class="capital-bar" :class="row.net_amount >= 0 ? 'bar-up' : 'bar-down'">
                <span
                  class="capital-fill"
                  :style="{ width: getBarWidth(row.net_amount) + '%' }"
                ></span>
              </span>
              <span class="capital-val" :class="row.net_amount >= 0 ? 'text-up' : 'text-down'">
                {{ formatCapital(row.net_amount) }}
              </span>
            </div>
            <span v-else class="text-dim">—</span>
          </template>
        </el-table-column>

        <el-table-column prop="add_time" label="添加时间" width="150">
          <template #default="{ row }">
            <span class="text-muted">{{ formatTime(row.add_time || row.created_at || row.create_time) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click.stop="goToMarket(row)">
              <el-icon><TrendCharts /></el-icon>
              行情
            </el-button>
            <el-button size="small" type="info" link @click.stop="goToAI(row)">
              <el-icon><MagicStick /></el-icon>
              分析
            </el-button>
            <el-button size="small" type="danger" link @click.stop="handleDelete(row)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <div class="empty-tip">
            <el-icon size="40" color="hsl(215 14% 35%)"><StarOff /></el-icon>
            <p style="margin-top: 8px">暂无自选股，点击右上角添加</p>
          </div>
        </template>
      </el-table>

      <!-- 批量操作工具栏 -->
      <transition name="slide-up">
        <div v-if="batchMode && selectedRows.length > 0" class="batch-toolbar">
          <span class="batch-info">已选 {{ selectedRows.length }} 只</span>
          <el-select v-model="batchGroup" placeholder="移动到分组" size="small" style="width: 140px">
            <el-option v-for="g in groups" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
          <el-button size="small" @click="batchMoveGroup" :disabled="!batchGroup">
            <el-icon><Rank /></el-icon>
            移动分组
          </el-button>
          <el-button size="small" type="danger" @click="batchDelete">
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
          <el-button size="small" text @click="batchMode = false">取消</el-button>
        </div>
      </transition>
    </div>

    <!-- 添加弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加自选股" width="440px">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="股票代码" required>
          <el-input
            v-model="addForm.code"
            placeholder="请输入股票代码，如 000001"
            @keyup.enter="handleAdd"
          />
        </el-form-item>
        <el-form-item label="股票名称">
          <el-input
            v-model="addForm.name"
            placeholder="可选，如 平安银行"
            @keyup.enter="handleAdd"
          />
        </el-form-item>
        <el-form-item label="所属分组">
          <el-select v-model="addForm.group" placeholder="选择分组（可选）" clearable style="width: 100%">
            <el-option v-for="g in groups" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleAdd">
          确认添加
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="showImportDialog" title="批量导入自选股" width="520px">
      <el-alert type="info" :closable="false" style="margin-bottom: 12px">
        每行一个股票代码，支持 6 位数字代码（如 000001, 600519）
      </el-alert>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="8"
        placeholder="000001&#10;000002&#10;600519&#10;300750"
      />
      <el-form-item label="导入分组" style="margin-top: 12px">
        <el-select v-model="importGroup" placeholder="选择分组（可选）" clearable style="width: 100%">
          <el-option v-for="g in groups" :key="g.name" :label="g.name" :value="g.name" />
        </el-select>
      </el-form-item>
      <template #footer>
        <el-button @click="showImportDialog = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="handleImport">
          导入 ({{ importCodeList.length }} 只)
        </el-button>
      </template>
    </el-dialog>

    <!-- 新建分组弹窗 -->
    <el-dialog v-model="showGroupDialog" title="新建分组" width="360px">
      <el-input v-model="newGroupName" placeholder="分组名称，如：核心持仓、观察池" @keyup.enter="addGroup" />
      <template #footer>
        <el-button @click="showGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="addGroup">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { getFavoriteList, addFavorite, deleteFavorite } from '@/api/favorite'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const tableData = ref([])
const showAddDialog = ref(false)
const addLoading = ref(false)
const addForm = ref({ code: '', name: '', group: '' })

// 批量模式
const batchMode = ref(false)
const selectedRows = ref([])
const batchGroup = ref('')

// 批量导入
const showImportDialog = ref(false)
const importText = ref('')
const importLoading = ref(false)
const importGroup = ref('')

// 分组管理
const showGroupDialog = ref(false)
const newGroupName = ref('')
const activeGroup = ref('all')

// 本地分组数据（持久化到 localStorage）
const groups = reactive([])

// 加载分组
function loadGroups() {
  try {
    const saved = localStorage.getItem('dsa_fav_groups')
    if (saved) {
      const parsed = JSON.parse(saved)
      groups.splice(0, groups.length, ...parsed)
    }
  } catch {}
}

// 保存分组
function saveGroups() {
  localStorage.setItem('dsa_fav_groups', JSON.stringify(groups))
}

// 添加分组
function addGroup() {
  const name = newGroupName.value.trim()
  if (!name) return
  if (groups.some(g => g.name === name)) {
    ElMessage.warning('分组已存在')
    return
  }
  groups.push({ name, count: 0 })
  saveGroups()
  newGroupName.value = ''
  showGroupDialog.value = false
  ElMessage.success('分组已创建')
}

// 更新分组计数
function updateGroupCounts() {
  groups.forEach(g => {
    g.count = tableData.value.filter(t => t.group === g.name).length
  })
}

// 按分组过滤
const filteredData = computed(() => {
  if (activeGroup.value === 'all') return tableData.value
  return tableData.value.filter(t => t.group === activeGroup.value)
})

// 统计
const upCount = computed(() => tableData.value.filter(t => parseFloat(t.change || t.pct_chg) > 0).length)
const downCount = computed(() => tableData.value.filter(t => parseFloat(t.change || t.pct_chg) < 0).length)

// 导入代码列表
const importCodeList = computed(() => {
  return importText.value.split('\n').map(s => s.trim()).filter(s => /^\d{6}$/.test(s))
})

function formatTime(t) {
  if (!t) return '—'
  return dayjs(t).format('YYYY-MM-DD HH:mm')
}

function formatPrice(v) {
  if (v == null) return '—'
  return parseFloat(v).toFixed(2)
}

function formatPercent(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function formatCapital(v) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (abs >= 1e4) return (v / 1e4).toFixed(0) + '万'
  return v.toFixed(0)
}

function getBarWidth(v) {
  if (!v) return 0
  const abs = Math.abs(v)
  // 对数缩放，最大 100%
  const max = 1e8
  return Math.min(100, (Math.log10(abs + 1) / Math.log10(max + 1)) * 100)
}

function priceClass(row) {
  const c = parseFloat(row.change || row.pct_chg || 0)
  if (c > 0) return 'text-up'
  if (c < 0) return 'text-down'
  return 'text-flat'
}

function rowClassName({ row }) {
  const c = parseFloat(row.change || row.pct_chg || 0)
  if (c > 0) return 'row-up'
  if (c < 0) return 'row-down'
  return ''
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    selectedRows.value = []
    batchGroup.value = ''
  }
}

function handleSelectionChange(rows) {
  selectedRows.value = rows
}

async function loadList() {
  loading.value = true
  try {
    const data = await getFavoriteList()
    tableData.value = Array.isArray(data) ? data : []
    // 加载本地分组映射
    loadGroupMapping()
    updateGroupCounts()
  } catch {
    tableData.value = []
  } finally {
    loading.value = false
  }
}

// 本地分组映射（stock_code -> group_name）
function loadGroupMapping() {
  try {
    const saved = localStorage.getItem('dsa_fav_group_map')
    if (saved) {
      const map = JSON.parse(saved)
      tableData.value.forEach(t => {
        const code = t.code || t.stock_code
        if (map[code]) t.group = map[code]
      })
    }
  } catch {}
}

function saveGroupMapping() {
  const map = {}
  tableData.value.forEach(t => {
    const code = t.code || t.stock_code
    if (t.group && code) map[code] = t.group
  })
  localStorage.setItem('dsa_fav_group_map', JSON.stringify(map))
}

async function handleAdd() {
  if (!addForm.value.code.trim()) {
    ElMessage.warning('请输入股票代码')
    return
  }
  addLoading.value = true
  try {
    await addFavorite(addForm.value.code.trim(), addForm.value.name.trim())
    // 本地保存分组
    if (addForm.value.group) {
      const map = JSON.parse(localStorage.getItem('dsa_fav_group_map') || '{}')
      map[addForm.value.code.trim()] = addForm.value.group
      localStorage.setItem('dsa_fav_group_map', JSON.stringify(map))
    }
    ElMessage.success('添加成功')
    showAddDialog.value = false
    addForm.value = { code: '', name: '', group: '' }
    await loadList()
  } catch {
    // 错误信息已由拦截器提示
  } finally {
    addLoading.value = false
  }
}

async function handleDelete(row) {
  const favId = row.id || row.fav_id || row.favId
  if (!favId) {
    ElMessage.warning('未找到记录 ID，无法删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除 ${row.name || row.code || '该自选股'}？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await deleteFavorite(favId)
    ElMessage.success('删除成功')
    await loadList()
  } catch (err) {
    if (err !== 'cancel') {
      // 错误已由拦截器提示
    }
  }
}

async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedRows.value.length} 只自选股？`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    for (const row of selectedRows.value) {
      const favId = row.id || row.fav_id || row.favId
      if (favId) await deleteFavorite(favId)
    }
    ElMessage.success(`已删除 ${selectedRows.value.length} 只`)
    batchMode.value = false
    await loadList()
  } catch (err) {
    if (err !== 'cancel') {}
  }
}

function batchMoveGroup() {
  if (!batchGroup.value || !selectedRows.value.length) return
  const map = JSON.parse(localStorage.getItem('dsa_fav_group_map') || '{}')
  selectedRows.value.forEach(row => {
    const code = row.code || row.stock_code
    if (code) map[code] = batchGroup.value
  })
  localStorage.setItem('dsa_fav_group_map', JSON.stringify(map))
  ElMessage.success(`已将 ${selectedRows.value.length} 只股票移至「${batchGroup.value}」`)
  batchMode.value = false
  loadList()
}

async function handleImport() {
  const codes = importCodeList.value
  if (!codes.length) {
    ElMessage.warning('未检测到有效的股票代码')
    return
  }
  importLoading.value = true
  let success = 0, fail = 0
  for (const code of codes) {
    try {
      await addFavorite(code, '')
      if (importGroup.value) {
        const map = JSON.parse(localStorage.getItem('dsa_fav_group_map') || '{}')
        map[code] = importGroup.value
        localStorage.setItem('dsa_fav_group_map', JSON.stringify(map))
      }
      success++
    } catch {
      fail++
    }
  }
  importLoading.value = false
  showImportDialog.value = false
  importText.value = ''
  ElMessage.success(`导入完成：成功 ${success} 只${fail > 0 ? `，失败 ${fail} 只` : ''}`)
  await loadList()
}

function handleRowClick(row) {
  const code = row.code || row.stock_code
  const name = row.name || row.stock_name || code
  if (code) appStore.setStock(code, name)
}

function goToMarket(row) {
  const code = row.code || row.stock_code
  const name = row.name || row.stock_name || code
  if (code) appStore.setStock(code, name)
  router.push('/market')
}

function goToAI(row) {
  const code = row.code || row.stock_code
  const name = row.name || row.stock_name || code
  if (code) appStore.setStock(code, name)
  router.push('/ai')
}

onMounted(() => {
  loadGroups()
  loadList()
})
</script>

<style scoped>
.favorite-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header-left-area {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-chips {
  display: flex;
  gap: 8px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  color: hsl(215 16% 60%);
}

.stat-chip.up { color: hsl(0 88% 64%); border-color: hsl(0 88% 64% / 0.3); }
.stat-chip.down { color: hsl(149 100% 44%); border-color: hsl(149 100% 44% / 0.3); }

.header-actions {
  display: flex;
  gap: 8px;
}

/* 分组标签栏 */
.group-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.group-tab {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  color: hsl(215 16% 60%);
  transition: all 0.2s;
}

.group-tab:hover {
  background: hsl(222 25% 16%);
  border-color: hsl(220 20% 28%);
}

.group-tab.active {
  background: hsl(190 100% 50% / 0.1);
  border-color: hsl(190 100% 50% / 0.4);
  color: hsl(190 100% 50%);
}

.group-tab.add-group {
  border-style: dashed;
  color: hsl(215 14% 45%);
}

.group-count {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  background: hsl(222 25% 16%);
  color: hsl(215 14% 45%);
}

.group-tab.active .group-count {
  background: hsl(190 100% 50% / 0.2);
  color: hsl(190 100% 50%);
}

/* 表格卡片 */
.table-card {
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 20%);
  border-radius: 8px;
  padding: 4px;
  position: relative;
}

.stock-code {
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
  font-size: 13px;
  color: hsl(190 100% 50%);
}

.stock-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stock-name {
  font-size: 13px;
  color: hsl(210 20% 92%);
}

.group-tag {
  font-size: 10px !important;
  height: 18px !important;
  line-height: 16px !important;
  padding: 0 6px !important;
}

.quote-text {
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
  font-size: 14px;
  font-weight: 600;
}

.quote-text.sm {
  font-size: 12px;
  font-weight: 400;
}

.text-up { color: hsl(0 88% 64%); }
.text-down { color: hsl(149 100% 44%); }
.text-flat { color: hsl(215 16% 60%); }
.text-dim { color: hsl(215 14% 45%); font-size: 12px; }
.text-muted { color: hsl(215 14% 45%); font-size: 12px; }

/* 资金流向迷你条 */
.capital-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: flex-end;
}

.capital-bar {
  width: 40px;
  height: 4px;
  border-radius: 2px;
  background: hsl(222 25% 16%);
  overflow: hidden;
}

.capital-fill {
  display: block;
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.bar-up .capital-fill { background: hsl(0 88% 64%); }
.bar-down .capital-fill { background: hsl(149 100% 44%); }

.capital-val {
  font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
  font-size: 12px;
}

/* 行高亮 */
:deep(.row-up td) {
  background: hsl(0 88% 64% / 0.03) !important;
}

:deep(.row-down td) {
  background: hsl(149 100% 44% / 0.03) !important;
}

/* 批量操作工具栏 */
.batch-toolbar {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: hsl(225 28% 11%);
  border-top: 1px solid hsl(220 20% 28%);
  border-radius: 0 0 8px 8px;
  z-index: 10;
}

.batch-info {
  font-size: 13px;
  color: hsl(38 100% 55%);
  font-weight: 600;
}

.slide-up-enter-active, .slide-up-leave-active {
  transition: all 0.3s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
