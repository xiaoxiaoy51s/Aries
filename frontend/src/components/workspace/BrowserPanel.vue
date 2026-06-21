<template>
  <div class="browser-panel">
    <!-- 顶部 tab 栏 -->
    <div class="browser-tabs">
      <div class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="tab-btn"
          :class="{ active: tab.id === activeTabId }"
          :title="tab.title || tab.currentUrl || '新标签页'"
          @click="switchTab(tab.id)"
        >
          <span class="tab-title">{{ tab.title || hostFromUrl(tab.currentUrl) || '新标签页' }}</span>
          <span
            v-if="tabs.length > 1"
            class="tab-close"
            title="关闭标签页"
            @click.stop="closeTab(tab.id)"
          >×</span>
        </button>
        <button type="button" class="tab-add" title="新建标签页" @click="addTab()">+</button>
      </div>
    </div>

    <!-- 当前 tab 的工具栏 -->
    <div v-if="activeTab" class="browser-toolbar">
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
        v-model="activeTab.urlInput"
        type="text"
        class="browser-url-input"
        placeholder="输入 URL 或搜索..."
        @keydown.enter="navigate()"
      />
      <button type="button" class="browser-btn" title="访问" @click="navigate()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      </button>
      <button
        type="button"
        class="browser-btn"
        :class="{ active: activeTab.inspecting }"
        :title="activeTab.inspecting ? '退出元素检查' : '检查元素（查看标签/尺寸/颜色/字体）'"
        @click="toggleInspect"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 3l7.07 17 2.51-7.42L20 10.07 3 3z"/>
          <path d="M13 13l6 6"/>
        </svg>
      </button>
    </div>

    <div class="browser-content">
      <!-- 顶部加载进度条（仅当前 tab） -->
      <div v-show="activeTab?.loading" class="browser-progress">
        <div class="browser-progress-bar"></div>
      </div>

      <!-- 每个 tab 一个 webview，通过 v-show 切换 -->
      <template v-for="tab in tabs" :key="tab.id">
        <webview
          v-if="tab.currentUrl"
          v-show="tab.id === activeTabId"
          :src="tab.currentUrl"
          :ref="(el) => setWebviewRef(tab.id, el as HTMLElement | null)"
          class="browser-webview"
          allowpopups
          webpreferences="contextIsolation=no; nodeIntegration=no"
          @did-navigate="(e) => onNavigate(tab, e)"
          @did-navigate-in-page="(e) => onNavigateInPage(tab, e)"
          @dom-ready="() => onDomReady(tab)"
          @did-start-loading="() => onStartLoading(tab)"
          @did-stop-loading="() => onStopLoading(tab)"
          @did-fail-load="(e) => onFailLoad(tab, e)"
          @page-title-updated="(e) => onTitleUpdated(tab, e)"
        ></webview>
      </template>

      <!-- 中央加载提示 -->
      <div v-if="activeTab && activeTab.loading && !activeTab.pageRendered" class="browser-loading-overlay">
        <div class="browser-spinner"></div>
        <div class="browser-loading-text">正在加载…</div>
        <div class="browser-loading-url" :title="activeTab.currentUrl">{{ activeTab.currentUrl }}</div>
      </div>

      <!-- 加载错误提示 -->
      <div v-if="activeTab && activeTab.loadError && !activeTab.loading" class="browser-error-overlay">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 8v4M12 16h.01"/>
        </svg>
        <div class="browser-error-title">加载失败</div>
        <div class="browser-error-detail">{{ activeTab.loadError }}</div>
        <button type="button" class="browser-error-retry" @click="reload">重试</button>
      </div>

      <!-- 空状态：未输入 URL -->
      <div v-if="activeTab && !activeTab.currentUrl" class="browser-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="browser-empty-icon">
          <circle cx="12" cy="12" r="10"/>
          <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </svg>
        <div class="browser-empty-hint">输入 URL 开始浏览</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  visible?: boolean
  /** 由父级（RightPanel）传入：要打开的 URL；变化时自动新建 tab 加载 */
  initialUrl?: string
}>()

const workspace = useWorkspaceStore()

interface BrowserTab {
  id: string
  title: string
  urlInput: string
  currentUrl: string
  loading: boolean
  pageRendered: boolean
  loadError: string
  inspecting: boolean
}

const tabs = ref<BrowserTab[]>([])
const activeTabId = ref('')
const webviewRefs = new Map<string, HTMLElement>()

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) || null)

function newTabId() {
  return crypto.randomUUID()
}

