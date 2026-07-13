<template>
  <section id="chatPage" class="page">
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
        @toggle-side-chat="toggleRightPanel"
        @compact-done="onCompactDone"
      />
    </div>

    <!-- 对话中状态 -->
    <div v-else class="chat-active">
      <header class="chat-header">
        <div class="chat-header-start">
          <span class="chat-header-doc-icon" aria-hidden="true">
            <svg t="1782991051959" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="26670" width="14" height="14"><path d="M842.666667 981.333333H181.333333a53.393333 53.393333 0 0 1-53.333333-53.333333V96a53.393333 53.393333 0 0 1 53.333333-53.333333h466.746667a52.986667 52.986667 0 0 1 37.713333 15.62l194.586667 194.586666a52.986667 52.986667 0 0 1 15.62 37.713334V928a53.393333 53.393333 0 0 1-53.333333 53.333333zM181.333333 85.333333a10.666667 10.666667 0 0 0-10.666666 10.666667v832a10.666667 10.666667 0 0 0 10.666666 10.666667h661.333334a10.666667 10.666667 0 0 0 10.666666-10.666667V298.666667h-160a53.393333 53.393333 0 0 1-53.333333-53.333334V85.333333z m501.333334 30.166667V245.333333a10.666667 10.666667 0 0 0 10.666666 10.666667h129.833334z m21.333333 652.5H320a21.333333 21.333333 0 0 1 0-42.666667h384a21.333333 21.333333 0 0 1 0 42.666667z m0-213.333333H320a21.333333 21.333333 0 0 1 0-42.666667h384a21.333333 21.333333 0 0 1 0 42.666667zM490.666667 298.666667H320a21.333333 21.333333 0 0 1 0-42.666667h170.666667a21.333333 21.333333 0 0 1 0 42.666667z" fill="#5C5C66" p-id="26671"></path></svg>
          </span>
          <h2 class="chat-header-title" :title="displaySessionTitle">{{ displaySessionTitle }}</h2>
          <div class="chat-header-more-wrap">
            <button
              type="button"
              class="chat-header-icon-btn"
              title="更多"
              aria-label="更多"
              :aria-expanded="headerMenuOpen"
              @click.stop="headerMenuOpen = !headerMenuOpen"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="5" cy="12" r="1.5"/>
                <circle cx="12" cy="12" r="1.5"/>
                <circle cx="19" cy="12" r="1.5"/>
              </svg>
            </button>
            <div v-if="headerMenuOpen" class="chat-header-menu">
              <button type="button" class="chat-header-menu-item" @click="onHeaderRename">
                重命名
              </button>
            </div>
          </div>
        </div>
        <div class="chat-header-actions">
          <button
            type="button"
            class="chat-header-icon-btn"
            :class="{ active: bottomConsoleOpen }"
            :title="bottomConsoleOpen ? '收起控制台' : '展开控制台'"
            :aria-label="bottomConsoleOpen ? '收起控制台' : '展开控制台'"
            :aria-expanded="bottomConsoleOpen"
            @click="toggleBottomConsole"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m7 9 3 3-3 3"/>
              <path d="M13 15h4"/>
              <rect x="3" y="3" width="18" height="18" rx="2"/>
            </svg>
          </button>
          <button
            type="button"
            class="chat-header-icon-btn"
            :class="{ active: rightPanelVisible }"
            :title="rightPanelVisible ? '收起面板' : '展开面板'"
            :aria-label="rightPanelVisible ? '收起面板' : '展开面板'"
            @click="toggleRightPanel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="M15 3v18"/>
            </svg>
          </button>
        </div>
      </header>

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
      <div class="chat-composer-area">
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
        @toggle-side-chat="toggleRightPanel"
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

      <div v-show="bottomConsoleOpen" class="bottom-console-dock">
        <div
          class="bottom-console-panel"
          :style="{ height: `${bottomConsoleHeight}px` }"
        >
          <div
            class="bottom-console-resize-handle"
            title="拖动调整高度"
            @pointerdown="startConsoleResize"
            @pointermove="onConsoleResize"
            @pointerup="stopConsoleResize"
            @pointercancel="stopConsoleResize"
          />
          <ConsolePanel :visible="bottomConsoleOpen" @close="closeBottomConsole" />
        </div>
      </div>
    </div>
    </div>

    <!-- 右侧面板：浏览器/Git/Diff/临时对话 -->
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
import type { ComposerImage } from '@/components/SlashComposerInput.vue'
import UserMessageContent from '@/components/UserMessageContent.vue'
import RightPanel from '@/components/workspace/RightPanel.vue'
import ConsolePanel from '@/components/workspace/ConsolePanel.vue'
import type { ChatMessage, SubagentRecord } from '@/types/chatMessage'
import { parseToolResultForDisplay } from '@/utils/toolResultDisplay'
import {
  applyStreamEvent,
  clearPetStatus,
  flushPetStatusForComplete,
  type ApplyStreamEventDeps,
} from '@/utils/applyStreamEvent'
import { buildStreamEventFromLogEvent } from '@/utils/chatLogBridge'
import {
  buildSessionTitle,
  enrichUserMessage,
  findAssistantMessageIndex as findAssistantIdx,
  mapRawMessagesToChat,
  messageHasRunningWork,
  parseStoredImagePaths,
  sessionHasActiveWork,
} from '@/utils/chatMessageHelpers'
import { rebuildAssistantFromJsonl } from '@/utils/jsonlCatchUp'
import {
  enqueueLogEvent,
  enqueueSubagentLogEvent,
  flushLogEventsNow,
  setLogEventBatchHandler,
  type LogEventBatchItem,
} from '@/utils/logEventBatcher'
import { streamDiag, setStreamDebugEnabled } from '@/utils/streamDebug'
import { handleSubagentLogPayload } from '@/utils/chatSubagentWs'
import { bindSubagentLogBatch, isSubagentLogBatchBound, unbindSubagentLogBatch } from '@/utils/chatSubagentBatchBridge'

