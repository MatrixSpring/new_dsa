<template>
  <div class="stock-search">
    <el-input
      v-model="innerCode"
      placeholder="输入股票代码，如 000001"
      clearable
      style="width: 200px"
      @keyup.enter="handleSearch"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>
    <el-button type="primary" @click="handleSearch">
      <el-icon><Search /></el-icon>
      搜索
    </el-button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['search', 'update:modelValue'])

const appStore = useAppStore()
const innerCode = ref(props.modelValue || appStore.currentStockCode || '')

watch(() => props.modelValue, (v) => { innerCode.value = v })

function handleSearch() {
  const code = innerCode.value.trim()
  if (!code) return
  appStore.setStock(code)
  emit('update:modelValue', code)
  emit('search', code)
}
</script>

<style scoped>
.stock-search {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
