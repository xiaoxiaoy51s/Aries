import api from './index'

export async function listSubagents() {
  const res = await api.get('/api/subagents')
  return res.data?.subagents || []
}

export async function getSubagent(name) {
  const res = await api.get(`/api/subagents/${encodeURIComponent(name)}`)
  return res.data
}

export async function createSubagent(payload) {
  const res = await api.post('/api/subagents', payload)
  return res.data
}

export async function updateSubagent(name, payload) {
  const res = await api.put(`/api/subagents/${encodeURIComponent(name)}`, payload)
  return res.data
}

export async function deleteSubagent(name) {
  await api.delete(`/api/subagents/${encodeURIComponent(name)}`)
}

export async function setMainEnabled(name, enabled) {
  const res = await api.put(`/api/subagents/${encodeURIComponent(name)}/main-enabled`, { enabled })
  return res.data
}

export async function getAgentsConfig() {
  const res = await api.get('/api/subagents/config')
  return res.data
}
