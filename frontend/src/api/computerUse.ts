/**
 * Computer Use API - Stub
 */
export interface ComputerUseStreamEvent {
  type: 'computer_use_log' | 'screenshot' | 'action' | 'done' | 'error'
  data?: any
  meta?: { session_id?: string }
}

export interface SlashCommandDef {
  id: string
  label: string
}

export function streamComputerUse(
  _objective: string,
  _workDir: string,
  _signal?: AbortSignal
): AsyncGenerator<ComputerUseStreamEvent> {
  async function* gen() {
    // stub - 不实际执行
  }
  return gen()
}

export async function stopComputerUse(): Promise<void> {
  // stub
}

export function parseComputerUseCommand(_text: string): string | null {
  return null
}

export function buildComputerUseUserDisplay(_objective: string): string {
  return ''
}

export function parseUserSlashMessage(_content: string): SlashCommandDef | null {
  return null
}

export function isComputerUseLogLine(_line: string): boolean {
  return false
}

export function messageHasComputerUseLogs(_msg: any): boolean {
  return false
}

export function buildWorkBlocksFromReasoning(
  _reasoningParts: string[],
  _workBlocks: any[]
): any[] {
  return []
}

export function splitComputerUseReasoningSegments(_reasoning: string): string[] {
  return []
}
