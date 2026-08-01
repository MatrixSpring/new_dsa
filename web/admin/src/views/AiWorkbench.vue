<template>
  <div class="ai-page dsa-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left-area">
        <h2 class="page-title">AI 分析工作台</h2>
        <div class="stat-chips">
          <span class="stat-chip">
            <el-icon><ChatLineRound /></el-icon>
            {{ chatHistory.length }} 轮对话
          </span>
          <span class="stat-chip" v-if="totalTokens > 0">
            <el-icon><Coin /></el-icon>
            {{ totalTokens }} tokens
          </span>
        </div>
      </div>
      <div class="header-actions">
        <el-button size="small" @click="exportChat" :disabled="!chatHistory.length">
          <el-icon><Download /></el-icon>
          导出对话
        </el-button>
        <el-button size="small" @click="clearHistory" :disabled="!chatHistory.length">
          <el-icon><Delete /></el-icon>
          清空
        </el-button>
      </div>
    </div>

    <div class="workbench-layout">
      <!-- 左侧: 配置面板 -->
      <div class="dsa-card config-panel">
        <!-- LLM 健康状态 -->
        <div class="health-section">
          <span class="section-label">LLM 状态</span>
          <div class="health-tags">
            <el-tag :type="healthStatus.doubao ? 'success' : 'danger'" size="small" effect="dark">
              豆包 {{ healthStatus.doubao ? '可用' : '不可用' }}
            </el-tag>
            <el-tag :type="healthStatus.deepseek ? 'success' : 'danger'" size="small" effect="dark">
              DeepSeek {{ healthStatus.deepseek ? '可用' : '不可用' }}
            </el-tag>
          </div>
        </div>

        <div class="divider"></div>

        <!-- 模型选择 -->
        <el-form label-position="top" size="small">
          <el-form-item label="模型选择">
            <el-select v-model="modelType" style="width: 100%">
              <el-option label="豆包 (Doubao)" value="doubao" />
              <el-option label="DeepSeek" value="deepseek" />
            </el-select>
          </el-form-item>

          <el-form-item label="温度 (Temperature)">
            <el-slider v-model="temperature" :min="0" :max="1" :step="0.1" show-input :show-input-controls="false" style="padding-right: 8px" />
          </el-form-item>

          <el-form-item label="系统提示词">
            <el-input
              v-model="systemPrompt"
              type="textarea"
              :rows="3"
              placeholder="设定 AI 角色与任务"
            />
          </el-form-item>
        </el-form>

        <div class="divider"></div>

        <!-- 快捷分析模板 -->
        <span class="section-label">快捷分析</span>
        <div class="quick-templates">
          <el-button
            v-for="tpl in templates"
            :key="tpl.key"
            size="small"
            :type="tpl.active ? 'primary' : 'default'"
            @click="applyTemplate(tpl)"
          >
            <el-icon><component :is="tpl.icon" /></el-icon>
            {{ tpl.label }}
          </el-button>
        </div>

        <!-- 当前股票 -->
        <div v-if="appStore.currentStockCode" class="current-stock-section">
          <el-alert type="info" :closable="false">
            当前股票: {{ appStore.currentStockName }} ({{ appStore.currentStockCode }})
          </el-alert>
        </div>

        <!-- Token 用量统计 -->
        <div v-if="tokenStats.length" class="token-stats-section">
          <span class="section-label">Token 用量统计</span>
          <div class="token-stats">
            <div v-for="stat in tokenStats" :key="stat.label" class="token-stat-item">
              <div class="token-stat-label">{{ stat.label }}</div>
              <div class="token-stat-value" :style="{ color: stat.color }">{{ stat.value }}</div>
              <div class="token-stat-bar">
                <div class="token-stat-bar-fill" :style="{ width: stat.percent + '%', background: stat.color }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧: 对话区 -->
      <div class="dsa-card chat-panel">
        <div class="chat-header">
          <span class="chart-title">AI 对话</span>
          <div class="chat-header-actions">
            <el-button size="small" text @click="copyLastReply" v-if="lastAiReply">
              <el-icon><CopyDocument /></el-icon>
              复制回复
            </el-button>
          </div>
        </div>

        <!-- 消息列表 -->
        <div ref="chatContainerRef" class="chat-container">
          <div v-if="!chatHistory.length" class="chat-empty">
            <el-icon size="48" color="hsl(215 14% 35%)"><ChatLineRound /></el-icon>
            <p style="margin-top: 12px; color: hsl(215 16% 60%)">输入问题开始 AI 分析对话</p>
            <div class="chat-suggestions">
              <div class="suggestion-chip" v-for="s in suggestions" :key="s" @click="userInput = s">
                {{ s }}
              </div>
            </div>
          </div>

          <div
            v-for="(msg, idx) in chatHistory"
            :key="idx"
            class="chat-message"
            :class="msg.role === 'user' ? 'msg-user' : 'msg-ai'"
          >
            <div class="msg-avatar">
              <el-icon size="20" :color="msg.role === 'user' ? '#00d4ff' : '#e6a23c'">
                <component :is="msg.role === 'user' ? 'User' : 'MagicStick'" />
              </el-icon>
            </div>
            <div class="msg-bubble">
              <div class="msg-content" v-html="formatContent(msg.content)"></div>
              <div v-if="msg.meta" class="msg-meta">
                <span class="meta-tag">{{ msg.meta }}</span>
              </div>
            </div>
          </div>

          <!-- 加载中 — 流式指示器 -->
          <div v-if="chatLoading" class="chat-message msg-ai">
            <div class="msg-avatar">
              <el-icon size="20" color="#e6a23c"><MagicStick /></el-icon>
            </div>
            <div class="msg-bubble">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
              <div class="streaming-label">AI 正在思考...</div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="chat-input-area">
          <el-input
            v-model="userInput"
            type="textarea"
            :rows="3"
            placeholder="输入分析问题，如：分析平安银行近期资金流向和舆情情况"
            resize="none"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <div class="input-actions">
            <span class="char-count" :class="{ warn: userInput.length > 500 }">
              {{ userInput.length }} / 1000
            </span>
            <el-button
              type="primary"
              :loading="chatLoading"
              :disabled="!userInput.trim()"
              @click="sendMessage"
              class="send-btn"
            >
              <el-icon><Promotion /></el-icon>
              发送
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { llmChat, llmHealth } from '@/api/llm'

