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

export async function openUrl(url: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/system/open-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '打开网址失败')
  }
  const data = await res.json()
  if (!data.ok) {
    throw new Error(data.error || '打开网址失败')
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

export interface HomePathInfo {
  home: string
  pets_dir: string
  work_dir: string
}

let _homePathCache: HomePathInfo | null = null

export async function getHomePath(): Promise<HomePathInfo> {
  if (_homePathCache) return _homePathCache
  const res = await fetch(`${getBaseUrl()}/system/home-path`)
  if (!res.ok) {
    throw new Error('获取用户目录失败')
  }
  _homePathCache = await res.json()
  return _homePathCache
}
