import { ref, onUnmounted } from 'vue'

const BOOT_PING_INTERVAL_MS = 1000
const BOOT_MAX_WAIT_SECONDS = 150
const HEARTBEAT_INTERVAL_MS = 30000
const HEARTBEAT_FAIL_THRESHOLD = 3

export function useBackendBoot(port = 30000) {
  const ready = ref(false)
  const elapsed = ref(0)
  const error = ref<string | null>(null)
  const lostConnection = ref(false)

  let bootTimer: ReturnType<typeof setInterval> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let heartbeatFailCount = 0

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

  function stopBootTimer() {
    if (bootTimer) {
      clearInterval(bootTimer)
      bootTimer = null
    }
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function stop() {
    stopBootTimer()
    stopHeartbeat()
  }

  async function bootTick() {
    if (ready.value) return

    if (await ping()) {
      ready.value = true
      stopBootTimer()
      startHeartbeat()
      return
    }

    elapsed.value += 1
    if (elapsed.value >= BOOT_MAX_WAIT_SECONDS) {
      error.value = `后端在 ${BOOT_MAX_WAIT_SECONDS} 秒内未就绪，请稍后重试`
      stopBootTimer()
    }
  }

  async function heartbeatTick() {
    const ok = await ping()
    if (ok) {
      heartbeatFailCount = 0
      lostConnection.value = false
    } else {
      heartbeatFailCount += 1
      if (heartbeatFailCount >= HEARTBEAT_FAIL_THRESHOLD) {
        lostConnection.value = true
      }
    }
  }

  function startHeartbeat() {
    stopHeartbeat()
    heartbeatFailCount = 0
    lostConnection.value = false
    heartbeatTimer = setInterval(() => void heartbeatTick(), HEARTBEAT_INTERVAL_MS)
  }

  function start() {
    stop()
    error.value = null
    elapsed.value = 0
    ready.value = false
    lostConnection.value = false
    void bootTick()
    bootTimer = setInterval(() => void bootTick(), BOOT_PING_INTERVAL_MS)
  }

  onUnmounted(stop)

  return { ready, elapsed, error, lostConnection, start }
}
