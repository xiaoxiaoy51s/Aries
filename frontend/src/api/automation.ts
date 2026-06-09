import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export interface ScheduleConfig {
  datetime?: string    // 单次执行的具体日期时间
  time?: string        // 每天执行的时间点，如 "09:00"
  minutes?: number     // 间隔执行的分钟数
}

export interface NotifyConfig {
  webhook_url?: string  // 企业微信/QQ/飞书的 webhook 地址
  secret?: string       // 飞书签名密钥
  url?: string          // 自定义 webhook URL
  method?: string       // 自定义 webhook HTTP 方法
  headers?: Record<string, string>  // 自定义 webhook 请求头
}

export interface ScheduledTask {
  id: number
  title: string
  task_content: string
  schedule_type: 'once' | 'daily' | 'interval'
  schedule_config: ScheduleConfig
  scheduled_at: string
  session_id: string
  notify_type: 'none' | 'wechat' | 'qq' | 'feishu' | 'webhook'
  notify_config: NotifyConfig
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
  scheduled_at: string
  task_content?: string
  session_id?: string
  session_mode?: 'new' | 'bind'
  schedule_type?: 'once' | 'daily' | 'interval'
  schedule_config?: ScheduleConfig
  notify_type?: 'none' | 'wechat' | 'qq' | 'feishu' | 'webhook'
  notify_config?: NotifyConfig
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
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/sessions/list?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
