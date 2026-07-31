<template>
  <div class="chat-app">
    <ChatSidebar
      :style="sidebarOpen ? { width: sidebarWidth + 'px' } : {}"
      :sidebar-open="sidebarOpen"
      :sessions="sessions"
      :current-session-id="currentSessionId"
      :user="auth.user"
      :viewing-file-path="viewingFile?.file?.path || ''"
      @toggle-sidebar="sidebarOpen = !sidebarOpen"
      @create-new-chat="createNewChat"
      @select-session="selectSession"
      @open-search="searchOpen = true"
      @sessions-changed="reloadSessions"
      @session-deleted="handleSessionDeleted"
      @logout="handleLogout"
      @view-file="handleViewFile"
      @exit-file-view="handleExitFileView"
      @add-to-chat="handleAddToChat"
    />
    <div
      v-if="sidebarOpen"
      class="chat-resize-handle chat-resize-left"
      title="拖动调整侧边栏宽度"
      @mousedown.prevent="startResize('sidebar', $event)"
    />
    <ChatMain
      ref="chatMainRef"
      :has-active-chat="hasActiveChat"
      :current-session="currentSession"
      :current-messages="currentMessages"
      :sending="sending"
      :user="auth.user"
      :as-agent="activeAgentName"
      :highlight-message-id="focusMessageId"
      :selected-workspace="selectedWorkspace"
      @send-message="sendMessage"
      @stop-generation="stopGeneration"
      @create-new-chat="createNewChat"
      @sessions-changed="reloadSessions"
      @session-deleted="handleSessionDeleted"
      @update:selected-workspace="v => selectedWorkspace = v"
    />
    <div
      v-if="viewingFile"
      class="chat-resize-handle chat-resize-right"
      title="拖动调整文件查看器宽度"
      @mousedown.prevent="startResize('fileviewer', $event)"
    />
    <FileViewerPanel
      v-if="viewingFile"
      :style="{ width: fileViewerWidth + 'px' }"
      :workspace="viewingFile.workspace"
      :file="viewingFile.file"
      @back="handleExitFileView"
      @add-to-chat="handleAddToChat"
    />
    <SettingsModal v-if="settingsStore.settingsOpen" />
    <ChatSearchPalette
      v-model:open="searchOpen"
      :sessions="sessions"
      @select-result="handleSearchSelect"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import ChatSidebar from './ChatSidebar.vue'
import ChatMain from './ChatMain.vue'
import FileViewerPanel from './FileViewerPanel.vue'
import ChatSearchPalette from '../components/ChatSearchPalette.vue'
import SettingsModal from '../components/SettingsModal.vue'
import {
  applySubagentJsonlEvent,
  isTerminalSubagentStatus,
} from '../utils/subagentLogParser'
import './ChatPage.css'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const settingsStore = useSettingsStore()

const sidebarOpen = ref(true)
const sending = ref(false)
const searchOpen = ref(false)
const chatMainRef = ref(null)
const focusMessageId = ref('')
const abortController = ref(null)
// 面板宽度（可拖拽调整）
const sidebarWidth = ref(260)
const fileViewerWidth = ref(460)

