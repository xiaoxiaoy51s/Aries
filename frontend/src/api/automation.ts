import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export type PushPlatform = 'wechat' | 'qq' | 'feishu'

export interface ScheduledTask {
  id: number
  title: string
  task_content: string
  schedule_type: 'once' | 'daily' | 'interval'
  scheduled_at: string
  /** 间隔任务专用，单位：分钟 */
  interval_minutes?: number | null
  /** 网页会话 UUID，或 __wechat__ / __qq__ / __feishu__ 表示手机推送 */
  session_id: string
  /** 后端由 session_id 推导，仅用于展示 */
  notify_type?: 'none' | PushPlatform
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'failed'
  created_at: string
  updated_at: string
  executed_at: string | null
}

export interface TaskListResponse {
  tasks: ScheduledTask[]
  total: number
  page: number
  page_size: number
}

export interface CreateTaskParams {
  title: string
  scheduled_at?: string
  task_content?: string
  session_id?: string
  session_mode?: 'new' | 'bind'
  schedule_type?: 'once' | 'daily' | 'interval'
  interval_minutes?: number
}

export interface SessionItem {
  session_id: string
  title: string
  work_dir: string
  created_at: string
  updated_at: string
  last_user_message?: string
}

export async function createScheduledTask(params: CreateTaskParams): Promise<{ success: boolean; task_id: number }> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listScheduledTasks(page = 1, pageSize = 20): Promise<TaskListResponse> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/?page=${page}&page_size=${pageSize}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getScheduledTask(taskId: number): Promise<ScheduledTask> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/${taskId}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function cancelScheduledTask(taskId: number): Promise<{ success: boolean }> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/${taskId}/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function deleteScheduledTask(taskId: number): Promise<{ success: boolean }> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/${taskId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listSessions(limit = 50): Promise<{ sessions: SessionItem[] }> {
  let res = await fetch(`${getBaseUrl()}/sessions/?limit=${limit}`)
  if (res.ok) return res.json()
  res = await fetch(`${getBaseUrl()}/scheduled-tasks/sessions/list?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
