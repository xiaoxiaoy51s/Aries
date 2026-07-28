<template>
  <div class="assistant-message">
    <!-- 运行元数据栏：模型、运行时间、token 使用 -->
    <div v-if="hasMetaInfo" class="meta-bar">
      <span v-if="model" class="meta-item meta-model">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 10v6M4.22 4.22l4.24 4.24m7.08 7.08l4.24 4.24M1 12h6m10 0h6M4.22 19.78l4.24-4.24m7.08-7.08l4.24-4.24"/></svg>
        {{ model }}
      </span>
      <span v-if="formattedDuration" class="meta-item">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        {{ formattedDuration }}
      </span>
      <span v-if="tokenInput" class="meta-item" title="输入 tokens">
        ↑ {{ tokenInput }}
      </span>
      <span v-if="tokenOutput" class="meta-item" title="输出 tokens">
        ↓ {{ tokenOutput }}
      </span>
      <span v-if="tokenTotal" class="meta-item" title="总 tokens">
        Σ {{ tokenTotal }}
      </span>
    </div>

    <!-- 按事件顺序渲染 blocks -->
    <template v-for="(block, index) in computedBlocks" :key="index">
      <!-- 思考过程块 -->
      <div v-if="block.type === 'reasoning'" class="work-block">
        <div class="work-header" @click="toggleReasoning(index)">
          <svg class="work-icon" :class="{ expanded: isReasoningOpen(index) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="m9 18 6-6-6-6"/>
          </svg>
          <span class="work-title">{{ isLoading && !hasContentAfter(index) ? '思考中…' : '思考过程' }}</span>
        </div>
        <div v-show="isReasoningOpen(index)" class="work-content">
          <div class="reasoning-text">{{ block.text }}</div>
        </div>
      </div>

      <!-- 工具调用块 -->
      <div v-else-if="block.type === 'tool'" class="tool-block">
        <div v-if="!isToolExpanded(block.toolCallId)" class="tool-header" @click="toggleTool(block.toolCallId)">
          <svg class="tool-icon" :class="{ expanded: isToolExpanded(block.toolCallId) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="m9 18 6-6-6-6"/>
          </svg>
          <span class="tool-name">{{ block.toolName }}</span>
          <span v-if="block.args && block.args.query" class="tool-args-preview">{{ block.args.query }}</span>
          <span v-else-if="block.args && Object.keys(block.args).length > 0" class="tool-args-preview">{{ JSON.stringify(block.args).slice(0, 60) }}</span>
          <span v-if="block.status === 'running'" class="tool-running-badge">运行中…</span>
        </div>
        <div v-else class="tool-body">
          <div class="tool-body-header" @click="toggleTool(block.toolCallId)">
            <svg class="tool-icon expanded" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="m9 18 6-6-6-6"/>
            </svg>
            <span class="tool-name">{{ block.toolName }}</span>
            <span v-if="block.args && block.args.query" class="tool-args-preview">{{ block.args.query }}</span>
            <span v-else-if="block.args && Object.keys(block.args).length > 0" class="tool-args-preview">{{ JSON.stringify(block.args).slice(0, 60) }}</span>
          </div>
          <div v-if="block.args && Object.keys(block.args).length > 0" class="tool-section">
            <span class="section-label">参数</span>
            <pre class="code-text">{{ JSON.stringify(block.args, null, 2) }}</pre>
          </div>
          <div v-if="block.result" class="tool-section">
            <span class="section-label">结果</span>
            <pre class="code-text">{{ block.result }}</pre>
          </div>
          <div v-else-if="block.status === 'running'" class="tool-section">
            <span class="running-text">运行中…</span>
          </div>
        </div>
      </div>

      <!-- 文本内容块 -->
      <div v-else-if="block.type === 'text'" class="message-content">
        <MarkdownRenderer
          :content="block.text"
          :is-streaming="isLoading && !hasContentAfter(index)"
          :show-actions="false"
        />
      </div>
    </template>

    <!-- 加载动画 -->
    <div v-if="isLoading && computedBlocks.length === 0" class="loading-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <!-- 复制按钮 -->
    <div v-if="!isLoading && content" class="message-actions">
      <button class="action-btn" @click="copyContent" :title="copied ? t('chat.copied') : t('chat.copy')">
        <svg v-if="copied" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useI18n } from '../i18n'
