<template>
  <div class="subagent-embed" @click="toggleExpand">
    <div class="subagent-embed-header">
      <svg
        class="subagent-embed-chevron"
        :class="{ expanded: isExpanded }"
        width="10"
        height="10"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="3"
      >
        <path d="m9 18 6-6-6-6" />
      </svg>
      <span class="sa-badge">子 Agent</span>
      <span class="sa-name">{{ displayName }}</span>
      <span v-if="taskText" class="sa-task" :title="taskText">{{ taskText }}</span>
      <span class="sa-status" :class="statusClass">{{ statusLabel }}</span>
      <span v-if="elapsedText" class="sa-elapsed">{{ elapsedText }}</span>
    </div>

    <div v-if="isExpanded" class="subagent-embed-body" @click.stop>
      <div v-if="displayBlocks.length > 0" class="sa-inner">
        <template v-for="(block, idx) in displayBlocks" :key="idx">
          <div v-if="block.type === 'text'" class="sa-text" :class="block.phase || 'work'">
            <div v-if="block.phase === 'answer'" class="sa-phase-label">结论</div>
            <pre class="sa-text-body">{{ block.text }}</pre>
          </div>
          <div v-else-if="block.type === 'tool'" class="sa-tool">
            <div class="sa-tool-header" @click="toggleInnerTool(idx)">
              <svg
                class="sa-tool-chevron"
                :class="{ expanded: isInnerToolOpen(idx) }"
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
              >
                <path d="m9 18 6-6-6-6" />
              </svg>
              <span class="sa-tool-name">{{ block.tool_name }}</span>
              <span v-if="toolArgsPreview(block)" class="sa-tool-preview">{{ toolArgsPreview(block) }}</span>
              <span
                class="sa-tool-status"
                :class="{ running: block.status === 'running', error: block.status === 'error' }"
              >
                {{ block.status === 'running' ? '运行中…' : block.status === 'error' ? '失败' : '完成' }}
              </span>
            </div>
            <div v-show="isInnerToolOpen(idx)" class="sa-tool-body">
              <div v-if="block.args && Object.keys(block.args).length" class="sa-section">
                <span class="sa-section-label">参数</span>
                <pre class="sa-code">{{ JSON.stringify(block.args, null, 2) }}</pre>
              </div>
              <div v-if="block.result" class="sa-section">
                <span class="sa-section-label">结果</span>
                <pre class="sa-code">{{ truncate(block.result, 4000) }}</pre>
              </div>
              <div v-else-if="block.status === 'running'" class="sa-section">
                <span class="sa-running">运行中…</span>
              </div>
              <div v-if="block.error" class="sa-section">
                <span class="sa-section-label">错误</span>
                <pre class="sa-code sa-error">{{ block.error }}</pre>
              </div>
            </div>
          </div>
        </template>
      </div>
      <div v-else class="subagent-embed-empty">
        {{ isRunning ? '智能体正在启动…' : (errorText || '暂无工作过程') }}
      </div>
      <div v-if="finalMessage && !hasAnswerBlock" class="sa-final">
        <div class="sa-phase-label">结论</div>
        <pre class="sa-text-body">{{ finalMessage }}</pre>
      </div>
      <div v-if="errorText && isTerminal" class="sa-final sa-final-error">
        <div class="sa-phase-label">失败原因</div>
        <pre class="sa-text-body">{{ errorText }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  finalizeSubagentDisplayBlocks,
  isTerminalSubagentStatus,
} from '../utils/subagentLogParser'

const props = defineProps({
  args: { type: Object, default: () => ({}) },
  subagent: { type: Object, default: null },
  status: { type: String, default: '' },
  result: { type: String, default: '' },
})

const isExpanded = ref(true)
const innerToolOpen = ref({})

const displayName = computed(
  () => props.subagent?.subagent || props.args?.subagent_name || '智能体',
)
const taskText = computed(() => props.subagent?.task || props.args?.task || '')
const currentStatus = computed(
  () => props.subagent?.status || props.status || 'pending',
)
const isRunning = computed(() => {
  const s = currentStatus.value
  return !s || s === 'pending' || s === 'running' || s === 'stalled'
})
const isTerminal = computed(() => isTerminalSubagentStatus(currentStatus.value))

const statusLabel = computed(() => {
  const s = currentStatus.value
  const map = {
    pending: '等待中',
    running: '运行中',
    stalled: '长时间无响应',
    success: '已完成',
    failed: '失败',
    timeout: '超时',
    cancelled: '已取消',
    completed: '已完成',
    error: '失败',
  }
  return map[s] || s || '运行中'
})

