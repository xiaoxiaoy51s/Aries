import type { StreamEvent } from '@/api/chat'

export function buildStreamEventFromLogEvent(
  event: Record<string, unknown>,
): StreamEvent | null | 'complete' {
  switch (event.type) {
    case 'reasoning_text':
      return { type: 'reasoning', data: String(event.text || '') }
    case 'assistant_text':
      return { type: 'content', data: String(event.text || '') }
    case 'tool_call':
      return {
        type: 'tool_call',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          args: event.args,
          session_id: event.session_id || '',
        },
      }
    case 'tool_result':
      return {
        type: 'tool_result',
        data: {
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          status: event.status,
          output: typeof event.result === 'string' ? event.result : (event.result as { output?: string })?.output || '',
          file_change: event.file_change,
          session_id: event.session_id || '',
        },
      }
    case 'run_metadata':
      return { type: 'meta', data: event }
    case 'log_complete':
      return 'complete'
    case 'sub_agent':
      return {
        type: 'subagent_event',
        data: {
          task_id: event.tool_call_id,
          subagent: event.subagent,
          task: event.task,
          status: event.status,
          log_path: event.log_path,
          round: event.rounds,
          elapsed_ms: event.duration_ms,
          final_message: event.final_output,
        },
      }
    case 'error_event':
      return { type: 'error', data: event.error_msg || event.error || '未知错误' }
    case 'info_event':
      return { type: 'hint', data: event.info_msg || '' }
    default:
      return null
  }
}
