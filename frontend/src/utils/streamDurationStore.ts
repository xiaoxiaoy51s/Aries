/**
 * 流式输出时长：按 sessionId + messageId 记录，组件卸载或切换目录后仍可持续计时。
 */
import { ref } from 'vue'

const PENDING_SUFFIX = '__pending__'

const activeStarts = new Map<string, number>()
const frozenMs = new Map<string, number>()

/** 供 computed 订阅，驱动 UI 每 200ms 刷新 */
export const streamDurationTick = ref(0)

let globalTimer: ReturnType<typeof setInterval> | null = null

function makeKey(sessionId: string, messageId: number | string): string {
  return `${sessionId}:${messageId}`
}

function ensureGlobalTicker() {
  if (globalTimer) return
  globalTimer = setInterval(() => {
    if (activeStarts.size === 0) {
      if (globalTimer) {
        clearInterval(globalTimer)
        globalTimer = null
      }
      return
    }
    streamDurationTick.value++
  }, 200)
}

/** 开始计时（若已在计时不重置起点） */
export function startStreamDuration(sessionId: string, messageId: number | string): void {
  if (!sessionId) return
  const key = makeKey(sessionId, messageId)
  if (frozenMs.has(key)) return
  if (!activeStarts.has(key)) {
    activeStarts.set(key, Date.now())
    ensureGlobalTicker()
  }
}

/** 将 __pending__ 计时绑定到真实 messageId（发送后 log_started 到达时） */
export function bindStreamDuration(sessionId: string, messageId: number | string): void {
  if (!sessionId || !messageId) return
  const pendingKey = makeKey(sessionId, PENDING_SUFFIX)
  const msgKey = makeKey(sessionId, messageId)
  const pendingStart = activeStarts.get(pendingKey)
  if (pendingStart !== undefined && !activeStarts.has(msgKey) && !frozenMs.has(msgKey)) {
    activeStarts.set(msgKey, pendingStart)
    activeStarts.delete(pendingKey)
  }
}

/** 结束计时并冻结时长 */
export function freezeStreamDuration(sessionId: string, messageId: number | string): void {
  if (!sessionId) return
  const key = makeKey(sessionId, messageId)
  const start = activeStarts.get(key)
  if (start !== undefined) {
    frozenMs.set(key, Date.now() - start)
    activeStarts.delete(key)
  }
}

/** 结束流式：冻结 messageId 与 pending 占位 */
export function stopStreamDuration(sessionId: string, messageId?: number | string): void {
  if (!sessionId) return
  if (messageId) freezeStreamDuration(sessionId, messageId)
  freezeStreamDuration(sessionId, PENDING_SUFFIX)
}

/** 获取当前或已冻结的毫秒数 */
export function getStreamDurationMs(sessionId: string, messageId: number | string): number {
  if (!sessionId) return 0
  const key = makeKey(sessionId, messageId)
  const frozen = frozenMs.get(key)
  if (frozen !== undefined) return frozen
  const start = activeStarts.get(key)
  if (start !== undefined) return Date.now() - start
  return 0
}

/** 新对话时清理该 session 的计时缓存 */
export function clearSessionStreamDurations(sessionId: string): void {
  if (!sessionId) return
  const prefix = `${sessionId}:`
  for (const key of [...activeStarts.keys(), ...frozenMs.keys()]) {
    if (key.startsWith(prefix)) {
      activeStarts.delete(key)
      frozenMs.delete(key)
    }
  }
}
