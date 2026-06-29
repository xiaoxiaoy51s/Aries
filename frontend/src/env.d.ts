/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface Window {
  electronAPI?: {
    /**
     * 显示宠物。可传 (url, name) 单图旧调用，或传一个 spec 对象支持 sprite 动画：
     *   { url, name?, frameWidth?, frameHeight?, columns?, rows?, states? }
     */
    showPet: (...args: any[]) => void
    hidePet: () => void
    onPetClose: (callback: (...args: any[]) => void) => void
    sendPetStatus: (text: string) => void
    clearPetStatus: () => void
    isPetVisible: () => Promise<boolean>
    /** 切换宠物动画状态 */
    setPetState?: (
      state:
        | 'idle'
        | 'running-right'
        | 'running-left'
        | 'waving'
        | 'jumping'
        | 'failed'
        | 'waiting'
        | 'running'
        | 'review'
    ) => void

    /** 系统用户主目录 */
    homePath?: string
    /** 弹出系统原生文件/文件夹选择对话框 */
    selectDirectory?: (opts?: any) => Promise<{ path: string | null; cancelled: boolean }>
    selectFile?: (opts?: any) => Promise<{ path: string | null; cancelled: boolean }>
    /** 重启应用 */
    relaunch?: () => void
    /** 完全退出应用（关闭后端） */
    quitApp?: () => void
    /** 确保后端进程已启动（启动页重试） */
    ensureBackend?: () => void

    /** 窗口控制 */
    windowMinimize?: () => void
    windowMaximize?: () => void
    windowClose?: () => void
    windowIsMaximized?: () => Promise<boolean>
    onWindowMaximizedChange?: (callback: (value: boolean) => void) => void

    /** 创建新窗口 */
    createNewWindow?: () => void
  }
}