function hostFromUrl(url: string): string {
  if (!url) return ''
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function setWebviewRef(id: string, el: HTMLElement | null) {
  if (el) webviewRefs.set(id, el)
  else webviewRefs.delete(id)
}

function createTab(opts: { url?: string } = {}): BrowserTab {
  const tab: BrowserTab = {
    id: newTabId(),
    title: '',
    urlInput: opts.url || '',
    currentUrl: '',
    loading: false,
    pageRendered: false,
    loadError: '',
    inspecting: false,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
  if (opts.url) {
    // 在 push 后进行导航，确保 watch/render 完成
    queueMicrotask(() => navigate(tab, opts.url!))
  }
  return tab
}

function addTab(url?: string) {
  createTab({ url })
}

function switchTab(id: string) {
  activeTabId.value = id
}

function closeTab(id: string) {
  const idx = tabs.value.findIndex(t => t.id === id)
  if (idx < 0) return
  tabs.value.splice(idx, 1)
  webviewRefs.delete(id)
  if (activeTabId.value === id) {
    const next = tabs.value[idx] || tabs.value[idx - 1]
    activeTabId.value = next ? next.id : ''
  }
  if (tabs.value.length === 0) {
    // 至少保留一个空 tab
    createTab()
  }
}

function normalizeUrl(raw: string): string {
  let url = raw.trim()
  if (!url) return ''
  if (!/^https?:\/\//.test(url)) {
    if (/^[\d.]+(:\d+)?$/.test(url) || /^localhost(:\d+)?$/.test(url)) {
      url = 'http://' + url
    } else {
      url = 'https://' + url
    }
  }
  return url
}

function navigate(tab: BrowserTab | null = activeTab.value, override?: string) {
  if (!tab) return
  const raw = override !== undefined ? override : tab.urlInput
  const url = normalizeUrl(raw)
  if (!url) return
  tab.urlInput = url
  if (url === tab.currentUrl) return
  tab.pageRendered = false
  tab.loadError = ''
  tab.currentUrl = url
}

function goBack() {
  const tab = activeTab.value
  if (!tab) return
  const webview = webviewRefs.get(tab.id) as any
  if (webview?.goBack) webview.goBack()
}

function goForward() {
  const tab = activeTab.value
  if (!tab) return
  const webview = webviewRefs.get(tab.id) as any
  if (webview?.goForward) webview.goForward()
}

function reload() {
  const tab = activeTab.value
  if (!tab) return
  const webview = webviewRefs.get(tab.id) as any
  if (webview?.reload) webview.reload()
}

/* ---------------- 元素检查（inspect） ---------------- */
const INSPECT_SCRIPT = `
(function(){
  if (window.__mimoInspectorInstalled) return;
  window.__mimoInspectorInstalled = true;

  const hl = document.createElement('div');
  Object.assign(hl.style, {
    position: 'fixed', pointerEvents: 'none', zIndex: 2147483646,
    border: '1px solid #3b82f6',
    background: 'rgba(59,130,246,0.18)',
    transition: 'all 60ms linear',
    display: 'none', boxSizing: 'border-box'
  });

  const tip = document.createElement('div');
  Object.assign(tip.style, {
    position: 'fixed', pointerEvents: 'none', zIndex: 2147483647,
    background: 'rgba(20,20,20,0.92)', color: '#fff',
    font: '12px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    padding: '8px 10px', borderRadius: '6px',
    boxShadow: '0 6px 18px rgba(0,0,0,0.25)',
    maxWidth: '320px', display: 'none', whiteSpace: 'nowrap'
  });

  document.documentElement.appendChild(hl);
  document.documentElement.appendChild(tip);

  function rgbToHex(rgb){
    if(!rgb) return '';
    const m = rgb.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
    if(!m) return rgb;
    const r=+m[1], g=+m[2], b=+m[3], a=m[4]!==undefined?+m[4]:1;
    const hex = '#' + [r,g,b].map(v=>v.toString(16).padStart(2,'0').toUpperCase()).join('');
    return a < 1 ? hex + ' / ' + a : hex;
  }

  function fmt(label, value){
    return '<div style="display:flex;justify-content:space-between;gap:18px;">'
      + '<span style="opacity:.7">'+label+'</span>'
      + '<span style="font-family:Consolas,Menlo,monospace">'+value+'</span></div>';
  }

  function update(el, ev){
    if(!el || el===hl || el===tip) { hl.style.display='none'; tip.style.display='none'; return; }
    const r = el.getBoundingClientRect();
    hl.style.display='block';
    hl.style.left = r.left+'px';
    hl.style.top = r.top+'px';
    hl.style.width = r.width+'px';
    hl.style.height = r.height+'px';

    const cs = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const cls = el.className && typeof el.className==='string'
      ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.')
      : '';
    const id = el.id ? '#'+el.id : '';
    const sel = tag + id + cls;

    tip.innerHTML =
      '<div style="font-weight:600;margin-bottom:6px;color:#7dd3fc">'+sel+'</div>'
      + fmt('尺寸', Math.round(r.width)+' × '+Math.round(r.height))
      + fmt('颜色', rgbToHex(cs.color))
      + fmt('背景', rgbToHex(cs.backgroundColor))
      + fmt('字体', cs.fontSize+' '+(cs.fontFamily||'').split(',')[0].replace(/['"]/g,''));

    tip.style.display='block';
    const pad = 8;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    const vw = window.innerWidth, vh = window.innerHeight;
    let x = (ev ? ev.clientX : r.left) + 12;
    let y = (ev ? ev.clientY : r.bottom) + 12;
    if (x + tw + pad > vw) x = vw - tw - pad;
    if (y + th + pad > vh) y = (ev ? ev.clientY : r.top) - th - 12;
    if (y < pad) y = pad;
    tip.style.left = x+'px';
    tip.style.top = y+'px';
  }

  function onMove(e){ update(e.target, e); }
  function onClick(e){ e.preventDefault(); e.stopPropagation(); update(e.target, e); return false; }
  function onLeave(){ hl.style.display='none'; tip.style.display='none'; }

  window.__mimoInspectCleanup = function(){
    document.removeEventListener('mousemove', onMove, true);
    document.removeEventListener('mouseover', onMove, true);
    document.removeEventListener('mouseout', onLeave, true);
    document.removeEventListener('click', onClick, true);
    hl.remove(); tip.remove();
    window.__mimoInspectorInstalled = false;
    delete window.__mimoInspectCleanup;
  };

  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('mouseover', onMove, true);
  document.addEventListener('mouseout', onLeave, true);
  document.addEventListener('click', onClick, true);
})();
`

const UNINSPECT_SCRIPT = `
(function(){
  if (typeof window.__mimoInspectCleanup === 'function') window.__mimoInspectCleanup();
})();
`

async function toggleInspect() {
  const tab = activeTab.value
  if (!tab) return
  const webview = webviewRefs.get(tab.id) as any
  if (!webview?.executeJavaScript) return
  tab.inspecting = !tab.inspecting
  try {
    await webview.executeJavaScript(tab.inspecting ? INSPECT_SCRIPT : UNINSPECT_SCRIPT, true)
  } catch (err) {
    console.warn('inspect 注入失败:', err)
    tab.inspecting = false
  }
}

/* ---------------- webview 事件 ---------------- */
function onNavigate(tab: BrowserTab, e: any) {
  if (e?.url) tab.urlInput = e.url
  else if (e?.target?.src) tab.urlInput = e.target.src
}

function onNavigateInPage(tab: BrowserTab, e: any) {
  if (e?.url) tab.urlInput = e.url
  else if (e?.target?.src) tab.urlInput = e.target.src
}

function onDomReady(tab: BrowserTab) {
  tab.pageRendered = true
  if (tab.inspecting) {
    const webview = webviewRefs.get(tab.id) as any
    webview?.executeJavaScript?.(INSPECT_SCRIPT, true).catch(() => {})
  }
}

function onStartLoading(tab: BrowserTab) {
  tab.loading = true
  tab.loadError = ''
}

function onStopLoading(tab: BrowserTab) {
  tab.loading = false
}

function onFailLoad(tab: BrowserTab, e: any) {
  tab.loading = false
  if (e?.isMainFrame === false) return
  const code = e?.errorCode
  if (code === -3 || code === -2 || code === -27) return
  if (tab.pageRendered) return
  tab.loadError = e?.errorDescription || `加载失败 (${code ?? '未知错误'})`
}

function onTitleUpdated(tab: BrowserTab, e: any) {
  if (e?.title) tab.title = e.title
}

/* ---------------- 外部 props 联动 ---------------- */
watch(() => props.visible, (val) => {
  if (val && tabs.value.length === 0) {
    const dir = workspace.workDir
    const url = dir ? 'http://localhost:3000' : ''
    createTab(url ? { url } : {})
  }
})

// 父级传入新 URL 时：若当前活动 tab 是空白则复用，否则新开 tab
watch(() => props.initialUrl, (val) => {
  if (!val) return
  const tab = activeTab.value
  if (tab && !tab.currentUrl) {
    navigate(tab, val)
  } else {
    addTab(val)
  }
}, { immediate: true })

// 始终保证至少有一个 tab（首次挂载时若没有任何 tab，建一个空白 tab）
if (tabs.value.length === 0 && !props.initialUrl) {
  createTab()
}
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

/* tab 栏 */
.browser-tabs {
  display: flex;
  align-items: center;
  padding: 4px 6px 0 6px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.tab-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.tab-bar::-webkit-scrollbar {
  height: 0;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 160px;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.tab-btn.active {
  background: #ffffff;
  border-color: var(--border);
  color: var(--text-primary);
}

.tab-btn:hover:not(.active) {
  background: var(--accent-hover);
  color: var(--text);
}

.tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
}

.tab-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1;
  opacity: 0.6;
}

.tab-close:hover {
  opacity: 1;
  background: var(--accent-hover);
}

.tab-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
}

.tab-add:hover {
  background: var(--accent-hover);
  color: var(--text);
}

/* 工具栏 */
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

.browser-btn.active {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
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

.browser-empty-hint {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
