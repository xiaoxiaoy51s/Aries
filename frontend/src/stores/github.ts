import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getGithubStatus,
  connectWithPat,
  disconnectGithub,
  type GithubStatus,
} from '@/api/github'

export const useGithubStore = defineStore('github', () => {
  const status = ref<GithubStatus>({
    connected: false,
    username: null,
    avatar_url: null,
    name: null,
    scope: [],
  })
  const loading = ref(false)
  const error = ref('')

  /**
   * 获取 GitHub 连接状态
   */
  async function fetchStatus() {
    try {
      loading.value = true
      error.value = ''
      const data = await getGithubStatus()
      status.value = data
    } catch (e: any) {
      error.value = e.message || '获取 GitHub 状态失败'
    } finally {
      loading.value = false
    }
  }

  /**
   * 使用 PAT 连接
   */
  async function connectWithToken(token: string) {
    try {
      loading.value = true
      error.value = ''
      await connectWithPat(token)
      await fetchStatus()
      return true
    } catch (e: any) {
      error.value = e.message || 'Token 验证失败'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 断开连接
   */
  async function disconnect() {
    try {
      loading.value = true
      error.value = ''
      await disconnectGithub()
      status.value = {
        connected: false,
        username: null,
        avatar_url: null,
        name: null,
        scope: [],
      }
      return true
    } catch (e: any) {
      error.value = e.message || '断开连接失败'
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    status,
    loading,
    error,
    fetchStatus,
    connectWithToken,
    disconnect,
  }
})
