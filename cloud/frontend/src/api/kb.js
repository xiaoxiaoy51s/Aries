import api from './index'

export function listKbPages(type) {
  return api.get('/api/kb/pages', { params: type ? { type } : {} })
}

export function getKbPage(path) {
  return api.get('/api/kb/page', { params: { path } })
}

export function deleteKbPage(file_path) {
  return api.delete('/api/kb/pages', { data: { file_path } })
}

export function moveKbPage(path, newPath, newTitle) {
  return api.post('/api/kb/move', { path, new_path: newPath, new_title: newTitle || null })
}

export function deleteKbFolder(dirPath) {
  return api.post('/api/kb/folder/delete', { path: dirPath })
}

export function ingestText(text, meta = {}) {
  return api.post('/api/kb/ingest', { text, ...meta })
}

export function ingestFile(file, sourceLabel) {
  const fd = new FormData()
  fd.append('file', file)
  if (sourceLabel) fd.append('source_label', sourceLabel)
  return api.post('/api/kb/ingest/file', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function chatWithKb(question) {
  return api.post('/api/kb/chat', { question })
}

export function exportZip() {
  return `/api/kb/export`
}

export function getJobs(page = 1, pageSize = 20) {
  return api.get('/api/kb/jobs', { params: { page, page_size: pageSize } })
}

export function getRawFileUrl(file_path) {
  return `/api/kb/raw/${encodeURIComponent(file_path)}`
}

// 外链图片/视频代理（绕过微信 mmbiz 防盗链水印），仅支持白名单图床域名
export function imageProxyUrl(url) {
  return `/api/kb/image_proxy?url=${encodeURIComponent(url)}`
}
