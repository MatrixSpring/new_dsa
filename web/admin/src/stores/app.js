import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  // 全局选中的股票代码 — 跨页面共享
  const currentStockCode = ref('')
  const currentStockName = ref('')

  function setStock(code, name = '') {
    currentStockCode.value = code
    currentStockName.value = name || code
  }

  return {
    currentStockCode,
    currentStockName,
    setStock,
  }
})
