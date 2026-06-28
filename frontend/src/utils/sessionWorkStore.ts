/** 全局：哪些 session 正在流式工作（侧边栏 loading + 多会话 WS 保活） */
import { ref } from 'vue'

export const MAX_CONCURRENT_WORKING_SESSIONS = 3

const _workingIds = ref<Set<string>>(new Set())

export const workingSessionIds = _workingIds

export function isSessionWorking(sessionId: string | null | undefined): boolean {
  if (!sessionId) return false
  return _workingIds.value.has(sessionId)
}

export function markSessionWorking(sessionId: string | null | undefined): void {
  if (!sessionId) return
  if (_workingIds.value.has(sessionId)) return
  const next = new Set(_workingIds.value)
  next.add(sessionId)
  _workingIds.value = next
}

export function markSessionIdle(sessionId: string | null | undefined): void {
  if (!sessionId) return
  if (!_workingIds.value.has(sessionId)) return
  const next = new Set(_workingIds.value)
  next.delete(sessionId)
  _workingIds.value = next
}

export function workingSessionCount(): number {
  return _workingIds.value.size
}
