import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/Register.vue'),
  },
  {
    // 空对话（新建/欢迎页）
    path: '/',
    name: 'chat',
    component: () => import('../views/ChatPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    // 指定会话：/session/:sessionId
    path: '/session/:sessionId',
    name: 'chat-session',
    component: () => import('../views/ChatPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/automation',
    name: 'automation',
    component: () => import('../views/AutomationPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/agents',
    name: 'agents',
    component: () => import('../views/SubagentsPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/skills',
    name: 'skills',
    component: () => import('../views/SkillsPage.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) {
    return { name: 'chat' }
  }
  if ((to.name === 'login' || to.name === 'register') && auth.token) {
    return { name: 'chat' }
  }
})

export default router
