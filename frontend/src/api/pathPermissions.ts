import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface PathPermission {
  id: number
  path: string
  type: 'whitelist' | 'blacklist'
  created_at: string
}

export async function listPathPermissions() {
  const res = await fetch(`${getBaseUrl()}/path-permissions/`)
  if (!res.ok) throw new Error('获取路径权限列表失败')
  return res.json() as Promise<{ permissions: PathPermission[] }>
}

export async function addPathPermission(path: string, type: 'whitelist' | 'blacklist') {
  const res = await fetch(`${getBaseUrl()}/path-permissions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, type }),
  })
  if (!res.ok) throw new Error('添加路径权限失败')
  return res.json()
}

export async function removePathPermission(path: string) {
  const res = await fetch(`${getBaseUrl()}/path-permissions/${encodeURIComponent(path)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除路径权限失败')
  return res.json()
}