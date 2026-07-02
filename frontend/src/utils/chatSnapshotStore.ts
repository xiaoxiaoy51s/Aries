import type { ChatMessage } from '@/types/chatMessage'
import type { SessionChatSnapshot } from '@/utils/sessionChatPool'
import {
  bindStreamDuration,
  startStreamDuration,
  stopStreamDuration,
} from '@/utils/streamDurationStore'
import { markSessionWorking } from '@/utils/sessionWorkStore'

export function getOrCreateSnapshot(
  sessionId: string,
  loadSessionSnapshot: (id: string) => SessionChatSnapshot | undefined,
): SessionChatSnapshot {
  return loadSessionSnapshot(sessionId) ?? {
    messages: [],
    isSending: false,
    hasActiveChat: false,
    activeAssistantMessageId: null,
    activeAssistantIdx: null,
    sessionSubagents: [],
    platformStreaming: false,
  }
}

export function findAssistantMessageIndexInSnapshot(
  snapshot: SessionChatSnapshot,
  messageId: number,
): number {
  const msgs = snapshot.messages as ChatMessage[]
  if (messageId > 0) {
    const byId = msgs.findIndex((m) => m.role === 'assistant' && m.messageId === messageId)
    if (byId >= 0) return byId
    return -1
  }
  if (snapshot.activeAssistantIdx != null && msgs[snapshot.activeAssistantIdx]?.role === 'assistant') {
    return snapshot.activeAssistantIdx
  }
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'assistant' && msgs[i].isLoading) return i
  }
  return -1
}

export function completeLogMessageSnapshot(
  snapshot: SessionChatSnapshot,
  sessionId: string,
  messageId: number,
) {
  const idx = findAssistantMessageIndexInSnapshot(snapshot, messageId)
  if (idx >= 0) {
    const m = snapshot.messages[idx] as ChatMessage
    snapshot.messages[idx] = { ...m, isLoading: false }
  }
  stopStreamDuration(sessionId, messageId)
  if (!messageId || snapshot.activeAssistantMessageId === messageId) {
    snapshot.activeAssistantMessageId = null
    snapshot.activeAssistantIdx = null
  }
  snapshot.isSending = false
}

export function ensureLogPlaceholderSnapshot(
  snapshot: SessionChatSnapshot,
  sessionId: string,
  messageId: number,
  jsonlPath: string,
) {
  const msgs = snapshot.messages as ChatMessage[]
  let idx = msgs.findIndex((m) => m.role === 'assistant' && m.messageId === messageId)
  if (idx < 0) {
    const last = msgs[msgs.length - 1]
    if (
      last?.role === 'assistant' &&
      last.isLoading &&
      (!last.messageId || last.messageId === messageId)
    ) {
      idx = msgs.length - 1
    }
  }
  if (idx < 0) {
    snapshot.messages = [
      ...msgs,
      {
        role: 'assistant',
        content: '',
        reasoning: [],
        tools: [],
        blocks: [],
        isLoading: true,
        messageId,
        messageSnapshotJson: jsonlPath || undefined,
      },
    ]
    idx = snapshot.messages.length - 1
  } else {
    const m = snapshot.messages[idx] as ChatMessage
    snapshot.messages[idx] = {
      ...m,
      isLoading: true,
      messageId,
      messageSnapshotJson: jsonlPath || m.messageSnapshotJson,
    }
  }
  snapshot.activeAssistantIdx = idx
  snapshot.activeAssistantMessageId = messageId
  snapshot.hasActiveChat = true
  snapshot.isSending = true
  bindStreamDuration(sessionId, messageId)
  startStreamDuration(sessionId, messageId)
  markSessionWorking(sessionId)
}