const appStore = useAppStore()

const modelType = ref('doubao')
const temperature = ref(0.4)
const systemPrompt = ref('你是一个专业的A股股票分析师，擅长资金面分析、舆情解读和趋势研判。')
const userInput = ref('')
const chatHistory = ref([])
const chatLoading = ref(false)
const healthStatus = ref({ doubao: true, deepseek: true })
const chatContainerRef = ref(null)
const totalTokens = ref(0)

const suggestions = [
  '分析今日大盘走势',
  '解读央行最新政策',
  '比较银行板块龙头',
  '生成股票分析报告',
]

const templates = ref([
  { key: 'sentiment', label: '舆情总结', icon: 'ChatDotRound', active: false,
    prompt: `请总结股票${appStore.currentStockCode || '000001'}近期的舆情情感趋势，分析市场情绪偏向正面还是负面，并给出关键舆情事件。` },
  { key: 'capital', label: '资金解读', icon: 'Coin', active: false,
    prompt: `请解读股票${appStore.currentStockCode || '000001'}近期的资金流向数据，主力资金是净流入还是净流出？结合趋势判断后续走势。` },
  { key: 'market', label: '大盘复盘', icon: 'DataAnalysis', active: false,
    prompt: '请对今日A股大盘进行复盘，分析主要指数涨跌、板块轮动和资金偏好。' },
  { key: 'strategy', label: '策略建议', icon: 'Aim', active: false,
    prompt: `基于当前市场环境，请为股票${appStore.currentStockCode || '000001'}提供短期交易策略建议，包括支撑位、压力位和仓位管理。` },
  { key: 'report', label: '研报生成', icon: 'Document', active: false,
    prompt: `请为股票${appStore.currentStockCode || '000001'}生成一份简要研究报告，包含基本面分析、技术面分析、资金面分析和投资建议。` },
])

