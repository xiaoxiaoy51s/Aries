const { app, BrowserWindow, Menu, ipcMain, screen, dialog, Tray, nativeImage } = require('electron')
const path = require('path')
const { spawn, spawnSync } = require('child_process')
const http = require('http')
const fs = require('fs')

const BACKEND_PORT = 30000

// 单实例：再次启动时聚焦已有窗口
const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
  app.quit()
}

app.setName('Aries')
app.setAboutPanelOptions({ applicationName: 'Aries' })
app.commandLine.appendSwitch('no-sandbox')

// 静默 webview 加载链路抛出的 ERR_FAILED / ERR_ABORTED 噪声日志：
// 这些通常来自页面重定向、用户重复 navigate、子资源被拦，页面其实正常显示。
process.on('unhandledRejection', (reason) => {
  const code = reason && (reason.code || reason.errno)
  const msg = reason && (reason.message || String(reason))
  const isWebviewLoad = msg && /loading '/.test(msg)
  const isIgnorableCode =
    code === 'ERR_FAILED' ||
    code === 'ERR_ABORTED' ||
    code === -2 ||
    code === -3
  if (isWebviewLoad && isIgnorableCode) return
  // 其他错误仍打到 stderr
  console.error('[unhandledRejection]', reason)
})

const windows = new Set()
let mainWindow = null
let petWindow = null
let petStatusWindow = null
let petStatusTimer = null
let backendProcess = null
let backendPid = null
let backendOwned = false
let backendSpawnedByApp = false
let backendStartInProgress = false
let tray = null
let isQuitting = false

function checkBackendReady() {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port: BACKEND_PORT, path: '/health', timeout: 1000 }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

async function waitBackendReady(maxWaitMs = 15000) {
  const start = Date.now()
  while (Date.now() - start < maxWaitMs) {
    if (await checkBackendReady()) return true
    await new Promise(r => setTimeout(r, 500))
  }
  return false
}

function getBackendLogPath() {
  const home = process.env.USERPROFILE || process.env.HOME || app.getPath('home')
  const dir = path.join(home, '.Aries', 'logs')
  fs.mkdirSync(dir, { recursive: true })
  return path.join(dir, 'backend.log')
}

function getTrayIconPath() {
  const ico = path.join(__dirname, '..', 'public', 'logo.ico')
  const png = path.join(__dirname, '..', 'public', 'logo.png')
  if (process.platform === 'win32' && fs.existsSync(ico)) return ico
  return png
}

function showMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
    return
  }
  createWindow()
}

function quitApp() {
  isQuitting = true
  killBackend({ forceAll: true })
  if (tray) {
    tray.destroy()
    tray = null
  }
  app.quit()
}

function createTray() {
  if (tray) return
  const iconPath = getTrayIconPath()
  let icon = nativeImage.createFromPath(iconPath)
  if (icon.isEmpty()) {
    console.error('[Tray] failed to load icon:', iconPath)
    return
  }
  // Windows 托盘推荐 16×16，避免大图不显示
  if (process.platform === 'win32') {
    icon = icon.resize({ width: 16, height: 16 })
  }
  tray = new Tray(icon)
  tray.setToolTip('Aries')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示主窗口', click: () => showMainWindow() },
    { type: 'separator' },
    { label: '退出', click: () => quitApp() },
  ]))
  tray.on('double-click', () => showMainWindow())
}

function shouldMinimizeToTray() {
  return app.isPackaged
}

function killProcessOnPort(port) {
  if (process.platform !== 'win32') return
  try {
    const result = spawnSync('netstat', ['-ano'], { encoding: 'utf8' })
    const lines = (result.stdout || '').split(/\r?\n/)
    const pids = new Set()
    for (const line of lines) {
      if (!line.includes('LISTENING')) continue
      const m = line.trim().match(/:(\d+)\s+\S+\s+LISTENING\s+(\d+)$/)
      if (!m || Number(m[1]) !== port) continue
      const pid = Number(m[2])
      if (Number.isInteger(pid) && pid > 0) pids.add(pid)
    }
    for (const pid of pids) {
      spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' })
    }
  } catch (e) {
    console.error('[Backend] kill by port error:', e)
  }
}

