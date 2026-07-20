<template>
  <div class="assistant-message" @click="onMessageClick">
    <!-- 运行元数据栏：模型、处理时长、token 使用 -->
    <div v-if="hasMetaInfo" class="meta-bar">
      <span v-if="props.meta?.model" class="meta-item meta-model">
        <svg t="1781949967022" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="4962" width="12" height="12"><path d="M229.0688 665.4464l183.1424-102.7072 3.1232-8.9088-3.1232-4.9664h-8.9088l-30.6688-1.8432-104.704-2.816-90.7776-3.7888-87.9104-4.7104-22.1696-4.7104-20.7872-27.3408 2.1504-13.6704 18.6368-12.4416 26.624 2.304 58.9824 3.9936 88.3712 6.144 64.1024 3.7888 95.0272 9.8816h15.104l2.1504-6.0928-5.2224-3.7888-3.9936-3.7888-91.4944-61.952-99.0208-65.4848-51.8144-37.7344-28.1088-19.0464-14.1312-17.92-6.144-39.1168 25.4464-28.0064 34.2016 2.304 8.7552 2.3552 34.6624 26.624 74.0352 57.2928L391.2704 380.416l14.1824 11.776 5.632-3.9936 0.7168-2.816-6.3488-10.6496-52.5824-94.9248-56.1152-96.6144-24.9856-40.0384-6.6048-24.0128c-2.5088-9.216-3.8912-18.7392-4.0448-28.2624l29.0304-39.3216 16.0256-5.2224 38.656 5.2224 16.2816 14.1312 24.064 54.8864 38.8608 86.4768L484.352 324.608l17.7152 34.8672 9.4208 32.3072 3.5328 9.8816h6.144v-5.6832l4.9664-66.2016 9.216-81.3056 8.9088-104.5504 3.1232-29.4912 14.592-35.328 28.9792-19.0976 22.6816 10.8544 18.6368 26.5728-2.6112 17.2032-11.1104 71.8336-21.7088 112.64-14.1312 75.3664h8.2432l9.4208-9.3696 38.1952-50.688 64.1024-80.0768 28.3136-31.7952 32.9728-35.072 21.248-16.7424h40.0896l29.4912 43.8272-13.2096 45.2608-41.2672 52.2752-34.2016 44.288-49.0496 65.9456-30.6688 52.7872 2.816 4.2496 7.2704-0.768 110.7968-23.5008 59.8528-10.8544 71.424-12.2368 32.3072 15.0528 3.5328 15.3088-12.7488 31.3344-76.3904 18.8416-89.6 17.92-133.4272 31.5392-1.6384 1.1776 1.8944 2.3552 60.1088 5.6832 25.7024 1.3824h62.9248l117.1968 8.7552 30.6688 20.2752 18.3808 24.7808-3.072 18.8416-47.1552 24.064-63.6416-15.104-148.5824-35.328-50.8928-12.7488h-7.0656v4.2496l42.3936 41.4208 77.824 70.2464 97.3312 90.4192 4.9152 22.4256-12.4928 17.664-13.2096-1.8944-85.5552-64.3072-33.024-28.9792-74.752-62.8736h-4.9664v6.6048l17.2032 25.1904 90.9824 136.6016 4.7104 41.8816-6.6048 13.7216-23.6032 8.2432-25.9072-4.7104-53.2992-74.7008-54.8864-84.0704-44.3392-75.4176-5.4272 3.1232-26.1632 281.4976-12.2368 14.336-28.2624 10.8544-23.552-17.8688-12.4928-28.9792 12.4928-57.2928 15.104-74.6496 12.2368-59.392 11.1104-73.728 6.6048-24.5248-0.4608-1.6384-5.4272 0.7168-55.6544 76.3392-84.5824 114.2784-66.9696 71.5776-16.0768 6.3488-27.8016-14.336 2.6112-25.7024 15.5648-22.8352 92.672-117.8112 55.8592-73.0112 36.096-42.1376-0.256-6.144h-2.1504l-246.1184 159.6928-43.8272 5.6832-18.8928-17.7152 2.3552-28.928 8.96-9.4208 74.0352-50.8928-0.256 0.256z" fill="#D97757" p-id="4963"></path></svg>
        {{ props.meta?.model }}
      </span>
      <span v-if="formattedDuration" class="meta-item">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        {{ formattedDuration }}
      </span>
      <span v-if="tokenInOut.input" class="meta-item" :title="tokenInOut.estimated ? '输入 tokens（估算）' : '输入 tokens'">
        {{ tokenInOut.input }}
      </span>
      <span v-if="tokenInOut.output" class="meta-item" :title="tokenInOut.estimated ? '输出 tokens（估算）' : '输出 tokens'">
        {{ tokenInOut.output }}
      </span>
      <span v-if="tokenInOut.cache" class="meta-item" title="缓存命中">
        {{ tokenInOut.cache }}
      </span>
      <span v-if="contextPercent !== null" class="meta-item meta-context" :class="{ 'meta-context--high': contextPercent >= 80 }">
        ctx {{ contextPercent }}%
      </span>
    </div>
    <!-- 使用 blocks 方式渲染（参考 frontend1） -->
    <template v-if="props.blocks && props.blocks.length > 0">
      <template v-for="(group, groupIndex) in groupedBlocks" :key="groupIndex">
        <!-- 工作过程组（思考 + 工具调用，可折叠） -->
        <div v-if="group.type === 'work'" class="work-block">
          <div class="work-header" @click="toggleWork(groupIndex)">
            <svg class="work-icon" :class="{ expanded: isWorkOpen(groupIndex) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="m9 18 6-6-6-6"/>
            </svg>
            <span class="work-title">{{ isLoading && groupIndex === groupedBlocks.length - 1 ? '思考中…' : '思考过程' }}</span>
          </div>
          <div v-show="isWorkOpen(groupIndex)" class="work-content">
            <template v-for="(block, idx) in group.items" :key="`${groupIndex}-${idx}-${block.type}-${block.tool_call_id || ''}`">
              <ToolBlock
                v-if="block.type === 'tool'"
                :tool-name="block.tool_name || 'unknown'"
                :status="block.status || 'running'"
                :args="block.args"
                :preview="block.preview"
                :result="block.result || ''"
                :error="block.error || ''"
                :screenshot-preview="block.screenshot_preview || ''"
                :screenshot-path="block.screenshot_path || ''"
                :started-at="block.started_at || ''"
                :ended-at="block.ended_at || ''"
                :compact="false"
                :pending-confirmation="block.pending_confirmation || false"
                :danger-info="block.danger_info || ''"
                :session-id="block.session_id || ''"
                :tool-call-id="block.tool_call_id || ''"
                :chat-session-id="chatSessionId || ''"
                :subagent="block.subagent"
              />
              <div v-else class="reasoning-text">
                <MarkdownRenderer
                  :content="block.text || ''"
                  text-color="#94a3b8"
                  :font-size="Math.max(10, Math.round(fontSize * 0.8))"
                  :show-actions="false"
                  :is-streaming="isLoading"
                />
              </div>
            </template>
          </div>
        </div>

        <!-- 最终回复块（assistant_text，phase=answer）+ 文件变更工具 -->
        <template v-else>
          <template v-for="(block, idx) in group.items" :key="idx">
            <div
              v-if="block.type === 'text' || block.type === 'summary'"
              class="text-block"
              :class="[
                { 'error-block': block.error },
                block.errorType === 'step_limit_exceeded' ? 'pause-block' : ''
              ]"
            >
              <MarkdownRenderer
                :content="block.text || ''"
                :text-color="block.error && block.errorType !== 'step_limit_exceeded' ? '#b91c1c' : textColor"
                :font-size="block.error && block.errorType !== 'step_limit_exceeded' ? Math.max(12, fontSize - 2) : fontSize"
                :show-actions="false"
                :is-streaming="isLoading"
              />
            </div>
            <ToolBlock
              v-else-if="block.type === 'tool'"
              :tool-name="block.tool_name || 'unknown'"
              :status="block.status || 'running'"
              :args="block.args"
              :preview="block.preview"
              :result="block.result || ''"
              :error="block.error || ''"
              :screenshot-preview="block.screenshot_preview || ''"
              :screenshot-path="block.screenshot_path || ''"
              :started-at="block.started_at || ''"
              :ended-at="block.ended_at || ''"
              :compact="false"
              :pending-confirmation="block.pending_confirmation || false"
              :danger-info="block.danger_info || ''"
              :session-id="block.session_id || ''"
              :tool-call-id="block.tool_call_id || ''"
              :chat-session-id="chatSessionId || ''"
              :subagent="block.subagent"
            />
          </template>
        </template>
      </template>
    </template>
    
    <!-- 兼容旧方式：使用 reasoning 和 tools props -->
    <template v-else>
      <!-- 思考块（可折叠） -->
      <div v-if="props.reasoning && props.reasoning.length > 0" class="reasoning-block">
        <div class="reasoning-header" @click="showReasoning = !showReasoning">
          <svg class="reasoning-icon" :class="{ expanded: showReasoning }" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m9 18 6-6-6-6"/>
          </svg>
          <span class="reasoning-title">思考过程</span>
          <span class="reasoning-count">{{ props.reasoning.length }} 段</span>
        </div>
        <div v-show="showReasoning" class="reasoning-content">
          <div v-for="(text, idx) in props.reasoning" :key="idx" class="reasoning-text">
            <MarkdownRenderer :content="text" :text-color="textColor" :font-size="fontSize" :show-actions="false" />
          </div>
        </div>
      </div>

      <!-- 工具调用块 -->
      <div v-if="props.tools && props.tools.length > 0" class="tools-block">
        <div v-for="(tool, idx) in props.tools" :key="idx" class="tool-item">
          <div class="tool-header">
            <div class="tool-info">
              <svg class="tool-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
              <span class="tool-name">{{ tool.name }}</span>
            </div>
            <span class="tool-status" :class="tool.status">
              {{ tool.status === 'completed' ? '完成' : tool.status === 'running' ? '运行中' : '错误' }}
            </span>
          </div>
          <!-- 工具参数 -->
          <div v-if="tool.args && Object.keys(tool.args).length > 0" class="tool-args">
            <details>
              <summary>参数</summary>
              <pre class="code-block">{{ JSON.stringify(tool.args, null, 2) }}</pre>
            </details>
          </div>
          <!-- 工具输出 -->
          <div v-if="tool.output" class="tool-output">
            <details open>
              <summary>输出</summary>
              <pre class="code-block">{{ tool.output }}</pre>
            </details>
          </div>
        </div>
      </div>

      <!-- 助手回复内容（Markdown 渲染） -->
      <div v-if="props.content" class="message-content">
        <MarkdownRenderer :content="props.content" :text-color="textColor" :font-size="fontSize" :show-actions="false" :is-streaming="isLoading" />
      </div>
    </template>

    <!-- 加载动画（流式输出中） -->
    <div v-if="isLoading" class="loading-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <!-- 统一复制按钮：渲染在最后 -->
    <div v-if="showCopyAction" class="message-actions">
      <button class="action-btn" @click="copyFullContent" title="复制">
        <svg v-if="copiedAll" t="1780846687143" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="6050" width="12" height="12"><path d="M896 288a32 32 0 0 0-54.656-22.592L418.656 688.096 184.992 396l-0.112 0.08a31.872 31.872 0 1 0-49.76 39.824l-0.112 0.096 256 320 0.112-0.08a31.872 31.872 0 0 0 47.52 2.688l447.952-447.952c5.824-5.808 9.408-13.808 9.408-22.656z" fill="#231815" p-id="6051"></path></svg>
        <svg v-else t="1780846643473" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5009" width="12" height="12"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="#000000" p-id="5010"></path><path d="M875.52 745.984h-52.736V220.672H297.984V168.448H875.52z" fill="#000000" p-id="5011"></path></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolBlock from './ToolBlock.vue'