/** 子 Agent 内嵌细节由 JSONL batch 渲染；stream_event 仅保留 subagent_event 状态更新 */
const SUBAGENT_GRANULAR_STREAM_TYPES = new Set([
  'subagent_reasoning',
  'subagent_content',
  'subagent_tool_call',
  'subagent_tool_result',
])
import {
  buildMessageFromSnapshotEvents,
  buildReasoningContentFallback,
} from '@/utils/chatSnapshotApply'
import {
  completeLogMessageSnapshot,
  ensureLogPlaceholderSnapshot,
  findAssistantMessageIndexInSnapshot,
  getOrCreateSnapshot,
} from '@/utils/chatSnapshotStore'
import { normalizeRunMetadata, mergeRunMeta, type RunMeta } from '@/utils/runMetadata'
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
  workingSessionIds,
} from '@/utils/sessionWorkStore'
import { parseSseEvents } from '@/api/chat'
import {
  saveSessionSnapshot,
  loadSessionSnapshot,
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
const bottomConsoleOpen = ref(false)
const bottomConsoleHeight = ref(280)
const BOTTOM_CONSOLE_MIN_HEIGHT = 120
const BOTTOM_CONSOLE_MAX_HEIGHT = 560
let consoleResizing = false
let consoleResizeStartY = 0
let consoleResizeStartHeight = 0
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
/** working session 健康检查定时器 */
let healthCheckTimer: ReturnType<typeof setInterval> | null = null
const emptyComposerRef = ref<InstanceType<typeof ChatComposer>>()
const activeComposerRef = ref<InstanceType<typeof ChatComposer>>()
const currentSessionId = ref<string | undefined>(undefined)
const currentSessionTitle = ref('')
const headerMenuOpen = ref(false)
const contextUsagePercent = ref(0)
const contextUsageBreakdown = ref<import('@/api/sessions').ContextUsageInfo | null>(null)

// 当前 assistant message_id（用于把 log_event 路由到正确的消息）
let activeAssistantMessageId: number | null = null
let activeAssistantIdx: number | null = null
// 多 session SSE 流管理：每个 session 一条独立 HTTP 流，切换对话时后台继续跑
interface StreamEntry {
  abortCtrl: AbortController
  bufferedEvents: Array<{ event: string; data: Record<string, unknown> }>
}
const activeStreams = new Map<string, StreamEntry>()
/** 后台 SSE 流上限：超过此数量时自动 abort 最早的非当前会话流，避免 HTTP 连接耗尽 */
const MAX_BACKGROUND_STREAMS = 2
/** 用户已请求停止的 session 集合：忽略后端延迟到达的内容消息，避免停止后仍在输出 */
const stoppedSessions = new Set<string>()
/** run_metadata 可能在 log_complete 之后到达，先缓存，完成时统一写入 */
const pendingRunMetaByMessageId = new Map<number, RunMeta>()

const displaySessionTitle = computed(() => {
  const stored = currentSessionTitle.value.trim()
  if (stored) return stored
  const firstUser = messages.value.find((m) => m.role === 'user')
  if (firstUser?.content) return buildSessionTitle(firstUser.content)
  return '新对话'
})

function toggleRightPanel() {
  rightPanelVisible.value = !rightPanelVisible.value
}

function toggleBottomConsole() {
  bottomConsoleOpen.value = !bottomConsoleOpen.value
}

function closeBottomConsole() {
  bottomConsoleOpen.value = false
}

function openBottomConsole() {
  bottomConsoleOpen.value = true
}

function startConsoleResize(e: PointerEvent) {
  consoleResizing = true
  consoleResizeStartY = e.clientY
  consoleResizeStartHeight = bottomConsoleHeight.value
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onConsoleResize(e: PointerEvent) {
  if (!consoleResizing) return
  const delta = consoleResizeStartY - e.clientY
  bottomConsoleHeight.value = Math.min(
    Math.max(consoleResizeStartHeight + delta, BOTTOM_CONSOLE_MIN_HEIGHT),
    BOTTOM_CONSOLE_MAX_HEIGHT,
  )
}

function stopConsoleResize(e: PointerEvent) {
  if (!consoleResizing) return
  consoleResizing = false
  try {
    ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  } catch {
    // ignore
  }
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

function onHeaderRename() {
  headerMenuOpen.value = false
  if (!currentSessionId.value) return
  window.dispatchEvent(new CustomEvent('aries:rename-session', {
    detail: { sessionId: currentSessionId.value },
  }))
}

function closeHeaderMenu() {
  headerMenuOpen.value = false
}

async function refreshCurrentSessionTitle(sessionId?: string) {
  const sid = sessionId || currentSessionId.value
  if (!sid) return
  try {
    const meta = await getSession(sid)
    if (sid === currentSessionId.value) {
      currentSessionTitle.value = meta?.title?.trim() || ''
    }
  } catch {
    // ignore
  }
}

function onRefreshSessions() {
  void refreshCurrentSessionTitle()
}

// 实时数据通过 SSE 推送，后台 session 事件写入快照

/**
 * 为 log_started 事件创建/定位 assistant placeholder
 * 若该 message_id 已在 messages 中（断线重连场景），复用并把 isLoading 置为 true
 */
function ensureLogPlaceholder(messageId: number, jsonlPath: string) {
  if (!currentSessionId.value) return
  let idx = messages.value.findIndex(
    (m) => m.role === 'assistant' && m.messageId === messageId
  )
  if (idx < 0) {
    const last = messages.value[messages.value.length - 1]
    if (
      last?.role === 'assistant' &&
      last.isLoading &&
      (!last.messageId || last.messageId === messageId)
    ) {
      idx = messages.value.length - 1
    }
  }
  if (idx < 0) {
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
    const m = messages.value[idx]
    messages.value[idx] = {
      ...m,
      isLoading: true,
      messageId,
      messageSnapshotJson: jsonlPath || m.messageSnapshotJson,
    }
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
  streamDiag('State', 'ensureLogPlaceholder', streamStateSnapshot({ messageId, jsonlPath }))
  nextTick(() => scheduleScrollToBottom(true))
}

function applyMetaToMessage(messageId: number, meta: RunMeta): boolean {
  const idx = findAssistantMessageIndex(messageId)
  if (idx < 0) return false
  const msg = messages.value[idx]
  if (!msg || msg.role !== 'assistant') return false
  messages.value[idx] = { ...msg, meta: mergeRunMeta(msg.meta, meta) }
  return true
}

function stashRunMetadata(messageId: number, raw: unknown) {
  if (!messageId) return
  const meta = normalizeRunMetadata(raw)
  if (!meta.model && !meta.duration_ms && !meta.token_usage) return
  const prev = pendingRunMetaByMessageId.get(messageId)
  const merged = mergeRunMeta(prev, meta)
  pendingRunMetaByMessageId.set(messageId, merged)
  applyMetaToMessage(messageId, merged)
}

/** 终态 run_metadata（写盘那条）视为任务结束信号；流中间的 snapshot 无 final 标记 */
function isFinalRunMetadata(event: Record<string, unknown>): boolean {
  return event.final === true
}

/**
 * 将 JSONL/WS 事件转为 StreamEvent（供批量/单条共用）
 */
function buildStreamEventFromLogRecord(event: Record<string, any>): StreamEvent | null {
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
    case 'tool_result': {
      let output = ''
      let screenshotPreview = ''
      let screenshotPath = ''
      if (typeof event.result === 'string') {
        const parsed = parseToolResultForDisplay(event.result, event.tool_name)
        output = parsed.displayText
        screenshotPreview = parsed.screenshotPreview || ''
        screenshotPath = parsed.screenshotPath || ''
      } else {
        output = event.result?.output || event.output || ''
      }
      return {
        type: 'tool_result',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          output,
          screenshot_preview: screenshotPreview || undefined,
          screenshot_path: screenshotPath || undefined,
          file_change: event.file_change,
          session_id: event.session_id || '',
        },
      }
    }
    case 'confirmation_required':
      return {
        type: 'confirmation_required',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          command: event.command,
          danger_info: event.danger_info,
          danger_types: event.danger_types,
          args: event.args,
        },
      }
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
          error: event.error,
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

function resolveLogEventTarget(messageId: number, jsonlPath: string): number | null {
  let idx = messageId > 0 ? findAssistantMessageIndex(messageId) : activeAssistantIdx
  if (idx == null || idx < 0) {
    ensureLogPlaceholder(messageId, jsonlPath)
    idx = activeAssistantIdx
  } else {
    activeAssistantIdx = idx
    activeAssistantMessageId = messageId
  }
  return idx
}

function commitPendingAssistantUpdates(pending: Map<number, ChatMessage>) {
  for (const [idx, msg] of pending) {
    messages.value[idx] = { ...msg }
  }
  pending.clear()
}

function applyLogEventBatch(items: LogEventBatchItem[]) {
  if (!currentSessionId.value || !items.length) return
  const pending = new Map<number, ChatMessage>()
  let needsScroll = false

  for (const { event, messageId, jsonlPath } of items) {
    const evtType = event.type as string

    if (evtType === 'run_metadata') {
      stashRunMetadata(messageId, event)
      if (isFinalRunMetadata(event as Record<string, unknown>)) {
        commitPendingAssistantUpdates(pending)
        streamDiag('Event', 'applyLogEvent run_metadata(final) → complete', streamStateSnapshot({ messageId }))
        stoppedSessions.delete(currentSessionId.value || '')
        completeLogMessage(messageId)
      }
      continue
    }
    if (evtType === 'error_event') {
      const idx = resolveLogEventTarget(messageId, jsonlPath)
      if (idx != null) {
        let msg = pending.get(idx) ?? messages.value[idx]
        if (msg?.role === 'assistant') {
          const streamEvt = buildStreamEventFromLogRecord(event as Record<string, any>)
          if (streamEvt) {
            pushStreamEvent(msg, streamEvt)
            pending.set(idx, msg)
          }
        }
      }
      commitPendingAssistantUpdates(pending)
      stoppedSessions.delete(currentSessionId.value || '')
      completeLogMessage(messageId)
      syncSessionWorkingState()
      nextTick(() => scheduleScrollToBottom())
      continue
    }
    if (evtType === 'log_complete') {
      commitPendingAssistantUpdates(pending)
      streamDiag('Event', 'applyLogEvent log_complete (nested)', streamStateSnapshot({ messageId }))
      completeLogMessage(messageId)
      continue
    }

    const idx = resolveLogEventTarget(messageId, jsonlPath)
    if (idx == null) continue

    let msg = pending.get(idx) ?? messages.value[idx]
    if (!msg || msg.role !== 'assistant') continue

    const streamEvt = buildStreamEventFromLogRecord(event as Record<string, any>)
    if (!streamEvt) continue

    pushStreamEvent(msg, streamEvt)
    pending.set(idx, msg)
    maybeAutoConfirmTool(streamEvt, msg, idx, false)

    if (streamEvt.type === 'todo_update' && streamEvt.data?.todos) {
      window.dispatchEvent(new CustomEvent('aries:todo-update', {
        detail: {
          sessionId: currentSessionId.value || '',
          todos: streamEvt.data.todos,
        },
      }))
    }
    needsScroll = true
  }

  commitPendingAssistantUpdates(pending)
  syncSessionWorkingState()
  if (needsScroll) nextTick(() => scheduleScrollToBottom())
}

/**
 * 将后端 JSONL 事件应用到 UI（无需重新拉取 JSONL）
 */
function applyLogEvent(event: Record<string, any>, messageId: number, jsonlPath: string) {
  applyLogEventBatch([{ event, messageId, jsonlPath }])
}

function findAssistantMessageIndex(messageId: number): number {
  return findAssistantIdx(messages.value, messageId, activeAssistantIdx)
}

/**
 * log_complete：标记当前 placeholder 完成，更新 isLoading / isSending
 */
function completeLogMessage(messageId: number) {
  flushLogEventsNow()
  streamDiag('State', 'completeLogMessage → UI idle', streamStateSnapshot({ messageId, source: 'log_complete' }))
  let idx = findAssistantMessageIndex(messageId)
  if (idx < 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant' && messages.value[i].isLoading) {
        idx = i
        break
      }
    }
  }
  const pendingMeta = messageId ? pendingRunMetaByMessageId.get(messageId) : undefined
  if (idx >= 0) {
    const m = messages.value[idx]
    if (m) {
      const resolvedMessageId = messageId || m.messageId
      messages.value[idx] = {
        ...m,
        isLoading: false,
        messageId: resolvedMessageId || m.messageId,
        meta: pendingMeta || m.meta,
      }
    }
  }
  if (messageId) pendingRunMetaByMessageId.delete(messageId)
  if (currentSessionId.value) {
    const stopId = messageId || (idx >= 0 ? messages.value[idx]?.messageId : undefined)
    stopStreamDuration(currentSessionId.value, stopId || '__pending__')
  }

  if (!messageId || activeAssistantMessageId === messageId) {
    activeAssistantMessageId = null
    activeAssistantIdx = null
  }
  if (isPlatformSession(currentSessionId.value)) {
    platformStreaming = false
  }
  isSending.value = false
  flushPetStatusForComplete()
  clearPetStatus()
  syncSessionWorkingState()
  if (currentSessionId.value) {
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
  }
}

// 平台流式输出状态
let platformStreaming: boolean = false

const PLATFORM_SESSION_IDS = new Set(['__wechat__', '__qq__', '__feishu__'])

function isPlatformSession(sessionId?: string | null): boolean {
  return !!sessionId && PLATFORM_SESSION_IDS.has(sessionId)
}

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
  pushStreamEvent(assistantMsg, evt)
  messages.value[assistantIdx] = { ...assistantMsg }
  maybeAutoConfirmTool(evt, assistantMsg, assistantIdx)
  nextTick(() => scheduleScrollToBottom())
}

