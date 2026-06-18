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
        <button type="button" class="tab-add" title="新建终端" @click="addTerminal()">+</button>
      </div>
      <div class="console-actions">
        <button type="button" class="action-btn" title="清屏" @click="clearScreen">清屏</button>
        <button type="button" class="action-btn" title="重置终端" @click="resetShell">重置</button>
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

    <!-- 无终端时的空状态 -->
    <div v-if="tabs.length === 0" class="console-empty-state">
      <div class="empty-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <polyline points="4 17 10 11 4 5"></polyline>
          <line x1="12" y1="19" x2="20" y2="19"></line>
        </svg>
      </div>
      <p class="empty-title">AI 命令终端</p>
      <p class="empty-desc">AI 执行 CLI 命令时，点击消息中的<strong>「查看终端」</strong>按钮即可在此实时查看命令输出</p>
      <button type="button" class="empty-connect-btn" @click="addTerminal()">手动连接终端</button>
    </div>

    <div v-if="!workDir" class="console-empty">请先选择工作目录</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal, type ILink } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { closeTerminalSession, getTerminalWsUrl } from '@/api/terminal'
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
  term: Terminal | null
  fitAddon: FitAddon | null
  ws: WebSocket | null
  wsGen: number
  initialized: boolean
}

const tabs = ref<TerminalTab[]>([])
const activeTabId = ref('')
const hostRefs = new Map<string, HTMLElement>()
let tabCounter = 0
let resizeObserver: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null
const URL_RE = /https?:\/\/[^\s\]\)>'\"]+/g

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) || null)

function newTabId() {
  return crypto.randomUUID()
}

function setHostRef(id: string, el: HTMLElement | null) {
  if (el) hostRefs.set(id, el)
  else hostRefs.delete(id)
}

function openTerminalUrl(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

function fitTab(tab: TerminalTab) {
  if (!tab.term || !tab.fitAddon) return false
  const host = hostRefs.get(tab.id)
  if (!host || host.clientWidth < 20 || host.clientHeight < 20) return false
  try {
    tab.fitAddon.fit()
    return true
  } catch {
    return false
  }
}

function createTerminal(tab: TerminalTab) {
  if (tab.initialized) return
  const host = hostRefs.get(tab.id)
  if (!host) return

  tab.term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    lineHeight: 1.15,
    fontFamily: "'Cascadia Mono', 'Consolas', 'Courier New', monospace",
    scrollback: 5000,
    theme: {
      background: '#ffffff',
      foreground: '#000000',
      cursor: '#000000',
      cursorAccent: '#ffffff',
      selectionBackground: '#cce5ff',
      black: '#000000',
      red: '#c50f1f',
      green: '#0a5c0a',
      yellow: '#7a5f00',
      blue: '#0037da',
      magenta: '#6c1a6c',
      cyan: '#005f5f',
      white: '#666666',
      brightBlack: '#333333',
      brightRed: '#a80c1a',
      brightGreen: '#0d7a0d',
      brightYellow: '#8a6e00',
      brightBlue: '#0028a8',
      brightMagenta: '#7a1a7a',
      brightCyan: '#006666',
      brightWhite: '#999999',
    },
  })
  tab.fitAddon = new FitAddon()
  tab.term.loadAddon(tab.fitAddon)
  tab.term.open(host)
  tab.term.registerLinkProvider({
    provideLinks: (lineNumber, callback) => {
      const line = tab.term?.buffer.active.getLine(lineNumber - 1)
      const text = line?.translateToString(true) || ''
      const links: ILink[] = []
      for (const match of text.matchAll(URL_RE)) {
        const url = match[0]
        const start = (match.index || 0) + 1
        const end = start + url.length
        links.push({
          text: url,
          range: {
            start: { x: start, y: lineNumber },
            end: { x: end, y: lineNumber },
          },
          decorations: { pointerCursor: true, underline: true },
          activate: () => openTerminalUrl(url),
        })
      }
      callback(links.length ? links : undefined)
    },
  })

  tab.term.attachCustomKeyEventHandler((event) => {
    if (event.type === 'keydown' && event.ctrlKey && event.key.toLowerCase() === 'c') {
      const selection = tab.term?.getSelection()
      if (selection) {
        void navigator.clipboard?.writeText(selection).catch(() => {})
        tab.term?.clearSelection()
        return false
      }
    }
    return true
  })

  tab.term.onData((data) => {
    if (tab.ws?.readyState === WebSocket.OPEN && tab.attached) {
      tab.ws.send(JSON.stringify({ type: 'input', data }))
    }
  })

  tab.initialized = true
}

