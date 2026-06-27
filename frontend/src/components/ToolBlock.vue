<template>
  <div class="tool-block" :class="{ 'tool-block--expanded': isExpanded, 'tool-block--confirm': pendingConfirmation }">
    <!-- 折叠状态：显示工具名和参数预览 -->
    <div v-if="!isExpanded" class="tool-header" @click="toggleExpand">
      <div class="tool-title">
        <span class="tool-name">{{ toolName }}</span>
        <span class="tool-args-preview">{{ argsPreview }}</span>
      </div>
      <span v-if="pendingConfirmation" class="confirm-badge">待确认</span>
      <div v-if="hasTerminalSession || isSubagentDelegate || isTodoWrite" class="tool-actions">
        <button
          v-if="hasTerminalSession"
          type="button"
          class="view-terminal-btn"
          title="在控制台查看命令执行过程"
          @click.stop="openTerminal"
        >查看终端</button>
        <button
          v-if="isSubagentDelegate"
          type="button"
          class="view-terminal-btn"
          title="查看智能体实时工作过程"
          @click.stop="viewSubagent"
        >查看智能体</button>
        <button
          v-if="isTodoWrite"
          type="button"
          class="view-terminal-btn"
          title="查看任务清单"
          @click.stop="openTodos"
        >查看任务</button>
        <button
          v-if="showBackgroundBtn"
          type="button"
          class="background-btn"
          :title="autoDetached ? '停止后台服务' : '转入后台运行'"
          @click.stop="autoDetached ? stopService() : doBackground()"
        >{{ autoDetached ? '停止服务' : '后台运行' }}</button>
      </div>
    </div>

    <!-- 展开状态：显示完整内容 -->
    <div v-else class="tool-body">
      <!-- 头部（可点击折叠） -->
      <div class="tool-body-header" @click="toggleExpand">
        <div class="tool-title">
          <span class="tool-name">{{ toolName }}</span>
          <span class="tool-args-preview">{{ argsPreview }}</span>
        </div>
        <div v-if="hasTerminalSession || isSubagentDelegate || isTodoWrite" class="tool-actions">
          <button
            v-if="hasTerminalSession"
            type="button"
            class="view-terminal-btn"
            title="在控制台查看命令执行过程"
            @click.stop="openTerminal"
          >查看终端</button>
          <button
            v-if="isSubagentDelegate"
            type="button"
            class="view-terminal-btn"
            title="查看智能体实时工作过程"
            @click.stop="viewSubagent"
          >查看智能体</button>
          <button
            v-if="isTodoWrite"
            type="button"
            class="view-terminal-btn"
            title="查看任务清单"
            @click.stop="openTodos"
          >查看任务</button>
          <button
            v-if="showBackgroundBtn"
            type="button"
            class="background-btn"
            :title="autoDetached ? '停止后台服务' : '转入后台运行'"
            @click.stop="autoDetached ? stopService() : doBackground()"
          >{{ autoDetached ? '停止服务' : '后台运行' }}</button>
        </div>
      </div>

      <!-- 参数详情 -->
      <div class="tool-section">
        <span class="section-label">参数</span>
        <div class="section-content code-block">
          <pre class="code-text">{{ formattedArgs }}</pre>
        </div>
      </div>
      
      <!-- 执行结果 -->
      <div v-if="result || error" class="tool-section">
        <span class="section-label">结果</span>
        <div class="section-content code-block">
          <pre class="code-text" :class="{ 'error-text': error }">{{ result || error }}</pre>
        </div>
      </div>
      
      <!-- 运行中状态 -->
      <div v-else-if="status === 'running' && !pendingConfirmation" class="tool-section">
        <span class="section-label">状态</span>
        <div class="section-content">
          <span class="running-text">{{ isBackgrounded ? '已转入后台运行' : '运行中...' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { backgroundTerminalCommand, getTerminalSessionId, stopTerminalCommand } from '@/api/terminal'
import MarkdownRenderer from './MarkdownRenderer.vue'

defineOptions({ name: 'ToolBlock' })

const props = defineProps<{
  toolName: string
  status: string
  args?: Record<string, any>
  preview?: string
  result?: string
  error?: string
  startedAt?: string
  endedAt?: string
  compact?: boolean
  pendingConfirmation?: boolean
  dangerInfo?: string
  autoDetached?: boolean
  sessionId?: string
  toolCallId?: string
  subagent?: {
    task_id?: string
    subagent?: string
    task?: string
    status?: string
    round?: number
    last_event?: string
    elapsed_ms?: number
    log_path?: string
    inner_blocks?: InnerBlock[]
    final_message?: string
  }
}>()

interface InnerBlock {
  type: 'tool' | 'text' | 'summary'
  phase?: 'work' | 'answer'
  text?: string
  tool_name?: string
  status?: string
  args?: Record<string, any>
  result?: string
  error?: string
  tool_call_id?: string
}

const isExpanded = ref(false)
const isBackgrounded = ref(false)
const isStopped = ref(false)
const isOpeningTerminal = ref(false)

const isSubagentDelegate = computed(() => props.toolName === 'delegate_to_subagent')
const isTodoWrite = computed(() => props.toolName === 'todo_write')
const subagentStatusLabel = computed(() => {
  const s = props.subagent?.status || ''
  switch (s) {
    case 'running': return '执行中'
    case 'stalled': return '可能卡住'
    case 'success': return '已完成'
    case 'failed': return '失败'
    case 'timeout': return '超时'
    case 'cancelled': return '已取消'
    default: return s || '准备中'
  }
})
const subagentElapsedText = computed(() => {
  const ms = props.subagent?.elapsed_ms || 0
  if (!ms) return ''
  const s = Math.round(ms / 100) / 10
  return `${s.toFixed(1)}s`
})

const autoDetached = computed(() => props.autoDetached || isBackgrounded.value)

const showBackgroundBtn = computed(() => {
  return isCliExecutor.value && !isStopped.value && (props.status === 'running' || autoDetached.value)
})

const argsPreview = computed(() => {
  if (props.preview) return props.preview
  
  const args = props.args || {}
  const keys = Object.keys(args)
  if (keys.length === 0) return ''
  
  const priorityKeys = ['query', 'command', 'url', 'path', 'action', 'file_path']
  for (const key of priorityKeys) {
    if (args[key]) {
      const value = String(args[key])
      if (value.length > 40) {
        return value.substring(0, 40) + '...'
      }
      return value
    }
  }
  
  const firstValue = String(args[keys[0]])
  if (firstValue.length > 40) {
    return firstValue.substring(0, 40) + '...'
  }
  return firstValue
})

const formattedArgs = computed(() => {
  try {
    return JSON.stringify(props.args, null, 2)
  } catch (e) {
    return '{}'
  }
})

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

const isCliExecutor = computed(() => {
  return props.toolName === 'cli_executor'
})

const hasTerminalSession = computed(() => {
  return isCliExecutor.value && (!!props.sessionId || !!props.toolCallId)
})

async function openTerminal() {
  if (isOpeningTerminal.value) return
  isOpeningTerminal.value = true
  try {
    let sessionId = props.sessionId || ''
    if (!sessionId && props.toolCallId) {
      sessionId = await getTerminalSessionId(props.toolCallId) || ''
    }
    if (!sessionId) {
      window.dispatchEvent(new CustomEvent('aries:toast', {
        detail: { message: '终端不存在或已关闭', type: 'warning' }
      }))
      return
    }
    window.dispatchEvent(new CustomEvent('aries:focus-console'))
    window.dispatchEvent(new CustomEvent('aries:open-terminal', {
      detail: { sessionId, command: argsPreview.value }
    }))
  } finally {
    setTimeout(() => {
      isOpeningTerminal.value = false
    }, 500)
  }
}

function openTodos() {
  window.dispatchEvent(new CustomEvent('aries:open-todo-panel'))
}

function viewSubagent() {
  // 即使 subagent 还没绑定（子 Agent 刚启动，subagent_event 尚未到达），
  // 也允许打开面板：用 args 里的 subagent_name/task 做 fallback，
  // taskId 用 toolCallId 临时充当，SubagentChatPanel 会在收到第一个
  // subagent_event 时自动锁定真实 task_id。
  const sa = props.subagent || ({} as any)
  const initial = {
    subagent: sa.subagent || props.args?.subagent_name || '',
    task: sa.task || props.args?.task || '',
    status: sa.status || 'running',
    round: sa.round,
    last_event: sa.last_event,
    elapsed_ms: sa.elapsed_ms,
    log_path: sa.log_path,
    inner_blocks: sa.inner_blocks,
    final_message: sa.final_message,
  }
  window.dispatchEvent(new CustomEvent('aries:focus-console'))
  window.dispatchEvent(new CustomEvent('aries:view-subagent', {
    detail: {
      taskId: sa.task_id || props.toolCallId || '',
      subagent: initial.subagent,
      task: initial.task,
      status: initial.status,
      round: initial.round,
      lastEvent: initial.last_event,
      elapsedMs: initial.elapsed_ms,
      logPath: initial.log_path,
      innerBlocks: initial.inner_blocks,
      finalMessage: initial.final_message,
    }
  }))
}

async function doBackground() {
  if (!props.toolCallId) return
  try {
    await backgroundTerminalCommand(props.toolCallId)
    isBackgrounded.value = true
  } catch (e) {
    console.error('Background failed', e)
  }
}

async function stopService() {
  if (!props.toolCallId) return
  try {
    await stopTerminalCommand(props.toolCallId)
    isStopped.value = true
  } catch (e) {
    console.error('Stop service failed', e)
  }
}
</script>

<style scoped>
.tool-block {
  background: transparent;
  border-radius: 4px;
  margin: 2px 0;
  overflow: hidden;
  border: none;
  border-left: 2px solid #cbd5e1;
  padding-left: 8px;
}

.tool-block--confirm {
  border-left-color: #f59e0b;
}

.tool-block--expanded {
  background: transparent;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px;
  cursor: pointer;
  user-select: none;
  background: transparent;
  transition: background-color 0.2s;
  min-height: 18px;
}

.tool-header:hover {
  background: rgba(0, 0, 0, 0.03);
}

.confirm-badge {
  font-size: 10px;
  color: #b45309;
  background: #fef3c7;
  padding: 1px 6px;
  border-radius: 999px;
}

.tool-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.view-terminal-btn {
  font-size: 10px;
  color: #000000;
  background: transparent;
  border: none;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  margin-left: 6px;
  flex-shrink: 0;
  font-weight: 500;
  letter-spacing: 0.5px;
  transition: background 0.15s;
}

.view-terminal-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

.background-btn {
  font-size: 10px;
  color: #6b7280;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.background-btn:hover {
  background: #e5e7eb;
}

.tool-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-body {
  border-top: none;
}

.tool-body-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px;
  background: transparent;
  border-bottom: none;
  cursor: pointer;
  user-select: none;
  min-height: 18px;
}

.tool-body-header:hover {
  background: rgba(0, 0, 0, 0.03);
}

.tool-section {
  padding: 4px 4px 4px 8px;
  border-bottom: none;
}

.tool-section:last-child {
  border-bottom: none;
}

.section-label {
  font-size: 10px;
  color: #94a3b8;
  margin-bottom: 2px;
  display: block;
}

.code-block {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  overflow-x: auto;
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

.error-text {
  color: #c2410c;
}

.running-text {
  font-size: 11px;
  color: #3b82f6;
  font-style: italic;
}

.sa-inline-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  border: 1px solid transparent;
}
.sa-inline-pill .sa-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #888;
}
.sa-inline-pill .sa-inline-text { font-weight: 500; }
.sa-inline-pill .sa-inline-meta { color: var(--text-muted); }

