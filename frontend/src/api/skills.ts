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
  group?: 'personal' | 'system' | 'builtin'
}

export async function listSkills(): Promise<{ skills: SkillItem[]; skillsRoot: string; pluginsSkillsRoot: string }> {
  try {
    const res = await fetch(`${getBaseUrl()}/api/skills`)
    if (!res.ok) return { skills: [], skillsRoot: '', pluginsSkillsRoot: '' }
    const data = await res.json()
    return {
      skills: data.skills || [],
      skillsRoot: data.skills_root || '',
      pluginsSkillsRoot: data.plugins_skills_root || '',
    }
  } catch {
    return { skills: [], skillsRoot: '', pluginsSkillsRoot: '' }
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

export interface UploadSkillResult {
  success: boolean
  folder_name: string
  name: string
  description: string
  path: string
  skill_md_path: string
}

export async function uploadSkillPackage(file: File): Promise<UploadSkillResult> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${getBaseUrl()}/api/skills/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '上传技能失败')
  }
  return res.json()
}
