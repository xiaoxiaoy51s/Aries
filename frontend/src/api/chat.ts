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
  type: 'content' | 'reasoning' | 'tool_call' | 'tool_result' | 'confirmation_required' | 'error' | 'context_usage' | 'meta' | 'intent' | 'hint' | 'subagent_event' | 'subagent_reasoning' | 'subagent_content' | 'subagent_tool_call' | 'subagent_tool_result' | 'todo_update'
  data: any
  meta?: { session_id?: string }
}

export interface StartChatResponse {
  status: 'started' | 'error'
  session_id: string
  subagent_mode?: string
  error?: string
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
  if (json.intent) {
    return { type: 'intent', data: json.intent }
  }
  if (json.hint) {
    return { type: 'hint', data: json.hint }
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
  if (json.subagent_event) {
    return { type: 'subagent_event', data: json.subagent_event }
  }
  if (json.subagent_reasoning) {
    return { type: 'subagent_reasoning', data: json.subagent_reasoning }
  }
  if (json.subagent_content) {
    return { type: 'subagent_content', data: json.subagent_content }
  }
  if (json.subagent_tool_call) {
    return { type: 'subagent_tool_call', data: json.subagent_tool_call }
  }
  if (json.subagent_tool_result) {
    return { type: 'subagent_tool_result', data: json.subagent_tool_result }
  }
  if (json.todo_update) {
    return { type: 'todo_update', data: json.todo_update }
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

/**
 * 发送聊天消息（POST 后立即返回，不做流式接收）
 * 实时数据通过 WebSocket（/ws/chat?session_id=xxx）推送
 */
export async function startChat(
  messages: ChatMessage[],
  sessionId?: string,
  workDir?: string
): Promise<StartChatResponse> {
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
    const errText = await res.text()
    throw new Error(errText || '请求失败')
  }
  return (await res.json()) as StartChatResponse
}

/**
 * @deprecated 流式 API 已废弃。保留仅为兼容旧调用方，实际数据请通过 WebSocket 接收。
 */
export async function* streamChat(
  messages: ChatMessage[],
  sessionId?: string,
  workDir?: string
): AsyncGenerator<StreamEvent> {
  // 改为非流式：调用 startChat 后立即返回，事件通过 WebSocket 推送
  yield* _noopStream()
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
  if (!res.ok) {
    const errText = await res.text()
    throw new Error(errText || '请求失败')
  }
  // 实时数据通过 WebSocket 推送
  yield* _noopStream()
}

export async function startVision(
  messages: ChatMessage[],
  images: string[],
  sessionId?: string,
  workDir?: string
): Promise<StartChatResponse> {
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
  if (!res.ok) {
    const errText = await res.text()
    throw new Error(errText || '请求失败')
  }
  return (await res.json()) as StartChatResponse
}

export function stopChat(sessionId: string): Promise<void> {
  return fetch(`${getBaseUrl()}/chat/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
    .then(() => undefined)
    .catch((e) => {
      console.error('stopChat error', e)
    })
}

export async function checkChatStatus(sessionId: string): Promise<boolean> {
  try {
    const res = await fetch(`${getBaseUrl()}/chat/status/${sessionId}`)
    const data = await res.json()
    return !!data.running
  } catch {
    return false
  }
}

/**
 * @deprecated 旧版 SSE resume 已被 WebSocket 替代。保留仅为兼容旧调用方。
 */
export async function* resumeChat(sessionId: string): AsyncGenerator<StreamEvent> {
  yield* _noopStream()
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
  yield* _noopStream()
}

async function* _noopStream(): AsyncGenerator<StreamEvent> {
  // 流式 API 已统一替换为 WebSocket + JSONL 推送；此处不再产生任何事件
}
