import { defineStore } from 'pinia'
import { ref } from 'vue'
import { checkForUpdate, type CheckUpdateResult } from '@/api/update'

export const useUpdateStore = defineStore('update', () => {
  const result = ref<CheckUpdateResult | null>(null)
  const checking = ref(false)
  const checked = ref(false)

  // 自动更新状态（electron-updater，仅打包模式）
  const downloading = ref(false)
  const downloadProgress = ref(0)
  const downloaded = ref(false)
  const updateError = ref<string | null>(null)

  let listenersReady = false

  function initElectronListeners() {
    if (listenersReady) return
    listenersReady = true
    const api = (window as any).electronAPI?.update
    if (!api) return

    api.onProgress((progress: { percent: number }) => {
      downloadProgress.value = Math.round(progress.percent || 0)
    })
    api.onDownloaded(() => {
      downloading.value = false
      downloaded.value = true
    })
    api.onError((msg: string) => {
      downloading.value = false
      updateError.value = msg
    })
  }

  async function check(force = false): Promise<CheckUpdateResult | null> {
    if (checking.value) return result.value
    if (checked.value && !force && result.value) return result.value

    checking.value = true
    updateError.value = null
    initElectronListeners()

    try {
      const api = (window as any).electronAPI?.update
      if (api) {
        // 打包模式：使用 electron-updater
        const res = await api.check()
        if (res.isDev) {
          // 开发模式：回退到后端 API
          result.value = await checkForUpdate()
        } else if (res.available) {
          const notes = typeof res.releaseNotes === 'string'
            ? res.releaseNotes
            : Array.isArray(res.releaseNotes)
              ? res.releaseNotes.map((n: any) => typeof n === 'string' ? n : n.note).join('\n')
              : null
          result.value = {
            current_version: '',
            github_repo: 'xiaoxiaoy51s/Aries',
            latest_version: res.version,
            update_available: true,
            release_name: res.releaseName,
            release_url: `https://github.com/xiaoxiaoy51s/Aries/releases/tag/v${res.version}`,
            release_notes: notes,
            published_at: res.releaseDate,
            error: null,
          }
        } else {
          result.value = {
            current_version: '',
            github_repo: 'xiaoxiaoy51s/Aries',
            latest_version: null,
            update_available: false,
            release_name: null,
            release_url: '',
            release_notes: null,
            published_at: null,
            error: res.error || null,
          }
        }
        checked.value = true
        return result.value
      }

      // 回退：后端 API
      result.value = await checkForUpdate()
      checked.value = true
      return result.value
    } catch {
      return null
    } finally {
      checking.value = false
    }
  }

  function download() {
    const api = (window as any).electronAPI?.update
    if (!api) return
    downloading.value = true
    downloadProgress.value = 0
    updateError.value = null
    api.download()
  }

  function install() {
    (window as any).electronAPI?.update?.install()
  }

  function reset() {
    result.value = null
    checked.value = false
    downloaded.value = false
    downloadProgress.value = 0
    updateError.value = null
  }

  return {
    result,
    checking,
    checked,
    downloading,
    downloadProgress,
    downloaded,
    updateError,
    check,
    download,
    install,
    reset,
  }
})