interface BlockGroup {
  type: 'work' | 'normal'
  items: MessageBlock[]
}

import { FILE_EDIT_TOOL_NAMES } from '@/utils/fileEditPreview'
import {
  streamDurationTick,
  startStreamDuration,
  stopStreamDuration,
  bindStreamDuration,
  getStreamDurationMs,
} from '@/utils/streamDurationStore'
import { formatTokenInOutLabels } from '@/utils/runMetadata'

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
  errorType?: string
  started_at?: string
  ended_at?: string
  tool_call_id?: string
  session_id?: string
  auto_detached?: boolean
  pending_confirmation?: boolean
  danger_info?: string
  danger_types?: string[]
  subagent?: {
    task_id?: string
    subagent?: string
    task?: string
    status?: string
    round?: number
    last_event?: string
    elapsed_ms?: number
    log_path?: string
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

const props = withDefaults(defineProps<{
  content?: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  isLoading?: boolean
  textColor?: string
  fontSize?: number
  meta?: MessageMeta
  chatSessionId?: string
  messageId?: number
}>(), {
  content: '',
  reasoning: () => [],
  tools: () => [],
  blocks: () => [],
  isLoading: false,
  textColor: '#1a1a1a',
  fontSize: 15,
  meta: () => ({})
})

const showReasoning = ref(false)

// ---------- 统一复制按钮 ----------
const copiedAll = ref(false)
let copyResetTimer: ReturnType<typeof setTimeout> | null = null

// 是否存在可复制的最终文本（最后一条非 error 的 text/summary 块）
const hasCopyableText = computed(() => {
  if (props.blocks && props.blocks.length > 0) {
    return lastTextBlockIndex.value >= 0 && !(props.blocks[lastTextBlockIndex.value] || {}).error
  }
  return !!props.content
})

// 复制按钮只在流式结束后、且有可复制内容时显示
const showCopyAction = computed(() => !props.isLoading && hasCopyableText.value)

function getCopyableContent(): string {
  if (props.blocks && props.blocks.length > 0) {
    const idx = lastTextBlockIndex.value
    if (idx >= 0) return props.blocks[idx].text || ''
    return ''
  }
  return props.content || ''
}

function copyFullContent() {
  const text = getCopyableContent()
  if (!text) return
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    copiedAll.value = true
    if (copyResetTimer) clearTimeout(copyResetTimer)
    copyResetTimer = setTimeout(() => {
      copiedAll.value = false
    }, 1500)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}

onBeforeUnmount(() => {
  if (copyResetTimer) clearTimeout(copyResetTimer)
})

// ---------- 实时计时（sessionId + messageId 全局 store，切换目录/卸载组件不重置） ----------
function syncStreamDurationState() {
  const sid = props.chatSessionId
  if (!sid || !props.isLoading) return
  if (props.messageId) {
    bindStreamDuration(sid, props.messageId)
    startStreamDuration(sid, props.messageId)
  } else {
    startStreamDuration(sid, '__pending__')
  }
}

watch(
  () => [props.isLoading, props.chatSessionId, props.messageId] as const,
  ([loading]) => {
    const sid = props.chatSessionId
    if (!sid) return
    if (loading) {
      syncStreamDurationState()
    } else {
      stopStreamDuration(sid, props.messageId ?? undefined)
    }
  },
  { immediate: true },
)

const textColor = computed(() => props.textColor || '#1a1a1a')
const fontSize = computed(() => props.fontSize || 15)

// meta 相关计算
const hasMetaInfo = computed(() => {
  const t = tokenInOut.value
  return !!(
    props.isLoading ||
    props.meta?.model ||
    formattedDuration.value ||
    t.input ||
    t.output ||
    t.cache ||
    contextPercent.value !== null
  )
})

const tokenInOut = computed(() => formatTokenInOutLabels(props.meta?.token_usage))

const formattedDuration = computed(() => {
  streamDurationTick.value // 订阅全局 ticker 刷新
  let ms = 0
  if (!props.isLoading && props.meta?.duration_ms) {
    ms = props.meta.duration_ms
  } else {
    const sid = props.chatSessionId
    if (sid) {
      if (props.messageId) {
        ms = getStreamDurationMs(sid, props.messageId)
      } else if (props.isLoading) {
        ms = getStreamDurationMs(sid, '__pending__')
      }
    }
    if (!ms && !props.isLoading) {
      ms = props.meta?.duration_ms || 0
    }
  }
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = Math.round(s % 60)
  return `${m}m${rest}s`
})

const contextPercent = computed(() => {
  const pct = props.meta?.token_usage?.context?.usage_percent
  if (typeof pct !== 'number') return null
  return Math.round(pct)
})

// 计算最后一个 text/summary block 的索引，用于控制复制按钮只出现在最后一条
const lastTextBlockIndex = computed(() => {
  if (!props.blocks || props.blocks.length === 0) return -1
  for (let i = props.blocks.length - 1; i >= 0; i--) {
    const b = props.blocks[i]
    if (b.type === 'text' || b.type === 'summary') {
      return i
    }
  }
  return -1
})

// 把「工具块 + phase=work 文本」合并为一个 work 组（可折叠）
// phase=answer 的 assistant_text 作为分段标志，单独成 normal 组
interface BlockGroup {
  type: 'work' | 'normal'
  items: (MessageBlock & { _isLastText?: boolean })[]
}

const groupedBlocks = computed<BlockGroup[]>(() => {
  const blocks = props.blocks || []
  const groups: BlockGroup[] = []
  let current: BlockGroup | null = null

  blocks.forEach((b, idx) => {
    const isFileTool = b.type === 'tool' && FILE_EDIT_TOOL_NAMES.has(b.tool_name || '')
    const isFinalText =
      (b.type === 'text' || b.type === 'summary') && b.phase !== 'work'
    // 文件变更工具单独成组，不折叠在"思考过程"中
    const groupType: 'work' | 'normal' = isFileTool ? 'normal' : (isFinalText ? 'normal' : 'work')
    if (!current || current.type !== groupType) {
      current = { type: groupType, items: [] }
      groups.push(current)
    }
    const isLastText = idx === lastTextBlockIndex.value
    current.items.push({ ...b, _isLastText: isLastText })
  })
  return groups
})

// 折叠状态：默认全部折叠；流式中最后一组保持展开
const workOpenMap = ref<Record<number, boolean>>({})

function toggleWork(idx: number) {
  workOpenMap.value = { ...workOpenMap.value, [idx]: !isWorkOpen(idx) }
}

function isWorkOpen(idx: number): boolean {
  if (idx in workOpenMap.value) return workOpenMap.value[idx]
  // 默认：流式中且是最后一组 → 展开；否则 → 折叠
  if (props.isLoading && idx === groupedBlocks.value.length - 1) return true
  return false
}

/**
 * 拦截 AI 回复中渲染出来的 <a> 链接点击：
 * 不走系统/外部浏览器，改为派发全局事件让右侧 BrowserPanel 打开它。
 * 仅处理 http/https 链接；mailto/锚点/javascript 等保持默认行为。
 */
function onMessageClick(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  if (!target) return
  const anchor = target.closest('a') as HTMLAnchorElement | null
  if (!anchor) return
  // 已是下载链接（带 download 属性）保留默认
  if (anchor.hasAttribute('download')) return
  const href = anchor.getAttribute('href') || ''
  if (!href) return
  // 只接管 http/https，让其余协议（mailto:/#anchor/javascript:）走默认
  if (!/^https?:\/\//i.test(href)) return
  // 用户用 ctrl/meta/中键时仍交给系统处理（保留新窗口打开等习惯）
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return
  e.preventDefault()
  e.stopPropagation()
  window.dispatchEvent(new CustomEvent('aries:open-url', { detail: { url: href } }))
}
</script>

<style scoped>
.assistant-message {
  width: 100%;
  font-family: 'Inter', 'Noto Sans SC', ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  letter-spacing: -0.003em;
}

/* 运行元数据栏 */
.meta-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
  padding: 4px 0 10px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border, rgba(0,0,0,0.06));
  font-size: 11px;
  color: var(--text-muted, #999);
  line-height: 1.4;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.meta-item svg {
  opacity: 0.7;
  flex-shrink: 0;
}

.meta-model {
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
  font-weight: 500;
  color: var(--text-secondary, #666);
}

.meta-context {
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--bg-secondary, #f0f0f0);
  font-weight: 500;
}

.meta-context--high {
  background: #fee2e2;
  color: #dc2626;
}

/* 工作过程组（极简风：无边框/背景，仅小三角触发器） */
.work-block {
  margin: 4px 0 8px;
}

.work-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px 2px 0;
  cursor: pointer;
  user-select: none;
  color: var(--text-muted, #9ca3af);
  font-size: 12px;
  border-radius: 4px;
  transition: color 0.15s;
}

.work-header:hover {
  color: var(--text-secondary, #6b7280);
}

.work-icon {
  transition: transform 0.18s;
  flex-shrink: 0;
  opacity: 0.85;
}

.work-icon.expanded {
  transform: rotate(90deg);
}

.work-title {
  font-weight: 400;
  letter-spacing: 0;
}

.work-content {
  margin-top: 5px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  max-height: 360px;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  padding-right: 4px;
}

.work-content > * {
  flex-shrink: 0;
}

.work-content :deep(.tool-block),
.work-content :deep(.file-edit-card) {
  flex-shrink: 0;
}

.work-content::-webkit-scrollbar {
  width: 6px;
}

.work-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.14);
  border-radius: 3px;
}

.work-content::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.22);
}

