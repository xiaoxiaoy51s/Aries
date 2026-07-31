import api from './index'

// 全局记忆
export const getGlobalMemory = () => api.get('/api/memory/global')
export const saveGlobalMemory = (content) => api.post('/api/memory/global', { content })

// 项目记忆列表
export const listProjectMemories = () => api.get('/api/memory/projects')

// 项目记忆读写
export const getProjectMemory = (workspaceName) =>
  api.get(`/api/memory/project/${encodeURIComponent(workspaceName)}`)

export const saveProjectMemory = (workspaceName, content) =>
  api.post(`/api/memory/project/${encodeURIComponent(workspaceName)}`, { content })
