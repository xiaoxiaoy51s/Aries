import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface PluginItem {
  id: string
  name: string
  description: string
  transport?: string
  command?: string
  status?: string
  tool_count?: number
  last_error?: string
}

export async function listPlugins(): Promise<{
  plugins: PluginItem[]
  configPath: string
  cacheRoot: string
}> {
  try {
    const res = await fetch(`${getBaseUrl()}/api/plugins`)
    if (!res.ok) return { plugins: [], configPath: '', cacheRoot: '' }
    const data = await res.json()
    return {
      plugins: data.plugins || [],
      configPath: data.config_path || '',
      cacheRoot: data.cache_root || '',
    }
  } catch {
    return { plugins: [], configPath: '', cacheRoot: '' }
  }
}

export async function refreshPlugins(): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/api/plugins/refresh`, { method: 'POST' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '刷新 MCP 连接失败')
  }
}

export async function importPlugins(configJson: string): Promise<string[]> {
  const res = await fetch(`${getBaseUrl()}/api/plugins/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_json: configJson }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '导入 MCP 配置失败')
  }
  const data = await res.json()
  return data.added || []
}

export interface PluginDetail {
  id: string
  name: string
  description: string
  config_path: string
  server_config: Record<string, unknown>
  config_json: string
  status?: string
  tool_count?: number
  last_error?: string
}

export async function getPluginDetail(id: string): Promise<PluginDetail> {
  const res = await fetch(`${getBaseUrl()}/api/plugins/${encodeURIComponent(id)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '加载插件详情失败')
  }
  return res.json()
}