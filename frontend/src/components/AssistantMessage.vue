<template>
  <div class="assistant-message">
    <!-- 使用 blocks 方式渲染（参考 frontend1） -->
    <template v-if="props.blocks && props.blocks.length > 0">
      <template v-for="(block, blockIndex) in props.blocks" :key="blockIndex">
        <ToolBlock
          v-if="block.type === 'tool'"
          :tool-name="block.tool_name || 'unknown'"
          :status="block.status || 'running'"
          :args="block.args"
          :preview="block.preview"
          :result="block.result || ''"
          :error="block.error || ''"
          :started-at="block.started_at || ''"
          :ended-at="block.ended_at || ''"
          :compact="false"
        />
        <div
          v-else-if="block.type === 'text' || block.type === 'summary'"
          class="text-block"
        >
          <MarkdownRenderer 
            :content="block.text || ''" 
            :text-color="block.phase === 'work' ? '#64748b' : textColor" 
            :font-size="block.phase === 'work' ? Math.max(12, fontSize - 2) : fontSize" 
            :show-actions="block.phase !== 'work' && blockIndex === lastTextBlockIndex" 
            :is-streaming="isLoading"
          />
        </div>
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
        <MarkdownRenderer :content="props.content" :text-color="textColor" :font-size="fontSize" :show-actions="true" :is-streaming="isLoading" />
      </div>
    </template>

    <!-- 加载动画（流式输出中） -->
    <div v-if="isLoading" class="loading-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolBlock from './ToolBlock.vue'

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
}

const props = withDefaults(defineProps<{
  content?: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  isLoading?: boolean
  textColor?: string
  fontSize?: number
}>(), {
  content: '',
  reasoning: () => [],
  tools: () => [],
  blocks: () => [],
  isLoading: false,
  textColor: '#1a1a1a',
  fontSize: 15
})

const showReasoning = ref(false)

const textColor = computed(() => props.textColor || '#1a1a1a')
const fontSize = computed(() => props.fontSize || 15)

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
</script>

<style scoped>
.assistant-message {
  width: 100%;
}

/* 思考块样式 */
.reasoning-block {
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-secondary);
  overflow: hidden;
}

.reasoning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.reasoning-header:hover {
  background: var(--accent-hover);
}

.reasoning-icon {
  transition: transform 0.2s;
  color: var(--text-muted);
}

.reasoning-icon.expanded {
  transform: rotate(90deg);
}

.reasoning-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.reasoning-count {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}

.reasoning-content {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}

.reasoning-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.reasoning-text:last-child {
  margin-bottom: 0;
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
</style>