function maybeAutoConfirmTool(
  evt: StreamEvent,
  msg: ChatMessage,
  idx: number,
  commit = true,
) {
  if (evt.type !== 'confirmation_required' || !evt.data) return
  const dangerTypes: string[] = evt.data.danger_types || []
  const command = String(evt.data.command || '').trim()
  if (privacyStore.needsConfirmation(dangerTypes, command)) return
  const toolCallId = evt.data.tool_call_id as string
  if (msg.blocks) {
    for (const block of msg.blocks) {
      if (block.type === 'tool' && block.tool_call_id === toolCallId && block.pending_confirmation) {
        block.pending_confirmation = false
        block.status = 'running'
      }
    }
  }
  if (commit) messages.value[idx] = { ...msg }
  confirmTool(toolCallId, true).catch(() => {})
  autoConfirmedToolIds.add(toolCallId)
}

function ensurePlatformUserMessage(preview: string) {
  const text = preview.trim()
  if (!text || !currentSessionId.value) return

  const insertAt = activeAssistantIdx != null ? activeAssistantIdx : messages.value.length
  const prev = insertAt > 0 ? messages.value[insertAt - 1] : undefined
  if (prev?.role === 'user' && (prev.content === text || prev.content?.endsWith(text))) return

  messages.value.splice(insertAt, 0, {
    role: 'user',
    ...enrichUserMessage(text),
    reasoning: [],
    tools: [],
    blocks: [],
  })
  if (activeAssistantIdx != null) {
    activeAssistantIdx += 1
  }
  hasActiveChat.value = true
  nextTick(() => scheduleScrollToBottom(true))
}

