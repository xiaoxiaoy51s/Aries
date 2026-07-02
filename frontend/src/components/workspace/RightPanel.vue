<template>
  <aside v-show="visible" class="right-panel" :style="{ width: panelWidth + 'px' }">
    <div
      class="resize-handle"
      :class="{ resizing }"
      @pointerdown="startResize"
      @pointermove="onResize"
      @pointerup="stopResize"
      @pointercancel="stopResize"
    ></div>

    <div v-if="resizing" class="resize-shield"></div>

    <div class="panel-tabbar">
      <div class="panel-tab-list">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="panel-tab"
          :class="{ active: tab.id === activeTabId }"
          :title="tab.title"
          @click="activeTabId = tab.id"
        >
          <span class="panel-tab-icon" v-html="iconForKind(tab.kind)"></span>
          <span class="panel-tab-title">{{ tab.title }}</span>
          <span
            class="panel-tab-close"
            title="关闭"
            @click.stop="closeTab(tab.id)"
          >×</span>
        </button>
      </div>

      <div class="panel-tab-add-wrap">
        <button
          type="button"
          class="panel-tab-add"
          title="新建标签页"
          aria-label="新建标签页"
          :aria-expanded="addMenuOpen"
          @click.stop="toggleAddMenu"
        >
          +
        </button>
        <div v-if="addMenuOpen" class="panel-add-menu" @mousedown.prevent>
          <button
            v-for="item in launcherItems"
            :key="item.kind"
            type="button"
            class="panel-add-item"
            @click="addTabFromMenu(item.kind)"
          >
            <span class="panel-add-icon" v-html="item.icon"></span>
            <span class="panel-add-label">{{ item.label }}</span>
          </button>
        </div>
      </div>

      <button type="button" class="panel-close-btn" title="关闭面板" @click="closePanel">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6 6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <div class="panel-content">
      <div v-if="tabs.length === 0" class="panel-home">
        <button
          v-for="item in launcherItems"
          :key="item.kind"
          type="button"
          class="panel-launcher-item"
          @click="addTabFromMenu(item.kind)"
        >
          <span class="panel-launcher-icon" v-html="item.icon"></span>
          <span class="panel-launcher-label">{{ item.label }}</span>
        </button>
      </div>

      <template v-for="tab in tabs" :key="tab.id">
        <ConsolePanel
          v-if="tab.kind === 'console'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
          @close="closeTab(tab.id)"
        />

        <BrowserPanel
          v-else-if="tab.kind === 'browser'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
          :initial-url="tab.browserUrl || ''"
        />

        <GitPanel
          v-else-if="tab.kind === 'git'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
          @show-diff="onShowDiff"
          @show-commit-diff="onShowCommitDiff"
        />

        <DiffPanel
          v-else-if="tab.kind === 'diff'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
          :file-path="tab.diffFilePath || null"
          :commit-hash="tab.diffCommitHash || null"
          :inline-original="tab.inlineOriginal"
          :inline-modified="tab.inlineModified"
          :inline-path="tab.inlinePath"
          :inline-key="tab.inlineKey"
        />

        <ExplorerPanel
          v-else-if="tab.kind === 'explorer'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
        />

        <SideChatPanel
          v-else-if="tab.kind === 'sidechat'"
          v-show="tab.id === activeTabId"
          :visible="tab.id === activeTabId"
          :session-id="sessionId"
          :work-dir="workDir"
        />
      </template>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import ConsolePanel from '@/components/workspace/ConsolePanel.vue'
import BrowserPanel from '@/components/workspace/BrowserPanel.vue'
import GitPanel from '@/components/workspace/GitPanel.vue'
import DiffPanel from '@/components/workspace/DiffPanel.vue'
import ExplorerPanel from '@/components/workspace/ExplorerPanel.vue'
import SideChatPanel from '@/components/workspace/SideChatPanel.vue'

type PanelKind = 'console' | 'browser' | 'git' | 'explorer' | 'sidechat' | 'diff'

