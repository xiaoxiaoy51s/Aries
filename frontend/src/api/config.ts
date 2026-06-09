import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface ModelItem {
  id: string
  apiKey: string
  baseUrl: string
  model: string
  isActive: boolean
}

export async function getConfig() {
  const res = await fetch(`${getBaseUrl()}/config/`)
  if (!res.ok) throw new Error('获取配置失败')
  return res.json()
}

export async function listModels(): Promise<ModelItem[]> {
  const res = await fetch(`${getBaseUrl()}/config/models`)
  if (!res.ok) throw new Error('获取模型列表失败')
  return res.json()
}

export async function getActiveModel(): Promise<ModelItem> {
  const res = await fetch(`${getBaseUrl()}/config/model`)
  if (!res.ok) throw new Error('获取激活模型失败')
  return res.json()
}

export async function createModel(data: Omit<ModelItem, 'id'> & { id?: string }): Promise<ModelItem> {
  const res = await fetch(`${getBaseUrl()}/config/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('创建模型失败')
  return res.json()
}

export async function updateModelConfig(modelId: string, data: Partial<ModelItem>) {
  const res = await fetch(`${getBaseUrl()}/config/models/${modelId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('更新模型失败')
  return res.json()
}

export async function deleteModel(modelId: string) {
  const res = await fetch(`${getBaseUrl()}/config/models/${modelId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除模型失败')
  return res.json()
}

export async function activateModel(modelId: string) {
  const res = await fetch(`${getBaseUrl()}/config/models/${modelId}/activate`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('激活模型失败')
  return res.json()
}
