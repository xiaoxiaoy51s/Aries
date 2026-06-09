import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listPlatforms,
  togglePlatform as apiToggle,
  unbindQQ,
  unbindWeChat,
  unbindFeishu,
  type PlatformStatus,
} from '@/api/platform'

export const useAccountStore = defineStore('account', () => {
  const accounts = ref<PlatformStatus[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchAccounts() {
    try {
      loading.value = true
      error.value = ''
      const data = await listPlatforms()
      accounts.value = data.platforms
    } catch (e: any) {
      error.value = e.message || '获取平台列表失败'
    } finally {
      loading.value = false
    }
  }

  async function togglePlatform(platform: string) {
    try {
      await apiToggle(platform)
      await fetchAccounts()
    } catch (e: any) {
      error.value = e.message || '切换平台状态失败'
    }
  }

  async function unbind(platform: string) {
    try {
      if (platform === 'qq') await unbindQQ()
      else if (platform === 'wechat') await unbindWeChat()
      else if (platform === 'feishu') await unbindFeishu()
      await fetchAccounts()
    } catch (e: any) {
      error.value = e.message || '解绑失败'
    }
  }

  return {
    accounts,
    loading,
    error,
    fetchAccounts,
    togglePlatform,
    unbind,
  }
})
