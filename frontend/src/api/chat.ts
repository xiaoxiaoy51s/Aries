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
  type: 'content' | 'reasoning' | 'tool_call' | 'tool_result' | 'confirmation_required'
  data: any
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
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          const json = JSON.parse(data)
          
          // 检查是否是工具调用事件
          if (json.tool_call) {
            yield { type: 'tool_call', data: json.tool_call }
            continue
          }
          
          // 检查是否是工具结果事件
          if (json.tool_result) {
            yield { type: 'tool_result', data: json.tool_result }
            continue
          }
          
          // 检查是否是确认事件
          if (json.confirmation_required) {
            yield { type: 'confirmation_required', data: json.confirmation_required }
            continue
          }
          
          // 检查是否是推理内容
          const delta = json.choices?.[0]?.delta
          if (delta) {
            if (delta.reasoning_content) {
              yield { type: 'reasoning', data: delta.reasoning_content }
            }
            if (delta.content) {
              yield { type: 'content', data: delta.content }
            }
          }
        } catch {
          // ignore invalid json
        }
      }
    }
  }
}

export async function* streamVision(
  messages: ChatMessage[],
  images: string[],
  sessionId?: string,
  workDir?: string
): AsyncGenerator<StreamEvent> {
  // stub: fallback to streamChat
  yield* streamChat(messages, sessionId, workDir)
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
