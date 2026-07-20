<template>
  <div class="tool-block" :class="{ 'tool-block--expanded': isExpanded, 'tool-block--confirm': pendingConfirmation, 'tool-block--file-edit': !!fileEditPreview, 'tool-block--subagent': isSubagentDelegate, 'tool-block--mcp': isMcpToolBlock }">
    <!-- 文件编辑/写入：diff 卡片样式 -->
    <template v-if="fileEditPreview">
      <div class="file-edit-wrap">
        <FileEditPreviewCard
          :data="fileEditPreview"
          :expanded="isExpanded"
          :error="error"
          @click="toggleExpand"
          @view-diff="onViewFileDiff"
        />
      </div>
      <div v-if="isExpanded && status === 'running' && !pendingConfirmation && !result && !error" class="file-edit-running">
        Running...
      </div>
      <ToolActionBar
        :show-terminal="hasTerminalSession"
        :show-todo="isTodoWrite"
        :show-background="showBackgroundBtn"
        :auto-detached="autoDetached"
        @open-terminal="openTerminal"
        @open-todos="openTodos"
        @toggle-background="autoDetached ? stopService() : doBackground()"
      />
    </template>

    <!-- 子智能体委派：内嵌展示完整工作过程（思考 + 工具 + 回复） -->
    <template v-else-if="isSubagentDelegate">
      <div class="subagent-embed" @click="toggleExpand">
        <div class="subagent-embed-header">
          <svg class="subagent-embed-chevron" :class="{ expanded: isExpanded }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <path d="m9 18 6-6-6-6"/>
          </svg>
          <span class="sa-name">{{ subagentDisplayName }}</span>
          <span v-if="subagentTaskText" class="sa-task">{{ subagentTaskText }}</span>
          <span class="sa-status">{{ subagentStatusLabel }}</span>
          <span v-if="subagentElapsedText" class="sa-elapsed">{{ subagentElapsedText }}</span>
        </div>
        <div v-if="isExpanded" class="subagent-embed-body" @click.stop>
          <AssistantMessage
            v-if="subagentBlocks.length > 0"
            class="subagent-embed-message"
            :blocks="subagentBlocks"
            :is-loading="subagentIsRunning"
            text-color="#1a1a1a"
            :font-size="13"
          />
          <div v-else class="subagent-embed-empty">
            {{ subagentIsRunning ? '智能体正在启动…' : '暂无工作过程' }}
          </div>
        </div>
      </div>
    </template>

    <!-- MCP 工具：卡片样式 -->
    <template v-else-if="isMcpToolBlock">
      <div class="mcp-card">
        <div class="mcp-card-header" @click="toggleExpand">
          <svg class="mcp-card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          <span class="mcp-card-title">{{ mcpDisplayName }}</span>
          <span v-if="pendingConfirmation" class="confirm-badge">待确认</span>
          <button type="button" class="mcp-toggle-btn" :title="isExpanded ? '收起' : '展开'" @click.stop="toggleExpand">
            <svg v-if="!isExpanded" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="m6 9 6 6 6-6"/>
            </svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="m18 15-6-6-6 6"/>
            </svg>
          </button>
        </div>

        <div v-if="isExpanded" class="mcp-card-body">
          <div class="mcp-section">
            <span class="mcp-section-label">参数</span>
            <div class="mcp-code-block">
              <pre class="mcp-code-text">{{ formattedArgs }}</pre>
            </div>
          </div>

          <div v-if="result || error || status === 'running'" class="mcp-section">
            <div class="mcp-section-head">
              <span class="mcp-section-label">响应</span>
              <div v-if="result || error" class="mcp-view-toggle">
                <button
                  type="button"
                  class="mcp-view-btn"
                  :class="{ active: mcpResultView === 'content' }"
                  @click.stop="mcpResultView = 'content'"
                >
                  Content
                </button>
                <button
                  type="button"
                  class="mcp-view-btn"
                  :class="{ active: mcpResultView === 'raw' }"
                  @click.stop="mcpResultView = 'raw'"
                >
                  Raw
                </button>
              </div>
            </div>

            <div v-if="isScreenshotToolBlock && screenshotDisplay.screenshotPreview" class="screenshot-preview-wrap">
              <img
                class="screenshot-preview-img"
                :src="screenshotDisplay.screenshotPreview"
                :alt="screenshotDisplay.screenshotPath || 'screenshot'"
                @click.stop="openScreenshotPreview"
              />
              <div v-if="screenshotDisplay.screenshotPath" class="screenshot-path">{{ screenshotDisplay.screenshotPath }}</div>
            </div>

            <div v-if="error" class="mcp-code-block">
              <pre class="mcp-code-text error-text">{{ error }}</pre>
            </div>
            <div v-else-if="result" class="mcp-code-block">
              <pre class="mcp-code-text">{{ mcpResultText }}</pre>
            </div>
            <div v-else-if="status === 'running' && !pendingConfirmation" class="mcp-running">
              <span class="running-text">{{ isBackgrounded ? '已转入后台运行' : '运行中...' }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 其他工具：原有样式 -->
    <template v-else>
    <!-- CLI：统一卡片，顶部灰色栏始终展示 -->
    <template v-if="isCliExecutor && cliCommand">
      <div class="cli-card">
        <div class="cli-card-header">
          <button type="button" class="cli-toggle-btn" :title="isExpanded ? '收起' : '展开'" @click.stop="toggleExpand">
            <svg v-if="!isExpanded" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="m6 9 6 6 6-6"/>
            </svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="m18 15-6-6-6 6"/>
            </svg>
          </button>
          <ToolActionBar
            class="cli-action-bar"
            :expanded="isExpanded"
            :show-terminal="hasTerminalSession"
            :show-stop="showStopBtn"
            :show-background="showBackgroundBtn"
            :auto-detached="autoDetached"
            plain
            @open-terminal="openTerminal"
            @stop-command="stopService"
            @toggle-background="autoDetached ? stopService() : doBackground()"
          />
        </div>

        <div v-if="!isExpanded" class="cli-card-body cli-card-body--preview" @click="toggleExpand">
          <span class="cli-prompt">$</span>
          <code class="cli-command-text">{{ cliCommand }}</code>
        </div>

        <div v-else class="cli-card-body cli-card-body--expanded">
          <button type="button" class="cli-copy-btn" title="复制命令与输出" @click.stop="copyCliContent">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
          </button>
          <div class="cli-terminal-view">
            <div class="cli-command-line">
              <span class="cli-prompt">$</span>
              <code class="cli-command-text">{{ cliCommand }}</code>
            </div>
            <div v-if="cliOutputText" class="cli-output-block">
              <pre class="cli-output-text">{{ cliOutputText }}</pre>
            </div>
            <div v-else-if="status === 'running' && !pendingConfirmation" class="cli-output-block cli-output-running">
              <span class="running-text">{{ isBackgrounded ? '已转入后台运行' : '运行中...' }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 折叠状态：显示工具名和参数预览 -->
    <template v-else-if="!isExpanded">
      <template v-if="isTodoWrite && toolTodos.length">
        <div class="todo-card" @click="toggleExpand">
          <div class="todo-card-header">
            <span class="todo-card-title">任务规划（{{ toolTodos.length }}）</span>
            <ToolActionBar
              :show-todo="isTodoWrite"
              plain
              @open-todos="openTodos"
            />
          </div>
          <ul class="todo-mini-list">
            <li
              v-for="todo in toolTodos"
              :key="todo.id"
              class="todo-mini-item"
              :class="`todo-mini-status-${todo.status}`"
            >
              <span class="todo-mini-icon">
                <svg v-if="todo.status === 'completed'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <svg v-else-if="todo.status === 'in_progress'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <circle cx="12" cy="12" r="9" stroke-dasharray="40 16"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="9"/>
                </svg>
              </span>
              <span class="todo-mini-content">{{ todo.content }}</span>
              <span class="todo-mini-priority">{{ todo.priority }}</span>
            </li>
          </ul>
        </div>
      </template>
      <template v-else>
        <div class="tool-header" @click="toggleExpand">
          <div class="tool-title">
            <span class="tool-name">{{ toolName }}</span>
            <span class="tool-args-preview">{{ argsPreview }}</span>
          </div>
          <span v-if="pendingConfirmation" class="confirm-badge">待确认</span>
        </div>
        <ToolActionBar
          :show-terminal="hasTerminalSession"
          :show-todo="isTodoWrite"
          :show-background="showBackgroundBtn"
          :auto-detached="autoDetached"
          @open-terminal="openTerminal"
          @open-todos="openTodos"
          @toggle-background="autoDetached ? stopService() : doBackground()"
        />
      </template>
    </template>

    <!-- 展开状态：显示完整内容 -->
    <div v-else-if="!(isCliExecutor && cliCommand)" class="tool-body">
      <div class="tool-body-header" @click="toggleExpand">
        <div class="tool-title">
          <span class="tool-name">{{ toolName }}</span>
          <span class="tool-args-preview">{{ argsPreview }}</span>
        </div>
      </div>
      <ToolActionBar
        :show-terminal="hasTerminalSession"
        :show-todo="isTodoWrite"
        :show-background="showBackgroundBtn"
        :auto-detached="autoDetached"
        @open-terminal="openTerminal"
        @open-todos="openTodos"
        @toggle-background="autoDetached ? stopService() : doBackground()"
      />

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
        <div v-if="isScreenshotToolBlock && screenshotDisplay.screenshotPreview" class="screenshot-preview-wrap">
          <img
            class="screenshot-preview-img"
            :src="screenshotDisplay.screenshotPreview"
            :alt="screenshotDisplay.screenshotPath || 'screenshot'"
            @click.stop="openScreenshotPreview"
          />
          <div v-if="screenshotDisplay.screenshotPath" class="screenshot-path">{{ screenshotDisplay.screenshotPath }}</div>
        </div>
        <div class="section-content code-block">
          <pre class="code-text" :class="{ 'error-text': error }">{{ displayResult || error }}</pre>
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { backgroundTerminalCommand, getTerminalSessionId, stopTerminalCommand } from '@/api/terminal'
import FileEditPreviewCard from './FileEditPreviewCard.vue'
import ToolActionBar from './ToolActionBar.vue'
import AssistantMessage from './AssistantMessage.vue'
import { buildFileEditPreview } from '@/utils/fileEditPreview'
import { parseDelegateToolResult, finalizeSubagentDisplayBlocks } from '@/utils/subagentLogParser'
import { isTerminalSubagentStatus } from '@/utils/chatSubagentWs'
import { isScreenshotTool, parseToolResultForDisplay } from '@/utils/toolResultDisplay'
import { formatMcpToolDisplayName, isMcpTool, ensureMcpServerSlugsLoaded } from '@/utils/mcpToolDisplay'

defineOptions({ name: 'ToolBlock' })

const props = defineProps<{
  toolName: string
  status: string
  args?: Record<string, any>
  preview?: string
  result?: string
  error?: string
  screenshotPreview?: string
  screenshotPath?: string
  startedAt?: string
  endedAt?: string
  compact?: boolean
  pendingConfirmation?: boolean
  dangerInfo?: string
  autoDetached?: boolean
  sessionId?: string
  toolCallId?: string
  chatSessionId?: string
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
const mcpResultView = ref<'content' | 'raw'>('content')
const mcpSlugsReady = ref(false)

const isMcpToolBlock = computed(() => isMcpTool(props.toolName))
const mcpDisplayName = computed(() => {
  void mcpSlugsReady.value
  return formatMcpToolDisplayName(props.toolName)
})
const mcpResultText = computed(() => {
  if (mcpResultView.value === 'raw') return props.result || ''
  return displayResult.value || props.result || ''
})

const isSubagentDelegate = computed(() => props.toolName === 'delegate_to_subagent')
const isTodoWrite = computed(() => props.toolName === 'todo_write')
const isScreenshotToolBlock = computed(() => isScreenshotTool(props.toolName))

const screenshotDisplay = computed(() =>
  parseToolResultForDisplay(props.result, props.toolName, props.screenshotPreview),
)

const displayResult = computed(() => {
  if (props.error) return ''
  return screenshotDisplay.value.displayText || props.result || ''
})

function openScreenshotPreview() {
  const url = screenshotDisplay.value.screenshotPreview
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const fileEditPreview = computed(() => buildFileEditPreview(props.toolName, props.args))

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

// 即使 subagent_event 尚未到达（子 Agent 刚启动），也用 args 里的占位信息展示名称/任务
const subagentDisplayName = computed(() => {
  return props.subagent?.subagent || props.args?.subagent_name || '智能体'
})
const subagentTaskText = computed(() => {
  return props.subagent?.task || props.args?.task || ''
})
const subagentIsRunning = computed(() => {
  const s = props.subagent?.status || ''
  if (s === 'running' || s === 'pending' || s === 'stalled') return true
  return props.status === 'running'
})

watch(
  () => subagentIsRunning.value,
  (running) => {
    if (running && isSubagentDelegate.value) isExpanded.value = true
  },
  { immediate: true },
)

onMounted(() => {
  if (!isMcpToolBlock.value) return
  void ensureMcpServerSlugsLoaded().finally(() => {
    mcpSlugsReady.value = true
  })
})

watch(
  () => props.subagent?.status,
  (status) => {
    if (isTerminalSubagentStatus(status)) {
      isExpanded.value = false
    }
  },
)

// 子 Agent 内容由 chatPage 通过 SSE subagent_log_event 增量写入 inner_blocks
const subagentBlocks = computed<InnerBlock[]>(() => {
  if (!isExpanded.value && isTerminalSubagentStatus(props.subagent?.status)) {
    return []
  }
  const rawBlocks = props.subagent?.inner_blocks || []
  const finalText = props.subagent?.final_message
    || parseDelegateToolResult(props.result).final_message
    || ''
  return finalizeSubagentDisplayBlocks(rawBlocks, finalText)
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

const cliCommand = computed(() => {
  return String(props.args?.command || props.preview || '')
})

const cliOutputText = computed(() => {
  if (props.error) return props.error
  if (!props.result) return ''
  return parseToolResultForDisplay(props.result, props.toolName).displayText
})

async function copyCliContent() {
  const parts = [`$ ${cliCommand.value}`]
  if (cliOutputText.value) parts.push(cliOutputText.value)
  try {
    await navigator.clipboard.writeText(parts.join('\n\n'))
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: '已复制到剪贴板', type: 'success' },
    }))
  } catch {
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: '复制失败', type: 'warning' },
    }))
  }
}

