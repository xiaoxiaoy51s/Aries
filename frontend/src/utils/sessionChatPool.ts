/** 多会话 WebSocket 连接池 + 切换 session 时的 UI 状态快照 */
import { isSessionWorking, workingSessionIds, MAX_CONCURRENT_WORKING_SESSIONS } from './sessionWorkStore'
import { streamDiag, wsReadyStateLabel } from './streamDebug'
import { ingestSubagentWsPayload, isSubagentLogBatchBound } from './chatSubagentBatchBridge'

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
}

/** 心跳间隔（ms）：working session 期间保持较高频率避免中间层空闲断连 */
const PING_INTERVAL = 15000
/** 无消息超时（ms）：超过此时间未收到任何消息则判定断连 */
const WATCHDOG_TIMEOUT = 40000
/** 断线重连基础延迟（ms）：首次尝试尽量快（秒级） */
const RECONNECT_BASE_DELAY = 400
/** 断线重连最大延迟（ms）：连续失败时指数退避封顶 */
const RECONNECT_MAX_DELAY = 5000

const snapshots = new Map<string, SessionChatSnapshot>()
const pool = new Map<string, PoolEntry>()
const handlers = new Map<string, WsPayloadHandler>()
/** 连续重连失败次数（用于指数退避），成功连上即清零 */
const reconnectAttempts = new Map<string, number>()
/** 正在重连的 session：新连接 onopen 时据此触发补拉回调 */
const reconnectPending = new Set<string>()
/** 已排期的重连定时器，避免重复排期 */
const reconnectTimers = new Map<string, ReturnType<typeof setTimeout>>()
/**
 * 当前查看的 session：即使 working=false 也保持 WS 保活+断线重连。
 * 这样即便 UI 的 working 状态被误清，WS 仍会重连并通过 onReconnectCallback
 * 用后端真实状态自愈，避免「后端在写日志但前端显示已结束」的死锁。
 */
let keepAliveSessionId: string | null = null
/** 重连成功后的回调（chatPage 注册，用于拉取断连期间漏掉的消息） */
let onReconnectCallback: ((sessionId: string) => void) | null = null

/** 设置当前需保活的 session（切换会话时调用，null 表示无） */
export function setKeepAliveSession(sessionId: string | null): void {
  keepAliveSessionId = sessionId
}

/** 该 session 是否应保持 WS 连接（working 或当前查看） */
function shouldKeepConnected(sessionId: string): boolean {
  return isSessionWorking(sessionId) || keepAliveSessionId === sessionId
}

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
    if (isSubagentLogBatchBound() && ingestSubagentWsPayload(data) === 'handled') return
    handlers.get(sessionId)?.(data)
  } catch {
    // ignore malformed
  }
}

