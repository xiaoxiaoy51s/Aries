/** 多会话 WebSocket 连接池 + 切换 session 时的 UI 状态快照 */
import { isSessionWorking, workingSessionIds, MAX_CONCURRENT_WORKING_SESSIONS } from './sessionWorkStore'

export interface SessionChatSnapshot {
  messages: unknown[]
  isSending: boolean
  hasActiveChat: boolean
  activeAssistantMessageId: number | null
  activeAssistantIdx: number | null
  sessionSubagents: unknown[]
  platformStreaming: boolean
}

type WsPayloadHandler = (data: Record<string, unknown>) => void

interface PoolEntry {
  ws: WebSocket
  connectPromise: Promise<void> | null
  /** 心跳定时器 */
  pingTimer: ReturnType<typeof setInterval> | null
  /** 无消息超时定时器：超时认为连接已死，触发重连 */
  watchdogTimer: ReturnType<typeof setTimeout> | null
  /** 最近一次收到任意消息（含 pong）的时间戳 */
  lastMsgAt: number
  /** 重连所需的 wsBase，供自动重连使用 */
  wsBase: string
  /** 防止重连风暴 */
  reconnecting: boolean
}

/** 心跳间隔（ms） */
const PING_INTERVAL = 20000
/** 无消息超时（ms）：超过此时间未收到任何消息则判定断连 */
const WATCHDOG_TIMEOUT = 45000

const snapshots = new Map<string, SessionChatSnapshot>()
const pool = new Map<string, PoolEntry>()
const handlers = new Map<string, WsPayloadHandler>()
/** 重连成功后的回调（chatPage 注册，用于拉取断连期间漏掉的消息） */
let onReconnectCallback: ((sessionId: string) => void) | null = null

/** 注册重连成功回调 */
export function setOnReconnect(cb: ((sessionId: string) => void) | null): void {
  onReconnectCallback = cb
}

function cloneSnapshot(s: SessionChatSnapshot): SessionChatSnapshot {
  return JSON.parse(JSON.stringify(s)) as SessionChatSnapshot
}

export function saveSessionSnapshot(sessionId: string, snapshot: SessionChatSnapshot): void {
  if (!sessionId) return
  snapshots.set(sessionId, cloneSnapshot(snapshot))
}

export function loadSessionSnapshot(sessionId: string): SessionChatSnapshot | undefined {
  const s = snapshots.get(sessionId)
  return s ? cloneSnapshot(s) : undefined
}

export function hasSessionSnapshot(sessionId: string): boolean {
  return snapshots.has(sessionId)
}

export function clearSessionSnapshot(sessionId: string): void {
  snapshots.delete(sessionId)
}

export function setSessionWsHandler(sessionId: string, handler: WsPayloadHandler | null): void {
  if (handler) handlers.set(sessionId, handler)
  else handlers.delete(sessionId)
}

function dispatchWsMessage(sessionId: string, raw: string): void {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    handlers.get(sessionId)?.(data)
  } catch {
    // ignore malformed
  }
}

function closePoolEntry(sessionId: string): void {
  const entry = pool.get(sessionId)
  if (!entry) return
  if (entry.pingTimer) clearInterval(entry.pingTimer)
  if (entry.watchdogTimer) clearTimeout(entry.watchdogTimer)
  entry.ws.onmessage = null
  entry.ws.onclose = null
  entry.ws.onerror = null
  if (entry.ws.readyState === WebSocket.OPEN || entry.ws.readyState === WebSocket.CONNECTING) {
    entry.ws.close()
  }
  pool.delete(sessionId)
}

/** 保留正在工作的 session + 当前查看的 session 的 WS，其余关闭 */
export function pruneSessionWsKeep(keepSessionIds: Iterable<string>): void {
  const keep = new Set(keepSessionIds)
  for (const sid of [...pool.keys()]) {
    if (!keep.has(sid)) closePoolEntry(sid)
  }
}

export function closeSessionWs(sessionId: string): void {
  closePoolEntry(sessionId)
}

