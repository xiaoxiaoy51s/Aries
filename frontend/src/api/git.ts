/**
 * Git 及工具确认 API
 */
const BASE_URL = ''

function getBaseUrl(): string {
  try {
    const raw = localStorage.getItem('mimo:base_url')
    if (raw) return raw
  } catch {}
  return '/api'
}

export async function confirmTool(toolCallId: string, confirmed: boolean): Promise<void> {
  const baseUrl = getBaseUrl()
  const res = await fetch(`${baseUrl}/chat/confirm-tool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_call_id: toolCallId, confirmed }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || '确认失败')
  }
}
