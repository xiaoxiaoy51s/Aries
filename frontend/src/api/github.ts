import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

// ---------- Types ----------

export interface GithubStatus {
  connected: boolean
  username: string | null
  avatar_url: string | null
  name: string | null
  scope: string[]
  error?: string
}

// ---------- API ----------

/**
 * 获取 GitHub 连接状态
 */
export async function getGithubStatus(): Promise<GithubStatus> {
  const res = await fetch(`${getBaseUrl()}/github/status`)
  if (!res.ok) throw new Error('获取 GitHub 状态失败')
  return res.json()
}

/**
 * 使用 Personal Access Token 连接
 */
export async function connectWithPat(token: string): Promise<{ success: boolean; username: string }> {
  const res = await fetch(`${getBaseUrl()}/github/pat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({}))
    throw new Error(error.detail || 'Token 验证失败')
  }
  return res.json()
}

/**
 * 断开 GitHub 连接
 */
export async function disconnectGithub(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${getBaseUrl()}/github/disconnect`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('断开连接失败')
  return res.json()
}
