/** 解析工具结果 JSON，供 ToolBlock 展示（剥离 base64，保留路径/预览）。 */

export interface ParsedToolResult {
  displayText: string
  screenshotPreview?: string
  screenshotPath?: string
  width?: number
  height?: number
}

const SCREENSHOT_TOOLS = new Set([
  'computer_screenshot',
  'sky_get_window_state',
])

const SCREENSHOT_TOOL_SUFFIXES = [
  'get_window_state',
  'screenshot',
]

export function isScreenshotTool(toolName?: string): boolean {
  if (!toolName) return false
  if (SCREENSHOT_TOOLS.has(toolName)) return true
  if (toolName.startsWith('mcp_')) {
    return SCREENSHOT_TOOL_SUFFIXES.some((suffix) => toolName.endsWith(`_${suffix}`) || toolName.endsWith(suffix))
  }
  return false
}

function stripBase64Fields(obj: Record<string, unknown>): Record<string, unknown> {
  const slim: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (k === 'image_base64' || k === 'screenshot_preview') continue
    if (k === 'screenshots' && Array.isArray(v)) {
      slim[k] = v.map((shot) => {
        if (!shot || typeof shot !== 'object') return shot
        const s = { ...(shot as Record<string, unknown>) }
        delete s.url
        return s
      })
      continue
    }
    slim[k] = v
  }
  return slim
}

export function parseToolResultForDisplay(
  raw: string | undefined,
  toolName?: string,
  screenshotPreviewFromEvent?: string,
): ParsedToolResult {
  const fallback: ParsedToolResult = { displayText: raw || '' }
  if (!raw || typeof raw !== 'string') {
    if (screenshotPreviewFromEvent) {
      fallback.screenshotPreview = screenshotPreviewFromEvent
    }
    return fallback
  }

  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) {
    return {
      displayText: trimmed,
      screenshotPreview: screenshotPreviewFromEvent,
    }
  }

  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>
    const preview =
      screenshotPreviewFromEvent ||
      (typeof parsed.screenshot_preview === 'string' ? parsed.screenshot_preview : undefined)
    const path =
      typeof parsed.screenshot_path === 'string'
        ? parsed.screenshot_path
        : typeof parsed.path === 'string'
          ? parsed.path
          : undefined
    const width = typeof parsed.width === 'number' ? parsed.width : undefined
    const height = typeof parsed.height === 'number' ? parsed.height : undefined

    let displayText = ''
    if (typeof parsed.output === 'string' && parsed.output.trim()) {
      displayText = parsed.output.trim()
    } else if (isScreenshotTool(toolName) && path) {
      displayText = `截图已保存 (${width ?? '?'}x${height ?? '?'})`
    } else {
      displayText = JSON.stringify(stripBase64Fields(parsed), null, 2)
    }

    if (path) {
      displayText = `${displayText}\n路径: ${path}`
    }

    return {
      displayText,
      screenshotPreview: preview,
      screenshotPath: path,
      width,
      height,
    }
  } catch {
    return {
      displayText: trimmed,
      screenshotPreview: screenshotPreviewFromEvent,
    }
  }
}
