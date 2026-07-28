<template>
  <AuthShell title="Aries Cloud" subtitle="欢迎回来，请登录您的账号">
    <form @submit.prevent="handleLogin" style="display: flex; flex-direction: column; gap: var(--spacer-16);">
      <!-- 邮箱 -->
      <div>
        <label class="ds-label" for="login-email">邮箱</label>
        <input
          id="login-email"
          v-model="email"
          type="email"
          required
          autocomplete="email"
          placeholder="请输入邮箱"
          class="ds-input"
        />
      </div>

      <!-- 密码 -->
      <div>
        <label class="ds-label" for="login-password">密码</label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          required
          autocomplete="current-password"
          placeholder="请输入密码"
          class="ds-input"
        />
      </div>

      <!-- 错误提示 -->
      <div v-if="error" class="ds-alert ds-alert-error">
        {{ error }}
      </div>

      <!-- 登录按钮（单一品牌 CTA） -->
      <button
        type="submit"
        :disabled="loading"
        class="ds-btn ds-btn-primary ds-btn-block"
      >
        <span v-if="loading">登录中…</span>
        <span v-else>登录</span>
      </button>
    </form>

    <!-- 底部跳转 -->
    <p
      style="
        text-align: center;
        font-size: var(--body-base-font-size);
        color: var(--text-tertiary);
        margin-top: var(--spacer-24);
      "
    >
      还没有账号？
      <router-link to="/register" class="ds-link">立即注册</router-link>
    </p>
  </AuthShell>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AuthShell from '../components/AuthShell.vue'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (err) {
    error.value = err.response?.data?.detail || '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>