import {
  streamDurationTick,
  startStreamDuration,
  stopStreamDuration,
  bindStreamDuration,
  getStreamDurationMs,
} from '../utils/streamDurationStore'

const { t } = useI18n()

const props = defineProps({
  content: { type: String, default: '' },
  reasoning: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  model: { type: String, default: '' },
  tokenUsage: { type: Object, default: null },
  sessionId: { type: String, default: '' },
  messageId: { type: [Number, String], default: '' },
  durationMs: { type: Number, default: 0 },
  toolCalls: { type: Array, default: () => [] },
  blocks: { type: Array, default: () => [] },
})

// 若父级未提供 blocks（如历史消息），从 content/reasoning/toolCalls 生成后备 blocks
const computedBlocks = computed(() => {
  if (props.blocks && props.blocks.length > 0) return props.blocks
  const fallback = []
  if (props.reasoning) {
    fallback.push({ type: 'reasoning', text: props.reasoning })
  }
  if (props.toolCalls && props.toolCalls.length > 0) {
    for (const tc of props.toolCalls) {
      fallback.push({
        type: 'tool',
        toolCallId: tc.tool_call_id || tc.id || `tc-${fallback.length}`,
        toolName: tc.tool_name || tc.name || 'tool',
        args: tc.args || (tc.function ? JSON.parse(tc.function.arguments || '{}') : {}),
        status: tc.status || (tc.result ? 'completed' : 'running'),
        result: tc.result || '',
      })
    }
  }
  if (props.content) {
    fallback.push({ type: 'text', text: props.content })
  }
  return fallback
})

const expandedReasoning = ref({})
const expandedTools = ref({})
const copied = ref(false)
let copyTimer = null

function toggleReasoning(index) {
  expandedReasoning.value = { ...expandedReasoning.value, [index]: !expandedReasoning.value[index] }
}
function isReasoningOpen(index) {
  if (index in expandedReasoning.value) return expandedReasoning.value[index]
  return props.isLoading
}

function toggleTool(id) {
  expandedTools.value = { ...expandedTools.value, [id]: !expandedTools.value[id] }
}
function isToolExpanded(id) {
  return !!expandedTools.value[id]
}

function hasContentAfter(index) {
  return computedBlocks.value.slice(index + 1).some(b => b.type === 'text')
}

// ---------- 实时计时 ----------
function syncStreamDurationState() {
  const sid = props.sessionId
  if (!sid || !props.isLoading) return
  if (props.messageId) {
    bindStreamDuration(sid, props.messageId)
    startStreamDuration(sid, props.messageId)
  } else {
    startStreamDuration(sid, '__pending__')
  }
}

watch(
  () => [props.isLoading, props.sessionId, props.messageId],
  ([loading]) => {
    const sid = props.sessionId
    if (!sid) return
    if (loading) {
      syncStreamDurationState()
    } else {
      stopStreamDuration(sid, props.messageId || undefined)
    }
  },
  { immediate: true },
)

const apiUsage = computed(() => props.tokenUsage?.api_usage || {})
const tokenInput = computed(() => apiUsage.value?.prompt_tokens || '')
const tokenOutput = computed(() => apiUsage.value?.completion_tokens || '')
const tokenTotal = computed(() => apiUsage.value?.total_tokens || '')

// 实时运行时长
const formattedDuration = computed(() => {
  streamDurationTick.value

  if (props.isLoading) {
    const sid = props.sessionId
    if (sid) {
      if (props.messageId) {
        const ms = getStreamDurationMs(sid, props.messageId)
        if (ms > 0) return formatDuration(ms)
      } else {
        const ms = getStreamDurationMs(sid, '__pending__')
        if (ms > 0) return formatDuration(ms)
      }
    }
    return ''
  }

  const sid = props.sessionId
  if (sid && props.messageId) {
    const ms = getStreamDurationMs(sid, props.messageId)
    if (ms > 0) return formatDuration(ms)
  }
  if (props.durationMs > 0) return formatDuration(props.durationMs)
  return ''
})

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = Math.round(s % 60)
  return `${m}m${rest}s`
}