// Token 统计
const tokenStats = computed(() => {
  const aiMessages = chatHistory.value.filter(m => m.role === 'assistant')
  const totalTokensUsed = aiMessages.reduce((sum, m) => {
    const match = m.meta?.match(/(\d+)\s*tokens/i)
    return sum + (match ? parseInt(match[1]) : 0)
  }, 0)
  totalTokens.value = totalTokensUsed

  const avgTokens = aiMessages.length ? Math.round(totalTokensUsed / aiMessages.length) : 0
  const maxTokens = Math.max(...aiMessages.map(m => {
    const match = m.meta?.match(/(\d+)\s*tokens/i)
    return match ? parseInt(match[1]) : 0
  }), 0)
  const avgContentLen = aiMessages.length
    ? Math.round(aiMessages.reduce((s, m) => s + m.content.length, 0) / aiMessages.length)
    : 0

  const maxBar = Math.max(totalTokensUsed, maxTokens, avgTokens, 1)
  return [
    { label: '总 Token', value: totalTokensUsed, percent: (totalTokensUsed / maxBar) * 100, color: '#00d4ff' },
    { label: '平均/次', value: avgTokens, percent: (avgTokens / maxBar) * 100, color: '#e6a23c' },
    { label: '最大单次', value: maxTokens, percent: (maxTokens / maxBar) * 100, color: '#e6382e' },
    { label: '平均字数', value: avgContentLen, percent: (avgContentLen / maxBar) * 100, color: '#a855f7' },
  ]
})

const lastAiReply = computed(() => {
  for (let i = chatHistory.value.length - 1; i >= 0; i--) {
    if (chatHistory.value[i].role === 'assistant') return chatHistory.value[i].content
  }
  return ''
})

function applyTemplate(tpl) {
  templates.value.forEach(t => t.active = false)
  tpl.active = true
  const code = appStore.currentStockCode || '000001'
  userInput.value = tpl.prompt.replace(/000001/g, code)
}

function formatContent(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\n/g, '<br>')
}

async function sendMessage() {
  const prompt = userInput.value.trim()
  if (!prompt || chatLoading.value) return

  chatHistory.value.push({ role: 'user', content: prompt })
  userInput.value = ''
  chatLoading.value = true

  await nextTick()
  scrollToBottom()

  try {
    const history = chatHistory.value
      .filter(m => m.role !== 'system')
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }))

    const data = await llmChat({
      prompt,
      system_prompt: systemPrompt.value,
      model_type: modelType.value,
      temperature: temperature.value,
      history: history.length > 1 ? history.slice(0, -1) : null,
    })

    chatHistory.value.push({
      role: 'assistant',
      content: data?.content || '(空回复)',
      meta: `${data?.model_name || modelType.value} · ${data?.tokens || 0} tokens`,
    })
  } catch {
    chatHistory.value.push({
      role: 'assistant',
      content: 'AI 分析失败，请检查 LLM 服务状态后重试。',
    })
  } finally {
    chatLoading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
  }
}

function clearHistory() {
  chatHistory.value = []
  templates.value.forEach(t => t.active = false)
}

function exportChat() {
  if (!chatHistory.value.length) return
  let md = `# AI 分析对话记录\n\n`
  md += `> 导出时间: ${new Date().toLocaleString('zh-CN')}\n`
  md += `> 模型: ${modelType.value} | 温度: ${temperature.value}\n`
  md += `> 总 Token: ${totalTokens.value}\n\n---\n\n`

  chatHistory.value.forEach((msg, idx) => {
    const role = msg.role === 'user' ? '👤 用户' : '🤖 AI'
    md += `## ${role}\n\n${msg.content}\n`
    if (msg.meta) md += `\n*${msg.meta}*\n`
    md += '\n---\n\n'
  })

  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `ai_chat_${Date.now()}.md`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('对话已导出')
}

