/** MCP 工具展示：识别 mcp_ 前缀并格式化为 server/tool 显示名。 */

import { listPlugins } from '@/api/plugins'

let cachedServerSlugs: string[] | null = null
let slugsLoadPromise: Promise<void> | null = null

function slug(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_|_$/g, '') || 'tool'
}

export function isMcpTool(toolName?: string): boolean {
  return !!toolName?.startsWith('mcp_')
}

export function setMcpServerSlugs(serverIds: string[]): void {
  cachedServerSlugs = serverIds.map(slug).sort((a, b) => b.length - a.length)
}

export function ensureMcpServerSlugsLoaded(): Promise<void> {
  if (cachedServerSlugs) return Promise.resolve()
  if (slugsLoadPromise) return slugsLoadPromise
  slugsLoadPromise = listPlugins()
    .then(({ plugins }) => {
      setMcpServerSlugs(plugins.map((plugin) => plugin.id))
    })
    .catch(() => {
      setMcpServerSlugs(['computer_use'])
    })
    .finally(() => {
      slugsLoadPromise = null
    })
  return slugsLoadPromise
}

export function formatMcpToolDisplayName(toolName: string): string {
  if (!isMcpTool(toolName)) return toolName

  const rest = toolName.slice(4)
  const slugs = cachedServerSlugs?.length ? cachedServerSlugs : []

  for (const serverSlug of slugs) {
    if (rest === serverSlug) return serverSlug.replace(/_/g, '-')
    if (rest.startsWith(`${serverSlug}_`)) {
      const tool = rest.slice(serverSlug.length + 1)
      return `${serverSlug.replace(/_/g, '-')}/${tool}`
    }
  }

  const idx = rest.indexOf('_')
  if (idx < 0) return rest
  return `${rest.slice(0, idx).replace(/_/g, '-')}/${rest.slice(idx + 1)}`
}