function startResize(which, e) {
  const startX = e.clientX
  const startWidth = which === 'sidebar' ? sidebarWidth.value : fileViewerWidth.value
  const appEl = document.querySelector('.chat-app')
  appEl?.classList.add('is-resizing-panel')
  const onMove = (ev) => {
    if (which === 'sidebar') {
      sidebarWidth.value = Math.min(Math.max(startWidth + (ev.clientX - startX), 200), 480)
    } else {
      fileViewerWidth.value = Math.min(Math.max(startWidth - (ev.clientX - startX), 280), 800)
    }
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    appEl?.classList.remove('is-resizing-panel')
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function stopGeneration() {
  abortController.value?.abort()
}

/** 以指定子 Agent 身份对话（其 system prompt 作为主提示词） */
const activeAgentName = computed(() => {
  const a = route.query.agent
  return typeof a === 'string' && a.trim() ? a.trim() : ''
})

const sessions = ref([])
// 初始 session id 优先取路由参数，支持 /session/:sessionId 直达
const currentSessionId = ref(route.params.sessionId || null)
const currentMessages = ref([])
// 新建对话时使用的工作目录（default = 普通对话）
const selectedWorkspace = ref('default')

const hasActiveChat = computed(() => !!currentSessionId.value)

// 文件查看器状态：{ workspace, file } | null
const viewingFile = ref(null)

function handleViewFile({ workspace, file }) {
  viewingFile.value = { workspace, file }
}

function handleExitFileView() {
  viewingFile.value = null
}

function handleAddToChat(ref) {
  chatMainRef.value?.addFileRef(ref)
}

const currentSession = computed(() => sessions.value.find(s => s.id === currentSessionId.value) || null)

function handleLogout() {
  auth.logout()
  router.push('/login')
}

async function reloadSessions() {
  try {
    const res = await api.get('/api/chat/sessions')
    sessions.value = res.data
  } catch (err) {
    console.error('Failed to load sessions', err)
  }
}

function handleSessionDeleted(session) {
  if (currentSessionId.value === session.id) {
    createNewChat()
  }
}

// 新建对话：回到根路径（清除子 Agent 身份）
function createNewChat() {
  const needNav =
    currentSessionId.value !== null ||
    !!route.query.agent ||
    route.name !== 'chat'
  currentSessionId.value = null
  currentMessages.value = []
  focusMessageId.value = ''
  if (needNav) {
    router.push({ name: 'chat' })
  }
}

// 切换会话：URL 同步为 /session/:id（会话默认用主 Agent）
async function selectSession(s) {
  focusMessageId.value = ''
  if (currentSessionId.value !== s.id || route.query.agent) {
    currentSessionId.value = s.id
    currentMessages.value = []
    router.push({ name: 'chat-session', params: { sessionId: s.id } })
    await loadMessages(s.id)
  }
}

function syncFocusFromRoute() {
  const msg = route.query.msg
  focusMessageId.value = typeof msg === 'string' && msg ? msg : ''
}

async function handleSearchSelect(item) {
  if (!item?.session_id || !item?.message_id) return

  const sessionId = item.session_id
  const messageId = String(item.message_id)

  focusMessageId.value = messageId
  const routeQuery = { msg: messageId }

  if (currentSessionId.value !== sessionId) {
    currentSessionId.value = sessionId
    currentMessages.value = []
    await router.push({ name: 'chat-session', params: { sessionId }, query: routeQuery })
    await loadMessages(sessionId)
  } else if (currentMessages.value.length === 0) {
    await router.replace({ name: 'chat-session', params: { sessionId }, query: routeQuery })
    await loadMessages(sessionId)
  } else {
    await router.replace({ name: 'chat-session', params: { sessionId }, query: routeQuery })
  }

  await nextTick()
  chatMainRef.value?.scrollToMessage(messageId)
}

// 将后端返回的 JSONL 事件列表转换为前端 blocks 数组（按事件顺序）
function eventsToBlocks(events) {
  if (!events || !Array.isArray(events)) return []
  const blocks = []
  for (const ev of events) {
    switch (ev.type) {
      case 'reasoning_text': {
        const last = blocks[blocks.length - 1]
        if (last && last.type === 'reasoning') {
          last.text += ev.text || ''
        } else {
          blocks.push({ type: 'reasoning', text: ev.text || '' })
        }
        break
      }
      case 'assistant_text': {
        const last = blocks[blocks.length - 1]
        if (last && last.type === 'text') {
          last.text += ev.text || ''
        } else {
          blocks.push({ type: 'text', text: ev.text || '' })
        }
        break
      }
      case 'tool_call':
        blocks.push({
          type: 'tool',
          toolCallId: ev.tool_call_id || `tc-${blocks.length}`,
          toolName: ev.tool_name || 'tool',
          args: ev.args || {},
          status: 'running',
          result: '',
          subagent: ev.tool_name === 'delegate_to_subagent'
            ? {
                subagent: ev.args?.subagent_name || '',
                task: ev.args?.task || '',
                status: 'running',
                inner_blocks: [],
              }
            : undefined,
        })
        break
      case 'tool_result': {
        const block = blocks.find(
          b => b.type === 'tool' && b.toolCallId === ev.tool_call_id
        )
        if (block) {
          block.result = ev.result || ev.error || ''
          block.status = ev.error ? 'error' : 'completed'
          if (block.toolName === 'delegate_to_subagent') {
            block.subagent = {
              ...(block.subagent || {}),
              status: ev.error ? 'failed' : 'success',
              final_message: String(ev.result || '').slice(0, 2000),
              error: ev.error || '',
            }
          }
        }
        break
      }
      case 'sub_agent': {
        // 主会话 JSONL 里的子 agent 汇总块：挂到对应 tool 块上
        let block = blocks.find(
          b => b.type === 'tool' && b.toolCallId === ev.tool_call_id
        )
        if (!block) {
          block = {
            type: 'tool',
            toolCallId: ev.tool_call_id || `sa-${blocks.length}`,
            toolName: 'delegate_to_subagent',
            args: {
              subagent_name: ev.subagent || '',
              task: ev.task || '',
            },
            status: ev.status === 'success' ? 'completed' : (ev.status || 'completed'),
            result: ev.final_output || ev.error || '',
          }
          blocks.push(block)
        }
        block.subagent = {
          ...(block.subagent || {}),
          task_id: block.subagent?.task_id,
          subagent: ev.subagent || block.subagent?.subagent || '',
          task: ev.task || block.subagent?.task || '',
          status: ev.status || block.subagent?.status || 'success',
          log_path: ev.log_path || '',
          final_message: ev.final_output || '',
          error: ev.error || '',
          elapsed_ms: ev.duration_ms || 0,
          inner_blocks: block.subagent?.inner_blocks || [],
        }
        break
      }
      default:
        break
    }
  }
  return blocks
}

function findDelegateBlock(assistantMsg, opts = {}) {
  const blocks = assistantMsg?.blocks || []
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b.type !== 'tool' || b.toolName !== 'delegate_to_subagent') continue
    if (opts.taskId && b.subagent?.task_id === opts.taskId) return b
    if (opts.toolCallId && b.toolCallId === opts.toolCallId) return b
    if (opts.logPath && b.subagent?.log_path === opts.logPath) return b
    if (
      opts.subagentName
      && !b.subagent?.task_id
      && (b.subagent?.subagent === opts.subagentName || b.args?.subagent_name === opts.subagentName)
    ) {
      return b
    }
  }
  return null
}