// 加载当前 session 的新消息（完整重载，处理新增和更新）
async function loadNewMessages(force: boolean = false) {
  if (!currentSessionId.value) return
  // 用户正在从网页发送消息时跳过，避免打断流式输出（force 时除外：切换 session / 重连后恢复）
  if (isSending.value && !force) return
  // 平台流式输出进行中时跳过，避免打断实时更新
  if (platformStreaming && !force) return
  // 后台仍在跑时不要用 DB 快照覆盖内存中的流式 UI
  if (force && sessionHasActiveWork(messages.value, isSending.value)) {
    const running = await checkChatStatus(currentSessionId.value)
    if (running === true) {
      restoreRunningAssistantUi()
      syncSessionWorkingState()
      return
    }
  }
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

    // 异步加载所有尚未加载快照的助手消息
    for (let i = 0; i < allMsgs.length; i++) {
      if (allMsgs[i].role !== 'assistant') continue
      const messageId = allMsgs[i].id
      if (!messageId) continue
      // 跳过已加载 blocks 的消息，避免 SSE 事件反复触发 jsonl 请求
      const existing = messages.value[i]
      if (existing?.blocks && existing.blocks.length > 0) continue
      await loadMessageSnapshot(messageId, i, allMsgs[i])
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

function clearComposerCommand() {
  activeSlashCommand.value = null
  commandObjective.value = ''
}

const messages = ref<ChatMessage[]>([])

/** 仅看消息区 loading-dots（三个点）：还在就不算终止 */
const composerIsSending = computed(() =>
  messages.value.some((m) => m.role === 'assistant' && m.isLoading === true),
)

/** 诊断用：当前流式/UI 状态快照（安全，不抛错） */
function streamStateSnapshot(extra?: Record<string, unknown>) {
  try {
    const sid = currentSessionId.value
    return {
      sessionId: sid,
      isSending: isSending.value,
      isSessionWorking: sid ? isSessionWorking(sid) : false,
      activeAssistantMessageId,
      activeAssistantIdx,
      loadingAssistantCount: messages.value.filter((m) => m?.role === 'assistant' && m.isLoading).length,
      ...extra,
    }
  } catch {
    return { ...(extra || {}) }
  }
}

/** 清除过期的 sending / loading UI（仅在后端确认已结束时调用） */
function clearStaleSendingUi(reason = 'unknown') {
  streamDiag('State', 'clearStaleSendingUi', streamStateSnapshot({ reason }))
  isSending.value = false
  let changed = false
  messages.value = messages.value.map((m) => {
    if (m.role === 'assistant' && m.isLoading) {
      changed = true
      return { ...m, isLoading: false }
    }
    return m
  })
  if (changed || !sessionHasActiveWork(messages.value, false)) {
    syncSessionWorkingState()
  }
}

// 本会话所有子 Agent 委派记录（按 task_id 去重 upsert）
const sessionSubagents = ref<SubagentRecord[]>([])

function captureSessionSnapshot(): SessionChatSnapshot {
  return {
    messages: messages.value.slice(),
    isSending: isSending.value,
    hasActiveChat: hasActiveChat.value,
    activeAssistantMessageId,
    activeAssistantIdx,
    sessionSubagents: sessionSubagents.value.slice(),
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

// debounce 快照持久化：SSE 事件高频到达时避免每个事件都做快照
let _persistTimer: ReturnType<typeof setTimeout> | null = null
function persistCurrentSessionSnapshotDebounced(sessionId?: string) {
  const sid = sessionId || currentSessionId.value
  if (!sid) return
  if (_persistTimer) clearTimeout(_persistTimer)
  _persistTimer = setTimeout(() => {
    _persistTimer = null
    persistCurrentSessionSnapshot(sid)
  }, 500)
}

function syncSessionWorkingState(sessionId?: string) {
  const sid = sessionId || currentSessionId.value
  if (!sid) return
  // 用户已请求停止：强制 idle，不因后端延迟到达的消息恢复 working 状态
  if (stoppedSessions.has(sid)) {
    markSessionIdle(sid)
    persistCurrentSessionSnapshotDebounced(sid)
    return
  }
  const isCurrent = sid === currentSessionId.value
  const snapshot = isCurrent ? null : loadSessionSnapshot(sid)
  const msgs = isCurrent ? messages.value : (snapshot?.messages as ChatMessage[] | undefined) ?? []
  const sending = isCurrent ? isSending.value : !!snapshot?.isSending
  const working = sessionHasActiveWork(msgs, sending)
  const prevWorking = isSessionWorking(sid)
  if (working) markSessionWorking(sid)
  else markSessionIdle(sid)
  if (prevWorking !== working) {
    streamDiag('State', 'syncSessionWorkingState', streamStateSnapshot({
      sid,
      working,
      prevWorking,
      sending,
      loadingAssistantCount: msgs.filter((m) => m && (m as ChatMessage).role === 'assistant' && (m as ChatMessage).isLoading).length,
    }))
  }
  persistCurrentSessionSnapshotDebounced(sid)
}

function syncSnapshotWorkingState(sessionId: string, snapshot: SessionChatSnapshot) {
  const working = sessionHasActiveWork(
    snapshot.messages as ChatMessage[],
    snapshot.isSending,
  )
  if (working) markSessionWorking(sessionId)
  else markSessionIdle(sessionId)
}

/** 后端仍在跑但 UI 丢失 loading 时，恢复输入框停止按钮与消息 loading 态 */
function restoreRunningAssistantUi(reason = 'unknown') {
  if (!currentSessionId.value) return
  streamDiag('State', 'restoreRunningAssistantUi', streamStateSnapshot({ reason }))
  isSending.value = true

  let idx = activeAssistantIdx
  if (idx == null || messages.value[idx]?.role !== 'assistant') {
    if (activeAssistantMessageId) {
      idx = findAssistantMessageIndex(activeAssistantMessageId)
    }
  }
  if (idx == null || idx < 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messageHasRunningWork(messages.value[i])) {
        idx = i
        break
      }
    }
  }
  if (idx == null || idx < 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        idx = i
        break
      }
    }
  }
  if (idx == null || idx < 0) return

  const m = messages.value[idx]
  if (m && !m.isLoading) {
    messages.value[idx] = { ...m, isLoading: true }
  }
  activeAssistantIdx = idx
}

async function catchUpActiveAssistantFromJsonl(sessionId: string): Promise<boolean> {
  if (sessionId !== currentSessionId.value) return false
  streamDiag('Resume', 'catchUpActiveAssistantFromJsonl start', streamStateSnapshot({ sessionId }))

  let messageId = activeAssistantMessageId
  let idx = messageId ? findAssistantMessageIndex(messageId) : activeAssistantIdx

  if (idx == null || idx < 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.role === 'assistant' && (m.isLoading || messageHasRunningWork(m))) {
        idx = i
        messageId = m.messageId || null
        break
      }
    }
  }

  if (idx == null || idx < 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        idx = i
        messageId = messages.value[i].messageId || null
        break
      }
    }
  }

  if (idx == null || idx < 0 || !messageId) {
    streamDiag('Resume', 'catchUp skip: no messageId', streamStateSnapshot({ sessionId }))
    return false
  }

  const prev = messages.value[idx]
  if (!prev || prev.role !== 'assistant') return false

  try {
    const rebuilt = await rebuildAssistantFromJsonl(
      modelStore.getBaseUrl(),
      messageId,
      prev,
      upsertSubagent,
    )
    if (!rebuilt) {
      streamDiag('Resume', 'catchUp skip: empty jsonl', streamStateSnapshot({ sessionId, messageId }))
      return false
    }

    const running = await checkChatStatus(sessionId)
    streamDiag('Resume', 'catchUp jsonl rebuilt', streamStateSnapshot({
      sessionId,
      messageId,
      backendRunning: running,
      contentLen: rebuilt.content?.length ?? 0,
    }))
    // 仅在后端明确 false 时才清 loading；null（网络抖动）保持 loading，交由权威轮询纠正
    const stillRunning = running !== false
    messages.value[idx] = {
      ...rebuilt,
      isLoading: stillRunning,
    }
    activeAssistantMessageId = messageId
    activeAssistantIdx = idx
    if (stillRunning) {
      isSending.value = true
      markSessionWorking(sessionId)
    }
    return true
  } catch (err) {
    streamDiag('Resume', 'catchUp failed', streamStateSnapshot({
      sessionId,
      messageId,
      error: String((err as Error)?.message || err),
    }))
    return false
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
    if (event.final === true) {
      completeLogMessageSnapshot(snapshot, sessionId, messageId)
    }
    return
  }
  if (event.type === 'error_event') {
    let idx = messageId > 0
      ? findAssistantMessageIndexInSnapshot(snapshot, messageId)
      : snapshot.activeAssistantIdx
    if (idx == null || idx < 0) {
      ensureLogPlaceholderSnapshot(snapshot, sessionId, messageId, jsonlPath)
      idx = snapshot.activeAssistantIdx
    }
    if (idx != null && idx >= 0) {
      const msg = snapshot.messages[idx] as ChatMessage | undefined
      if (msg?.role === 'assistant') {
        const streamEvt = buildStreamEventFromLogEvent(event)
        if (streamEvt && streamEvt !== 'complete') {
          pushStreamEvent(msg, streamEvt, { silent: true, subagents: snapshot.sessionSubagents as SubagentRecord[] })
          snapshot.messages[idx] = { ...msg }
        }
      }
    }
    completeLogMessageSnapshot(snapshot, sessionId, messageId)
    return
  }
  if (event.type === 'log_complete') {
    completeLogMessageSnapshot(snapshot, sessionId, messageId)
    return
  }

  let idx = messageId > 0
    ? findAssistantMessageIndexInSnapshot(snapshot, messageId)
    : snapshot.activeAssistantIdx
  if (idx == null || idx < 0) {
    ensureLogPlaceholderSnapshot(snapshot, sessionId, messageId, jsonlPath)
    idx = snapshot.activeAssistantIdx
  } else {
    snapshot.activeAssistantIdx = idx
    snapshot.activeAssistantMessageId = messageId
  }
  if (idx == null) return
  const msg = snapshot.messages[idx] as ChatMessage | undefined
  if (!msg || msg.role !== 'assistant') return

  const streamEvt = buildStreamEventFromLogEvent(event)
  if (streamEvt === 'complete') {
    completeLogMessageSnapshot(snapshot, sessionId, messageId)
    return
  }
  if (!streamEvt) return

  pushStreamEvent(msg, streamEvt, { silent: true, subagents: snapshot.sessionSubagents as SubagentRecord[] })
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

