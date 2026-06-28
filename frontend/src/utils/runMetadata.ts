/** 单条 assistant 回复的运行元数据（模型、耗时、token） */

export interface RunMeta {
  model?: string
  duration_ms?: number
  token_usage?: {
    context?: {
      usage_percent?: number
      estimated_tokens?: number
      context_window?: number
      [key: string]: unknown
    }
    api_usage?: {
      prompt_tokens?: number
      completion_tokens?: number
      total_tokens?: number
    }
    [key: string]: unknown
  }
}

/** 将 run_metadata 事件 / SSE meta 统一为前端 MessageMeta 结构 */
export function normalizeRunMetadata(raw: unknown): RunMeta {
  if (!raw || typeof raw !== 'object') return {}

  const obj = raw as Record<string, unknown>
  const base = (
    obj.meta && typeof obj.meta === 'object' ? obj.meta : obj
  ) as Record<string, unknown>

  let tokenUsage: Record<string, unknown> = {}
  const rawUsage = base.token_usage
  if (rawUsage && typeof rawUsage === 'object') {
    tokenUsage = rawUsage as Record<string, unknown>
  } else if (typeof rawUsage === 'string') {
    try {
      const parsed = JSON.parse(rawUsage)
      if (parsed && typeof parsed === 'object') tokenUsage = parsed
    } catch {
      /* ignore */
    }
  }

  const rawApi = tokenUsage.api_usage
  const apiObj =
    rawApi && typeof rawApi === 'object' ? (rawApi as Record<string, unknown>) : {}

  const prompt = Number(apiObj.prompt_tokens ?? tokenUsage.prompt_tokens ?? 0) || 0
  const completion =
    Number(apiObj.completion_tokens ?? tokenUsage.completion_tokens ?? 0) || 0
  const total = Number(apiObj.total_tokens ?? tokenUsage.total_tokens ?? 0) || 0

  const api_usage =
    prompt || completion || total
      ? {
          prompt_tokens: prompt,
          completion_tokens: completion,
          total_tokens: total || prompt + completion,
        }
      : undefined

  const context =
    tokenUsage.context && typeof tokenUsage.context === 'object'
      ? (tokenUsage.context as NonNullable<RunMeta['token_usage']>['context'])
      : undefined

  const duration =
    typeof base.duration_ms === 'number'
      ? base.duration_ms
      : Number(base.duration_ms) || undefined

  const model = typeof base.model === 'string' && base.model ? base.model : undefined

  const token_usage =
    api_usage || context
      ? {
          ...(context ? { context } : {}),
          ...(api_usage ? { api_usage } : {}),
        }
      : undefined

  return {
    model,
    duration_ms: duration,
    token_usage,
  }
}

/** 从 token_usage 提取可展示的输入/输出 token 文案 */
export function formatTokenUsageLabel(
  tokenUsage: RunMeta['token_usage'] | undefined,
): string {
  if (!tokenUsage) return ''

  const api = tokenUsage.api_usage
  if (api) {
    const parts: string[] = []
    if (api.prompt_tokens) parts.push(`↑${formatCompactNum(api.prompt_tokens)}`)
    if (api.completion_tokens) parts.push(`↓${formatCompactNum(api.completion_tokens)}`)
    if (parts.length) return parts.join(' ')
    if (api.total_tokens) return `${formatCompactNum(api.total_tokens)} tok`
  }

  const flat = tokenUsage as Record<string, unknown>
  const prompt = Number(flat.prompt_tokens ?? 0) || 0
  const completion = Number(flat.completion_tokens ?? 0) || 0
  const parts: string[] = []
  if (prompt) parts.push(`↑${formatCompactNum(prompt)}`)
  if (completion) parts.push(`↓${formatCompactNum(completion)}`)
  return parts.join(' ')
}

function formatCompactNum(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}
