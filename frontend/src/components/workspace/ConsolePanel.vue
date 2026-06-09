<template>
  <div class="console-panel">
    <div class="console-toolbar">
      <div class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="tab-btn"
          :class="{ active: tab.id === activeTabId }"
          @click="switchTab(tab.id)"
        >
          <span>{{ tab.title }}</span>
          <span
            v-if="tabs.length > 1"
            class="tab-close"
            title="关闭终端"
            @click.stop="closeTab(tab.id)"
          >×</span>
        </button>
        <button type="button" class="tab-add" title="新建终端" @click="() => addTerminal()">+</button>
      </div>
      <div class="console-actions">
        <button type="button" class="action-btn" title="停止 AI 命令" @click="stopAgentCommand">⏹ 停止AI</button>
        <button type="button" class="action-btn" title="清屏" @click="clearActiveScreen">清屏</button>
        <button type="button" class="action-btn" title="重置为 PowerShell" @click="resetActiveShell">重置</button>
        <span v-if="activeTab?.shellKind" class="shell-badge">{{ activeTab.shellKind }}</span>
        <span
          class="conn-dot"
          :class="{ online: activeTab?.connected }"
          :title="activeTab?.connected ? '已连接' : '未连接'"
        ></span>
      </div>
    </div>

    <div class="terminal-body">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        v-show="tab.id === activeTabId"
        :ref="(el) => setHostRef(tab.id, el as HTMLElement | null)"
        class="terminal-host"
      ></div>
    </div>

    <div v-if="!workDir" class="console-empty">请先选择工作目录</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { getTerminalWsUrl } from '@/api/terminal'
import { useWorkspaceStore } from '@/stores/workspace'
import { storeToRefs } from 'pinia'

const props = defineProps<{
  visible?: boolean
}>()

const workspace = useWorkspaceStore()
const { workDir } = storeToRefs(workspace)

interface TerminalTab {
  id: string
  sessionId: string
  title: string
  connected: boolean
  attached: boolean
  attaching: boolean
  attachSent: boolean
  connecting: boolean
  inputUnlocked: boolean
  initialized: boolean
  ptyRows: number
  ptyCols: number
  term: Terminal | null
  fitAddon: FitAddon | null
  ws: WebSocket | null
  wsGen: number
  reconnectTimer: ReturnType<typeof setTimeout> | null
  inputUnlockTimer: ReturnType<typeof setTimeout> | null
  shellKind: string
}

const tabs = ref<TerminalTab[]>([])
const activeTabId = ref('')
const hostRefs = new Map<string, HTMLElement>()
const lastInputSent = new WeakMap<TerminalTab, { data: string; at: number }>()
let tabCounter = 0
let resizeObserver: ResizeObserver | null = null
let resizeDebounce: ReturnType<typeof setTimeout> | null = null

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) || null)

const TERMINAL_THEME = {
  background: '#ffffff',
  foreground: '#0c0c0c',
  cursor: '#0c0c0c',
  cursorAccent: '#ffffff',
  selectionBackground: '#cce5ff',
  black: '#0c0c0c',
  red: '#c50f1f',
  green: '#107c10',
  yellow: '#c19c00',
  blue: '#0037da',
  magenta: '#881798',
  cyan: '#008080',
  white: '#cccccc',
  brightBlack: '#767676',
  brightRed: '#e74856',
  brightGreen: '#16c60c',
  brightYellow: '#f9f1a5',
  brightBlue: '#3b78ff',
  brightMagenta: '#b4009e',
  brightCyan: '#00b7c3',
  brightWhite: '#f2f2f2',
}

function agentSessionId(_workDir: string): string {
  // 前端无需关心后端路径规范化细节，发送 `__agent__` 占位符，
  // 后端 WebSocket 处理器会解析为该 work_dir 对应的 agent session id。
  return '__agent__'
}

function newTabId() {
  return crypto.randomUUID()
}

