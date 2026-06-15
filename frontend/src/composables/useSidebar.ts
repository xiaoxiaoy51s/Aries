import { ref } from 'vue'

const sidebarOpen = ref(true)

export function useSidebar() {
  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  function setSidebarOpen(open: boolean) {
    sidebarOpen.value = open
  }

  return { sidebarOpen, toggleSidebar, setSidebarOpen }
}
