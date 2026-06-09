const { app, BrowserWindow } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

let mainWindow = null
let backendProcess = null

function startBackend() {
  const backendDir = path.join(__dirname, '..', '..', 'backend')
  backendProcess = spawn('python', ['main.py'], {
    cwd: backendDir,
    env: { ...process.env, BACKEND_PORT: '2026' },
    stdio: 'pipe',
  })
  backendProcess.stdout.on('data', (data) => console.log(`[Backend] ${data}`))
  backendProcess.stderr.on('data', (data) => console.error(`[Backend] ${data}`))
  backendProcess.on('exit', (code) => console.log(`[Backend] exited with code ${code}`))
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    titleBarStyle: 'hiddenInset',
    frame: process.platform === 'darwin' ? false : true,
    backgroundColor: '#f3f3f2',
  })

  // 开发模式连接 vite dev server
  const isDev = process.env.NODE_ENV !== 'production' && !app.isPackaged
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  startBackend()
  createWindow()
})

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
