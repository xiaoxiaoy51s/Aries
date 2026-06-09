<template>
  <div id="app">
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
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