function killBackend({ forceAll = false } = {}) {
  if (!forceAll && !backendSpawnedByApp && !backendOwned) return

  if (backendPid) {
    try {
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/PID', String(backendPid), '/T', '/F'], { stdio: 'ignore' })
      } else {
        process.kill(backendPid, 'SIGTERM')
      }
    } catch (e) {
      console.error('[Backend] kill error:', e)
    }
  }

  // 用户退出时强制清理 30000 端口，避免「already running」遗留孤儿进程
  if (forceAll || backendSpawnedByApp || backendOwned) {
    killProcessOnPort(BACKEND_PORT)
  }

  backendPid = null
  backendProcess = null
  backendOwned = false
  backendSpawnedByApp = false
}

async function startBackend() {
  if (backendStartInProgress) return

  if (await checkBackendReady()) {
    console.log(`[Backend] already running on :${BACKEND_PORT} (will stop when app quits)`)
    backendOwned = false
    backendSpawnedByApp = false
    return
  }

  backendStartInProgress = true
  const isPackaged = app.isPackaged
  const backendExe = isPackaged
    ? path.join(process.resourcesPath, 'aries_backend.exe')
    : path.join(__dirname, '..', 'resources', 'aries_backend.exe')

  try {
    if (isPackaged) {
      if (!fs.existsSync(backendExe)) {
        console.error(`[Backend] missing executable: ${backendExe}`)
        return
      }
      console.log(`[Backend] starting: ${backendExe}`)
      const logPath = getBackendLogPath()
      fs.appendFileSync(logPath, `\n--- ${new Date().toISOString()} spawn ${backendExe} ---\n`)
      const logFd = fs.openSync(logPath, 'a')
      backendProcess = spawn(backendExe, [], {
        env: { ...process.env, BACKEND_PORT: String(BACKEND_PORT) },
        cwd: path.dirname(backendExe),
        windowsHide: true,
        detached: false,
        stdio: ['ignore', logFd, logFd],
      })
      backendPid = backendProcess.pid
      backendOwned = true
      backendSpawnedByApp = true
    } else {
      // 开发模式始终用 python，避免与 resources/aries_backend.exe 重复拉起
      const backendDir = path.join(__dirname, '..', '..', 'backend')
      console.log('[Backend] starting: python main.py')
      backendProcess = spawn('python', ['main.py'], {
        cwd: backendDir,
        env: { ...process.env, BACKEND_PORT: String(BACKEND_PORT) },
        stdio: 'pipe',
      })
      backendPid = backendProcess.pid
      backendOwned = true
      backendSpawnedByApp = true
    }

    if (backendProcess) {
      if (!isPackaged) {
        backendProcess.stdout.on('data', (data) => console.log(`[Backend] ${data}`))
        backendProcess.stderr.on('data', (data) => console.error(`[Backend] ${data}`))
      }
      backendProcess.on('error', (err) => {
        console.error('[Backend] spawn error:', err)
        backendOwned = false
        backendSpawnedByApp = false
      })
      backendProcess.on('exit', (code) => {
        console.log(`[Backend] exited with code ${code}`)
        backendProcess = null
        backendPid = null
        backendOwned = false
        if (!isQuitting) {
          backendSpawnedByApp = false
        }
      })
    }

    void monitorBackendStartup(isPackaged)
  } finally {
    backendStartInProgress = false
  }
}

