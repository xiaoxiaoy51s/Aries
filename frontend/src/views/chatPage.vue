<template>
  <section id="chatPage" class="page">
    <!-- 空状态 -->
    <div v-if="!hasActiveChat" class="chat-empty">
      <h1 class="welcome-title">我们要在 MIMOClaw 里构建什么？</h1>
      <div class="composer composer-with-slash">
        <SlashComposerInput
          ref="emptyComposerRef"
          v-model:plain-text="inputMessage"
          v-model:active-command="activeSlashCommand"
          v-model:objective="commandObjective"
          v-model:plugin-menu-open="pluginMenuOpen"
          v-model:attached-images="attachedImages"
          :rows="3"
          :disabled="isSending"
          @send="sendMessage"
        />
        <div class="composer-toolbar">
          <div class="composer-left">
            <button type="button" class="icon-btn" title="上传图片" @click="openImagePicker">+</button>
            <div class="workdir-picker">
              <button
                type="button"
                class="icon-btn workdir-btn"
                :title="workDirLabel || '选择工作目录'"
                @click="workDirMenuOpen = !workDirMenuOpen"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <span v-if="workDir" class="workdir-name">{{ workDirLabel }}</span>
              </button>
              <div v-if="workDirMenuOpen" class="workdir-menu" @click.stop>
                <div class="workdir-menu-title">历史工作目录</div>
                <ul v-if="workDirHistory.length" class="workdir-menu-list">
                  <li
                    v-for="dir in workDirHistory"
                    :key="dir"
                    class="workdir-menu-item"
                    :class="{ active: dir === workDir }"
                    @click="applyWorkDir(dir); workDirMenuOpen = false"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                    </svg>
                    <span class="workdir-menu-path" :title="dir">{{ dir }}</span>
                  </li>
                </ul>
                <div v-else class="workdir-menu-empty">暂无历史工作目录</div>
                <div class="workdir-menu-divider"></div>
                <button type="button" class="workdir-menu-new" @click="pickWorkDir">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14"/>
                  </svg>
                  <span>新工作目录</span>
                </button>
              </div>
            </div>
          </div>
          <div class="composer-right">
            <button
              type="button"
              class="icon-btn plugin-btn"
              :class="{ 'plugin-btn--active': pluginMenuOpen }"
              title="插件"
              :disabled="isSending || !!activeSlashCommand"
              @click="pluginMenuOpen = !pluginMenuOpen"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="14" width="7" height="7" rx="1.5"/>
                <rect x="3" y="14" width="7" height="7" rx="1.5"/>
              </svg>
            </button>
            <select v-model="selectedModel" class="model-select">
              <option v-for="model in modelStore.modelList" :key="model.id" :value="model.model">
                {{ model.name }}
              </option>
            </select>
            <button
              v-if="!isSending"
              type="button"
              class="send-btn"
              @click="sendMessage"
              :disabled="!canSend"
            >
              <span class="send-icon-inner">
                <svg class="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="m5 12 7-7 7 7M12 19V5"/>
                </svg>
              </span>
            </button>
            <button
              v-else
              type="button"
              class="send-btn send-btn--streaming"
              title="停止生成"
              @click="stopGeneration"
            >
              <span class="loading-spinner">
                <span class="spinner-circle"></span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 对话中状态 -->
    <div v-else class="chat-active">
      <div class="chat-messages" ref="messagesContainer">
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
              :is-loading="msg.isLoading"
              :computer-use="assistantShowsCuLogs(msg)"
              :show-copy-button="!!msg.hasSnapshot && !msg.isLoading"
              :text-color="textColor"
              :font-size="fontSize"
              @tool-confirm="onToolConfirm"
              @tool-cancel="onToolCancel"
            />
          </div>
        </div>
      </div>
      <div class="composer composer-bottom composer-with-slash">
        <div v-if="pendingToolConfirmation" class="danger-confirm-bar">
          <div class="danger-confirm-left">
            <span class="danger-confirm-label">危险命令</span>
            <span class="danger-confirm-detail" :title="pendingToolConfirmation.detail">
              {{ pendingToolConfirmation.detail }}
            </span>
            <span class="danger-confirm-timer">{{ confirmCountdown }}s</span>
          </div>
          <div class="danger-confirm-actions">
            <button
              type="button"
              class="danger-btn danger-btn--reject"
              @click="onToolCancel(pendingToolConfirmation.toolCallId)"
            >
              拒绝
            </button>
            <button
              type="button"
              class="danger-btn danger-btn--accept"
              @click="onToolConfirm(pendingToolConfirmation.toolCallId)"
            >
              接受
            </button>
          </div>
        </div>
        <SlashComposerInput
          ref="activeComposerRef"
          v-model:plain-text="inputMessage"
          v-model:active-command="activeSlashCommand"
          v-model:objective="commandObjective"
          v-model:plugin-menu-open="pluginMenuOpen"
          v-model:attached-images="attachedImages"
          :rows="2"
          :disabled="isSending"
          @send="sendMessage"
        />
        <div class="composer-toolbar">
          <div class="composer-left">
            <button
              v-if="!isComputerUseActive"
              type="button"
              class="icon-btn"
              title="上传图片"
              :disabled="isSending || !!activeSlashCommand"
              @click="openImagePicker"
            >
              +
            </button>
            <button
              v-if="isComputerUseActive"
              type="button"
              class="stop-btn"
              @click="stopDesktopTask"
            >
              停止操控
            </button>
          </div>
          <div class="composer-right">
            <button
              type="button"
              class="icon-btn plugin-btn"
              :class="{ 'plugin-btn--active': pluginMenuOpen }"
              title="插件"
              :disabled="isSending || !!activeSlashCommand"
              @click="pluginMenuOpen = !pluginMenuOpen"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="3" width="7" height="7" rx="1.5"/>
                <rect x="14" y="14" width="7" height="7" rx="1.5"/>
                <rect x="3" y="14" width="7" height="7" rx="1.5"/>
              </svg>
            </button>
            <select v-model="selectedModel" class="model-select">
              <option v-for="model in modelStore.modelList" :key="model.id" :value="model.model">
                {{ model.name }}
              </option>
            </select>
            <button
              v-if="!isSending"
              type="button"
              class="send-btn"
              @click="sendMessage"
              :disabled="!canSend"
            >
              <span class="send-icon-inner">
                <svg class="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="m5 12 7-7 7 7M12 19V5"/>
                </svg>
              </span>
            </button>
            <button
              v-else
              type="button"
              class="send-btn send-btn--streaming"
              title="停止生成"
              @click="stopGeneration"
            >
              <span class="loading-spinner">
                <span class="spinner-circle"></span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useModelStore } from '@/stores/model'
