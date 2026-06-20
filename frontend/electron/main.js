const { app, BrowserWindow, Menu, ipcMain, screen } = require('electron')
const path = require('path')
const { spawn, spawnSync } = require('child_process')
const http = require('http')
const fs = require('fs')

const BACKEND_PORT = 30000

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

let mainWindow = null
let petWindow = null
let petStatusWindow = null
let petStatusTimer = null
let backendProcess = null
let backendPid = null

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

function killBackend() {
  // Kill by PID if we have it (synchronous to ensure it completes before quit)
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
    backendPid = null
  }
  
  backendProcess = null
}

async function startBackend() {
  // 检查后端是否已经在运行
  if (await checkBackendReady()) {
    console.log(`[Backend] already running on :${BACKEND_PORT}`)
    return
  }

  // 启动后端
  const isPackaged = app.isPackaged
  const backendExe = isPackaged
    ? path.join(process.resourcesPath, 'aries_backend.exe')
    : path.join(__dirname, '..', 'resources', 'aries_backend.exe')

  if (fs.existsSync(backendExe)) {
    console.log(`[Backend] starting: ${backendExe}`)
    backendProcess = spawn(backendExe, [], {
      env: { ...process.env, BACKEND_PORT: String(BACKEND_PORT) },
      stdio: 'pipe',
      windowsHide: true,
      cwd: path.dirname(backendExe),
    })
    backendPid = backendProcess.pid
  } else if (!isPackaged) {
    const backendDir = path.join(__dirname, '..', '..', 'backend')
    console.log('[Backend] starting: python main.py')
    backendProcess = spawn('python', ['main.py'], {
      cwd: backendDir,
      env: { ...process.env, BACKEND_PORT: String(BACKEND_PORT) },
      stdio: 'pipe',
    })
    backendPid = backendProcess.pid
  }

  if (backendProcess) {
    backendProcess.stdout.on('data', (data) => console.log(`[Backend] ${data}`))
    backendProcess.stderr.on('data', (data) => console.error(`[Backend] ${data}`))
    backendProcess.on('exit', (code) => {
      console.log(`[Backend] exited with code ${code}`)
      backendProcess = null
    })
  }

  // 等待后端就绪
  console.log('[Backend] waiting for ready...')
  const ready = await waitBackendReady()
  console.log(ready ? '[Backend] ready!' : '[Backend] timeout, continuing anyway...')
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200, height: 800, minWidth: 800, minHeight: 600,
    icon: path.join(__dirname, '..', 'public', 'favicon.png'),
    title: '',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webviewTag: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    backgroundColor: '#f3f3f2',
  })

  const isDev = process.env.NODE_ENV !== 'production' && !app.isPackaged
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  // mainWindow.webContents.openDevTools()

  // F12 打开/关闭 DevTools（类似浏览器行为）
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F12') {
      mainWindow.webContents.toggleDevTools()
    }
  })
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

app.whenReady().then(async () => {
  if (process.platform === 'darwin' && app.dock) {
    app.dock.setIcon(path.join(__dirname, '..', 'public', 'favicon.png'))
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

  await startBackend()
  createWindow()
})

app.on('window-all-closed', () => {
  killBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  killBackend()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