async function monitorBackendStartup(isPackaged) {
  const maxWaitMs = isPackaged ? 90000 : 15000
  let ready = await waitBackendReady(maxWaitMs)

  if (!ready && backendOwned && backendPid) {
    console.log('[Backend] timeout but process alive, waiting extra 60s...')
    ready = await waitBackendReady(60000)
  }

  if (ready) {
    console.log('[Backend] ready!')
    return
  }

  if (backendOwned) {
    console.error('[Backend] startup failed, cleaning up')
    killBackend()
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200, height: 800, minWidth: 800, minHeight: 600,
    icon: path.join(__dirname, '..', 'public', 'logo.png'),
    title: '',
    frame: false,
    titleBarStyle: 'hidden',
    thickFrame: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webviewTag: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    backgroundColor: '#f8f8f7',
  })

  windows.add(win)
  if (!mainWindow || mainWindow.isDestroyed()) {
    mainWindow = win
  }

  win.on('maximize', () => {
    win.webContents.send('window:maximized-change', true)
  })
  win.on('unmaximize', () => {
    win.webContents.send('window:maximized-change', false)
  })

  win.on('closed', () => {
    windows.delete(win)
    if (mainWindow === win) {
      mainWindow = null
      for (const w of windows) {
        if (!w.isDestroyed()) {
          mainWindow = w
          break
        }
      }
    }
  })

  win.on('close', (event) => {
    if (!isQuitting && shouldMinimizeToTray()) {
      event.preventDefault()
      win.hide()
    }
  })

  const isDev = process.env.NODE_ENV !== 'production' && !app.isPackaged
  if (isDev) {
    win.loadURL('http://localhost:5173')
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  // F12 打开/关闭 DevTools（类似浏览器行为）
  win.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F12') {
      win.webContents.toggleDevTools()
    }
  })

  return win
}

function createNewWindow() {
  const win = createWindow()
  if (!win) return
  const primaryDisplay = screen.getPrimaryDisplay()
  const { width, height } = primaryDisplay.workAreaSize
  // 简单偏移，避免完全重叠
  const offset = windows.size * 30
  const x = Math.min(offset, Math.max(0, width - 1200))
  const y = Math.min(offset, Math.max(0, height - 800))
  win.setPosition(x, y)
  win.show()
}

// ---------- 宠物窗口 ----------
function createPetWindow() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.show()
    return
  }

  petWindow = new BrowserWindow({
    width: 192,
    height: 208,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true,
    maximizable: false,
    minimizable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: false,
    x: screen.getPrimaryDisplay().workAreaSize.width - 220,
    y: screen.getPrimaryDisplay().workAreaSize.height - 260,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  })

  petWindow.loadFile(path.join(__dirname, 'pet.html'))
  petWindow.setIgnoreMouseEvents(false)

  petWindow.on('closed', () => {
    petWindow = null
  })
}

// IPC: 显示宠物
ipcMain.on('pet:show', (event, data) => {
  const isNew = !petWindow || petWindow.isDestroyed()
  createPetWindow()
  const send = () => {
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('pet:set-url', data)
    }
  }
  if (isNew) {
    petWindow.webContents.once('did-finish-load', send)
  } else {
    send()
  }
})

// IPC: 切换宠物动画状态（idle / running-right / waving / jumping / failed / waiting / running / review / running-left）
ipcMain.on('pet:set-state', (event, data) => {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.webContents.send('pet:set-state', data)
  }
})

// IPC: 隐藏宠物
ipcMain.on('pet:hide', () => {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.close()
    petWindow = null
  }
})

// IPC: 宠物窗口拖拽
ipcMain.on('pet:drag', (event, { dx, dy }) => {
  if (!petWindow || petWindow.isDestroyed()) return
  const [x, y] = petWindow.getPosition()
  petWindow.setPosition(Math.round(x + dx), Math.round(y + dy))
  // 状态窗口跟随移动
  if (petStatusWindow && !petStatusWindow.isDestroyed() && petStatusWindow.isVisible()) {
    const [sx, sy] = petStatusWindow.getPosition()
    petStatusWindow.setPosition(Math.round(sx + dx), Math.round(sy + dy))
  }
})

