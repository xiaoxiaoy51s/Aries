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

export function saveSessionSnapshot(sessionId: string, snapshot: SessionChatSnapshot): void {
  if (!sessionId) return
  // 浅拷贝数组引用即可：captureSessionSnapshot 已用 .slice() 创建新数组
  // 避免对含大 base64 截图的消息做 JSON.parse(JSON.stringify()) 深拷贝
  snapshots.set(sessionId, {
    messages: snapshot.messages,
    isSending: snapshot.isSending,
    hasActiveChat: snapshot.hasActiveChat,
    activeAssistantMessageId: snapshot.activeAssistantMessageId,
    activeAssistantIdx: snapshot.activeAssistantIdx,
    sessionSubagents: snapshot.sessionSubagents,
    platformStreaming: snapshot.platformStreaming,
  })
}

export function loadSessionSnapshot(sessionId: string): SessionChatSnapshot | undefined {
  const s = snapshots.get(sessionId)
  if (!s) return undefined
  // 返回浅拷贝：调用方在 restoreSessionSnapshot 中会赋值给 messages.value
  // 不做深拷贝，避免对大消息列表（含截图 base64）的性能损耗
  return {
    messages: s.messages,
    isSending: s.isSending,
    hasActiveChat: s.hasActiveChat,
    activeAssistantMessageId: s.activeAssistantMessageId,
    activeAssistantIdx: s.activeAssistantIdx,
    sessionSubagents: s.sessionSubagents,
    platformStreaming: s.platformStreaming,
  }
}

export function hasSessionSnapshot(sessionId: string): boolean {
  return snapshots.has(sessionId)
}

export function clearSessionSnapshot(sessionId: string): void {
  snapshots.delete(sessionId)
}