.reasoning-block {
  margin: 4px 0 8px;
}

.reasoning-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px 2px 0;
  cursor: pointer;
  user-select: none;
  color: var(--text-muted, #9ca3af);
  font-size: 12px;
}

.reasoning-icon {
  transition: transform 0.18s;
  flex-shrink: 0;
}

.reasoning-icon.expanded {
  transform: rotate(90deg);
}

.reasoning-title {
  font-weight: 400;
}

.reasoning-count {
  font-size: 11px;
  color: var(--text-muted, #9ca3af);
}

.reasoning-content {
  margin-top: 5px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  padding-right: 4px;
}

.reasoning-content::-webkit-scrollbar {
  width: 6px;
}

.reasoning-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.14);
  border-radius: 3px;
}

.reasoning-text {
  margin: 0;
  line-height: 1.4;
}

.reasoning-text :deep(.rich-text-content) {
  line-height: 1.4 !important;
}

.reasoning-text :deep(p) {
  margin: 3px 0 !important;
}

/* 工具块样式 */
.tools-block {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-item {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-secondary);
  padding: 12px;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.tool-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-icon {
  color: var(--text-muted);
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  font-family: monospace;
}

.tool-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 12px;
}

.tool-status.completed {
  background: #dcfce7;
  color: #166534;
}

