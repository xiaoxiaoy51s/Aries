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
      <!-- 顶部加载进度条 -->
      <div v-show="loading" class="browser-progress">
        <div class="browser-progress-bar"></div>
      </div>
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
        @did-start-loading="onStartLoading"
        @did-stop-loading="onStopLoading"
        @did-fail-load="onFailLoad"
      ></webview>
      <!-- 中央加载提示（页面尚未渲染时显示） -->
      <div v-if="loading && !pageRendered" class="browser-loading-overlay">
        <div class="browser-spinner"></div>
        <div class="browser-loading-text">正在加载…</div>
        <div class="browser-loading-url" :title="currentUrl">{{ currentUrl }}</div>
      </div>
      <!-- 加载错误提示 -->
      <div v-if="loadError && !loading" class="browser-error-overlay">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 8v4M12 16h.01"/>
        </svg>
        <div class="browser-error-title">加载失败</div>
        <div class="browser-error-detail">{{ loadError }}</div>
        <button type="button" class="browser-error-retry" @click="reload">重试</button>
      </div>
      <div v-if="!currentUrl" class="browser-empty">
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
  /** 由父级（RightPanel）传入：要打开的 URL；变化时自动导航 */
  initialUrl?: string
}>()

const workspace = useWorkspaceStore()
const urlInput = ref('')
const currentUrl = ref('')
const webviewRef = ref<HTMLElement | null>(null)
// 加载状态
const loading = ref(false)
const pageRendered = ref(false) // dom-ready 后置 true，用于隐藏中央 loading
const loadError = ref('')

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
  // 同 URL 不重复加载，避免触发 webview 的重复 navigate 抛 ERR_FAILED
  if (url === currentUrl.value) return
  // 切换 URL 时复位渲染状态
  pageRendered.value = false
  loadError.value = ''
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
  pageRendered.value = true
}

function onStartLoading() {
  loading.value = true
  loadError.value = ''
}

function onStopLoading() {
  loading.value = false
}

function onFailLoad(e: any) {
  loading.value = false
  // 仅处理主框架失败，子资源（iframe/广告/统计脚本）失败忽略
  if (e?.isMainFrame === false) return
  const code = e?.errorCode
  // 静默以下常见非真实错误：
  //  -3  ERR_ABORTED              用户取消 / 重新导航
  //  -2  ERR_FAILED               webview 重复 navigate / 重定向中断（页面通常已加载）
  //  -27 ERR_BLOCKED_BY_RESPONSE  跨源资源被拦但主页 OK
  if (code === -3 || code === -2 || code === -27) return
  // 页面已经渲染出来了，也不再展示错误覆盖层
  if (pageRendered.value) return
  loadError.value = e?.errorDescription || `加载失败 (${code ?? '未知错误'})`
}

watch(() => props.visible, (val) => {
  if (val && !currentUrl.value) {
    const dir = workspace.workDir
    if (dir) {
      urlInput.value = 'http://localhost:3000'
    }
  }
})

// 父级传入新 URL 时自动加载
watch(() => props.initialUrl, (val) => {
  if (!val) return
  urlInput.value = val
  navigate()
}, { immediate: true })
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

/* 顶部加载进度条（无确定进度，做循环位移） */
.browser-progress {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(59, 130, 246, 0.12);
  overflow: hidden;
  z-index: 5;
}

.browser-progress-bar {
  position: absolute;
  top: 0;
  left: -40%;
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, transparent, #3b82f6, transparent);
  animation: browser-progress-slide 1.1s ease-in-out infinite;
}

@keyframes browser-progress-slide {
  0% { left: -40%; }
  100% { left: 100%; }
}

/* 中央加载浮层（首次渲染前盖住空白 webview） */
.browser-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #fff;
  z-index: 4;
}

.browser-spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid rgba(59, 130, 246, 0.15);
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: browser-spinner-rotate 0.8s linear infinite;
}

@keyframes browser-spinner-rotate {
  to { transform: rotate(360deg); }
}

.browser-loading-text {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.browser-loading-url {
  font-size: 11px;
  color: var(--text-muted, #999);
  max-width: 80%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
}

/* 加载失败提示 */
.browser-error-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: #fff;
  color: var(--text-muted, #999);
  z-index: 4;
  padding: 24px;
}

.browser-error-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #222);
}

.browser-error-detail {
  font-size: 12px;
  text-align: center;
  word-break: break-all;
  max-width: 80%;
}

.browser-error-retry {
  margin-top: 6px;
  padding: 6px 14px;
  border: 1px solid #3b82f6;
  background: transparent;
  color: #3b82f6;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.browser-error-retry:hover {
  background: #3b82f6;
  color: #fff;
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
