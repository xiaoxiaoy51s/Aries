import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface SkillItem {
  name: string
  description: string
  folder_name: string
  path: string
  skill_md_path: string
  enabled: boolean
  group?: 'personal' | 'system'
}

export async function listSkills(): Promise<SkillItem[]> {
  try {
    const res = await fetch(`${getBaseUrl()}/api/skills`)
    if (!res.ok) return []
    const data = await res.json()
    return data.skills || []
  } catch {
    return []
  }
}

export async function updateSkillStatus(folder_name: string, enabled: boolean): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/api/skills/${encodeURIComponent(folder_name)}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '更新技能状态失败')
  }
}

export interface SkillDetail {
  folder_name: string
  name: string
  description: string
  enabled: boolean
  skill_path: string
  skill_md_path: string
  content: string
}

export async function getSkillDetail(folder_name: string): Promise<SkillDetail> {
  const res = await fetch(`${getBaseUrl()}/api/skills/${encodeURIComponent(folder_name)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '加载技能详情失败')
  }
  return res.json()
}