import { usePrivacyStore } from '@/stores/privacy'
import { streamChat, streamVision, stopChat, type StreamEvent } from '@/api/chat'
import { confirmTool } from '@/api/git'
import { useWorkspaceStore } from '@/stores/workspace'
import {
  streamComputerUse,
  stopComputerUse,
  parseComputerUseCommand,
  buildComputerUseUserDisplay,
  parseUserSlashMessage,
  isComputerUseLogLine,
  messageHasComputerUseLogs,
  buildWorkBlocksFromReasoning,
  splitComputerUseReasoningSegments,
  type ComputerUseStreamEvent,
  type SlashCommandDef,
} from '@/api/computerUse'
import { getSessionMessages, getSession, updateSessionMeta } from '@/api/sessions'
import AssistantMessage from '@/components/AssistantMessage.vue'
import SlashComposerInput, { type ComposerImage } from '@/components/SlashComposerInput.vue'
import UserMessageContent from '@/components/UserMessageContent.vue'
import { parseSnapshotEventObjects } from '@/utils/snapshotParser'

const modelStore = useModelStore()
const privacyStore = usePrivacyStore()
const workspaceStore = useWorkspaceStore()

const inputMessage = ref('')
const attachedImages = ref<ComposerImage[]>([])
const pluginMenuOpen = ref(false)
const activeSlashCommand = ref<SlashCommandDef | null>(null)
const commandObjective = ref('')
const selectedModel = ref('')
const hasActiveChat = ref(false)
const isSending = ref(false)
const isComputerUseActive = ref(false)
const messagesContainer = ref<HTMLElement>()
const emptyComposerRef = ref<InstanceType<typeof SlashComposerInput>>()
const activeComposerRef = ref<InstanceType<typeof SlashComposerInput>>()
const currentSessionId = ref<string | undefined>(undefined)
let streamAbortController: AbortController | null = null

