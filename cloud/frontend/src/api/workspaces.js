import api from './index'

export function listWorkspaces() {
  return api.get('/api/workspaces')
}

export function createWorkspace(name) {
  return api.post('/api/workspaces', { name })
}

export function listWorkspaceFiles(workspaceName, path = '') {
  return api.get(`/api/workspaces/${encodeURIComponent(workspaceName)}/files`, {
    params: { path },
  })
}

export function uploadToWorkspace(workspaceName, file, path = '') {
  const form = new FormData()
  form.append('file', file)
  return api.post(
    `/api/workspaces/${encodeURIComponent(workspaceName)}/files`,
    form,
    { params: { path }, headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export function createWorkspaceEntry(workspaceName, path, isDir) {
  return api.post(`/api/workspaces/${encodeURIComponent(workspaceName)}/files/create`, {
    path,
    is_dir: isDir,
  })
}

export function downloadWorkspaceFile(workspaceName, path) {
  return `/api/workspaces/${encodeURIComponent(workspaceName)}/files/download?path=${encodeURIComponent(path)}`
}

export function readWorkspaceFile(workspaceName, path) {
  return api.get(`/api/workspaces/${encodeURIComponent(workspaceName)}/files/read`, {
    params: { path },
  })
}

export function saveWorkspaceFileContent(workspaceName, path, content) {
  return api.put(`/api/workspaces/${encodeURIComponent(workspaceName)}/files/content`, {
    path,
    content,
  })
}

export function deleteWorkspaceFile(workspaceName, path) {
  return api.delete(`/api/workspaces/${encodeURIComponent(workspaceName)}/files`, {
    params: { path },
  })
}

export function renameWorkspaceFile(workspaceName, path, newName) {
  return api.put(`/api/workspaces/${encodeURIComponent(workspaceName)}/files/rename`, {
    path,
    new_name: newName,
  })
}

export function listUploads() {
  return api.get('/api/upload')
}

export function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function downloadUpload(path) {
  return `/api/upload/download?path=${encodeURIComponent(path)}`
}

export function setSessionWorkspace(sessionId, workspaceDir) {
  return api.put(`/api/chat/sessions/${sessionId}/workspace`, {
    workspace_dir: workspaceDir,
  })
}

export function renameWorkspace(workspaceName, newName) {
  return api.put(`/api/workspaces/${encodeURIComponent(workspaceName)}/rename`, {
    new_name: newName,
  })
}

export function deleteWorkspace(workspaceName) {
  return api.delete(`/api/workspaces/${encodeURIComponent(workspaceName)}`)
}
