import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  listModels,
  getActiveModel,
  createModel,
  updateModelConfig,
  deleteModel as deleteModelApi,
  activateModel as activateModelApi,
  type ModelItem as ApiModelItem,
} from '@/api/config'

// 前端展示用的模型项（含 name 展示字段）
export interface ModelItem {
  id: string
  name: string
  apiKey: string
  baseUrl: string
  model: string
  isActive: boolean
}

// 把 API 返回的模型项转为前端展示项
function toViewModel(m: ApiModelItem): ModelItem {
  return {
    id: m.id,
    name: m.model,
    apiKey: m.apiKey,
    baseUrl: m.baseUrl,
    model: m.model,
    isActive: m.isActive,
  }
}

export const useModelStore = defineStore('model', () => {
  // State
  const models = ref<ModelItem[]>([])
  const backendPort = ref(30000)

  // Getters
  const activeModel = computed(() => models.value.find(m => m.isActive) || models.value[0])
  const modelList = computed(() => models.value)

  // Actions
  function setBackendPort(port: number) {
    backendPort.value = port
  }

  function getBaseUrl() {
    return `http://127.0.0.1:${backendPort.value}`
  }

  async function loadModels() {
    try {
      const data = await listModels()
      models.value = (data || []).map(toViewModel)
      // 兜底：如果后端没返回激活模型，调用 getActiveModel 获取
      if (models.value.length > 0 && !models.value.some(m => m.isActive)) {
        try {
          const active = await getActiveModel()
          if (active && active.id) {
            models.value = models.value.map(m => ({ ...m, isActive: m.id === active.id }))
          }
        } catch { /* ignore */ }
      }
    } catch (e) {
      console.error('加载模型列表失败', e)
      models.value = []
    }
  }

  async function addModel(model: Omit<ModelItem, 'id'>) {
    try {
      const created = await createModel({
        apiKey: model.apiKey,
        baseUrl: model.baseUrl,
        model: model.model,
        isActive: model.isActive,
      })
      await loadModels()
      return created.id
    } catch (e) {
      console.error('新增模型失败', e)
      throw e
    }
  }

  async function updateModel(id: string, updates: Partial<ModelItem>) {
    try {
      await updateModelConfig(id, {
        apiKey: updates.apiKey,
        baseUrl: updates.baseUrl,
        model: updates.model,
        isActive: updates.isActive,
      })
      await loadModels()
      return true
    } catch (e) {
      console.error('更新模型失败', e)
      return false
    }
  }

  async function deleteModel(id: string) {
    try {
      await deleteModelApi(id)
      await loadModels()
      return true
    } catch (e) {
      console.error('删除模型失败', e)
      return false
    }
  }

  async function setActiveModel(id: string) {
    try {
      await activateModelApi(id)
      // 本地立即更新激活状态
      models.value = models.value.map(m => ({ ...m, isActive: m.id === id }))
      return true
    } catch (e) {
      console.error('激活模型失败', e)
      return false
    }
  }

  return {
    models,
    backendPort,
    activeModel,
    modelList,
    setBackendPort,
    getBaseUrl,
    loadModels,
    addModel,
    updateModel,
    deleteModel,
    setActiveModel,
  }
})
