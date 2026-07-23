const { contextBridge, ipcRenderer } = require('electron')

const HOME_DIR = process.env.USERPROFILE || process.env.HOME || ''

contextBridge.exposeInMainWorld('electronAPI', {
  /** 系统用户主目录 */
  homePath: HOME_DIR,
  /**
   * 显示宠物。
   *  - 传统调用 showPet(url, name)：仍兼容（按 GIF/单图模式渲染）
   *  - 推荐调用 showPet(spec)：spec 含 spritesheet metadata，可播放 9 状态动画
   *      { url, name, frameWidth?, frameHeight?, columns?, rows?, states? }
   */
  showPet: (...args) => {
    let payload
    if (args.length === 1 && typeof args[0] === 'object' && args[0] !== null) {
      payload = args[0]
    } else {
      payload = { url: args[0], name: args[1] }
    }
    ipcRenderer.send('pet:show', payload)
  },
  hidePet: () => ipcRenderer.send('pet:hide'),
  onPetClose: (callback) => ipcRenderer.on('pet:closed', callback),
  sendPetStatus: (text) => ipcRenderer.send('pet:status', { text }),
  clearPetStatus: () => ipcRenderer.send('pet:status', { clear: true }),
  isPetVisible: () => ipcRenderer.invoke('pet:is-visible'),
  /** 切换宠物动画状态：idle / running-right / running-left / waving / jumping / failed / waiting / running / review */
  setPetState: (state) => ipcRenderer.send('pet:set-state', { state }),

  /** 弹出系统原生文件/文件夹选择对话框（带地址栏，可粘贴路径） */
  selectDirectory: (opts) => ipcRenderer.invoke('dialog:select-directory', opts),
  selectFile: (opts) => ipcRenderer.invoke('dialog:select-file', opts),

  /** 使用系统默认浏览器打开外部链接 */
  openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),

  /** 重启应用 */
  relaunch: () => ipcRenderer.send('app:relaunch'),

  /** 完全退出应用（关闭后端） */
  quitApp: () => ipcRenderer.send('app:quit'),

  /** 确保后端进程已启动（启动页重试） */
  ensureBackend: () => ipcRenderer.send('backend:ensure'),

  /** 强制 kill 并重启后端进程（不重启 Electron） */
  forceRestartBackend: () => ipcRenderer.send('backend:force-restart'),

  /** 系统从休眠/睡眠唤醒后，主进程通知渲染层重新探活后端（复位连接丢失状态） */
  onBackendResume: (callback) => ipcRenderer.on('backend:resume', () => callback()),

  /** 窗口控制 */
  windowMinimize: () => ipcRenderer.send('window:minimize'),
  windowMaximize: () => ipcRenderer.send('window:maximize'),
  windowClose: () => ipcRenderer.send('window:close'),
  windowIsMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  onWindowMaximizedChange: (callback) => ipcRenderer.on('window:maximized-change', (_event, value) => callback(value)),

  /** 创建新窗口 */
  createNewWindow: () => ipcRenderer.send('window:create-new'),

  /** 切换开发者工具 */
  toggleDevTools: () => ipcRenderer.send('window:toggle-devtools'),

  /** 应用更新（仅打包模式可用） */
  update: {
    check: () => ipcRenderer.invoke('update:check'),
    download: () => ipcRenderer.send('update:download'),
    install: () => ipcRenderer.send('update:install'),
    onAvailable: (cb) => {
      const handler = (_e, info) => cb(info)
      ipcRenderer.on('update:available', handler)
      return () => ipcRenderer.removeListener('update:available', handler)
    },
    onProgress: (cb) => {
      const handler = (_e, progress) => cb(progress)
      ipcRenderer.on('update:progress', handler)
      return () => ipcRenderer.removeListener('update:progress', handler)
    },
    onDownloaded: (cb) => {
      const handler = (_e, info) => cb(info)
      ipcRenderer.on('update:downloaded', handler)
      return () => ipcRenderer.removeListener('update:downloaded', handler)
    },
    onError: (cb) => {
      const handler = (_e, msg) => cb(msg)
      ipcRenderer.on('update:error', handler)
      return () => ipcRenderer.removeListener('update:error', handler)
    },
  },
})
