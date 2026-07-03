/** 将高频 log_event / subagent_log_event 合并到同一 animation frame，避免长任务中每个事件都触发整页重渲染 */

export type LogEventBatchItem = {
  event: Record<string, unknown>
  messageId: number
  jsonlPath: string
}

export type SubagentLogBatchItem = {
  data: Record<string, unknown>
}

type LogFlushHandler = (items: LogEventBatchItem[]) => void
type SubagentFlushHandler = (items: SubagentLogBatchItem[]) => void

let pending: LogEventBatchItem[] = []
let subagentPending: SubagentLogBatchItem[] = []
let rafId: number | null = null
let logHandler: LogFlushHandler | null = null
let subagentHandler: SubagentFlushHandler | null = null

export function setLogEventBatchHandler(fn: LogFlushHandler | null) {
  logHandler = fn
}

export function setSubagentLogBatchHandler(fn: SubagentFlushHandler | null) {
  subagentHandler = fn
}

export function enqueueLogEvent(item: LogEventBatchItem) {
  pending.push(item)
  const evt = item.event
  const evtType = typeof evt.type === 'string' ? evt.type : ''
  if (
    evtType === 'error_event'
    || (evtType === 'run_metadata' && evt.final === true)
    || evtType === 'log_complete'
  ) {
    flushLogEventsNow()
    return
  }
  scheduleFlush()
}

export function enqueueSubagentLogEvent(data: Record<string, unknown>) {
  subagentPending.push({ data })
  scheduleFlush()
}

/** 立即刷掉队列（log_complete 等边界事件前调用） */
export function flushLogEventsNow() {
  if (rafId != null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  flushQueues()
}

function flushQueues() {
  const logBatch = pending
  const subagentBatch = subagentPending
  pending = []
  subagentPending = []
  if (logBatch.length && logHandler) logHandler(logBatch)
  if (subagentBatch.length && subagentHandler) subagentHandler(subagentBatch)
}

function scheduleFlush() {
  if (rafId != null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    flushQueues()
  })
}
