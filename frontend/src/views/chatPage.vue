<template>
  <section id="chatPage" class="page">
    <!-- 右侧面板开关按钮 -->
    <button
      type="button"
      class="right-panel-toggle"
      :title="rightPanelVisible ? '收起面板' : '展开面板'"
      :aria-label="rightPanelVisible ? '收起面板' : '展开面板'"
      @click="rightPanelVisible = !rightPanelVisible"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path v-if="rightPanelVisible" d="M15 3v18"/>
        <path v-else d="M15 3v18M15 9h6"/>
      </svg>
    </button>

    <!-- 任务清单按钮 -->
    <TodoButton class="chat-todo-button" />

    <div class="chat-content">
    <!-- 空状态 -->
    <div v-if="!hasActiveChat" class="chat-empty">
      <h1 class="welcome-title">我们要在 Aries 里构建什么？</h1>
      <ChatComposer
        ref="emptyComposerRef"
        v-model="inputMessage"
        v-model:attached-images="attachedImages"
        v-model:active-slash-command="activeSlashCommand"
        v-model:command-objective="commandObjective"
        v-model:plugin-menu-open="pluginMenuOpen"
        :is-sending="composerIsSending"
        v-model:selected-model="selectedModel"
        :model-list="modelStore.modelList"
        :can-send="canSend"
        :show-work-dir="true"
        :work-dir="workDir"
        :work-dir-label="workDirLabel"
        :work-dir-history="workDirHistory"
        :context-usage-percent="contextUsagePercent"
        :context-usage-info="contextUsageBreakdown"
        :session-id="currentSessionId"
        :rows="3"
        @send="sendMessage"
        @stop="stopGeneration"
        @open-image-picker="openImagePicker"
        @pick-work-dir="pickWorkDir"
        @apply-work-dir="applyWorkDir"
        @toggle-side-chat="rightPanelVisible = !rightPanelVisible"
        @compact-done="onCompactDone"
      />
    </div>

    <!-- 对话中状态 -->
    <div v-else class="chat-active">
      <div
        class="chat-messages"
        ref="messagesContainer"
        @mousemove="markPointerActivity"
        @mousedown="markPointerActivity"
        @wheel.passive="markPointerActivity"
        @scroll="onMessagesScroll"
      >
        <div 
          v-for="(msg, index) in messages" 
          :key="index"
          class="msg-row"
          :class="msg.role"
        >
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="msg-bubble user-bubble">
            <UserMessageContent
              :content="msg.content"
              :slash-command="msg.slashCommand"
              :slash-body="msg.slashBody"
              :images="msg.images"
            />
          </div>
          
          <!-- 助手消息（支持 Markdown/LaTeX/思考/工具） -->
          <div v-else class="msg-bubble assistant-bubble">
            <AssistantMessage
              :content="msg.content"
              :reasoning="msg.reasoning || []"
              :tools="msg.tools || []"
              :blocks="msg.blocks || []"
              :artifacts="msg.artifacts || []"
              :is-loading="msg.isLoading"
              :text-color="textColor"
              :font-size="fontSize"
              :meta="msg.meta"
              :message-id="msg.messageId"
              :chat-session-id="currentSessionId || ''"
              @revert="(idx: number) => revertArtifact(index, idx)"
              @view-artifact="(idx: number) => viewArtifact(index, idx)"
            />
          </div>
        </div>
      </div>
      <ChatComposer
        ref="activeComposerRef"
        v-model="inputMessage"
        v-model:attached-images="attachedImages"
        v-model:active-slash-command="activeSlashCommand"
        v-model:command-objective="commandObjective"
        v-model:plugin-menu-open="pluginMenuOpen"
        :is-sending="composerIsSending"
        v-model:selected-model="selectedModel"
        :model-list="modelStore.modelList"
        :can-send="canSend"
        :show-work-dir="false"
        :work-dir="workDir"
        :work-dir-label="workDirLabel"
        :work-dir-history="workDirHistory"
        :context-usage-percent="contextUsagePercent"
        :context-usage-info="contextUsageBreakdown"
        :session-id="currentSessionId"
        :rows="2"
        is-bottom
        @send="sendMessage"
        @stop="stopGeneration"
        @open-image-picker="openImagePicker"
        @pick-work-dir="pickWorkDir"
        @apply-work-dir="applyWorkDir"
        @toggle-side-chat="rightPanelVisible = !rightPanelVisible"
        @compact-done="onCompactDone"
      >
        <DangerCommandConfirm
          v-if="pendingToolConfirmation"
          :description="confirmDescription"
          :command="pendingToolConfirmation.command"
          :countdown="confirmCountdown"
          @submit="onDangerConfirmSubmit"
          @skip="onToolCancel(pendingToolConfirmation.toolCallId)"
        />
      </ChatComposer>
    </div>
    </div>

    <!-- 右侧面板：控制台/浏览器/Git/Diff/临时对话 -->
    <RightPanel
      :visible="rightPanelVisible"
      :session-id="currentSessionId"
      :work-dir="workDir"
      :inline-diff="inlineDiffData"
      @close="rightPanelVisible = false"
    />

    <!-- 顶部 Toast 通知 -->
    <Transition name="toast">
      <div v-if="toastVisible" class="page-toast" :class="'toast-' + toastType">
        <span>{{ toastMessage }}</span>
      </div>
    </Transition>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useModelStore } from '@/stores/model'
 import { usePrivacyStore } from '@/stores/privacy'
import { stopChat, checkChatStatus, jsonToStreamEvent, type StreamEvent, startChat, startVision } from '@/api/chat'
import { confirmTool } from '@/api/git'
import { useWorkspaceStore } from '@/stores/workspace'
import { getSessionMessages, getSession, updateSessionMeta, getSessionContextUsage, getSessionBootstrap } from '@/api/sessions'
import { listWorkDirs, createWorkDir } from '@/api/work_dirs'
import { selectDirectory } from '@/api/system'
import AssistantMessage from '@/components/AssistantMessage.vue'
import ChatComposer from '@/components/ChatComposer.vue'
import DangerCommandConfirm from '@/components/DangerCommandConfirm.vue'
import SlashComposerInput, { type ComposerImage } from '@/components/SlashComposerInput.vue'
import UserMessageContent from '@/components/UserMessageContent.vue'
import RightPanel from '@/components/workspace/RightPanel.vue'
import TodoButton from '@/components/TodoButton.vue'
import { parseSnapshotEventObjects } from '@/utils/snapshotParser'
import { normalizeRunMetadata, type RunMeta } from '@/utils/runMetadata'
import {
  bindStreamDuration,
  startStreamDuration,
  stopStreamDuration,
  clearSessionStreamDurations,
} from '@/utils/streamDurationStore'
import {
  markSessionWorking,
  markSessionIdle,
  isSessionWorking,
} from '@/utils/sessionWorkStore'
import {
  saveSessionSnapshot,
  loadSessionSnapshot,
  ensureSessionWs,
  pruneSessionWsKeep,
  closeSessionWs,
  closeAllSessionWs,
  setSessionWsHandler,
  buildWsKeepSet,
  type SessionChatSnapshot,
} from '@/utils/sessionChatPool'

interface SlashCommandDef {
  id: string
  label?: string
}

const props = defineProps<{
  sessionIdToLoad?: string | null
}>()

const emit = defineEmits<{
  sessionLoaded: []
}>()

const modelStore = useModelStore()
const privacyStore = usePrivacyStore()
const workspaceStore = useWorkspaceStore()

const inputMessage = ref('')
const attachedImages = ref<ComposerImage[]>([])
const pluginMenuOpen = ref(false)
const activeSlashCommand = ref<SlashCommandDef | null>(null)
const commandObjective = ref('')
const selectedModel = ref('')
const inlineDiffData = ref<{ path: string; original: string; modified: string; key: number } | null>(null)
const hasActiveChat = ref(false)
const isSending = ref(false)
const rightPanelVisible = ref(false)
const toastVisible = ref(false)
const toastMessage = ref('')
const toastType = ref<'info' | 'warning' | 'error'>('info')
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string, type: 'info' | 'warning' | 'error' = 'info', duration = 3000) {
  if (toastTimer) clearTimeout(toastTimer)
  toastMessage.value = message
  toastType.value = type
  toastVisible.value = true
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, duration)
}
const messagesContainer = ref<HTMLElement>()
const SCROLL_IDLE_MS = 5000
let lastPointerActivityAt = 0
let scrollIdleTimer: ReturnType<typeof setTimeout> | null = null
const emptyComposerRef = ref<InstanceType<typeof ChatComposer>>()
const activeComposerRef = ref<InstanceType<typeof ChatComposer>>()
const currentSessionId = ref<string | undefined>(undefined)
const contextUsagePercent = ref(0)
const contextUsageBreakdown = ref<import('@/api/sessions').ContextUsageInfo | null>(null)

// 当前 assistant message_id（用于把 log_event 路由到正确的消息）
let activeAssistantMessageId: number | null = null
let activeAssistantIdx: number | null = null
/** run_metadata 可能在 log_complete 之后到达，先缓存，完成时统一写入 */
const pendingRunMetaByMessageId = new Map<number, RunMeta>()

// WebSocket 由 sessionChatPool 管理（支持多 session 并行，见下方 ensureChatWsReady）

/**
 * 为 log_started 事件创建/定位 assistant placeholder
 * 若该 message_id 已在 messages 中（断线重连场景），复用并把 isLoading 置为 true
 */
function ensureLogPlaceholder(messageId: number, jsonlPath: string) {
  if (!currentSessionId.value) return
  // 先查找已存在的
  let idx = messages.value.findIndex(
    (m) => m.role === 'assistant' && m.messageId === messageId
  )
  if (idx < 0) {
    // 兜底：最后一条 assistant 消息
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        idx = i
        break
      }
    }
  }
  if (idx < 0) {
    // 没有 placeholder：新建
    messages.value.push({
      role: 'assistant',
      content: '',
      reasoning: [],
      tools: [],
      blocks: [],
      isLoading: true,
      messageId,
      messageSnapshotJson: jsonlPath || undefined,
    })
    idx = messages.value.length - 1
  } else {
    // 已存在：标记为 loading（断线重连场景）
    const m = messages.value[idx]
    m.isLoading = true
    m.messageId = messageId
    if (jsonlPath) m.messageSnapshotJson = jsonlPath
  }
  if (currentSessionId.value) {
    bindStreamDuration(currentSessionId.value, messageId)
    startStreamDuration(currentSessionId.value, messageId)
  }
  activeAssistantIdx = idx
  hasActiveChat.value = true
  isSending.value = true
  if (currentSessionId.value) {
    markSessionWorking(currentSessionId.value)
  }
  nextTick(() => scheduleScrollToBottom(true))
}

function applyMetaToMessage(messageId: number, meta: RunMeta): boolean {
  const idx = findAssistantMessageIndex(messageId)
  if (idx < 0) return false
  const msg = messages.value[idx]
  if (!msg || msg.role !== 'assistant') return false
  messages.value[idx] = { ...msg, meta }
  return true
}

function stashRunMetadata(messageId: number, raw: unknown) {
  if (!messageId) return
  const meta = normalizeRunMetadata(raw)
  if (!meta.model && !meta.duration_ms && !meta.token_usage) return
  pendingRunMetaByMessageId.set(messageId, meta)
  applyMetaToMessage(messageId, meta)
}

/**
 * 将后端 JSONL 事件应用到 UI（无需重新拉取 JSONL）
 */
