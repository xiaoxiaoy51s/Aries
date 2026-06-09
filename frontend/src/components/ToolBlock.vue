<template>
  <div class="tool-block" :class="{ 'tool-block--expanded': isExpanded, 'tool-block--confirm': pendingConfirmation }">
    <!-- 折叠状态：显示工具名和参数预览 -->
    <div v-if="!isExpanded" class="tool-header" @click="toggleExpand">
      <div class="tool-title">
        <span class="tool-name">{{ toolName }}</span>
        <span class="tool-args-preview">{{ argsPreview }}</span>
      </div>
      <span v-if="pendingConfirmation" class="confirm-badge">待确认</span>
      <button
        v-if="isCliExecutor && status === 'running'"
        type="button"
        class="view-terminal-btn"
        title="在控制台查看命令执行过程"
        @click.stop="openTerminal"
      >查看终端</button>
    </div>
    
    <!-- 展开状态：显示完整内容 -->
    <div v-else class="tool-body">
      <!-- 头部（可点击折叠） -->
      <div class="tool-body-header" @click="toggleExpand">
        <div class="tool-title">
          <span class="tool-name">{{ toolName }}</span>
          <span class="tool-args-preview">{{ argsPreview }}</span>
        </div>
        <button
          v-if="isCliExecutor && status === 'running'"
          type="button"
          class="view-terminal-btn"
          title="在控制台查看命令执行过程"
          @click.stop="openTerminal"
        >查看终端</button>
      </div>

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
        <div class="section-content code-block">
          <pre class="code-text" :class="{ 'error-text': error }">{{ result || error }}</pre>
        </div>
      </div>
      
      <!-- 运行中状态 -->
      <div v-else-if="status === 'running' && !pendingConfirmation" class="tool-section">
        <span class="section-label">状态</span>
        <div class="section-content">
          <span class="running-text">运行中...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  toolName: string
  status: string
  args?: Record<string, any>
  preview?: string
  result?: string
  error?: string
  startedAt?: string
  endedAt?: string
  compact?: boolean
  pendingConfirmation?: boolean
  dangerInfo?: string
}>()

const isExpanded = ref(false)

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

function openTerminal() {
  const workspace = useWorkspaceStore()
  workspace.openPanel('console')
  window.dispatchEvent(new CustomEvent('mimo:focus-console'))
}
</script>

<style scoped>
.tool-block {
  background: transparent;
  border-radius: 4px;
  margin: 2px 0;
  overflow: hidden;
  border: none;
  border-left: 2px solid #cbd5e1;
  padding-left: 8px;
}

.tool-block--confirm {
  border-left-color: #f59e0b;
}

.tool-block--expanded {
  background: transparent;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.view-terminal-btn {
  font-size: 10px;
  color: #3b82f6;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 1px 8px;
  border-radius: 999px;
  cursor: pointer;
  margin-left: 6px;
  flex-shrink: 0;
}

.view-terminal-btn:hover {
  background: #dbeafe;
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
  justify-content: space-between;
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
  color: #ef4444;
}

.running-text {
  font-size: 11px;
  color: #3b82f6;
  font-style: italic;
}
</style>
