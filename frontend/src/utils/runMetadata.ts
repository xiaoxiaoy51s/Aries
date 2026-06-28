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
      cached_tokens?: number
      estimated?: boolean
      from_api?: boolean
    }
    prompt_cache?: {
      enabled?: boolean
      fingerprint?: string
      cached_tokens?: number
      cache_hit_rate_percent?: number
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
  const cached =
    Number(apiObj.cached_tokens ?? tokenUsage.cached_tokens ?? 0) ||
    Number(
      (tokenUsage.prompt_cache as Record<string, unknown> | undefined)?.cached_tokens ?? 0,
    ) ||
    0

  const api_usage =
    prompt || completion || total || cached
      ? {
          prompt_tokens: prompt,
          completion_tokens: completion,
          total_tokens: total || prompt + completion,
          ...(cached ? { cached_tokens: cached } : {}),
          ...(apiObj.estimated === true ? { estimated: true } : {}),
          ...(apiObj.from_api === true ? { from_api: true } : {}),
        }
      : undefined

  const prompt_cache_raw = tokenUsage.prompt_cache
  const prompt_cache =
    prompt_cache_raw && typeof prompt_cache_raw === 'object'
      ? (prompt_cache_raw as NonNullable<RunMeta['token_usage']>['prompt_cache'])
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
    api_usage || context || prompt_cache
      ? {
          ...(context ? { context } : {}),
          ...(api_usage ? { api_usage } : {}),
          ...(prompt_cache ? { prompt_cache } : {}),
        }
      : undefined

  return {
    model,
    duration_ms: duration,
    token_usage,
  }
}

/** 合并多次 run_metadata（开头 context 估算 + 结尾 api_usage） */
export function mergeRunMeta(prev: RunMeta | undefined, next: RunMeta): RunMeta {
  if (!prev) return next
  const prevUsage = prev.token_usage
  const nextUsage = next.token_usage
  let token_usage: RunMeta['token_usage']
  if (prevUsage && nextUsage) {
    token_usage = {
      ...prevUsage,
      ...nextUsage,
      context: { ...prevUsage.context, ...nextUsage.context },
      api_usage: { ...prevUsage.api_usage, ...nextUsage.api_usage },
      prompt_cache: { ...prevUsage.prompt_cache, ...nextUsage.prompt_cache },
    }
  } else {
    token_usage = nextUsage || prevUsage
  }
  return {
    model: next.model || prev.model,
    duration_ms: next.duration_ms ?? prev.duration_ms,
    token_usage,
  }
}

function formatCompactNum(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export interface TokenInOutLabels {
  input: string
  output: string
  cache: string
  estimated?: boolean
}

/** 分解为输入/输出标签，供 meta 栏分项展示 */
export function formatTokenInOutLabels(
  tokenUsage: RunMeta['token_usage'] | undefined,
): TokenInOutLabels {
  const empty = { input: '', output: '', cache: '', estimated: false }
  if (!tokenUsage) return empty

  const api = tokenUsage.api_usage
  const ctx = tokenUsage.context
  const fromApi = api?.from_api === true

  let inputTokens = Number(api?.prompt_tokens ?? 0) || 0
  let outputTokens = Number(api?.completion_tokens ?? 0) || 0

  // 无 API 累计数据时才用 context 估算输入
  if (!fromApi && !inputTokens && ctx?.estimated_tokens) {
    inputTokens = Number(ctx.estimated_tokens) || 0
  }

  if (!inputTokens && !outputTokens) {
    const flat = tokenUsage as Record<string, unknown>
    inputTokens = Number(flat.prompt_tokens ?? 0) || 0
    outputTokens = Number(flat.completion_tokens ?? 0) || 0
  }

  const cached = api?.cached_tokens ?? tokenUsage.prompt_cache?.cached_tokens
  const hitRate = tokenUsage.prompt_cache?.cache_hit_rate_percent
  let cache = ''
  if (cached) cache = `⚡${formatCompactNum(cached)}`
  else if (hitRate) cache = `⚡${hitRate}%`

  const approx = api?.estimated === true && !fromApi ? '≈' : ''

  return {
    input: inputTokens ? `${approx}↑${formatCompactNum(inputTokens)}` : '',
    output: outputTokens ? `${approx}↓${formatCompactNum(outputTokens)}` : '',
    cache,
    estimated: api?.estimated === true,
  }
}

/** 合并展示：↑输入 ↓输出 ⚡缓存 */
export function formatTokenUsageLabel(
  tokenUsage: RunMeta['token_usage'] | undefined,
): string {
  const { input, output, cache } = formatTokenInOutLabels(tokenUsage)
  return [input, output, cache].filter(Boolean).join(' ')
}
