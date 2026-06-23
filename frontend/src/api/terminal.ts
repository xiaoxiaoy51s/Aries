/**
 * Terminal WebSocket API
 */
import { useModelStore } from '@/stores/model'

export function getTerminalWsUrl(workDir: string, sessionId: string): string {
  const baseUrl = useModelStore().getBaseUrl()
  const wsBase = baseUrl.replace(/^http/, 'ws')
  return `${wsBase}/ws/terminal?work_dir=${encodeURIComponent(workDir)}&session_id=${encodeURIComponent(sessionId)}`
}

export function getAgentSessionId(workDir: string): string {
  return `agent:${workDir}`
}

export async function getTerminalSessionId(invocationId: string): Promise<string | null> {
  const baseUrl = useModelStore().getBaseUrl()
  const res = await fetch(`${baseUrl}/terminal/session/${encodeURIComponent(invocationId)}`)
  const data = await res.json()
  return data.session_id || null
}

export async function backgroundTerminalCommand(invocationId: string): Promise<void> {
  const baseUrl = useModelStore().getBaseUrl()
  const res = await fetch(`${baseUrl}/terminal/${encodeURIComponent(invocationId)}/background`, { method: 'POST' })
  if (!res.ok) throw new Error(`后台运行失败：${res.status}`)
}

export async function stopTerminalCommand(invocationId: string): Promise<void> {
  const baseUrl = useModelStore().getBaseUrl()
  const res = await fetch(`${baseUrl}/terminal/${encodeURIComponent(invocationId)}/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(`终止命令失败：${res.status}`)
}

export async function closeTerminalSession(sessionId: string): Promise<void> {
  const baseUrl = useModelStore().getBaseUrl()
  const res = await fetch(`${baseUrl}/terminal/session/${encodeURIComponent(sessionId)}/close`, { method: 'POST' })
  if (!res.ok) throw new Error(`关闭终端失败：${res.status}`)
}
