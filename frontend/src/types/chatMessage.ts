import type { RunMeta } from '@/utils/runMetadata'

export interface ToolInfo {
  name: string
  status: string
  args?: Record<string, unknown>
  output: string
}

export interface MessageBlock {
  type: 'tool' | 'text' | 'summary'
  phase?: 'work' | 'answer'
  text?: string
  tool_name?: string
  status?: string
  args?: Record<string, unknown>
  preview?: string
  result?: string
  error?: string
  started_at?: string
  ended_at?: string
  tool_call_id?: string
  session_id?: string
  auto_detached?: boolean
  pending_confirmation?: boolean
  danger_info?: string
  danger_types?: string[]
  subagent?: {
    task_id?: string
    subagent?: string
    task?: string
    status?: string
    round?: number
    last_event?: string
    elapsed_ms?: number
    log_path?: string
    inner_blocks?: MessageBlock[]
    final_message?: string
    error?: string
  }
}

export interface MessageMeta {
  model?: string
  duration_ms?: number
  token_usage?: RunMeta['token_usage']
}

export interface FileChangeArtifact {
  file_path: string
  operation: string
  previous_content: string
  new_content: string
  tool_name: string
  tool_call_id: string
  reverted?: boolean
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  slashCommand?: string
  slashBody?: string
  mode?: string
  reasoning?: string[]
  tools?: ToolInfo[]
  blocks?: MessageBlock[]
  artifacts?: FileChangeArtifact[]
  isLoading?: boolean
  messageId?: number
  messageSnapshotJson?: string
  hasSnapshot?: boolean
  meta?: MessageMeta
}

export interface SubagentRecord {
  task_id: string
  subagent?: string
  task?: string
  status?: string
  round?: number
  last_event?: string
  elapsed_ms?: number
  log_path?: string
  inner_blocks?: MessageBlock[]
  final_message?: string
  error?: string
  message_id?: number
}
