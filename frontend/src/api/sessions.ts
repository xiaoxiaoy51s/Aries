import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface ProjectSession {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Project {
  work_dir: string
  name: string
  archived?: boolean
  created_at?: string
  updated_at?: string
  sessions: ProjectSession[]
}

export async function listSessions(limit = 30) {
  const res = await fetch(`${getBaseUrl()}/sessions/?limit=${limit}`)
  if (!res.ok) throw new Error('获取会话列表失败')
  return res.json()
}

export async function listProjects() {
  const res = await fetch(`${getBaseUrl()}/sessions/projects`)
  if (!res.ok) throw new Error('获取项目列表失败')
  return res.json()
}

export async function getSessionMessages(sessionId: string, limit = 100) {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}/messages?limit=${limit}`)
  if (!res.ok) throw new Error('获取消息失败')
  return res.json()
}

export async function getSessionHistory(sessionId: string, limit = 20, userOnly = false) {
  const res = await fetch(
    `${getBaseUrl()}/sessions/${sessionId}/history?limit=${limit}&user_only=${userOnly}`
  )
  if (!res.ok) throw new Error('获取历史失败')
  return res.json()
}

export interface ContextUsageBreakdown {
  system_prompt: number
  tool_definitions: number
  rules: number
  skills: number
  summarized_conversation: number
  conversation: number
}

export interface ContextUsageInfo {
  estimated_tokens: number
  context_window: number
  usage_percent: number
  message_count?: number
  breakdown: ContextUsageBreakdown
  recent_message_count?: number
  memory_count?: number
  reasoning_count?: number
  recent_window_tokens?: number
}

export async function getSessionContextUsage(sessionId: string): Promise<ContextUsageInfo> {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}/context-usage`)
  if (!res.ok) throw new Error('获取上下文使用情况失败')
  return res.json()
}

export interface CompactResult {
  session_id: string
  compacted: boolean
  memory: any
  before: ContextUsageInfo
  after: ContextUsageInfo
}

export async function compactSession(sessionId: string): Promise<CompactResult> {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}/compact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error('压缩会话失败')
  return res.json()
}

export async function deleteSession(sessionId: string) {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除会话失败')
  return res.json()
}

export async function getSession(sessionId: string) {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}`)
  if (!res.ok) throw new Error('获取会话详情失败')
  return res.json()
}

export async function searchMessages(query: string, limit = 30) {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const res = await fetch(`${getBaseUrl()}/sessions/search/messages?${params}`)
  if (!res.ok) throw new Error('搜索消息失败')
  return res.json()
}

export async function updateSessionMeta(
  sessionId: string,
  data: { title?: string; work_dir?: string }
) {
  const res = await fetch(`${getBaseUrl()}/sessions/${sessionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('更新会话元数据失败')
  return res.json()
}