const hasTerminalSession = computed(() => {
  return isCliExecutor.value && (!!props.sessionId || !!props.toolCallId)
})

const showStopBtn = computed(() => {
  return isCliExecutor.value && props.status === 'running' && !autoDetached.value
})

const toolTodos = computed(() => extractToolTodos())

async function openTerminal() {
  if (isOpeningTerminal.value) return
  isOpeningTerminal.value = true
  try {
    let sessionId = props.sessionId || ''
    if (!sessionId && props.toolCallId) {
      // 后端 Python 端用 `${chatSessionId}:${toolCallId}` 作 invocation key
      // 兼容兜底：先按复合 key 查，再按 toolCallId 单独查
      const candidates: string[] = []
      if (props.chatSessionId) {
        candidates.push(`${props.chatSessionId}:${props.toolCallId}`)
      }
      candidates.push(props.toolCallId)
      for (const inv of candidates) {
        const sid = await getTerminalSessionId(inv) || ''
        if (sid) { sessionId = sid; break }
      }
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
  const toolTodos = extractToolTodos()
  if (toolTodos.length === 0) {
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: '该工具调用没有任务数据', type: 'warning' },
    }))
    return
  }
  window.dispatchEvent(new CustomEvent('aries:open-todo-panel', {
    detail: {
      snapshot: true,
      todos: toolTodos,
      merge: props.args?.merge,
    },
  }))
}

