<template>
  <div class="side-chat-page">
    <!-- 顶部工具栏：标题 + 状态 + 暂停按钮 + 关闭 -->
    <div class="panel-header">
      <div class="panel-title">
        <span class="title-name">{{ subagentMeta.subagent || '智能体' }}</span>
        <span
          class="title-status-pill"
          :class="'pill-' + (subagentMeta.status || 'pending')"
        >{{ statusLabel(subagentMeta.status) }}</span>
        <span v-if="subagentMeta.round" class="title-meta">第 {{ subagentMeta.round }} 轮</span>
        <span v-if="elapsedText" class="title-meta">{{ elapsedText }}</span>
      </div>
    </div>

    <!-- 任务描述（如果有） -->
    <div v-if="subagentMeta.task" class="panel-task">
      <span class="task-label">任务</span>
      <span class="task-text">{{ subagentMeta.task }}</span>
    </div>

    <!-- 消息流（复用 SideChatPanel 样式） -->
    <div
      v-if="sideMessages.length > 0"
      class="chat-messages"
      ref="msgContainer"
    >
      <div
        v-for="(msg, index) in sideMessages"
        :key="index"
        class="msg-row"
        :class="msg.role"
      >
        <div v-if="msg.role === 'user'" class="msg-bubble user-bubble">
          <UserMessageContent :content="msg.content" />
        </div>
        <div v-else class="msg-bubble assistant-bubble">
          <AssistantMessage
            :content="msg.content"
            :reasoning="msg.reasoning || []"
            :tools="msg.tools || []"
            :blocks="msg.blocks || []"
            :is-loading="msg.isLoading"
            :text-color="textColor"
            :font-size="fontSize"
          />
        </div>
      </div>
    </div>
    <div v-else class="chat-empty-hint">
      <p v-if="loadingLog">加载日志中…</p>
      <p v-else-if="isRunning">智能体正在启动…</p>
      <p v-else>暂无工作过程</p>
    </div>

    <!-- 日志路径 -->
    <div v-if="subagentMeta.log_path" class="panel-footer">
      <span class="footer-label">日志</span>
      <code class="footer-path">{{ subagentMeta.log_path }}</code>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import AssistantMessage from '@/components/AssistantMessage.vue'
import UserMessageContent from '@/components/UserMessageContent.vue'

const API_BASE = import.meta.env.VITE_API_BASE || ''

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

interface SubagentMeta {
  task_id: string
  subagent?: string
  task?: string
  status?: string
  round?: number
  last_event?: string
  elapsed_ms?: number
  log_path?: string
}