function closePoolEntry(sessionId: string, reason = 'closePoolEntry'): void {
  streamDiag('WS', 'closePoolEntry', { sessionId, reason, working: isSessionWorking(sessionId) })
  const timer = reconnectTimers.get(sessionId)
  if (timer) {
    clearTimeout(timer)
    reconnectTimers.delete(sessionId)
  }
  reconnectPending.delete(sessionId)
  reconnectAttempts.delete(sessionId)
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

/**
 * 断线后为 working session 排期重连（指数退避，首次约 400ms）。
 * 标记 reconnectPending，使新连接 onopen 时触发 JSONL 补拉回调。
 */
function scheduleReconnect(sessionId: string, wsBase: string, trigger = 'onclose'): void {
  if (!shouldKeepConnected(sessionId)) {
    streamDiag('WS', 'scheduleReconnect skipped (not kept)', { sessionId, trigger })
    return
  }
  // 已有存活/连接中的连接，无需重连
  const existing = pool.get(sessionId)
  if (
    existing &&
    (existing.ws.readyState === WebSocket.OPEN || existing.ws.readyState === WebSocket.CONNECTING)
  ) {
    return
  }
  // 已排期则不重复
  if (reconnectTimers.has(sessionId)) return

  const attempts = reconnectAttempts.get(sessionId) ?? 0
  const delay = Math.min(RECONNECT_BASE_DELAY * 2 ** attempts, RECONNECT_MAX_DELAY)
  reconnectAttempts.set(sessionId, attempts + 1)
  reconnectPending.add(sessionId)

  streamDiag('WS', 'scheduleReconnect', {
    sessionId,
    trigger,
    attempt: attempts + 1,
    delayMs: delay,
    working: isSessionWorking(sessionId),
  })

  const timer = setTimeout(() => {
    reconnectTimers.delete(sessionId)
    if (!shouldKeepConnected(sessionId)) {
      reconnectPending.delete(sessionId)
      reconnectAttempts.delete(sessionId)
      return
    }
    const cur = pool.get(sessionId)
    if (
      cur &&
      (cur.ws.readyState === WebSocket.OPEN || cur.ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    console.info(`[ChatWS] ${sessionId} 自动重连中…（第 ${attempts + 1} 次）`)
    streamDiag('WS', 'reconnect attempt', { sessionId, attempt: attempts + 1 })
    ensureSessionWs(sessionId, wsBase).catch(() => {})
  }, delay)
  reconnectTimers.set(sessionId, timer)
}

/** 供外部（健康检查）主动触发一次带补拉语义的重连 */
export function reconnectSessionWs(sessionId: string, wsBase: string): void {
  if (!sessionId) return
  streamDiag('WS', 'reconnectSessionWs (health check)', { sessionId })
  reconnectPending.add(sessionId)
  ensureSessionWs(sessionId, wsBase).catch(() => {})
}

/** 保留正在工作的 session + 当前查看的 session 的 WS，其余关闭 */
export function pruneSessionWsKeep(keepSessionIds: Iterable<string>): void {
  const keep = new Set(keepSessionIds)
  for (const sid of [...pool.keys()]) {
    if (!keep.has(sid)) closePoolEntry(sid, 'pruneSessionWsKeep')
  }
}

export function closeSessionWs(sessionId: string): void {
  closePoolEntry(sessionId, 'closeSessionWs')
}

export function closeAllSessionWs(): void {
  for (const sid of [...pool.keys()]) closePoolEntry(sid)
}

export function ensureSessionWs(sessionId: string, wsBase: string): Promise<void> {
  if (!sessionId) return Promise.resolve()

  const existing = pool.get(sessionId)
  if (existing?.ws.readyState === WebSocket.OPEN) {
    streamDiag('WS', 'ensureSessionWs reuse OPEN', { sessionId })
    return Promise.resolve()
  }
  if (existing?.connectPromise) {
    streamDiag('WS', 'ensureSessionWs wait connectPromise', {
      sessionId,
      readyState: wsReadyStateLabel(existing.ws.readyState),
    })
    return existing.connectPromise
  }

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
  streamDiag('WS', 'ensureSessionWs connecting', {
    sessionId,
    wsUrl,
    reconnectPending: reconnectPending.has(sessionId),
    working: isSessionWorking(sessionId),
  })
  const ws = new WebSocket(wsUrl)
  const entry: PoolEntry = {
    ws,
    connectPromise: null,
    pingTimer: null,
    watchdogTimer: null,
    lastMsgAt: Date.now(),
    wsBase,
  }
  pool.set(sessionId, entry)

  /** 重置 watchdog：收到任意消息后延长超时 */
  const resetWatchdog = () => {
    entry.lastMsgAt = Date.now()
    if (entry.watchdogTimer) clearTimeout(entry.watchdogTimer)
    entry.watchdogTimer = setTimeout(() => {
      const silentMs = Date.now() - entry.lastMsgAt
      console.warn(`[ChatWS] ${sessionId} 心跳超时，主动断开并重连`)
      streamDiag('WS', 'watchdog timeout → close', {
        sessionId,
        silentMs,
        watchdogTimeoutMs: WATCHDOG_TIMEOUT,
        readyState: wsReadyStateLabel(entry.ws.readyState),
      })
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
      reconnectAttempts.delete(sessionId)
      streamDiag('WS', 'onopen', {
        sessionId,
        reconnectPending: reconnectPending.has(sessionId),
        willCatchUp: reconnectPending.has(sessionId),
      })
      // 启动心跳
      entry.pingTimer = setInterval(() => {
        if (entry.ws.readyState === WebSocket.OPEN) {
          entry.ws.send('ping')
          // 客户端已发 ping 即视为连接存活，避免子 agent 长时间无业务消息时误判断连
          resetWatchdog()
        }
      }, PING_INTERVAL)
      resetWatchdog()
      finish()
      // 若本次是重连：触发补拉回调，拉取断连期间漏掉的消息
      if (reconnectPending.has(sessionId)) {
        reconnectPending.delete(sessionId)
        streamDiag('WS', 'onopen → onReconnectCallback', { sessionId })
        onReconnectCallback?.(sessionId)
      }
    }
    ws.onerror = (ev) => {
      clearTimeout(timer)
      streamDiag('WS', 'onerror', { sessionId, event: String(ev) })
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
      // 仅记录生命周期事件；log_event 每个 token 一条，开启后会卡 UI
      try {
        const data = JSON.parse(raw) as Record<string, unknown>
        const evtType = typeof data.type === 'string' ? data.type : ''
        if (evtType === 'log_complete' || evtType === 'log_started') {
          streamDiag('Event', `ws ${evtType}`, {
            sessionId,
            messageId: data.message_id,
          })
        }
      } catch {
        // ignore
      }
      dispatchWsMessage(sessionId, raw)
    }
    ws.onclose = (ev) => {
      streamDiag('WS', 'onclose', {
        sessionId,
        code: ev.code,
        reason: ev.reason || '',
        wasClean: ev.wasClean,
        working: isSessionWorking(sessionId),
        readyState: wsReadyStateLabel(ws.readyState),
      })
      if (entry.pingTimer) clearInterval(entry.pingTimer)
      if (entry.watchdogTimer) clearTimeout(entry.watchdogTimer)
      if (pool.get(sessionId)?.ws === ws) pool.delete(sessionId)
      scheduleReconnect(sessionId, wsBase, `onclose code=${ev.code}`)
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