/** 后台 session 的 SSE 事件：只写快照，不切换当前 UI（避免输入框闪烁） */
function applySsePayloadToSnapshot(sessionId: string, data: Record<string, unknown>) {
  const snapshot = getOrCreateSnapshot(sessionId, loadSessionSnapshot)

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
  } else if (
    data.type === 'subagent_log_started'
    || data.type === 'subagent_log_event'
    || data.type === 'subagent_log_complete'
  ) {
    snapshot.messages = handleSubagentLogPayload(
      data,
      snapshot.messages as ChatMessage[],
    ) as SessionChatSnapshot['messages']
  }

  saveSessionSnapshot(sessionId, snapshot)
  syncSnapshotWorkingState(sessionId, snapshot)
}

async function processSsePayload(data: Record<string, unknown>) {
  if (data.type === 'log_started') {
    const newMsgId = Number(data.message_id) || 0
    if (newMsgId) {
      activeAssistantMessageId = newMsgId
      if (isPlatformSession(currentSessionId.value)) {
        platformStreaming = true
      }
      ensureLogPlaceholder(newMsgId, String(data.jsonl_path || ''))
      syncSessionWorkingState()
    }
  } else if (data.type === 'log_event') {
    const evt = data.event as Record<string, unknown> | undefined
    const evtMessageId = Number(data.message_id) || activeAssistantMessageId || 0
    if (!evt) return
    if (evtMessageId && (!activeAssistantMessageId || evtMessageId !== activeAssistantMessageId)) {
      activeAssistantMessageId = evtMessageId
      ensureLogPlaceholder(evtMessageId, String(data.jsonl_path || ''))
    }
    enqueueLogEvent({
      event: evt,
      messageId: evtMessageId || activeAssistantMessageId || 0,
      jsonlPath: String(data.jsonl_path || ''),
    })
  } else if (data.type === 'log_complete') {
    flushLogEventsNow()
    streamDiag('Event', 'processSsePayload log_complete (top-level)', streamStateSnapshot({
      messageId: data.message_id,
    }))
    stoppedSessions.delete(currentSessionId.value || '')
    completeLogMessage(Number(data.message_id) || 0)
  } else if (data.type === 'subagent_log_started' || data.type === 'subagent_log_event') {
    enqueueSubagentLogEvent({
      type: data.type,
      task_id: data.task_id,
      jsonl_path: data.jsonl_path || '',
      tool_call_id: data.tool_call_id || '',
      subagent: data.subagent || '',
      ...(data.type === 'subagent_log_event' ? { event: data.event } : {}),
    })
    syncSessionWorkingState()
  } else if (data.type === 'subagent_log_complete') {
    flushLogEventsNow()
    messages.value = handleSubagentLogPayload(data, messages.value)
    syncSessionWorkingState()
    nextTick(() => scheduleScrollToBottom())
  } else if (data.type === 'stream_event') {
    const event = data.event as Record<string, unknown> | undefined
    if (!event) return
    const streamEvt = jsonToStreamEvent(event)
    // 子 Agent 内嵌细节已由 subagent_log_event（JSONL）推送；stream_event 仅保留状态更新
    if (streamEvt && isSubagentLogBatchBound() && SUBAGENT_GRANULAR_STREAM_TYPES.has(streamEvt.type)) {
      return
    }
    if (streamEvt?.type === 'subagent_event') {
      const lastIdx = messages.value.length - 1
      const lastAssistant = messages.value[lastIdx]
      if (lastAssistant?.role === 'assistant') {
        pushStreamEvent(lastAssistant, streamEvt)
        messages.value[lastIdx] = { ...lastAssistant }
      }
      syncSessionWorkingState()
      return
    }
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
    } else if (!isPlatformSession(currentSessionId.value) && !event.choices) {
      // Agent 会话正文/工具/错误已由 log_event (JSONL) 推送；stream_event.error 与之重复
      if (event.error) {
        syncSessionWorkingState()
        return
      }
      handlePlatformStreamEvent(event)
    }
    syncSessionWorkingState()
  } else if (data.type === 'new_message') {
    if (
      isPlatformSession(currentSessionId.value) &&
      data.role === 'user' &&
      platformStreaming
    ) {
      ensurePlatformUserMessage(String(data.preview || ''))
    } else {
      await loadNewMessages()
    }
  } else if (data.type === 'session_update') {
    stoppedSessions.delete(currentSessionId.value || '')
    platformStreaming = false
    clearPetStatus()
    await loadNewMessages(true)
    syncSessionWorkingState()
  }
}

/**
 * SSE 事件分发：将 SSE 事件映射到 processSsePayload 能处理的格式。
 * 如果事件属于当前查看的 session → 直接渲染；否则写入 buffer 等切回时 replay。
 */
