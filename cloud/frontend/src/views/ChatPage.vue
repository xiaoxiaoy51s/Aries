<template>
  <div class="chat-app">
    <ChatSidebar
      :sidebar-open="sidebarOpen"
      :sessions="sessions"
      :current-session-id="currentSessionId"
      :user="auth.user"
      @toggle-sidebar="sidebarOpen = !sidebarOpen"
      @create-new-chat="createNewChat"
      @select-session="selectSession"
      @logout="handleLogout"
    />
    <ChatMain
      :has-active-chat="hasActiveChat"
      :current-session="currentSession"
      :current-messages="currentMessages"
      :sending="sending"
      :user="auth.user"
      @send-message="sendMessage"
      @create-new-chat="createNewChat"
    />
    <SettingsModal v-if="settingsStore.settingsOpen" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import ChatSidebar from './ChatSidebar.vue'
import ChatMain from './ChatMain.vue'
import SettingsModal from '../components/SettingsModal.vue'
import './ChatPage.css'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const settingsStore = useSettingsStore()

const sidebarOpen = ref(true)
const sending = ref(false)

const sessions = ref([])
// 初始 session id 优先取路由参数，支持 /session/:sessionId 直达
const currentSessionId = ref(route.params.sessionId || null)
const currentMessages = ref([])

const hasActiveChat = computed(() => !!currentSessionId.value)
const currentSession = computed(() => sessions.value.find(s => s.id === currentSessionId.value) || null)

function handleLogout() {
  auth.logout()
  router.push('/login')
}

// 新建对话：回到根路径
function createNewChat() {
  if (currentSessionId.value !== null) {
    currentSessionId.value = null
    currentMessages.value = []
    router.push({ name: 'chat' })
  }
}

// 切换会话：URL 同步为 /session/:id
async function selectSession(s) {
  if (currentSessionId.value !== s.id) {
    currentSessionId.value = s.id
    currentMessages.value = []
    router.push({ name: 'chat-session', params: { sessionId: s.id } })
    await loadMessages(s.id)
  }
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
        })
        break
      case 'tool_result': {
        const block = blocks.find(
          b => b.type === 'tool' && b.toolCallId === ev.tool_call_id
        )
        if (block) {
          block.result = ev.result || ev.error || ''
          block.status = ev.error ? 'error' : 'completed'
        }
        break
      }
      default:
        // 忽略 token_usage / finalized / user_message 等非渲染事件
        break
    }
  }
  return blocks
}

async function loadMessages(sessionId) {
  try {
    const res = await api.get(`/api/chat/sessions/${sessionId}/messages`)
    currentMessages.value = res.data.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content || '',
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
  if (id) await loadMessages(id)
}, { immediate: false })

onMounted(async () => {
  try {
    const res = await api.get('/api/chat/sessions')
    sessions.value = res.data
  } catch (err) {
    console.error('Failed to load sessions', err)
  }
  // 直达 /session/:id 时加载对应消息
  if (currentSessionId.value) {
    await loadMessages(currentSessionId.value)
  }
})

async function sendMessage(content) {
  // 如果没有 session，先在前端创建一个占位
  if (!currentSessionId.value) {
    const tempId = `sess-${Date.now()}`
    const newSession = {
      id: tempId,
      title: content.length > 20 ? content.slice(0, 20) + '...' : content,
      is_pinned: false,
      created_at: new Date().toISOString(),
    }
    sessions.value.unshift(newSession)
    currentSessionId.value = tempId
    // 同步 URL（replace，避免新建占位 session 污染历史栈）
    router.replace({ name: 'chat-session', params: { sessionId: tempId } })
  }

  const userMsg = reactive({ id: `msg-${Date.now()}`, role: 'user', content, isLoading: false })
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
      }),
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
              })
              break

            case 'tool_result':
              // 工具调用结果——同步更新 toolCalls 和 blocks 中对应块
              if (assistantMsg.toolCalls) {
                const tc = assistantMsg.toolCalls.find(t => t.tool_call_id === event.tool_call_id)
                if (tc) {
                  tc.result = event.result || event.error || ''
                  tc.status = event.error ? 'error' : 'completed'
                }
              }
              {
                const block = assistantMsg.blocks.find(
                  b => b.type === 'tool' && b.toolCallId === event.tool_call_id
                )
                if (block) {
                  block.result = event.result || event.error || ''
                  block.status = event.error ? 'error' : 'completed'
                }
              }
              break

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
    assistantMsg.content = err.message || '请求失败，请检查模型配置或网络'
  } finally {
    assistantMsg.isLoading = false
    sending.value = false
  }
}
</script>