/* ---- 子 Agent 进度条 ---- */
.subagent-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  margin: 4px 0 6px;
  background: rgba(74, 144, 217, 0.08);
  border: 1px solid rgba(74, 144, 217, 0.18);
}
.subagent-progress .sa-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4a90d9;
  flex-shrink: 0;
}
.subagent-status--running .sa-dot { background: #4a90d9; animation: sa-pulse 1.4s infinite ease-in-out; }
.subagent-status--stalled .sa-dot { background: #ff9500; }
.subagent-status--success .sa-dot { background: #34c759; }
.subagent-status--failed .sa-dot,
.subagent-status--timeout .sa-dot,
.subagent-status--cancelled .sa-dot { background: #ff3b30; }
@keyframes sa-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.subagent-status--stalled { background: rgba(255, 149, 0, 0.08); border-color: rgba(255, 149, 0, 0.3); }
.subagent-status--success { background: rgba(52, 199, 89, 0.08); border-color: rgba(52, 199, 89, 0.3); }
.subagent-status--failed,
.subagent-status--timeout,
.subagent-status--cancelled { background: rgba(255, 59, 48, 0.08); border-color: rgba(255, 59, 48, 0.3); }

.subagent-progress .sa-name { font-weight: 600; color: var(--text); }
.subagent-progress .sa-status { color: var(--text-secondary); }
.subagent-progress .sa-round,
.subagent-progress .sa-elapsed { color: var(--text-muted); font-size: 11px; }
.subagent-progress .sa-event {
  flex: 1;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.subagent-detail { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.subagent-detail .sa-pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  margin-left: 6px;
}
.subagent-detail .sa-meta { color: var(--text-muted); margin-left: 8px; font-size: 11px; }
.subagent-detail .sa-event-line { color: var(--text-secondary); }
.subagent-detail .sa-task-line { color: var(--text-muted); }
.subagent-detail code { font-size: 11px; }

/* 子 Agent 流式工作过程 */
.subagent-stream {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 6px;
  border-left: 2px solid rgba(74, 144, 217, 0.3);
}
.subagent-reasoning {
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.subagent-answer {
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
  padding: 4px 0;
}
.subagent-final {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
}
.subagent-final .section-label {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
