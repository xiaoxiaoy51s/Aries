/**
 * 解析消息快照 JSONL 事件，转换为前端可渲染的格式
 */

export interface SnapshotEvent {
  type: 'reasoning' | 'tool_call' | 'tool_result' | 'assistant_text' | 'error'
  content: string
  toolName?: string
  toolCallId?: string
  args?: Record<string, any>
  status?: string
  timestamp?: string
  errorType?: string
}

/**
 * 解析 JSONL 字符串为事件数组
 */
export function parseJsonlEvents(jsonlText: string): SnapshotEvent[] {
  const events: SnapshotEvent[] = []
  const lines = jsonlText.trim().split('\n')

  for (const line of lines) {
    if (!line.trim()) continue
    try {
      const json = JSON.parse(line)
      const event = convertEvent(json)
      if (event) {
        events.push(event)
      }
    } catch (e) {
      console.warn('Failed to parse JSONL line:', line, e)
    }
  }

  return events
}

/**
 * 将原始 JSON 事件转换为 SnapshotEvent
 */
function convertEvent(json: any): SnapshotEvent | null {
  switch (json.type) {
    case 'reasoning_text':
      return {
        type: 'reasoning',
        content: json.text || '',
        timestamp: json.timestamp
      }

    case 'tool_call':
      return {
        type: 'tool_call',
        content: '',
        toolName: json.tool_name,
        toolCallId: json.tool_call_id,
        args: json.args,
        status: json.status,
        timestamp: json.started_at
      }

    case 'tool_result':
      // 兼容两种格式：
      // 1. JSONL 文件: { type: "tool_result", result: "<json-string>" }，result 字符串里包含 { output, success }
      // 2. SSE 流: { type: "tool_result", output: "..." }
      let resultContent = ''
      if (typeof json.result === 'string') {
        try {
          const parsed = JSON.parse(json.result)
          resultContent = parsed.output || parsed.result || json.result
        } catch {
          resultContent = json.result
        }
      } else if (json.result && typeof json.result === 'object') {
        resultContent = json.result.output || ''
      } else if (json.output) {
        resultContent = json.output
      }
      return {
        type: 'tool_result',
        content: resultContent,
        toolName: json.tool_name,
        toolCallId: json.tool_call_id,
        status: json.status,
        timestamp: json.ended_at
      }

    case 'assistant_text':
      return {
        type: 'assistant_text',
        content: json.text || '',
        timestamp: json.timestamp
      }

    case 'error_event':
      return {
        type: 'error',
        content: json.error_msg || json.error || '',
        errorType: json.error_type,
        timestamp: json.timestamp
      }

    default:
      return null
  }
}

/**
 * 将事件数组转换为可渲染的 Markdown 内容
 * 思考块折叠显示，工具调用显示状态，最终显示助手文本
 */
export function eventsToRenderableContent(events: SnapshotEvent[]): {
  reasoning: string[]
  tools: Array<{ name: string; status: string; args?: any; output: string }>
  assistantText: string
  errorText: string
} {
  const reasoning: string[] = []
  const tools: Array<{ name: string; status: string; args?: any; output: string }> = []
  let assistantText = ''
  let errorText = ''

  let currentTool: typeof tools[0] | null = null

  for (const event of events) {
    switch (event.type) {
      case 'reasoning':
        reasoning.push(event.content)
        break

      case 'tool_call':
        currentTool = {
          name: event.toolName || 'unknown',
          status: event.status || 'running',
          args: event.args,
          output: ''
        }
        break

      case 'tool_result':
        if (currentTool && currentTool.name === event.toolName) {
          currentTool.status = event.status || 'completed'
          currentTool.output = event.content
          tools.push(currentTool)
          currentTool = null
        } else {
          // 如果没有匹配的 tool_call，直接创建
          tools.push({
            name: event.toolName || 'unknown',
            status: event.status || 'completed',
            output: event.content
          })
        }
        break

      case 'assistant_text':
        assistantText += event.content
        break

      case 'error':
        errorText = event.content
        break
    }
  }

  return {
    reasoning,
    tools,
    assistantText,
    errorText
  }
}

/**
 * 解析原始事件列表（已解析的 JSON objects）为 SnapshotEvent 数组
 */
export function parseSnapshotEventObjects(events: any[]): SnapshotEvent[] {
  return events.map((e) => convertEvent(e)).filter(Boolean) as SnapshotEvent[]
}
