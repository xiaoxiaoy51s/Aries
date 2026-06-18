import { defineStore } from 'pinia'
import { ref } from 'vue'

const DEFAULT_WORK_DIR = '~/.Aries/work_dir'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workDir = ref(DEFAULT_WORK_DIR)

  function setWorkDir(dir: string) {
    workDir.value = dir?.trim() || DEFAULT_WORK_DIR
  }

  function focusConsole() {
    window.dispatchEvent(new CustomEvent('aries:focus-console'))
  }

  return {
    workDir,
    setWorkDir,
    focusConsole,
  }
})