async function handleSseEvent(sessionId: string, sseEvent: string, data: Record<string, unknown>) {
  // 非当前 session：写入 buffer
  if (sessionId !== currentSessionId.value) {
    const entry = activeStreams.get(sessionId)
    if (entry) {
      entry.bufferedEvents.push({ event: sseEvent, data })
    }
    return
  }

  // 当前 session：直接渲染
  if (sseEvent === 'log_started') {
    await processSsePayload({
      type: 'log_started',
      session_id: sessionId,
      message_id: data.message_id,
      jsonl_path: data.jsonl_path || '',
    })
  } else if (sseEvent === 'log_event') {
    await processSsePayload({
      type: 'log_event',
      session_id: sessionId,
      event: data,
      message_id: data.message_id ?? activeAssistantMessageId,
      jsonl_path: data.jsonl_path || '',
    })
  } else if (sseEvent === 'stream_event') {
    await processSsePayload({
      type: 'stream_event',
      session_id: sessionId,
      event: data,
    })
  } else if (sseEvent === 'log_complete') {
    await processSsePayload({
      type: 'log_complete',
      session_id: sessionId,
      message_id: data.message_id,
      jsonl_path: data.jsonl_path || '',
    })
  } else if (sseEvent === 'subagent_log_started') {
    await processSsePayload({
      type: 'subagent_log_started',
      session_id: sessionId,
      task_id: data.task_id,
      jsonl_path: data.jsonl_path || '',
      tool_call_id: data.tool_call_id || '',
      subagent: data.subagent || '',
    })
  } else if (sseEvent === 'subagent_log_event') {
    await processSsePayload({
      type: 'subagent_log_event',
      session_id: sessionId,
      task_id: data.task_id,
      jsonl_path: data.jsonl_path || '',
      tool_call_id: data.tool_call_id || '',
      subagent: data.subagent || '',
      event: data.event,
    })
  } else if (sseEvent === 'subagent_log_complete') {
    await processSsePayload({
      type: 'subagent_log_complete',
      session_id: sessionId,
      task_id: data.task_id,
      jsonl_path: data.jsonl_path || '',
      tool_call_id: data.tool_call_id || '',
    })
  } else if (sseEvent === 'error') {
    const errMsg = String(data.error || data.detail || '请求失败')
    throw Object.assign(new Error(errMsg), { running: !!data.running })
  }
}

/**
 * 切回某 session 时，把后台积攒的 buffer 事件一次性灌入。
 * log_event 走同步 applyLogEventBatch，避免异步 batch 和后续操作冲突。
 */
async function replayBufferedEvents(sessionId: string) {
  const entry = activeStreams.get(sessionId)
  if (!entry || entry.bufferedEvents.length === 0) return
  const events = entry.bufferedEvents.splice(0) // drain

  // 先清空之前的异步 batch
  flushLogEventsNow()

  // 收集 log_event 批量同步 apply
  const logEvents: LogEventBatchItem[] = []

  for (const { event, data } of events) {
    if (event === 'log_started') {
      // 先 flush 已收集的 log_event
      if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)); flushLogEventsNow() }
      await processSsePayload({
        type: 'log_started',
        session_id: sessionId,
        message_id: data.message_id,
        jsonl_path: data.jsonl_path || '',
      })
    } else if (event === 'log_event') {
      const messageId = Number(data.message_id) || 0
      if (messageId) {
        logEvents.push({
          event: data as Record<string, unknown>,
          messageId,
          jsonlPath: String(data.jsonl_path || ''),
        })
      }
    } else if (event === 'stream_event') {
      if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)); flushLogEventsNow() }
      await processSsePayload({
        type: 'stream_event',
        session_id: sessionId,
        event: data,
      })
    } else if (event === 'log_complete') {
      if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)); flushLogEventsNow() }
      await processSsePayload({
        type: 'log_complete',
        session_id: sessionId,
        message_id: data.message_id,
        jsonl_path: data.jsonl_path || '',
      })
    } else if (event === 'subagent_log_started') {
      if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)); flushLogEventsNow() }
      await processSsePayload({
        type: 'subagent_log_started',
        session_id: sessionId,
        task_id: data.task_id,
        jsonl_path: data.jsonl_path || '',
        tool_call_id: data.tool_call_id || '',
        subagent: data.subagent || '',
      })
    } else if (event === 'subagent_log_event') {
      await processSsePayload({
        type: 'subagent_log_event',
        session_id: sessionId,
        task_id: data.task_id,
        jsonl_path: data.jsonl_path || '',
        tool_call_id: data.tool_call_id || '',
        subagent: data.subagent || '',
        event: data.event,
      })
    } else if (event === 'subagent_log_complete') {
      if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)); flushLogEventsNow() }
      await processSsePayload({
        type: 'subagent_log_complete',
        session_id: sessionId,
        task_id: data.task_id,
        jsonl_path: data.jsonl_path || '',
        tool_call_id: data.tool_call_id || '',
      })
    }
  }

  // apply 剩余的 log_event
  if (logEvents.length) { applyLogEventBatch(logEvents.splice(0)) }
  flushLogEventsNow()
}

function stopChatSession(clearRouting = true) {
  const sid = currentSessionId.value
  if (sid) persistCurrentSessionSnapshot(sid)
  if (clearRouting) {
    activeAssistantMessageId = null
    activeAssistantIdx = null
  }
  // 切换对话时后台流继续跑，但限制并发数量避免 HTTP 连接耗尽
  pruneBackgroundStreams()
}

/** 后台 SSE 流数量超限时，abort 最早的非当前会话流 */
function pruneBackgroundStreams() {
  const current = currentSessionId.value
  const bgStreams = [...activeStreams.keys()].filter((sid) => sid !== current)
  while (bgStreams.length > MAX_BACKGROUND_STREAMS) {
    const oldest = bgStreams.shift()!
    abortSessionStream(oldest)
  }
}

/** 显式停止某 session 的后台 SSE 流（用户点击停止 / 组件卸载） */
function abortSessionStream(sessionId: string) {
  const entry = activeStreams.get(sessionId)
  if (entry) {
    entry.abortCtrl.abort()
    activeStreams.delete(sessionId)
  }
}

/** SSE 模式：不再需要轮询检测后端状态 */

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
        const command = String(
          block.args?.command || block.args?.file_path || block.args?.subdir || '',
        ).trim()
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

const streamEventDeps: ApplyStreamEventDeps = {
  autoConfirmedToolIds,
  onClearConfirmCountdown: clearConfirmCountdownTimer,
  upsertSubagent,
  upsertSubagentInList,
  findSubagentByTaskId,
}

function pushStreamEvent(
  msg: ChatMessage,
  evt: Parameters<typeof applyStreamEvent>[1],
  opts?: { silent?: boolean; subagents?: SubagentRecord[] },
) {
  applyStreamEvent(msg, evt, { ...opts, deps: streamEventDeps })
}

const textColor = computed(() => '#1a1a1a')
const fontSize = computed(() => 15)

