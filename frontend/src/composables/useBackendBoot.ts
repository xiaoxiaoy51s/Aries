import { ref, onUnmounted } from 'vue'

const BOOT_PING_INTERVAL_MS = 1000

export function useBackendBoot(port = 30000) {
  const ready = ref(false)

  let bootTimer: ReturnType<typeof setInterval> | null = null

  async function pingRenderer(): Promise<boolean> {
    const res = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(2000),
      cache: 'no-store',
      headers: { Connection: 'close' },
    })
    return res.ok
  }

  async function ping(): Promise<boolean> {
    if (window.electronAPI?.probeBackendHealth) {
      try {
        if (await window.electronAPI.probeBackendHealth()) return true
      } catch {
        // fall through to reset + renderer retry
      }
      await window.electronAPI.resetBackendConnections?.().catch(() => false)
    }
    try {
      return await pingRenderer()
    } catch {
      return false
    }
  }

  function stop() {
    if (bootTimer) {
      clearInterval(bootTimer)
      bootTimer = null
    }
  }

  async function bootTick() {
    if (ready.value) return
    if (await ping()) {
      ready.value = true
      stop()
    }
  }

  function start() {
    stop()
    ready.value = false
    void bootTick()
    bootTimer = setInterval(() => void bootTick(), BOOT_PING_INTERVAL_MS)
  }

  /** 主进程清连接池后调用，继续后台探活 */
  function nudge() {
    if (ready.value) return
    void bootTick()
  }

  onUnmounted(stop)

  return { ready, start, nudge }
}
