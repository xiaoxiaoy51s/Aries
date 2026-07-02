import type { ChatMessage } from '@/types/chatMessage'

const SUBAGENT_ACTIVE_STATUSES = new Set(['running', 'pending', 'stalled'])

export function parseStoredImagePaths(imagePath?: string | null): string[] {
  if (!imagePath) return []
  try {
    const parsed = JSON.parse(imagePath)
    return Array.isArray(parsed) ? parsed.filter(Boolean) : [imagePath]
  } catch {
    return [imagePath]
  }
}

export function enrichUserMessage(content: string): Pick<ChatMessage, 'content' | 'slashCommand' | 'slashBody'> {
  const match = content.match(/^(\/[\w-]+)\s*(.*)$/s)
  if (!match) return { content }
  return {
    content,
    slashCommand: match[1],
    slashBody: match[2]?.trim() || '',
  }
}

/**
 * 判断某条消息是否含运行中工具/子 agent。
 * 注意：仅用于「实时流式」场景下定位当前活动消息（如断线重连后恢复 loading），
 * 不能用于判断整个会话是否工作中，否则加载的历史消息里残留的 running 工具块会造成永久误判。
 */
export function messageHasRunningWork(msg: ChatMessage): boolean {
  if (msg.role !== 'assistant') return false
  if (msg.isLoading) return true
  for (const block of msg.blocks || []) {
    if (block.type !== 'tool') continue
    if (block.status === 'running') return true
    if (block.tool_name === 'delegate_to_subagent' && block.subagent?.status) {
      if (SUBAGENT_ACTIVE_STATUSES.has(block.subagent.status)) return true
    }
  }
  for (const tool of msg.tools || []) {
    if (tool.status === 'running') return true
  }
  return false
}

/**
 * 会话是否处于「工作中」。
 * 只依据实时信号：isSending（本标签正在流式）或占位消息 isLoading（log_started→log_complete 期间为 true）。
 * 不扫描任意工具块状态，避免历史消息里中断残留的 running 块导致输入框/侧边栏永久转圈。
 */
export function sessionHasActiveWork(msgs: ChatMessage[], sending: boolean): boolean {
  if (sending) return true
  return msgs.some((m) => m.role === 'assistant' && m.isLoading === true)
}

export function mapRawMessagesToChat(rawMessages: Array<Record<string, unknown>>): ChatMessage[] {
  return rawMessages.map((m) => {
    const base: ChatMessage = {
      role: m.role as 'user' | 'assistant',
      content: (m.content as string) || '',
      mode: (m.mode as string) || 'agent',
      reasoning: [],
      tools: [],
      blocks: [],
      isLoading: false,
      messageSnapshotJson: (m.message_snapshot_json as string) || undefined,
      messageId: m.id as number | undefined,
    }
    if (m.role === 'user') {
      Object.assign(base, enrichUserMessage((m.content as string) || ''))
      base.images = parseStoredImagePaths(m.image_path as string | undefined)
    }
    return base
  })
}

export function buildSessionTitle(text: string): string {
  const raw = text.trim().replace(/\n/g, ' ')
  if (!raw) return '新对话'
  return raw.slice(0, 18) + (raw.length > 18 ? '…' : '')
}

export function findAssistantMessageIndex(
  messages: ChatMessage[],
  messageId: number,
  activeAssistantIdx: number | null,
): number {
  if (messageId > 0) {
    const byId = messages.findIndex(
      (m) => m.role === 'assistant' && m.messageId === messageId,
    )
    if (byId >= 0) return byId
    return -1
  }
  if (activeAssistantIdx != null && messages[activeAssistantIdx]?.role === 'assistant') {
    return activeAssistantIdx
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant' && messages[i].isLoading) {
      return i
    }
  }
  return -1
}
