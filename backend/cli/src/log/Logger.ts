// VS Code CLI 风格日志系统（对齐 cli/src/log.rs）
import { LogLevel } from '../types.js'

const COLORS_ENABLED = true

function formatTime(): string {
  const now = new Date()
  return now.toISOString().replace('T', ' ').slice(0, 19)
}

export function emit(level: LogLevel, prefix: string, message: string): void {
  const time = formatTime()
  const levelName = LogLevel[level].padEnd(8)
  let colorCode = ''
  let resetCode = ''

  if (COLORS_ENABLED) {
    switch (level) {
      case LogLevel.Trace:    colorCode = '\x1b[90m'; break  // gray
      case LogLevel.Debug:    colorCode = '\x1b[36m'; break  // cyan
      case LogLevel.Info:     colorCode = '\x1b[35m'; break  // magenta
      case LogLevel.Warn:     colorCode = '\x1b[33m'; break  // yellow
      case LogLevel.Error:    colorCode = '\x1b[31m'; break  // red
      case LogLevel.Critical: colorCode = '\x1b[31m\x1b[1m'; break  // bold red
    }
    resetCode = '\x1b[0m'
  }

  const prefixStr = prefix ? `[${prefix}] ` : ''
  console.error(`${colorCode}${time} ${levelName} ${prefixStr}${message}${resetCode}`)
}

export class Logger {
  private level: LogLevel
  private prefix: string | null

  constructor(level: LogLevel = LogLevel.Info, prefix: string | null = null) {
    this.level = level
    this.prefix = prefix
  }

  withPrefix(prefix: string): Logger {
    return new Logger(this.level, prefix)
  }

  trace(message: string): void      { this.log(LogLevel.Trace, message) }
  debug(message: string): void      { this.log(LogLevel.Debug, message) }
  info(message: string): void       { this.log(LogLevel.Info, message) }
  warn(message: string): void       { this.log(LogLevel.Warn, message) }
  error(message: string): void      { this.log(LogLevel.Error, message) }
  critical(message: string): void   { this.log(LogLevel.Critical, message) }

  private log(level: LogLevel, message: string): void {
    if (level < this.level) return
    emit(level, this.prefix ?? '', message)
  }

  result(message: string): void {
    console.log(message)
  }
}