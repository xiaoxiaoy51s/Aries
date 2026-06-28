import { defineStore } from 'pinia'
import { ref } from 'vue'
import { checkForUpdate, type CheckUpdateResult } from '@/api/update'

export const useUpdateStore = defineStore('update', () => {
  const result = ref<CheckUpdateResult | null>(null)
  const checking = ref(false)
  const checked = ref(false)

  async function check(force = false): Promise<CheckUpdateResult | null> {
    if (checking.value) return result.value
    if (checked.value && !force && result.value) return result.value

    checking.value = true
    try {
      result.value = await checkForUpdate()
      checked.value = true
      return result.value
    } catch {
      return null
    } finally {
      checking.value = false
    }
  }

  function reset() {
    result.value = null
    checked.value = false
  }

  return {
    result,
    checking,
    checked,
    check,
    reset,
  }
})
