import { defineStore } from 'pinia'
import { ref } from 'vue'
import { setLocale } from '../i18n'

export const useSettingsStore = defineStore('settings', () => {
  const language = ref(localStorage.getItem('language') || 'zh')
  const theme = ref(localStorage.getItem('theme') || 'light')
  const settingsOpen = ref(false)

  function applyTheme() {
    const root = document.documentElement
    let actual = theme.value
    if (actual === 'system') {
      actual = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    root.dataset.theme = actual
    root.classList.toggle('dark', actual === 'dark')
  }

  function setLanguage(lang) {
    language.value = lang
    setLocale(lang)
    localStorage.setItem('language', lang)
  }

  function setTheme(t) {
    theme.value = t
    localStorage.setItem('theme', t)
    applyTheme()
  }

  function openSettings() {
    settingsOpen.value = true
  }

  function closeSettings() {
    settingsOpen.value = false
  }

  // 初始化
  applyTheme()
  // 监听系统主题变化
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (theme.value === 'system') applyTheme()
  })

  return { language, theme, settingsOpen, setLanguage, setTheme, openSettings, closeSettings, applyTheme }
})
