/**
 * 流式诊断日志（默认关闭，避免流式时刷屏卡 UI）。
 * 开启：localStorage.setItem('aries:stream-debug', '1') 或 window.ariesStreamDebug.on()
 * 关闭：localStorage.setItem('aries:stream-debug', '0') 或 window.ariesStreamDebug.off()
 */
const DEBUG_KEY = 'aries:stream-debug'

let cachedEnabled: boolean | null = null

export function isStreamDebugEnabled(): boolean {
  if (cachedEnabled !== null) return cachedEnabled
  try {
    cachedEnabled = localStorage.getItem(DEBUG_KEY) === '1'
  } catch {
    cachedEnabled = false
  }
  return cachedEnabled
}

export function setStreamDebugEnabled(enabled: boolean): void {
  cachedEnabled = enabled
  try {
    localStorage.setItem(DEBUG_KEY, enabled ? '1' : '0')
  } catch {
    // ignore
  }
}

export type StreamDiagCategory = 'SSE' | 'State' | 'Event' | 'Resume' | 'Health'

export function streamDiag(
  category: StreamDiagCategory,
  event: string,
  detail?: Record<string, unknown>,
): void {
  if (!isStreamDebugEnabled()) return
  try {
    const ts = new Date().toISOString().slice(11, 23)
    const prefix = `[StreamDiag:${category}] ${ts} ${event}`
    if (detail && Object.keys(detail).length > 0) {
      console.log(prefix, detail)
    } else {
      console.log(prefix)
    }
  } catch {
    // 诊断日志绝不能影响主流程
  }
}