function applyLogEvent(event: Record<string, any>, messageId: number, jsonlPath: string) {
  if (!currentSessionId.value) return
  const evtType = event.type

  if (evtType === 'run_metadata') {
    stashRunMetadata(messageId, event)
    return
  }
  if (evtType === 'log_complete') {
    completeLogMessage(messageId)
    return
  }

  if (activeAssistantIdx == null) {
    ensureLogPlaceholder(messageId, jsonlPath)
  }
  const idx = activeAssistantIdx
  if (idx == null) return
  const msg = messages.value[idx]
  if (!msg || msg.role !== 'assistant') return
  let streamEvt: StreamEvent | null = null

  switch (evtType) {
    case 'reasoning_text':
      streamEvt = { type: 'reasoning', data: String(event.text || '') }
      break
    case 'assistant_text':
      streamEvt = { type: 'content', data: String(event.text || '') }
      break
    case 'tool_call':
      streamEvt = {
        type: 'tool_call',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          args: event.args,
          session_id: event.session_id || '',
        },
      }
      break
    case 'tool_result':
      streamEvt = {
        type: 'tool_result',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          output: typeof event.result === 'string' ? event.result : (event.result?.output || ''),
          file_change: event.file_change,
          session_id: event.session_id || '',
        },
      }
      break
    case 'sub_agent':
      // 把 sub_agent 转换为 subagent_event 格式
      streamEvt = {
        type: 'subagent_event',
        data: {
          task_id: event.tool_call_id,
          subagent: event.subagent,
          task: event.task,
          status: event.status,
          log_path: event.log_path,
          round: event.rounds,
          elapsed_ms: event.duration_ms,
          final_message: event.final_output,
        },
      }
      break
    case 'error_event':
      streamEvt = { type: 'error', data: event.error_msg || event.error || '未知错误' }
      break
    case 'info_event':
      streamEvt = { type: 'hint', data: event.info_msg || '' }
      break
    default:
      return
  }
  if (!streamEvt) return
  applyStreamEvent(msg, streamEvt)
  messages.value[idx] = { ...msg }
  // 自动确认逻辑（与 runAssistantStream 一致）
  if (streamEvt.type === 'confirmation_required' && streamEvt.data) {
    const dangerTypes: string[] = streamEvt.data.danger_types || []
    const command = String(streamEvt.data.command || '').trim()
    const needsConfirm = privacyStore.needsConfirmation(dangerTypes, command)
    if (!needsConfirm) {
      const toolCallId = streamEvt.data.tool_call_id as string
      if (msg.blocks) {
        for (const block of msg.blocks) {
          if (block.type === 'tool' && block.tool_call_id === toolCallId && block.pending_confirmation) {
            block.pending_confirmation = false
            block.status = 'running'
          }
        }
      }
      messages.value[idx] = { ...msg }
      confirmTool(toolCallId, true).catch(() => {})
      autoConfirmedToolIds.add(toolCallId)
    }
  }
  if (streamEvt.type === 'todo_update' && streamEvt.data?.todos) {
    window.dispatchEvent(new CustomEvent('aries:todo-update', {
      detail: {
        sessionId: currentSessionId.value || '',
        todos: streamEvt.data.todos,
      },
    }))
  }
  nextTick(() => scheduleScrollToBottom())
}

function findAssistantMessageIndex(messageId: number): number {
  if (messageId > 0) {
    const byId = messages.value.findIndex(
      (m) => m.role === 'assistant' && m.messageId === messageId
    )
    if (byId >= 0) return byId
  }
  if (activeAssistantIdx != null && messages.value[activeAssistantIdx]?.role === 'assistant') {
    return activeAssistantIdx
  }
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant' && messages.value[i].isLoading) {
      return i
    }
  }
  return -1
}

/**
 * log_complete：标记当前 placeholder 完成，更新 isLoading / isSending
 */
function completeLogMessage(messageId: number) {
  const idx = findAssistantMessageIndex(messageId)
  const pendingMeta = messageId ? pendingRunMetaByMessageId.get(messageId) : undefined
  if (idx >= 0) {
    const m = messages.value[idx]
    if (m) {
      messages.value[idx] = {
        ...m,
        isLoading: false,
        meta: pendingMeta || m.meta,
      }
    }
  }
  if (messageId) pendingRunMetaByMessageId.delete(messageId)
  if (currentSessionId.value) {
    stopStreamDuration(currentSessionId.value, messageId)
  }

  if (!messageId || activeAssistantMessageId === messageId) {
    activeAssistantMessageId = null
    activeAssistantIdx = null
  }
  isSending.value = false
  flushPetStatus(petStatusPhase)
  clearPetStatus()
  syncSessionWorkingState()
  if (currentSessionId.value) {
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
  }
}

// 平台流式输出状态
let platformStreaming: boolean = false

// 确保平台 session 有一个 loading 的 assistant 占位消息
function ensurePlatformAssistantPlaceholder() {
  if (!currentSessionId.value || isSending.value) return
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant' && last.isLoading) return
  messages.value.push({
    role: 'assistant',
    content: '',
    reasoning: [],
    tools: [],
    blocks: [],
    isLoading: true,
  })
  hasActiveChat.value = true
  platformStreaming = true
  nextTick(() => scheduleScrollToBottom(true))
}

// 处理平台 AI 流式事件，实时更新 UI
function handlePlatformStreamEvent(rawEvent: Record<string, unknown>) {
  if (!currentSessionId.value) return
  const evt = jsonToStreamEvent(rawEvent)
  if (!evt) return

  // 确保有 assistant 占位消息
  ensurePlatformAssistantPlaceholder()
  const assistantMsg = messages.value[messages.value.length - 1]
  if (!assistantMsg || assistantMsg.role !== 'assistant') return
  const assistantIdx = messages.value.length - 1

  // 复用已有的 applyStreamEvent 逻辑
  applyStreamEvent(assistantMsg, evt)
  messages.value[assistantIdx] = { ...assistantMsg }
  nextTick(() => scheduleScrollToBottom())
}

// 加载当前 session 的新消息（完整重载，处理新增和更新）
async function loadNewMessages(force: boolean = false) {
  if (!currentSessionId.value) return
  // 用户正在从网页发送消息时跳过，避免打断流式输出
  if (isSending.value) return
  // 平台流式输出进行中时跳过，避免打断实时更新
  if (platformStreaming) return
  try {
    const data = await getSessionMessages(currentSessionId.value, 100)
    const allMsgs = data.messages || []

    // 记录之前最后一条助手消息的 id+content，用于判断是否需要更新
    const prevLast = messages.value[messages.value.length - 1]
    const prevLastKey = prevLast
      ? `${prevLast.role}:${prevLast.content?.length || 0}`
      : ''

    const dbLast = allMsgs[allMsgs.length - 1]
    const dbLastKey = dbLast
      ? `${dbLast.role}:${(dbLast.content || '').length}`
      : ''

    // 消息数量和最后一条内容都没变，且非强制更新，无需刷新
    if (!force && allMsgs.length === messages.value.length && prevLastKey === dbLastKey) return

    // 完整重载消息列表
    const msgs: ChatMessage[] = allMsgs.map((m: any) => {
      const base: ChatMessage = {
        role: m.role as 'user' | 'assistant',
        content: m.content || '',
        mode: m.mode || 'agent',
        reasoning: [],
        tools: [],
        blocks: [],
        isLoading: false,
        messageSnapshotJson: m.message_snapshot_json || undefined,
      }
      if (m.role === 'user') {
        Object.assign(base, enrichUserMessage(m.content || ''))
        base.images = parseStoredImagePaths(m.image_path)
      }
      return base
    })

    messages.value = msgs
    hasActiveChat.value = msgs.length > 0
    await nextTick()
    scheduleScrollToBottom(true)

    // 异步加载所有助手消息的快照
    for (let i = 0; i < allMsgs.length; i++) {
      if (allMsgs[i].role !== 'assistant') continue
      const messageId = allMsgs[i].id
      if (messageId) {
        await loadMessageSnapshot(messageId, i, allMsgs[i])
      }
    }
  } catch (err) {
    console.error('加载新消息失败', err)
  }
}

const canSend = computed(() => {
  return inputMessage.value.trim().length > 0 || attachedImages.value.length > 0
})

function openImagePicker() {
  const composer = hasActiveChat.value ? activeComposerRef.value : emptyComposerRef.value
  composer?.openFilePicker()
}

function clearAttachedImages() {
  attachedImages.value = []
  emptyComposerRef.value?.clearImages()
  activeComposerRef.value?.clearImages()
}

function parseStoredImagePaths(imagePath?: string | null): string[] {
  if (!imagePath) return []
  try {
    const parsed = JSON.parse(imagePath)
    return Array.isArray(parsed) ? parsed.filter(Boolean) : [imagePath]
  } catch {
    return [imagePath]
  }
}

function clearComposerCommand() {
  activeSlashCommand.value = null
  commandObjective.value = ''
}

interface ToolInfo {
  name: string
  status: string
  args?: Record<string, any>
  output: string
}

interface MessageBlock {
  type: 'tool' | 'text' | 'summary'
  phase?: 'work' | 'answer'
  text?: string
  tool_name?: string
  status?: string
  args?: Record<string, any>
  preview?: string
  result?: string
  error?: string
  started_at?: string
  ended_at?: string
  tool_call_id?: string
  session_id?: string
  auto_detached?: boolean
  pending_confirmation?: boolean
  danger_info?: string
  danger_types?: string[]
  // 子 Agent 委派的实时状态（仅 tool_name === 'delegate_to_subagent' 时使用）
  subagent?: {
    task_id?: string
    subagent?: string
    task?: string
    status?: string         // running | stalled | success | failed | timeout | cancelled
    round?: number
    last_event?: string
    elapsed_ms?: number
    log_path?: string
    // 子 Agent 的完整流式内容（展开工具块时显示）
    inner_blocks?: MessageBlock[]
    final_message?: string
  }
}

interface MessageMeta {
  model?: string
  duration_ms?: number
  token_usage?: {
    context?: { usage_percent?: number; estimated_tokens?: number; context_window?: number }
    api_usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }
  }
}

interface FileChangeArtifact {
  file_path: string
  operation: string  // "create" | "modify"
  previous_content: string
  new_content: string
  tool_name: string
  tool_call_id: string
  reverted?: boolean
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  slashCommand?: string
  slashBody?: string
  mode?: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  artifacts?: FileChangeArtifact[]
  isLoading?: boolean
  messageId?: number
  messageSnapshotJson?: string
  hasSnapshot?: boolean
  meta?: MessageMeta
}

function enrichUserMessage(content: string): Pick<ChatMessage, 'content' | 'slashCommand' | 'slashBody'> {
  const match = content.match(/^(\/[\w-]+)\s*(.*)$/s)
  if (match) {
    return {
      content,
      slashCommand: match[1],
      slashBody: match[2].trim(),
    }
  }
  return { content }
}

const messages = ref<ChatMessage[]>([])

/** 仅当前查看的 session 在流式时，输入框才显示加载/停止按钮 */
const composerIsSending = computed(() => {
  const sid = currentSessionId.value
  if (!sid || !isSessionWorking(sid)) return false
  return (
    isSending.value ||
    messages.value.some((m) => m.role === 'assistant' && m.isLoading)
  )
})

// 本会话所有子 Agent 委派记录（按 task_id 去重 upsert）
// 供 SubagentChatPanel 展示用，涵盖所有 assistant 消息里的 delegate_to_subagent 调用
interface SubagentRecord {
  task_id: string
  subagent?: string
  task?: string
  status?: string
  round?: number
  last_event?: string
  elapsed_ms?: number
  log_path?: string
  inner_blocks?: MessageBlock[]
  final_message?: string
  message_id?: number  // 来源 assistant 消息的 DB id，便于历史重建
}
const sessionSubagents = ref<SubagentRecord[]>([])

