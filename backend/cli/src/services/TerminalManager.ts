// 命令执行器（对齐 cli/src/util/command.rs 的 async Command 模式）
// 使用 node-pty 实现稳定的 PTY 终端（比 Python winpty 绑定稳定得多）
import { spawn, IPty } from 'node-pty'
import * as os from 'os'
import * as path from 'path'
import * as fs from 'fs'
import { Logger } from '../log/Logger.js'
import { isBlocked, checkDangerous, isOutOfBounds } from '../security/patterns.js'
import type { ExecuteResult, TerminalSession } from '../types.js'
import { v4 as uuidv4 } from 'uuid'

const DEFAULT_TIMEOUT = 300
const MAX_TIMEOUT = 86400

// 长运行服务检测模式（对齐 terminal_manager.py 的 PERSISTENT_COMMAND_PATTERNS）
const PERSISTENT_PATTERNS: RegExp[] = [
  /^(?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+(?:run\s+)?(?:dev|start|serve)(?:\s|$)/i,
  /^(?:npx\s+)?vite(?:\s|$)/i,
  /^(?:npx\s+)?next\s+dev(?:\s|$)/i,
  /^python(?:3)?(?:\.exe)?\s+(?:main|app|run|server|start|manage)\b/i,
  /^python(?:3)?(?:\.exe)?\s+-m\s+(?:uvicorn|gunicorn|flask|django)\b/i,
  /^uvicorn\b/i,
  /^gunicorn\b/i,
  /^flask\b.*\brun\b/i,
  /^go\s+run\b/i,
  /^cargo\s+run\b/i,
  /^java\s+-jar\b/i,
  // 新增：Spring Boot / Gradle / .NET / PHP / Rails
  /^(?:mvn(?:\.cmd)?|gradle(?:\.bat)?)\s+(?:spring-boot:run|bootRun)\b/i,
  /^dotnet\s+run\b/i,
  /^php\s+artisan\s+serve\b/i,
  /^(?:bundle\s+exec\s+)?rails\s+(?:s|server)\b/i,
]

// 自动后台完成信号：检测各框架启动成功的标志输出
// 参考 VS Code problemMatcher 的 beginsPattern/endsPattern 思路
const AUTO_DETACH_PATTERNS: RegExp[] = [
  // 通用：监听端口 / 本地 URL
  /https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+\/?/,
  /\bLocal:\s+http:\/\//,
  /\bListening on\s+(?:http:\/\/)?(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+/i,
  // Vite / Next / Webpack
  /\bready in\b/i,
  /\bcompiled successfully\b/i,
  // 通用 server 就绪
  /\bserver (?:running|started|listening)\b/i,
  // Python
  /\buvicorn running\b/i,
  /\bUvicorn running on\b/i,
  /\bApplication startup complete\b/i,
  /\bServing Flask app\b/i,
  /\bDjango version\b.*\bstarting development server\b/i,
  // Spring Boot（Tomcat/Jetty/Netty）
  /\bTomcat (?:started|initialized) on port\s+\d+/i,
  /\bStarted \w+Application in\b/i,
  /\bJetty started on port\s+\d+/i,
  /\bNetty started on port\s+\d+/i,
  // Go
  /\bServer listening on\b/i,
  /\bListening and serving (?:HTTP|TCP) on\b/i,
  // .NET
  /\bNow listening on:\s+http:\/\/localhost:\d+/i,
  // PHP
  /\bLaravel development server started\b/i,
  /\bPHP\s+\d+\.\d+\.\d+\s+Development Server\b.*\bstarted\b/i,
  // Rails
  /\bRails\s+\d+.*\bstarted\b/i,
]

interface SessionState {
  pty: IPty
  info: TerminalSession
  outputBuffer: string
  callbacks: Set<(data: string) => void>
}

/**
 * 清理 ANSI 转义序列，用于返回给 AI 的 output（避免乱码）
 * 保留普通文本、换行、制表符
 */
function sanitizeForAI(raw: string): string {
  if (!raw) return raw
  let cleaned = raw
    // C1 CSI（Windows conhost 常用 \x9b 替代 \x1b[）
    .replace(/\x9b[0-9;?]*[ -/]*[@-~]/g, '')
    // CSI 序列（颜色/光标移动/擦除等）
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')
    // C1 OSC（窗口标题等）
    .replace(/\x9d[^\x07\x9b\x1b\[\n]*(?:\x07|\x9b|\\)/g, '')
    // OSC 序列（标题设置等）
    .replace(/\x1b\][^\x07\x1b\[\n]*(?:\x07|\x1b\\)/g, '')
    // 其他单字符转义
    .replace(/\x1b[=>78MNcD]/g, '')
    // 控制字符（保留 \t \n）
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1a\x7f-\x9a\x9c\x9e-\x9f]/g, '')
    // ESC 丢失后的残留 OSC/CSI（先 OSC 再 CSI，避免标题吞掉正文）
    .replace(/\]0;[^\[\x07\x1b\n]+/g, '')
    .replace(/\[[\?]?[0-9;]*[ -/]*[@-~]/g, '')
    // \r\n 统一为 \n，去除单独 \r
    .replace(/\r\n/g, '\n').replace(/\r/g, '')
    // 压缩连续空行
    .replace(/\n{3,}/g, '\n\n')
  return cleaned.trim()
}

/** invocation_id → session_id 映射，用于通过 toolCallId 找到终端会话 */
const invocationToSession = new Map<string, string>()

/** session_id → detach 回调，用于手动触发后台运行 */
const detachCallbacks = new Map<string, () => void>()

export class TerminalManager {
  private sessions = new Map<string, SessionState>()
  private logger: Logger

  constructor(logger: Logger) {
    this.logger = logger.withPrefix('terminal')
  }

  /** 获取 shell 路径 */
  private getShell(): { exe: string; args: string[] } {
    if (os.platform() === 'win32') {
      const override = process.env.ARIESCLAW_CONSOLE_SHELL
      if (override) {
        const parts = override.split(/\s+/)
        return { exe: parts[0], args: parts.slice(1) }
      }
      // 优先 pwsh，其次 powershell，最后 cmd
      // 用 process.env.PATH 检测，避免引入 which 依赖
      if (this.findInPath('pwsh.exe')) {
        return { exe: 'pwsh.exe', args: ['-NoExit'] }
      }
      if (this.findInPath('powershell.exe')) {
        return { exe: 'powershell.exe', args: ['-NoExit'] }
      }
      return { exe: process.env.COMSPEC || 'cmd.exe', args: [] }
    }
    return { exe: process.env.SHELL || '/bin/bash', args: [] }
  }

  /** 在 PATH 中查找可执行文件 */
  private findInPath(exe: string): string | null {
    const pathEnv = process.env.PATH || ''
    const sep = os.platform() === 'win32' ? ';' : ':'
    const ext = os.platform() === 'win32' ? '.exe' : ''
    for (const dir of pathEnv.split(sep)) {
      if (!dir) continue
      const full = path.join(dir, exe.endsWith(ext) ? exe : exe + ext)
      try {
        if (fs.existsSync(full)) return full
      } catch { /* ignore */ }
    }
    return null
  }

  /** 是否为长运行命令 */
  isPersistent(command: string): boolean {
    return PERSISTENT_PATTERNS.some(p => p.test(command.trim()))
  }

  /** 检测是否应自动转入后台 */
  private shouldAutoDetach(output: string): boolean {
    return AUTO_DETACH_PATTERNS.some(p => p.test(output))
  }

  /** 判断会话是否存在 */
  hasSession(sessionId: string): boolean {
    return this.sessions.has(sessionId)
  }

  /** 创建终端会话 */
  createSession(workDir: string, sessionId?: string): string {
    const sid = sessionId || `term-${uuidv4().slice(0, 8)}`
    if (this.sessions.has(sid)) {
      return sid
    }

    const resolvedDir = path.resolve(workDir)

    // 确保目录存在
    try {
      fs.mkdirSync(resolvedDir, { recursive: true })
    } catch { /* ignore */ }

    const { exe, args } = this.getShell()
    this.logger.debug(`spawning shell: ${exe} cwd=${resolvedDir}`)

    const pty = spawn(exe, args, {
      name: 'xterm-256color',
      cols: 120,
      rows: 30,
      cwd: resolvedDir,
      env: { ...process.env } as { [key: string]: string },
    })

    const shellKind = this.detectShellKind(exe)
    const state: SessionState = {
      pty,
      info: {
        id: sid,
        workDir: resolvedDir,
        pid: pty.pid,
        alive: true,
        createdAt: Date.now(),
        shellKind,
      },
      outputBuffer: '',
      callbacks: new Set(),
    }
    this.sessions.set(sid, state)

    // 监听输出
    pty.onData((data: string) => {
      state.outputBuffer += data
      // 限制 buffer 大小
      if (state.outputBuffer.length > 500_000) {
        state.outputBuffer = state.outputBuffer.slice(-250_000)
      }
      for (const cb of state.callbacks) {
        try { cb(data) } catch { /* ignore */ }
      }
    })

    // 监听退出
    pty.onExit(({ exitCode, signal }) => {
      this.logger.debug(`session ${sid} exited: code=${exitCode} signal=${signal}`)
      state.info.alive = false
    })

    return sid
  }

  /** 检测 shell 类型 */
  private detectShellKind(exe: string): string {
    const lower = exe.toLowerCase()
    if (lower.includes('powershell') || lower.endsWith('pwsh.exe')) return 'powershell'
    if (lower.includes('cmd')) return 'cmd'
    return 'unix'
  }

  /** 获取 shell 类型 */
  getShellKind(sessionId: string): string {
    return this.sessions.get(sessionId)?.info.shellKind || 'unknown'
  }

  /** 写入数据到终端（用户输入或命令） */
  write(sessionId: string, data: string): void {
    const state = this.sessions.get(sessionId)
    if (!state) {
      throw new Error(`Session ${sessionId} not found`)
    }
    state.pty.write(data)
  }

  /** 写入命令并回车 */
  writeCommand(sessionId: string, command: string): void {
    this.write(sessionId, `${command}\r`)
  }

  /** 发送 Ctrl+C */
  interrupt(sessionId: string): void {
    const state = this.sessions.get(sessionId)
    if (!state) return
    state.pty.write('\x03')
  }

  /** 调整终端大小 */
  resize(sessionId: string, cols: number, rows: number): void {
    const state = this.sessions.get(sessionId)
    if (!state) return
    try {
      state.pty.resize(Math.max(1, cols), Math.max(1, rows))
    } catch { /* ignore */ }
  }

  /** 重置会话（关闭旧 shell，创建新 shell） */
  resetSession(sessionId: string): void {
    const state = this.sessions.get(sessionId)
    if (!state) return
    try { state.pty.kill() } catch { /* ignore */ }
    const workDir = state.info.workDir
    const shellKind = state.info.shellKind
    this.sessions.delete(sessionId)

    // 重建
    const { exe, args } = this.getShell()
    const pty = spawn(exe, args, {
      name: 'xterm-256color',
      cols: 120,
      rows: 30,
      cwd: workDir,
      env: { ...process.env } as { [key: string]: string },
    })
    const newState: SessionState = {
      pty,
      info: {
        id: sessionId,
        workDir,
        pid: pty.pid,
        alive: true,
        createdAt: Date.now(),
        shellKind,
      },
      outputBuffer: '',
      callbacks: state.callbacks, // 保留回调
    }
    this.sessions.set(sessionId, newState)

    pty.onData((data: string) => {
      newState.outputBuffer += data
      if (newState.outputBuffer.length > 500_000) {
        newState.outputBuffer = newState.outputBuffer.slice(-250_000)
      }
      for (const cb of newState.callbacks) {
        try { cb(data) } catch { /* ignore */ }
      }
    })
    pty.onExit(({ exitCode }) => {
      this.logger.debug(`session ${sessionId} reset-exited: code=${exitCode}`)
      newState.info.alive = false
    })
  }

  /** 重置 agent 终端 */
  resetAgent(_workDir?: string): void {
    // 关闭所有会话
    this.closeAll()
  }

  /** 获取终端输出缓冲区 */
  getOutput(sessionId: string): string {
    return this.sessions.get(sessionId)?.outputBuffer || ''
  }

  /** 清除输出缓冲区 */
  clearOutput(sessionId: string): void {
    const state = this.sessions.get(sessionId)
    if (state) state.outputBuffer = ''
  }

  /** 设置输出回调 */
  onOutput(sessionId: string, callback: (data: string) => void): void {
    const state = this.sessions.get(sessionId)
    if (state) state.callbacks.add(callback)
  }

  /** 移除输出回调 */
  offOutput(sessionId: string, callback?: (data: string) => void): void {
    const state = this.sessions.get(sessionId)
    if (!state) return
    if (callback) {
      state.callbacks.delete(callback)
    } else {
      state.callbacks.clear()
    }
  }

  /** 获取所有会话 */
  getSessions(): TerminalSession[] {
    return Array.from(this.sessions.values()).map(s => s.info)
  }

  /** 获取单个会话 */
  getSession(sessionId: string): TerminalSession | undefined {
    return this.sessions.get(sessionId)?.info
  }

  /** 清理会话 */
  closeSession(sessionId: string): void {
    const state = this.sessions.get(sessionId)
    if (state) {
      // Windows 上 pty.kill() 只杀 PTY 进程（conhost/cmd），不会杀它启动的孙子进程
      // （如 npm run dev 启动的 vite，会变成孤儿继续占用端口）。
      // 用 taskkill /T /F 杀整棵进程树，确保 dev server 等长运行进程一起退出。
      const ptyPid = state.pty.pid
      if (ptyPid && process.platform === 'win32') {
        try {
          require('child_process').execSync(`taskkill /PID ${ptyPid} /T /F`, { stdio: 'ignore' })
        } catch { /* ignore */ }
      } else {
        try { state.pty.kill() } catch { /* ignore */ }
      }
    }
    this.sessions.delete(sessionId)
  }

  /** 关闭全部 */
  closeAll(): void {
    for (const sid of this.sessions.keys()) {
      this.closeSession(sid)
    }
  }

  /** 通过 invocation_id 手动 detach（用户点击"后台运行"） */
  detachByInvocation(invocationId: string): boolean {
    const sid = invocationToSession.get(invocationId)
    if (!sid) return false
    const cb = detachCallbacks.get(sid)
    if (!cb) return false
    cb()
    return true
  }

  /** 通过 session_id 手动 detach */
  detachBySession(sessionId: string): boolean {
    const cb = detachCallbacks.get(sessionId)
    if (!cb) return false
    cb()
    return true
  }

  /** 核心命令执行（供 AI 调用） */
  async execute(
    command: string,
    options: {
      workingDir?: string
      timeout?: number
      skipConfirmation?: boolean
      invocationId?: string
      sessionId?: string
      allowedDir?: string
      userHomeDir?: string
    } = {}
  ): Promise<ExecuteResult> {
    const normalizedCommand = command.trim()
    const timeout = Math.max(1, Math.min(options.timeout || DEFAULT_TIMEOUT, MAX_TIMEOUT))
    const allowedDir = options.allowedDir || os.homedir()
    const userHomeDir = options.userHomeDir || os.homedir()
    const targetDir = options.workingDir
      ? path.resolve(options.workingDir)
      : allowedDir

    if (!normalizedCommand) {
      return {
        success: false, return_code: -1, output: '缺少要执行的命令',
        error: 'Missing command', command: '', working_dir: targetDir,
        requires_confirmation: false,
      }
    }

    // 安全检查
    const blocked = isBlocked(normalizedCommand)
    if (blocked.blocked) {
      return {
        success: false, return_code: -1,
        output: `命令被阻止\n命令: ${normalizedCommand}\n原因: ${blocked.reason}`,
        error: `Command blocked: ${blocked.reason}`,
        command: normalizedCommand, working_dir: targetDir,
        requires_confirmation: false,
      }
    }

    const danger = checkDangerous(normalizedCommand)
    if (danger.dangerous) {
      if (isOutOfBounds(targetDir, allowedDir, userHomeDir)) {
        danger.danger_types.push('工作目录超出允许范围')
        danger.danger_info = danger.danger_types.join('、')
      }

      if (!options.skipConfirmation) {
        return {
          success: false, return_code: -1,
          output: `危险命令需要确认\n命令: ${normalizedCommand}\n原因: ${danger.danger_info}`,
          error: 'Confirmation required',
          command: normalizedCommand, working_dir: targetDir,
          requires_confirmation: true,
          danger_types: danger.danger_types,
          danger_info: danger.danger_info,
        }
      }
    }

    // AI 指定了 session_id 则使用它，否则默认按 work_dir 复用 agent session
    const agentSessionId = `agent:${targetDir}`
    const sessionId = options.sessionId || agentSessionId

    // 复用已有 session 或创建新 session
    const sid = this.createSession(targetDir, sessionId)
    const state = this.sessions.get(sid)!

    // 注册 invocation_id → session_id 映射，用于手动 detach
    if (options.invocationId) {
      invocationToSession.set(options.invocationId, sid)
    }

    // 记录本次命令开始前的输出位置
    const outputBefore = state.outputBuffer.length
    const outputBuffer: string[] = []
    const captureCb = (data: string) => outputBuffer.push(data)
    state.callbacks.add(captureCb)

    // 注入命令
    this.writeCommand(sid, normalizedCommand)

    return new Promise((resolve) => {
      let timedOut = false
      let autoDetached = false
      let settled = false
      let lastOutputLen = 0
      let stableCount = 0
      // 长运行命令 + 自定义 session_id 的 fallback detach 句柄
      // 在 cleanup 阶段统一清理；fallbackDetach 闭包见下方
      let fallbackDetach: NodeJS.Timeout | null = null

      const cleanup = () => {
        clearTimeout(timeoutHandle)
        clearInterval(detachCheck)
        clearInterval(stableCheck)
        if (fallbackDetach) clearTimeout(fallbackDetach)
        state.callbacks.delete(captureCb)
        // 清理 detach 回调
        detachCallbacks.delete(sid)
        if (options.invocationId) {
          invocationToSession.delete(options.invocationId)
        }
      }

      const finish = () => {
        if (settled) return
        settled = true
        cleanup()

        // 提取本次命令的输出，给 AI 的做 ANSI sanitize
        const fullOutput = state.outputBuffer.slice(outputBefore)
        const aiOutput = sanitizeForAI(fullOutput)
        // captured_output 保留原始 ANSI 供前端回放
        const captured = outputBuffer.join('')

        if (autoDetached) {
          resolve({
            success: true, return_code: 0,
            output: `开发服务器已启动并转入后台运行\n命令: ${normalizedCommand}\n执行目录: ${targetDir}`,
            captured_output: captured,
            command: normalizedCommand, working_dir: targetDir,
            requires_confirmation: false,
            session_id: sid,
            pid: state.pty.pid,
            auto_detached: true,
          })
          return
        }

        if (timedOut) {
          resolve({
            success: false, return_code: -1,
            output: `命令执行超时\n命令: ${normalizedCommand}\n执行目录: ${targetDir}\n超时时间: ${timeout} 秒\n终端输出:\n${aiOutput || '(无输出)'}`,
            error: `Command timed out after ${timeout} seconds`,
            command: normalizedCommand, working_dir: targetDir,
            requires_confirmation: false,
            captured_output: captured,
            session_id: sid,
            timed_out: true,
            pid: state.pty.pid,
          })
          return
        }

        // 正常完成（输出稳定后判定为成功）
        resolve({
          success: true, return_code: 0,
          output: aiOutput || `命令完成\n命令: ${normalizedCommand}`,
          captured_output: captured,
          command: normalizedCommand, working_dir: targetDir,
          requires_confirmation: false,
          session_id: sid,
          pid: state.pty.pid,
        })
      }

      // 注册手动 detach 回调（用户点击"后台运行"时触发）
      detachCallbacks.set(sid, () => {
        if (autoDetached || settled) return
        autoDetached = true
        finish()
      })

      const timeoutHandle = setTimeout(() => {
        timedOut = true
        this.interrupt(sid)
        setTimeout(() => finish(), 500)
      }, timeout * 1000)

      // 长运行命令的自动 detach 检测
      const detachCheck = setInterval(() => {
        if (autoDetached || settled) return
        const captured = outputBuffer.join('')
        if (this.shouldAutoDetach(captured)) {
          autoDetached = true
          finish()
        }
      }, 500)

      // 输出稳定检测：非持久命令在输出稳定一段时间后视为完成
      // 这是 PTY 模式下检测命令完成的标准方式（shell 不退出）
      const stableCheck = setInterval(() => {
        if (settled) return
        const currentLen = outputBuffer.join('').length
        if (currentLen === lastOutputLen) {
          stableCount++
          // 输出稳定 1.5 秒（3 次 500ms 检查）后判定完成
          // 但只在已有输出时才触发，避免空输出立即完成
          if (stableCount >= 3 && currentLen > 0) {
            finish()
          }
        } else {
          stableCount = 0
          lastOutputLen = currentLen
        }
      }, 500)

      // 长运行命令不触发稳定检测完成（只靠 detach 或超时）
      if (this.isPersistent(normalizedCommand)) {
        clearInterval(stableCheck)
      }

      // 长运行命令 + 自定义 session_id 的 fallback detach：
      // AI 显式传入 session_id（区别于默认 agent session）说明期望 dev server 等
      // 持续运行。AUTO_DETACH_PATTERNS 是主要机制（检测各框架就绪输出），
      // 这里是兜底：模式没匹配到时，PTY 仍存活就强制 detach 返回给 AI。
      // 分阶段超时：快速命令 8s，慢启动命令（mvn/gradle/dotnet）给 30s。
      if (this.isPersistent(normalizedCommand) && options.sessionId && !options.sessionId.startsWith('agent:')) {
        const isSlowStartup = /^(?:mvn|gradle|dotnet)\b/i.test(normalizedCommand)
        const fallbackMs = isSlowStartup ? 30000 : 8000
        fallbackDetach = setTimeout(() => {
          if (settled || autoDetached) return
          // PTY 已退出（命令失败）则不强制 detach，让上层走 timeout 看到错误
          if (!state.info.alive) return
          autoDetached = true
          finish()
        }, fallbackMs)
      }
    })
  }
}
