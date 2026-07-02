import type { ChatMessage, MessageBlock } from '@/types/chatMessage'
import { applySubagentJsonlEvent } from '@/utils/subagentLogParser'

export function findSubagentDelegateLocation(
  msgs: ChatMessage[],
  opts: {
    taskId?: string
    logPath?: string
    toolCallId?: string
    subagentName?: string
  },
): { msgIdx: number; blockIdx: number } | null {
  for (let mi = msgs.length - 1; mi >= 0; mi--) {
    const msg = msgs[mi]
    if (msg.role !== 'assistant' || !msg.blocks?.length) continue
    for (let bi = msg.blocks.length - 1; bi >= 0; bi--) {
      const b = msg.blocks[bi]
      if (b.type !== 'tool' || b.tool_name !== 'delegate_to_subagent') continue
      const sa = b.subagent
      if (opts.taskId && sa?.task_id === opts.taskId) return { msgIdx: mi, blockIdx: bi }
      if (opts.logPath && sa?.log_path === opts.logPath) return { msgIdx: mi, blockIdx: bi }
      if (opts.toolCallId && b.tool_call_id === opts.toolCallId) return { msgIdx: mi, blockIdx: bi }
      if (!sa?.task_id && !sa?.log_path) {
        if (opts.subagentName && b.args?.subagent_name === opts.subagentName) {
          return { msgIdx: mi, blockIdx: bi }
        }
        if (opts.toolCallId && b.tool_call_id === opts.toolCallId) {
          return { msgIdx: mi, blockIdx: bi }
        }
      }
    }
  }
  return null
}

function applySubagentLogStarted(
  msgs: ChatMessage[],
  payload: {
    taskId: string
    logPath: string
    toolCallId: string
    subagentName: string
  },
): ChatMessage[] {
  const loc = findSubagentDelegateLocation(msgs, payload)
  if (!loc) return msgs
  const out = msgs.slice()
  const msg = { ...out[loc.msgIdx] }
  const blocks = (msg.blocks || []).slice()
  const block = { ...blocks[loc.blockIdx] }
  block.subagent = {
    ...(block.subagent || {}),
    task_id: payload.taskId || block.subagent?.task_id,
    log_path: payload.logPath || block.subagent?.log_path,
    subagent: payload.subagentName || block.subagent?.subagent || String(block.args?.subagent_name || ''),
    task: block.subagent?.task || String(block.args?.task || ''),
    status: 'running',
    inner_blocks: block.subagent?.inner_blocks || [],
  }
  blocks[loc.blockIdx] = block
  msg.blocks = blocks
  out[loc.msgIdx] = msg
  return out
}

function applySubagentLogEvent(
  msgs: ChatMessage[],
  payload: {
    taskId: string
    logPath: string
    toolCallId: string
    subagentName?: string
    event: Record<string, unknown>
  },
): ChatMessage[] {
  const loc = findSubagentDelegateLocation(msgs, payload)
  if (!loc) return msgs
  const out = msgs.slice()
  const msg = { ...out[loc.msgIdx] }
  const blocks = (msg.blocks || []).slice()
  const block = { ...blocks[loc.blockIdx] }
  const inner = (block.subagent?.inner_blocks || []).slice()
  const applied = applySubagentJsonlEvent(inner, payload.event)
  block.subagent = {
    ...(block.subagent || {}),
    task_id: payload.taskId || block.subagent?.task_id,
    log_path: payload.logPath || block.subagent?.log_path,
    subagent: payload.subagentName || block.subagent?.subagent,
    status: 'running',
    inner_blocks: applied.blocks,
    final_message: applied.finalMessage || block.subagent?.final_message,
  }
  blocks[loc.blockIdx] = block
  msg.blocks = blocks
  out[loc.msgIdx] = msg
  return out
}

function applySubagentLogComplete(
  msgs: ChatMessage[],
  payload: { taskId: string; logPath: string; toolCallId: string },
): ChatMessage[] {
  const loc = findSubagentDelegateLocation(msgs, payload)
  if (!loc) return msgs
  const out = msgs.slice()
  const msg = { ...out[loc.msgIdx] }
  const blocks = (msg.blocks || []).slice()
  const block = { ...blocks[loc.blockIdx] }
  if (block.subagent) {
    const st = block.subagent.status
    if (st === 'running' || st === 'pending' || st === 'stalled' || !st) {
      block.subagent = { ...block.subagent, status: 'success' }
    }
  }
  blocks[loc.blockIdx] = block
  msg.blocks = blocks
  out[loc.msgIdx] = msg
  return out
}

export function handleSubagentLogWsPayload(
  data: Record<string, unknown>,
  targetMessages: ChatMessage[],
): ChatMessage[] {
  const taskId = String(data.task_id || '')
  const logPath = String(data.jsonl_path || '')
  const toolCallId = String(data.tool_call_id || '')
  const subagentName = String(data.subagent || '')

  if (data.type === 'subagent_log_started') {
    return applySubagentLogStarted(targetMessages, { taskId, logPath, toolCallId, subagentName })
  }
  if (data.type === 'subagent_log_event') {
    const evt = data.event as Record<string, unknown> | undefined
    if (!evt) return targetMessages
    return applySubagentLogEvent(targetMessages, {
      taskId,
      logPath,
      toolCallId,
      subagentName,
      event: evt,
    })
  }
  if (data.type === 'subagent_log_complete') {
    return applySubagentLogComplete(targetMessages, { taskId, logPath, toolCallId })
  }
  return targetMessages
}

/** 在 assistant blocks 中定位 delegate_to_subagent 工具块（legacy stream_event 用） */
export function findDelegateBlockForStreamEvent(
  blocks: MessageBlock[],
  taskId: string,
  subName: string,
): MessageBlock | undefined {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b.type !== 'tool' || b.tool_name !== 'delegate_to_subagent') continue
    if (taskId && b.subagent?.task_id === taskId) return b
    if (
      !b.subagent?.task_id &&
      (!subName || !b.args?.subagent_name || b.args.subagent_name === subName)
    ) {
      return b
    }
  }
  return undefined
}