function captureSessionSnapshot(): SessionChatSnapshot {
  return {
    messages: JSON.parse(JSON.stringify(messages.value)),
    isSending: isSending.value,
    hasActiveChat: hasActiveChat.value,
    activeAssistantMessageId,
    activeAssistantIdx,
    sessionSubagents: JSON.parse(JSON.stringify(sessionSubagents.value)),
    platformStreaming,
  }
}

function restoreSessionSnapshot(snapshot: SessionChatSnapshot) {
  messages.value = snapshot.messages as ChatMessage[]
  isSending.value = snapshot.isSending
  hasActiveChat.value = snapshot.hasActiveChat
  activeAssistantMessageId = snapshot.activeAssistantMessageId
  activeAssistantIdx = snapshot.activeAssistantIdx
  sessionSubagents.value = snapshot.sessionSubagents as SubagentRecord[]
  platformStreaming = snapshot.platformStreaming
}

function persistCurrentSessionSnapshot(sessionId?: string) {
  const sid = sessionId || currentSessionId.value
  if (!sid) return
  saveSessionSnapshot(sid, captureSessionSnapshot())
}

function syncSessionWorkingState(sessionId?: string) {
  const sid = sessionId || currentSessionId.value
  if (!sid) return
  const working =
    isSending.value ||
    messages.value.some((m) => m.role === 'assistant' && m.isLoading)
  if (working) markSessionWorking(sid)
  else markSessionIdle(sid)
  persistCurrentSessionSnapshot(sid)
}

function syncSnapshotWorkingState(sessionId: string, snapshot: SessionChatSnapshot) {
  const working =
    snapshot.isSending ||
    (snapshot.messages as ChatMessage[]).some((m) => m.role === 'assistant' && m.isLoading)
  if (working) markSessionWorking(sessionId)
  else markSessionIdle(sessionId)
}

function getOrCreateSnapshot(sessionId: string): SessionChatSnapshot {
  return loadSessionSnapshot(sessionId) ?? {
    messages: [],
    isSending: false,
    hasActiveChat: false,
    activeAssistantMessageId: null,
    activeAssistantIdx: null,
    sessionSubagents: [],
    platformStreaming: false,
  }
}

function ensureLogPlaceholderSnapshot(
  snapshot: SessionChatSnapshot,
  sessionId: string,
  messageId: number,
  jsonlPath: string,
) {
  const msgs = snapshot.messages as ChatMessage[]
  let idx = msgs.findIndex((m) => m.role === 'assistant' && m.messageId === messageId)
  if (idx < 0) {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') {
        idx = i
        break
      }
    }
  }
  if (idx < 0) {
    msgs.push({
      role: 'assistant',
      content: '',
      reasoning: [],
      tools: [],
      blocks: [],
      isLoading: true,
      messageId,
      messageSnapshotJson: jsonlPath || undefined,
    })
    idx = msgs.length - 1
  } else {
    const m = msgs[idx]
    m.isLoading = true
    m.messageId = messageId
    if (jsonlPath) m.messageSnapshotJson = jsonlPath
  }
  bindStreamDuration(sessionId, messageId)
  startStreamDuration(sessionId, messageId)
  snapshot.activeAssistantIdx = idx
  snapshot.activeAssistantMessageId = messageId
  snapshot.hasActiveChat = true
  snapshot.isSending = true
  markSessionWorking(sessionId)
}

function findAssistantMessageIndexInSnapshot(snapshot: SessionChatSnapshot, messageId: number): number {
  const msgs = snapshot.messages as ChatMessage[]
  if (messageId > 0) {
    const byId = msgs.findIndex((m) => m.role === 'assistant' && m.messageId === messageId)
    if (byId >= 0) return byId
  }
  if (snapshot.activeAssistantIdx != null && msgs[snapshot.activeAssistantIdx]?.role === 'assistant') {
    return snapshot.activeAssistantIdx
  }
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'assistant' && msgs[i].isLoading) return i
  }
  return -1
}

function completeLogMessageSnapshot(
  snapshot: SessionChatSnapshot,
  sessionId: string,
  messageId: number,
) {
  const idx = findAssistantMessageIndexInSnapshot(snapshot, messageId)
  if (idx >= 0) {
    const m = snapshot.messages[idx] as ChatMessage
    snapshot.messages[idx] = { ...m, isLoading: false }
  }
  stopStreamDuration(sessionId, messageId)
  if (!messageId || snapshot.activeAssistantMessageId === messageId) {
    snapshot.activeAssistantMessageId = null
    snapshot.activeAssistantIdx = null
  }
  snapshot.isSending = false
}

function buildStreamEventFromLogEvent(
  event: Record<string, any>,
  messageId: number,
): StreamEvent | null | 'complete' {
  switch (event.type) {
    case 'reasoning_text':
      return { type: 'reasoning', data: String(event.text || '') }
    case 'assistant_text':
      return { type: 'content', data: String(event.text || '') }
    case 'tool_call':
      return {
        type: 'tool_call',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          args: event.args,
          session_id: event.session_id || '',
        },
      }
    case 'tool_result':
      return {
        type: 'tool_result',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          output: typeof event.result === 'string' ? event.result : (event.result?.output || ''),
          file_change: event.file_change,
          session_id: event.session_id || '',
        },
      }
    case 'run_metadata':
      return { type: 'meta', data: event }
    case 'log_complete':
      return 'complete'
    case 'sub_agent':
      return {
        type: 'subagent_event',
        data: {
          task_id: event.tool_call_id,
          subagent: event.subagent,
          task: event.task,
          status: event.status,
          log_path: event.log_path,
          round: event.rounds,
          elapsed_ms: event.duration_ms,
          final_message: event.final_output,
        },
      }
    case 'error_event':
      return { type: 'error', data: event.error_msg || event.error || '未知错误' }
    case 'info_event':
      return { type: 'hint', data: event.info_msg || '' }
    default:
      return null
  }
}

function applyLogEventSnapshot(
  snapshot: SessionChatSnapshot,
  sessionId: string,
  event: Record<string, any>,
  messageId: number,
  jsonlPath: string,
) {
  if (event.type === 'run_metadata') {
    const meta = normalizeRunMetadata(event)
    const metaIdx = findAssistantMessageIndexInSnapshot(snapshot, messageId)
    if (metaIdx >= 0) {
      const msg = snapshot.messages[metaIdx] as ChatMessage
      snapshot.messages[metaIdx] = { ...msg, meta }
    }
    return
  }
  if (event.type === 'log_complete') {
    completeLogMessageSnapshot(snapshot, sessionId, messageId)
    return
  }

  if (snapshot.activeAssistantIdx == null) {
    ensureLogPlaceholderSnapshot(snapshot, sessionId, messageId, jsonlPath)
  }
  const idx = snapshot.activeAssistantIdx
  if (idx == null) return
  const msg = snapshot.messages[idx] as ChatMessage | undefined
  if (!msg || msg.role !== 'assistant') return

  const streamEvt = buildStreamEventFromLogEvent(event, messageId)
  if (streamEvt === 'complete') {
    completeLogMessageSnapshot(snapshot, sessionId, messageId)
    return
  }
  if (!streamEvt) return

  applyStreamEvent(msg, streamEvt, { silent: true, subagents: snapshot.sessionSubagents as SubagentRecord[] })
  snapshot.messages[idx] = { ...msg }

  if (streamEvt.type === 'confirmation_required' && streamEvt.data) {
    const dangerTypes: string[] = streamEvt.data.danger_types || []
    const command = String(streamEvt.data.command || '').trim()
    if (!privacyStore.needsConfirmation(dangerTypes, command)) {
      const toolCallId = streamEvt.data.tool_call_id as string
      confirmTool(toolCallId, true).catch(() => {})
    }
  }
}

/** 后台 session 的 WS 事件：只写快照，不切换当前 UI（避免输入框闪烁） */
function applyWsPayloadToSnapshot(sessionId: string, data: Record<string, unknown>) {
  const snapshot = getOrCreateSnapshot(sessionId)

  if (data.type === 'log_started') {
    const newMsgId = Number(data.message_id) || 0
    if (newMsgId) {
      snapshot.activeAssistantMessageId = newMsgId
      ensureLogPlaceholderSnapshot(snapshot, sessionId, newMsgId, String(data.jsonl_path || ''))
    }
  } else if (data.type === 'log_event') {
    const evt = data.event as Record<string, unknown> | undefined
    const evtMessageId = Number(data.message_id) || 0
    if (!evt) return
    if (!snapshot.activeAssistantMessageId || evtMessageId !== snapshot.activeAssistantMessageId) {
      snapshot.activeAssistantMessageId = evtMessageId
      if (evtMessageId) {
        ensureLogPlaceholderSnapshot(snapshot, sessionId, evtMessageId, String(data.jsonl_path || ''))
      }
    }
    applyLogEventSnapshot(snapshot, sessionId, evt as Record<string, any>, evtMessageId, String(data.jsonl_path || ''))
  } else if (data.type === 'log_complete') {
    completeLogMessageSnapshot(snapshot, sessionId, Number(data.message_id) || 0)
  }

  saveSessionSnapshot(sessionId, snapshot)
  syncSnapshotWorkingState(sessionId, snapshot)
}

async function processChatWsPayload(data: Record<string, unknown>) {
  if (data.type === 'log_started') {
    const newMsgId = Number(data.message_id) || 0
    if (newMsgId) {
      activeAssistantMessageId = newMsgId
      ensureLogPlaceholder(newMsgId, String(data.jsonl_path || ''))
      syncSessionWorkingState()
    }
  } else if (data.type === 'log_event') {
    const evt = data.event as Record<string, unknown> | undefined
    const evtMessageId = Number(data.message_id) || 0
    if (!evt) return
    if (!activeAssistantMessageId || evtMessageId !== activeAssistantMessageId) {
      activeAssistantMessageId = evtMessageId
      if (evtMessageId) {
        ensureLogPlaceholder(evtMessageId, String(data.jsonl_path || ''))
      }
    }
    applyLogEvent(evt, evtMessageId, String(data.jsonl_path || ''))
    syncSessionWorkingState()
  } else if (data.type === 'log_complete') {
    completeLogMessage(Number(data.message_id) || 0)
  } else if (data.type === 'stream_event') {
    const event = data.event as Record<string, unknown> | undefined
    if (!event) return
    if (event.meta) {
      const meta = normalizeRunMetadata(event)
      const targetId = activeAssistantMessageId
      if (targetId && applyMetaToMessage(targetId, meta)) {
        /* applied by message id */
      } else {
        const lastIdx = messages.value.length - 1
        const lastAssistant = messages.value[lastIdx]
        if (lastAssistant?.role === 'assistant') {
          messages.value[lastIdx] = { ...lastAssistant, meta }
        }
      }
    } else {
      handlePlatformStreamEvent(event)
    }
    syncSessionWorkingState()
  } else if (data.type === 'new_message') {
    await loadNewMessages()
    ensurePlatformAssistantPlaceholder()
  } else if (data.type === 'session_update') {
    platformStreaming = false
    clearPetStatus()
    await loadNewMessages(true)
    syncSessionWorkingState()
  }
}

