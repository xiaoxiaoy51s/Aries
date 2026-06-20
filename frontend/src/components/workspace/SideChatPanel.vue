<template>
  <div class="side-chat-page">
    <!-- 消息列表 -->
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

    <!-- 空状态提示 -->
    <div v-else class="chat-empty-hint">
      <p>临时对话不会保存，关闭后消失。</p>
      <p class="hint-sub">会自动加载当前会话的上下文记忆。</p>
    </div>

    <!-- 输入区 -->
    <ChatComposer
      ref="composerRef"
      v-model="inputText"
      v-model:attached-images="attachedImages"
      v-model:active-slash-command="activeSlashCommand"
      v-model:command-objective="commandObjective"
      v-model:plugin-menu-open="pluginMenuOpen"
      :is-sending="isSending"
      v-model:selected-model="selectedModel"
      :model-list="modelList"
      :can-send="canSend"
      :show-work-dir="false"
      :rows="2"
      is-bottom
      @send="sendMessage"
      @stop="stopSideChat"
      @open-image-picker="openImagePicker"
      @pick-work-dir="() => {}"
      @apply-work-dir="() => {}"
      @toggle-side-chat="() => {}"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useModelStore } from '@/stores/model'
import { streamTempChat, type StreamEvent, type ChatMessage as ApiChatMessage } from '@/api/chat'
import AssistantMessage from '@/components/AssistantMessage.vue'
import ChatComposer from '@/components/ChatComposer.vue'
import UserMessageContent from '@/components/UserMessageContent.vue'
import SlashComposerInput, { type ComposerImage } from '@/components/SlashComposerInput.vue'

interface SlashCommandDef { id: string; label?: string }

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
  pending_confirmation?: boolean
  danger_info?: string
  danger_types?: string[]
}

interface SideMessage {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  isLoading?: boolean
}

const props = defineProps<{
  visible: boolean
  sessionId?: string
  workDir?: string
}>()

const modelStore = useModelStore()

const textColor = computed(() => '#1a1a1a')
const fontSize = computed(() => 15)
const modelList = computed(() => modelStore.modelList)
const selectedModel = ref(modelStore.activeModel?.model || '')

watch(() => modelStore.activeModel, (m) => {
  if (m) selectedModel.value = m.model
}, { immediate: true })

const sideMessages = ref<SideMessage[]>([])
const inputText = ref('')
const attachedImages = ref<ComposerImage[]>([])
const pluginMenuOpen = ref(false)
const activeSlashCommand = ref<SlashCommandDef | null>(null)
const commandObjective = ref('')
const isSending = ref(false)
const msgContainer = ref<HTMLElement>()
const composerRef = ref<InstanceType<typeof ChatComposer>>()

let stopRequested = false

const canSend = computed(() => inputText.value.trim().length > 0 || attachedImages.value.length > 0)

function scrollToBottom() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
}

function openImagePicker() {
  composerRef.value?.openFilePicker()
}

/** 简化版 applyStreamEvent */
function applyStreamEvent(assistantMsg: SideMessage, evt: StreamEvent) {
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
  } else if (evt.type === 'reasoning' && evt.data) {
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
      ended_at: '',
    }
    assistantMsg.blocks.push(toolBlock)
    assistantMsg.tools.push({
      name: evt.data.tool_name,
      status: 'running',
      args: evt.data.args,
      output: '',
    })
  } else if (evt.type === 'tool_result') {
    if (!assistantMsg.blocks) return
    const toolCallId = String(evt.data.tool_call_id || '')
    for (const block of assistantMsg.blocks) {
      if (block.type === 'tool' && block.tool_call_id === toolCallId) {
        block.status = evt.data.status || 'completed'
        block.result = evt.data.output || ''
        block.ended_at = new Date().toISOString()
        break
      }
    }
    if (assistantMsg.tools) {
      const tool = assistantMsg.tools.find((t) => t.name === evt.data.tool_name)
      if (tool) {
        tool.status = evt.data.status || 'completed'
        tool.output = evt.data.output || ''
      }
    }
  }
}

async function sendMessage() {
  const message = inputText.value.trim()
  if (!message || isSending.value) return

  sideMessages.value.push({ role: 'user', content: message })
  inputText.value = ''
  attachedImages.value = []
  composerRef.value?.clearImages()
  scrollToBottom()

  const assistantMsg: SideMessage = {
    role: 'assistant',
    content: '',
    reasoning: [],
    tools: [],
    blocks: [],
    isLoading: true,
  }
  sideMessages.value.push(assistantMsg)
  const assistantIdx = sideMessages.value.length - 1
  isSending.value = true
  stopRequested = false

  const chatMessages: ApiChatMessage[] = sideMessages.value
    .filter((m, i) => i < assistantIdx)
    .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
    .map((m) => ({ role: m.role, content: m.content }))

  try {
    const stream = streamTempChat(chatMessages, props.sessionId, props.workDir)
    for await (const event of stream) {
      if (stopRequested) break
      if (event.type === 'reasoning' && !event.data) continue
      if (event.type === 'content' && !event.data) continue
      applyStreamEvent(assistantMsg, event)
      sideMessages.value[assistantIdx] = { ...assistantMsg }
      scrollToBottom()
    }
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      assistantMsg.content += `\n[错误] ${e.message}`
    }
  } finally {
    assistantMsg.isLoading = false
    sideMessages.value[assistantIdx] = { ...assistantMsg }
    isSending.value = false
  }
}

function stopSideChat() {
  stopRequested = true
  isSending.value = false
}

function clearMessages() {
  sideMessages.value = []
}

defineExpose({ clearMessages, stopSideChat })
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

/* —— 消息列表 —— */
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
.chat-messages::-webkit-scrollbar {
  display: none;
}

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

/* —— 空状态提示 —— */
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
.hint-sub {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 4px;
}
</style>
