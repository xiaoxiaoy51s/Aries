import type { ChatMessage } from '@/types/chatMessage'
import { buildStreamEventFromLogEvent } from '@/utils/chatLogBridge'
import { buildMessageFromSnapshotEvents } from '@/utils/chatSnapshotApply'
import type { ApplyStreamEventDeps } from '@/utils/applyStreamEvent'
import { applyStreamEvent } from '@/utils/applyStreamEvent'
import type { StreamEvent } from '@/api/chat'

/** 从 JSONL 全量重建 assistant 消息（断线/切回会话时补拉） */
export async function rebuildAssistantFromJsonl(
  baseUrl: string,
  messageId: number,
  prev: ChatMessage,
  onSubagent?: Parameters<typeof buildMessageFromSnapshotEvents>[4],
): Promise<ChatMessage | null> {
  const res = await fetch(`${baseUrl}/sessions/messages/${messageId}/jsonl`)
  if (!res.ok) return null
  const data = await res.json()
  const events: unknown[] = data.events || []
  if (!events.length) return null
  return buildMessageFromSnapshotEvents(prev, messageId, events, undefined, onSubagent)
}

/** 增量应用 JSONL 中尚未处理的事件（从 fromIndex 起） */
export function applyJsonlEventsFromIndex(
  assistantMsg: ChatMessage,
  events: unknown[],
  fromIndex: number,
  deps: ApplyStreamEventDeps,
  onComplete?: (messageId: number) => void,
): number {
  let applied = fromIndex
  for (let i = fromIndex; i < events.length; i++) {
    const raw = events[i] as Record<string, unknown>
    if (!raw || typeof raw !== 'object') continue
    if (raw.type === 'run_metadata') {
      applied = i + 1
      // JSONL 文件里只会落盘终态 run_metadata（流中间 snapshot 不写盘）
      onComplete?.(assistantMsg.messageId || 0)
      continue
    }
    if (raw.type === 'log_complete') {
      onComplete?.(assistantMsg.messageId || 0)
      applied = i + 1
      continue
    }
    const streamEvt = buildStreamEventFromLogEvent(raw)
    if (streamEvt === 'complete') {
      onComplete?.(assistantMsg.messageId || 0)
      applied = i + 1
      continue
    }
    if (!streamEvt) continue
    applyStreamEvent(assistantMsg, streamEvt as StreamEvent, { deps })
    applied = i + 1
  }
  return applied
}
