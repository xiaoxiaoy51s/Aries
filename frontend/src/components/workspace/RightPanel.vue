<template>
  <aside v-show="visible" class="right-panel" :style="{ width: panelWidth + 'px' }">
    <!-- 拖动调整宽度的 handle -->
    <div
      class="resize-handle"
      :class="{ resizing }"
      @pointerdown="startResize"
      @pointermove="onResize"
      @pointerup="stopResize"
      @pointercancel="stopResize"
    ></div>

    <!-- 拖动期间盖一层透明遮罩，防止 webview / iframe 抢走鼠标事件 -->
    <div v-if="resizing" class="resize-shield"></div>

    <!-- Tab 切换栏 -->
    <div class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="panel-tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <span class="tab-icon" v-html="tab.icon"></span>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
      <button type="button" class="panel-close-btn" title="关闭面板" @click="closePanel">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6 6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- 面板内容 -->
    <div class="panel-content">
      <ConsolePanel v-show="activeTab === 'console'" :visible="activeTab === 'console'" />

      <BrowserPanel
        v-show="activeTab === 'browser'"
        :visible="activeTab === 'browser'"
        :initial-url="browserPendingUrl"
      />

      <GitPanel v-show="activeTab === 'git'" :visible="activeTab === 'git'" @show-diff="onShowDiff" @show-commit-diff="onShowCommitDiff" />

      <DiffPanel v-show="activeTab === 'diff'" :visible="activeTab === 'diff'" :file-path="diffFilePath" :commit-hash="diffCommitHash" />

      <ExplorerPanel v-show="activeTab === 'explorer'" :visible="activeTab === 'explorer'" />

      <SideChatPanel
        v-show="activeTab === 'sidechat'"
        :visible="activeTab === 'sidechat'"
        :session-id="sessionId"
        :work-dir="workDir"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import ConsolePanel from '@/components/workspace/ConsolePanel.vue'
import BrowserPanel from '@/components/workspace/BrowserPanel.vue'
import GitPanel from '@/components/workspace/GitPanel.vue'
import DiffPanel from '@/components/workspace/DiffPanel.vue'
import ExplorerPanel from '@/components/workspace/ExplorerPanel.vue'
import SideChatPanel from '@/components/workspace/SideChatPanel.vue'

type PanelTabId = 'console' | 'browser' | 'git' | 'diff' | 'explorer' | 'sidechat'

const props = defineProps<{
  visible: boolean
  sessionId?: string
  workDir?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const tabs: { id: PanelTabId; label: string; icon: string }[] = [
  {
    id: 'console',
    label: '控制台',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m7 9 3 3-3 3"/><path d="M13 15h4"/><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
  },
  {
    id: 'browser',
    label: '浏览器',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  },
  {
    id: 'git',
    label: 'Git',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M6 9v6a3 3 0 0 0 3 3h6"/></svg>',
  },
  {
    id: 'diff',
    label: 'Diff',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18M3 12h6M15 12h6"/></svg>',
  },
  {
    id: 'explorer',
    label: '文件',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    id: 'sidechat',
    label: '临时对话',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
]

const activeTab = ref<PanelTabId>('console')
const panelWidth = ref(480)
const diffFilePath = ref<string | null>(null)
const diffCommitHash = ref<string | null>(null)
// 由 AssistantMessage 链接点击触发，传给 BrowserPanel 让其加载
const browserPendingUrl = ref<string>('')

// 拖动调整宽度（pointer 事件 + setPointerCapture：跨越 webview 也能稳定跟随）
const resizing = ref(false)
let startX = 0
let startWidth = 0
let activePointerId: number | null = null

function startResize(e: PointerEvent) {
  resizing.value = true
  startX = e.clientX
  startWidth = panelWidth.value
  activePointerId = e.pointerId
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onResize(e: PointerEvent) {
  if (!resizing.value || e.pointerId !== activePointerId) return
  // 向左拖动增大宽度
  const delta = startX - e.clientX
  const newWidth = Math.min(Math.max(startWidth + delta, 320), 1200)
  panelWidth.value = newWidth
}

function stopResize(e: PointerEvent) {
  if (!resizing.value) return
  resizing.value = false
  if (activePointerId !== null) {
    try { (e.currentTarget as HTMLElement).releasePointerCapture(activePointerId) } catch { /* 忽略 */ }
    activePointerId = null
  }
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

function closePanel() {
  emit('close')
}

function onShowDiff(filePath: string) {
  diffFilePath.value = filePath
  diffCommitHash.value = null
  activeTab.value = 'diff'
}

function onShowCommitDiff(filePath: string, hash: string) {
  diffFilePath.value = filePath
  diffCommitHash.value = hash
  activeTab.value = 'diff'
}

// 监听外部的 focus-console 事件（从 ToolBlock 的「查看终端」按钮触发）
function onFocusConsole() {
  activeTab.value = 'console'
}

// 监听 AI 回复中点击链接：切到浏览器面板并加载 URL
function onOpenUrl(e: Event) {
  const url = (e as CustomEvent).detail?.url
  if (typeof url !== 'string' || !url) return
  // 父级面板若被关闭也尝试请求展开（这里只能切 tab，开/关由上层管理）
  activeTab.value = 'browser'
  // 用 timestamp 拼一下确保同一 URL 也能触发 watch
  browserPendingUrl.value = url
}

onMounted(() => {
  window.addEventListener('aries:focus-console', onFocusConsole)
  window.addEventListener('aries:open-url', onOpenUrl as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('aries:focus-console', onFocusConsole)
  window.removeEventListener('aries:open-url', onOpenUrl as EventListener)
})
</script>

<style scoped>
.right-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-panel);
  margin-left: 8px;
  flex-shrink: 0;
  overflow: hidden;
  min-width: 320px;
  position: relative;
  height: 100%;
}

.resize-handle {
  position: absolute;
  left: -4px;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: col-resize;
  z-index: 10;
  /* 命中区域稍宽，但视觉上仍是细线 */
  touch-action: none;
}

.resize-handle::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
  transition: background 0.12s;
  transform: translateX(-50%);
}

.resize-handle:hover::before,
.resize-handle.resizing::before {
  background: rgba(59, 130, 246, 0.6);
}

/* 拖动时全屏遮罩，确保 webview/iframe 不会拦截 pointer 事件 */
.resize-shield {
  position: fixed;
  inset: 0;
  z-index: 9999;
  cursor: col-resize;
  background: transparent;
}

.panel-tabs {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 4px;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 36px;
}

.panel-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
}

.panel-tab-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.panel-tab-btn.active {
  background: var(--bg-panel);
  color: var(--text);
  font-weight: 500;
}

.tab-icon {
  display: inline-flex;
  align-items: center;
}

.panel-close-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s, color 0.12s;
}

.panel-close-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
</style>
