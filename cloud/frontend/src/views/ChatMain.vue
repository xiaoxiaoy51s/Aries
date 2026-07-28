<template>
  <main class="chat-main">
    <!-- 空状态：欢迎页 + 输入框 + 模板画廊 -->
    <div v-if="!hasActiveChat" class="chat-empty">
      <div class="chat-empty-inner">
        <div class="chat-welcome-brand">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          <h1 class="chat-welcome-title">Work with Aries Cloud</h1>
        </div>
        <p class="chat-welcome-sub">
          {{ t('chat.welcomeSubtitle') }}
        </p>

        <!-- 输入框 -->
        <div class="chat-composer">
          <textarea
            ref="inputRef"
            v-model="inputMessage"
            class="chat-composer-input"
            :placeholder="t('chat.placeholder')"
            rows="3"
            @keydown.enter.exact.prevent="handleSend"
            @keydown.shift.enter="inputMessage += '\n'"
          />
          <div class="chat-composer-actions">
            <div class="chat-composer-left">
              <button type="button" class="composer-icon-btn" title="上传图片">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="9" cy="9" r="2"/>
                  <path d="m21 15-3.5-3.5a2 2 0 0 0-2.8 0L6 21"/>
                </svg>
              </button>
              <button type="button" class="composer-icon-btn" title="语音输入">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="2" width="6" height="12" rx="3"/>
                  <path d="M5 10v2a7 7 0 0 0 14 0v-2"/>
                  <line x1="12" y1="19" x2="12" y2="22"/>
                </svg>
              </button>
              <button type="button" class="composer-icon-btn" title="联网搜索">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M2 12h20"/>
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
              </button>
            </div>
            <div class="chat-composer-right">
              <!-- 上下文占用量指示器（模型按钮旁） -->
              <div v-if="contextInfo" class="context-usage" :title="contextTooltip">
                <span class="context-usage-label">ctx {{ contextInfo.usage_percent }}%</span>
                <span class="context-usage-bar">
                  <span class="context-usage-fill" :style="{ width: contextInfo.usage_percent + '%' }" />
                </span>
              </div>
              <div class="composer-model-dropdown" ref="welcomeDropdownRef">
                <button
                  type="button"
                  class="composer-mode-btn"
                  :class="{ 'is-active': welcomeModelOpen }"
                  :disabled="switchingModel"
                  @click="toggleModelMenu('welcome')"
                >
                    <span class="composer-mode-label">{{ switchingModel ? t('chat.switchingModel') : (hasModel ? activeModel.name : t('chat.noModel')) }}</span>
                  <svg class="composer-mode-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                <div v-if="welcomeModelOpen" class="composer-model-menu" role="listbox">
                  <div v-if="models.length === 0" class="composer-model-menu-empty">
                    <span>{{ t('chat.modelMenuEmpty') }}</span>
                    <button type="button" class="composer-model-menu-add" @click="openSettings">{{ t('chat.modelMenuAdd') }}</button>
                  </div>
                  <template v-else>
                    <button
                      v-for="m in models"
                      :key="m.id"
                      type="button"
                      class="composer-model-option"
                      :class="{ active: m.id === activeModel?.id }"
                      role="option"
                      :aria-selected="m.id === activeModel?.id"
                      :disabled="switchingModel"
                      @click="selectModel(m)"
                    >
                      <span class="composer-model-check" :class="{ checked: m.id === activeModel?.id }" />
                      <span class="composer-model-name">{{ m.name }}</span>
                      <span class="composer-model-id">{{ m.model }}</span>
                    </button>
                    <div class="composer-model-menu-divider" />
                    <button type="button" class="composer-model-menu-add" @click="openSettings">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 5v14M5 12h14"/>
                      </svg>
                      {{ t('chat.modelMenuAdd') }}
                    </button>
                  </template>
                </div>
              </div>
              <button
                type="button"
                class="composer-send-btn"
                :disabled="!inputMessage.trim() || sending"
                @click="handleSend"
              >
                <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5"/>
                  <polyline points="5 12 12 5 19 12"/>
                </svg>
                <span v-else class="composer-send-loading" />
              </button>
            </div>
          </div>
        </div>

        <!-- 模板画廊 -->
        <div class="template-gallery">
          <div class="template-gallery-header">
            <span class="template-gallery-title">精选模板</span>
            <button type="button" class="template-gallery-more">查看更多 ›</button>
          </div>
          <div class="template-cards">
            <button
              v-for="tpl in templates"
              :key="tpl.id"
              type="button"
              class="template-card"
              @click="useTemplate(tpl)"
            >
              <div class="template-card-cover">
                <img :src="tpl.cover" :alt="tpl.title" />
              </div>
              <div class="template-card-meta">
                <div class="template-card-title">{{ tpl.title }}</div>
                <div class="template-card-desc">{{ tpl.desc }}</div>
              </div>
            </button>
          </div>
        </div>

        <p class="chat-composer-tip">
            {{ t('chat.tip') }}
          </p>
      </div>
    </div>

    <!-- 对话中状态 -->
    <div v-else class="chat-active">
      <header class="chat-header">
        <div class="chat-header-start">
          <h2 class="chat-header-title" :title="currentSession?.title">{{ currentSession?.title }}</h2>
        </div>
        <div class="chat-header-actions">
          <button type="button" class="chat-header-icon-btn" title="新建对话" @click="$emit('create-new-chat')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </button>
          <button type="button" class="chat-header-icon-btn" title="更多">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="5" cy="12" r="1.5"/>
              <circle cx="12" cy="12" r="1.5"/>
              <circle cx="19" cy="12" r="1.5"/>
            </svg>
          </button>
        </div>
      </header>

      <div ref="messagesContainer" class="chat-messages">
        <div
          v-for="(msg, index) in currentMessages"
          :key="msg.id || index"
          class="msg-row"
          :class="msg.role"
        >
          <div class="msg-row-inner">
            <div v-if="msg.role === 'user'" class="msg-user-wrap">
              <div class="msg-content msg-content-user">{{ msg.content }}</div>
              <button
                type="button"
                class="msg-copy-btn"
                :title="copiedMsgId === msg.id ? t('chat.copied') : t('chat.copy')"
                @click="copyMessage(msg)"
              >
                <svg v-if="copiedMsgId === msg.id" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2"/>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
              </button>
            </div>
            <div v-else class="msg-assistant-wrap">
              <div class="msg-content msg-content-assistant">
                <AssistantMessage
                  :content="msg.content"
                  :reasoning="msg.reasoning || ''"
                  :is-loading="msg.isLoading"
                  :model="msg.model || ''"
                  :token-usage="msg.tokenUsage || null"
                  :session-id="currentSession?.id || ''"
                  :message-id="msg.id || ''"
                  :duration-ms="msg.durationMs || 0"
                  :tool-calls="msg.toolCalls || []"
                  :blocks="msg.blocks || []"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-composer-area">
        <div class="chat-composer">
          <textarea
            ref="inputRef"
            v-model="inputMessage"
            class="chat-composer-input"
            :placeholder="t('chat.sendPlaceholder')"
            rows="2"
            @keydown.enter.exact.prevent="handleSend"
            @keydown.shift.enter="inputMessage += '\n'"
          />
          <div class="chat-composer-actions">
            <div class="chat-composer-left">
              <button type="button" class="composer-icon-btn" title="上传图片">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="9" cy="9" r="2"/>
                  <path d="m21 15-3.5-3.5a2 2 0 0 0-2.8 0L6 21"/>
                </svg>
              </button>
            </div>
            <div class="chat-composer-right">
              <!-- 上下文占用量指示器（模型按钮旁） -->
              <div v-if="contextInfo" class="context-usage" :title="contextTooltip">
                <span class="context-usage-label">ctx {{ contextInfo.usage_percent }}%</span>
                <span class="context-usage-bar">
                  <span class="context-usage-fill" :style="{ width: contextInfo.usage_percent + '%' }" />
                </span>
              </div>
              <div class="composer-model-dropdown" ref="activeDropdownRef">
                <button
                  type="button"
                  class="composer-mode-btn"
                  :class="{ 'is-active': activeModelOpen }"
                  :disabled="switchingModel"
                  @click="toggleModelMenu('active')"
                >
                    <span class="composer-mode-label">{{ switchingModel ? t('chat.switchingModel') : (hasModel ? activeModel.name : t('chat.noModel')) }}</span>
                  <svg class="composer-mode-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
                <div v-if="activeModelOpen" class="composer-model-menu" role="listbox">
                  <div v-if="models.length === 0" class="composer-model-menu-empty">
                    <span>{{ t('chat.modelMenuEmpty') }}</span>
                    <button type="button" class="composer-model-menu-add" @click="openSettings">{{ t('chat.modelMenuAdd') }}</button>
                  </div>
                  <template v-else>
                    <button
                      v-for="m in models"
                      :key="m.id"
                      type="button"
                      class="composer-model-option"
                      :class="{ active: m.id === activeModel?.id }"
                      role="option"
                      :aria-selected="m.id === activeModel?.id"
                      :disabled="switchingModel"
                      @click="selectModel(m)"
                    >
                      <span class="composer-model-check" :class="{ checked: m.id === activeModel?.id }" />
                      <span class="composer-model-name">{{ m.name }}</span>
                      <span class="composer-model-id">{{ m.model }}</span>
                    </button>
                    <div class="composer-model-menu-divider" />
                    <button type="button" class="composer-model-menu-add" @click="openSettings">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 5v14M5 12h14"/>
                      </svg>
                      {{ t('chat.modelMenuAdd') }}
                    </button>
                  </template>
                </div>
              </div>
              <button
                type="button"
                class="composer-send-btn"
                :disabled="!inputMessage.trim() || sending"
                @click="handleSend"
              >
                <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="19" x2="12" y2="5"/>
                  <polyline points="5 12 12 5 19 12"/>
                </svg>
                <span v-else class="composer-send-loading" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '../i18n'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import AssistantMessage from '../components/AssistantMessage.vue'
