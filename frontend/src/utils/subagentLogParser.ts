export interface SubagentInnerBlock {
  type: 'tool' | 'text' | 'summary'
  phase?: 'work' | 'answer'
  text?: string
  tool_name?: string
  status?: string
  args?: Record<string, any>
  result?: string
  error?: string
  tool_call_id?: string
}

/** 从 delegate_to_subagent 的 tool_result JSON 中解析 log_path / 最终回复 */
export function parseDelegateToolResult(raw: string | undefined): {
  log_path?: string
  final_message?: string
  status?: string
} {
  if (!raw) return {}
  try {
    let parsed: any = JSON.parse(raw)
    if (typeof parsed === 'string') {
      parsed = JSON.parse(parsed)
    }
    if (!parsed || typeof parsed !== 'object') return {}
    const log_path = String(parsed.log_path || '').trim()
    const final_message = parsed.result != null ? String(parsed.result) : ''
    const status = parsed.error ? 'failed' : (final_message || log_path ? 'success' : undefined)
    return {
      log_path: log_path || undefined,
      final_message: final_message || undefined,
      status,
    }
  } catch {
    return {}
  }
}

/** 把子 Agent JSONL 事件还原为 InnerBlock[] */
export function eventsToInnerBlocks(events: any[]): {
  blocks: SubagentInnerBlock[]
  finalMessage: string
} {
  const out: SubagentInnerBlock[] = []
  let final = ''
  for (const ev of events) {
    const t = ev?.type
    if (t === 'reasoning' || t === 'reasoning_text') {
      const delta = String(ev.text || ev.content || ev.delta || '')
      if (!delta) continue
      const last = out[out.length - 1]
      if (last && last.type === 'text' && last.phase === 'work') {
        last.text = (last.text || '') + delta
      } else {
        out.push({ type: 'text', phase: 'work', text: delta })
      }
    } else if (t === 'assistant_text' || t === 'content') {
      const delta = String(ev.text || ev.content || ev.delta || '')
      if (!delta) continue
      const last = out[out.length - 1]
      if (last && last.type === 'text' && last.phase === 'answer') {
        last.text = (last.text || '') + delta
      } else {
        out.push({ type: 'text', phase: 'answer', text: delta })
      }
    } else if (t === 'tool_call') {
      const toolName = String(ev.tool_name || ev.name || 'unknown')
      if (toolName === 'report_to_main') {
        const msg = ev.args?.message || ev.args?.result || ''
        if (msg) final = String(msg)
        continue
      }
      out.push({
        type: 'tool',
        tool_name: toolName,
        tool_call_id: ev.tool_call_id || ev.id || '',
        status: ev.status || 'running',
        args: ev.args,
        result: '',
        error: '',
      })
    } else if (t === 'tool_result') {
      if (ev.tool_name === 'report_to_main') {
        const msg = typeof ev.output === 'string' && ev.output && ev.output !== '{"received": true}'
          ? ev.output
          : ''
        if (msg && !msg.startsWith('{"received"')) final = msg
        continue
      }
      const tcId = String(ev.tool_call_id || ev.id || '')
      for (let i = out.length - 1; i >= 0; i--) {
        const b = out[i]
        if (b.type === 'tool' && b.tool_call_id === tcId) {
          b.status = ev.status || 'completed'
          b.result = typeof ev.result === 'string'
            ? ev.result
            : typeof ev.output === 'string'
              ? ev.output
              : JSON.stringify(ev.result || ev.output || '')
          b.error = ev.error || ''
          break
        }
      }
    }
  }
  return { blocks: out, finalMessage: final }
}

const REPORT_TOOL = 'report_to_main'

/** 增量应用单条 JSONL 事件（与主 Agent applyLogEvent 同源） */
export function applySubagentJsonlEvent(
  blocks: SubagentInnerBlock[],
  event: Record<string, any>,
): { blocks: SubagentInnerBlock[]; finalMessage?: string } {
  const out = blocks.map((b) => ({ ...b }))
  let finalMessage: string | undefined
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
    if (event.tool_name === REPORT_TOOL) return { blocks: out }
    const tcId = String(event.tool_call_id || event.id || '')
    for (let i = out.length - 1; i >= 0; i--) {
      const b = out[i]
      if (b.type === 'tool' && b.tool_call_id === tcId) {
        b.status = event.status || 'completed'
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

/** 过滤 report_to_main 工具块，并把最终回复追加为 answer 文本 */
export function finalizeSubagentDisplayBlocks(
  blocks: SubagentInnerBlock[],
  finalMessage?: string,
): SubagentInnerBlock[] {
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
