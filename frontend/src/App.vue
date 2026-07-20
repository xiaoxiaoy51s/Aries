<template>
  <div id="app" :class="{ 'sidebar-collapsed': !sidebarOpen, 'is-booting': !backendReady }">
    <!-- 自定义标题栏 -->
    <div class="title-bar">
      <div v-show="backendReady" class="title-bar-left">
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
    <RouterView v-show="backendReady" />
    <BackendBootSplash
      v-if="!backendReady"
      :error="bootError"
      @retry="onBootRetry"
    />
    <OnboardingModal
      v-if="showOnboarding"
      :visible="showOnboarding"
      @skip="showOnboarding = false"
      @save="handleOnboardingSave"
    />
    <EnvCheckModal
      v-if="showEnvCheck"
      :visible="showEnvCheck"
      :missing="missingRuntimes"
      @skip="showEnvCheck = false"
      @all-installed="onEnvAllInstalled"
    />
    <ConnectionLostModal
      v-if="lostConnection"
      @restart="onRestartApp"
      @retry="onRetryConnection"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'
import { useBackendBoot } from '@/composables/useBackendBoot'
import { useModelStore } from '@/stores/model'
import { useWorkspaceStore } from '@/stores/workspace'
import { initPaths } from '@/utils/paths'
import TitleBarMenu, { type MenuDef } from '@/components/TitleBarMenu.vue'
import BackendBootSplash from '@/components/BackendBootSplash.vue'
import OnboardingModal from '@/components/OnboardingModal.vue'
import EnvCheckModal from '@/components/EnvCheckModal.vue'
import ConnectionLostModal from '@/components/ConnectionLostModal.vue'

const { sidebarOpen, toggleSidebar } = useSidebar()

const modelStore = useModelStore()
const workspaceStore = useWorkspaceStore()
const BACKEND_PORT = 30000
modelStore.setBackendPort(BACKEND_PORT)

const { ready: backendReady, error: bootError, lostConnection, start: startBackendBoot } = useBackendBoot(BACKEND_PORT)

const isMaximized = ref(false)
let appInitialized = false
const showOnboarding = ref(false)
const showEnvCheck = ref(false)
const missingRuntimes = ref<string[]>([])

async function initAppData() {
  if (appInitialized) return
  appInitialized = true
  await modelStore.loadModels().catch(() => {})
  // 首次启动且未配置任何模型时，弹出引导界面
  if (modelStore.models.length === 0) {
    showOnboarding.value = true
  }
  await initPaths().catch(() => {})
  workspaceStore.initWorkDir().catch(() => {})
  // 检查环境缺失
  try {
    const res = await fetch(`http://localhost:${BACKEND_PORT}/api/dev-env/missing`)
    const data = await res.json()
    if (data.missing && data.missing.length > 0) {
      missingRuntimes.value = data.missing
      showEnvCheck.value = true
    }
  } catch {
    // 后端未就绪，忽略
  }
}

function onEnvAllInstalled() {
  showEnvCheck.value = false
  missingRuntimes.value = []
}

async function handleOnboardingSave(data: { model: string; baseUrl: string; apiKey: string }) {
  try {
    await modelStore.addModel({
      model: data.model,
      name: data.model,
      baseUrl: data.baseUrl,
      apiKey: data.apiKey,
      isActive: true,
    })
    showOnboarding.value = false
  } catch (e) {
    console.error('引导配置模型失败', e)
    alert('保存失败，请稍后在设置中手动配置模型')
    showOnboarding.value = false
  }
}

function onBootRetry() {
  window.electronAPI?.ensureBackend?.()
  startBackendBoot()
}

function onRestartApp() {
  window.electronAPI?.relaunch?.()
}

function onRetryConnection() {
  window.electronAPI?.forceRestartBackend?.()
  startBackendBoot()
}

watch(backendReady, (ready) => {
  if (ready) {
    void initAppData()
    window.dispatchEvent(new Event('aries:refresh-sessions'))
  }
})

onMounted(async () => {
  startBackendBoot()

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

const menus: MenuDef[] = [
  {
    key: 'file',
    label: '文件',
    items: [
      { id: 'new-chat', label: '新建会话', shortcut: 'Ctrl+N' },
      { id: 'open-folder', label: '打开文件夹...', shortcut: 'Ctrl+O' },
      { divider: true },
      { id: 'settings', label: '设置', shortcut: 'Ctrl+,' },
      { divider: true },
      { id: 'exit', label: '退出', shortcut: 'Alt+F4' },
    ],
  },
  {
    key: 'edit',
    label: '编辑',
    items: [
      { id: 'undo', label: '撤销', shortcut: 'Ctrl+Z' },
      { id: 'redo', label: '重做', shortcut: 'Ctrl+Y' },
      { divider: true },
      { id: 'cut', label: '剪切', shortcut: 'Ctrl+X' },
      { id: 'copy', label: '复制', shortcut: 'Ctrl+C' },
      { id: 'paste', label: '粘贴', shortcut: 'Ctrl+V' },
      { divider: true },
      { id: 'select-all', label: '全选', shortcut: 'Ctrl+A' },
    ],
  },
  {
    key: 'view',
    label: '查看',
    items: [
      { id: 'reload', label: '重新加载', shortcut: 'Ctrl+R' },
      { id: 'new-window', label: '新窗口', shortcut: 'Ctrl+Shift+N' },
      { id: 'dev-tools', label: '开发者工具', shortcut: 'F12' },
      { divider: true },
      { id: 'open-sessions-dir', label: '查看会话日志' },
      { id: 'open-skills-dir', label: '查看技能列表' },
      { id: 'open-mcps-dir', label: '查看 MCP 工具列表' },
    ],
  },
  {
    key: 'window',
    label: '窗口',
    items: [
      { id: 'minimize', label: '最小化' },
      { id: 'maximize', label: '最大化' },
      { id: 'close', label: '关闭窗口' },
    ],
  },
  {
    key: 'help',
    label: '帮助',
    items: [
      { id: 'version', label: '查看版本' },
      { id: 'open-backend-log', label: '打开运行日志' },
    ],
  },
]

async function openInExplorer(workDir: string, path?: string, selectFile = false) {
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/open-in-editor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        work_dir: workDir,
        path,
        editor: selectFile ? 'explorer-file' : 'explorer',
      }),
    })
    const data = await res.json()
    if (data.error) {
      console.error('[Menu] openInExplorer failed:', data.error)
    }
  } catch (e) {
    console.error('[Menu] openInExplorer error:', e)
  }
}

