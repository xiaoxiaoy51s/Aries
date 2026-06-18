<template>
  <aside v-show="visible" class="right-panel" :style="{ width: panelWidth + 'px' }">
    <!-- 拖动调整宽度的 handle -->
    <div class="resize-handle" @mousedown="startResize"></div>

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

      <BrowserPanel v-show="activeTab === 'browser'" :visible="activeTab === 'browser'" />

      <GitPanel v-show="activeTab === 'git'" :visible="activeTab === 'git'" @show-diff="onShowDiff" @show-commit-diff="onShowCommitDiff" />

      <DiffPanel v-show="activeTab === 'diff'" :visible="activeTab === 'diff'" :file-path="diffFilePath" :commit-hash="diffCommitHash" />

      <ExplorerPanel v-show="activeTab === 'explorer'" :visible="activeTab === 'explorer'" />
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

type PanelTabId = 'console' | 'browser' | 'git' | 'diff' | 'explorer'

const props = defineProps<{
  visible: boolean
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
]

const activeTab = ref<PanelTabId>('console')
const panelWidth = ref(480)
const diffFilePath = ref<string | null>(null)
const diffCommitHash = ref<string | null>(null)

// 拖动调整宽度
let resizing = false
let startX = 0
let startWidth = 0

function startResize(e: MouseEvent) {
  resizing = true
  startX = e.clientX
  startWidth = panelWidth.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onResize(e: MouseEvent) {
  if (!resizing) return
  // 向左拖动增大宽度
  const delta = startX - e.clientX
  const newWidth = Math.min(Math.max(startWidth + delta, 320), 800)
  panelWidth.value = newWidth
}

function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
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

onMounted(() => {
  window.addEventListener('mimo:focus-console', onFocusConsole)
})

onUnmounted(() => {
  window.removeEventListener('mimo:focus-console', onFocusConsole)
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
  left: -3px;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 10;
}

.resize-handle:hover {
  background: rgba(0, 120, 212, 0.2);
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
