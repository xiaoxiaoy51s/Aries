import type { Ref } from 'vue'
import type { ChatMessage } from '@/types/chatMessage'
import {
  enqueueSubagentLogEvent,
  flushLogEventsNow,
  setSubagentLogBatchHandler,
} from '@/utils/logEventBatcher'
import { handleSubagentLogWsPayloadBatch } from '@/utils/chatSubagentWs'

let messagesRef: Ref<ChatMessage[]> | null = null
let afterUpdate: (() => void) | null = null

export function isSubagentLogBatchBound(): boolean {
  return messagesRef != null
}

export function bindSubagentLogBatch(
  messages: Ref<ChatMessage[]>,
  onUpdated?: () => void,
): void {
  messagesRef = messages
  afterUpdate = onUpdated ?? null
  setSubagentLogBatchHandler(applySubagentBatch)
}

export function unbindSubagentLogBatch(): void {
  setSubagentLogBatchHandler(null)
  messagesRef = null
  afterUpdate = null
}

function applySubagentBatch(items: Array<{ data: Record<string, unknown> }>) {
  if (!messagesRef || !items.length) return
  messagesRef.value = handleSubagentLogWsPayloadBatch(items, messagesRef.value)
  afterUpdate?.()
}

/** WebSocket 入口：子 Agent 高频 log_event 走批处理，complete 前先 flush */
export function ingestSubagentWsPayload(data: Record<string, unknown>): 'handled' | 'forward' {
  const type = data.type
  if (type === 'subagent_log_event' || type === 'subagent_log_started') {
    enqueueSubagentLogEvent(data)
    return 'handled'
  }
  if (type === 'subagent_log_complete') {
    flushLogEventsNow()
    return 'forward'
  }
  return 'forward'
}