interface WorkspaceTab {
  id: string
  kind: PanelKind
  title: string
  browserUrl?: string
  diffFilePath?: string
  diffCommitHash?: string | null
  inlineOriginal?: string
  inlineModified?: string
  inlinePath?: string
  inlineKey?: number
}

const props = defineProps<{
  visible: boolean
  sessionId?: string
  workDir?: string
  inlineDiff?: { path: string; original: string; modified: string; key: number } | null
}>()

const emit = defineEmits<{
  close: []
}>()

const launcherItems: { kind: Exclude<PanelKind, 'diff'>; label: string; icon: string }[] = [
  {
    kind: 'console',
    label: '控制台',
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m7 9 3 3-3 3"/><path d="M13 15h4"/><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
  },
  {
    kind: 'browser',
    label: '浏览器',
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  },
  {
    kind: 'git',
    label: 'Git',
    icon: '<svg width="16" height="16" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M512 64c-16.128 0-31.872 5.888-44 18.016l-90.016 90.976c-4.864 2.624-8.96 6.4-11.968 11.008l-284.032 284a62.304 62.304 0 0 0 0 88l386.016 386.016a62.56 62.56 0 0 0 88 0l386.016-386.016a62.304 62.304 0 0 0 0-88L555.968 81.984A61.536 61.536 0 0 0 512 64z m0 64.992L895.008 512 512 895.008 128.992 512l265.024-264.992 56 56A63.36 63.36 0 0 0 448 320c0 23.616 12.864 43.872 32 55.008v273.984c-19.136 11.136-32 31.36-32 55.008a63.968 63.968 0 1 0 128 0c0-23.616-12.864-43.872-32-55.008v-250.976l98.016 97.984A63.968 63.968 0 0 0 704 576c35.328 0 63.968-28.64 63.968-64a63.968 63.968 0 0 0-80-62.016L573.984 336A63.968 63.968 0 0 0 512 256a63.36 63.36 0 0 0-16.96 2.016l-56-56z"/></svg>',
  },
  {
    kind: 'explorer',
    label: '文件',
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    kind: 'sidechat',
    label: '临时对话',
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M12 8v4M10 10h4"/></svg>',
  },
]

const kindIcons: Record<PanelKind, string> = {
  console: launcherItems[0].icon,
  browser: launcherItems[1].icon,
  git: launcherItems[2].icon,
  explorer: launcherItems[3].icon,
  sidechat: launcherItems[4].icon,
  diff: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
}

const kindLabels: Record<PanelKind, string> = {
  console: '控制台',
  browser: '新选项卡',
  git: 'Git',
  explorer: '文件',
  sidechat: '临时对话',
  diff: 'Diff',
}

const tabs = ref<WorkspaceTab[]>([])
const activeTabId = ref('')
const addMenuOpen = ref(false)
const panelWidth = ref(480)

const resizing = ref(false)
let startX = 0
let startWidth = 0
let activePointerId: number | null = null

function iconForKind(kind: PanelKind): string {
  return kindIcons[kind]
}

function newTabId(): string {
  return crypto.randomUUID()
}

function toggleAddMenu() {
  addMenuOpen.value = !addMenuOpen.value
}

function closeAddMenu() {
  addMenuOpen.value = false
}

