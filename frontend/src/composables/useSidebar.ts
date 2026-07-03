import { ref } from 'vue'

const SIDEBAR_WIDTH_KEY = 'aries:sidebar-width'
export const SIDEBAR_WIDTH_DEFAULT = 260
export const SIDEBAR_WIDTH_MIN = 200
export const SIDEBAR_WIDTH_MAX = 480

const sidebarOpen = ref(true)

function readStoredWidth(): number {
  try {
    const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY)
    if (raw) {
      const n = parseInt(raw, 10)
      if (!Number.isNaN(n)) {
        return Math.min(Math.max(n, SIDEBAR_WIDTH_MIN), SIDEBAR_WIDTH_MAX)
      }
    }
  } catch { /* ignore */ }
  return SIDEBAR_WIDTH_DEFAULT
}

const sidebarWidth = ref(readStoredWidth())

export function useSidebar() {
  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  function setSidebarOpen(open: boolean) {
    sidebarOpen.value = open
  }

  function clampSidebarWidth(width: number) {
    return Math.min(Math.max(width, SIDEBAR_WIDTH_MIN), SIDEBAR_WIDTH_MAX)
  }

  function persistSidebarWidth() {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
    } catch { /* ignore */ }
  }

  return {
    sidebarOpen,
    sidebarWidth,
    toggleSidebar,
    setSidebarOpen,
    clampSidebarWidth,
    persistSidebarWidth,
    SIDEBAR_WIDTH_MIN,
    SIDEBAR_WIDTH_MAX,
  }
}
