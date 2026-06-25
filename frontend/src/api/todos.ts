import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface Todo {
  id: string
  content: string
  priority: 'high' | 'medium' | 'low'
  status: 'pending' | 'in_progress' | 'completed'
}

export async function getTodos(sessionId: string): Promise<Todo[]> {
  const res = await fetch(`${getBaseUrl()}/chat/todos/${encodeURIComponent(sessionId)}`)
  if (!res.ok) {
    throw new Error('获取任务清单失败')
  }
  const data = await res.json()
  return (data.todos || []) as Todo[]
}

export async function clearTodos(sessionId: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/chat/clear-todos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
  if (!res.ok) {
    throw new Error('清除任务清单失败')
  }
}