// IPC: 宠物窗口关闭
ipcMain.on('pet:close', () => {
  if (petStatusWindow && !petStatusWindow.isDestroyed()) {
    petStatusWindow.close()
    petStatusWindow = null
  }
  if (petStatusTimer) {
    clearTimeout(petStatusTimer)
    petStatusTimer = null
  }
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.close()
    petWindow = null
  }
  // 通知主窗口
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('pet:closed')
  }
})

// IPC: 宠物窗口缩放（等比缩放，保持左上角不变）
ipcMain.on('pet:resize', (event, { width, height }) => {
  if (!petWindow || petWindow.isDestroyed()) return
  const [x, y] = petWindow.getPosition()
  const w = Math.round(width)
  const h = Math.round(height)
  petWindow.setSize(w, h)
  petWindow.setPosition(x, y)
  // 状态窗口跟随重新定位（水平居中于宠物窗口上方）
  if (petStatusWindow && !petStatusWindow.isDestroyed() && petStatusWindow.isVisible()) {
    const [sw, sh] = petStatusWindow.getSize()
    const sx = Math.round(x + w / 2 - sw / 2)
    const sy = Math.round(y - sh - 4)
    petStatusWindow.setPosition(sx, sy)
  }
})

// IPC: 查询宠物窗口是否可见
ipcMain.handle('pet:is-visible', () => {
  return !!(petWindow && !petWindow.isDestroyed() && petWindow.isVisible())
})

// IPC: 宠物状态推送（AI 活动分段推送）—— 独立窗口显示在宠物上方
ipcMain.on('pet:status', (event, data) => {
  if (data.clear) {
    hidePetStatusWindow()
    return
  }
  if (!data.text) return
  showPetStatusWindow(data.text)
})

function showPetStatusWindow(text) {
  if (!petWindow || petWindow.isDestroyed()) return

  // 计算状态窗口尺寸：宽度 280px，高度根据文字估算
  const statusW = 280
  const charCount = Math.max(text.length, 10)
  const lines = Math.ceil(charCount / 22) // 约 22 字/行
  const statusH = Math.min(lines * 22 + 16, 120)

  // 计算位置：宠物窗口正上方，水平居中
  const [petX, petY] = petWindow.getPosition()
  const [petW] = petWindow.getSize()
  const statusX = Math.round(petX + petW / 2 - statusW / 2)
  const statusY = Math.round(petY - statusH - 4)

  if (!petStatusWindow || petStatusWindow.isDestroyed()) {
    petStatusWindow = new BrowserWindow({
      width: statusW,
      height: statusH,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      resizable: true,
      maximizable: false,
      minimizable: false,
      skipTaskbar: true,
      hasShadow: false,
      focusable: false,
      x: statusX,
      y: statusY,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false,
      },
    })
    petStatusWindow.loadFile(path.join(__dirname, 'pet_status.html'))
    petStatusWindow.setIgnoreMouseEvents(true)
    // 加载完成后发送状态
    petStatusWindow.webContents.once('did-finish-load', () => {
      petStatusWindow.webContents.send('pet:status', { text })
    })
  } else {
    petStatusWindow.setSize(statusW, statusH)
    petStatusWindow.setPosition(statusX, statusY)
    petStatusWindow.webContents.send('pet:status', { text })
  }
  petStatusWindow.show()

  // 3 秒后自动隐藏
  if (petStatusTimer) clearTimeout(petStatusTimer)
  petStatusTimer = setTimeout(() => {
    hidePetStatusWindow()
  }, 3000)
}

function hidePetStatusWindow() {
  if (petStatusTimer) {
    clearTimeout(petStatusTimer)
    petStatusTimer = null
  }
  if (petStatusWindow && !petStatusWindow.isDestroyed()) {
    petStatusWindow.webContents.send('pet:status', { clear: true })
    setTimeout(() => {
      if (petStatusWindow && !petStatusWindow.isDestroyed()) {
        petStatusWindow.hide()
      }
    }, 250) // 等淡出动画
  }
}