interface TodoItem {
  id: string
  content: string
  priority: 'high' | 'medium' | 'low'
  status: 'pending' | 'in_progress' | 'completed'
}

function normalizeTodoItem(raw: unknown): TodoItem | null {
  if (!raw || typeof raw !== 'object') return null
  const t = raw as Record<string, unknown>
  const content = String(t.content ?? '').trim()
  if (!content) return null
  const priority = String(t.priority ?? 'medium')
  const status = String(t.status ?? 'pending')
  return {
    id: String(t.id ?? content),
    content,
    priority: (priority === 'high' || priority === 'low' ? priority : 'medium'),
    status: (
      status === 'completed' || status === 'in_progress' ? status : 'pending'
    ),
  }
}

function extractToolTodos(): TodoItem[] {
  const args = props.args
  if (args && Array.isArray(args.todos)) {
    return args.todos.map(normalizeTodoItem).filter((t): t is TodoItem => t !== null)
  }
  if (props.result) {
    try {
      const parsed = JSON.parse(props.result) as { todos?: unknown[] }
      if (Array.isArray(parsed?.todos)) {
        return parsed.todos.map(normalizeTodoItem).filter((t): t is TodoItem => t !== null)
      }
    } catch {
      // ignore malformed result
    }
  }
  return []
}

