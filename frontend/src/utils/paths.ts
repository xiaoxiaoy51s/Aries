import { ref } from 'vue'
import { getHomePath } from '@/api/system'

/**
 * 系统路径（从后端获取实际路径，避免前端 fallback 到 /home/user）
 */
export const homePath = ref('')
export const defaultWorkDir = ref('~/.Aries/work_dir')
export const petsDir = ref('~/.Aries/pets')

let _initialized = false

/** 在应用启动时调用，从后端加载实际路径 */
export async function initPaths() {
  if (_initialized) return
  _initialized = true
  try {
    const info = await getHomePath()
    homePath.value = info.home
    defaultWorkDir.value = info.work_dir
    petsDir.value = info.pets_dir
  } catch (e) {
    // fallback：使用 electronAPI 或默认值
    const electronAPI = (window as any).electronAPI
    if (electronAPI?.homePath) {
      homePath.value = electronAPI.homePath
      const sep = homePath.value.includes('\\') ? '\\' : '/'
      defaultWorkDir.value = `${homePath.value}${sep}.Aries${sep}work_dir`
      petsDir.value = `${homePath.value}${sep}.Aries${sep}pets`
    }
  }
}
