<template>
  <AuthShell title="注册账号" subtitle="创建您的 Aries Cloud 账号">
    <form @submit.prevent="handleRegister" style="display: flex; flex-direction: column; gap: var(--spacer-16);">
      <!-- 邮箱 + 发送验证码 -->
      <div>
        <label class="ds-label" for="register-email">邮箱</label>
        <div style="display: flex; gap: var(--spacer-8);">
          <input
            id="register-email"
            v-model="email"
            type="email"
            required
            autocomplete="email"
            placeholder="请输入邮箱"
            class="ds-input"
          />
          <button
            type="button"
            @click="handleSendCode"
            :disabled="countdown > 0 || sendingCode"
            class="ds-btn ds-btn-secondary"
            style="flex-shrink: 0;"
          >
            <span v-if="sendingCode">发送中…</span>
            <span v-else-if="countdown > 0">{{ countdown }}s</span>
            <span v-else>发送验证码</span>
          </button>
        </div>
      </div>

      <!-- 验证码 -->
      <div>
        <label class="ds-label" for="register-code">验证码</label>
        <input
          id="register-code"
          v-model="code"
          type="text"
          required
          maxlength="6"
          inputmode="numeric"
          placeholder="请输入6位验证码"
          class="ds-input"
        />
      </div>

      <!-- 用户名 -->
      <div>
        <label class="ds-label" for="register-username">用户名</label>
        <input
          id="register-username"
          v-model="username"
          type="text"
          required
          autocomplete="username"
          placeholder="显示名称，可与他人重复"
          class="ds-input"
        />
      </div>

      <!-- 密码 -->
      <div>
        <label class="ds-label" for="register-password">密码</label>
        <input
          id="register-password"
          v-model="password"
          type="password"
          required
          autocomplete="new-password"
          placeholder="请输入密码"
          class="ds-input"
        />
      </div>

      <!-- 提示 -->
      <div v-if="error" class="ds-alert ds-alert-error">
        {{ error }}
      </div>
      <div v-if="success" class="ds-alert ds-alert-success">
        {{ success }}
      </div>

      <!-- 注册按钮（单一品牌 CTA） -->
      <button
        type="submit"
        :disabled="loading"
        class="ds-btn ds-btn-primary ds-btn-block"
      >
        <span v-if="loading">注册中…</span>
        <span v-else>注册</span>
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
      已有账号？
      <router-link to="/login" class="ds-link">返回登录</router-link>
    </p>
  </AuthShell>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AuthShell from '../components/AuthShell.vue'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const code = ref('')
const username = ref('')
const password = ref('')
const error = ref('')
const success = ref('')
const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)
let timer = null

async function handleSendCode() {
  if (!email.value) {
    error.value = '请先输入邮箱'
    return
  }
  error.value = ''
  sendingCode.value = true
  try {
    await auth.sendCode(email.value)
    success.value = '验证码已发送，请查收邮箱'
    countdown.value = 60
    timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  } catch (err) {
    error.value = err.response?.data?.detail || '验证码发送失败'
  } finally {
    sendingCode.value = false
  }
}

async function handleRegister() {
  error.value = ''
  loading.value = true
  try {
    await auth.register(email.value, code.value, username.value, password.value)
    router.push('/')
  } catch (err) {
    error.value = err.response?.data?.detail || '注册失败，请重试'
  } finally {
    loading.value = false
  }
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
