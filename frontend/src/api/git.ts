/**
 * 工具确认 API
 */
import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export async function confirmTool(toolCallId: string, confirmed: boolean): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/chat/confirm-tool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_call_id: toolCallId, confirmed }),
  })
  if (!res.ok) {
    let message = '确认失败'
    try {
      const data = await res.json()
      message = data.detail || message
    } catch {
      const text = await res.text()
      if (text) message = text
    }
    throw new Error(message)
  }
}