const props = defineProps<{
  taskId: string
  initial?: {
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

const textColor = computed(() => '#1a1a1a')
const fontSize = computed(() => 14)

const subagentMeta = ref<SubagentMeta>({
  task_id: props.taskId,
  subagent: props.initial?.subagent,
  task: props.initial?.task,
  status: props.initial?.status,
  round: props.initial?.round,
  last_event: props.initial?.last_event,
  elapsed_ms: props.initial?.elapsed_ms,
  log_path: props.initial?.log_path,
})

// 真实 task_id 锁定：初始 taskId 可能是 toolCallId（subagent_event 尚未到达），
// 收到第一个匹配 subagent name 的 subagent_event 后锁定真实 task_id。
const lockedTaskId = ref<string>('')
const actualTaskId = computed(() => lockedTaskId.value || props.taskId)

const blocks = ref<InnerBlock[]>(
  Array.isArray(props.initial?.inner_blocks) ? [...props.initial!.inner_blocks!] : []
)
const finalMessage = ref<string>(props.initial?.final_message || '')

const loadingLog = ref(false)
const msgContainer = ref<HTMLElement>()

const isRunning = computed(() => {
  const s = subagentMeta.value.status
  return s === 'running' || s === 'pending' || s === 'stalled'
})

const elapsedText = computed(() => {
  const ms = subagentMeta.value.elapsed_ms || 0
  if (!ms) return ''
  return `${(Math.round(ms / 100) / 10).toFixed(1)}s`
})

const hasContent = computed(() => blocks.value.length > 0 || !!finalMessage.value)

interface SideMessage {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string[]
  tools?: any[]
  blocks?: InnerBlock[]
  isLoading?: boolean
}

/** 把 InnerBlock[] + finalMessage 组装成一条 assistant SideMessage（复用 SideChatPanel 渲染） */
const sideMessages = computed<SideMessage[]>(() => {
  if (!hasContent.value) return []
  // 思考过程（reasoning）= 所有 work 阶段文本
  const reasoning: string[] = []
  // blocks 直接透传给 AssistantMessage，让它按既有规则渲染（包括 report_to_main 工具卡）
  const msgBlocks: InnerBlock[] = []
  // content = 所有 answer 阶段文本拼接
  let content = ''

  for (const b of blocks.value) {
    if (b.type === 'text' && b.phase === 'work' && b.text) {
      reasoning.push(b.text)
      msgBlocks.push({ ...b })
    } else if (b.type === 'text' && b.phase === 'answer' && b.text) {
      content += b.text
      msgBlocks.push({ ...b })
    } else if (b.type === 'tool') {
      // 工具块（含 report_to_main）保持原样透传
      msgBlocks.push({ ...b })
    } else {
      msgBlocks.push({ ...b })
    }
  }

  // 如果有 finalMessage（report_to_main 的最终回复），追加为 answer 文本
  if (finalMessage.value) {
    const finalText = finalMessage.value
    content += (content ? '\n\n' : '') + finalText
    msgBlocks.push({ type: 'text', phase: 'answer', text: finalText })
  }

  return [{
    role: 'assistant',
    content,
    reasoning,
    tools: [],
    blocks: msgBlocks,
    isLoading: isRunning.value,
  }]
})

function statusLabel(s?: string): string {
  switch (s) {
    case 'running': return '工作中'
    case 'stalled': return '可能卡住'
    case 'success': return '已完成'
    case 'failed': return '失败'
    case 'timeout': return '超时'
    case 'cancelled': return '已取消'
    default: return '准备中'
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
}

/** 把后端 JSONL 事件还原为 InnerBlock[] */
function eventsToInnerBlocks(events: any[]): { blocks: InnerBlock[]; finalMessage: string } {
  const out: InnerBlock[] = []
  let final = ''
  for (const ev of events) {
    const t = ev?.type
    if (t === 'reasoning' || t === 'reasoning_text') {
      const delta = String(ev.text || ev.content || ev.delta || '')
      if (!delta) continue
      const last = out[out.length - 1]
      if (last && last.type === 'text' && last.phase === 'work') {
        // reasoning_text 是聚合后的整段；reasoning 是 delta。统一按追加处理。
        if (t === 'reasoning_text') {
          last.text = delta
        } else {
          last.text = (last.text || '') + delta
        }
      } else {
        out.push({ type: 'text', phase: 'work', text: delta })
      }
    } else if (t === 'assistant_text' || t === 'content') {
      const delta = String(ev.text || ev.content || ev.delta || '')
      if (!delta) continue
      const last = out[out.length - 1]
      if (last && last.type === 'text' && last.phase === 'answer') {
        last.text = (last.text || '') + delta
      } else {
        out.push({ type: 'text', phase: 'answer', text: delta })
      }
    } else if (t === 'tool_call') {
      const toolName = String(ev.tool_name || ev.name || 'unknown')
      if (toolName === 'report_to_main') {
        const msg = ev.args?.message || ev.args?.result || ''
        if (msg) final = String(msg)
      }
      out.push({
        type: 'tool',
        tool_name: toolName,
        tool_call_id: ev.tool_call_id || ev.id || '',
        status: ev.status || 'running',
        args: ev.args,
        result: '',
        error: '',
      })
    } else if (t === 'tool_result') {
      const tcId = String(ev.tool_call_id || ev.id || '')
      for (let i = out.length - 1; i >= 0; i--) {
        const b = out[i]
        if (b.type === 'tool' && b.tool_call_id === tcId) {
          b.status = ev.status || 'completed'
          b.result = typeof ev.result === 'string'
            ? ev.result
            : typeof ev.output === 'string'
              ? ev.output
              : JSON.stringify(ev.result || ev.output || '')
          b.error = ev.error || ''
          break
        }
      }
    }
  }
  return { blocks: out, finalMessage: final }
}

/** 加载日志（首次进入时调用） */
async function loadLog() {
  const path = subagentMeta.value.log_path
  if (!path) return
  loadingLog.value = true
  try {
    const url = `${API_BASE}/api/subagents/log?path=${encodeURIComponent(path)}`
    const resp = await fetch(url)
    if (!resp.ok) {
      console.warn('[SubagentChatPanel] 加载日志失败', resp.status)
      return
    }
    const data = await resp.json()
    const events = Array.isArray(data?.events) ? data.events : []
    const parsed = eventsToInnerBlocks(events)
    // 全量覆盖：日志是权威来源，确保重新打开能看到完整历史
    if (parsed.blocks.length > 0) {
      blocks.value = parsed.blocks
    }
    if (parsed.finalMessage) {
      finalMessage.value = parsed.finalMessage
    }
    scrollToBottom()
  } catch (err) {
    console.warn('[SubagentChatPanel] 读取日志异常', err)
  } finally {
    loadingLog.value = false
  }
}

/** 实时 SSE 事件处理（由 ChatPage 中转） */
function handleSubagentEvent(evt: CustomEvent) {
  const detail = evt.detail || {}
  const evType: string = detail.eventType || ''
  const data = detail.data || {}
  const evTaskId = String(data.task_id || '')

  // 还没锁定真实 task_id 时，用 subagent name 匹配 subagent_event 来锁定
  if (!lockedTaskId.value && evType === 'subagent_event') {
    const metaName = subagentMeta.value.subagent || ''
    const dataName = String(data.subagent || '')
    // 名字非空且匹配，或者当前 meta 没有名字（首次）都接受
    if (dataName && (metaName === dataName || !metaName)) {
      lockedTaskId.value = evTaskId
    }
  }

  // 用 actualTaskId 匹配；锁定后用真实 task_id，锁定前用 props.taskId
  if (evTaskId !== actualTaskId.value) return

  if (evType === 'subagent_event') {
    // 状态进度更新
    subagentMeta.value = {
      ...subagentMeta.value,
      task_id: evTaskId || subagentMeta.value.task_id,
      subagent: data.subagent || subagentMeta.value.subagent,
      task: data.task || subagentMeta.value.task,
      status: data.status || subagentMeta.value.status,
      round: data.round ?? subagentMeta.value.round,
      last_event: data.last_event || subagentMeta.value.last_event,
      elapsed_ms: data.elapsed_ms ?? subagentMeta.value.elapsed_ms,
      log_path: data.log_path || subagentMeta.value.log_path,
    }
    // 若 log_path 首次到达且 blocks 为空，尝试加载历史
    if (data.log_path && blocks.value.length === 0 && !loadingLog.value) {
      loadLog()
    }
  } else if (evType === 'subagent_reasoning') {
    const delta = String(data.delta || '')
    if (!delta) return
    const last = blocks.value[blocks.value.length - 1]
    if (last && last.type === 'text' && last.phase === 'work') {
      last.text = (last.text || '') + delta
    } else {
      blocks.value.push({ type: 'text', phase: 'work', text: delta })
    }
    scrollToBottom()
  } else if (evType === 'subagent_content') {
    const delta = String(data.delta || '')
    if (!delta) return
    const last = blocks.value[blocks.value.length - 1]
    if (last && last.type === 'text' && last.phase === 'answer') {
      last.text = (last.text || '') + delta
    } else {
      blocks.value.push({ type: 'text', phase: 'answer', text: delta })
    }
    scrollToBottom()
  } else if (evType === 'subagent_tool_call') {
    blocks.value.push({
      type: 'tool',
      tool_name: data.tool_name || 'unknown',
      tool_call_id: data.tool_call_id || '',
      status: data.status || 'running',
      args: data.args,
      result: '',
      error: '',
    })
    scrollToBottom()
  } else if (evType === 'subagent_tool_result') {
    const tcId = String(data.tool_call_id || '')
    for (let i = blocks.value.length - 1; i >= 0; i--) {
      const b = blocks.value[i]
      if (b.type === 'tool' && b.tool_call_id === tcId) {
        b.status = data.status || 'completed'
        b.result = typeof data.output === 'string' ? data.output : JSON.stringify(data.output || '')
        b.error = data.error || ''
        break
      }
    }
    if (data.tool_name === 'report_to_main' && data.status === 'completed') {
      finalMessage.value = typeof data.output === 'string' ? data.output : ''
    }
    scrollToBottom()
  }
}

onMounted(() => {
  window.addEventListener('aries:subagent-stream', handleSubagentEvent as EventListener)
  // 如果 props.taskId 看起来是真实 task_id（非空且不等于 tool_call_id 形态），
  // 直接锁定；否则等待 subagent_event 锁定
  if (props.initial?.status === 'success' || props.initial?.status === 'failed'
      || props.initial?.status === 'timeout' || props.initial?.status === 'cancelled') {
    // 已完成状态：当前 props.taskId 一定是真实 task_id
    lockedTaskId.value = props.taskId
  }
  // 只要有 log_path 就尝试加载历史（即使有 inner_blocks 也用日志覆盖，确保完整）
  if (subagentMeta.value.log_path) {
    loadLog()
  } else {
    scrollToBottom()
  }
})

onUnmounted(() => {
  window.removeEventListener('aries:subagent-stream', handleSubagentEvent as EventListener)
})

// 切换不同 taskId 时重新加载
watch(() => props.taskId, (newId, oldId) => {
  if (newId === oldId) return
  lockedTaskId.value = ''
  blocks.value = props.initial?.inner_blocks ? [...props.initial.inner_blocks] : []
  finalMessage.value = props.initial?.final_message || ''
  subagentMeta.value = {
    task_id: newId,
    subagent: props.initial?.subagent,
    task: props.initial?.task,
    status: props.initial?.status,
    round: props.initial?.round,
    last_event: props.initial?.last_event,
    elapsed_ms: props.initial?.elapsed_ms,
    log_path: props.initial?.log_path,
  }
  if (blocks.value.length === 0 && subagentMeta.value.log_path) {
    loadLog()
  }
})
</script>

<style scoped>
.side-chat-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
  padding: 12px 12px 8px;
}

/* 顶部工具栏 */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 4px 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1;
}
.title-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.title-status-pill {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
}
.pill-running { background: rgba(74, 144, 217, 0.12); color: #4a90d9; }
.pill-stalled { background: rgba(255, 149, 0, 0.12); color: #ff9500; }
.pill-success { background: rgba(52, 199, 89, 0.12); color: #34c759; }
.pill-failed, .pill-timeout, .pill-cancelled { background: rgba(255, 59, 48, 0.12); color: #ff3b30; }
.pill-pending { background: rgba(128, 128, 128, 0.15); color: #888; }
.title-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.action-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text);
}
.action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.danger-btn {
  color: #ff3b30;
  border-color: rgba(255, 59, 48, 0.3);
}
.danger-btn:hover {
  background: rgba(255, 59, 48, 0.08);
  color: #ff3b30;
}

/* 任务行 */
.panel-task {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 4px 8px;
  border-bottom: 1px dashed var(--border);
  margin-bottom: 8px;
}
.task-label {
  color: var(--text-muted);
  flex-shrink: 0;
  font-weight: 500;
}
.task-text {
  flex: 1;
  word-break: break-word;
}

/* 消息列表 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0 12px;
  min-height: 0;
  scrollbar-width: none;
}
.chat-messages::-webkit-scrollbar { display: none; }

.msg-row {
  display: flex;
  box-sizing: border-box;
  width: 100%;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-row.assistant {
  justify-content: flex-start;
}

.msg-bubble {
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  box-sizing: border-box;
}
.user-bubble {
  max-width: 85%;
  padding: 10px 16px;
  background: #e8eaed;
  color: var(--text);
  white-space: pre-wrap;
}
.assistant-bubble {
  width: 100%;
  max-width: 100%;
  padding: 8px 0;
  background: transparent;
  border: none;
  color: var(--text);
}

/* 空状态提示 */
.chat-empty-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
  line-height: 1.8;
}
.chat-empty-hint p { margin: 0; }

/* 底部日志路径 */
.panel-footer {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 4px 0;
  border-top: 1px dashed var(--border);
  margin-top: 8px;
}
.footer-label { font-weight: 500; flex-shrink: 0; }
.footer-path {
  font-family: var(--font-mono, monospace);
  word-break: break-all;
}
</style>
