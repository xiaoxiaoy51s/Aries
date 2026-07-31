import api from './index'

export async function listSkills() {
  const res = await api.get('/api/skills')
  return res.data?.skills || []
}

export async function getSkill(name) {
  const res = await api.get(`/api/skills/${encodeURIComponent(name)}`)
  return res.data
}

export async function createSkill(payload) {
  const res = await api.post('/api/skills', payload)
  return res.data
}

export async function updateSkill(name, payload) {
  const res = await api.put(`/api/skills/${encodeURIComponent(name)}`, payload)
  return res.data
}

export async function deleteSkill(name) {
  await api.delete(`/api/skills/${encodeURIComponent(name)}`)
}

export async function setSkillMainEnabled(name, enabled) {
  const res = await api.put(`/api/skills/${encodeURIComponent(name)}/main-enabled`, { enabled })
  return res.data
}

export async function uploadSkill(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/api/skills/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return res.data
}