import tplResume from '../assets/template-resume.jpg'
import tplEvent from '../assets/template-event.jpg'
import tplBrand from '../assets/template-brand.jpg'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const props = defineProps({
  hasActiveChat: Boolean,
  currentSession: Object,
  currentMessages: { type: Array, default: () => [] },
  sending: Boolean,
  user: Object,
})

const emit = defineEmits(['send-message', 'create-new-chat'])

const inputRef = ref(null)
const messagesContainer = ref(null)
const inputMessage = ref('')
const models = ref([])
const switchingModel = ref(false)
const copiedMsgId = ref(null)
let copiedMsgTimer = null

// 模型下拉：两个输入区分别维护开关
const welcomeModelOpen = ref(false)
const activeModelOpen = ref(false)
const welcomeDropdownRef = ref(null)
const activeDropdownRef = ref(null)

const activeModel = computed(() => models.value.find(m => m.isActive) || models.value[0] || null)
const hasModel = computed(() => !!activeModel.value)

// 从最新助手消息中获取上下文占用量；若后端尚未返回，则按当前输入 + 模型窗口做兜底展示
const contextInfo = computed(() => {
  const msgs = props.currentMessages || []
  for (let i = msgs.length - 1; i >= 0; i--) {
    const info = msgs[i]?.contextInfo
    if (info) return info
  }
  const total = activeModel.value?.context_window
  if (!total) return null
  const text = (inputMessage.value || '') + msgs.map(m => m.content || '').join('')
  const estimated = Math.ceil(text.length / 4)
  return {
    estimated_tokens: estimated,
    context_window: total,
    usage_percent: Math.min(100, Math.round((estimated / total) * 1000) / 10),
    breakdown: {},
  }
})