.tool-status.running {
  background: #fef3c7;
  color: #92400e;
}

.tool-status.error {
  background: #fee2e2;
  color: #991b1b;
}

.tool-args,
.tool-output {
  margin-top: 8px;
}

.tool-args details,
.tool-output details {
  font-size: 13px;
}

.tool-args summary,
.tool-output summary {
  cursor: pointer;
  color: var(--text-secondary);
  user-select: none;
}

.tool-args summary:hover,
.tool-output summary:hover {
  color: var(--text);
}

.code-block {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  margin-top: 6px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-all;
}

/* 消息内容 */
.message-content {
  width: 100%;
}

/* 文本块样式（blocks 方式） */
.text-block {
  width: 100%;
}

.error-block {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  background: #fee2e2;
  border: 1px solid #fca5a5;
  border-radius: 6px;
  padding: 3px 8px;
  margin: 2px 0;
  color: #b91c1c;
  width: 100%;
  line-height: 1.3;
}

.error-block :deep(.markdown-body) {
  margin: 0;
  padding: 0;
  line-height: 1.3;
}

.error-block :deep(.markdown-body p) {
  margin: 0;
}

.error-block .error-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  color: #dc2626;
}

/* step_limit_exceeded 专用：不显示为错误，而是温和的暂停提示 */
.pause-block {
  background: #f0f9ff;
  border-color: #bae6fd;
  color: #0369a1;
}

.pause-block .error-header {
  color: #0284c7;
}

/* 加载动画 */
.loading-dots {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

/* 统一复制按钮：始终位于消息最底部 */
.message-actions {
  display: flex;
  justify-content: flex-start;
  margin-top: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-muted, #999);
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--bg-secondary, rgba(0,0,0,0.04));
  color: var(--text-secondary, #666);
}
</style>
