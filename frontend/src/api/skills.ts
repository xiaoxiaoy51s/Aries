export interface SkillItem {
  name: string
  description: string
  folder_name: string
  path: string
  skill_md_path: string
  enabled: boolean
}

export async function listSkills(): Promise<SkillItem[]> {
  try {
    const res = await fetch('/api/skills')
    if (!res.ok) return []
    const data = await res.json()
    return data.skills || []
  } catch {
    return []
  }
}

export async function updateSkillStatus(folder_name: string, enabled: boolean): Promise<void> {
  try {
    await fetch(`/api/skills/${folder_name}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
  } catch (e) {
    console.error('updateSkillStatus error', e)
  }
}