const contextTooltip = computed(() => {
  if (!contextInfo.value) return ''
  const info = contextInfo.value
  const est = info.estimated_tokens || 0
  const total = info.context_window || 0
  const pct = info.usage_percent || 0
  const breakdown = info.breakdown || {}
  const parts = [`${est.toLocaleString()} / ${total.toLocaleString()} tokens (${pct}%)`]
  if (breakdown.system) parts.push(`system: ${breakdown.system}`)
  if (breakdown.user) parts.push(`user: ${breakdown.user}`)
  if (breakdown.assistant) parts.push(`assistant: ${breakdown.assistant}`)
  return parts.join(' | ')
})

function toggleModelMenu(which) {
  if (which === 'welcome') {
    activeModelOpen.value = false
    welcomeModelOpen.value = !welcomeModelOpen.value
  } else {
    welcomeModelOpen.value = false
    activeModelOpen.value = !activeModelOpen.value
  }
}

function closeAllModelMenus() {
  welcomeModelOpen.value = false
  activeModelOpen.value = false
}

function openSettings() {
  closeAllModelMenus()
  settingsStore.openSettings()
}

// 切换激活模型，沿用 SettingsModal 的 PUT /api/models/{id} { isActive: true }
async function selectModel(m) {
  if (switchingModel.value || m.id === activeModel.value?.id) {
    closeAllModelMenus()
    return
  }
  switchingModel.value = true
  try {
    await api.put(`/api/models/${m.id}`, { isActive: true })
    // 本地立即更新激活态，避免等待列表刷新的视觉延迟
    models.value.forEach(item => { item.isActive = item.id === m.id })
    ElMessage.success(`${t('settings.active')}: ${m.name}`)
    closeAllModelMenus()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Switch model failed')
  } finally {
    switchingModel.value = false
  }
}

