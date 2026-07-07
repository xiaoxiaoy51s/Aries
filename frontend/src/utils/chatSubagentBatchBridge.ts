import type { Ref } from 'vue'
import type { ChatMessage } from '@/types/chatMessage'
import {
  setSubagentLogBatchHandler,
} from '@/utils/logEventBatcher'
import { handleSubagentLogPayloadBatch } from '@/utils/chatSubagentWs'

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
  messagesRef.value = handleSubagentLogPayloadBatch(items, messagesRef.value)
  afterUpdate?.()
}
