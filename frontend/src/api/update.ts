import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export interface AppVersionInfo {
  version: string
  github_repo: string
}

export interface CheckUpdateResult {
  current_version: string
  github_repo: string
  latest_version: string | null
  update_available: boolean
  release_name: string | null
  release_url: string
  release_notes: string | null
  published_at: string | null
  error: string | null
}

export async function getAppVersion(): Promise<AppVersionInfo> {
  const res = await fetch(`${getBaseUrl()}/system/version`)
  if (!res.ok) {
    throw new Error('获取版本信息失败')
  }
  return res.json()
}

export async function checkForUpdate(): Promise<CheckUpdateResult> {
  const res = await fetch(`${getBaseUrl()}/system/check-update`)
  if (!res.ok) {
    throw new Error('检查更新失败')
  }
  return res.json()
}
