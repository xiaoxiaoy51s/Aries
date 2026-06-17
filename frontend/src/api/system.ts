import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export async function openPath(path: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/system/open-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '打开路径失败')
  }
  const data = await res.json()
  if (!data.ok) {
    throw new Error(data.error || '打开路径失败')
  }
}

export interface SelectDirectoryResult {
  path: string | null
  cancelled: boolean
  error: string | null
}

export async function selectDirectory(): Promise<SelectDirectoryResult> {
  const res = await fetch(`${getBaseUrl()}/system/select-directory`, {
    method: 'POST',
  })
  if (!res.ok) {
    throw new Error('选择目录失败')
  }
  return res.json()
}
