import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface SubagentItem {
  name: string
  description: string
  model: string
  fallback_model: string
  enabled: boolean
  allowed_skills: string[]
  allowed_mcps: string[]
  available: boolean
  unavailable_reason: string
  system_prompt: string
  config_path: string
}

export interface SubagentPayload {
  name: string
  description?: string
  model?: string
  fallback_model?: string
  enabled?: boolean
  allowed_skills?: string[]
  allowed_mcps?: string[]
  system_prompt?: string
}

export async function listSubagents(): Promise<SubagentItem[]> {
  try {
    const res = await fetch(`${getBaseUrl()}/api/subagents`)
    if (!res.ok) return []
    const data = await res.json()
    return data.subagents || []
  } catch {
    return []
  }
}

export async function getSubagent(name: string): Promise<SubagentItem> {
  const res = await fetch(`${getBaseUrl()}/api/subagents/${encodeURIComponent(name)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '加载智能体详情失败')
  }
  return res.json()
}

export async function createSubagent(payload: SubagentPayload): Promise<SubagentItem> {
  const res = await fetch(`${getBaseUrl()}/api/subagents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '创建智能体失败')
  }
  return res.json()
}

export async function updateSubagent(name: string, payload: SubagentPayload): Promise<SubagentItem> {
  const res = await fetch(`${getBaseUrl()}/api/subagents/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '保存智能体失败')
  }
  return res.json()
}

export async function deleteSubagent(name: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/api/subagents/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '删除智能体失败')
  }
}

export async function updateSubagentStatus(name: string, enabled: boolean): Promise<SubagentItem> {
  const res = await fetch(`${getBaseUrl()}/api/subagents/${encodeURIComponent(name)}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '更新状态失败')
  }
  return res.json()
}