const content = computed(() => props.content || computedBlocks.value.filter(b => b.type === 'text').map(b => b.text).join(''))
const hasMetaInfo = computed(() => !!(props.isLoading || props.model || formattedDuration.value || tokenInput.value || tokenOutput.value || tokenTotal.value))

function copyContent() {
  if (!content.value) return
  navigator.clipboard.writeText(content.value).then(() => {
    copied.value = true
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copied.value = false }, 1500)
  })
}
</script>

<style scoped>
.assistant-message {
  width: 100%;
  font-family: 'Inter', 'Noto Sans SC', ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* 运行元数据栏 */
.meta-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 4px 0 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border-neutral-l1, rgba(0,0,0,0.06));
  font-size: 11px;
  color: var(--text-tertiary, #999);
  line-height: 1.4;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.meta-item svg {
  opacity: 0.7;
  flex-shrink: 0;
}

.meta-model {
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
  font-weight: 500;
  color: var(--text-secondary, #666);
}

/* 思考过程块 */
.work-block {
  margin: 2px 0 3px;
}

.work-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px 2px 0;
  cursor: pointer;
  user-select: none;
  color: var(--text-tertiary, #9ca3af);
  font-size: 12px;
  border-radius: 4px;
  transition: color 0.15s;
}

.work-header:hover {
  color: var(--text-secondary, #6b7280);
}

.work-icon {
  transition: transform 0.18s;
  flex-shrink: 0;
  opacity: 0.85;
}

.work-icon.expanded {
  transform: rotate(90deg);
}

.work-title {
  font-weight: 400;
}

.work-content {
  margin-top: 5px;
  max-height: 360px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.work-content::-webkit-scrollbar {
  width: 6px;
}

.work-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.14);
  border-radius: 3px;
}

.reasoning-text {
  margin: 0;
  line-height: 1.5;
  font-size: 13px;
  color: var(--text-tertiary, #94a3b8);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 回复内容 */
.message-content {
  width: 100%;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-default, #1a1a1a);
  word-break: break-word;
}

/* 加载动画 */
.loading-dots {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary, #9ca3af);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* 复制按钮 */
.message-actions {
  display: flex;
  justify-content: flex-start;
  margin-top: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-tertiary, #999);
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--bg-overlay-l1, rgba(0,0,0,0.04));
  color: var(--text-secondary, #666);
}

/* ============ 工具调用块（灰色框包裹） ============ */
.tools-block,
.tool-block {
  margin: 2px 0 4px;
  background: #f5f5f5;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 3px 8px;
}

.tool-header,
.tool-body-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  cursor: pointer;
  user-select: none;
  min-height: 20px;
  border-radius: 4px;
  transition: background 0.15s;
}

.tool-header:hover,
.tool-body-header:hover {
  background: rgba(0, 0, 0, 0.04);
}

.tool-icon {
  transition: transform 0.18s;
  flex-shrink: 0;
  opacity: 0.7;
  color: #9ca3af;
}

.tool-icon.expanded {
  transform: rotate(90deg);
}

.tool-name {
  font-size: 11px;
  font-weight: 500;
  color: #475569;
  flex-shrink: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.tool-args-preview {
  font-size: 11px;
  color: #94a3b8;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-running-badge {
  font-size: 11px;
  color: #3b82f6;
  font-style: italic;
  flex-shrink: 0;
}

.tool-body {
  border-radius: 4px;
}

.tool-section {
  padding: 2px 0;
}

.section-label {
  font-size: 10px;
  color: #94a3b8;
  margin-bottom: 2px;
  display: block;
}

.code-text {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.running-text {
  font-size: 11px;
  color: #3b82f6;
  font-style: italic;
}
</style>