function applySubagentLogEventToBlock(block, event) {
  if (!block.subagent) block.subagent = { inner_blocks: [] }
  if (!block.subagent.inner_blocks) block.subagent.inner_blocks = []
  const applied = applySubagentJsonlEvent(block.subagent.inner_blocks, event)
  block.subagent.inner_blocks = applied.blocks
  if (applied.finalMessage) {
    block.subagent.final_message = applied.finalMessage
  }
}

async function loadMessages(sessionId) {
  try {
    const res = await api.get(`/api/chat/sessions/${sessionId}/messages`)
    currentMessages.value = res.data.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content || '',
      images: msg.image_urls?.length ? msg.image_urls : undefined,
      reasoning: msg.reasoning_content || '',
      tokenUsage: msg.token_usage || null,
      model: msg.model || '',
      durationMs: msg.duration_ms || 0,
      isLoading: false,
      // 历史消息按事件顺序重建 blocks
      blocks: msg.role === 'assistant' ? eventsToBlocks(msg.events) : [],
    }))
  } catch (err) {
    console.error('Failed to load messages', err)
  }
}

// 监听路由变化（浏览器前进/后退或直接改 URL）
watch(() => route.params.sessionId, async (newId, oldId) => {
  const id = newId || null
  if (id === currentSessionId.value) return
  currentSessionId.value = id
  currentMessages.value = []
  syncFocusFromRoute()
  if (id) await loadMessages(id)
}, { immediate: false })

