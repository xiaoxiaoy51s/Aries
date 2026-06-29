import { ref, onUnmounted } from 'vue'

const HEALTH_INTERVAL_MS = 1000
const MAX_WAIT_SECONDS = 150

export function useBackendBoot(port = 30000) {
  const ready = ref(false)
  const elapsed = ref(0)
  const error = ref<string | null>(null)

  let timer: ReturnType<typeof setInterval> | null = null

  async function ping(): Promise<boolean> {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/health`, {
        signal: AbortSignal.timeout(2000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  async function tick() {
    if (ready.value) return

    if (await ping()) {
      ready.value = true
      stop()
      return
    }

    elapsed.value += 1
    if (elapsed.value >= MAX_WAIT_SECONDS) {
      error.value = `后端在 ${MAX_WAIT_SECONDS} 秒内未就绪，请稍后重试`
      stop()
    }
  }

  function start() {
    stop()
    error.value = null
    elapsed.value = 0
    ready.value = false
    void tick()
    timer = setInterval(() => void tick(), HEALTH_INTERVAL_MS)
  }

  onUnmounted(stop)

  return { ready, elapsed, error, start }
}
