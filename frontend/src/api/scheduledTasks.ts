import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export type TaskType = 'once' | 'recurring'

export interface ScheduledTask {
  id: number
  title: string
  task_content: string
  scheduled_at: string
  session_id: string
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'failed'
  task_type: TaskType
  interval_seconds: number | null
  created_at: string
  updated_at: string
  executed_at: string
}

export interface ListTasksResponse {
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
  task_type?: TaskType
  interval_seconds?: number
}

export async function listTasks(
  page = 1,
  pageSize = 20,
): Promise<ListTasksResponse> {
  const res = await fetch(
    `${getBaseUrl()}/scheduled-tasks/?page=${page}&page_size=${pageSize}`,
  )
  if (!res.ok) throw new Error('获取定时任务列表失败')
  return res.json()
}

export async function getTask(taskId: number): Promise<ScheduledTask> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/${taskId}`)
  if (!res.ok) throw new Error('获取任务详情失败')
  return res.json()
}

export async function createTask(
  params: CreateTaskParams,
): Promise<{ success: boolean; task_id: number }> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error('创建定时任务失败')
  return res.json()
}

export async function cancelTask(taskId: number): Promise<{ success: boolean }> {
  const res = await fetch(
    `${getBaseUrl()}/scheduled-tasks/${taskId}/cancel`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error('取消任务失败')
  return res.json()
}

export async function deleteTask(taskId: number): Promise<{ success: boolean }> {
  const res = await fetch(`${getBaseUrl()}/scheduled-tasks/${taskId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除任务失败')
  return res.json()
}
