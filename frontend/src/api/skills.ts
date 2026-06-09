export interface Skill {
  id: string
  name: string
  description: string
  enabled: boolean
}

export async function listSkills(): Promise<Skill[]> {
  try {
    const res = await fetch('/api/skills')
    if (!res.ok) return []
    const data = await res.json()
    return data.skills || []
  } catch {
    return []
  }
}

export async function updateSkillStatus(id: string, enabled: boolean): Promise<void> {
  try {
    await fetch(`/api/skills/${id}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
  } catch (e) {
    console.error('updateSkillStatus error', e)
  }
}