function handleChatWsForSession(sessionId: string, data: Record<string, unknown>) {
  if (sessionId === currentSessionId.value) {
    void processChatWsPayload(data).catch((e) => console.warn('[ChatWS] 处理失败', e))
    return
  }
  applyWsPayloadToSnapshot(sessionId, data)
}

async function ensureChatWsReady() {
  const sid = currentSessionId.value
  if (!sid) return
  const wsBase = modelStore.getBaseUrl().replace(/^http/, 'ws')
  setSessionWsHandler(sid, (data) => handleChatWsForSession(sid, data))
  await ensureSessionWs(sid, wsBase)
  pruneSessionWsKeep(buildWsKeepSet(sid))
}

function stopChatWs(clearRouting = true) {
  const sid = currentSessionId.value
  if (sid) persistCurrentSessionSnapshot(sid)
  if (clearRouting) {
    activeAssistantMessageId = null
    activeAssistantIdx = null
  }
  if (sid && !isSessionWorking(sid)) {
    closeSessionWs(sid)
    setSessionWsHandler(sid, null)
  }
}

function upsertSubagent(record: SubagentRecord) {
  const idx = sessionSubagents.value.findIndex((s) => s.task_id === record.task_id)
  if (idx >= 0) {
    // 合并字段（保留已有 inner_blocks，仅追加新内容由调用方处理）
    sessionSubagents.value[idx] = { ...sessionSubagents.value[idx], ...record }
  } else {
    sessionSubagents.value.push(record)
  }
}

function upsertSubagentInList(list: SubagentRecord[], record: SubagentRecord) {
  const idx = list.findIndex((s) => s.task_id === record.task_id)
  if (idx >= 0) {
    list[idx] = { ...list[idx], ...record }
  } else {
    list.push(record)
  }
}

function findSubagentByTaskId(taskId: string): SubagentRecord | undefined {
  return sessionSubagents.value.find((s) => s.task_id === taskId)
}

// 暴露给父组件
defineExpose({
  sessionSubagents,
})

// 已自动确认的 tool call ID 集合，用于跳过后续 pending_confirmation 事件
const autoConfirmedToolIds = new Set<string>()

const CONFIRM_TIMEOUT_SECONDS = 120

interface PendingToolConfirmation {
  toolCallId: string
  command: string
  dangerInfo: string
  dangerTypes: string[]
}

const pendingToolConfirmation = computed((): PendingToolConfirmation | null => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const msg = messages.value[i]
    if (msg.role !== 'assistant' || !msg.blocks) continue
    for (let j = msg.blocks.length - 1; j >= 0; j--) {
      const block = msg.blocks[j]
      if (block.type === 'tool' && block.pending_confirmation && block.tool_call_id) {
        const command = String(block.args?.command || '').trim()
        const dangerInfo = String(block.danger_info || '').trim()
        const dangerTypes = block.danger_types || []
        return {
          toolCallId: block.tool_call_id,
          command: command || dangerInfo || block.tool_name || '待确认命令',
          dangerInfo,
          dangerTypes,
        }
      }
    }
  }
  return null
})

const confirmDescription = computed(() => {
  const pending = pendingToolConfirmation.value
  if (!pending) return ''
  if (pending.dangerInfo) {
    return `此命令涉及${pending.dangerInfo}，需要您的批准后才能执行。`
  }
  if (pending.dangerTypes.length) {
    return `此命令涉及：${pending.dangerTypes.join('、')}，需要您的批准后才能执行。`
  }
  return '此命令可能具有风险，需要您的批准后才能执行。'
})

const confirmCountdown = ref(CONFIRM_TIMEOUT_SECONDS)
let confirmCountdownTimer: ReturnType<typeof setInterval> | null = null

function clearConfirmCountdownTimer() {
  if (confirmCountdownTimer) {
    clearInterval(confirmCountdownTimer)
    confirmCountdownTimer = null
  }
}

const textColor = computed(() => '#1a1a1a')
const fontSize = computed(() => 15)

// 同步默认模型
watch(() => modelStore.activeModel, (model) => {
  if (model) {
    selectedModel.value = model.model
  }
}, { immediate: true })

// 压缩完成后刷新上下文占用
async function onCompactDone() {
  if (!currentSessionId.value) return
  try {
    const usage = await getSessionContextUsage(currentSessionId.value)
    contextUsagePercent.value = Math.round(usage.usage_percent ?? 0)
    contextUsageBreakdown.value = usage
  } catch {
    // ignore
  }
}

// 监听侧边栏新对话事件
function onNewChat(e?: Event) {
  if (currentSessionId.value) {
    clearSessionStreamDurations(currentSessionId.value)
    persistCurrentSessionSnapshot(currentSessionId.value)
    stopChatWs(false)
  }
  currentSessionId.value = undefined
  isSending.value = false
  messages.value = []
  sessionSubagents.value = []
  hasActiveChat.value = false
  inputMessage.value = ''
  clearAttachedImages()
  clearComposerCommand()
  contextUsagePercent.value = 0
  contextUsageBreakdown.value = null
  const newWorkDir = (e as CustomEvent | undefined)?.detail?.workDir || defaultWorkDir.value
  pendingWorkDir.value = newWorkDir
  // 立即更新 UI 显示的工作目录，让用户看到正确的项目路径
  if (newWorkDir) {
    workDir.value = newWorkDir
    workspaceStore.setWorkDir(newWorkDir)
    loadWorkDirHistory()
  }
}

// 待写入的工作目录（来自项目创建新对话）
const pendingWorkDir = ref('')

// 当前工作目录（用于标签显示 + 选择）
import { defaultWorkDir } from '@/utils/paths'
const workDir = ref(defaultWorkDir.value)
const workDirHistory = ref<string[]>([])
const workDirLabel = computed(() => {
  if (!workDir.value) return 'work_dir'
  // 只显示最后一段路径名 + 父目录名，更紧凑
  const normalized = workDir.value.replace(/\\/g, '/').replace(/\/$/, '')
  const parts = normalized.split('/')
  return parts[parts.length - 1] || normalized
})

async function loadWorkDir() {
  await workspaceStore.initWorkDir()
  workDir.value = workspaceStore.workDir
  loadWorkDirHistory()
}

async function loadWorkDirHistory() {
  try {
    const data = await listWorkDirs()
    const list = (data.work_dirs || []).map((w: any) => w.work_dir as string)
    // 把当前 workDir 置顶（如果不在列表中）
    const cur = workDir.value
    if (cur && !list.includes(cur)) {
      list.unshift(cur)
    }
    workDirHistory.value = list.slice(0, 8)
  } catch {
    workDirHistory.value = workDir.value ? [workDir.value] : []
  }
}

function pushWorkDirHistory(path: string) {
  const list = workDirHistory.value.filter((d) => d !== path)
  list.unshift(path)
  workDirHistory.value = list.slice(0, 8)
}

function onWorkDirChanged(e: Event) {
  workDir.value = (e as CustomEvent).detail || defaultWorkDir.value
  workspaceStore.setWorkDir(workDir.value)
  loadWorkDirHistory()
}

// 点「+ 新工作目录」时调用 —— 后端调起系统文件夹选择对话框
async function pickWorkDir() {
  try {
    let path = ''

    // 优先使用 Electron 原生文件浏览器
    const electronAPI = (window as any).electronAPI
    if (electronAPI?.selectDirectory) {
      const result = await electronAPI.selectDirectory({ title: '选择工作目录' })
      if (result.cancelled || !result.path) return
      path = result.path
    } else {
      const result = await selectDirectory()
      if (result.cancelled || !result.path) return
      if (result.error) {
        alert(result.error)
        return
      }
      path = result.path
    }

    await applyWorkDir(path)
  } catch (e) {
    console.error('选择目录失败', e)
    alert('无法打开文件夹选择器：' + (e as Error).message)
  }
}

async function applyWorkDir(path: string) {
  try {
    await createWorkDir(path)
    workDir.value = path
    workspaceStore.setWorkDir(path)
    pendingWorkDir.value = path
    pushWorkDirHistory(path)
    window.dispatchEvent(new CustomEvent('aries:workdir-changed', { detail: path }))
  } catch (e) {
    console.error('保存工作目录失败', e)
    alert('保存失败')
  }
}

// 监听侧边栏 / 定时任务跳转，加载指定 session 的历史
let loadSessionSeq = 0

function isStaleSessionLoad(seq: number): boolean {
  return seq !== loadSessionSeq
}

async function refreshSessionContextUsage(sessionId: string, seq: number): Promise<void> {
  try {
    const usage = await getSessionContextUsage(sessionId)
    if (isStaleSessionLoad(seq)) return
    contextUsagePercent.value = Math.round(usage.usage_percent ?? 0)
    contextUsageBreakdown.value = usage
  } catch {
    if (isStaleSessionLoad(seq)) return
    contextUsagePercent.value = 0
    contextUsageBreakdown.value = null
  }
}

async function applySessionWorkDir(sessionId: string, seq: number): Promise<void> {
  try {
    const meta = await getSession(sessionId)
    if (isStaleSessionLoad(seq)) return
    const wd = meta?.work_dir
    if (wd && wd !== workDir.value) {
      workDir.value = wd
      workspaceStore.setWorkDir(wd)
      loadWorkDirHistory()
    }
  } catch {
    // ignore
  }
}

async function finishSessionSwitch(id: string, seq: number): Promise<void> {
  if (isStaleSessionLoad(seq)) return
  await ensureChatWsReady()
  if (isStaleSessionLoad(seq)) return
  emit('sessionLoaded')
  void tryResumeSession(id)
  void refreshSessionContextUsage(id, seq)
}

function scheduleSnapshotLoads(
  msgs: ChatMessage[],
  rawMessages: Array<{ id?: number; reasoning_content?: string }>,
  seq: number,
): void {
  const pending: Array<{ messageId: number; index: number; raw?: { reasoning_content?: string } }> = []
  for (let i = 0; i < msgs.length; i++) {
    if (msgs[i].role !== 'assistant') continue
    if (msgs[i].blocks && msgs[i].blocks.length > 0) continue
    const messageId = rawMessages[i]?.id ?? msgs[i].messageId
    if (!messageId) continue
    pending.push({ messageId, index: i, raw: rawMessages[i] })
  }
  if (pending.length === 0) return
  void loadSessionSnapshotsParallel(pending, seq)
}

async function loadSessionSnapshotsParallel(
  tasks: Array<{ messageId: number; index: number; raw?: { reasoning_content?: string } }>,
  seq: number,
  concurrency = 4,
): Promise<void> {
  for (let i = 0; i < tasks.length; i += concurrency) {
    if (isStaleSessionLoad(seq)) return
    const batch = tasks.slice(i, i + concurrency)
    await Promise.all(
      batch.map(({ messageId, index, raw }) => loadMessageSnapshot(messageId, index, raw, seq)),
    )
  }
}

function mapRawMessagesToChat(rawMessages: Array<Record<string, unknown>>): ChatMessage[] {
  return rawMessages.map((m) => {
    const base: ChatMessage = {
      role: m.role as 'user' | 'assistant',
      content: (m.content as string) || '',
      mode: (m.mode as string) || 'agent',
      reasoning: [],
      tools: [],
      blocks: [],
      isLoading: false,
      messageSnapshotJson: (m.message_snapshot_json as string) || undefined,
      messageId: m.id as number | undefined,
    }
    if (m.role === 'user') {
      Object.assign(base, enrichUserMessage((m.content as string) || ''))
      base.images = parseStoredImagePaths(m.image_path as string | undefined)
    }
    return base
  })
}

