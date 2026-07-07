/** 多会话 UI 状态快照（SSE 模式已移除 WebSocket 连接池） */

export interface SessionChatSnapshot {
  messages: unknown[]
  isSending: boolean
  hasActiveChat: boolean
  activeAssistantMessageId: number | null
  activeAssistantIdx: number | null
  sessionSubagents: unknown[]
  platformStreaming: boolean
}

const snapshots = new Map<string, SessionChatSnapshot>()

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