// IPC: 点击宠物 → 聚焦主窗口
ipcMain.on('pet:focus-main', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
})

// IPC: 重启应用
ipcMain.on('app:relaunch', () => {
  isQuitting = true
  killBackend({ forceAll: true })
  app.relaunch()
  app.exit(0)
})

// IPC: 完全退出（托盘菜单 / Ctrl+Q）
ipcMain.on('app:quit', () => {
  quitApp()
})

// IPC: 前端启动页重试时重新拉起后端
ipcMain.on('backend:ensure', () => {
  void startBackend()
})

// IPC: 窗口控制
function getSenderWindow(event) {
  const webContents = event.sender
  for (const win of windows) {
    if (!win.isDestroyed() && win.webContents === webContents) {
      return win
    }
  }
  return mainWindow
}

ipcMain.on('window:minimize', (event) => {
  const win = getSenderWindow(event)
  if (win && !win.isDestroyed()) win.minimize()
})

ipcMain.on('window:maximize', (event) => {
  const win = getSenderWindow(event)
  if (win && !win.isDestroyed()) {
    if (win.isMaximized()) {
      win.unmaximize()
    } else {
      win.maximize()
    }
  }
})

ipcMain.on('window:close', (event) => {
  const win = getSenderWindow(event)
  if (!win || win.isDestroyed()) return
  if (isQuitting || !shouldMinimizeToTray()) {
    win.close()
  } else {
    win.hide()
  }
})

ipcMain.handle('window:is-maximized', (event) => {
  const win = getSenderWindow(event)
  return !!(win && !win.isDestroyed() && win.isMaximized())
})

ipcMain.on('window:create-new', () => {
  createNewWindow()
})

// IPC: 系统原生文件/文件夹选择对话框
ipcMain.handle('dialog:select-directory', async (event, opts = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: opts.title || '选择文件夹',
    defaultPath: opts.defaultPath || undefined,
    properties: ['openDirectory'],
  })
  if (result.canceled || result.filePaths.length === 0) {
    return { path: null, cancelled: true }
  }
  return { path: result.filePaths[0], cancelled: false }
})

ipcMain.handle('dialog:select-file', async (event, opts = {}) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: opts.title || '选择文件',
    defaultPath: opts.defaultPath || undefined,
    filters: opts.filters || undefined,
    properties: ['openFile'],
  })
  if (result.canceled || result.filePaths.length === 0) {
    return { path: null, cancelled: true }
  }
  return { path: result.filePaths[0], cancelled: false }
})

if (gotSingleInstanceLock) {
  app.whenReady().then(async () => {
    if (process.platform === 'darwin' && app.dock) {
      app.dock.setIcon(path.join(__dirname, '..', 'public', 'logo.png'))
    }
    if (process.platform === 'darwin') {
      const template = [
        { label: app.getName(), submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'quit' }] },
        { label: 'Edit', submenu: [{ role: 'undo' }, { role: 'redo' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
        { label: 'View', submenu: [{ role: 'reload' }, { role: 'toggleDevTools' }] },
        { label: 'Window', submenu: [{ role: 'minimize' }, { role: 'close' }] },
      ]
      Menu.setApplicationMenu(Menu.buildFromTemplate(template))
    } else {
      Menu.setApplicationMenu(null)
    }

    void startBackend()
    createTray()
    createWindow()
  })

  app.on('second-instance', () => {
    showMainWindow()
  })

  app.on('window-all-closed', () => {
    // 开发模式：关窗即退出；打包模式：保留托盘
    if (!app.isPackaged) {
      quitApp()
    }
  })

  app.on('before-quit', () => {
    isQuitting = true
    killBackend({ forceAll: true })
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
    else showMainWindow()
  })
}
