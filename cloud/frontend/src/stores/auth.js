import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(tokenValue, userValue) {
    token.value = tokenValue
    user.value = userValue
    localStorage.setItem('token', tokenValue)
    localStorage.setItem('user', JSON.stringify(userValue))
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  async function login(email, password) {
    const res = await api.post('/api/auth/login', { email, password })
    setAuth(res.data.access_token, res.data.user)
    return res.data
  }

  async function register(email, code, username, password) {
    const res = await api.post('/api/auth/register', { email, code, username, password })
    setAuth(res.data.access_token, res.data.user)
    return res.data
  }

  async function sendCode(email) {
    const res = await api.post('/api/auth/send-code', { email })
    return res.data
  }

  function logout() {
    clearAuth()
  }

  return { token, user, isLoggedIn, login, register, sendCode, logout }
})
