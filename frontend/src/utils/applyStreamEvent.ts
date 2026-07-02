import type { StreamEvent } from '@/api/chat'
import type { ChatMessage, MessageBlock, SubagentRecord } from '@/types/chatMessage'
import { findDelegateBlockForStreamEvent } from '@/utils/chatSubagentWs'
import {
  clearPetStatus,
  flushPetStatusForComplete,
  onStreamContentDelta,
  onStreamReasoningDelta,
  onStreamToolPhase,
  sendPetStatus,
} from '@/utils/chatPetStatus'

export interface ApplyStreamEventDeps {
  autoConfirmedToolIds: Set<string>
  onClearConfirmCountdown?: () => void
  upsertSubagent?: (record: SubagentRecord) => void
  upsertSubagentInList?: (list: SubagentRecord[], record: SubagentRecord) => void
  findSubagentByTaskId?: (taskId: string) => SubagentRecord | undefined
}

export interface ApplyStreamEventOptions {
  silent?: boolean
  subagents?: SubagentRecord[]
  deps?: ApplyStreamEventDeps
}

export function applyStreamEvent(
  assistantMsg: ChatMessage,
  evt: StreamEvent,
  opts?: ApplyStreamEventOptions,
) {
  const silent = opts?.silent ?? false
  const deps = opts?.deps

  if (evt.type === 'content' && evt.data) {
    if (!silent) onStreamContentDelta(evt.data)
    assistantMsg.content += evt.data
    const blocks = (assistantMsg.blocks || []).slice()
    const lastBlock = blocks[blocks.length - 1]
    if (lastBlock && lastBlock.type === 'text' && lastBlock.phase === 'answer') {
      lastBlock.text = (lastBlock.text || '') + evt.data
    } else {
      blocks.push({ type: 'text', text: evt.data, phase: 'answer' })
    }
    assistantMsg.blocks = blocks
  } else if (evt.type === 'reasoning') {
    if (!silent) onStreamReasoningDelta(evt.data)
    if (!assistantMsg.reasoning) assistantMsg.reasoning = []
    const blocks = (assistantMsg.blocks || []).slice()

    if (assistantMsg.reasoning.length === 0) {
      assistantMsg.reasoning.push(evt.data)
    } else {
      assistantMsg.reasoning[assistantMsg.reasoning.length - 1] += evt.data
    }
    const lastBlock = blocks[blocks.length - 1]
    if (lastBlock && lastBlock.type === 'text' && lastBlock.phase === 'work') {
      lastBlock.text = (lastBlock.text || '') + evt.data
    } else {
      blocks.push({ type: 'text', text: evt.data, phase: 'work' })
    }
    assistantMsg.blocks = blocks
  } else if (evt.type === 'tool_call') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    if (!silent) onStreamToolPhase()
    const toolCallId = String(evt.data.tool_call_id || '').trim()
    let existingBlockIdx = -1
    if (toolCallId) {
      existingBlockIdx = assistantMsg.blocks.findIndex(
        (b) => b.type === 'tool' && b.tool_call_id === toolCallId,
      )
    }
    if (existingBlockIdx >= 0) {
      const blocks = assistantMsg.blocks.slice()
      blocks[existingBlockIdx] = {
        ...blocks[existingBlockIdx],
        status: 'running',
        args: evt.data.args || blocks[existingBlockIdx].args,
        pending_confirmation: false,
      }
      assistantMsg.blocks = blocks
      const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
      if (lastTool && lastTool.name === evt.data.tool_name) {
        lastTool.status = 'running'
      }
    } else {
      const toolBlock: MessageBlock = {
        type: 'tool',
        tool_name: evt.data.tool_name,
        tool_call_id: evt.data.tool_call_id,
        session_id: evt.data.session_id || '',
        status: 'running',
        args: evt.data.args,
        result: '',
        error: '',
        started_at: '',
        ended_at: '',
      }
      assistantMsg.tools.push({
        name: evt.data.tool_name,
        status: 'running',
        args: evt.data.args,
        output: '',
      })
      assistantMsg.blocks = [...assistantMsg.blocks, toolBlock]
    }
  } else if (evt.type === 'tool_result') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    const toolName = evt.data.tool_name || 'tool'
    const ok = evt.data.status !== 'error'
    const output = (evt.data.output || '').trim()
    if (!silent) {
      let msg = `${ok ? '✅' : '❌'} ${toolName}`
      if (output) {
        msg += ': ' + (output.length > 150 ? output.slice(0, 150) + '…' : output)
      }
      sendPetStatus(msg)
    }
    if (evt.data.file_change) {
      if (!assistantMsg.artifacts) assistantMsg.artifacts = []
      assistantMsg.artifacts.push({
        file_path: evt.data.file_change.file_path || '',
        operation: evt.data.file_change.operation || 'modify',
        previous_content: evt.data.file_change.previous_content || '',
        new_content: evt.data.file_change.new_content || '',
        tool_name: toolName,
        tool_call_id: String(evt.data.tool_call_id || ''),
      })
    }
    const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
    if (lastTool && lastTool.name === evt.data.tool_name) {
      lastTool.status = evt.data.status || 'completed'
      lastTool.output = evt.data.output || ''
    }
    if (assistantMsg.blocks && assistantMsg.blocks.length > 0) {
      const blocks = assistantMsg.blocks.slice()
      const toolCallId = String(evt.data.tool_call_id || '').trim()
      let targetIdx = -1
      if (toolCallId) {
        targetIdx = blocks.findIndex(
          (b) => b.type === 'tool' && b.tool_call_id === toolCallId,
        )
      }
      if (targetIdx < 0) {
        for (let i = blocks.length - 1; i >= 0; i -= 1) {
          const b = blocks[i]
          if (b.type === 'tool' && (!evt.data.tool_name || b.tool_name === evt.data.tool_name)) {
            targetIdx = i
            break
          }
        }
      }
      if (targetIdx >= 0) {
        const block = blocks[targetIdx]
        if (block.type === 'tool') {
          const newStatus = evt.data.status || 'completed'
          const isPendingConfirm = newStatus === 'pending_confirmation'
          const isAutoConfirmed = block.tool_call_id && deps?.autoConfirmedToolIds.has(block.tool_call_id)
          const nextBlock: MessageBlock = {
            ...block,
            status: isAutoConfirmed && isPendingConfirm ? 'running' : newStatus,
            result: evt.data.output || '',
            ended_at: '',
            pending_confirmation: isAutoConfirmed ? false : (isPendingConfirm ? block.pending_confirmation : false),
            session_id: evt.data.session_id || block.session_id || '',
            auto_detached: Boolean(evt.data.auto_detached || block.auto_detached),
          }
          if (nextBlock.tool_name === 'delegate_to_subagent' && evt.data.output) {
            try {
              let parsed: unknown = JSON.parse(String(evt.data.output))
              if (typeof parsed === 'string') parsed = JSON.parse(parsed)
              if (parsed && typeof parsed === 'object') {
                const obj = parsed as Record<string, unknown>
                const logPath = String(obj.log_path || '').trim()
                const finalMsg = obj.result != null ? String(obj.result) : ''
                nextBlock.subagent = {
                  ...(nextBlock.subagent || {}),
                  log_path: logPath || nextBlock.subagent?.log_path,
                  final_message: finalMsg || nextBlock.subagent?.final_message,
                  status: obj.error ? 'failed' : 'success',
                }
              }
            } catch {
              // ignore malformed result
            }
          }
          blocks[targetIdx] = nextBlock
        }
      }
      assistantMsg.blocks = blocks
    }
    if (evt.data.status && evt.data.status !== 'pending_confirmation') {
      deps?.onClearConfirmCountdown?.()
    }
  } else if (evt.type === 'confirmation_required') {
    if (!assistantMsg.tools) assistantMsg.tools = []
    const lastTool = assistantMsg.tools[assistantMsg.tools.length - 1]
    if (lastTool && lastTool.name === evt.data.tool_name) {
      lastTool.status = 'pending_confirmation'
      lastTool.output = '等待确认…'
    }
    if (assistantMsg.blocks && assistantMsg.blocks.length > 0) {
      const blocks = assistantMsg.blocks.slice()
      const lastToolBlock = blocks[blocks.length - 1]
      if (lastToolBlock && lastToolBlock.type === 'tool') {
        lastToolBlock.status = 'pending_confirmation'
        lastToolBlock.pending_confirmation = true
        lastToolBlock.danger_info = evt.data.danger_info || ''
        lastToolBlock.danger_types = evt.data.danger_types || []
        lastToolBlock.tool_call_id = evt.data.tool_call_id
        if (evt.data.command && lastToolBlock.args) {
          lastToolBlock.args = { ...lastToolBlock.args, command: evt.data.command }
        }
      }
      assistantMsg.blocks = blocks
    }
  } else if (evt.type === 'subagent_event') {
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    const subData = evt.data || {}
    const subName = String(subData.subagent || '')
    const taskId = String(subData.task_id || '')
    const target = findDelegateBlockForStreamEvent(assistantMsg.blocks, taskId, subName)
    if (target) {
      target.subagent = {
        task_id: taskId || target.subagent?.task_id,
        subagent: subData.subagent,
        task: subData.task,
        status: subData.status,
        round: subData.round,
        last_event: subData.last_event,
        elapsed_ms: subData.elapsed_ms,
        log_path: subData.log_path,
        inner_blocks: target.subagent?.inner_blocks,
        final_message: target.subagent?.final_message,
      }
    }
    if (taskId && deps) {
      const record: SubagentRecord = {
        task_id: taskId,
        subagent: subData.subagent,
        task: subData.task,
        status: subData.status,
        round: subData.round,
        last_event: subData.last_event,
        elapsed_ms: subData.elapsed_ms,
        log_path: subData.log_path,
      }
      if (opts?.subagents && deps.upsertSubagentInList) {
        deps.upsertSubagentInList(opts.subagents, record)
      } else {
        deps.upsertSubagent?.(record)
      }
    }
  } else if (
    evt.type === 'subagent_reasoning' ||
    evt.type === 'subagent_content' ||
    evt.type === 'subagent_tool_call' ||
    evt.type === 'subagent_tool_result'
  ) {
    applySubagentGranularEvent(assistantMsg, evt, opts)
  } else if (evt.type === 'error') {
    assistantMsg.isLoading = false
    const errorMsg = typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data)
    assistantMsg.content = errorMsg
    if (!assistantMsg.blocks) assistantMsg.blocks = []
    assistantMsg.blocks.push({
      type: 'text',
      text: errorMsg,
      phase: 'answer',
      error: errorMsg,
    })
  }
}

