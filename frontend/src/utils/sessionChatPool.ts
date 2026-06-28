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
}

const snapshots = new Map<string, SessionChatSnapshot>()
const pool = new Map<string, PoolEntry>()
const handlers = new Map<string, WsPayloadHandler>()

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
  const entry: PoolEntry = { ws, connectPromise: null }
  pool.set(sessionId, entry)

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
      finish()
    }
    ws.onerror = () => {
      clearTimeout(timer)
      finish()
    }
    ws.onmessage = (ev) => dispatchWsMessage(sessionId, String(ev.data ?? ''))
    ws.onclose = () => {
      if (pool.get(sessionId)?.ws === ws) pool.delete(sessionId)
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
