const { contextBridge, ipcRenderer } = require('electron')
const os = require('os')

contextBridge.exposeInMainWorld('electronAPI', {
  /** 系统用户主目录 */
  homePath: os.homedir(),
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

  /** 重启应用 */
  relaunch: () => ipcRenderer.send('app:relaunch'),
})
