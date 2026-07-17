<template>
  <div class="settings-section">
    <!-- 账号列表 -->
    <template v-if="!configPanel">
      <p class="section-desc">绑定第三方账号以启用消息推送</p>
      <div class="account-bind-list">
        <div v-for="account in accountStore.accounts" :key="account.platform" class="account-item">
          <div class="account-icon" :class="account.platform">
            <img v-if="account.platform === 'feishu'" src="@/assets/feishu.svg" alt="飞书" />
            <img v-else-if="account.platform === 'qq'" src="@/assets/qq.svg" alt="QQ" />
            <img v-else src="@/assets/weixin.svg" alt="微信" />
          </div>
          <div class="account-info">
            <span class="account-name">{{ account.name }}</span>
            <span class="account-status" :class="{ bound: account.enabled && account.running }">
              {{ account.enabled && account.running ? '已连接' : account.enabled ? '已启用' : account.configured ? '未启用' : '未配置' }}
            </span>
          </div>
          <div class="account-actions">
            <button
              v-if="!account.configured"
              type="button"
              class="bind-btn"
              @click="openConfigPanel(account.platform)"
            >
              配置
            </button>
            <template v-else>
              <span
                v-if="hasPlatformSession(account.platform)"
                class="chat-link-btn"
                @click="goToPlatformSession(sessionIdFor(account.platform))"
              >
                查看对话
              </span>
              <button
                type="button"
                class="bind-btn"
                @click="openSettingsModal(account.platform)"
              >
                设置
              </button>
            </template>
          </div>
        </div>

        <!-- GitHub 卡片 -->
        <div class="account-item github-item">
          <div class="account-icon github">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
          </div>
          <div class="account-info">
            <span class="account-name">GitHub</span>
            <span class="account-status" :class="{ bound: githubStore.status.connected }">
              {{ githubStore.status.connected ? `已连接 @${githubStore.status.username}` : '未连接' }}
            </span>
          </div>
          <div class="account-actions">
            <button
              v-if="!githubStore.status.connected"
              type="button"
              class="bind-btn"
              @click="openConfigPanel('github')"
              :disabled="githubStore.loading"
            >
              连接
            </button>
            <template v-else>
              <button
                type="button"
                class="bind-btn"
                @click="openGithubSettings()"
              >
                设置
              </button>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- QQ 配置面板 -->
    <div v-if="configPanel === 'qq'" class="config-panel">
      <div class="config-panel-header">
        <button type="button" class="back-btn" @click="closeConfigPanel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        </button>
        <h3>QQ 机器人配置</h3>
      </div>
      <div class="config-form">
        <label class="form-label">App ID</label>
        <input v-model="qqForm.app_id" type="text" class="form-input" placeholder="请输入 QQ 机器人 App ID" />
        <label class="form-label">App Secret</label>
        <input v-model="qqForm.app_secret" type="password" class="form-input" placeholder="请输入 App Secret" />
        <button type="button" class="form-submit-btn" :disabled="!qqForm.app_id || !qqForm.app_secret || configLoading" @click="saveQQ">
          {{ configLoading ? '保存中...' : '保存并启用' }}
        </button>
      </div>
    </div>

    <!-- 微信配置面板（扫码） -->
    <div v-if="configPanel === 'wechat'" class="config-panel">
      <div class="config-panel-header">
        <button type="button" class="back-btn" @click="closeConfigPanel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        </button>
        <h3>微信绑定</h3>
      </div>
      <div class="qrcode-area">
        <template v-if="wechatQRImg">
          <img :src="wechatQRImg" alt="微信二维码" class="qrcode-img" />
          <p class="qrcode-tip">{{ wechatPollStatus === 'scaned' ? '已扫码，请在手机上确认' : '请使用微信扫码绑定' }}</p>
        </template>
        <template v-else>
          <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startWechatQR">
            {{ configLoading ? '获取中...' : '获取二维码' }}
          </button>
        </template>
      </div>
    </div>

    <!-- 飞书配置面板（扫码） -->
    <div v-if="configPanel === 'feishu'" class="config-panel">
      <div class="config-panel-header">
        <button type="button" class="back-btn" @click="closeConfigPanel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        </button>
        <h3>飞书绑定</h3>
      </div>
      <div class="qrcode-area">
        <template v-if="feishuQRImg">
          <img :src="feishuQRImg" alt="飞书二维码" class="qrcode-img" />
          <p class="qrcode-tip">{{ feishuPollStatus === 'pending' ? '请使用飞书 App 扫码授权' : '授权成功' }}</p>
        </template>
        <template v-else>
          <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startFeishuQR">
            {{ configLoading ? '获取中...' : '获取二维码' }}
          </button>
        </template>
      </div>
    </div>

    <!-- GitHub 配置面板 -->
    <div v-if="configPanel === 'github'" class="config-panel">
      <div class="config-panel-header">
        <button type="button" class="back-btn" @click="closeConfigPanel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        </button>
        <h3>GitHub 连接</h3>
      </div>

      <!-- PAT 方式 -->
      <div class="github-pat-section">
        <div class="auth-method-header">
          <span class="auth-method-title">Personal Access Token</span>
          <span class="auth-method-desc">粘贴 GitHub Token 以便 git push/pull 免密</span>
        </div>
        <div class="pat-form">
          <input
            v-model="githubPatToken"
            type="password"
            class="form-input"
            placeholder="ghp_xxxxxxxxxxxx"
            @keyup.enter="connectWithGithubPat"
          />
          <a
            href="https://github.com/settings/tokens/new?scopes=repo,read:user&description=Aries+Agent"
            class="pat-help-link"
            @click.prevent="openExternalLink"
          >
            如何获取 Token？
          </a>
          <button
            type="button"
            class="form-submit-btn"
            @click="connectWithGithubPat"
            :disabled="!githubPatToken.trim() || githubStore.loading"
          >
            {{ githubStore.loading ? '验证中...' : '连接 GitHub' }}
          </button>
        </div>
      </div>

      <!-- 错误提示 -->
      <p v-if="githubStore.error" class="error-tip">{{ githubStore.error }}</p>
    </div>

    <!-- GitHub 设置弹窗 -->
    <div v-if="showGithubSettingsModal" class="modal-overlay" @click="closeGithubSettingsModal">
      <div class="modal-dialog settings-dialog" @click.stop>
        <div class="modal-header">GitHub 设置</div>
        <div class="modal-body">
          <div class="github-user-info" v-if="githubStore.status.connected">
            <img
              :src="githubStore.status.avatar_url || ''"
              :alt="githubStore.status.username || ''"
              class="github-avatar"
            />
            <div class="github-user-details">
              <span class="github-username">@{{ githubStore.status.username }}</span>
              <span class="github-name" v-if="githubStore.status.name">{{ githubStore.status.name }}</span>
              <div class="github-scope-tags">
                <span v-for="scope in githubStore.status.scope" :key="scope" class="scope-tag">{{ scope }}</span>
              </div>
            </div>
          </div>

          <div class="settings-row">
            <button type="button" class="unbind-inline-btn" @click="disconnectGithub">
              断开连接
            </button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="closeGithubSettingsModal">关闭</button>
        </div>
      </div>
    </div>

    <!-- 平台配置弹窗 -->
    <div v-if="showSettingsModal" class="modal-overlay" @click="closeSettingsModal">
      <div class="modal-dialog settings-dialog" @click.stop>
        <div class="modal-header">{{ settingsPlatformName }} 配置</div>
        <div class="modal-body">
          <div class="settings-form">
            <label class="form-label">工作目录</label>
            <div class="workdir-input-row">
              <input v-model="settingsForm.work_dir" type="text" class="form-input" :placeholder="defaultWorkDirPlaceholder" />
              <button type="button" class="select-dir-btn" @click="selectWorkDir">选择目录</button>
            </div>
            <p class="form-hint">留空则使用默认工作目录</p>
            <label class="form-label">性格（系统提示词）</label>
            <textarea v-model="settingsForm.system_prompt" class="form-textarea" placeholder="自定义该平台的系统提示词，留空使用默认" rows="4"></textarea>
            <p class="form-hint">配置机器人的回复风格和行为规范</p>
            <div class="settings-row">
              <button type="button" class="unbind-inline-btn" @click="unbindInSettings">解绑该平台</button>
              <button type="button" class="toggle-btn" :class="{ enabled: settingsForm.enabled }" @click="settingsForm.enabled = !settingsForm.enabled">
                {{ settingsForm.enabled ? '已启用' : '已禁用' }}
              </button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="closeSettingsModal">取消</button>
          <button class="modal-btn modal-btn-primary" :disabled="settingsSaving" @click="saveSettings">
            {{ settingsSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useGithubStore } from '@/stores/github'
import {
  saveQQConfig,
  saveFeishuConfig,
  saveWeChatConfig,
  getPlatform,
  listActivePlatforms,
  wechatQRCode,
  wechatQRCodePoll,
  feishuQRCode,
  feishuQRCodePoll,
  cancelFeishuRegistration,
} from '@/api/platform'
import { selectDirectory } from '@/api/system'
import { defaultWorkDir, initPaths } from '@/utils/paths'

const accountStore = useAccountStore()
const githubStore = useGithubStore()

const configPanel = ref('')
const configLoading = ref(false)
const qqForm = ref({ app_id: '', app_secret: '' })

// 微信扫码
const wechatQRImg = ref('')
const wechatQRKey = ref('')
const wechatPollStatus = ref('')
let wechatPollTimer: ReturnType<typeof setInterval> | null = null

// 飞书扫码
const feishuQRImg = ref('')
const feishuPollStatus = ref('')
let feishuPollTimer: ReturnType<typeof setInterval> | null = null

// GitHub
const githubPatToken = ref('')
const showGithubSettingsModal = ref(false)

// ---------- 平台配置弹窗 ----------
const showSettingsModal = ref(false)
const settingsPlatform = ref('')
const settingsPlatformName = ref('')
const settingsForm = ref({ work_dir: '', system_prompt: '', enabled: false })
const settingsSaving = ref(false)

// ---------- 平台对话列表 ----------
const platformSessions = ref<{ id: string; name: string; platform: string }[]>([])

async function loadPlatformSessions() {
  try {
    const data = await listActivePlatforms()
    platformSessions.value = (data.platforms || []).map((p: any) => ({
      id: p.session_id,
      name: p.name,
      platform: p.platform,
    }))
  } catch {
    platformSessions.value = []
  }
}

function goToPlatformSession(sessionId: string) {
  window.dispatchEvent(new CustomEvent('aries:open-session', { detail: sessionId }))
}

function sessionIdFor(platform: string): string {
  return `__${platform}__`
}

function hasPlatformSession(platform: string): boolean {
  return platformSessions.value.some(s => s.platform === platform)
}

const PLATFORM_LABELS: Record<string, string> = { qq: 'QQ', wechat: '微信', feishu: '飞书' }

const defaultWorkDirPlaceholder = computed(() => `留空则使用默认 ${defaultWorkDir.value}`)

async function openSettingsModal(platform: string) {
  settingsPlatform.value = platform
  settingsPlatformName.value = PLATFORM_LABELS[platform] || platform
  try {
    const detail = await getPlatform(platform)
    const conf = detail.config || {}
    settingsForm.value = {
      work_dir: conf.work_dir || '',
      system_prompt: conf.system_prompt || '',
      enabled: detail.enabled || false,
    }
  } catch {
    settingsForm.value = { work_dir: '', system_prompt: '', enabled: false }
  }
  showSettingsModal.value = true
}

function closeSettingsModal() {
  showSettingsModal.value = false
}

async function selectWorkDir() {
  try {
    const electronAPI = (window as any).electronAPI
    let result
    if (electronAPI?.selectDirectory) {
      result = await electronAPI.selectDirectory({ title: '选择工作目录' })
    } else {
      result = await selectDirectory()
    }
    if (!result.cancelled && result.path) {
      settingsForm.value.work_dir = result.path
    }
  } catch (e: any) {
    alert(e.message || '选择目录失败')
  }
}

async function saveSettings() {
  settingsSaving.value = true
  try {
    const platform = settingsPlatform.value
    const payload = {
      enabled: settingsForm.value.enabled,
      mode: 'agent',
      work_dir: settingsForm.value.work_dir,
      system_prompt: settingsForm.value.system_prompt,
    }
    if (platform === 'qq') {
      await saveQQConfig({ ...payload, app_id: '', app_secret: '' })
    } else if (platform === 'feishu') {
      await saveFeishuConfig({ ...payload, app_id: '', app_secret: '' })
    } else if (platform === 'wechat') {
      await saveWeChatConfig(payload)
    }
    showSettingsModal.value = false
    await accountStore.fetchAccounts()
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    settingsSaving.value = false
  }
}

async function unbindInSettings() {
  const platform = settingsPlatform.value
  if (!platform) return
  if (!confirm(`确定要解绑${PLATFORM_LABELS[platform] || platform}吗？此操作会清除该平台的所有配置。`)) return
  await accountStore.unbind(platform)
  showSettingsModal.value = false
}

function openConfigPanel(platform: string) {
  if (configPanel.value === 'feishu' && platform !== 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  configPanel.value = platform
  qqForm.value = { app_id: '', app_secret: '' }
  wechatQRImg.value = ''
  wechatQRKey.value = ''
  wechatPollStatus.value = ''
  feishuQRImg.value = ''
  feishuPollStatus.value = ''
}

function closeConfigPanel() {
  if (configPanel.value === 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  stopWechatPoll()
  stopFeishuPoll()
  configPanel.value = ''
}

async function saveQQ() {
  configLoading.value = true
  try {
    await saveQQConfig({
      enabled: true,
      app_id: qqForm.value.app_id,
      app_secret: qqForm.value.app_secret,
      mode: 'agent',
    })
    configPanel.value = ''
    await accountStore.fetchAccounts()
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    configLoading.value = false
  }
}

async function startWechatQR() {
  configLoading.value = true
  try {
    const res = await wechatQRCode()
    if (res.success && res.qrcode_img) {
      wechatQRImg.value = res.qrcode_img
      wechatQRKey.value = res.qrcode_key || ''
      wechatPollStatus.value = 'pending'
      startWechatPoll()
    } else {
      alert(res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startWechatPoll() {
  stopWechatPoll()
  wechatPollTimer = setInterval(async () => {
    try {
      const res = await wechatQRCodePoll(wechatQRKey.value || undefined)
      wechatPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopWechatPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'expired') {
        stopWechatPoll()
        wechatQRImg.value = ''
      }
    } catch {
      // ignore
    }
  }, 3000)
}

function stopWechatPoll() {
  if (wechatPollTimer) {
    clearInterval(wechatPollTimer)
    wechatPollTimer = null
  }
}

async function startFeishuQR() {
  configLoading.value = true
  try {
    const res = await feishuQRCode()
    if (res.success && res.qrcode_img) {
      feishuQRImg.value = res.qrcode_img
      feishuPollStatus.value = 'pending'
      startFeishuPoll()
    } else if (res.phase === 'configured' || res.phase === 'authorized') {
      feishuPollStatus.value = 'confirmed'
      configPanel.value = ''
      await accountStore.fetchAccounts()
    } else {
      alert(res.message || res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startFeishuPoll() {
  stopFeishuPoll()
  feishuPollTimer = setInterval(async () => {
    try {
      const res = await feishuQRCodePoll()
      feishuPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopFeishuPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'error') {
        stopFeishuPoll()
        feishuQRImg.value = ''
      }
    } catch {
      // ignore
    }
  }, 3000)
}

function stopFeishuPoll() {
  if (feishuPollTimer) {
    clearInterval(feishuPollTimer)
    feishuPollTimer = null
  }
}

// ---------- GitHub ----------

/** 使用系统默认浏览器打开链接 */
function openExternalLink(e: MouseEvent) {
  const href = (e.currentTarget as HTMLAnchorElement).href
  const electronAPI = (window as any).electronAPI
  if (electronAPI?.openExternal) {
    electronAPI.openExternal(href)
  } else {
    window.open(href, '_blank')
  }
}

async function connectWithGithubPat() {
  const token = githubPatToken.value.trim()
  if (!token) return

  const success = await githubStore.connectWithToken(token)
  if (success) {
    githubPatToken.value = ''
    configPanel.value = ''
  }
}

function openGithubSettings() {
  showGithubSettingsModal.value = true
}

function closeGithubSettingsModal() {
  showGithubSettingsModal.value = false
}

async function disconnectGithub() {
  if (!confirm('确定要断开 GitHub 连接吗？')) return
  const success = await githubStore.disconnect()
  if (success) {
    showGithubSettingsModal.value = false
  }
}

onMounted(() => {
  initPaths()
  accountStore.fetchAccounts()
  loadPlatformSessions()
  githubStore.fetchStatus()
})

onUnmounted(() => {
  stopWechatPoll()
  stopFeishuPoll()
})
</script>

<style scoped>
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.account-bind-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.account-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.account-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.account-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.account-status {
  font-size: 12px;
  color: var(--text-muted);
}

.account-status.bound { color: #2d7a4f; }

.bind-btn {
  padding: 6px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.bind-btn:hover { background: var(--accent-hover); }
.bind-btn.bound { background: #e8f5ee; border-color: #b8dfc8; color: #2d7a4f; }

.account-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.unbind-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.unbind-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
}

.config-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-panel-header h3 {
  font-size: 15px;
  font-weight: 600;
}

.back-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.back-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: var(--border-strong);
}

.form-submit-btn {
  padding: 8px 16px;
  background: #2d7a4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
  margin-top: 4px;
}

.form-submit-btn:hover { opacity: 0.9; }
.form-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.qrcode-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.qrcode-img {
  width: 180px;
  height: 180px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.qrcode-tip {
  font-size: 13px;
  color: var(--text-secondary);
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-dialog {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 320px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.modal-body {
  padding: 20px;
  color: var(--text);
}

.modal-body p {
  margin: 0;
  line-height: 1.5;
}

.modal-footer {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.modal-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.modal-btn:hover {
  opacity: 0.85;
}

.modal-btn-cancel {
  background: #e5e7eb;
  color: #374151;
}

.modal-btn-danger {
  background: #1f2937;
  color: #ffffff;
}

/* 平台配置弹窗 */
.settings-dialog {
  min-width: 420px;
  max-width: 500px;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-textarea {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
  resize: vertical;
  font-family: inherit;
  min-height: 80px;
}

.form-textarea:focus {
  border-color: var(--border-strong);
}

.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: -4px 0 4px 0;
}

.settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.workdir-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workdir-input-row .form-input {
  flex: 1;
}

.select-dir-btn {
  padding: 8px 14px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.select-dir-btn:hover {
  background: var(--accent-hover);
}

.toggle-btn {
  padding: 6px 16px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.toggle-btn.enabled {
  background: #e8f5ee;
  border-color: #b8dfc8;
  color: #2d7a4f;
}

.unbind-inline-btn {
  margin-top: 12px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  align-self: flex-start;
}

.unbind-inline-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
}

.modal-btn-primary {
  background: #2d7a4f;
  color: #fff;
}

.chat-link-btn {
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  transition: all 0.15s;
  user-select: none;
}

.chat-link-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

/* ---------- GitHub 卡片 ---------- */
.account-icon.github {
  background: #24292e;
  color: #fff;
}

.account-icon.github svg {
  width: 22px;
  height: 22px;
}

/* ---------- GitHub 配置面板 ---------- */
.github-pat-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.auth-method-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.auth-method-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.auth-method-desc {
  font-size: 12px;
  color: var(--text-muted);
}

/* PAT 表单 */
.pat-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pat-help-link {
  font-size: 12px;
  color: #2563eb;
  text-decoration: none;
  align-self: flex-start;
}

.pat-help-link:hover {
  text-decoration: underline;
}

.error-tip {
  font-size: 12px;
  color: #991b1b;
  background: #fee2e2;
  padding: 8px 12px;
  border-radius: 6px;
  margin: 0;
}

/* ---------- GitHub 设置弹窗 ---------- */
.github-user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0 16px;
}

.github-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  border: 2px solid var(--border);
}

.github-user-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.github-username {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.github-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.github-scope-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.scope-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--accent-hover);
  color: var(--text-secondary);
}
</style>