function addTabFromMenu(kind: Exclude<PanelKind, 'diff'>, opts?: { browserUrl?: string }) {
  closeAddMenu()

  if (kind !== 'browser') {
    const existing = tabs.value.find((t) => t.kind === kind)
    if (existing) {
      activeTabId.value = existing.id
      return
    }
  }

  const tab: WorkspaceTab = {
    id: newTabId(),
    kind,
    title: kindLabels[kind],
    browserUrl: opts?.browserUrl,
  }
  if (opts?.browserUrl) {
    tab.title = hostFromUrl(opts.browserUrl) || kindLabels.browser
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
}

function openOrFocusTab(kind: Exclude<PanelKind, 'diff'>, opts?: { browserUrl?: string }) {
  addTabFromMenu(kind, opts)
}

function closeTab(id: string) {
  const idx = tabs.value.findIndex((t) => t.id === id)
  if (idx < 0) return
  tabs.value.splice(idx, 1)
  if (activeTabId.value === id) {
    const next = tabs.value[idx] || tabs.value[idx - 1]
    activeTabId.value = next?.id || ''
  }
}

function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname || ''
  } catch {
    return ''
  }
}

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
  const delta = startX - e.clientX
  panelWidth.value = Math.min(Math.max(startWidth + delta, 320), 1200)
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
  closeAddMenu()
  emit('close')
}

function onShowDiff(filePath: string) {
  const tab: WorkspaceTab = {
    id: newTabId(),
    kind: 'diff',
    title: filePath.split(/[/\\]/).pop() || 'Diff',
    diffFilePath: filePath,
    diffCommitHash: null,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
}

function onShowCommitDiff(filePath: string, hash: string) {
  const tab: WorkspaceTab = {
    id: newTabId(),
    kind: 'diff',
    title: filePath.split(/[/\\]/).pop() || 'Diff',
    diffFilePath: filePath,
    diffCommitHash: hash,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
}

watch(() => props.inlineDiff, (val) => {
  if (!val) return
  const tab: WorkspaceTab = {
    id: newTabId(),
    kind: 'diff',
    title: val.path.split(/[/\\]/).pop() || 'Diff',
    diffFilePath: val.path,
    diffCommitHash: null,
    inlineOriginal: val.original,
    inlineModified: val.modified,
    inlinePath: val.path,
    inlineKey: val.key,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
})

function onOpenUrl(e: Event) {
  const url = (e as CustomEvent).detail?.url
  if (typeof url !== 'string' || !url) return
  addTabFromMenu('browser', { browserUrl: url })
}

function onFocusConsole() {
  openOrFocusTab('console')
}

function onDocumentClick() {
  closeAddMenu()
}

onMounted(() => {
  window.addEventListener('aries:open-url', onOpenUrl as EventListener)
  window.addEventListener('aries:focus-console', onFocusConsole)
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  window.removeEventListener('aries:open-url', onOpenUrl as EventListener)
  window.removeEventListener('aries:focus-console', onFocusConsole)
  document.removeEventListener('click', onDocumentClick)
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

.resize-shield {
  position: fixed;
  inset: 0;
  z-index: 9999;
  cursor: col-resize;
  background: transparent;
}

.panel-tabbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 40px;
  box-sizing: border-box;
}

.panel-tab-list {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
}

.panel-tab-list::-webkit-scrollbar {
  display: none;
}

.panel-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 168px;
  padding: 6px 8px 6px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
}

.panel-tab:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.panel-tab.active {
  background: #f0f0f0;
  color: var(--text);
  font-weight: 500;
}

.panel-tab-icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.panel-tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.panel-tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1;
  opacity: 0.55;
  flex-shrink: 0;
}

.panel-tab-close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.06);
}

.panel-tab-add-wrap {
  position: relative;
  flex-shrink: 0;
}

.panel-tab-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.panel-tab-add:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.panel-add-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 220px;
  padding: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
  z-index: 30;
}

.panel-add-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.panel-add-item:hover {
  background: var(--accent-hover);
}

.panel-add-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
}

.panel-add-label {
  flex: 1;
  min-width: 0;
}

.panel-close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 6px;
  flex-shrink: 0;
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

.panel-home {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 20px;
  box-sizing: border-box;
}

.panel-launcher-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  max-width: 280px;
  padding: 10px 14px;
  border: none;
  border-radius: 8px;
  background: #f3f3f3;
  color: var(--text);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.panel-launcher-item:hover {
  background: #e8e8e8;
}

.panel-launcher-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-secondary);
}

.panel-launcher-label {
  flex: 1;
  min-width: 0;
}
</style>
