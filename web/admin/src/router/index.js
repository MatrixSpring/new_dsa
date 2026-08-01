import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/favorite',
    children: [
      {
        path: 'favorite',
        name: 'Favorite',
        component: () => import('@/views/FavoriteManage.vue'),
        meta: { title: '自选股管理', icon: 'Star' },
      },
      {
        path: 'market',
        name: 'Market',
        component: () => import('@/views/MarketDashboard.vue'),
        meta: { title: '行情资金看板', icon: 'TrendCharts' },
      },
      {
        path: 'news',
        name: 'News',
        component: () => import('@/views/NewsPanel.vue'),
        meta: { title: '资讯舆情', icon: 'ChatDotRound' },
      },
      {
        path: 'ai',
        name: 'AIWorkbench',
        component: () => import('@/views/AIWorkbench.vue'),
        meta: { title: 'AI分析工作台', icon: 'MagicStick' },
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/BacktestPanel.vue'),
        meta: { title: '策略回测', icon: 'DataAnalysis' },
      },
      {
        path: 'chain',
        name: 'IndustryChain',
        component: () => import('@/views/IndustryChainView.vue'),
        meta: { title: '产业链全景', icon: 'Share' },
      },
      {
        path: 'macro',
        name: 'MacroCapital',
        component: () => import('@/views/MacroCapitalView.vue'),
        meta: { title: '资金全球动态', icon: 'Money' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - 量化投研` : '量化投研管理后台'
  next()
})

export default router
