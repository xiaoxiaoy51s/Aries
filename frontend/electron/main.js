const { app, BrowserWindow, Menu } = require('electron')
const path = require('path')
const { spawn, spawnSync } = require('child_process')
const http = require('http')
const fs = require('fs')

const BACKEND_PORT = 30000

app.setName('MIMOClaw')
app.setAboutPanelOptions({ applicationName: 'MIMOClaw' })
app.commandLine.appendSwitch('no-sandbox')

let mainWindow = null
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
    ? path.join(process.resourcesPath, 'mimo_backend.exe')
    : path.join(__dirname, '..', 'resources', 'mimo_backend.exe')

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
