<template>
  <div id="app" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <!-- 自定义标题栏 -->
    <div class="title-bar">
      <div class="title-bar-left">
        <button
          type="button"
          class="title-bar-toggle"
          :title="sidebarOpen ? '收起侧边栏' : '展开侧边栏'"
          :aria-label="sidebarOpen ? '收起侧边栏' : '展开侧边栏'"
          @click="toggleSidebar"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path v-if="sidebarOpen" d="M9 3v18"/>
            <path v-else d="M9 3v18M3 9h6"/>
          </svg>
        </button>

        <button
          type="button"
          class="title-bar-icon-btn"
          :class="{ disabled: !canGoBack }"
          title="返回"
          aria-label="返回"
          @click="onGoBack"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5"/>
            <path d="M12 19l-7-7 7-7"/>
          </svg>
        </button>

        <button
          type="button"
          class="title-bar-icon-btn"
          :class="{ disabled: !canGoForward }"
          title="前进"
          aria-label="前进"
          @click="onGoForward"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14"/>
            <path d="M12 5l7 7-7 7"/>
          </svg>
        </button>

        <span class="title-bar-brand">Aries</span>

        <TitleBarMenu :menus="menus" @select="onMenuSelect" />
      </div>
      <div class="title-bar-spacer" />
      <div class="title-bar-controls">
        <button type="button" class="title-bar-btn" title="最小化" @click="onMinimize">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14"/>
          </svg>
        </button>
        <button type="button" class="title-bar-btn" :title="isMaximized ? '还原' : '最大化'" @click="onMaximize">
          <svg v-if="isMaximized" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
          </svg>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
        </button>
        <button type="button" class="title-bar-btn title-bar-btn--close" title="关闭" @click="onClose">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'
import { useModelStore } from '@/stores/model'
import { useWorkspaceStore } from '@/stores/workspace'
import { initPaths } from '@/utils/paths'
import TitleBarMenu, { type MenuDef } from '@/components/TitleBarMenu.vue'

const { sidebarOpen, toggleSidebar } = useSidebar()

const modelStore = useModelStore()
const workspaceStore = useWorkspaceStore()
const BACKEND_PORT = 30000
modelStore.setBackendPort(BACKEND_PORT)

const isMaximized = ref(false)

onMounted(async () => {
  modelStore.loadModels().catch(() => {})
  await initPaths().catch(() => {})
  workspaceStore.initWorkDir().catch(() => {})

  isMaximized.value = !!(await window.electronAPI?.windowIsMaximized?.())
  window.electronAPI?.onWindowMaximizedChange?.((value: boolean) => {
    isMaximized.value = value
  })
})

async function onMinimize() {
  window.electronAPI?.windowMinimize?.()
}

async function onMaximize() {
  window.electronAPI?.windowMaximize?.()
}

async function onClose() {
  window.electronAPI?.windowClose?.()
}

const router = useRouter()

// 追踪路由历史，实现浏览器式的返回/前进
const historyStack = ref<string[]>([])
const historyIndex = ref(-1)

const canGoBack = computed(() => historyIndex.value > 0)
const canGoForward = computed(() => historyIndex.value < historyStack.value.length - 1)

function recordRoute(path: string) {
  // 如果不在栈尾，先截断当前位置之后的“前进历史”
  if (historyIndex.value < historyStack.value.length - 1) {
    historyStack.value = historyStack.value.slice(0, historyIndex.value + 1)
  }
  // 避免连续重复记录
  if (historyStack.value[historyIndex.value] !== path) {
    historyStack.value.push(path)
    historyIndex.value++
  }
}

router.afterEach((to) => {
  if (historyStack.value.length === 0) {
    historyStack.value.push(to.fullPath)
    historyIndex.value = 0
    return
  }

  const prevPath = historyStack.value[historyIndex.value - 1]
  const nextPath = historyStack.value[historyIndex.value + 1]

  if (to.fullPath === prevPath) {
    // 浏览器或程序触发 back
    historyIndex.value--
  } else if (to.fullPath === nextPath) {
    // 浏览器或程序触发 forward
    historyIndex.value++
  } else if (to.fullPath !== historyStack.value[historyIndex.value]) {
    recordRoute(to.fullPath)
  }
})

function onGoBack() {
  if (canGoBack.value) router.back()
}

function onGoForward() {
  if (canGoForward.value) router.forward()
}

