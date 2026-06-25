// MIMO CLI Server - VS Code 风格 CLI 后端
// 提供 HTTP API + WebSocket 终端，由 Python 后端自动启动
import * as http from 'http'
import * as url from 'url'
import * as path from 'path'
import * as os from 'os'
import { WebSocketServer, WebSocket } from 'ws'

import { Logger } from './log/Logger.js'
import { LogLevel, type ExecuteRequest, type ExecuteResult, type WsMessage } from './types.js'
import { printBannerHeader, printBannerLine, printBannerFooter } from './output/Styles.js'
import { TerminalManager } from './services/TerminalManager.js'

// ---- 解析命令行参数 ----
const args = process.argv.slice(2)
let port = 18765
let host = '127.0.0.1'
let logLevel = LogLevel.Info
let allowedDir = path.join(os.homedir(), '.Aries')

for (let i = 0; i < args.length; i++) {
  switch (args[i]) {
    case '--port':      port = parseInt(args[++i], 10); break
    case '--host':      host = args[++i]; break
    case '--log-level': logLevel = parseInt(args[++i], 10) as LogLevel; break
    case '--allowed-dir': allowedDir = path.resolve(args[++i]); break
    case '--verbose':   logLevel = LogLevel.Trace; break
  }
}

// ---- 初始化 ----
const logger = new Logger(logLevel, 'cli-server')
const termManager = new TerminalManager(logger)

// ---- HTTP Server ----
const server = http.createServer((req, res) => {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return
  }

  const parsedUrl = url.parse(req.url || '', true)
  const method = req.method || 'GET'

  // 健康检查
  if (method === 'GET' && parsedUrl.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ status: 'ok', pid: process.pid }))
    return
  }

  // 获取会话列表
  if (method === 'GET' && parsedUrl.pathname === '/sessions') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(termManager.getSessions()))
    return
  }

  // 获取单个会话输出
  if (method === 'GET' && parsedUrl.pathname?.startsWith('/sessions/')) {
    const sid = parsedUrl.pathname.split('/')[2]
    if (parsedUrl.query.clear === '1') {
      termManager.clearOutput(sid)
    }
    const output = termManager.getOutput(sid)
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ session_id: sid, output }))
    return
  }

  // 执行命令（AI 调用的核心 API）
  if (method === 'POST' && parsedUrl.pathname === '/execute') {
    let body = ''
    req.on('data', (chunk: Buffer) => { body += chunk.toString() })
    req.on('end', async () => {
      try {
        const reqData: ExecuteRequest = JSON.parse(body)
        const result = await termManager.execute(reqData.command, {
          workingDir: reqData.working_dir,
          timeout: reqData.timeout,
          skipConfirmation: reqData.skip_confirmation,
          invocationId: reqData.invocation_id,
          sessionId: reqData.session_id,
          allowedDir,
          userHomeDir: os.homedir(),
        })
        res.writeHead(result.success ? 200 : (result.requires_confirmation ? 403 : 400), {
          'Content-Type': 'application/json'
        })
        res.end(JSON.stringify(result))
      } catch (err: any) {
        const errMsg = err?.message || String(err)
        const errStack = err?.stack || ''
        logger.error(`Execute failed: ${errMsg}\n${errStack}`)
        res.writeHead(500, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ success: false, error: errMsg, stack: errStack }))
      }
    })
    return
  }

  // 中断命令 / 手动 detach（后台运行）
  if (method === 'POST' && parsedUrl.pathname?.startsWith('/sessions/')) {
    const parts = parsedUrl.pathname.split('/')
    const sid = parts[2]
    if (parsedUrl.pathname.endsWith('/interrupt')) {
      termManager.interrupt(sid)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ success: true }))
      return
    }
    if (parsedUrl.pathname.endsWith('/detach')) {
      // 先尝试用 sid 作为 session_id
      let ok = termManager.detachBySession(sid)
      if (!ok) {
        // 再尝试用 sid 作为 invocation_id
        ok = termManager.detachByInvocation(sid)
      }
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ success: ok, detached: ok }))
      return
    }
  }

  // 关闭会话
  if (method === 'DELETE' && parsedUrl.pathname?.startsWith('/sessions/')) {
    const sid = parsedUrl.pathname.split('/')[2]
    termManager.closeSession(sid)
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ success: true }))
    return
  }

  // 重置 agent 终端
  if (method === 'POST' && parsedUrl.pathname === '/reset-agent') {
    let body = ''
    req.on('data', (chunk: Buffer) => { body += chunk.toString() })
    req.on('end', () => {
      try {
        const data = JSON.parse(body)
        termManager.resetAgent(data.work_dir)
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ status: 'ok' }))
      } catch {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ status: 'ok' }))
      }
    })
    return
  }

  // 404
  res.writeHead(404, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ error: 'Not found' }))
})

