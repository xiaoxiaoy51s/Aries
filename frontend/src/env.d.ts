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
  }
}
