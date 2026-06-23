// 安全模式检测（对齐 cli_executor.py 的安全逻辑 + VS Code 风格）
import type { DangerCheck } from '../types.js'

/** 危险操作模式 */
const DANGEROUS_PATTERNS: [RegExp, string][] = [
  [/\b(del|erase|rd|rmdir|rm)\b/i, '删除文件或目录'],
  [/\b(move|mv|ren|rename)\b/i, '移动或重命名文件'],
  [/((?<!-)\bformat\b(?!-)|\bshutdown\b|\brestart\b)/i, '系统危险操作'],
  [/\b(reg\s)/i, '注册表操作'],
  [/\b(net\s+user|net\s+localgroup)\b/i, '用户管理操作'],
]

/** 完全阻止的命令模式 */
const BLOCKED_PATTERNS: RegExp[] = [
  /\.\.\\/,
  /\.\.\//,
  /powershell.*-enc/i,
  /powershell.*-e\s/i,
  /wget\b/i,
  /curl.*\|\s*bash/i,
]

/** 白名单模式（匹配时跳过危险检测） */
const ALLOWED_PATTERNS: RegExp[] = [
  /^python\s+/i,
  /^python3\s+/i,
  /^pip\s+/i,
  /^npm\s+/i,
]

/** 检查命令是否被阻止 */
export function isBlocked(command: string): { blocked: boolean; reason?: string } {
  const isAllowed = ALLOWED_PATTERNS.some(p => p.test(command))
  if (isAllowed) return { blocked: false }

  for (const pattern of BLOCKED_PATTERNS) {
    if (pattern.test(command)) {
      return { blocked: true, reason: `命令包含被阻止的模式：${pattern.source}` }
    }
  }
  return { blocked: false }
}

/** 检查命令是否危险 */
export function checkDangerous(command: string): DangerCheck {
  const dangerTypes: string[] = []
  for (const [pattern, description] of DANGEROUS_PATTERNS) {
    if (pattern.test(command)) {
      dangerTypes.push(description)
    }
  }
  return {
    dangerous: dangerTypes.length > 0,
    danger_types: dangerTypes,
    danger_info: dangerTypes.join('、'),
  }
}

/** 检查工作目录是否越界 */
export function isOutOfBounds(
  targetDir: string,
  allowedDir: string,
  userHomeDir: string
): boolean {
  const normalized = targetDir.replace(/\\/g, '/')
  const allowed = allowedDir.replace(/\\/g, '/')
  const home = userHomeDir.replace(/\\/g, '/')

  if (normalized === home || normalized.startsWith(home + '/')) return false
  if (normalized === allowed || normalized.startsWith(allowed + '/')) return false
  return true
}