function editCommand(cmd: string) {
  try {
    document.execCommand(cmd)
  } catch {
    // 按钮样式保留，部分浏览器可能不支持
  }
}

function onMenuSelect(menuKey: string, item: { id?: string; divider?: boolean }) {
  if (item.divider || !item.id) return

  const id = item.id

  if (menuKey === 'file') {
    switch (id) {
      case 'new-chat':
        window.dispatchEvent(new CustomEvent('aries:new-chat'))
        break
      case 'open-folder':
        window.dispatchEvent(new CustomEvent('aries:select-work-dir'))
        break
      case 'exit':
        window.electronAPI?.quitApp?.()
        break
      case 'settings':
        window.dispatchEvent(new CustomEvent('aries:open-settings'))
        break
    }
    return
  }

  if (menuKey === 'edit') {
    switch (id) {
      case 'undo':
        editCommand('undo')
        break
      case 'redo':
        editCommand('redo')
        break
      case 'cut':
        editCommand('cut')
        break
      case 'copy':
        editCommand('copy')
        break
      case 'paste':
        editCommand('paste')
        break
      case 'select-all':
        editCommand('selectAll')
        break
    }
    return
  }

  if (menuKey === 'view') {
    switch (id) {
      case 'reload':
        location.reload()
        break
      case 'new-window':
        window.electronAPI?.createNewWindow?.()
        break
      case 'dev-tools':
        window.electronAPI?.toggleDevTools?.()
        break
      case 'open-sessions-dir': {
        const home = window.electronAPI?.homePath || ''
        void openInExplorer(`${home}\\.Aries`, 'session')
        break
      }
      case 'open-skills-dir': {
        const home = window.electronAPI?.homePath || ''
        void openInExplorer(`${home}\\.Aries`, 'skills')
        break
      }
      case 'open-mcps-dir': {
        const home = window.electronAPI?.homePath || ''
        void openInExplorer(`${home}\\.Aries`, 'mcps')
        break
      }
    }
    return
  }

  if (menuKey === 'window') {
    switch (id) {
      case 'minimize':
        window.electronAPI?.windowMinimize?.()
        break
      case 'maximize':
        window.electronAPI?.windowMaximize?.()
        break
      case 'close':
        window.electronAPI?.windowClose?.()
        break
    }
    return
  }

  if (menuKey === 'help') {
    switch (id) {
      case 'version':
        window.dispatchEvent(new CustomEvent('aries:open-settings', { detail: { tab: 'updates' } }))
        break
      case 'open-backend-log': {
        const home = window.electronAPI?.homePath || ''
        void openInExplorer(`${home}\\.Aries`, 'logs/backend.log', true)
        break
      }
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
  /* 侧边栏 / 标题栏：极浅蓝玻璃 */
  --glass-surface: rgba(205, 222, 223, 0);
  --glass-surface-soft: rgba(192, 231, 198, 0.72);
  --glass-border: rgba(248, 248, 248, 0.95);
  --glass-highlight: rgba(255, 255, 255, 0);
  --glass-blur: blur(24px) saturate(1.12);
  --glass-blur-light: blur(12px) saturate(1.08);
  --glass-shadow:
    inset 0 1px 0 var(--glass-highlight),
    4px 0 16px rgba(80, 120, 180, 0.03);
  --glass-shadow-top:
    inset 0 1px 0 var(--glass-highlight),
    0 2px 12px rgba(80, 120, 180, 0.03);
  --boot-bg-color: #f8fafc;
  --boot-bg-image:
    radial-gradient(ellipse 90% 70% at 8% 10%, rgba(236, 244, 255, 0.35) 0%, transparent 55%),
    radial-gradient(ellipse 80% 60% at 92% 90%, rgba(240, 246, 255, 0.25) 0%, transparent 50%),
    linear-gradient(165deg, #fbfcfe 0%, #f8fafc 50%, #fafbfd 100%);
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

#app.is-booting {
  background-color: var(--boot-bg-color);
  background-image: var(--boot-bg-image);
}

#app.is-booting .title-bar {
  background: transparent;
  border-bottom: none;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
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
  z-index: 1100;
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