const statusClass = computed(() => {
  const s = currentStatus.value
  if (s === 'success' || s === 'completed') return 'ok'
  if (s === 'failed' || s === 'timeout' || s === 'cancelled' || s === 'error') return 'bad'
  if (s === 'stalled') return 'warn'
  return 'run'
})

const elapsedText = computed(() => {
  const ms = props.subagent?.elapsed_ms || 0
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
})

const finalMessage = computed(
  () => props.subagent?.final_message || '',
)
const errorText = computed(() => props.subagent?.error || '')

const displayBlocks = computed(() => {
  const raw = props.subagent?.inner_blocks || []
  return finalizeSubagentDisplayBlocks(raw, finalMessage.value)
})

const hasAnswerBlock = computed(() =>
  displayBlocks.value.some((b) => b.type === 'text' && b.phase === 'answer'),
)

watch(
  () => isRunning.value,
  (running) => {
    if (running) isExpanded.value = true
  },
  { immediate: true },
)

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function toggleInnerTool(idx) {
  innerToolOpen.value = {
    ...innerToolOpen.value,
    [idx]: !innerToolOpen.value[idx],
  }
}

function isInnerToolOpen(idx) {
  // 运行中的工具默认展开
  if (idx in innerToolOpen.value) return !!innerToolOpen.value[idx]
  const b = displayBlocks.value[idx]
  return b?.status === 'running'
}

function toolArgsPreview(block) {
  if (!block?.args) return ''
  if (block.args.query) return String(block.args.query)
  if (block.args.command) return String(block.args.command)
  if (block.args.path) return String(block.args.path)
  const raw = JSON.stringify(block.args)
  return raw.length > 60 ? raw.slice(0, 60) + '…' : raw
}

function truncate(text, max) {
  const s = String(text || '')
  return s.length > max ? s.slice(0, max) + '\n…(已截断)' : s
}
</script>

<style scoped>
.subagent-embed {
  background: transparent;
  border: none;
  padding: 4px 0;
  margin: 4px 0;
  cursor: pointer;
}

.subagent-embed-header {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  min-width: 0;
}

.subagent-embed-chevron {
  flex-shrink: 0;
  color: #9ca3af;
  transition: transform 0.18s;
}

.subagent-embed-chevron.expanded {
  transform: rotate(90deg);
}

.sa-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #6b7280;
}

.sa-name {
  font-weight: 600;
  color: #111827;
  flex-shrink: 0;
}

.sa-task {
  flex: 1;
  min-width: 0;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sa-status {
  flex-shrink: 0;
  font-size: 11px;
  color: #6b7280;
}

.sa-status.run {
  font-style: italic;
}

.sa-elapsed {
  color: #9ca3af;
  font-size: 11px;
  flex-shrink: 0;
}

.subagent-embed-body {
  margin-top: 8px;
  padding-top: 4px;
  cursor: default;
  max-height: 420px;
  overflow-y: auto;
}

.subagent-embed-empty {
  font-size: 12px;
  color: #9ca3af;
  font-style: italic;
}

.sa-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sa-text {
  background: transparent;
  border: none;
  padding: 2px 0;
}

.sa-text.answer {
  background: transparent;
  border: none;
}

.sa-phase-label {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 6px;
}

.sa-text-body {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.sa-tool {
  background: #f5f5f5;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 6px 10px;
}

.sa-tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  color: #475569;
}

.sa-tool-chevron {
  transition: transform 0.18s;
  flex-shrink: 0;
  opacity: 0.6;
}

.sa-tool-chevron.expanded {
  transform: rotate(90deg);
}

.sa-tool-name {
  font-size: 12px;
  font-weight: 500;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  flex-shrink: 0;
}

.sa-tool-preview {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sa-tool-status {
  font-size: 11px;
  color: #6b7280;
  flex-shrink: 0;
}

.sa-tool-status.running {
  font-style: italic;
}

.sa-tool-body {
  margin-top: 8px;
}

.sa-section {
  padding: 4px 0;
}

.sa-section-label {
  font-size: 10px;
  color: #94a3b8;
  margin-bottom: 2px;
  display: block;
}

.sa-code {
  margin: 0;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

.sa-running {
  font-size: 11px;
  color: #6b7280;
  font-style: italic;
}

.sa-final,
.sa-final-error {
  margin-top: 8px;
  background: transparent;
  border: none;
  padding: 2px 0;
}
</style>