const menus: MenuDef[] = [
  {
    key: 'file',
    label: '文件',
    items: [
      { id: 'new-window', label: '新建窗口', shortcut: 'Ctrl+Shift+N' },
      { id: 'new-chat', label: '新对话', shortcut: 'Ctrl+N' },
      { id: 'quick-chat', label: '快速对话', shortcut: 'Alt+Ctrl+N' },
      { id: 'open-folder', label: '打开文件夹...', shortcut: 'Ctrl+O' },
      { divider: true },
      { id: 'settings', label: '设置', shortcut: 'Ctrl+,' },
      { divider: true },
      { id: 'exit', label: '退出', shortcut: 'Ctrl+Q' },
    ],
  },
]

function onMenuSelect(menuKey: string, item: { id?: string; divider?: boolean }) {
  if (item.divider || !item.id) return

  const id = item.id

  if (menuKey === 'file') {
    switch (id) {
      case 'new-window':
        window.electronAPI?.createNewWindow?.()
        break
      case 'new-chat':
      case 'quick-chat':
        window.dispatchEvent(new CustomEvent('aries:new-chat'))
        break
      case 'open-folder':
        window.dispatchEvent(new CustomEvent('aries:select-work-dir'))
        break
      case 'exit':
        window.electronAPI?.windowClose?.()
        break
      case 'settings':
        window.dispatchEvent(new CustomEvent('aries:open-settings'))
        break
    }
    return
  }

}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --bg-app: #fafbfd;
  --bg-sidebar: #fbfcfe;
  --bg-panel: #ffffff;
  --bg-content: #ffffff;
  --bg-chat: #ffffff;
  --border: #eef1f6;
  --border-strong: #e3e8f0;
  --text: #1a1a18;
  --text-secondary: #5c6672;
  --text-muted: #8a96a6;
  --accent: #2d2d2a;
  --accent-hover: #f5f7fb;
  --accent-active: #eef2f8;
  --send-bg: #1a1a18;
  --send-hover: #333330;
  --user-msg: #e8f0fa;
  --assistant-msg: #ffffff;
  --radius: 12px;
  --radius-lg: 16px;
  --sidebar-width: 260px;
  --shadow-panel: 0 1px 2px rgba(80, 120, 180, 0.04), 0 4px 16px rgba(80, 120, 180, 0.03);
  /* 侧边栏 / 标题栏：极浅蓝，接近白 */
  --glass-surface: rgba(252, 253, 255, 0.82);
  --glass-surface-soft: rgba(250, 251, 254, 0.72);
  --glass-border: rgba(232, 237, 245, 0.95);
  --glass-highlight: rgba(255, 255, 255, 0.95);
  --glass-blur: blur(24px) saturate(1.12);
  --glass-blur-light: blur(12px) saturate(1.08);
  --glass-shadow:
    inset 0 1px 0 var(--glass-highlight),
    4px 0 16px rgba(80, 120, 180, 0.03);
  --glass-shadow-top:
    inset 0 1px 0 var(--glass-highlight),
    0 2px 12px rgba(80, 120, 180, 0.03);
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background-color: #f8fafc;
  background-image:
    radial-gradient(ellipse 90% 70% at 8% 10%, rgba(236, 244, 255, 0.35) 0%, transparent 55%),
    radial-gradient(ellipse 80% 60% at 92% 90%, rgba(240, 246, 255, 0.25) 0%, transparent 50%),
    linear-gradient(165deg, #fbfcfe 0%, #f8fafc 50%, #fafbfd 100%);
  color: var(--text);
  overflow: hidden;
  font-size: 14px;
  line-height: 1.5;
}

#app {
  display: flex;
  width: 100vw;
  height: 100vh;
  position: relative;
  background: transparent;
}

/* 自定义标题栏 */
.title-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  height: 40px;
  display: flex;
  align-items: center;
  padding: 0 16px 0 12px;
  background: var(--glass-surface);
  border-bottom: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow-top);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  -webkit-app-region: drag;
  app-region: drag;
}

.title-bar-left {
  display: flex;
  align-items: center;
  gap: 6px;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.title-bar-toggle,
.title-bar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--glass-border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.55);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
  flex-shrink: 0;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  backdrop-filter: var(--glass-blur-light);
  -webkit-backdrop-filter: var(--glass-blur-light);
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.title-bar-toggle:hover,
.title-bar-icon-btn:hover:not(.disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.title-bar-icon-btn.disabled {
  opacity: 0.35;
  cursor: default;
  pointer-events: none;
}

.title-bar-brand {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  user-select: none;
  margin-left: 6px;
  margin-right: 8px;
}

.title-bar-spacer {
  flex: 1;
  -webkit-app-region: drag;
  app-region: drag;
}

.title-bar-controls {
  display: flex;
  align-items: center;
  gap: 2px;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.title-bar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.title-bar-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.title-bar-btn--close:hover {
  background: #ef4444;
  color: #fff;
}

.app-container {
  width: 100%;
  height: 100%;
}

/* 滚动条 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 3px;
}
</style>
