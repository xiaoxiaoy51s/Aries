<template>
  <div id="app" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <button
      type="button"
      class="sidebar-toggle"
      :title="sidebarOpen ? '收起侧边栏' : '展开侧边栏'"
      :aria-label="sidebarOpen ? '收起侧边栏' : '展开侧边栏'"
      @click="toggleSidebar"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path v-if="sidebarOpen" d="M9 3v18"/>
        <path v-else d="M9 3v18M3 9h6"/>
      </svg>
    </button>
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'
import { useModelStore } from '@/stores/model'
import { useWorkspaceStore } from '@/stores/workspace'
import { initPaths } from '@/utils/paths'

const { sidebarOpen, toggleSidebar } = useSidebar()

const modelStore = useModelStore()
const workspaceStore = useWorkspaceStore()
const BACKEND_PORT = 30000
modelStore.setBackendPort(BACKEND_PORT)

onMounted(async () => {
  modelStore.loadModels().catch(() => {})
  await initPaths().catch(() => {})
  workspaceStore.initWorkDir().catch(() => {})
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --bg-app: #f3f3f2;
  --bg-sidebar: #f7f7f5;
  --bg-panel: #ffffff;
  --border: #e8e8e6;
  --border-strong: #d4d4d0;
  --text: #1a1a18;
  --text-secondary: #6b6b66;
  --text-muted: #9a9a94;
  --accent: #2d2d2a;
  --accent-hover: #f0f0ee;
  --accent-active: #ebebea;
  --send-bg: #1a1a18;
  --send-hover: #333330;
  --user-msg: #eef4ff;
  --assistant-msg: #f5f5f3;
  --radius: 12px;
  --radius-lg: 16px;
  --sidebar-width: 260px;
  --shadow-panel: 0 1px 3px rgba(0, 0, 0, 0.06), 0 4px 24px rgba(0, 0, 0, 0.04);
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg-app);
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
}

.sidebar-toggle {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-panel);
  transition: background 0.15s, color 0.15s, left 0.2s ease;
}

.sidebar-toggle:hover {
  background: var(--accent-hover);
  color: var(--text);
}

#app.sidebar-collapsed .sidebar-toggle {
  left: 12px;
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