// 后端 Python 端用 `${chatSessionId}:${toolCallId}` 作为 invocation key
// 前端调用 background/stop 时必须用这个复合 key，否则 signal_detach 找不到事件
function buildInvocationId(): string {
  if (!props.toolCallId) return ''
  if (props.chatSessionId) return `${props.chatSessionId}:${props.toolCallId}`
  return props.toolCallId
}

async function doBackground() {
  const invocationId = buildInvocationId()
  if (!invocationId) return
  try {
    await backgroundTerminalCommand(invocationId)
    isBackgrounded.value = true
  } catch (e) {
    console.error('Background failed', e)
  }
}

async function stopService() {
  const invocationId = buildInvocationId()
  if (!invocationId) return
  try {
    await stopTerminalCommand(invocationId)
    isStopped.value = true
  } catch (e) {
    console.error('Stop service failed', e)
  }
}

function onViewFileDiff() {
  const data = fileEditPreview.value
  if (!data) return
  window.dispatchEvent(new CustomEvent('aries:view-file-diff', {
    detail: {
      path: data.filePath,
      original: data.original,
      modified: data.modified,
    },
  }))
}
</script>

<style scoped>
.tool-block--file-edit {
  border-left: none;
  padding-left: 0;
  margin: 6px 0;
}

.file-edit-wrap {
  position: relative;
}