function applySubagentGranularEvent(
  assistantMsg: ChatMessage,
  evt: StreamEvent,
  opts?: ApplyStreamEventOptions,
) {
  const deps = opts?.deps
  if (!assistantMsg.blocks) assistantMsg.blocks = []
  const d = evt.data || {}
  const taskId = String(d.task_id || '')
  const blocks = assistantMsg.blocks
  let target: MessageBlock | undefined
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b.type !== 'tool' || b.tool_name !== 'delegate_to_subagent') continue
    if (taskId && b.subagent?.task_id === taskId) { target = b; break }
    if (!b.subagent?.task_id && d.subagent && b.args?.subagent_name === d.subagent) { target = b; break }
  }
  if (!target) return
  if (!target.subagent) target.subagent = {}
  if (taskId && !target.subagent.task_id) target.subagent.task_id = taskId
  if (!target.subagent.inner_blocks) target.subagent.inner_blocks = []
  const inner: MessageBlock[] = target.subagent.inner_blocks

  let sessRecord = taskId && deps?.findSubagentByTaskId ? deps.findSubagentByTaskId(taskId) : undefined
  if (taskId && !sessRecord && deps?.upsertSubagent && deps.findSubagentByTaskId) {
    deps.upsertSubagent({ task_id: taskId, subagent: d.subagent, status: 'running' })
    sessRecord = deps.findSubagentByTaskId(taskId)
  }
  if (sessRecord && !sessRecord.inner_blocks) sessRecord.inner_blocks = []

  if (evt.type === 'subagent_reasoning') {
    appendTextDelta(inner, String(d.delta || ''), 'work', sessRecord?.inner_blocks)
  } else if (evt.type === 'subagent_content') {
    appendTextDelta(inner, String(d.delta || ''), 'answer', sessRecord?.inner_blocks)
  } else if (evt.type === 'subagent_tool_call') {
    const newBlock: MessageBlock = {
      type: 'tool',
      tool_name: d.tool_name || 'unknown',
      tool_call_id: d.tool_call_id || '',
      status: d.status || 'running',
      args: d.args,
      result: '',
      error: '',
      started_at: '',
      ended_at: '',
    }
    inner.push(newBlock)
    sessRecord?.inner_blocks?.push({ ...newBlock })
  } else if (evt.type === 'subagent_tool_result') {
    const tcId = String(d.tool_call_id || '')
    patchToolResult(inner, tcId, d)
    if (sessRecord?.inner_blocks) patchToolResult(sessRecord.inner_blocks, tcId, d)
    if (d.tool_name === 'report_to_main' && d.status === 'completed') {
      const finalMsg = typeof d.output === 'string' ? d.output : ''
      target.subagent.final_message = finalMsg
      if (sessRecord) sessRecord.final_message = finalMsg
    }
  }
}

function appendTextDelta(
  inner: MessageBlock[],
  delta: string,
  phase: 'work' | 'answer',
  sessInner?: MessageBlock[],
) {
  if (!delta) return
  const last = inner[inner.length - 1]
  if (last && last.type === 'text' && last.phase === phase) {
    last.text = (last.text || '') + delta
  } else {
    inner.push({ type: 'text', text: delta, phase })
  }
  if (sessInner) {
    const sLast = sessInner[sessInner.length - 1]
    if (sLast && sLast.type === 'text' && sLast.phase === phase) {
      sLast.text = (sLast.text || '') + delta
    } else {
      sessInner.push({ type: 'text', text: delta, phase })
    }
  }
}

function patchToolResult(blocks: MessageBlock[], tcId: string, d: Record<string, unknown>) {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i]
    if (b.type === 'tool' && b.tool_call_id === tcId) {
      b.status = (d.status as string) || 'completed'
      b.result = typeof d.output === 'string' ? d.output : JSON.stringify(d.output || '')
      b.error = (d.error as string) || ''
      b.ended_at = ''
      break
    }
  }
}

export { clearPetStatus, flushPetStatusForComplete }
