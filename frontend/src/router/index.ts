import { createRouter, createWebHashHistory } from 'vue-router'
import MainLayout from '@/views/MainLayout.vue'

const routes = [
  {
    path: '/',
    component: MainLayout,
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