const canSend = computed(() => {
  if (activeSlashCommand.value?.id === 'computer-use') {
    return commandObjective.value.trim().length > 0
  }
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
  pending_confirmation?: boolean
  danger_info?: string
  danger_types?: string[]
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  slashCommand?: string
  slashBody?: string
  isComputerUse?: boolean
  mode?: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  isLoading?: boolean
  messageSnapshotJson?: string
  hasSnapshot?: boolean
}

function assistantShowsCuLogs(msg: ChatMessage): boolean {
  return !!msg.isComputerUse || messageHasComputerUseLogs(msg)
}

function enrichUserMessage(content: string): Pick<ChatMessage, 'content' | 'slashCommand' | 'slashBody'> {
  const parsed = parseUserSlashMessage(content)
  if (parsed) {
    return {
      content,
      slashCommand: parsed.slashCommand,
      slashBody: parsed.slashBody,
    }
  }
  return { content }
}

const messages = ref<ChatMessage[]>([])

// 已自动确认的 tool call ID 集合，用于跳过后续 pending_confirmation 事件
const autoConfirmedToolIds = new Set<string>()

const CONFIRM_TIMEOUT_SECONDS = 120

interface PendingToolConfirmation {
  toolCallId: string
  detail: string
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
          detail: command || dangerInfo || block.tool_name || '待确认命令',
          dangerInfo,
          dangerTypes,
        }
      }
    }
  }
  return null
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