function copyLastReply() {
  if (!lastAiReply.value) return
  navigator.clipboard.writeText(lastAiReply.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败')
  })
}

async function checkHealth() {
  try {
    const data = await llmHealth()
    healthStatus.value = {
      doubao: data?.doubao ?? true,
      deepseek: data?.deepseek ?? true,
    }
  } catch {
    healthStatus.value = { doubao: false, deepseek: false }
  }
}

onMounted(() => {
  checkHealth()
})
</script>

<style scoped>
.ai-page {
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

.header-actions {
  display: flex;
  gap: 8px;
}

.workbench-layout {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.config-panel {
  width: 300px;
  flex-shrink: 0;
  padding: 14px;
}

.chat-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid hsl(220 20% 20%);
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(210 20% 92%);
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: hsl(215 16% 60%);
  display: block;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.divider {
  height: 1px;
  background: hsl(220 20% 20%);
  margin: 12px 0;
}

.health-section {
  margin-bottom: 4px;
}

.health-tags {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.quick-templates {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.current-stock-section {
  margin-top: 12px;
}

.token-stats-section {
  margin-top: 16px;
}

.token-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.token-stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.token-stat-label {
  font-size: 11px;
  color: hsl(215 16% 60%);
  width: 60px;
  flex-shrink: 0;
}

.token-stat-value {
  font-size: 13px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  width: 50px;
  text-align: right;
}

.token-stat-bar {
  flex: 1;
  height: 4px;
  background: hsl(220 20% 18%);
  border-radius: 2px;
  overflow: hidden;
}

.token-stat-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 400px;
  max-height: 520px;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
}

.chat-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 16px;
  max-width: 500px;
}

.suggestion-chip {
  padding: 6px 14px;
  border-radius: 16px;
  background: hsl(224 25% 13%);
  border: 1px solid hsl(220 20% 28%);
  color: hsl(210 20% 92%);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.suggestion-chip:hover {
  border-color: hsl(190 100% 50% / 0.5);
  color: hsl(190 100% 50%);
  background: hsl(190 100% 50% / 0.08);
}

.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.msg-user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(224 25% 16%);
  border-radius: 50%;
}

.msg-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
}

.msg-user .msg-bubble {
  background: hsl(190 100% 50% / 0.15);
  border: 1px solid hsl(190 100% 50% / 0.3);
  color: hsl(210 20% 92%);
}

.msg-ai .msg-bubble {
  background: hsl(224 25% 16%);
  border: 1px solid hsl(220 20% 20%);
  color: hsl(210 20% 92%);
}

.msg-content {
  word-break: break-word;
}

.msg-content :deep(pre) {
  background: hsl(228 35% 7%);
  color: #d4d4d4;
  padding: 8px 12px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 6px 0;
  font-size: 13px;
  border: 1px solid hsl(220 20% 20%);
}

.msg-content :deep(code) {
  background: hsl(220 20% 16%);
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 13px;
  color: hsl(190 100% 60%);
}

.msg-content :deep(h4), .msg-content :deep(h3), .msg-content :deep(h2) {
  margin: 8px 0 4px;
  color: hsl(190 100% 60%);
}

.msg-meta {
  margin-top: 6px;
}

.meta-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: hsl(220 20% 16%);
  color: hsl(215 16% 60%);
  font-family: 'JetBrains Mono', monospace;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: hsl(190 100% 50%);
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.streaming-label {
  font-size: 11px;
  color: hsl(190 100% 50%);
  margin-top: 4px;
}

.chat-input-area {
  padding: 12px 14px;
  border-top: 1px solid hsl(220 20% 20%);
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.char-count {
  font-size: 11px;
  color: hsl(215 14% 45%);
  font-family: 'JetBrains Mono', monospace;
}
.char-count.warn {
  color: hsl(38 100% 55%);
}

.send-btn {
  height: 36px;
}
</style>