function applyBootstrapSnapshots(
  rawMessages: Array<{ id?: number; reasoning_content?: string }>,
  snapshots: Record<string, { events?: unknown[] }>,
  seq: number,
): void {
  for (let i = 0; i < messages.value.length; i++) {
    if (messages.value[i].role !== 'assistant') continue
    const messageId = rawMessages[i]?.id ?? messages.value[i].messageId
    if (!messageId) continue
    const snap = snapshots[String(messageId)]
    if (snap?.events?.length) {
      applyMessageSnapshotEvents(messageId, i, snap.events, rawMessages[i], seq)
    } else if (rawMessages[i]?.reasoning_content) {
      applyReasoningContentFallback(messageId, i, rawMessages[i].reasoning_content)
    }
  }
}

async function fetchSessionFromBackend(id: string, seq: number): Promise<boolean> {
  try {
    const bootstrap = await getSessionBootstrap(id, 100)
    if (isStaleSessionLoad(seq)) return false

    const wd = bootstrap.session?.work_dir
    if (wd && wd !== workDir.value) {
      workDir.value = wd
      workspaceStore.setWorkDir(wd)
      loadWorkDirHistory()
    }

    const rawMessages = bootstrap.messages || []
    messages.value = mapRawMessagesToChat(rawMessages)
    hasActiveChat.value = messages.value.length > 0
    await nextTick()
    if (isStaleSessionLoad(seq)) return false
    scheduleScrollToBottom(true)

    applyBootstrapSnapshots(rawMessages, bootstrap.snapshots || {}, seq)
    return true
  } catch (bootstrapErr) {
    console.warn('[session] bootstrap 失败，回退分步加载', bootstrapErr)
    try {
      const [metaSettled, dataSettled] = await Promise.allSettled([
        getSession(id),
        getSessionMessages(id, 100),
      ])
      if (isStaleSessionLoad(seq)) return false

      if (metaSettled.status === 'fulfilled') {
        const wd = metaSettled.value?.work_dir
        if (wd && wd !== workDir.value) {
          workDir.value = wd
          workspaceStore.setWorkDir(wd)
          loadWorkDirHistory()
        }
      }

      if (dataSettled.status !== 'fulfilled') throw dataSettled.reason

      const rawMessages = dataSettled.value.messages || []
      messages.value = mapRawMessagesToChat(rawMessages)
      hasActiveChat.value = messages.value.length > 0
      await nextTick()
      if (isStaleSessionLoad(seq)) return false
      scheduleScrollToBottom(true)
      scheduleSnapshotLoads(messages.value, rawMessages, seq)
      return true
    } catch (err) {
      console.error('加载历史消息失败', err)
      messages.value = []
      sessionSubagents.value = []
      hasActiveChat.value = false
      return false
    }
  }
}

async function loadSessionById(id: string) {
  if (!id) return
  const seq = ++loadSessionSeq

  const prevId = currentSessionId.value
  if (prevId && prevId !== id) {
    persistCurrentSessionSnapshot(prevId)
    stopChatWs(false)
  }

  currentSessionId.value = id
  isSending.value = false
  inputMessage.value = ''
  clearAttachedImages()
  clearComposerCommand()

  const cached = loadSessionSnapshot(id)
  if (cached?.messages?.length) {
    restoreSessionSnapshot(cached)
    await nextTick()
    if (isStaleSessionLoad(seq)) return
    scheduleScrollToBottom(true)
    void applySessionWorkDir(id, seq)
    const wsBase = modelStore.getBaseUrl().replace(/^http/, 'ws')
    for (const wsSid of buildWsKeepSet(id)) {
      setSessionWsHandler(wsSid, (data) => handleChatWsForSession(wsSid, data))
      await ensureSessionWs(wsSid, wsBase)
      if (isStaleSessionLoad(seq)) return
    }
    pruneSessionWsKeep(buildWsKeepSet(id))
    scheduleSnapshotLoads(cached.messages as ChatMessage[], cached.messages as ChatMessage[], seq)
    await finishSessionSwitch(id, seq)
    return
  }

  activeAssistantMessageId = null
  activeAssistantIdx = null
  sessionSubagents.value = []
  messages.value = []
  hasActiveChat.value = false

  await fetchSessionFromBackend(id, seq)
  if (isStaleSessionLoad(seq)) return
  await finishSessionSwitch(id, seq)
}

async function tryResumeSession(sessionId: string) {
  // 流式输出已切换为 WebSocket + JSONL，无需 SSE resume
  // 仅做最终状态检查：若后台任务仍在运行，确保 placeholder 是 loading 状态
  try {
    const running = await checkChatStatus(sessionId)
    if (!running) return
    // 找最后一条 assistant 消息
    let assistantIdx = -1
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        assistantIdx = i
        break
      }
    }
    if (assistantIdx < 0) {
      // 没有 placeholder → 等待 log_started 事件创建
      isSending.value = true
      return
    }
    const msg = messages.value[assistantIdx]
    // 标记为 loading，等待 WebSocket 推送后续事件
    if (!msg.isLoading) {
      msg.isLoading = true
      messages.value[assistantIdx] = { ...msg }
    }
    isSending.value = true
    markSessionWorking(sessionId)
    syncSessionWorkingState(sessionId)
  } catch {
    // ignore
  }
}