function handleDocClick(e) {
  if (welcomeDropdownRef.value && !welcomeDropdownRef.value.contains(e.target)) {
    welcomeModelOpen.value = false
  }
  if (activeDropdownRef.value && !activeDropdownRef.value.contains(e.target)) {
    activeModelOpen.value = false
  }
}

function handleEsc(e) {
  if (e.key === 'Escape') closeAllModelMenus()
}

onMounted(async () => {
  document.addEventListener('mousedown', handleDocClick)
  document.addEventListener('keydown', handleEsc)
  try {
    const res = await api.get('/api/models')
    models.value = res.data
  } catch (err) {
    console.error('Failed to load models', err)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocClick)
  document.removeEventListener('keydown', handleEsc)
})


const templates = [
  { id: 'tpl-1', title: '求职面试', desc: '结构化简历模板', cover: tplResume },
  { id: 'tpl-2', title: '活动策划', desc: '活动方案与排期', cover: tplEvent },
  { id: 'tpl-3', title: '品牌方案', desc: '品牌视觉规范', cover: tplBrand },
]

function useTemplate(tpl) {
  inputMessage.value = `使用「${tpl.title}」模板，${tpl.desc}。请帮我生成一份。`
  nextTick(() => inputRef.value?.focus())
}

function handleSend() {
  const content = inputMessage.value.trim()
  if (!content || props.sending) return
  emit('send-message', content)
  inputMessage.value = ''
}

function copyMessage(msg) {
  if (!msg.content) return
  navigator.clipboard.writeText(msg.content).then(() => {
    copiedMsgId.value = msg.id
    if (copiedMsgTimer) clearTimeout(copiedMsgTimer)
    copiedMsgTimer = setTimeout(() => { copiedMsgId.value = null }, 1500)
  }).catch(() => {})
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 消息变化时自动滚动到底部
watch(() => props.currentMessages, scrollToBottom, { deep: true })

// 新建对话时清空输入框并聚焦
watch(() => props.hasActiveChat, (val) => {
  if (!val) {
    inputMessage.value = ''
    nextTick(() => inputRef.value?.focus())
  }
})
</script>
