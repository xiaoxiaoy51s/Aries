import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workDir = ref('')

  function setWorkDir(dir: string) {
    workDir.value = dir
  }

  function focusConsole() {
    window.dispatchEvent(new CustomEvent('mimo:focus-console'))
  }

  return {
    workDir,
    setWorkDir,
    focusConsole,
  }
})
