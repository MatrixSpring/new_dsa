<template>
  <el-container class="admin-layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <div class="logo-icon-wrap">
          <el-icon size="20" color="#00d4ff"><DataLine /></el-icon>
        </div>
        <span v-show="!isCollapse" class="logo-text">量化投研</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        router
        background-color="transparent"
        text-color="hsl(215 16% 60%)"
        active-text-color="hsl(190 100% 50%)"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧主区域 -->
    <el-container>
      <!-- 顶部头部 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon
            class="collapse-btn"
            size="20"
            @click="isCollapse = !isCollapse"
          >
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag v-if="appStore.currentStockCode" type="primary" effect="plain" size="small">
            {{ appStore.currentStockName }}({{ appStore.currentStockCode }})
          </el-tag>
          <el-tooltip content="系统状态" placement="bottom">
            <el-badge :value="'在线'" type="success" class="status-badge">
              <el-icon size="18" color="hsl(190 100% 50%)"><Monitor /></el-icon>
            </el-badge>
          </el-tooltip>
        </div>
      </el-header>

      <!-- 内容区域 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()
const isCollapse = ref(false)

const menuItems = [
  { path: '/favorite', title: '自选股管理', icon: 'Star' },
  { path: '/market', title: '行情资金看板', icon: 'TrendCharts' },
  { path: '/news', title: '资讯舆情', icon: 'ChatDotRound' },
  { path: '/chain', title: '产业链全景', icon: 'Share' },
  { path: '/macro', title: '资金全球动态', icon: 'Money' },
  { path: '/ai', title: 'AI分析工作台', icon: 'MagicStick' },
  { path: '/backtest', title: '策略回测', icon: 'DataAnalysis' },
]

const activeMenu = computed(() => route.path)
const currentTitle = computed(() => route.meta.title || '')
</script>

<style scoped>
.admin-layout {
  height: 100vh;
}

.sidebar {
  background: hsl(225 28% 11%);
  border-right: 1px solid hsl(220 20% 20%);
  transition: width 0.3s ease;
  overflow: hidden;
}

.logo-area {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-bottom: 1px solid hsl(220 20% 20%);
}

.logo-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, hsl(190 100% 50%), hsl(190 80% 40%));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: hsl(210 20% 92%);
  white-space: nowrap;
  letter-spacing: 0.02em;
}

.header {
  background: hsl(225 28% 11%);
  border-bottom: 1px solid hsl(220 20% 20%);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  z-index: 10;
  height: 52px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  cursor: pointer;
  color: hsl(215 16% 60%);
  transition: color 0.2s;
}
.collapse-btn:hover {
  color: hsl(190 100% 50%);
}

:deep(.el-breadcrumb__inner) {
  color: hsl(215 16% 60%) !important;
}

:deep(.el-breadcrumb__inner.is-link:hover) {
  color: hsl(190 100% 50%) !important;
}

:deep(.el-breadcrumb__separator) {
  color: hsl(215 14% 45%) !important;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-badge {
  cursor: pointer;
}

.main-content {
  background: hsl(228 35% 7%);
  overflow-y: auto;
  padding: 20px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

:deep(.el-menu) {
  border-right: none;
}

:deep(.el-menu-item) {
  border-radius: 6px;
  margin: 2px 8px;
  transition: all 0.2s;
}

:deep(.el-menu-item:hover) {
  background: hsl(222 25% 16%);
}

:deep(.el-menu-item.is-active) {
  background: hsl(190 100% 50% / 0.1);
}
</style>
