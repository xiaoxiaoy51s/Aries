import { getIconForFile, DEFAULT_FILE } from 'vscode-icons-js'

const ICON_CDN = './file-icons'

export const FILE_EDIT_TOOL_NAMES = new Set([
  'edit_file',
  'write_file',
  'apply_patch',
  'multi_replace_string',
])

export type DiffLineType = 'remove' | 'add' | 'context'

export interface DiffPreviewLine {
  type: DiffLineType
  text: string
  /** 行内高亮片段（如 async 关键字变更） */
  highlight?: string
}

export interface FileEditPreviewData {
  filePath: string
  fileName: string
  iconSrc: string
  added: number
  removed: number
  /** 折叠时最多 3 行 */
  lines: DiffPreviewLine[]
  /** 展开时完整 diff */
  allLines: DiffPreviewLine[]
}

export function isFileEditTool(toolName: string): boolean {
  return FILE_EDIT_TOOL_NAMES.has(toolName)
}

function basename(filePath: string): string {
  const normalized = filePath.replace(/\\/g, '/').replace(/\/+$/, '')
  const parts = normalized.split('/')
  return parts[parts.length - 1] || filePath
}

function iconSrcForFile(fileName: string): string {
  const iconName = getIconForFile(fileName) || DEFAULT_FILE
  return `${ICON_CDN}/${iconName}`
}

function countLines(text: string): number {
  if (!text) return 0
  return text.split('\n').length
}

function inlineHighlight(oldLine: string, newLine: string): string | undefined {
  if (!oldLine || oldLine === newLine) return undefined
  let start = 0
  while (start < oldLine.length && start < newLine.length && oldLine[start] === newLine[start]) {
    start++
  }
  let endOld = oldLine.length - 1
  let endNew = newLine.length - 1
  while (endOld >= start && endNew >= start && oldLine[endOld] === newLine[endNew]) {
    endOld--
    endNew--
  }
  const changed = newLine.slice(start, endNew + 1)
  return changed || undefined
}

/** 按行对比 old/new，生成 remove/add/context 序列 */
export function linesDiff(oldText: string, newText: string): DiffPreviewLine[] {
  const oldLines = (oldText ?? '').split('\n')
  const newLines = (newText ?? '').split('\n')
  const maxLen = Math.max(oldLines.length, newLines.length)
  const result: DiffPreviewLine[] = []

  for (let i = 0; i < maxLen; i++) {
    const oldL = oldLines[i] ?? ''
    const newL = newLines[i] ?? ''
    if (oldL === newL) {
      if (oldL) result.push({ type: 'context', text: oldL })
      continue
    }
    if (i < oldLines.length && oldL !== newL) {
      result.push({ type: 'remove', text: oldL })
    }
    if (i < newLines.length) {
      result.push({
        type: 'add',
        text: newL,
        highlight: inlineHighlight(oldL, newL),
      })
    }
  }
  return result
}

function parseUnifiedDiffPatch(patch: string): DiffPreviewLine[] {
  const result: DiffPreviewLine[] = []
  for (const raw of (patch ?? '').split('\n')) {
    if (!raw) continue
    if (raw.startsWith('---') || raw.startsWith('+++') || raw.startsWith('@@')) continue
    if (raw.startsWith('-')) {
      result.push({ type: 'remove', text: raw.slice(1) })
    } else if (raw.startsWith('+')) {
      result.push({ type: 'add', text: raw.slice(1) })
    } else if (raw.startsWith(' ')) {
      result.push({ type: 'context', text: raw.slice(1) })
    }
  }
  return result
}

function countDiffStats(lines: DiffPreviewLine[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const l of lines) {
    if (l.type === 'add') added++
    if (l.type === 'remove') removed++
  }
  return { added, removed }
}

function takePreviewLines(lines: DiffPreviewLine[], limit = 3): DiffPreviewLine[] {
  const nonEmpty = lines.filter((l) => l.text !== '')
  const changed = nonEmpty.filter((l) => l.type === 'remove' || l.type === 'add')
  const pool = changed.length > 0 ? changed : nonEmpty
  return pool.slice(0, limit)
}