function connectTab(tab: TerminalTab, reset = true) {
  if (!workDir.value) return
  createTerminal(tab)

  // 关闭旧连接
  if (tab.ws) {
    tab.ws.onmessage = null
    tab.ws.onopen = null
    tab.ws.onclose = null
    tab.ws.onerror = null
    tab.ws.close()
    tab.ws = null
  }

  tab.wsGen++
  const gen = tab.wsGen
  tab.connected = false
  tab.attached = false

  const ws = new WebSocket(getTerminalWsUrl(workDir.value, tab.sessionId))
  tab.ws = ws

  ws.onopen = () => {
    if (gen !== tab.wsGen) return
    // 等待 xterm 渲染完成后再 attach
    nextTick().then(() => {
      fitTab(tab)
      ws.send(JSON.stringify({
        type: 'attach',
        rows: tab.term?.rows || 24,
        cols: tab.term?.cols || 80,
        reset,
        replay: !reset,
      }))
    })
  }

  ws.onmessage = (ev) => {
    if (gen !== tab.wsGen) return
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'ready') {
        tab.attached = true
        tab.connected = true
        tab.term?.focus()
        return
      }
      if (msg.type === 'output' && msg.data) {
        tab.term?.write(msg.data)
        return
      }
    } catch {
      // plain text
      tab.term?.write(ev.data)
    }
  }

  ws.onclose = () => {
    if (gen !== tab.wsGen) return
    const wasAttached = tab.attached
    tab.connected = false
    tab.attached = false
    // 如果从未成功 attach，说明终端 session 不存在
    if (!wasAttached) {
      tab.term?.write('\r\n\x1b[31m终端已关闭或不存在\x1b[0m\r\n')
      return
    }
    // 自动重连
    setTimeout(() => {
      if (workDir.value && tabs.value.some(t => t.id === tab.id)) {
        connectTab(tab, false)
      }
    }, 3000)
  }

  ws.onerror = () => {
    if (gen !== tab.wsGen) return
    tab.connected = false
    tab.attached = false
  }
}

