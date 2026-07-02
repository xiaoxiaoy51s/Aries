import type { ChatMessage, MessageBlock, MessageMeta, SubagentRecord, ToolInfo } from '@/types/chatMessage'
import { normalizeRunMetadata } from '@/utils/runMetadata'
import { parseSnapshotEventObjects } from '@/utils/snapshotParser'

export function buildMessageFromSnapshotEvents(
  prev: ChatMessage,
  messageId: number,
  rawEvents: unknown[],
  raw?: { reasoning_content?: string },
  onSubagent?: (record: SubagentRecord) => void,
): ChatMessage | null {
  if (!prev || prev.role !== 'assistant') return null

  if (!rawEvents || rawEvents.length === 0) {
    return buildReasoningContentFallback(prev, messageId, raw?.reasoning_content)
  }

  const parsed = parseSnapshotEventObjects(rawEvents)
  const blocks: MessageBlock[] = []
  let snapshotMeta: MessageMeta | undefined

  for (const event of parsed) {
    switch (event.type) {
      case 'reasoning':
        if (
          blocks.length > 0 &&
          blocks[blocks.length - 1].type === 'text' &&
          blocks[blocks.length - 1].phase === 'work'
        ) {
          blocks[blocks.length - 1].text = (blocks[blocks.length - 1].text || '') + event.content
        } else {
          blocks.push({ type: 'text', text: event.content, phase: 'work' })
        }
        break

      case 'tool_call':
        blocks.push({
          type: 'tool',
          tool_name: event.toolName || 'unknown',
          tool_call_id: event.toolCallId || '',
          status: event.status || 'running',
          args: event.args,
          result: '',
          error: '',
          started_at: event.timestamp || '',
          ended_at: '',
        })
        break

      case 'sub_agent': {
        const tcId = event.toolCallId || ''
        let existing: MessageBlock | undefined
        if (tcId) {
          for (let i = blocks.length - 1; i >= 0; i--) {
            const b = blocks[i]
            if (b.type === 'tool' && b.tool_call_id === tcId) {
              existing = b
              break
            }
          }
        }
        const subagentField = {
          task_id: tcId,
          subagent: event.subagent,
          task: event.task,
          status: event.status,
          log_path: event.logPath,
          elapsed_ms: event.durationMs,
          final_message: event.finalOutput,
        }
        if (existing) {
          existing.tool_name = 'delegate_to_subagent'
          existing.status = event.status === 'success' ? 'completed' : (event.status || existing.status || 'running')
          if (event.finalOutput) existing.result = event.finalOutput
          if (event.status && event.status !== 'success') {
            existing.error = event.content || existing.error || ''
          }
          existing.ended_at = event.timestamp || existing.ended_at || ''
          existing.args = {
            ...(existing.args || {}),
            subagent_name: event.subagent || existing.args?.subagent_name || '',
            task: event.task || existing.args?.task || '',
          }
          existing.subagent = { ...(existing.subagent || {}), ...subagentField }
        } else {
          blocks.push({
            type: 'tool',
            tool_name: 'delegate_to_subagent',
            tool_call_id: tcId,
            status: event.status === 'success' ? 'completed' : (event.status || 'running'),
            args: {
              subagent_name: event.subagent || '',
              task: event.task || '',
              description: '',
            },
            result: event.finalOutput || '',
            error: event.status && event.status !== 'success' ? (event.content || '') : '',
            started_at: event.timestamp || '',
            ended_at: event.timestamp || '',
            subagent: subagentField,
          })
        }
        if (tcId && onSubagent) {
          onSubagent({
            task_id: tcId,
            subagent: event.subagent,
            task: event.task,
            status: event.status,
            log_path: event.logPath,
            elapsed_ms: event.durationMs,
            final_message: event.finalOutput,
            message_id: messageId,
          })
        }
        break
      }

      case 'tool_result':
        for (let i = blocks.length - 1; i >= 0; i--) {
          const b = blocks[i]
          if (b.type === 'tool' && (b.tool_name === event.toolName || b.tool_name === event.toolCallId)) {
            b.status = event.status || 'completed'
            b.result = event.content
            b.ended_at = event.timestamp || ''
            if (event.sessionId) b.session_id = event.sessionId
            break
          }
        }
        break

      case 'assistant_text':
        if (
          blocks.length > 0 &&
          blocks[blocks.length - 1].type === 'text' &&
          blocks[blocks.length - 1].phase === 'answer'
        ) {
          blocks[blocks.length - 1].text = (blocks[blocks.length - 1].text || '') + event.content
        } else {
          blocks.push({ type: 'text', text: event.content, phase: 'answer' })
        }
        break

      case 'error':
        blocks.push({
          type: 'text',
          text: event.content,
          phase: 'answer',
          error: event.content,
        })
        break

      case 'run_metadata':
        if (event.meta) snapshotMeta = normalizeRunMetadata(event.meta)
        break
    }
  }

  const reasoningJoined = parsed.filter((e) => e.type === 'reasoning').map((e) => e.content).join('')
  const reasoningSegments = reasoningJoined ? [reasoningJoined] : []
  const answerText = parsed.filter((e) => e.type === 'assistant_text').map((e) => e.content).join('')
  const errorText = parsed.find((e) => e.type === 'error')?.content || ''

  const artifacts = parsed
    .filter((e) => e.type === 'tool_result' && e.fileChange)
    .map((e) => ({
      file_path: e.fileChange!.file_path || '',
      operation: e.fileChange!.operation || 'modify',
      previous_content: e.fileChange!.previous_content || '',
      new_content: e.fileChange!.new_content || '',
      tool_name: e.toolName || '',
      tool_call_id: e.toolCallId || '',
      reverted: false,
    }))

  return {
    ...prev,
    blocks,
    reasoning: reasoningSegments,
    tools: parsed
      .filter((e) => e.type === 'tool_call' || e.type === 'tool_result')
      .reduce((acc: ToolInfo[], e) => {
        if (e.type === 'tool_call') {
          acc.push({
            name: e.toolName || 'unknown',
            status: e.status || 'running',
            args: e.args,
            output: '',
          })
        } else if (e.type === 'tool_result') {
          const t = acc.find((t) => t.name === e.toolName)
          if (t) {
            t.status = e.status || 'completed'
            t.output = e.content
          }
        }
        return acc
      }, []),
    content: answerText || errorText || prev.content,
    hasSnapshot: true,
    meta: snapshotMeta || prev.meta,
    artifacts,
  }
}

export function buildReasoningContentFallback(
  prev: ChatMessage,
  messageId: number,
  reasoningContent?: string | null,
): ChatMessage | null {
  if (!prev || prev.role !== 'assistant') return null
  const rc = (reasoningContent || '').trim()
  if (!rc) return null

  const segments = rc.split('\n').filter((line) => line.trim())
  if (segments.length === 0) return null

  const blocks: MessageBlock[] = segments.map((text) => ({
    type: 'text',
    text,
    phase: 'work',
  }))

  console.log(`[snapshot] 消息 ${messageId} 使用 reasoning_content 回退，${segments.length} 段`)

  return {
    ...prev,
    blocks,
    reasoning: segments,
    content: prev.content,
  }
}
