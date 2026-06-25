import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getLatestWorkDir } from '@/api/work_dirs'
import { defaultWorkDir } from '@/utils/paths'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workDir = ref(defaultWorkDir.value)

  function setWorkDir(dir: string) {
    workDir.value = dir?.trim() || defaultWorkDir.value
  }

  async function initWorkDir() {
    try {
      const data = await getLatestWorkDir()
      workDir.value = data.work_dir || defaultWorkDir.value
    } catch {
      workDir.value = defaultWorkDir.value
    }
  }

  function focusConsole() {
    window.dispatchEvent(new CustomEvent('aries:focus-console'))
  }

  return {
    workDir,
    setWorkDir,
    initWorkDir,
    focusConsole,
  }
})