function addTerminal(reset = true) {
  if (!workDir.value) return
  tabCounter++
  const tab: TerminalTab = {
    id: newTabId(),
    sessionId: crypto.randomUUID(),
    title: `终端 ${tabCounter}`,
    connected: false,
    attached: false,
    term: null,
    fitAddon: null,
    ws: null,
    wsGen: 0,
    initialized: false,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
  nextTick(() => {
    connectTab(tab, reset)
  })
}

function switchTab(id: string) {
  activeTabId.value = id
  const tab = tabs.value.find(t => t.id === id)
  if (!tab) return
  nextTick(() => {
    fitTab(tab)
    if (tab.ws?.readyState !== WebSocket.OPEN || !tab.attached) {
      connectTab(tab, false)
    }
    tab.term?.focus()
  })
}

function closeTab(id: string) {
  const idx = tabs.value.findIndex(t => t.id === id)
  if (idx < 0) return
  const tab = tabs.value[idx]
  tab.ws?.close()
  void closeTerminalSession(tab.sessionId).catch((error) => {
    console.error('Close terminal session failed', error)
  })
  tab.term?.dispose()
  hostRefs.delete(tab.id)
  tabs.value.splice(idx, 1)
  if (activeTabId.value === id) {
    const next = tabs.value[idx] || tabs.value[idx - 1]
    if (next) switchTab(next.id)
    else activeTabId.value = ''
  }
}

function clearScreen() {
  const tab = activeTab.value
  if (!tab) return
  tab.term?.clear()
  if (tab.attached && tab.ws?.readyState === WebSocket.OPEN) {
    tab.ws.send(JSON.stringify({ type: 'input', data: 'cls\r\n' }))
  }
}

function resetShell() {
  const tab = activeTab.value
  if (!tab) return
  connectTab(tab, true)
}

function disposeAllTabs() {
  for (const tab of tabs.value) {
    tab.ws?.close()
    tab.term?.dispose()
  }
  tabs.value = []
  activeTabId.value = ''
  hostRefs.clear()
  tabCounter = 0
}

function onFocusConsoleFromTool() {
  if (!workDir.value) return
  const tab = activeTab.value
  if (tab && tab.ws?.readyState !== WebSocket.OPEN) {
    connectTab(tab, false)
  }
}

function onOpenTerminal(e: Event) {
  const detail = (e as CustomEvent).detail as { sessionId: string; command?: string } | undefined
  if (!detail?.sessionId || !workDir.value) return

  // 检查是否已存在同 session 的 tab
  const existing = tabs.value.find(t => t.sessionId === detail.sessionId)
  if (existing) {
    switchTab(existing.id)
    return
  }

  // 创建新 tab 并连接到指定 session
  tabCounter++
  const tab: TerminalTab = {
    id: newTabId(),
    sessionId: detail.sessionId,
    title: detail.command ? `AI: ${detail.command.slice(0, 15)}` : `终端 ${tabCounter}`,
    connected: false,
    attached: false,
    term: null,
    fitAddon: null,
    ws: null,
    wsGen: 0,
    initialized: false,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id
  nextTick(() => {
    connectTab(tab, false)
  })
}

// 只在用户点击「查看终端」或手动连接时才建立终端
watch(() => props.visible, (visible) => {
  if (visible && workDir.value && tabs.value.length > 0) {
    const tab = activeTab.value
    if (tab) {
      nextTick(() => fitTab(tab))
      if (tab.ws?.readyState !== WebSocket.OPEN) {
        connectTab(tab, false)
      }
    }
  }
})

// 监听工作目录变化：不自动创建终端，只清理旧连接
watch(workDir, () => {
  disposeAllTabs()
})

onMounted(() => {
  // 不再自动创建终端
  // 监听「查看终端」事件，按需创建终端
  window.addEventListener('aries:focus-console', onFocusConsoleFromTool)
  window.addEventListener('aries:open-terminal', onOpenTerminal)

  resizeObserver = new ResizeObserver(() => {
    if (resizeTimer) clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      const tab = activeTab.value
      if (tab && tab.attached) {
        fitTab(tab)
        if (tab.ws?.readyState === WebSocket.OPEN) {
          tab.ws.send(JSON.stringify({
            type: 'resize',
            rows: tab.term?.rows || 24,
            cols: tab.term?.cols || 80,
          }))
        }
      }
    }, 150)
  })

  // 观察所有 host 元素
  hostRefs.forEach((el) => resizeObserver?.observe(el))
})

onUnmounted(() => {
  window.removeEventListener('aries:focus-console', onFocusConsoleFromTool)
  window.removeEventListener('aries:open-terminal', onOpenTerminal)
  resizeObserver?.disconnect()
  if (resizeTimer) clearTimeout(resizeTimer)
  disposeAllTabs()
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

.tab-bar::-webkit-scrollbar {
  height: 0;
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
  background: #ffffff;
  border-color: var(--border);
  color: var(--text-primary);
}

.tab-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
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

.console-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.action-btn {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.action-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.conn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e74c3c;
  flex-shrink: 0;
}

.conn-dot.online {
  background: #2ecc71;
}

.terminal-body {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.terminal-host {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  padding: 4px;
}

.console-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

.console-empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  gap: 12px;
  text-align: center;
}

.empty-icon {
  color: var(--text-muted);
  opacity: 0.5;
  margin-bottom: 4px;
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.empty-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  max-width: 280px;
  line-height: 1.5;
}

.empty-connect-btn {
  margin-top: 8px;
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.empty-connect-btn:hover {
  background: #333333;
}
</style>