async function revertArtifact(msgIdx: number, artifactIdx: number) {
  const msg = messages.value[msgIdx]
  if (!msg?.artifacts?.[artifactIdx]) return
  const artifact = msg.artifacts[artifactIdx]
  try {
    const baseUrl = modelStore.getBaseUrl()
    const res = await fetch(`${baseUrl}/files/revert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: artifact.file_path,
        content: artifact.previous_content,
      }),
    })
    const data = await res.json()
    if (data.ok) {
      artifact.reverted = true
      messages.value[msgIdx] = { ...msg, artifacts: [...msg.artifacts!] }
    }
  } catch {
    // 静默处理
  }
}

let inlineDiffCounter = 0
function viewArtifact(msgIdx: number, artifactIdx: number) {
  const msg = messages.value[msgIdx]
  if (!msg?.artifacts?.[artifactIdx]) return
  const artifact = msg.artifacts[artifactIdx]
  inlineDiffData.value = {
    path: artifact.file_path,
    original: artifact.previous_content,
    modified: artifact.new_content,
    key: ++inlineDiffCounter,
  }
  rightPanelVisible.value = true
}

// 加载消息快照（JSONL 优先；无事件时用 DB reasoning_content 拆段）
function applyMessageSnapshotEvents(
  messageId: number,
  msgIndex: number,
  rawEvents: unknown[],
  raw?: { reasoning_content?: string },
  seq?: number,
): void {
  const prev = messages.value[msgIndex]
  if (!prev || prev.role !== 'assistant') return

  if (!rawEvents || rawEvents.length === 0) {
    applyReasoningContentFallback(messageId, msgIndex, raw?.reasoning_content)
    return
  }

  const parsed = parseSnapshotEventObjects(rawEvents)

  const blocks: MessageBlock[] = []
  let snapshotMeta: MessageMeta | undefined

  for (const event of parsed) {
    switch (event.type) {
      case 'reasoning':
        if (
          blocks.length > 0 &&
          blocks[blocks.length - 1].type === 'text' &&
          blocks[blocks.length - 1].phase === 'work'
        ) {
          blocks[blocks.length - 1].text = (blocks[blocks.length - 1].text || '') + event.content
        } else {
          blocks.push({ type: 'text', text: event.content, phase: 'work' })
        }
        break

      case 'tool_call':
        blocks.push({
          type: 'tool',
          tool_name: event.toolName || 'unknown',
          tool_call_id: event.toolCallId || '',
          status: event.status || 'running',
          args: event.args,
          result: '',
          error: '',
          started_at: event.timestamp || '',
          ended_at: ''
        })
        break

      case 'sub_agent': {
        const tcId = event.toolCallId || ''
        let existing: MessageBlock | undefined
        if (tcId) {
          for (let i = blocks.length - 1; i >= 0; i--) {
            const b = blocks[i]
            if (b.type === 'tool' && b.tool_call_id === tcId) {
              existing = b
              break
            }
          }
        }
        const subagentField = {
          task_id: tcId,
          subagent: event.subagent,
          task: event.task,
          status: event.status,
          log_path: event.logPath,
          elapsed_ms: event.durationMs,
          final_message: event.finalOutput,
        }
        if (existing) {
          existing.tool_name = 'delegate_to_subagent'
          existing.status = event.status === 'success' ? 'completed' : (event.status || existing.status || 'running')
          if (event.finalOutput) existing.result = event.finalOutput
          if (event.status && event.status !== 'success') {
            existing.error = event.content || existing.error || ''
          }
          existing.ended_at = event.timestamp || existing.ended_at || ''
          existing.args = {
            ...(existing.args || {}),
            subagent_name: event.subagent || existing.args?.subagent_name || '',
            task: event.task || existing.args?.task || '',
          }
          existing.subagent = { ...(existing.subagent || {}), ...subagentField }
        } else {
          blocks.push({
            type: 'tool',
            tool_name: 'delegate_to_subagent',
            tool_call_id: tcId,
            status: event.status === 'success' ? 'completed' : (event.status || 'running'),
            args: {
              subagent_name: event.subagent || '',
              task: event.task || '',
              description: '',
            },
            result: event.finalOutput || '',
            error: event.status && event.status !== 'success' ? (event.content || '') : '',
            started_at: event.timestamp || '',
            ended_at: event.timestamp || '',
            subagent: subagentField,
          })
        }
        if (tcId) {
          upsertSubagent({
            task_id: tcId,
            subagent: event.subagent,
            task: event.task,
            status: event.status,
            log_path: event.logPath,
            elapsed_ms: event.durationMs,
            final_message: event.finalOutput,
            message_id: messageId,
          })
        }
        break
      }

      case 'tool_result':
        for (let i = blocks.length - 1; i >= 0; i--) {
          const b = blocks[i]
          if (b.type === 'tool' && (b.tool_name === event.toolName || b.tool_name === event.toolCallId)) {
            b.status = event.status || 'completed'
            b.result = event.content
            b.ended_at = event.timestamp || ''
            if (event.sessionId) {
              b.session_id = event.sessionId
            }
            break
          }
        }
        break

      case 'assistant_text':
        if (blocks.length > 0 && blocks[blocks.length - 1].type === 'text' && blocks[blocks.length - 1].phase === 'answer') {
          blocks[blocks.length - 1].text = (blocks[blocks.length - 1].text || '') + event.content
        } else {
          blocks.push({ type: 'text', text: event.content, phase: 'answer' })
        }
        break

      case 'error':
        blocks.push({
          type: 'text',
          text: event.content,
          phase: 'answer',
          error: event.content,
        })
        break

      case 'run_metadata':
        if (event.meta) {
          snapshotMeta = normalizeRunMetadata(event.meta)
        }
        break
    }
  }

  const reasoningJoined = parsed.filter(e => e.type === 'reasoning').map(e => e.content).join('')
  const reasoningSegments = reasoningJoined ? [reasoningJoined] : []
  const answerText = parsed.filter(e => e.type === 'assistant_text').map(e => e.content).join('')
  const errorText = parsed.find(e => e.type === 'error')?.content || ''

  const artifacts = parsed
    .filter(e => e.type === 'tool_result' && e.fileChange)
    .map(e => ({
      file_path: e.fileChange!.file_path || '',
      operation: e.fileChange!.operation || 'modify',
      previous_content: e.fileChange!.previous_content || '',
      new_content: e.fileChange!.new_content || '',
      tool_name: e.toolName || '',
      tool_call_id: e.toolCallId || '',
      reverted: false,
    }))

  if (seq !== undefined && isStaleSessionLoad(seq)) return

  messages.value[msgIndex] = {
    ...prev,
    blocks,
    reasoning: reasoningSegments,
    tools: parsed
      .filter(e => e.type === 'tool_call' || e.type === 'tool_result')
      .reduce((acc: ToolInfo[], e) => {
        if (e.type === 'tool_call') {
          acc.push({
            name: e.toolName || 'unknown',
            status: e.status || 'running',
            args: e.args,
            output: ''
          })
        } else if (e.type === 'tool_result') {
          const t = acc.find(t => t.name === e.toolName)
          if (t) {
            t.status = e.status || 'completed'
            t.output = e.content
          }
        }
        return acc
      }, []),
    content: answerText || errorText || prev.content,
    hasSnapshot: true,
    meta: snapshotMeta || prev.meta,
    artifacts,
  }
}

async function loadMessageSnapshot(
  messageId: number,
  msgIndex: number,
  raw?: { reasoning_content?: string },
  seq?: number,
) {
  const prev = messages.value[msgIndex]
  if (!prev || prev.role !== 'assistant') return

  try {
    const baseUrl = modelStore.getBaseUrl()
    const res = await fetch(`${baseUrl}/sessions/messages/${messageId}/jsonl`)
    if (!res.ok) {
      console.warn(`消息 ${messageId} 快照接口返回 ${res.status}`)
      applyReasoningContentFallback(messageId, msgIndex, raw?.reasoning_content)
      return
    }

    const data = await res.json()
    applyMessageSnapshotEvents(messageId, msgIndex, data.events || [], raw, seq)
  } catch (err) {
    console.error('加载快照失败:', err)
    applyReasoningContentFallback(messageId, msgIndex, raw?.reasoning_content)
  }
}

function buildSessionTitle(text: string): string {
  const raw = text.trim().replace(/\n/g, ' ')
  if (!raw) return '新对话'
  return raw.slice(0, 18) + (raw.length > 18 ? '…' : '')
}

function resolveWorkDirForSend(): string {
  return (pendingWorkDir.value || workDir.value || defaultWorkDir.value || '').trim()
}

async function ensureSessionTitle(sessionId: string, text: string, workDirPath?: string) {
  const title = buildSessionTitle(text)
  const resolvedWorkDir = (workDirPath || resolveWorkDirForSend()).trim()
  try {
    await updateSessionMeta(sessionId, {
      title,
      work_dir: resolvedWorkDir || defaultWorkDir.value,
    })
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
  } catch (e) {
    console.error('设置会话标题失败', e)
  }
}

async function markSnapshotAvailable(messageId: number, msgIndex: number) {
  const prev = messages.value[msgIndex]
  if (!prev || prev.role !== 'assistant') return

  try {
    const baseUrl = modelStore.getBaseUrl()
    const res = await fetch(`${baseUrl}/sessions/messages/${messageId}/jsonl`)
    if (!res.ok) return

    const data = await res.json()
    if (!data.events || data.events.length === 0) return

    messages.value[msgIndex] = {
      ...prev,
      hasSnapshot: true,
    }
  } catch (err) {
    console.error('检查消息快照失败:', err)
  }
}

async function refreshAssistantSnapshot(sessionId: string, assistantIdx: number) {
  try {
    const data = await getSessionMessages(sessionId, 20)
    const list = data.messages || []
    const lastAssistant = [...list].reverse().find((m: { role: string }) => m.role === 'assistant')
    if (lastAssistant?.id) {
      await markSnapshotAvailable(lastAssistant.id, assistantIdx)
    }
  } catch (err) {
    console.error('刷新助手快照状态失败', err)
  }
}

function applyReasoningContentFallback(
  messageId: number,
  msgIndex: number,
  reasoningContent?: string | null
) {
  const prev = messages.value[msgIndex]
  if (!prev || prev.role !== 'assistant') return

  const rc = (reasoningContent || '').trim()
  if (!rc) return

  const segments = rc.split('\n').filter((line) => line.trim())
  if (segments.length === 0) return

  const blocks: MessageBlock[] = segments.map((text) => ({
    type: 'text',
    text,
    phase: 'work',
  }))

  console.log(`[snapshot] 消息 ${messageId} 使用 reasoning_content 回退，${segments.length} 段`)

  messages.value[msgIndex] = {
    ...prev,
    blocks,
    reasoning: segments,
    content: prev.content,
  }
}

function onFocusConsole() {
  rightPanelVisible.value = true
}

// AI 回复中点击链接：把右侧面板展开（具体切到浏览器 tab 由 RightPanel 处理）
function onOpenUrlFromMessage() {
  rightPanelVisible.value = true
}

function onToast(e: Event) {
  const detail = (e as CustomEvent).detail as { message?: string; type?: 'info' | 'warning' | 'error' }
  if (detail?.message) showToast(detail.message, detail.type || 'info')
}

function onAddToChat(e: Event) {
  const detail = (e as CustomEvent).detail as string
  if (detail) {
    inputMessage.value += inputMessage.value ? ` ${detail}` : detail
  }
}

onMounted(() => {
  window.addEventListener('aries:new-chat', onNewChat)
  window.addEventListener('aries:workdir-changed', onWorkDirChanged)
  window.addEventListener('aries:focus-console', onFocusConsole)
  window.addEventListener('aries:open-url', onOpenUrlFromMessage)
  window.addEventListener('aries:toast', onToast)
  window.addEventListener('aries:add-to-chat', onAddToChat)
  window.addEventListener('aries:select-work-dir', onSelectWorkDir)
  loadWorkDir()
  // 确保模型列表已加载（避免 MainLayout 加载未完成导致下拉框为空）
  void modelStore.loadModels()
  if (props.sessionIdToLoad) {
    void loadSessionById(props.sessionIdToLoad)
  }
  // 自动恢复桌面宠物
  restorePet()
})

// ---------- 宠物持久化恢复 ----------
function restorePet() {
  try {
    // 用户上次明确关闭过，则不自动恢复
    if (localStorage.getItem('pet:enabled') === '0') return
    const saved = localStorage.getItem('pet:active')
    if (!saved) return
    const spec = JSON.parse(saved)
    if (!spec || typeof spec !== 'object' || !spec.url) return
    // 旧版仅含 { url, name } 不带 sprite metadata：可能指向已迁走的 GIF，丢弃缓存
    const isNewFormat = spec.frameWidth || spec.columns || Array.isArray(spec.states)
      || /spritesheet\.(webp|png)(\?|$)/i.test(spec.url)
    if (!isNewFormat) {
      localStorage.removeItem('pet:active')
      return
    }
    window.electronAPI?.showPet(spec)
  } catch { /* 忽略 */ }
}

// 监听宠物窗口被用户从右上角关闭按钮关闭：同步持久化"已关闭"
window.electronAPI?.onPetClose?.(() => {
  try { localStorage.setItem('pet:enabled', '0') } catch { /* 忽略 */ }
})

watch(() => props.sessionIdToLoad, (id) => {
  if (id) void loadSessionById(id)
})

onUnmounted(() => {
  clearConfirmCountdownTimer()
  if (currentSessionId.value) persistCurrentSessionSnapshot(currentSessionId.value)
  closeAllSessionWs()
  if (scrollIdleTimer) {
    clearTimeout(scrollIdleTimer)
    scrollIdleTimer = null
  }
  window.removeEventListener('aries:new-chat', onNewChat)
  window.removeEventListener('aries:workdir-changed', onWorkDirChanged)
  window.removeEventListener('aries:focus-console', onFocusConsole)
  window.removeEventListener('aries:open-url', onOpenUrlFromMessage)
  window.removeEventListener('aries:toast', onToast)
  window.removeEventListener('aries:add-to-chat', onAddToChat)
  window.removeEventListener('aries:select-work-dir', onSelectWorkDir)
})

function onSelectWorkDir() {
  void pickWorkDir()
}

// ---------- 宠物窗口状态推送 ----------
let petStatusPhase = ''
let petReasoningBuf = '' // 累积思考内容
let petContentBuf = ''   // 累积回复内容

function sendPetStatus(text: string) {
  try {
    window.electronAPI?.sendPetStatus(text)
  } catch { /* 非 Electron 环境忽略 */ }
}

function clearPetStatus() {
  petStatusPhase = ''
  petReasoningBuf = ''
  petContentBuf = ''
  try {
    window.electronAPI?.clearPetStatus()
    window.electronAPI?.setPetState?.('idle')
  } catch { /* 非 Electron 环境忽略 */ }
}

/** 阶段切换时，把上一阶段的文字内容推送到宠物窗口 */
function flushPetStatus(oldPhase: string) {
  if (oldPhase === 'reasoning' && petReasoningBuf.trim()) {
    const text = petReasoningBuf.trim()
    sendPetStatus(text.length > 200 ? text.slice(0, 200) + '…' : text)
    petReasoningBuf = ''
  } else if (oldPhase === 'content' && petContentBuf.trim()) {
    const text = petContentBuf.trim()
    sendPetStatus(text.length > 200 ? text.slice(0, 200) + '…' : text)
    petContentBuf = ''
  }
}

function applyStreamEvent(
  assistantMsg: ChatMessage,
  evt: StreamEvent,
  opts?: { silent?: boolean; subagents?: SubagentRecord[] },
) {
  const silent = opts?.silent ?? false
  if (evt.type === 'content' && evt.data) {
    if (!silent) {
      if (petStatusPhase !== 'content') {
        flushPetStatus(petStatusPhase)
        petStatusPhase = 'content'
        window.electronAPI?.setPetState?.('waving')
      }
      petContentBuf += evt.data
    }
    assistantMsg.content += evt.data
    const blocks = (assistantMsg.blocks || []).slice()
    const lastBlock = blocks[blocks.length - 1]
    if (lastBlock && lastBlock.type === 'text' && lastBlock.phase === 'answer') {
      lastBlock.text = (lastBlock.text || '') + evt.data
    } else {
      blocks.push({ type: 'text', text: evt.data, phase: 'answer' })
    }
    assistantMsg.blocks = blocks
  } else if (evt.type === 'reasoning') {
    if (!silent) {
      if (petStatusPhase !== 'reasoning') {
        flushPetStatus(petStatusPhase)
        petStatusPhase = 'reasoning'
        window.electronAPI?.setPetState?.('waiting')
      }
      petReasoningBuf += evt.data
    }
    if (!assistantMsg.reasoning) assistantMsg.reasoning = []
    const blocks = (assistantMsg.blocks || []).slice()

    if (assistantMsg.reasoning.length === 0) {
      assistantMsg.reasoning.push(evt.data)
    } else {
      assistantMsg.reasoning[assistantMsg.reasoning.length - 1] += evt.data
    }
    const lastBlock = blocks[blocks.length - 1]
    if (lastBlock && lastBlock.type === 'text' && lastBlock.phase === 'work') {
      lastBlock.text = (lastBlock.text || '') + evt.data
    } else {
      blocks.push({ type: 'text', text: evt.data, phase: 'work' })
    }
    assistantMsg.blocks = blocks
  } else if (evt.type === 'tool_call') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    if (!silent) {
      flushPetStatus(petStatusPhase)
      petStatusPhase = 'tool'
      window.electronAPI?.setPetState?.('review')
    }
    const toolCallId = String(evt.data.tool_call_id || '').trim()
    // 查找已有的同 tool_call_id 的 tool block（避免危险命令确认重发时重复创建）
    let existingBlockIdx = -1
    if (toolCallId) {
      existingBlockIdx = assistantMsg.blocks.findIndex(
        (b) => b.type === 'tool' && b.tool_call_id === toolCallId
      )
    }
    if (existingBlockIdx >= 0) {
      // 更新已有 block 状态为 running
      const blocks = assistantMsg.blocks.slice()
      blocks[existingBlockIdx] = {
        ...blocks[existingBlockIdx],
        status: 'running',
        args: evt.data.args || blocks[existingBlockIdx].args,
        pending_confirmation: false,
      }
      assistantMsg.blocks = blocks
      // 同步更新 tools
      const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
      if (lastTool && lastTool.name === evt.data.tool_name) {
        lastTool.status = 'running'
      }
    } else {
      const toolBlock: MessageBlock = {
        type: 'tool',
        tool_name: evt.data.tool_name,
        tool_call_id: evt.data.tool_call_id,
        session_id: evt.data.session_id || '',
        status: 'running',
        args: evt.data.args,
        result: '',
        error: '',
        started_at: '',
        ended_at: ''
      }
      assistantMsg.tools.push({
        name: evt.data.tool_name,
        status: 'running',
        args: evt.data.args,
        output: ''
      })
      assistantMsg.blocks = [...assistantMsg.blocks, toolBlock]
    }
  } else if (evt.type === 'tool_result') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    const _toolName = evt.data.tool_name || 'tool'
    const _ok = evt.data.status !== 'error'
    const _output = (evt.data.output || '').trim()
    if (!silent) {
      let _msg = `${_ok ? '✅' : '❌'} ${_toolName}`
      if (_output) {
        _msg += ': ' + (_output.length > 150 ? _output.slice(0, 150) + '…' : _output)
      }
      sendPetStatus(_msg)
    }
    // 收集 file_change 到 artifacts
    if (evt.data.file_change) {
      if (!assistantMsg.artifacts) assistantMsg.artifacts = []
      assistantMsg.artifacts.push({
        file_path: evt.data.file_change.file_path || '',
        operation: evt.data.file_change.operation || 'modify',
        previous_content: evt.data.file_change.previous_content || '',
        new_content: evt.data.file_change.new_content || '',
        tool_name: _toolName,
        tool_call_id: String(evt.data.tool_call_id || ''),
      })
    }
    const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
    if (lastTool && lastTool.name === evt.data.tool_name) {
      lastTool.status = evt.data.status || 'completed'
      lastTool.output = evt.data.output || ''
    }
    if (assistantMsg.blocks && assistantMsg.blocks.length > 0) {
      const blocks = assistantMsg.blocks.slice()
      const toolCallId = String(evt.data.tool_call_id || '').trim()
      let targetIdx = -1
      if (toolCallId) {
        targetIdx = blocks.findIndex(
          (b) => b.type === 'tool' && b.tool_call_id === toolCallId
        )
      }
      if (targetIdx < 0) {
        for (let i = blocks.length - 1; i >= 0; i -= 1) {
          const b = blocks[i]
          if (b.type === 'tool' && (!evt.data.tool_name || b.tool_name === evt.data.tool_name)) {
            targetIdx = i
            break
          }
        }
      }
      if (targetIdx >= 0) {
        const block = blocks[targetIdx]
        if (block.type === 'tool') {
          const newStatus = evt.data.status || 'completed'
          const isPendingConfirm = newStatus === 'pending_confirmation'
          // 已自动确认的 tool，跳过 pending_confirmation 状态，保持 running
          const isAutoConfirmed = block.tool_call_id && autoConfirmedToolIds.has(block.tool_call_id)
          blocks[targetIdx] = {
            ...block,
            status: isAutoConfirmed && isPendingConfirm ? 'running' : newStatus,
            result: evt.data.output || '',
            ended_at: '',
            pending_confirmation: isAutoConfirmed ? false : (isPendingConfirm ? block.pending_confirmation : false),
            session_id: evt.data.session_id || (block as MessageBlock).session_id || '',
            auto_detached: Boolean(evt.data.auto_detached || (block as MessageBlock).auto_detached),
          }
        }
      }
      assistantMsg.blocks = blocks
    }
    if (evt.data.status && evt.data.status !== 'pending_confirmation') {
      clearConfirmCountdownTimer()
    }
  } else if (evt.type === 'confirmation_required') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
    if (lastTool && lastTool.name === evt.data.tool_name) {
      lastTool.status = 'pending_confirmation'
      lastTool.output = '等待确认…'
    }
    if (assistantMsg.blocks && assistantMsg.blocks.length > 0) {
      const blocks = assistantMsg.blocks.slice()
      const lastToolBlock = blocks[blocks.length - 1]
      if (lastToolBlock && lastToolBlock.type === 'tool') {
        lastToolBlock.status = 'pending_confirmation'
        lastToolBlock.pending_confirmation = true
        lastToolBlock.danger_info = evt.data.danger_info || ''
        lastToolBlock.danger_types = evt.data.danger_types || []
        lastToolBlock.tool_call_id = evt.data.tool_call_id
        if (evt.data.command && lastToolBlock.args) {
          lastToolBlock.args = { ...lastToolBlock.args, command: evt.data.command }
        }
      }
      assistantMsg.blocks = blocks
    }
  } else if (evt.type === 'subagent_event') {
    if (!silent) {
      window.dispatchEvent(new CustomEvent('aries:subagent-stream', { detail: { eventType: evt.type, data: evt.data || {} } }))
    }
    // 子 Agent 实时进度：合并到匹配的 delegate_to_subagent 工具块上
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    const subData = evt.data || {}
    const subName = String(subData.subagent || '')
    const taskId = String(subData.task_id || '')
    // 找到最后一个还在 running 状态的 delegate_to_subagent 块（按 subagent 名匹配）
    const blocks = assistantMsg.blocks
    let target: MessageBlock | undefined
    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i]
      if (b.type !== 'tool' || b.tool_name !== 'delegate_to_subagent') continue
      // 优先用 task_id 精确匹配
      if (taskId && b.subagent?.task_id === taskId) { target = b; break }
      // fallback：subagent 名匹配且尚未绑定 task_id
      if (!taskId && (!subName || !b.args || !b.args.subagent_name || b.args.subagent_name === subName)) {
        target = b
        break
      }
    }
    if (target) {
      target.subagent = {
        task_id: taskId || target.subagent?.task_id,
        subagent: subData.subagent,
        task: subData.task,
        status: subData.status,
        round: subData.round,
        last_event: subData.last_event,
        elapsed_ms: subData.elapsed_ms,
        log_path: subData.log_path,
        inner_blocks: target.subagent?.inner_blocks,
        final_message: target.subagent?.final_message,
      }
    }
    // 同步到 sessionSubagents
    if (taskId) {
      const record: SubagentRecord = {
        task_id: taskId,
        subagent: subData.subagent,
        task: subData.task,
        status: subData.status,
        round: subData.round,
        last_event: subData.last_event,
        elapsed_ms: subData.elapsed_ms,
        log_path: subData.log_path,
      }
      if (opts?.subagents) {
        upsertSubagentInList(opts.subagents, record)
      } else {
        upsertSubagent(record)
      }
    }
  } else if (
    evt.type === 'subagent_reasoning' ||
    evt.type === 'subagent_content' ||
    evt.type === 'subagent_tool_call' ||
    evt.type === 'subagent_tool_result'
  ) {
    if (!silent) {
      window.dispatchEvent(new CustomEvent('aries:subagent-stream', { detail: { eventType: evt.type, data: evt.data || {} } }))
    }
    // 子 Agent 的细粒度流式事件：追加到匹配 tool block 的 subagent.inner_blocks
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    const d = evt.data || {}
    const taskId = String(d.task_id || '')
    const blocks = assistantMsg.blocks
    let target: MessageBlock | undefined
    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i]
      if (b.type !== 'tool' || b.tool_name !== 'delegate_to_subagent') continue
      // 用 task_id 精确匹配（更稳），fallback 到 subagent 名
      const sa = b.subagent
      if (!sa) continue
      if (taskId && sa.task_id === taskId) { target = b; break }
      if (!taskId && d.subagent && b.args?.subagent_name === d.subagent) { target = b; break }
    }
    if (!target) return
    if (!target.subagent) target.subagent = {}
    if (!target.subagent.inner_blocks) target.subagent.inner_blocks = []
    const inner: MessageBlock[] = target.subagent.inner_blocks

    // 同时同步到 sessionSubagents
    let sessRecord = taskId ? findSubagentByTaskId(taskId) : undefined
    if (taskId && !sessRecord) {
      // 第一次细粒度事件先于 subagent_event 到达的兜底
      upsertSubagent({
        task_id: taskId,
        subagent: d.subagent,
        status: 'running',
      })
      sessRecord = findSubagentByTaskId(taskId)
    }
    if (sessRecord) {
      if (!sessRecord.inner_blocks) sessRecord.inner_blocks = []
    }

    if (evt.type === 'subagent_reasoning') {
      const delta = String(d.delta || '')
      if (!delta) return
      const last = inner[inner.length - 1]
      if (last && last.type === 'text' && last.phase === 'work') {
        last.text = (last.text || '') + delta
      } else {
        inner.push({ type: 'text', text: delta, phase: 'work' })
      }
      if (sessRecord) {
        const sLast = sessRecord.inner_blocks![sessRecord.inner_blocks!.length - 1]
        if (sLast && sLast.type === 'text' && sLast.phase === 'work') {
          sLast.text = (sLast.text || '') + delta
        } else {
          sessRecord.inner_blocks!.push({ type: 'text', text: delta, phase: 'work' })
        }
      }
    } else if (evt.type === 'subagent_content') {
      const delta = String(d.delta || '')
      if (!delta) return
      const last = inner[inner.length - 1]
      if (last && last.type === 'text' && last.phase === 'answer') {
        last.text = (last.text || '') + delta
      } else {
        inner.push({ type: 'text', text: delta, phase: 'answer' })
      }
      if (sessRecord) {
        const sLast = sessRecord.inner_blocks![sessRecord.inner_blocks!.length - 1]
        if (sLast && sLast.type === 'text' && sLast.phase === 'answer') {
          sLast.text = (sLast.text || '') + delta
        } else {
          sessRecord.inner_blocks!.push({ type: 'text', text: delta, phase: 'answer' })
        }
      }
    } else if (evt.type === 'subagent_tool_call') {
      const newBlock: MessageBlock = {
        type: 'tool',
        tool_name: d.tool_name || 'unknown',
        tool_call_id: d.tool_call_id || '',
        status: d.status || 'running',
        args: d.args,
        result: '',
        error: '',
        started_at: '',
        ended_at: '',
      }
      inner.push(newBlock)
      if (sessRecord) {
        sessRecord.inner_blocks!.push({ ...newBlock })
      }
    } else if (evt.type === 'subagent_tool_result') {
      const tcId = String(d.tool_call_id || '')
      for (let i = inner.length - 1; i >= 0; i--) {
        const b = inner[i]
        if (b.type === 'tool' && b.tool_call_id === tcId) {
          b.status = d.status || 'completed'
          b.result = typeof d.output === 'string' ? d.output : JSON.stringify(d.output || '')
          b.error = d.error || ''
          b.ended_at = ''
          break
        }
      }
      if (sessRecord) {
        for (let i = sessRecord.inner_blocks!.length - 1; i >= 0; i--) {
          const b = sessRecord.inner_blocks![i]
          if (b.type === 'tool' && b.tool_call_id === tcId) {
            b.status = d.status || 'completed'
            b.result = typeof d.output === 'string' ? d.output : JSON.stringify(d.output || '')
            b.error = d.error || ''
            break
          }
        }
      }
      // 如果是 report_to_main 的结果，把 message 存为 final_message
      if (d.tool_name === 'report_to_main' && d.status === 'completed') {
        const finalMsg = typeof d.output === 'string' ? d.output : ''
        target.subagent.final_message = finalMsg
        if (sessRecord) sessRecord.final_message = finalMsg
      }
    }
  } else if (evt.type === 'error') {
    // 处理错误事件（如 API 错误、黑名单拦截等）
    assistantMsg.isLoading = false
    const errorMsg = typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data)
    assistantMsg.content = errorMsg
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    // 添加错误块，用 error 属性标记
    assistantMsg.blocks.push({
      type: 'text',
      text: errorMsg,
      phase: 'answer',
      error: errorMsg,
    })
  }
}

function isStaleConfirmationError(e: unknown): boolean {
  const msg = String((e as Error)?.message || '')
  return msg.includes('未找到待确认') || msg.includes('404')
}

function clearPendingConfirmationUi() {
  clearConfirmCountdownTimer()
  autoConfirmedToolIds.clear()
  messages.value = messages.value.map((msg) => {
    if (msg.role !== 'assistant' || !msg.blocks) return msg
    let changed = false
    const blocks = msg.blocks.map((block) => {
      if (block.type === 'tool' && block.pending_confirmation) {
        changed = true
        return { ...block, pending_confirmation: false }
      }
      return block
    })
    return changed ? { ...msg, blocks } : msg
  })
}

function dismissPendingConfirmations(reason = '已取消') {
  clearConfirmCountdownTimer()
  messages.value = messages.value.map((msg) => {
    if (msg.role !== 'assistant' || !msg.blocks) return msg
    let changed = false
    const blocks = msg.blocks.map((block) => {
      if (block.type === 'tool' && block.pending_confirmation) {
        changed = true
        return {
          ...block,
          pending_confirmation: false,
          status: 'error',
          error: block.error || reason,
        }
      }
      return block
    })
    return changed ? { ...msg, blocks } : msg
  })
}

function resolveToolConfirmation(toolCallId: string, accepted: boolean) {
  clearConfirmCountdownTimer()
  messages.value = messages.value.map((msg) => {
    if (msg.role !== 'assistant' || !msg.blocks) return msg
    let changed = false
    const blocks = msg.blocks.map((block) => {
      if (block.type === 'tool' && block.tool_call_id === toolCallId && block.pending_confirmation) {
        changed = true
        return {
          ...block,
          pending_confirmation: false,
          status: accepted ? 'running' : 'error',
          error: accepted ? block.error : (block.error || '已拒绝'),
        }
      }
      return block
    })
    return changed ? { ...msg, blocks } : msg
  })
}

async function onToolConfirm(toolCallId: string) {
  if (!toolCallId) return
  clearConfirmCountdownTimer()
  try {
    await confirmTool(toolCallId, true)
  } catch (e) {
    if (!isStaleConfirmationError(e)) {
      alert((e as Error).message)
    }
  } finally {
    resolveToolConfirmation(toolCallId, true)
  }
}

async function onToolCancel(toolCallId: string) {
  if (!toolCallId) return
  const stillPending = pendingToolConfirmation.value?.toolCallId === toolCallId
  if (!stillPending) return
  clearConfirmCountdownTimer()
  try {
    await confirmTool(toolCallId, false)
  } catch (e) {
    if (!isStaleConfirmationError(e)) {
      alert((e as Error).message)
    }
  } finally {
    resolveToolConfirmation(toolCallId, false)
  }
}

async function onDangerConfirmSubmit(mode: 'yes' | 'no') {
  const pending = pendingToolConfirmation.value
  if (!pending) return
  if (mode === 'yes') {
    await onToolConfirm(pending.toolCallId)
    return
  }
  await onToolCancel(pending.toolCallId)
}

watch(pendingToolConfirmation, (pending) => {
  clearConfirmCountdownTimer()
  if (!pending) return
  confirmCountdown.value = CONFIRM_TIMEOUT_SECONDS
  confirmCountdownTimer = setInterval(() => {
    confirmCountdown.value -= 1
    if (confirmCountdown.value <= 0) {
      clearConfirmCountdownTimer()
      onToolCancel(pending.toolCallId)
    }
  }, 1000)
})

async function stopGeneration() {
  if (pendingToolConfirmation.value) {
    dismissPendingConfirmations('已停止')
  }
  const sessionId = currentSessionId.value
  if (sessionId) {
    stopChat(sessionId).catch(() => {})
    markSessionIdle(sessionId)
    syncSessionWorkingState(sessionId)
  }
  isSending.value = false
  clearPetStatus()
  const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
  if (lastAssistant) {
    lastAssistant.isLoading = false
    if (lastAssistant.blocks) {
      for (const block of lastAssistant.blocks) {
        if (block.type === 'tool' && block.status === 'running') {
          block.status = 'error'
          block.result = block.result || '已停止'
        }
      }
    }
    if (lastAssistant.tools) {
      for (const tool of lastAssistant.tools) {
        if (tool.status === 'running') {
          tool.status = 'error'
          tool.output = tool.output || '已停止'
        }
      }
    }
  }
}

async function sendMessage() {
  if (composerIsSending.value || !canSend.value) return

  const message = inputMessage.value.trim()
  const imagesToSend = attachedImages.value.map((img) => img.data)
  if (!message && imagesToSend.length === 0) return

  const userDisplayContent = message || (imagesToSend.length > 1 ? `[${imagesToSend.length} 张图片]` : '[图片]')

  messages.value.push({
    role: 'user',
    content: userDisplayContent,
    images: imagesToSend.length ? [...imagesToSend] : undefined,
  })
  inputMessage.value = ''
  clearAttachedImages()
  clearComposerCommand()
  hasActiveChat.value = true
  isSending.value = true

  // placeholder assistant 消息：等到 log_started 事件到达时再创建/定位
  // 主动创建一个占位以保证 UI 立即显示 loading
  messages.value.push({
    role: 'assistant',
    content: '',
    reasoning: [],
    tools: [],
    blocks: [],
    isLoading: true,
  })
  const assistantIdx = messages.value.length - 1
  activeAssistantIdx = assistantIdx

  const isNewSession = !currentSessionId.value
  const sessionIdAtSend = currentSessionId.value || crypto.randomUUID().replace(/-/g, '')
  startStreamDuration(sessionIdAtSend, '__pending__')
  markSessionWorking(sessionIdAtSend)
  if (isNewSession) {
    currentSessionId.value = sessionIdAtSend
  }
  const workDirAtSend = resolveWorkDirForSend()
  if (workDirAtSend && !workDir.value.trim()) {
    workDir.value = workDirAtSend
    workspaceStore.setWorkDir(workDirAtSend)
  }
  if (workDirAtSend && isNewSession) {
    pendingWorkDir.value = ''
  }

  await nextTick()
  scheduleScrollToBottom(true)
  if (isNewSession) {
    await Promise.all([
      ensureSessionTitle(
        sessionIdAtSend,
        message || (imagesToSend.length > 1 ? `[${imagesToSend.length} 张图片]` : '[图片]'),
        workDirAtSend
      ),
      ensureChatWsReady(),
    ])
  } else {
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
    await ensureChatWsReady()
  }

  try {
    const chatMessages = messages.value
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
      .map((m) => ({ role: m.role, content: m.content }))

    // POST /chat/completions 或 /chat/vision：返回 { status, session_id }
    // 实时数据通过 WebSocket（log_started / log_event / log_complete）推送
    if (imagesToSend.length > 0) {
      await startVision(chatMessages, imagesToSend, sessionIdAtSend, workDirAtSend)
    } else {
      await startChat(chatMessages, sessionIdAtSend, workDirAtSend)
    }
    // 重要：不在这里设置 isSending=false / isLoading=false
    // 这些由 completeLogMessage() 在收到 log_complete 事件时设置
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      messages.value.push({
        role: 'assistant',
        content: `错误: ${e.message}`,
        reasoning: [],
        tools: []
      })
    }
    isSending.value = false
    if (activeAssistantIdx != null) {
      const m = messages.value[activeAssistantIdx]
      if (m) m.isLoading = false
    }
    await nextTick()
    scheduleScrollToBottom()
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
  }
}

function markPointerActivity() {
  lastPointerActivityAt = Date.now()
  if (scrollIdleTimer) {
    clearTimeout(scrollIdleTimer)
    scrollIdleTimer = null
  }
}

function onMessagesScroll() {
  const el = messagesContainer.value
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distanceFromBottom > 64) {
    markPointerActivity()
  }
}

function scrollToBottomImmediate() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function scheduleScrollToBottom(force = false) {
  if (force) {
    if (scrollIdleTimer) {
      clearTimeout(scrollIdleTimer)
      scrollIdleTimer = null
    }
    scrollToBottomImmediate()
    return
  }

  const idleLongEnough = () => Date.now() - lastPointerActivityAt >= SCROLL_IDLE_MS

  if (idleLongEnough()) {
    scrollToBottomImmediate()
    return
  }

  if (scrollIdleTimer) return

  const wait = () => {
    scrollIdleTimer = null
    if (idleLongEnough()) {
      scrollToBottomImmediate()
    } else {
      scrollIdleTimer = setTimeout(wait, SCROLL_IDLE_MS - (Date.now() - lastPointerActivityAt))
    }
  }
  scrollIdleTimer = setTimeout(wait, SCROLL_IDLE_MS - (Date.now() - lastPointerActivityAt))
}
</script>

<style scoped>
.page {
  display: flex;
  flex: 1;
  flex-direction: row;
  overflow: hidden;
  min-height: 0;
  width: 100%;
  align-items: stretch;
  position: relative;
  background: var(--bg-content);
}

.right-panel-toggle {
  position: absolute;
  top: 8px;
  right: 48px;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.right-panel-toggle:hover {
  background: var(--accent-hover);
  color: var(--text);
  border-color: var(--border-strong);
}

.chat-todo-button {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 100;
}

.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-content);
}

/* —— 对话：空状态 —— */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 48px 80px;
  gap: 56px;
}

.welcome-title {
  font-size: 28px;
  font-weight: 400;
  color: var(--text);
  letter-spacing: -0.01em;
  text-align: center;
  max-width: 640px;
  line-height: 0.75;
  margin: 0;
}

/* —— 对话：进行中 —— */
.chat-active {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 0;
  padding: 20px 24px 16px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 0 16px;
  min-height: 0;
  width: 100%;
  max-width: 900px;
  box-sizing: border-box;
  scrollbar-width: none;
}

.chat-messages::-webkit-scrollbar {
  display: none;
}

/* —— 消息行 —— */
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
  max-width: 80%;
  padding: 10px 18px;
  background: var(--user-msg);
  color: var(--text);
  white-space: pre-wrap;
}

.assistant-bubble {
  width: 100%;
  max-width: 100%;
  padding: 12px 0;
  background: transparent;
  border: none;
  color: var(--text);
}



/* 顶部 Toast 通知 */
.page-toast {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  pointer-events: none;
  white-space: nowrap;
}

.page-toast.toast-warning {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffc107;
}

.page-toast.toast-info {
  background: #d1ecf1;
  color: #0c5460;
  border: 1px solid #17a2b8;
}

.page-toast.toast-error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #dc3545;
}

.toast-enter-active {
  transition: all 0.25s ease-out;
}

.toast-leave-active {
  transition: all 0.2s ease-in;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-12px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-12px);
}
</style>