// 监听侧边栏新对话事件
function onNewChat(e?: Event) {
  currentSessionId.value = undefined
  messages.value = []
  hasActiveChat.value = false
  inputMessage.value = ''
  clearAttachedImages()
  clearComposerCommand()
  const newWorkDir = (e as CustomEvent | undefined)?.detail?.workDir || ''
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
const workDir = ref('')
const workDirMenuOpen = ref(false)
const workDirHistory = ref<string[]>([])
const workDirLabel = computed(() => {
  if (!workDir.value) return '选择工作目录'
  // 只显示最后一段路径名 + 父目录名，更紧凑
  const normalized = workDir.value.replace(/\\/g, '/').replace(/\/$/, '')
  const parts = normalized.split('/')
  return parts[parts.length - 1] || normalized
})

async function loadWorkDir() {
  try {
    const meta = await getSession('__project_mimoclaw__')
    workDir.value = meta.work_dir || ''
  } catch (e) {
    workDir.value = localStorage.getItem('mimo:workdir') || ''
  }
  workspaceStore.setWorkDir(workDir.value)
  loadWorkDirHistory()
}

function loadWorkDirHistory() {
  try {
    const raw = localStorage.getItem('mimo:workdir_history')
    const list = raw ? (JSON.parse(raw) as string[]) : []
    // 把当前 workDir 置顶
    const cur = workDir.value
    workDirHistory.value = cur && !list.includes(cur) ? [cur, ...list].slice(0, 8) : list.slice(0, 8)
  } catch {
    workDirHistory.value = workDir.value ? [workDir.value] : []
  }
}

function pushWorkDirHistory(path: string) {
  const list = workDirHistory.value.filter((d) => d !== path)
  list.unshift(path)
  workDirHistory.value = list.slice(0, 8)
  try {
    localStorage.setItem('mimo:workdir_history', JSON.stringify(workDirHistory.value))
  } catch {}
}

function onWorkDirChanged(e: Event) {
  workDir.value = (e as CustomEvent).detail || ''
  workspaceStore.setWorkDir(workDir.value)
  loadWorkDirHistory()
}

// 点「+ 新工作目录」时调用 —— 后端调起系统文件夹选择对话框
async function pickWorkDir() {
  try {
    const baseUrl = modelStore.getBaseUrl()
    const res = await fetch(`${baseUrl}/system/select-directory`, {
      method: 'POST',
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (data.cancelled || !data.path) return
    if (data.error) throw new Error(data.error)
    await applyWorkDir(data.path)
  } catch (e) {
    console.error('选择目录失败', e)
    alert('无法打开文件夹选择器：' + (e as Error).message)
  }
}

async function applyWorkDir(path: string) {
  try {
    await updateSessionMeta('__project_mimoclaw__', { work_dir: path })
    workDir.value = path
    workspaceStore.setWorkDir(path)
    pendingWorkDir.value = path
    localStorage.setItem('mimo:workdir', path)
    pushWorkDirHistory(path)
    window.dispatchEvent(new CustomEvent('mimo:workdir-changed', { detail: path }))
  } catch (e) {
    console.error('保存工作目录失败', e)
    alert('保存失败')
  }
}

// 监听侧边栏点击会话事件，加载历史
async function onLoadSession(e: Event) {
  const id = (e as CustomEvent).detail
  if (!id) return
  currentSessionId.value = id
  try {
    const data = await getSessionMessages(id, 100)
    const msgs: ChatMessage[] = (data.messages || []).map((m: any) => {
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
        if (m.mode === 'computer_use' && !base.slashCommand) {
          const body = (m.content || '').replace(/^\/computer-use\s*/i, '').trim()
          base.slashCommand = '/computer-use'
          base.slashBody = body || m.content
        }
      }
      return base
    })

    for (let i = 0; i < msgs.length; i++) {
      const m = msgs[i]
      if (m.role === 'assistant') {
        const prev = i > 0 ? msgs[i - 1] : null
        if (m.mode === 'computer_use' || prev?.slashCommand || prev?.mode === 'computer_use') {
          m.isComputerUse = true
        }
      }
    }
    
    // 先渲染不含快照的内容
    messages.value = msgs
    hasActiveChat.value = msgs.length > 0
    await nextTick()
    scrollToBottom()
    
    // 异步加载每条助手消息的 JSONL 快照（优先 JSONL，无则回退 DB reasoning_content）
    for (let i = 0; i < msgs.length; i++) {
      if (msgs[i].role !== 'assistant') continue
      const raw = (data.messages[i] as any)
      const messageId = raw?.id
      if (messageId) {
        await loadMessageSnapshot(messageId, i, raw)
      }
    }
  } catch (err) {
    console.error('加载历史消息失败', err)
  }
}

// 加载消息快照（JSONL 优先；无事件时用 DB reasoning_content 拆段）
async function loadMessageSnapshot(
  messageId: number,
  msgIndex: number,
  raw?: { reasoning_content?: string }
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
    if (!data.events || data.events.length === 0) {
      console.warn(`消息 ${messageId} 没有 JSONL 事件，尝试 reasoning_content`)
      applyReasoningContentFallback(messageId, msgIndex, raw?.reasoning_content)
      return
    }

    console.log(`[snapshot] 消息 ${messageId} 加载到 ${data.events.length} 个事件`)

    const parsed = parseSnapshotEventObjects(data.events)
    console.log(`[snapshot] 解析后 ${parsed.length} 个 SnapshotEvent`)

    const blocks: MessageBlock[] = []

    for (const event of parsed) {
      switch (event.type) {
        case 'reasoning':
          blocks.push({ type: 'text', text: event.content, phase: 'work' })
          break

        case 'tool_call':
          blocks.push({
            type: 'tool',
            tool_name: event.toolName || 'unknown',
            status: event.status || 'running',
            args: event.args,
            result: '',
            error: '',
            started_at: event.timestamp || '',
            ended_at: ''
          })
          break

        case 'tool_result':
          for (let i = blocks.length - 1; i >= 0; i--) {
            const b = blocks[i]
            if (b.type === 'tool' && (b.tool_name === event.toolName || b.tool_name === event.toolCallId)) {
              b.status = event.status || 'completed'
              b.result = event.content
              b.ended_at = event.timestamp || ''
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
      }
    }

    const reasoningSegments = parsed.filter(e => e.type === 'reasoning').map(e => e.content)
    const answerText = parsed.filter(e => e.type === 'assistant_text').map(e => e.content).join('')

    console.log(`[snapshot] 消息 ${messageId} 构建了 ${blocks.length} 个 blocks（${reasoningSegments.length} 段思考）`)

    messages.value[msgIndex] = {
      ...prev,
      isComputerUse: prev.isComputerUse || messageHasComputerUseLogs({ blocks, reasoning: reasoningSegments }),
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
      content: answerText || prev.content,
      hasSnapshot: true,
    }
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

async function ensureSessionTitle(sessionId: string, text: string, workDir?: string) {
  const title = buildSessionTitle(text)
  try {
    await updateSessionMeta(sessionId, {
      title,
      ...(workDir ? { work_dir: workDir } : {}),
    })
    window.dispatchEvent(new CustomEvent('mimo:refresh-sessions'))
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

  const segments = splitComputerUseReasoningSegments(rc)
  if (segments.length === 0) return

  const blocks: MessageBlock[] = buildWorkBlocksFromReasoning(rc)

  console.log(`[snapshot] 消息 ${messageId} 使用 reasoning_content 回退，${segments.length} 段`)

  messages.value[msgIndex] = {
    ...prev,
    isComputerUse: prev.isComputerUse || messageHasComputerUseLogs({ blocks, reasoning: segments }),
    blocks,
    reasoning: segments,
    content: prev.content,
  }
}

function onGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isComputerUseActive.value) {
    e.preventDefault()
    stopDesktopTask()
  }
}

onMounted(() => {
  window.addEventListener('mimo:new-chat', onNewChat)
  window.addEventListener('mimo:load-session', onLoadSession)
  window.addEventListener('mimo:workdir-changed', onWorkDirChanged)
  document.addEventListener('mousedown', closeWorkDirMenu)
  document.addEventListener('keydown', onGlobalKeydown)
  loadWorkDir()
})

onUnmounted(() => {
  clearConfirmCountdownTimer()
  window.removeEventListener('mimo:new-chat', onNewChat)
  window.removeEventListener('mimo:load-session', onLoadSession)
  window.removeEventListener('mimo:workdir-changed', onWorkDirChanged)
  document.removeEventListener('mousedown', closeWorkDirMenu)
  document.removeEventListener('keydown', onGlobalKeydown)
})

function closeWorkDirMenu(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  if (target && target.closest('.workdir-picker')) return
  workDirMenuOpen.value = false
}

function applyStreamEvent(assistantMsg: ChatMessage, evt: StreamEvent) {
  if (evt.type === 'content' && evt.data) {
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
    const isLogLine = isComputerUseLogLine(evt.data)
    if (isLogLine) {
      assistantMsg.isComputerUse = true
    }

    if (!assistantMsg.reasoning) assistantMsg.reasoning = []
    const blocks = (assistantMsg.blocks || []).slice()

    if (isLogLine) {
      // 桌面操控：每条 JSONL/SSE 日志独立一段
      assistantMsg.reasoning.push(evt.data)
      blocks.push({ type: 'text', text: evt.data, phase: 'work' })
    } else {
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
    }
    assistantMsg.blocks = blocks
  } else if (evt.type === 'tool_call') {
    if (evt.data.tool_name === 'cli_executor') {
      workspaceStore.focusConsole()
      // 延迟发送 focus 事件，等 Vue 完成 DOM 更新（ConsolePanel 挂载并注册监听器）后再切换 Tab
      nextTick(() => {
        window.dispatchEvent(new CustomEvent('mimo:focus-console'))
      })
    }
    if (!assistantMsg.tools) assistantMsg.tools = []
    const toolBlock: MessageBlock = {
      type: 'tool',
      tool_name: evt.data.tool_name,
      tool_call_id: evt.data.tool_call_id,
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
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    assistantMsg.blocks = [...assistantMsg.blocks, toolBlock]
  } else if (evt.type === 'tool_result') {
    if (!assistantMsg.tools) assistantMsg.tools = []
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

async function stopDesktopTask() {
  try {
    await stopComputerUse()
  } catch (e) {
    console.error('停止 desktop 操控失败', e)
  }
}

async function stopGeneration() {
  if (pendingToolConfirmation.value) {
    dismissPendingConfirmations('已停止')
  }
  const sessionId = currentSessionId.value
  if (sessionId) {
    stopChat(sessionId).catch(() => {})
  }
  if (isComputerUseActive.value) {
    stopDesktopTask().catch(() => {})
  }
  streamAbortController?.abort()
}

async function runAssistantStream(
  stream: AsyncGenerator<ComputerUseStreamEvent | StreamEvent>,
  assistantMsg: ChatMessage,
  assistantIdx: number,
  onMeta?: (sessionId: string) => void
) {
  try {
    for await (const event of stream) {
      const meta = 'meta' in event ? event.meta : undefined
      if (meta?.session_id) {
        onMeta?.(meta.session_id)
      }
      if (event.type === 'reasoning' && !event.data) continue
      if (event.type === 'content' && !event.data) continue
      applyStreamEvent(assistantMsg, event)
      // 自动确认：如果用户关闭了该类危险命令的确认，直接放行
      if (event.type === 'confirmation_required' && event.data) {
        const dangerTypes: string[] = event.data.danger_types || []
        const needsConfirm = dangerTypes.some((dt: string) => privacyStore.shouldConfirmByType(dt))
        if (!needsConfirm) {
          const toolCallId = event.data.tool_call_id as string
          // 同步清除 assistantMsg 中的 pending 状态，防止确认条闪烁
          if (assistantMsg.blocks) {
            for (const block of assistantMsg.blocks) {
              if (block.type === 'tool' && block.tool_call_id === toolCallId && block.pending_confirmation) {
                block.pending_confirmation = false
                block.status = 'running'
              }
            }
          }
          messages.value[assistantIdx] = { ...assistantMsg }
          // 异步通知后端放行，不阻塞流处理
          confirmTool(toolCallId, true).catch(() => {})
          autoConfirmedToolIds.add(toolCallId)
        }
      }
      messages.value[assistantIdx] = { ...assistantMsg }
      await nextTick()
      scrollToBottom()
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      dismissPendingConfirmations('已停止')
      return
    }
    throw e
  } finally {
    clearPendingConfirmationUi()
  }
}

async function sendComputerUseMessage(objective: string) {
  const userDisplay = buildComputerUseUserDisplay(objective)
  messages.value.push({
    role: 'user',
    content: userDisplay,
    slashCommand: '/computer-use',
    slashBody: objective,
  })
  inputMessage.value = ''
  clearAttachedImages()
  clearComposerCommand()
  hasActiveChat.value = true
  isSending.value = true
  isComputerUseActive.value = true

  let assistantMsg: ChatMessage = {
    role: 'assistant',
    content: '',
    isComputerUse: true,
    reasoning: [],
    tools: [],
    blocks: [],
    isLoading: true
  }
  messages.value.push(assistantMsg)
  const assistantIdx = messages.value.length - 1

  const isNewSession = !currentSessionId.value
  const sessionIdAtSend = currentSessionId.value || crypto.randomUUID().replace(/-/g, '')
  if (isNewSession) {
    currentSessionId.value = sessionIdAtSend
  }
  const workDirAtSend = pendingWorkDir.value || workDir.value
  if (workDirAtSend && isNewSession) {
    pendingWorkDir.value = ''
  }

  await nextTick()
  scrollToBottom()
  if (isNewSession) {
    await ensureSessionTitle(sessionIdAtSend, userDisplay, workDirAtSend)
  } else {
    window.dispatchEvent(new CustomEvent('mimo:refresh-sessions'))
  }

  streamAbortController = new AbortController()

  try {
    await runAssistantStream(
      streamComputerUse(objective, sessionIdAtSend, workDirAtSend, userDisplay),
      assistantMsg,
      assistantIdx,
      (sid) => { currentSessionId.value = sid }
    )
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      assistantMsg.content = `错误: ${e.message}`
      messages.value[assistantIdx] = { ...assistantMsg }
    }
  } finally {
    streamAbortController = null
    assistantMsg.isLoading = false
    messages.value[assistantIdx] = { ...assistantMsg }
    isSending.value = false
    isComputerUseActive.value = false
    await nextTick()
    scrollToBottom()
    if (currentSessionId.value) {
      await refreshAssistantSnapshot(currentSessionId.value, assistantIdx)
    }
    window.dispatchEvent(new CustomEvent('mimo:refresh-sessions'))
  }
}

async function sendMessage() {
  if (isSending.value || !canSend.value) return

  if (activeSlashCommand.value?.id === 'computer-use') {
    const objective = commandObjective.value.trim()
    if (!objective) {
      alert('请描述要完成的桌面任务')
      return
    }
    await sendComputerUseMessage(objective)
    return
  }

  const message = inputMessage.value.trim()
  const imagesToSend = attachedImages.value.map((img) => img.dataUrl)
  if (!message && imagesToSend.length === 0) return

  const computerObjective = parseComputerUseCommand(message)
  if (computerObjective !== null) {
    if (!computerObjective) {
      alert('请在 /computer-use 后输入任务描述，例如：/computer-use 打开抖音')
      return
    }
    await sendComputerUseMessage(computerObjective)
    return
  }

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

  let assistantMsg: ChatMessage = {
    role: 'assistant',
    content: '',
    reasoning: [],
    tools: [],
    blocks: [],
    isLoading: true
  }
  messages.value.push(assistantMsg)
  const assistantIdx = messages.value.length - 1

  const isNewSession = !currentSessionId.value
  const sessionIdAtSend = currentSessionId.value || crypto.randomUUID().replace(/-/g, '')
  if (isNewSession) {
    currentSessionId.value = sessionIdAtSend
  }
  const workDirAtSend = pendingWorkDir.value
  if (workDirAtSend && isNewSession) {
    pendingWorkDir.value = ''
  }

  await nextTick()
  scrollToBottom()
  if (isNewSession) {
    await ensureSessionTitle(
      sessionIdAtSend,
      message || (imagesToSend.length > 1 ? `[${imagesToSend.length} 张图片]` : '[图片]'),
      workDirAtSend
    )
  } else {
    window.dispatchEvent(new CustomEvent('mimo:refresh-sessions'))
  }

  streamAbortController = new AbortController()
  const signal = streamAbortController.signal

  try {
    const stream = imagesToSend.length > 0
      ? streamVision(message, imagesToSend, sessionIdAtSend, workDirAtSend, signal)
      : streamChat(
          messages.value
            .filter(m => m.role === 'user' || (m.role === 'assistant' && m.content))
            .map(m => ({ role: m.role, content: m.content })),
          sessionIdAtSend,
          workDirAtSend,
          signal
        )

    await runAssistantStream(stream, assistantMsg, assistantIdx, (sid) => {
      currentSessionId.value = sid
    })
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      messages.value.push({
        role: 'assistant',
        content: `错误: ${e.message}`,
        reasoning: [],
        tools: []
      })
    }
  } finally {
    streamAbortController = null
    assistantMsg.isLoading = false
    messages.value[assistantIdx] = { ...assistantMsg }
    isSending.value = false
    await nextTick()
    scrollToBottom()
    if (currentSessionId.value) {
      await refreshAssistantSnapshot(currentSessionId.value, assistantIdx)
    }
    window.dispatchEvent(new CustomEvent('mimo:refresh-sessions'))
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}
</script>

<style scoped>
.page {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  width: 100%;
  align-items: stretch;
}

/* —— 对话：空状态 —— */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 48px 32px;
  gap: 24px;
}

.welcome-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.02em;
  text-align: center;
  max-width: 640px;
}

.composer {
  width: 100%;
  max-width: 900px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--bg-panel);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  overflow: visible;
}

.composer-with-slash {
  position: relative;
}

.stop-btn {
  border: 1px solid #e74c3c;
  color: #e74c3c;
  background: transparent;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}

.stop-btn:hover {
  background: rgba(231, 76, 60, 0.08);
}

.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 12px;
  gap: 12px;
}

.composer-left,
.composer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.workdir-btn {
  width: auto;
  max-width: 320px;
  gap: 6px;
  padding: 0 10px;
}

.workdir-name {
  font-size: 12px;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-btn:hover {
  background: var(--accent-hover);
}

.plugin-btn--active {
  border-color: rgba(52, 152, 219, 0.45);
  background: rgba(52, 152, 219, 0.1);
  color: #1565c0;
}

.plugin-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.model-select {
  appearance: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 28px 6px 12px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-panel) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b6b66' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 8px center;
  cursor: pointer;
  max-width: 200px;
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--send-bg);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  flex-shrink: 0;
  position: relative;
}

.send-btn:hover:not(:disabled) {
  background: var(--send-hover);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn--streaming {
  cursor: pointer;
}

.send-btn--streaming:hover {
  background: var(--send-hover);
}

.send-icon-inner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.spinner-circle {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin-send 0.75s linear infinite;
}

@keyframes spin-send {
  to { transform: rotate(360deg); }
}

.workdir-picker {
  position: relative;
}

.workdir-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  min-width: 280px;
  max-width: 420px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 200;
  overflow: visible;
}

.workdir-menu-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 6px 10px 4px;
}

