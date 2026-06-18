<template>
  <div class="browser-panel">
    <div class="browser-toolbar">
      <button type="button" class="browser-btn" title="后退" @click="goBack">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>
      </button>
      <button type="button" class="browser-btn" title="前进" @click="goForward">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <button type="button" class="browser-btn" title="刷新" @click="reload">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/></svg>
      </button>
      <input
        v-model="urlInput"
        type="text"
        class="browser-url-input"
        placeholder="输入 URL 或搜索..."
        @keydown.enter="navigate"
      />
      <button type="button" class="browser-btn" title="访问" @click="navigate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      </button>
    </div>
    <div class="browser-content">
      <webview
        v-if="currentUrl"
        :src="currentUrl"
        ref="webviewRef"
        class="browser-webview"
        allowpopups
        webpreferences="contextIsolation=no; nodeIntegration=no"
        @did-navigate="onNavigate"
        @did-navigate-in-page="onNavigateInPage"
        @dom-ready="onDomReady"
      ></webview>
      <div v-else class="browser-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="browser-empty-icon">
          <circle cx="12" cy="12" r="10"/>
          <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </svg>
        
       
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  visible?: boolean
}>()

const workspace = useWorkspaceStore()
const urlInput = ref('')
const currentUrl = ref('')
const webviewRef = ref<HTMLElement | null>(null)

function navigate() {
  let url = urlInput.value.trim()
  if (!url) return
  if (!/^https?:\/\//.test(url)) {
    if (/^[\d.]+(:\d+)?$/.test(url) || /^localhost(:\d+)?$/.test(url)) {
      url = 'http://' + url
    } else {
      url = 'https://' + url
    }
  }
  currentUrl.value = url
}

function navigateTo(url: string) {
  urlInput.value = url
  navigate()
}

function goBack() {
  const webview = webviewRef.value as any
  if (webview?.goBack) webview.goBack()
}

function goForward() {
  const webview = webviewRef.value as any
  if (webview?.goForward) webview.goForward()
}

function reload() {
  const webview = webviewRef.value as any
  if (webview?.reload) webview.reload()
}

function onNavigate(e: any) {
  if (e?.target?.src) {
    urlInput.value = e.target.src
  }
}

function onNavigateInPage(e: any) {
  if (e?.target?.src) {
    urlInput.value = e.target.src
  }
}

function onDomReady() {
  console.log('Browser webview DOM ready')
}

watch(() => props.visible, (val) => {
  if (val && !currentUrl.value) {
    const dir = workspace.workDir
    if (dir) {
      urlInput.value = 'http://localhost:3000'
    }
  }
})
</script>

<style scoped>
.browser-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #fff;
  height: 100%;
}

.browser-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.browser-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
  flex-shrink: 0;
}

.browser-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.browser-url-input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  outline: none;
  background: #fff;
}

.browser-url-input:focus {
  border-color: var(--accent, #0078d4);
}

.browser-content {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.browser-webview {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: none;
}

.browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-muted);
}

.browser-empty-icon {
  opacity: 0.3;
}

.browser-shortcuts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.shortcut-btn {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.12s;
}

.shortcut-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}
</style>
