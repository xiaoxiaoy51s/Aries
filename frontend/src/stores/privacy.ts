import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/**
 * 危险命令确认设置项
 * key 对应后端 cli_executor.py DANGEROUS_PATTERNS 返回的 danger_info
 * confirm=true 表示需要弹出确认，false 表示自动放行
 */
export interface DangerConfirmItem {
  /** 后端返回的 danger_info 关键词（用于匹配） */
  dangerType: string
  /** 显示名称 */
  label: string
  /** 描述 */
  desc: string
  /** 是否需要确认（true=弹确认框, false=自动放行） */
  confirm: boolean
}

const STORAGE_KEY = 'mimo:privacy_danger_confirms'

const defaultSettings: DangerConfirmItem[] = [
  { dangerType: '删除文件或目录', label: '删除确认', desc: '执行删除操作前需要手动确认，防止误删重要文件', confirm: true },
  { dangerType: '移动或重命名文件', label: '移动/重命名确认', desc: '移动或重命名文件前需要手动确认', confirm: true },
  { dangerType: '格式化磁盘', label: '格式化确认', desc: '格式化磁盘前需要手动确认', confirm: true },
  { dangerType: '系统关闭/重启', label: '关机/重启确认', desc: '系统关闭或重启前需要手动确认', confirm: true },
  { dangerType: '注册表操作', label: '注册表确认', desc: '注册表操作前需要手动确认', confirm: true },
  { dangerType: '用户管理操作', label: '用户管理确认', desc: '用户管理操作前需要手动确认', confirm: true },
]

function loadFromStorage(): DangerConfirmItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultSettings.map((s) => ({ ...s }))
    const saved: DangerConfirmItem[] = JSON.parse(raw)
    // 合并：以默认为基准，保留已保存的值，新增的用默认值
    return defaultSettings.map((def) => {
      const found = saved.find((s) => s.dangerType === def.dangerType)
      return found ? { ...def, confirm: found.confirm } : { ...def }
    })
  } catch {
    return defaultSettings.map((s) => ({ ...s }))
  }
}

export const usePrivacyStore = defineStore('privacy', () => {
  const settings = ref<DangerConfirmItem[]>(loadFromStorage())

  // 持久化到 localStorage
  watch(settings, (val) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
    } catch {}
  }, { deep: true })

  /** 切换某个危险类型的确认开关 */
  function toggleConfirm(dangerType: string) {
    const item = settings.value.find((s) => s.dangerType === dangerType)
    if (item) item.confirm = !item.confirm
  }

  /** 判断某个 danger_type 是否需要确认（精确匹配后端 DANGEROUS_PATTERNS 返回的 description） */
  function shouldConfirmByType(dangerType: string): boolean {
    const item = settings.value.find((s) => s.dangerType === dangerType)
    return item ? item.confirm : true // 未知类型默认需要确认
  }

  const commandPrefixes = ref<string[]>(loadCommandPrefixes())

  watch(commandPrefixes, (val) => {
    try {
      localStorage.setItem(COMMAND_PREFIX_KEY, JSON.stringify(val))
    } catch {}
  }, { deep: true })

  function addCommandPrefix(prefix: string) {
    const p = prefix.trim()
    if (!p || commandPrefixes.value.includes(p)) return
    commandPrefixes.value = [...commandPrefixes.value, p]
  }

  function isCommandPrefixWhitelisted(command: string): boolean {
    const prefix = extractCommandPrefix(command)
    return prefix ? commandPrefixes.value.includes(prefix) : false
  }

  /** 综合危险类型与命令前缀，判断是否需要弹出确认 */
  function needsConfirmation(dangerTypes: string[], command: string): boolean {
    if (isCommandPrefixWhitelisted(command)) return false
    if (!dangerTypes.length) return true
    return dangerTypes.some((dt) => shouldConfirmByType(dt))
  }

  return {
    settings,
    toggleConfirm,
    shouldConfirmByType,
    addCommandPrefix,
    isCommandPrefixWhitelisted,
    needsConfirmation,
  }
})

const COMMAND_PREFIX_KEY = 'mimo:privacy_command_prefixes'

function loadCommandPrefixes(): string[] {
  try {
    const raw = localStorage.getItem(COMMAND_PREFIX_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((p) => typeof p === 'string') : []
  } catch {
    return []
  }
}

/** 提取命令前缀（首个 token），用于「不再询问」白名单 */
export function extractCommandPrefix(command: string): string {
  const trimmed = (command || '').trim()
  if (!trimmed) return ''
  const match = trimmed.match(/^[^\s]+/)
  return match ? match[0] : ''
}