watch(() => route.query.msg, () => {
  syncFocusFromRoute()
  if (focusMessageId.value && currentMessages.value.length) {
    nextTick(() => chatMainRef.value?.scrollToMessage(focusMessageId.value))
  }
})

onMounted(async () => {
  await reloadSessions()
  // 直达 /session/:id 时加载对应消息
  syncFocusFromRoute()
  if (currentSessionId.value) {
    await loadMessages(currentSessionId.value)
  }
})

async function sendMessage(payload) {
  const content = typeof payload === 'string' ? payload : (payload?.content || '')
  const images = typeof payload === 'string' ? [] : (payload?.images || [])
  const displayContent = content || (images.length > 1 ? `[${images.length} 张图片]` : '[图片]')

  // 如果没有 session，先在前端创建一个占位
  if (!currentSessionId.value) {
    const tempId = `sess-${Date.now()}`
    const newSession = {
      id: tempId,
      title: displayContent.length > 20 ? displayContent.slice(0, 20) + '...' : displayContent,
      is_pinned: false,
      workspace_dir: selectedWorkspace.value,
      created_at: new Date().toISOString(),
    }
    sessions.value.unshift(newSession)
    currentSessionId.value = tempId
    // 同步 URL（replace，避免新建占位 session 污染历史栈）
    router.replace({
      name: 'chat-session',
      params: { sessionId: tempId },
      query: activeAgentName.value ? { agent: activeAgentName.value } : {},
    })
  }

  const userMsg = reactive({
    id: `msg-${Date.now()}`,
    role: 'user',
    content,
    images: images.length ? [...images] : undefined,
    isLoading: false,
  })
  currentMessages.value.push(userMsg)

  const assistantMsg = reactive({
    id: `msg-${Date.now() + 1}`,
    role: 'assistant',
    content: '',
    reasoning: '',
    tokenUsage: null,
    model: '',
    durationMs: 0,
    contextInfo: null,
    toolCalls: [],
    isLoading: true,
    blocks: [], // 按 SSE 事件顺序累积的渲染块
  })
  currentMessages.value.push(assistantMsg)

  sending.value = true
  abortController.value = new AbortController()
  try {
    const token = localStorage.getItem('token')
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        session_id: currentSessionId.value,
        message: content,
        workspace_dir: selectedWorkspace.value,
        ...(images.length ? { images } : {}),
        ...(activeAgentName.value ? { agent_name: activeAgentName.value } : {}),
      }),
      signal: abortController.value.signal,
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || errData.error || `HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') continue
        try {
          const event = JSON.parse(data)

          switch (event.type) {
            case 'session':
              // session_id（后端可能创建新 session）
              if (event.session_id && currentSessionId.value !== event.session_id) {
                currentSessionId.value = event.session_id
                // 后端确认的真实 session id，替换占位 id
                router.replace({ name: 'chat-session', params: { sessionId: event.session_id } })
                api.get('/api/chat/sessions').then(res => {
                  sessions.value = res.data
                }).catch(() => {})
              }
              break

            case 'reasoning_text':
              // 思考过程（token 级流式）——追加到当前 reasoning 块或新建块
              assistantMsg.reasoning += event.text
              {
                const blocks = assistantMsg.blocks
                const last = blocks[blocks.length - 1]
                if (last && last.type === 'reasoning') {
                  last.text += event.text
                } else {
                  blocks.push({ type: 'reasoning', text: event.text })
                }
              }
              break

            case 'assistant_text':
              // 回复内容（token 级流式）——追加到当前 text 块或新建块
              assistantMsg.content += event.text
              {
                const blocks = assistantMsg.blocks
                const last = blocks[blocks.length - 1]
                if (last && last.type === 'text') {
                  last.text += event.text
                } else {
                  blocks.push({ type: 'text', text: event.text })
                }
              }
              break

            case 'tool_call':
              // 工具调用开始——按事件顺序插入新 tool 块
              if (!assistantMsg.toolCalls) assistantMsg.toolCalls = []
              assistantMsg.toolCalls.push({
                tool_call_id: event.tool_call_id,
                tool_name: event.tool_name,
                args: event.args,
                status: 'running',
                result: '',
              })
              assistantMsg.blocks.push({
                type: 'tool',
                toolCallId: event.tool_call_id,
                toolName: event.tool_name,
                args: event.args,
                status: 'running',
                result: '',
                subagent: event.tool_name === 'delegate_to_subagent'
                  ? {
                      subagent: event.args?.subagent_name || '',
                      task: event.args?.task || '',
                      status: 'running',
                      inner_blocks: [],
                    }
                  : undefined,
              })
              break

            case 'tool_result':
              // 工具调用结果——同步更新 toolCalls 和 blocks 中对应块
              if (assistantMsg.toolCalls) {
                const tc = assistantMsg.toolCalls.find(t => t.tool_call_id === event.tool_call_id)
                if (tc) {
                  tc.result = event.result || event.output || event.error || ''
                  tc.status = event.error ? 'error' : 'completed'
                }
              }
              {
                const block = assistantMsg.blocks.find(
                  b => b.type === 'tool' && b.toolCallId === event.tool_call_id
                )
                if (block) {
                  block.result = event.result || event.output || event.error || ''
                  block.status = event.error ? 'error' : 'completed'
                  if (block.toolName === 'delegate_to_subagent') {
                    const st = event.status || (event.error ? 'failed' : 'success')
                    block.subagent = {
                      ...(block.subagent || {}),
                      status: st,
                      final_message: block.subagent?.final_message
                        || String(event.output || event.result || '').slice(0, 2000),
                      error: event.error || block.subagent?.error || '',
                    }
                  }
                }
              }
              break

            case 'sub_agent': {
              const block = findDelegateBlock(assistantMsg, {
                toolCallId: event.tool_call_id,
                subagentName: event.subagent,
              }) || (() => {
                const b = {
                  type: 'tool',
                  toolCallId: event.tool_call_id || `sa-${assistantMsg.blocks.length}`,
                  toolName: 'delegate_to_subagent',
                  args: {
                    subagent_name: event.subagent || '',
                    task: event.task || '',
                  },
                  status: 'running',
                  result: '',
                  subagent: { inner_blocks: [] },
                }
                assistantMsg.blocks.push(b)
                return b
              })()
              block.subagent = {
                ...(block.subagent || {}),
                subagent: event.subagent || block.subagent?.subagent || '',
                task: event.task || block.subagent?.task || '',
                status: event.status || block.subagent?.status || 'running',
                log_path: event.log_path || block.subagent?.log_path || '',
                final_message: event.final_output || block.subagent?.final_message || '',
                error: event.error || block.subagent?.error || '',
                elapsed_ms: event.duration_ms || block.subagent?.elapsed_ms || 0,
                inner_blocks: block.subagent?.inner_blocks || [],
              }
              if (event.status === 'success' || event.status === 'failed' || event.status === 'timeout' || event.status === 'cancelled') {
                block.status = event.status === 'success' ? 'completed' : 'error'
                block.result = event.final_output || event.error || block.result
              }
              break
            }

            case 'subagent_event': {
              const d = event.data || event
              const block = findDelegateBlock(assistantMsg, {
                taskId: d.task_id,
                toolCallId: event.tool_call_id || d.tool_call_id,
                subagentName: d.subagent,
              })
              if (block) {
                block.subagent = {
                  ...(block.subagent || {}),
                  task_id: d.task_id || block.subagent?.task_id,
                  subagent: d.subagent || block.subagent?.subagent,
                  task: d.task || block.subagent?.task,
                  status: d.status || block.subagent?.status || 'running',
                  log_path: d.log_path || block.subagent?.log_path || '',
                  elapsed_ms: d.elapsed_ms || block.subagent?.elapsed_ms || 0,
                  final_message: d.final_message || block.subagent?.final_message || '',
                  error: d.error || block.subagent?.error || '',
                  inner_blocks: block.subagent?.inner_blocks || [],
                }
              }
              break
            }

            case 'subagent_log_started': {
              const d = event.data || event
              const block = findDelegateBlock(assistantMsg, {
                taskId: d.task_id,
                toolCallId: d.tool_call_id,
                logPath: d.jsonl_path,
                subagentName: d.subagent,
              })
              if (block) {
                block.subagent = {
                  ...(block.subagent || {}),
                  task_id: d.task_id || block.subagent?.task_id,
                  log_path: d.jsonl_path || block.subagent?.log_path,
                  subagent: d.subagent || block.subagent?.subagent || block.args?.subagent_name,
                  task: block.subagent?.task || block.args?.task || '',
                  status: 'running',
                  inner_blocks: block.subagent?.inner_blocks || [],
                }
              }
              break
            }

            case 'subagent_log_event': {
              const d = event.data || event
              const block = findDelegateBlock(assistantMsg, {
                taskId: d.task_id,
                toolCallId: d.tool_call_id,
                logPath: d.jsonl_path,
                subagentName: d.subagent,
              })
              if (block && !isTerminalSubagentStatus(block.subagent?.status)) {
                if (d.subagent || d.task_id || d.jsonl_path) {
                  block.subagent = {
                    ...(block.subagent || {}),
                    task_id: d.task_id || block.subagent?.task_id,
                    log_path: d.jsonl_path || block.subagent?.log_path,
                    subagent: d.subagent || block.subagent?.subagent,
                    status: block.subagent?.status || 'running',
                    inner_blocks: block.subagent?.inner_blocks || [],
                  }
                }
                if (d.event) applySubagentLogEventToBlock(block, d.event)
              }
              break
            }

            case 'subagent_log_complete': {
              const d = event.data || event
              const block = findDelegateBlock(assistantMsg, {
                taskId: d.task_id,
                toolCallId: d.tool_call_id,
                logPath: d.jsonl_path,
              })
              if (block?.subagent) {
                const st = block.subagent.status
                if (!st || st === 'running' || st === 'pending' || st === 'stalled') {
                  block.subagent.status = 'success'
                }
              }
              break
            }

            case 'token_usage':
              // token 使用信息（含 cached_tokens 等）
              assistantMsg.tokenUsage = event.token_usage
              assistantMsg.model = event.model
              break

            case 'context_info':
              // 上下文 token 估算（预检信息）
              assistantMsg.contextInfo = event.context_info
              break

            case 'error':
              assistantMsg.content += `\n[错误: ${event.error}]`
              {
                const blocks = assistantMsg.blocks
                const last = blocks[blocks.length - 1]
                const errText = `\n[错误: ${event.error}]`
                if (last && last.type === 'text') {
                  last.text += errText
                } else {
                  blocks.push({ type: 'text', text: errText })
                }
              }
              break

            case 'finalized':
              // 记录后端返回的运行时长
              if (event.duration_ms) {
                assistantMsg.durationMs = event.duration_ms
              }
              break
          }
        } catch {
          // 忽略解析失败的行
        }
      }
    }

    if (!assistantMsg.content && !assistantMsg.reasoning) {
      assistantMsg.content = '（未收到回复内容）'
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      // 用户主动停止：保留已生成内容，追加停止标记
      assistantMsg.content = (assistantMsg.content ? assistantMsg.content + '\n\n' : '') + '（已停止）'
    } else {
      assistantMsg.content = err.message || '请求失败，请检查模型配置或网络'
    }
  } finally {
    assistantMsg.isLoading = false
    sending.value = false
    abortController.value = null
  }
}
</script>
