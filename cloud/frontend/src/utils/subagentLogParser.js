/** 子 Agent JSONL 事件 → 内嵌 blocks（参照 frontend/src/utils/subagentLogParser.ts） */

/**
 * @typedef {{ type: 'tool'|'text'|'summary', phase?: 'work'|'answer', text?: string, tool_name?: string, status?: string, args?: Record<string, any>, result?: string, error?: string, tool_call_id?: string }} SubagentInnerBlock
 */

const REPORT_TOOL = 'report_to_main'

/** 增量应用单条 JSONL 事件 */
export function applySubagentJsonlEvent(blocks, event) {
  const out = blocks.slice()
  let finalMessage
  const t = event?.type

  if (t === 'reasoning_text' || t === 'reasoning') {
    const delta = String(event.text || event.content || event.delta || '')
    if (!delta) return { blocks: out }
    const last = out[out.length - 1]
    if (last?.type === 'text' && last.phase === 'work') {
      last.text = (last.text || '') + delta
    } else {
      out.push({ type: 'text', phase: 'work', text: delta })
    }
  } else if (t === 'assistant_text' || t === 'content') {
    const delta = String(event.text || event.content || event.delta || '')
    if (!delta) return { blocks: out }
    const last = out[out.length - 1]
    if (last?.type === 'text' && last.phase === 'answer') {
      last.text = (last.text || '') + delta
    } else {
      out.push({ type: 'text', phase: 'answer', text: delta })
    }
  } else if (t === 'tool_call') {
    const toolName = String(event.tool_name || event.name || 'unknown')
    if (toolName === REPORT_TOOL) {
      const msg = event.args?.message || event.args?.result || ''
      if (msg) finalMessage = String(msg)
      return { blocks: out, finalMessage }
    }
    out.push({
      type: 'tool',
      tool_name: toolName,
      tool_call_id: event.tool_call_id || event.id || '',
      status: event.status || 'running',
      args: event.args,
      result: '',
      error: '',
    })
  } else if (t === 'tool_result') {
    if (event.tool_name === REPORT_TOOL) {
      const fromOutput = typeof event.output === 'string' ? event.output.trim() : ''
      if (fromOutput && !fromOutput.startsWith('{"received"')) {
        finalMessage = fromOutput
      }
      return { blocks: out, finalMessage }
    }
    const tcId = String(event.tool_call_id || event.id || '')
    for (let i = out.length - 1; i >= 0; i--) {
      const b = out[i]
      if (b.type === 'tool' && b.tool_call_id === tcId) {
        b.status = event.status || (event.error ? 'error' : 'completed')
        b.result = typeof event.result === 'string'
          ? event.result
          : typeof event.output === 'string'
            ? event.output
            : JSON.stringify(event.result || event.output || '')
        b.error = event.error || ''
        break
      }
    }
  }

  return { blocks: out, finalMessage }
}

/** 过滤 report_to_main，并把最终回复追加为 answer 文本 */
export function finalizeSubagentDisplayBlocks(blocks, finalMessage) {
  const out = blocks
    .filter((b) => !(b.type === 'tool' && b.tool_name === REPORT_TOOL))
    .map((b) => ({ ...b }))
  const finalText = String(finalMessage || '').trim()
  if (!finalText) return out
  const hasAnswer = out.some((b) => b.type === 'text' && b.phase === 'answer' && b.text === finalText)
  if (!hasAnswer) {
    out.push({ type: 'text', phase: 'answer', text: finalText })
  }
  return out
}

export const TERMINAL_SUBAGENT_STATUSES = new Set([
  'success',
  'failed',
  'timeout',
  'cancelled',
])

export function isTerminalSubagentStatus(status) {
  return !!status && TERMINAL_SUBAGENT_STATUSES.has(status)
}
