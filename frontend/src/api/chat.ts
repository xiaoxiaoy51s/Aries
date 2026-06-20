import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface StreamEvent {
  type: 'content' | 'reasoning' | 'tool_call' | 'tool_result' | 'confirmation_required' | 'error' | 'context_usage' | 'meta'
  data: any
  meta?: { session_id?: string }
}

export function jsonToStreamEvent(json: Record<string, unknown>): StreamEvent | null {
  // 处理错误事件
  if (json.error) {
    return { type: 'error', data: json.error }
  }
  if (json.context_token_usage) {
    return { type: 'context_usage', data: json.context_token_usage }
  }
  if (json.meta) {
    return { type: 'meta', data: json.meta }
  }
  if (json.tool_call) {
    return { type: 'tool_call', data: json.tool_call }
  }
  if (json.tool_result) {
    return { type: 'tool_result', data: json.tool_result }
  }
  if (json.confirmation_required) {
    return { type: 'confirmation_required', data: json.confirmation_required }
  }

  const delta = (json.choices as Array<{ delta?: Record<string, unknown> }> | undefined)?.[0]?.delta
  if (!delta) return null

  if (delta.reasoning_content) {
    return { type: 'reasoning', data: delta.reasoning_content }
  }
  if (delta.content) {
    return { type: 'content', data: delta.content }
  }
  return null
}

async function* parseSseResponse(res: Response): AsyncGenerator<StreamEvent> {
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || '请求失败')
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取响应')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') return
      try {
        const json = JSON.parse(data) as Record<string, unknown>
        const event = jsonToStreamEvent(json)
        if (event) yield event
      } catch {
        // ignore invalid json
      }
    }
  }
}

export async function* streamChat(
  messages: ChatMessage[],
  sessionId?: string,
  workDir?: string
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${getBaseUrl()}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      session_id: sessionId,
      work_dir: workDir || undefined,
      stream: true,
    }),
  })

  yield* parseSseResponse(res)
}

export async function* streamVision(
  messages: ChatMessage[],
  images: string[],
  sessionId?: string,
  workDir?: string
): AsyncGenerator<StreamEvent> {
  const lastUser = [...messages].reverse().find((m) => m.role === 'user')
  const text = lastUser?.content?.trim() || '请描述这张图片的内容'

  const res = await fetch(`${getBaseUrl()}/chat/vision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      images,
      session_id: sessionId,
      work_dir: workDir || undefined,
      stream: true,
    }),
  })

  yield* parseSseResponse(res)
}

export async function stopChat(sessionId: string): Promise<void> {
  try {
    await fetch(`${getBaseUrl()}/chat/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    })
  } catch (e) {
    console.error('stopChat error', e)
  }
}

export async function* streamTempChat(
  messages: { role: string; content: string }[],
  sessionId?: string,
  workDir?: string
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${getBaseUrl()}/chat/temp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      session_id: sessionId,
      work_dir: workDir || undefined,
    }),
  })
  yield* parseSseResponse(res)
}
