import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface WorkDir {
  work_dir: string
  name: string
  archived: boolean
  created_at: string
  updated_at: string
}

export async function listWorkDirs(includeArchived = false) {
  const res = await fetch(`${getBaseUrl()}/work-dirs/?include_archived=${includeArchived}`)
  if (!res.ok) throw new Error('获取工作目录列表失败')
  return res.json()
}

export async function getLatestWorkDir() {
  const res = await fetch(`${getBaseUrl()}/work-dirs/latest`)
  if (!res.ok) throw new Error('获取最新工作目录失败')
  return res.json()
}

export async function createWorkDir(workDir: string, name?: string) {
  const res = await fetch(`${getBaseUrl()}/work-dirs/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ work_dir: workDir, name }),
  })
  if (!res.ok) throw new Error('创建工作目录失败')
  return res.json()
}

export async function deleteWorkDir(workDir: string) {
  const params = new URLSearchParams({ work_dir: workDir })
  const res = await fetch(`${getBaseUrl()}/work-dirs/?${params}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除工作目录失败')
  return res.json()
}

export async function archiveWorkDir(workDir: string, archived = true) {
  const res = await fetch(`${getBaseUrl()}/work-dirs/archive`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ work_dir: workDir, archived }),
  })
  if (!res.ok) throw new Error('归档工作目录失败')
  return res.json()
}

export async function renameWorkDir(workDir: string, name: string) {
  const res = await fetch(`${getBaseUrl()}/work-dirs/rename`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ work_dir: workDir, name }),
  })
  if (!res.ok) throw new Error('重命名工作目录失败')
  return res.json()
}