/** Drop xterm→shell handshake queries that make cmd.exe print ^[[?1;2c garbage. */
function shouldForwardInput(data: string): boolean {
  if (!data.includes('\u001b')) return true
  if (/^\u001b\[>[0-9;]*c/.test(data)) return false
  if (/^\u001b\[\?[0-9;]*c/.test(data)) return false
  if (/^\u001b\]/.test(data)) return false
  return true
}

/** Strip device-attribute responses before writing to xterm. */
function sanitizeTerminalOutput(data: string): string {
  return data
    .replace(/\u001b\[\?1;2c/g, '')
    .replace(/\u001b\[>0;[0-9;]*c/g, '')
    .replace(/\u001b\[\?62;[0-9;]*c/g, '')
    .replace(/\u001b\[c/g, '')
}

function writeTerminalOutput(tab: TerminalTab, data: string) {
  const cleaned = sanitizeTerminalOutput(data)
  if (cleaned) tab.term?.write(cleaned)
}

function forwardInput(tab: TerminalTab, data: string) {
  if (!data || !tab.attached || !tab.inputUnlocked || tab.ws?.readyState !== WebSocket.OPEN) return
  if (!shouldForwardInput(data)) return
  const now = Date.now()
  const prev = lastInputSent.get(tab)
  if (prev && prev.data === data && now - prev.at < 120) return
  lastInputSent.set(tab, { data, at: now })
  tab.ws.send(JSON.stringify({ type: 'input', data }))
}

function normalizePasteInput(raw: string): string {
  const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const hadTrailingNewline = /\n$/.test(normalized)
  const trimmed = normalized.replace(/\n+$/, '')
  if (normalized.includes('\n')) {
    const payload = trimmed.replace(/\n/g, '\r\n')
    // 多行脚本：剪贴板末尾有换行时整体提交执行
    return hadTrailingNewline ? `${payload}\r\n` : payload
  }
  const autoRun = hadTrailingNewline
    || /^\s*cd\s+/i.test(trimmed)
    || /^\s*\$/.test(trimmed)
    || /^\s*Get-/i.test(trimmed)
    || /^\s*foreach\b/i.test(trimmed)
  return autoRun ? `${trimmed}\r` : trimmed
}

function bindSinglePasteHandler(tab: TerminalTab, host: HTMLElement) {
  const textarea = host.querySelector('textarea')
  if (!textarea || (textarea as HTMLElement & { __mimoPasteBound?: boolean }).__mimoPasteBound) return
  ;(textarea as HTMLElement & { __mimoPasteBound?: boolean }).__mimoPasteBound = true
  textarea.addEventListener('paste', (ev: Event) => {
    const e = ev as ClipboardEvent
    e.preventDefault()
    e.stopImmediatePropagation()
    const raw = e.clipboardData?.getData('text/plain') ?? ''
    if (!raw) return
    forwardInput(tab, normalizePasteInput(raw))
  }, true)
}

function unlockTabInput(tab: TerminalTab, delayMs = 250) {
  if (tab.inputUnlockTimer) clearTimeout(tab.inputUnlockTimer)
  tab.inputUnlocked = false
  tab.inputUnlockTimer = setTimeout(() => {
    tab.inputUnlocked = true
    tab.inputUnlockTimer = null
  }, delayMs)
}

function setHostRef(id: string, el: HTMLElement | null) {
  if (el) hostRefs.set(id, el)
  else hostRefs.delete(id)
}

function getTab(id: string) {
  return tabs.value.find(t => t.id === id)
}

function fitTab(tab: TerminalTab) {
  if (!tab.term || !tab.fitAddon) return false
  const host = hostRefs.get(tab.id)
  if (!host || host.clientWidth < 20 || host.clientHeight < 20) return false
  tab.fitAddon.fit()
  return true
}

async function waitForHostReady(tab: TerminalTab, maxFrames = 30): Promise<boolean> {
  for (let i = 0; i < maxFrames; i += 1) {
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
    if (fitTab(tab)) return true
  }
  return fitTab(tab)
}

function isWsBusy(tab: TerminalTab): boolean {
  if (tab.connecting || tab.attaching) return true
  const state = tab.ws?.readyState
  return (
    state === WebSocket.CONNECTING ||
    state === WebSocket.OPEN ||
    state === WebSocket.CLOSING
  )
}

function detachWebSocketHandlers(ws: WebSocket | null) {
  if (!ws) return
  ws.onmessage = null
  ws.onopen = null
  ws.onclose = null
  ws.onerror = null
}

function sendAttach(tab: TerminalTab, reset: boolean, replay = false) {
  if (!tab.term || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) return
  if (tab.attaching || tab.attachSent) return
  if (!fitTab(tab)) return
  tab.attaching = true
  tab.attachSent = true
  tab.attached = false
  tab.inputUnlocked = false
  tab.ptyRows = tab.term.rows
  tab.ptyCols = tab.term.cols
  tab.ws.send(JSON.stringify({
    type: 'attach',
    rows: tab.term.rows,
    cols: tab.term.cols,
    reset,
    replay,
  }))
}

function scheduleAttach(tab: TerminalTab, reset: boolean, replay = false, attempt = 0) {
  if (!tab.term || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) return
  if (tab.attachSent) return
  if (!fitTab(tab)) {
    if (attempt < 30) {
      setTimeout(() => scheduleAttach(tab, reset, replay, attempt + 1), 100)
    }
    return
  }
  sendAttach(tab, reset, replay)
}

function sendResizeOnly(tab: TerminalTab) {
  if (!tab.attached || !tab.term || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) return
  if (!fitTab(tab)) return
  if (tab.term.rows === tab.ptyRows && tab.term.cols === tab.ptyCols) return
  tab.ptyRows = tab.term.rows
  tab.ptyCols = tab.term.cols
  tab.ws.send(JSON.stringify({ type: 'resize', rows: tab.term.rows, cols: tab.term.cols }))
}

function scheduleResize() {
  if (resizeDebounce) clearTimeout(resizeDebounce)
  resizeDebounce = setTimeout(() => {
    const tab = activeTab.value
    if (tab?.attached) sendResizeOnly(tab)
  }, 120)
}

function initTabTerminal(tab: TerminalTab) {
  if (tab.initialized) return
  const host = hostRefs.get(tab.id)
  if (!host || !workDir.value) return

  tab.term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    lineHeight: 1.15,
    fontFamily: "'Cascadia Mono', 'Consolas', 'Courier New', monospace",
    scrollback: 5000,
    theme: TERMINAL_THEME,
    convertEol: false,
    windowsMode: true,
    windowsPty: { backend: 'winpty' },
  })
  tab.fitAddon = new FitAddon()
  tab.term.loadAddon(tab.fitAddon)
  tab.term.open(host)
  bindSinglePasteHandler(tab, host)

  tab.term.attachCustomKeyEventHandler((ev) => {
    if (ev.type !== 'keydown') return true
    const mod = ev.ctrlKey || ev.metaKey
    if (!mod) return true
    const key = ev.key.toLowerCase()
    if (key === 'c' && tab.term?.hasSelection()) {
      copyFromTab(tab)
      return false
    }
    // 拦截 xterm 内置粘贴，改由 textarea paste 事件统一转发（只发一次）
    if (key === 'v') return false
    return true
  })

  tab.term.onData((data) => forwardInput(tab, data))

  tab.initialized = true
}

function openWebSocket(tab: TerminalTab) {
  if (!workDir.value || isWsBusy(tab)) return

  if (tab.reconnectTimer) {
    clearTimeout(tab.reconnectTimer)
    tab.reconnectTimer = null
  }

  tab.wsGen = (tab.wsGen || 0) + 1
  const wsGen = tab.wsGen
  tab.connecting = true
  tab.attached = false
  tab.attaching = false
  tab.attachSent = false
  detachWebSocketHandlers(tab.ws)
  tab.ws?.close()
  tab.ws = null
  tab.connected = false

  const ws = new WebSocket(getTerminalWsUrl(workDir.value, tab.sessionId))
  tab.ws = ws
  ws.onmessage = (ev) => {
    if (wsGen !== tab.wsGen) return
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'ready') {
        tab.attaching = false
        tab.attached = true
        tab.connecting = false
        tab.shellKind = String(msg.shell || '')
        if (tab.shellKind === 'cmd') {
          writeTerminalOutput(
            tab,
            '\r\n\x1b[33m[警告] 当前为 CMD，PowerShell 命令无法运行。请点击「重置」或新建终端。\x1b[0m\r\n',
          )
        }
        unlockTabInput(tab)
        if (tab.id === activeTabId.value) tab.term?.focus()
        return
      }
      if (msg.type === 'output' && msg.data) {
        writeTerminalOutput(tab, msg.data)
      }
    } catch {
      writeTerminalOutput(tab, ev.data)
    }
  }
  ws.onopen = () => {
    if (wsGen !== tab.wsGen) return
    tab.connected = true
    tab.connecting = false
    tab.attaching = false
    tab.attached = false
    tab.attachSent = false
    tab.term?.reset()
    tab.term?.clear()
    void (async () => {
      await nextTick()
      await waitForHostReady(tab)
      // 每次 WebSocket 连接都重建 shell，避免沿用旧的 cmd 会话
      scheduleAttach(tab, true, false)
    })()
  }
  ws.onclose = () => {
    if (wsGen !== tab.wsGen) return
    tab.connected = false
    tab.attached = false
    tab.connecting = false
    tab.attachSent = false
    if (tab.reconnectTimer) clearTimeout(tab.reconnectTimer)
    tab.reconnectTimer = setTimeout(() => {
      if (workDir.value && props.visible !== false && tabs.value.some(t => t.id === tab.id)) {
        openWebSocket(tab)
      }
    }, 3000)
  }
  ws.onerror = () => {
    if (wsGen !== tab.wsGen) return
    tab.connected = false
    tab.attached = false
    tab.connecting = false
  }
}

function connectTab(tab: TerminalTab, resetShell: boolean, replay = false) {
  if (!workDir.value || isWsBusy(tab)) return
  initTabTerminal(tab)
  if (!tab.ws || tab.ws.readyState === WebSocket.CLOSED) {
    openWebSocket(tab)
  }
}

function addTerminal(resetShell = true) {
  if (!workDir.value) return
  // 只有当还没有 AI 终端时，新建才落到 agent session；用户额外开的 tab 保持独立
  const hasAgentTab = tabs.value.some(t => t.sessionId === agentSessionId(workDir.value))
  const useAgentSession = !hasAgentTab
  tabCounter += 1
  const tab: TerminalTab = {
    id: newTabId(),
    sessionId: useAgentSession ? agentSessionId(workDir.value) : crypto.randomUUID(),
    title: useAgentSession ? 'AI 终端' : `终端 ${tabCounter}`,
    connected: false,
    attached: false,
    attaching: false,
    attachSent: false,
    connecting: false,
    inputUnlocked: false,
    initialized: false,
    ptyRows: 0,
    ptyCols: 0,
    term: null,
    fitAddon: null,
    ws: null,
    wsGen: 0,
    reconnectTimer: null,
    inputUnlockTimer: null,
    shellKind: '',
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
  void (async () => {
    await nextTick()
    initTabTerminal(tab)
    await waitForHostReady(tab)
    openWebSocket(tab)
  })()
}

function switchTab(id: string) {
  activeTabId.value = id
  const tab = getTab(id)
  if (!tab) return
  void (async () => {
    await nextTick()
    initTabTerminal(tab)
    await waitForHostReady(tab)
    if (!tab.ws || tab.ws.readyState === WebSocket.CLOSED) {
      connectTab(tab, false, true)
      return
    }
    if (tab.attached) {
      sendResizeOnly(tab)
      tab.term?.focus()
    } else {
      tab.term?.focus()
    }
  })()
}

function disposeTab(tab: TerminalTab) {
  if (tab.reconnectTimer) {
    clearTimeout(tab.reconnectTimer)
    tab.reconnectTimer = null
  }
  if (tab.inputUnlockTimer) {
    clearTimeout(tab.inputUnlockTimer)
    tab.inputUnlockTimer = null
  }
  tab.ws?.close()
  tab.ws = null
  tab.term?.dispose()
  tab.term = null
  tab.fitAddon = null
  tab.connected = false
  tab.attached = false
  tab.attaching = false
  tab.attachSent = false
  tab.connecting = false
  tab.inputUnlocked = false
  tab.initialized = false
  tab.ptyRows = 0
  tab.ptyCols = 0
  hostRefs.delete(tab.id)
}

function closeTab(id: string) {
  const idx = tabs.value.findIndex(t => t.id === id)
  if (idx < 0) return
  const tab = tabs.value[idx]
  disposeTab(tab)
  tabs.value.splice(idx, 1)
  if (activeTabId.value === id) {
    const next = tabs.value[idx] || tabs.value[idx - 1]
    if (next) switchTab(next.id)
    else addTerminal(true)
  }
}

function copyFromTab(tab: TerminalTab) {
  const text = tab.term?.getSelection()
  if (!text) return
  navigator.clipboard.writeText(text).catch(() => {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    } catch {
      // ignore
    }
  })
}

function resetActiveShell() {
  const tab = activeTab.value
  if (!tab?.term || !tab.ws || tab.ws.readyState !== WebSocket.OPEN) return
  tab.attachSent = false
  tab.attaching = false
  tab.attached = false
  tab.inputUnlocked = false
  tab.term.reset()
  tab.term.clear()
  scheduleAttach(tab, true, false)
}

function clearActiveScreen() {
  const tab = activeTab.value
  if (!tab) return
  if (tab.attached && tab.ws?.readyState === WebSocket.OPEN) {
    tab.ws.send(JSON.stringify({ type: 'input', data: 'cls\r\n' }))
  }
  tab.term?.clear()
}

function stopAgentCommand() {
  const tab = activeTab.value
  if (!tab?.attached || tab.ws?.readyState !== WebSocket.OPEN) return
  // 向 PTY 发送 Ctrl+C (0x03)，中断正在运行的命令
  tab.ws.send(JSON.stringify({ type: 'input', data: '\x03' }))
}

function disposeAllTabs() {
  for (const tab of tabs.value) disposeTab(tab)
  tabs.value = []
  activeTabId.value = ''
  tabCounter = 0
}

function ensureDefaultTab() {
  if (!workDir.value) return
  if (!tabs.value.length) addTerminal(true)
  else if (!activeTabId.value) activeTabId.value = tabs.value[0].id
}

function isAgentTab(tab: TerminalTab | null | undefined): boolean {
  if (!tab) return false
  return tab.sessionId === agentSessionId(workDir.value)
}

function ensureAgentTabActive() {
  if (!workDir.value) return
  // 已有 tab 且第一个 tab 是 agent tab，复用即可
  if (tabs.value.length && isAgentTab(tabs.value[0])) {
    activeTabId.value = tabs.value[0].id
    return
  }
  // 旧 tab（sessionId 为随机 UUID）已不匹配，丢弃重建，让 AI 命令真正可见
  disposeAllTabs()
  tabCounter = 0
  addTerminal(true)
}

function onFocusConsole() {
  ensureAgentTabActive()
  const tab = activeTab.value
  if (!tab) return
  void (async () => {
    await nextTick()
    initTabTerminal(tab)
    await waitForHostReady(tab)
    if (tab.attached) {
      sendResizeOnly(tab)
      tab.term?.focus()
    } else if (!tab.ws || tab.ws?.readyState === WebSocket.CLOSED) {
      connectTab(tab, false, true)
    } else {
      tab.term?.focus()
    }
  })()
}

function onPanelVisible() {
  if (props.visible === false || !workDir.value) return
  if (!tabs.value.length) {
    ensureAgentTabActive()
    return
  }
  const tab = activeTab.value
  if (!tab) return
  void (async () => {
    await nextTick()
    initTabTerminal(tab)
    await waitForHostReady(tab)
    if (tab.attached) {
      sendResizeOnly(tab)
      tab.term?.focus()
    } else if (!tab.ws || tab.ws.readyState === WebSocket.CLOSED) {
      connectTab(tab, false, true)
    } else {
      tab.term?.focus()
    }
  })()
}

onMounted(() => {
  if (props.visible !== false) ensureDefaultTab()
  resizeObserver = new ResizeObserver(() => {
    if (props.visible !== false) scheduleResize()
  })
  hostRefs.forEach(el => resizeObserver?.observe(el))
  window.addEventListener('mimo:focus-console', onFocusConsole)
})

watch(activeTabId, () => {
  nextTick(() => {
    hostRefs.forEach(el => resizeObserver?.observe(el))
    const tab = activeTab.value
    if (tab?.attached) sendResizeOnly(tab)
  })
})

onUnmounted(() => {
  window.removeEventListener('mimo:focus-console', onFocusConsole)
  resizeObserver?.disconnect()
  if (resizeDebounce) clearTimeout(resizeDebounce)
  disposeAllTabs()
})

watch(workDir, () => {
  disposeAllTabs()
  if (props.visible !== false) nextTick(() => ensureDefaultTab())
})

watch(() => props.visible, (visible) => {
  if (visible) onPanelVisible()
})
</script>

<style scoped>
.console-panel {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
}

.console-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 6px 4px 4px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.tab-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 120px;
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.tab-btn.active {
  background: #fff;
  border-color: var(--border);
  color: var(--text-primary);
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
  background: rgba(0, 0, 0, 0.08);
}

.tab-add {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.tab-add:hover {
  background: var(--accent-hover);
}

.console-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.action-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-secondary);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.action-btn:hover {
  background: var(--accent-hover);
}

.conn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c4c4c0;
}

.conn-dot.online {
  background: #22c55e;
}

.shell-badge {
  font-size: 10px;
  color: var(--text-muted);
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #fff;
  text-transform: lowercase;
}

.terminal-body {
  flex: 1;
  min-height: 0;
  position: relative;
}

.terminal-host {
  position: absolute;
  inset: 0;
  padding: 6px 8px;
  overflow: hidden;
  background: #ffffff;
}

.terminal-host :deep(.xterm) {
  height: 100%;
}

.terminal-host :deep(.xterm-viewport) {
  background-color: #ffffff !important;
}

.console-empty {
  position: absolute;
  inset: 0;
  top: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
  pointer-events: none;
  background: rgba(255, 255, 255, 0.92);
}
</style>