.tool-body--file-edit {
  margin-top: 8px;
  border-top: 1px solid #f1f5f9;
  padding-top: 4px;
}

.file-edit-running {
  padding: 4px 2px 0;
  font-size: 11px;
  color: #3b82f6;
  font-style: italic;
}

.tool-block {
  background: transparent;
  border-radius: 4px;
  margin: 2px 0;
  overflow: hidden;
  border: none;
  padding-left: 0;
}

.tool-block--confirm {
  border-left: 2px solid #f59e0b;
  padding-left: 8px;
}

.tool-block--expanded {
  background: transparent;
}

.tool-header {
  display: flex;
  align-items: center;
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

/* ---- 子 Agent 内嵌卡片（全白背景） ---- */
.tool-block--subagent {
  border-left: none;
  padding-left: 0;
  margin: 6px 0;
}

.subagent-embed {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 12px;
  margin: 4px 0;
  cursor: pointer;
}
.subagent-embed:hover {
  background: #ffffff;
}

.subagent-embed-header {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}

.subagent-embed-chevron {
  flex-shrink: 0;
  color: #9ca3af;
  transition: transform 0.18s;
}
.subagent-embed-chevron.expanded {
  transform: rotate(90deg);
}

.sa-name { font-weight: 600; color: #111827; flex-shrink: 0; }
.sa-task {
  flex: 1;
  min-width: 0;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sa-status { color: #6b7280; flex-shrink: 0; }
.sa-elapsed { color: #9ca3af; font-size: 11px; flex-shrink: 0; }

.subagent-embed-body {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
  cursor: default;
  background: #ffffff;
}

.subagent-embed-body :deep(.subagent-embed-message) {
  background: #ffffff;
}

.subagent-embed-body :deep(.work-block),
.subagent-embed-body :deep(.work-content),
.subagent-embed-body :deep(.text-block),
.subagent-embed-body :deep(.assistant-message) {
  background: #ffffff;
}

.subagent-embed-empty {
  font-size: 12px;
  color: #9ca3af;
  font-style: italic;
  background: #ffffff;
}

/* ---- CLI 命令卡片 ---- */
.cli-card {
  margin: 4px 0;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
  background: #eef0f2;
}

.cli-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  padding: 3px 10px;
  background: #eef0f2;
  border-bottom: 1px solid #e5e7eb;
}

.cli-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.cli-toggle-btn:hover {
  color: #111827;
  background: rgba(0, 0, 0, 0.06);
}

.cli-action-bar {
  flex-shrink: 0;
}

.cli-card-body--preview {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 10px 12px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #1f2937;
  background: #eef0f2;
  cursor: pointer;
}

.cli-card-body--expanded {
  position: relative;
  padding: 14px 16px;
  max-height: 480px;
  overflow: auto;
  background: #eef0f2;
}

.cli-prompt {
  color: #9ca3af;
  flex-shrink: 0;
  user-select: none;
}

.cli-command-text {
  font-family: inherit;
  word-break: break-all;
  white-space: pre-wrap;
}

.cli-copy-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.7);
  color: #6b7280;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.cli-copy-btn:hover {
  background: #ffffff;
  color: #111827;
}

.cli-terminal-view {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.55;
  color: #1f2937;
  padding-right: 28px;
}

.cli-command-line {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.cli-output-block {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e5e7eb;
}

.cli-output-text {
  margin: 0;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  white-space: pre-wrap;
  word-break: break-word;
  color: inherit;
}

.cli-output-running {
  border-top: none;
  margin-top: 8px;
  padding-top: 0;
}

.cli-output-running .running-text {
  color: #6b7280;
  font-style: italic;
}

/* ---- 任务规划卡片 ---- */
.todo-card {
  background: #f3f4f6;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 4px 0;
  cursor: pointer;
  transition: background-color 0.15s;
}

.todo-card:hover {
  background: #e5e7eb;
}

.todo-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.todo-card-title {
  font-size: 12px;
  font-weight: 600;
  color: #111827;
}

.todo-mini-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.todo-mini-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #1f2937;
}

.todo-mini-icon {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  margin-top: 1px;
  color: #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
}

.todo-mini-status-completed .todo-mini-icon {
  color: #111827;
}

.todo-mini-status-in_progress .todo-mini-icon {
  color: #111827;
}

.todo-mini-content {
  flex: 1;
  word-break: break-word;
}

.todo-mini-status-completed .todo-mini-content {
  text-decoration: line-through;
  color: #6b7280;
}

.todo-mini-priority {
  flex-shrink: 0;
  font-size: 10px;
  color: #6b7280;
  text-transform: uppercase;
}

.screenshot-preview-wrap {
  margin-bottom: 8px;
}

.screenshot-preview-img {
  display: block;
  max-width: 100%;
  max-height: 280px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  cursor: zoom-in;
  object-fit: contain;
  background: #f8fafc;
}

.screenshot-path {
  margin-top: 4px;
  font-size: 10px;
  color: #64748b;
  word-break: break-all;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

/* ---- MCP 工具卡片 ---- */
.tool-block--mcp {
  border-left: none;
  padding-left: 0;
  margin: 8px 0;
}

.mcp-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  background: #ffffff;
}

.mcp-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 6px 12px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
  cursor: pointer;
  user-select: none;
}

.mcp-card-header:hover {
  background: #e9eef5;
}

.mcp-card-icon {
  flex-shrink: 0;
  color: #3b82f6;
}

.mcp-card-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mcp-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s, background 0.15s;
}

.mcp-toggle-btn:hover {
  color: #1e293b;
  background: rgba(255, 255, 255, 0.65);
}

.mcp-card-body {
  padding: 12px 14px 14px;
  background: #ffffff;
}

.mcp-section + .mcp-section {
  margin-top: 14px;
}

.mcp-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.mcp-section-label {
  font-size: 11px;
  color: #94a3b8;
  display: block;
  margin-bottom: 6px;
}

.mcp-section-head .mcp-section-label {
  margin-bottom: 0;
}

.mcp-view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: 999px;
  background: #f1f5f9;
}

.mcp-view-btn {
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 11px;
  line-height: 1;
  padding: 4px 8px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.mcp-view-btn.active {
  background: #ffffff;
  color: #334155;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.mcp-code-block {
  overflow-x: auto;
}

.mcp-code-text {
  margin: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.55;
  color: #475569;
  white-space: pre-wrap;
  word-break: break-word;
}

.mcp-running {
  padding-top: 2px;
}
</style>