// ---- WebSocket Server ----
const wss = new WebSocketServer({ server, path: '/ws/terminal' })

wss.on('connection', (ws: WebSocket, req) => {
  const parsedUrl = url.parse(req.url || '', true)
  const sessionId = (parsedUrl.query.session_id as string) || ''
  const workDir = (parsedUrl.query.work_dir as string) || ''

  logger.debug(`WebSocket connected: session=${sessionId}`)

  let attached = false
  let outputCallback: ((data: string) => void) | null = null

  ws.on('message', (raw) => {
    let msg: WsMessage
    try {
      msg = JSON.parse(raw.toString())
    } catch {
      return // 忽略无效 JSON
    }

    switch (msg.type) {
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong' }))
        break

      case 'attach': {
        const rows = msg.rows || 30
        const cols = msg.cols || 120
        const reset = msg.reset !== false // 默认 true
        const replay = msg.replay === true

        // 确保会话存在
        let sid = sessionId
        if (!termManager.hasSession(sid)) {
          sid = termManager.createSession(workDir || allowedDir, sid)
        }

        // 注册输出回调，推送实时数据到前端
        outputCallback = (data: string) => {
          if (ws.readyState === WebSocket.OPEN) {
            const outMsg: WsMessage = { type: 'output', data, session_id: sid }
            ws.send(JSON.stringify(outMsg))
          }
        }
        termManager.onOutput(sid, outputCallback)
        attached = true

        // 如果要求重置，重建 shell
        if (reset) {
          termManager.resetSession(sid)
        }

        // 调整终端大小
        termManager.resize(sid, cols, rows)

        // 如果要求回放历史输出且不重置
        if (replay && !reset) {
          const replayData = termManager.getOutput(sid)
          if (replayData) {
            const outMsg: WsMessage = { type: 'output', data: replayData, session_id: sid }
            ws.send(JSON.stringify(outMsg))
          }
        }

        // 发送 ready 信号
        const readyMsg: WsMessage = {
          type: 'ready',
          shell: termManager.getShellKind(sid),
          session_id: sid,
        }
        ws.send(JSON.stringify(readyMsg))
        break
      }

      case 'input': {
        if (!attached) return
        const data = msg.data || ''
        if (data) termManager.write(sessionId, data)
        break
      }

      case 'resize': {
        if (!attached) return
        const rows = msg.rows || 30
        const cols = msg.cols || 120
        termManager.resize(sessionId, cols, rows)
        break
      }
    }
  })

  ws.on('close', () => {
    if (outputCallback && sessionId) {
      termManager.offOutput(sessionId)
    }
  })
})

// ---- 优雅关闭 ----
function shutdown() {
  logger.info('Shutting down CLI server...')
  termManager.closeAll()
  wss.close()
  server.close()
  process.exit(0)
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
process.on('uncaughtException', (err) => {
  logger.error(`Uncaught exception: ${err.message}`)
  logger.error(err.stack || '')
})

// ---- Start ----
server.listen(port, host, () => {
  printBannerHeader('MIMO CLI Server', 0)
  printBannerLine('Port', `${port}`)
  printBannerLine('Host', host)
  printBannerLine('PID', `${process.pid}`)
  printBannerLine('Allowed', allowedDir)
  printBannerFooter()

  // 输出 JSON 格式的就绪信号（供 Python 父进程解析）
  console.log(JSON.stringify({
    event: 'ready',
    pid: process.pid,
    port,
    host,
  }))

  logger.info('CLI server ready')
})