export function closeAllSessionWs(): void {
  for (const sid of [...pool.keys()]) closePoolEntry(sid)
}

export function ensureSessionWs(sessionId: string, wsBase: string): Promise<void> {
  if (!sessionId) return Promise.resolve()

  const existing = pool.get(sessionId)
  if (existing?.ws.readyState === WebSocket.OPEN) return Promise.resolve()
  if (existing?.connectPromise) return existing.connectPromise

  // 限制连接数：优先保留 working + 当前 session
  if (pool.size >= MAX_CONCURRENT_WORKING_SESSIONS + 1) {
    for (const sid of pool.keys()) {
      if (!isSessionWorking(sid) && sid !== sessionId) {
        closePoolEntry(sid)
        break
      }
    }
  }

  const wsUrl = `${wsBase}/ws/chat?session_id=${encodeURIComponent(sessionId)}`
  const ws = new WebSocket(wsUrl)
  const entry: PoolEntry = {
    ws,
    connectPromise: null,
    pingTimer: null,
    watchdogTimer: null,
    lastMsgAt: Date.now(),
    wsBase,
    reconnecting: false,
  }
  pool.set(sessionId, entry)

  /** 重置 watchdog：收到任意消息后延长超时 */
  const resetWatchdog = () => {
    entry.lastMsgAt = Date.now()
    if (entry.watchdogTimer) clearTimeout(entry.watchdogTimer)
    entry.watchdogTimer = setTimeout(() => {
      // 长时间未收到任何消息（含 pong），判定连接已死
      console.warn(`[ChatWS] ${sessionId} 心跳超时，主动断开并重连`)
      if (entry.ws.readyState === WebSocket.OPEN) entry.ws.close()
    }, WATCHDOG_TIMEOUT)
  }

  entry.connectPromise = new Promise<void>((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      resolve()
    }
    const timer = setTimeout(finish, 5000)

    ws.onopen = () => {
      clearTimeout(timer)
      // 启动心跳
      entry.pingTimer = setInterval(() => {
        if (entry.ws.readyState === WebSocket.OPEN) {
          entry.ws.send('ping')
        }
      }, PING_INTERVAL)
      resetWatchdog()
      finish()
      // 触发重连回调：拉取断连期间漏掉的消息
      if (entry.reconnecting) {
        entry.reconnecting = false
        onReconnectCallback?.(sessionId)
      }
    }
    ws.onerror = () => {
      clearTimeout(timer)
      finish()
    }
    ws.onmessage = (ev) => {
      const raw = String(ev.data ?? '')
      // pong 是心跳响应，不转发给业务 handler
      if (raw === 'pong') {
        resetWatchdog()
        return
      }
      resetWatchdog()
      dispatchWsMessage(sessionId, raw)
    }
    ws.onclose = () => {
      if (entry.pingTimer) clearInterval(entry.pingTimer)
      if (entry.watchdogTimer) clearTimeout(entry.watchdogTimer)
      if (pool.get(sessionId)?.ws === ws) pool.delete(sessionId)
      // working 状态下自动重连，避免流式输出中途断开后前端无感知
      if (isSessionWorking(sessionId) && !entry.reconnecting) {
        entry.reconnecting = true
        setTimeout(() => {
          entry.reconnecting = false
          if (isSessionWorking(sessionId) && pool.get(sessionId)?.ws !== ws) {
            console.info(`[ChatWS] ${sessionId} 自动重连中...`)
            ensureSessionWs(sessionId, wsBase).catch(() => {})
          }
        }, 1500)
      }
    }
  })

  return entry.connectPromise
}

/** 构建应保活的 session WS 集合 */
export function buildWsKeepSet(currentSessionId: string | undefined): Set<string> {
  const keep = new Set(workingSessionIds.value)
  if (currentSessionId) keep.add(currentSessionId)
  return keep
}

/** 检查指定 session 的 WebSocket 是否处于 OPEN 状态 */
export function isSessionWsConnected(sessionId: string): boolean {
  const entry = pool.get(sessionId)
  return !!entry?.ws && entry.ws.readyState === WebSocket.OPEN
}