.workdir-menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
}

.workdir-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.12s, color 0.12s;
}

.workdir-menu-item:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.workdir-menu-item.active {
  background: var(--accent-active);
  color: var(--text);
}

.workdir-menu-item svg {
  flex-shrink: 0;
  color: var(--text-muted);
}

.workdir-menu-path {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: ui-monospace, monospace;
}

.workdir-menu-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 10px 10px;
}

.workdir-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 4px;
}

.workdir-menu-new {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.workdir-menu-new:hover {
  background: var(--accent-hover);
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
  background: #e8eaed;
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

.composer-bottom {
  max-width: 900px;
  width: 100%;
  flex-shrink: 0;
  margin-top: 8px;
}

.danger-confirm-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 0;
  border: 1px solid var(--border);
  border-bottom: none;
  background: #fff;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.danger-confirm-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.danger-confirm-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.danger-confirm-detail {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-secondary);
  font-family: ui-monospace, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.danger-confirm-timer {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.danger-confirm-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.danger-btn {
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.danger-btn--reject {
  background: transparent;
  color: var(--text-secondary);
}

.danger-btn--reject:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.danger-btn--accept {
  background: #1a1a18;
  color: #fff;
}

.danger-btn--accept:hover {
  background: #33332f;
}

.composer-bottom textarea {
  padding: 12px 16px 6px;
  font-size: 14px;
}
</style>