function buildPreview(
  filePath: string,
  diffLines: DiffPreviewLine[],
): FileEditPreviewData {
  const stats = countDiffStats(diffLines)
  const nonEmpty = diffLines.filter((l) => l.text !== '')
  const fileName = basename(filePath)
  return {
    filePath,
    fileName,
    iconSrc: iconSrcForFile(fileName),
    added: stats.added,
    removed: stats.removed,
    lines: takePreviewLines(nonEmpty),
    allLines: nonEmpty,
  }
}

export function buildFileEditPreview(
  toolName: string,
  args?: Record<string, unknown> | string,
): FileEditPreviewData | null {
  const normalizedArgs = normalizeToolArgs(args)
  if (!normalizedArgs || !isFileEditTool(toolName)) return null

  if (toolName === 'write_file') {
    if (normalizedArgs.memory) return null
    const filePath = String(normalizedArgs.file_path ?? '').trim()
    const content = String(normalizedArgs.content ?? '')
    if (!filePath) return null
    const contentLines = content.split('\n')
    const diffLines: DiffPreviewLine[] = contentLines.map((text) => ({
      type: 'add',
      text,
    }))
    return {
      filePath,
      fileName: basename(filePath),
      iconSrc: iconSrcForFile(basename(filePath)),
      added: countLines(content),
      removed: 0,
      lines: takePreviewLines(diffLines),
      allLines: diffLines.filter((l) => l.text !== ''),
    }
  }

  if (toolName === 'edit_file') {
    const filePath = String(normalizedArgs.file_path ?? '').trim()
    if (!filePath) return null
    const editType = String(normalizedArgs.edit_type ?? '')

    if (editType === 'search_replace') {
      const diffLines = linesDiff(
        String(normalizedArgs.search_text ?? ''),
        String(normalizedArgs.new_content ?? ''),
      )
      return buildPreview(filePath, diffLines)
    }

    const newContent = String(normalizedArgs.new_content ?? '')
    const diffLines: DiffPreviewLine[] = newContent.split('\n').map((text) => ({
      type: 'add' as const,
      text,
    }))
    const startLine = Number(normalizedArgs.start_line)
    const endLine = Number(normalizedArgs.end_line)
    const removed =
      editType === 'line_range' && startLine > 0 && endLine >= startLine
        ? endLine - startLine + 1
        : 0
    return {
      filePath,
      fileName: basename(filePath),
      iconSrc: iconSrcForFile(basename(filePath)),
      added: countLines(newContent),
      removed,
      lines: takePreviewLines(diffLines),
      allLines: diffLines.filter((l) => l.text !== ''),
    }
  }

  if (toolName === 'apply_patch') {
    const filePath = String(normalizedArgs.file_path ?? '').trim()
    const patch = String(normalizedArgs.patch ?? '')
    if (!filePath || !patch) return null
    const diffLines = parseUnifiedDiffPatch(patch)
    return buildPreview(filePath, diffLines)
  }

  if (toolName === 'multi_replace_string') {
    const filePath = String(normalizedArgs.file_path ?? '').trim()
    const replacements = normalizedArgs.replacements
    if (!filePath || !Array.isArray(replacements)) return null
    const allLines: DiffPreviewLine[] = []
    for (const item of replacements) {
      if (!item || typeof item !== 'object') continue
      const r = item as Record<string, unknown>
      allLines.push(...linesDiff(String(r.old_text ?? ''), String(r.new_text ?? '')))
    }
    return buildPreview(filePath, allLines)
  }

  return null
}

function normalizeToolArgs(args?: Record<string, unknown> | string): Record<string, unknown> | null {
  if (!args) return null
  if (typeof args === 'string') {
    try {
      const parsed = JSON.parse(args)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
    } catch {
      return null
    }
  }
  return args
}