// 同步默认模型（与设置页一致：selectedModel 存 model.id）
watch(() => modelStore.activeModel?.id, (id) => {
  if (id) {
    selectedModel.value = id
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
    stopChatSession(false)
  }
  // 新对话
  currentSessionId.value = undefined
  currentSessionTitle.value = ''
  bottomConsoleOpen.value = false
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
// 启动时立即从 localStorage 恢复上次工作目录，避免等待 API 时显示默认值
const workDir = ref(localStorage.getItem('aries:lastWorkDir') || defaultWorkDir.value)
const workDirHistory = ref<string[]>([])
const workDirLabel = computed(() => {
  if (!workDir.value) return 'work_dir'
  // 只显示最后一段路径名 + 父目录名，更紧凑
  const normalized = workDir.value.replace(/\\/g, '/').replace(/\/$/, '')
  const parts = normalized.split('/')
  return parts[parts.length - 1] || normalized
})

let workDirPollTimer: ReturnType<typeof setInterval> | null = null
let workDirPollAttempts = 0

async function loadWorkDir() {
  try {
    await workspaceStore.initWorkDir()
    const dir = workspaceStore.workDir
    if (dir && dir !== defaultWorkDir.value) {
      workDir.value = dir
      localStorage.setItem('aries:lastWorkDir', dir)
      loadWorkDirHistory()
      stopWorkDirPoll()
      return
    }
    // 后端返回了默认值，说明数据库可能还没初始化好，开始轮询
    startWorkDirPoll()
  } catch {
    startWorkDirPoll()
  }
}

function startWorkDirPoll() {
  if (workDirPollTimer) return
  workDirPollAttempts = 0
  workDirPollTimer = setInterval(async () => {
    workDirPollAttempts++
    try {
      await workspaceStore.initWorkDir()
      const dir = workspaceStore.workDir
      if (dir && dir !== defaultWorkDir.value) {
        workDir.value = dir
        localStorage.setItem('aries:lastWorkDir', dir)
        loadWorkDirHistory()
        stopWorkDirPoll()
        return
      }
    } catch {
      // 继续重试
    }
    if (workDirPollAttempts >= 30) {
      // 超过 30 次仍无结果，用 localStorage 缓存值或默认值
      const cached = localStorage.getItem('aries:lastWorkDir')
      if (cached) {
        workDir.value = cached
      }
      loadWorkDirHistory()
      stopWorkDirPoll()
    }
  }, 800)
}

function stopWorkDirPoll() {
  if (workDirPollTimer) {
    clearInterval(workDirPollTimer)
    workDirPollTimer = null
  }
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
  if (workDir.value) localStorage.setItem('aries:lastWorkDir', workDir.value)
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
    if (path) localStorage.setItem('aries:lastWorkDir', path)
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
  void refreshCurrentSessionTitle(id)
  if (isStaleSessionLoad(seq)) return
  // 切回此 session 时，把后台积攒的 buffer 事件一次性灌入
  await replayBufferedEvents(id)
  if (isStaleSessionLoad(seq)) return
  emit('sessionLoaded')
  // 非阻塞：切换会话不等待状态检查/补拉，避免切换卡顿
  void tryResumeSession(id)
  void refreshSessionContextUsage(id, seq)
}

function scheduleSnapshotLoads(
  msgs: ChatMessage[],
  rawMessages: Array<{ id?: number; reasoning_content?: string }> = [],
  seq: number,
): void {
  const pending: Array<{ messageId: number; index: number; raw?: { reasoning_content?: string } }> = []
  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i]
    if (!msg || msg.role !== 'assistant') continue
    if (msg.blocks && msg.blocks.length > 0) continue
    const raw = rawMessages[i]
    const messageId = raw?.id ?? msg.messageId
    if (!messageId) continue
    pending.push({ messageId, index: i, raw })
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
    currentSessionTitle.value = bootstrap.session?.title?.trim() || ''

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
        currentSessionTitle.value = metaSettled.value?.title?.trim() || ''
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

  try {
    const prevId = currentSessionId.value
    if (prevId && prevId !== id) {
      persistCurrentSessionSnapshot(prevId)
      stopChatSession(false)
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
      scheduleSnapshotLoads(cached.messages as ChatMessage[], [], seq)
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
  } catch (err) {
    console.error('[ChatPage] loadSessionById failed', id, err)
    if (!isStaleSessionLoad(seq)) {
      emit('sessionLoaded')
    }
  }
}

async function tryResumeSession(sessionId: string) {
  streamDiag('Resume', 'tryResumeSession start', streamStateSnapshot({ targetSessionId: sessionId }))
  try {
    // 有活跃的 SSE 流：数据已通过事件流到达，不需要从 JSONL 补拉
    if (activeStreams.has(sessionId)) {
      syncSessionWorkingState(sessionId)
      return
    }
    const running = await checkChatStatus(sessionId)
    streamDiag('Resume', 'tryResumeSession checkChatStatus', { sessionId, running })
    if (running === false) {
      if (sessionId === currentSessionId.value) {
        clearStaleSendingUi('tryResumeSession: backend not running')
        syncSessionWorkingState(sessionId)
      }
      return
    }
    if (running !== true) {
      streamDiag('Resume', 'tryResumeSession uncertain (null) → keep snapshot', { sessionId })
      syncSessionWorkingState(sessionId)
      return
    }
    if (sessionId === currentSessionId.value) {
      await catchUpActiveAssistantFromJsonl(sessionId)
    }
    // 找最后一条 assistant 消息
    let assistantIdx = activeAssistantIdx ?? -1
    if (assistantIdx < 0 || messages.value[assistantIdx]?.role !== 'assistant') {
      for (let i = messages.value.length - 1; i >= 0; i--) {
        if (messages.value[i].role === 'assistant') {
          assistantIdx = i
          break
        }
      }
    }
    if (assistantIdx < 0) {
      isSending.value = true
      markSessionWorking(sessionId)
      syncSessionWorkingState(sessionId)
      return
    }
    const msg = messages.value[assistantIdx]
    if (!msg.isLoading) {
      messages.value[assistantIdx] = { ...msg, isLoading: true }
    }
    activeAssistantIdx = assistantIdx
    if (msg.messageId) activeAssistantMessageId = msg.messageId
    isSending.value = true
    markSessionWorking(sessionId)
    syncSessionWorkingState(sessionId)
    streamDiag('Resume', 'tryResumeSession restored loading', streamStateSnapshot({ sessionId }))
  } catch (err) {
    streamDiag('Resume', 'tryResumeSession error', {
      sessionId,
      error: String((err as Error)?.message || err),
    })
    syncSessionWorkingState(sessionId)
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
  if (seq !== undefined && isStaleSessionLoad(seq)) return

  const next = !rawEvents?.length
    ? buildReasoningContentFallback(prev, messageId, raw?.reasoning_content)
    : buildMessageFromSnapshotEvents(prev, messageId, rawEvents, raw, upsertSubagent)
  if (next) messages.value[msgIndex] = next
}

function applyReasoningContentFallback(
  messageId: number,
  msgIndex: number,
  reasoningContent?: string | null,
) {
  const prev = messages.value[msgIndex]
  const next = buildReasoningContentFallback(prev, messageId, reasoningContent)
  if (next) messages.value[msgIndex] = next
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

function resolveWorkDirForSend(): string {
  return (pendingWorkDir.value || workDir.value || defaultWorkDir.value || '').trim()
}

async function ensureSessionTitle(sessionId: string, text: string, workDirPath?: string) {
  const title = buildSessionTitle(text)
  currentSessionTitle.value = title
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

function onHeaderMenuEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') closeHeaderMenu()
}

function onFocusConsole() {
  openBottomConsole()
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
  setLogEventBatchHandler(applyLogEventBatch)
  bindSubagentLogBatch(messages, () => {
    syncSessionWorkingState()
    nextTick(() => scheduleScrollToBottom())
  })
  ;(window as unknown as { ariesStreamDebug?: { on: () => void; off: () => void } }).ariesStreamDebug = {
    on: () => setStreamDebugEnabled(true),
    off: () => setStreamDebugEnabled(false),
  }
  window.addEventListener('aries:new-chat', onNewChat)
  window.addEventListener('aries:workdir-changed', onWorkDirChanged)
  window.addEventListener('aries:focus-console', onFocusConsole)
  window.addEventListener('aries:open-url', onOpenUrlFromMessage)
  window.addEventListener('aries:toast', onToast)
  window.addEventListener('aries:add-to-chat', onAddToChat)
  window.addEventListener('aries:select-work-dir', onSelectWorkDir)
  window.addEventListener('aries:emergency-stop', onEmergencyStopEvent)
  window.addEventListener('aries:refresh-sessions', onRefreshSessions)
  window.addEventListener('click', closeHeaderMenu)
  window.addEventListener('keydown', onHeaderMenuEsc)
  window.addEventListener('keydown', onGlobalEscKey, true)
  loadWorkDir()
  // 确保模型列表已加载（避免 MainLayout 加载未完成导致下拉框为空）
  void modelStore.loadModels()
  if (props.sessionIdToLoad) {
    void loadSessionById(props.sessionIdToLoad)
  }
  // 自动恢复桌面宠物
  restorePet()
  // SSE 模式：不再需要健康检查轮询
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
  flushLogEventsNow()
  setLogEventBatchHandler(null)
  unbindSubagentLogBatch()
  clearConfirmCountdownTimer()
  stopWorkDirPoll()
  if (healthCheckTimer) {
    clearInterval(healthCheckTimer)
    healthCheckTimer = null
  }
  if (currentSessionId.value) persistCurrentSessionSnapshot(currentSessionId.value)
  // 组件卸载：abort 所有活跃的后台 SSE 流
  for (const sid of activeStreams.keys()) {
    abortSessionStream(sid)
  }
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
  window.removeEventListener('aries:emergency-stop', onEmergencyStopEvent)
  window.removeEventListener('aries:refresh-sessions', onRefreshSessions)
  window.removeEventListener('click', closeHeaderMenu)
  window.removeEventListener('keydown', onHeaderMenuEsc)
  window.removeEventListener('keydown', onGlobalEscKey, true)
})

function onSelectWorkDir() {
  void pickWorkDir()
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
  const wd = (workDir.value || resolveWorkDirForSend() || '').trim()
  if (sessionId) {
    stoppedSessions.add(sessionId)
    abortSessionStream(sessionId)
    stopChat(sessionId, wd || undefined).catch(() => {})
    markSessionIdle(sessionId)
    syncSessionWorkingState(sessionId)
  }
  isSending.value = false
  clearPetStatus()
  for (const sa of sessionSubagents.value) {
    if (sa.status === 'running' || sa.status === 'pending' || sa.status === 'stalled') {
      sa.status = 'cancelled'
    }
  }
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

function onGlobalEscKey(e: KeyboardEvent) {
  if (e.key !== 'Escape' || e.repeat) return
  if (!composerIsSending.value) return
  e.preventDefault()
  e.stopPropagation()
  void stopGeneration()
}

function onEmergencyStopEvent() {
  if (composerIsSending.value) {
    void stopGeneration()
  }
}

async function sendMessage() {
  if (composerIsSending.value || !canSend.value) return

  const message = inputMessage.value.trim()
  const imagesToSend = attachedImages.value.map((img) => img.data)
  if (!message && imagesToSend.length === 0) return

  const sessionIdAtSend = currentSessionId.value || crypto.randomUUID().replace(/-/g, '')
  // 不做发送前的阻塞式状态检查（避免每次发送多一次网络往返导致卡顿）：
  // 后端 is_bg_running 会拒绝并发请求，前端在 catch 中按 e.running 处理。

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
    await ensureSessionTitle(
      sessionIdAtSend,
      message || (imagesToSend.length > 1 ? `[${imagesToSend.length} 张图片]` : '[图片]'),
      workDirAtSend
    )
  } else {
    window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
  }

  const abortCtrl = new AbortController()
  // 若同一 session 已有旧流（重复 send），先 abort 旧流再覆盖，避免 AbortController 引用泄漏
  const oldEntry = activeStreams.get(sessionIdAtSend)
  if (oldEntry) {
    oldEntry.abortCtrl.abort()
  }
  activeStreams.set(sessionIdAtSend, { abortCtrl, bufferedEvents: [] })

  try {
    const chatMessages = messages.value
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
      .map((m) => ({ role: m.role, content: m.content }))

    // POST /chat/completions 或 /chat/vision，返回 SSE Response
    const res = imagesToSend.length > 0
      ? await startVision(chatMessages, imagesToSend, sessionIdAtSend, workDirAtSend, abortCtrl.signal)
      : await startChat(chatMessages, sessionIdAtSend, workDirAtSend, abortCtrl.signal)

    // 读取 SSE 事件流：即使切换到其他 session，此循环仍在后台继续
    for await (const { event, data } of parseSseEvents(res)) {
      if (abortCtrl.signal.aborted) break
      await handleSseEvent(sessionIdAtSend, event, data)
    }
    flushLogEventsNow()
    // SSE 连接关闭后兜底：若 log_complete 未到达或 messageId 未匹配，仍结束 loading 态
    if (sessionIdAtSend === currentSessionId.value) {
      const stillLoading = messages.value.some((m) => m.role === 'assistant' && m.isLoading)
      if (stillLoading) {
        completeLogMessage(activeAssistantMessageId || 0)
      }
    } else {
      const snapshot = loadSessionSnapshot(sessionIdAtSend)
      if (snapshot?.isSending) {
        completeLogMessageSnapshot(snapshot, sessionIdAtSend, snapshot.activeAssistantMessageId || 0)
        saveSessionSnapshot(sessionIdAtSend, snapshot)
      }
    }
    // 重要：isSending / isLoading 主要由 completeLogMessage(log_complete) 设置；上方为兜底
  } catch (e: any) {
    // running 错误只在发送时发生（当前 session 一定是活跃的）
    if (e?.running) {
      messages.value.splice(assistantIdx - 1, 2)
      inputMessage.value = message
      isSending.value = false
      await catchUpActiveAssistantFromJsonl(sessionIdAtSend)
      restoreRunningAssistantUi()
      syncSessionWorkingState(sessionIdAtSend)
      showToast(e.message || '当前仍在生成中', 'warning')
      return
    }
    // 非 abort 错误：只在当前 session 显示错误，后台 session 静默处理
    if (e?.name !== 'AbortError' && sessionIdAtSend === currentSessionId.value) {
      messages.value.push({
        role: 'assistant',
        content: `错误: ${e.message}`,
        reasoning: [],
        tools: []
      })
    }
    if (sessionIdAtSend === currentSessionId.value) {
      isSending.value = false
      if (activeAssistantIdx != null) {
        const m = messages.value[activeAssistantIdx]
        if (m) m.isLoading = false
      }
      await nextTick()
      scheduleScrollToBottom()
      window.dispatchEvent(new CustomEvent('aries:refresh-sessions'))
    } else {
      // 后台 session 出错：标记为 idle，保存快照
      markSessionIdle(sessionIdAtSend)
      persistCurrentSessionSnapshot(sessionIdAtSend)
    }
  } finally {
    activeStreams.delete(sessionIdAtSend)
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

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  align-self: stretch;
  width: calc(100% + 48px);
  max-width: none;
  margin-left: -24px;
  margin-right: -24px;
  height: 44px;
  padding: 0 24px;
  margin-bottom: 2px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  flex-shrink: 0;
  box-sizing: border-box;
}

.chat-header-start {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.chat-header-doc-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.chat-header-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.chat-header-more-wrap {
  position: relative;
  flex-shrink: 0;
}

.chat-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-left: auto;
}

.chat-header-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.chat-header-icon-btn:hover,
.chat-header-icon-btn.active {
  background: var(--accent-hover);
  color: var(--text);
}

.chat-header-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 120px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
  z-index: 30;
}

.chat-header-menu-item {
  display: block;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.chat-header-menu-item:hover {
  background: var(--accent-hover);
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
.chat-composer-area {
  width: 100%;
  max-width: 900px;
  flex-shrink: 0;
}

.bottom-console-dock {
  align-self: stretch;
  flex-shrink: 0;
  margin-top: auto;
  margin-left: -24px;
  margin-right: -24px;
  width: calc(100% + 48px);
  display: flex;
  flex-direction: column;
  border-top: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}

.bottom-console-panel {
  position: relative;
  min-height: 120px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.bottom-console-resize-handle {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 6px;
  cursor: row-resize;
  z-index: 6;
  touch-action: none;
}

.bottom-console-resize-handle::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 2px;
  height: 2px;
  background: transparent;
  transition: background 0.12s;
}

.bottom-console-resize-handle:hover::after {
  background: rgba(59, 130, 246, 0.45);
}

.chat-active {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 0;
  padding: 8px 24px 0;
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
