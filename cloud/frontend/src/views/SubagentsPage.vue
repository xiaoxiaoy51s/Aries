<template>
  <div class="chat-app">
    <ChatSidebar
      :sidebar-open="sidebarOpen"
      :sessions="sessions"
      :current-session-id="null"
      :user="auth.user"
      @toggle-sidebar="sidebarOpen = !sidebarOpen"
      @create-new-chat="goToChat"
      @select-session="goToSession"
      @logout="handleLogout"
    />
    <div class="agents-page">
      <header class="agents-head">
        <div class="agents-head-left">
          <h2 class="agents-title">{{ t('agents.title') }}</h2>
          <p class="agents-desc">{{ t('agents.desc') }}</p>
        </div>
        <button type="button" class="ds-btn ds-btn-primary agents-create-btn" @click="openCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('agents.create') }}
        </button>
      </header>

      <!-- Tab 切换：官方 / 我的 -->
      <nav class="agents-tabs">
        <button
          type="button"
          class="agent-tab"
          :class="{ active: activeTab === 'official' }"
          @click="activeTab = 'official'"
        >
          {{ t('agents.official') }}
          <span class="tab-count">{{ officialAgents.length }}</span>
        </button>
        <button
          type="button"
          class="agent-tab"
          :class="{ active: activeTab === 'personal' }"
          @click="activeTab = 'personal'"
        >
          {{ t('agents.personal') }}
          <span class="tab-count">{{ personalAgents.length }}</span>
        </button>
      </nav>

      <div class="agents-body">
        <div v-if="loading && agents.length === 0" class="agents-empty">
          <div class="empty-spinner"></div>
          <span>{{ t('agents.loading') }}</span>
        </div>

        <div v-else-if="activeAgents.length === 0" class="agents-empty">
          <div class="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M8 4h8"/><path d="M8 14h.01M16 14h.01"/></svg>
          </div>
          <p class="empty-title">{{ activeTab === 'official' ? t('agents.officialEmpty') : t('agents.personalEmpty') }}</p>
          <p v-if="activeTab === 'personal'" class="empty-hint">{{ t('agents.personalEmptyHint') }}</p>
          <button
            v-if="activeTab === 'personal'"
            type="button"
            class="ds-btn ds-btn-primary empty-action"
            @click="openCreate"
          >
            {{ t('agents.create') }}
          </button>
        </div>

        <div v-else class="agents-grid">
          <div
            v-for="agent in activeAgents"
            :key="agent.name"
            class="agent-card"
            :class="{ disabled: !agent.enabled }"
            @click="openDetail(agent)"
          >
            <div class="agent-card-head">
              <div class="agent-avatar" :class="{ 'official-avatar': isOfficial(agent) }">
                <img v-if="agent.avatar_data" :src="agent.avatar_data" :alt="agent.name" />
                <span v-else-if="isOfficial(agent)" class="agent-avatar-default">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M8 4h8"/><path d="M8 14h.01M16 14h.01"/></svg>
                </span>
                <span v-else class="agent-avatar-default">{{ (agent.name || '?').charAt(0).toUpperCase() }}</span>
              </div>
              <div class="agent-card-titles">
                <h3 class="agent-card-title">{{ agent.name }}</h3>
                <span v-if="isOfficial(agent)" class="agent-badge-official">
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>
                  {{ t('agents.officialBadge') }}
                </span>
                <span v-else class="agent-scope">{{ t('agents.scopePrivate') }}</span>
              </div>
            </div>
            <p class="agent-card-desc">{{ agent.description || t('agents.noDesc') }}</p>
            <div class="agent-card-meta" @click.stop>
              <label class="agent-switch">
                <input
                  type="checkbox"
                  :checked="agent.main_enabled"
                  @change="(e) => toggleMain(agent, e.target.checked)"
                />
                <span>{{ t('agents.mainEnabled') }}</span>
              </label>
            </div>
            <div class="agent-card-actions" @click.stop>
              <button type="button" class="agent-btn" @click="openDetail(agent)">{{ t('agents.view') }}</button>
              <button type="button" class="agent-btn" @click="chatAsAgent(agent)">{{ t('agents.chatAs') }}</button>
              <template v-if="!isOfficial(agent)">
                <button type="button" class="agent-btn" @click="openEdit(agent)">{{ t('agents.edit') }}</button>
                <button type="button" class="agent-btn danger" @click="removeAgent(agent)">{{ t('agents.delete') }}</button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div v-if="errorMessage" class="agents-error" @click="errorMessage = ''">{{ errorMessage }}</div>
    </div>

    <!-- 详情 -->
    <div v-if="detail" class="modal-overlay" @click="detail = null">
      <div class="modal-dialog modal-wide" @click.stop>
        <div class="modal-header">
          <div class="detail-head">
            <div class="agent-avatar lg" :class="{ 'official-avatar': isOfficial(detail) }">
              <img v-if="detail.avatar_data" :src="detail.avatar_data" :alt="detail.name" />
              <span v-else-if="isOfficial(detail)" class="agent-avatar-default">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M8 4h8"/><path d="M8 14h.01M16 14h.01"/></svg>
              </span>
              <span v-else class="agent-avatar-default">{{ (detail.name || '?').charAt(0).toUpperCase() }}</span>
            </div>
            <div>
              <div class="detail-title-row">
                <span>{{ detail.name }}</span>
                <span v-if="isOfficial(detail)" class="agent-badge-official">
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>
                  {{ t('agents.officialBadge') }}
                </span>
              </div>
              <div class="detail-sub">
                {{ isOfficial(detail) ? t('agents.officialBadge') : t('agents.scopePrivate') }}
              </div>
            </div>
          </div>
        </div>
        <div class="modal-body">
          <p class="detail-desc">{{ detail.description || t('agents.noDesc') }}</p>
          <label class="form-label">{{ t('agents.skills') }}</label>
          <div class="chip-row">
            <span v-for="s in (detail.allowed_skills || [])" :key="s" class="chip">{{ s }}</span>
            <span v-if="!(detail.allowed_skills || []).length" class="muted">—</span>
          </div>
          <label class="form-label">{{ t('agents.systemPrompt') }}</label>
          <div class="detail-md">
            <MarkdownRenderer :content="detail.system_prompt || ''" :show-actions="false" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="ds-btn" @click="detail = null">{{ t('agents.cancel') }}</button>
          <button type="button" class="ds-btn" @click="chatAsAgent(detail); detail = null">{{ t('agents.chatAs') }}</button>
          <button
            v-if="!isOfficial(detail)"
            type="button"
            class="ds-btn ds-btn-primary"
            @click="openEdit(detail); detail = null"
          >{{ t('agents.edit') }}</button>
        </div>
      </div>
    </div>

    <!-- 新建/编辑 -->
    <div v-if="dialogVisible" class="modal-overlay" @click="closeDialog">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">{{ dialogMode === 'create' ? t('agents.dialogCreate') : t('agents.dialogEdit', { name: form.name }) }}</div>
        <div class="modal-body">
          <label class="form-label">{{ t('agents.name') }}</label>
          <input
            v-model="form.name"
            class="form-input"
            :disabled="dialogMode === 'edit'"
            :placeholder="t('agents.nameHint')"
          />
          <label class="form-label">{{ t('agents.description') }}</label>
          <input v-model="form.description" class="form-input" :placeholder="t('agents.descriptionHint')" />

          <!-- 头像上传 -->
          <label class="form-label">{{ t('agents.avatar') }}</label>
          <div class="avatar-uploader" @click="$refs.avatarInput.click()">
            <input
              ref="avatarInput"
              type="file"
              accept="image/*"
              class="avatar-uploader-input"
              @change="onAvatarPick"
            />
            <div class="avatar-uploader-box">
              <img v-if="form.avatarPreview" :src="form.avatarPreview" alt="avatar" />
              <div v-else class="avatar-uploader-placeholder">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
              </div>
              <div class="avatar-uploader-mask">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                <span>{{ form.avatarPreview ? t('agents.avatarChange') : t('agents.avatarUpload') }}</span>
              </div>
            </div>
            <div class="avatar-uploader-meta">
              <span class="avatar-uploader-title">{{ form.avatarPreview ? t('agents.avatarChange') : t('agents.avatarUpload') }}</span>
              <span class="avatar-uploader-hint">{{ t('agents.avatarHint') }}</span>
            </div>
          </div>

          <label class="form-label">{{ t('agents.skills') }}</label>
          <div class="skill-checks">
            <label v-for="s in skillOptions" :key="s.folder_name" class="skill-check">
              <input
                type="checkbox"
                :checked="form.allowed_skills.includes(s.folder_name)"
                @change="(e) => toggleSkill(s.folder_name, e.target.checked)"
              />
              <span>{{ s.name }}</span>
            </label>
            <div v-if="skillOptions.length === 0" class="muted">{{ t('skills.empty') }}</div>
          </div>
          <label class="form-label">{{ t('agents.systemPrompt') }}</label>
          <textarea
            v-model="form.system_prompt"
            class="form-textarea"
            rows="12"
            :placeholder="t('agents.systemPromptHint')"
          />
        </div>
        <div class="modal-footer">
          <button type="button" class="ds-btn" @click="closeDialog">{{ t('agents.cancel') }}</button>
          <button type="button" class="ds-btn ds-btn-primary" :disabled="saving" @click="saveDialog">
            {{ saving ? t('agents.saving') : t('agents.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
  <SettingsModal v-if="settingsStore.settingsOpen" />
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useI18n } from '../i18n'
import api from '../api'
import {
  listSubagents,
  getSubagent,
  createSubagent,
  updateSubagent,
  deleteSubagent,
  setMainEnabled,
} from '../api/subagents'
import { listSkills } from '../api/skills'
import ChatSidebar from './ChatSidebar.vue'
import SettingsModal from '../components/SettingsModal.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { ElMessageBox } from 'element-plus'
import { useSettingsStore } from '../stores/settings'
import './ChatPage.css'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const settingsStore = useSettingsStore()

const sidebarOpen = ref(true)
const sessions = ref([])
const agents = ref([])
const skillOptions = ref([])
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const dialogVisible = ref(false)
const dialogMode = ref('create')
const detail = ref(null)
const activeTab = ref('official')
const form = ref({
  name: '',
  description: '',
  system_prompt: '',
  enabled: true,
  allowed_skills: [],
  allowed_mcps: [],
  avatar: '',
  avatarPreview: '',
})

// 判断是否为官方智能体：scope 不为 private 的视为官方
function isOfficial(agent) {
  return agent && agent.scope !== 'private'
}

const officialAgents = computed(() => agents.value.filter(isOfficial))
const personalAgents = computed(() => agents.value.filter((a) => !isOfficial(a)))
const activeAgents = computed(() =>
  activeTab.value === 'official' ? officialAgents.value : personalAgents.value
)

// 官方为空时自动切到个人 tab；个人为空时切回官方
watch([officialAgents, personalAgents], ([o, p]) => {
  if (activeTab.value === 'official' && o.length === 0 && p.length > 0) activeTab.value = 'personal'
  else if (activeTab.value === 'personal' && p.length === 0 && o.length > 0) activeTab.value = 'official'
})

async function loadSessions() {
  try {
    const res = await api.get('/api/chat/sessions')
    sessions.value = res.data || []
  } catch {
    sessions.value = []
  }
}

async function loadAgents() {
  loading.value = true
  errorMessage.value = ''
  try {
    agents.value = await listSubagents()
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadSkillOptions() {
  try {
    skillOptions.value = await listSkills()
  } catch {
    skillOptions.value = []
  }
}

function goToChat() {
  router.push({ name: 'chat' })
}

function goToSession(s) {
  router.push({ name: 'chat-session', params: { sessionId: s.id } })
}

function handleLogout() {
  auth.logout()
  router.push({ name: 'login' })
}

function chatAsAgent(agent) {
  router.push({ name: 'chat', query: { agent: agent.name } })
}

async function openDetail(agent) {
  try {
    detail.value = await getSubagent(agent.name)
  } catch (e) {
    // list 已有完整字段时直接展示
    detail.value = agent
  }
}

function openCreate() {
  dialogMode.value = 'create'
  form.value = {
    name: '',
    description: '',
    system_prompt: '',
    enabled: true,
    allowed_skills: [],
    allowed_mcps: [],
    avatar: '',
    avatarPreview: '',
  }
  dialogVisible.value = true
}

function openEdit(agent) {
  dialogMode.value = 'edit'
  form.value = {
    name: agent.name,
    description: agent.description || '',
    system_prompt: agent.system_prompt || '',
    enabled: agent.enabled !== false,
    allowed_skills: [...(agent.allowed_skills || [])],
    allowed_mcps: [...(agent.allowed_mcps || [])],
    avatar: '',
    avatarPreview: agent.avatar_data || '',
  }
  dialogVisible.value = true
}

function closeDialog() {
  dialogVisible.value = false
}

function onAvatarPick(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    form.value.avatar = String(reader.result || '')
    form.value.avatarPreview = form.value.avatar
  }
  reader.readAsDataURL(file)
  e.target.value = ''
}

function toggleSkill(name, checked) {
  const set = new Set(form.value.allowed_skills)
  if (checked) set.add(name)
  else set.delete(name)
  form.value.allowed_skills = [...set]
}

async function saveDialog() {
  const name = (form.value.name || '').trim()
  const prompt = (form.value.system_prompt || '').trim()
  if (!name) {
    errorMessage.value = t('agents.nameRequired')
    return
  }
  if (!prompt) {
    errorMessage.value = t('agents.promptRequired')
    return
  }
  saving.value = true
  errorMessage.value = ''
  const payload = {
    name,
    description: form.value.description,
    system_prompt: prompt,
    enabled: form.value.enabled,
    allowed_skills: form.value.allowed_skills,
    allowed_mcps: form.value.allowed_mcps,
    avatar: form.value.avatar.startsWith('data:') ? form.value.avatar : '',
  }
  try {
    if (dialogMode.value === 'create') {
      await createSubagent(payload)
    } else {
      await updateSubagent(name, payload)
    }
    closeDialog()
    await loadAgents()
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleMain(agent, enabled) {
  try {
    const updated = await setMainEnabled(agent.name, enabled)
    const idx = agents.value.findIndex((a) => a.name === agent.name)
    if (idx >= 0) agents.value[idx] = updated
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '更新失败'
    await loadAgents()
  }
}

async function removeAgent(agent) {
  try {
    await ElMessageBox.confirm(
      t('agents.deleteConfirm', { name: agent.name }),
      t('agents.deleteTitle'),
      {
        type: 'warning',
        confirmButtonText: t('agents.delete'),
        cancelButtonText: t('agents.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await deleteSubagent(agent.name)
    await loadAgents()
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '删除失败'
  }
}

onMounted(async () => {
  await Promise.all([loadSessions(), loadAgents(), loadSkillOptions()])
})
</script>

<style scoped>
/* ============ 页面容器 ============ */
.agents-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-base-secondary, #f5f5f5);
  overflow: hidden;
}

/* ============ 头部 ============ */
.agents-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacer-16, 16px);
  height: 60px;
  padding: 0 var(--spacer-24, 24px);
  flex-shrink: 0;
  background-color: var(--bg-base-default, #fff);
  border-bottom: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.agents-head-left { min-width: 0; flex-shrink: 0; }
.agents-title {
  margin: 0;
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-default, #171717);
  letter-spacing: -0.02em;
  line-height: 1.3;
}
.agents-desc {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, #737373);
  max-width: 560px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.agents-create-btn {
  height: 34px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  background-color: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
  border-color: var(--text-default, #171717);
}
.agents-create-btn:hover:not(:disabled) {
  background-color: var(--icon-default-hover, #171717);
  border-color: var(--icon-default-hover, #171717);
}
.agents-create-btn:active:not(:disabled) {
  background-color: var(--text-default, #171717);
  border-color: var(--text-default, #171717);
}

/* ============ Tab 栏 ============ */
.agents-tabs {
  display: flex;
  align-items: stretch;
  gap: var(--spacer-4, 4px);
  height: 46px;
  padding: 0 var(--spacer-24, 24px);
  flex-shrink: 0;
  background-color: var(--bg-base-default, #fff);
  border-bottom: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.agent-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px;
  margin-right: var(--spacer-24, 24px);
  background: none;
  border: none;
  cursor: pointer;
  font-family: var(--font-family-default, "SF Pro Text", "PingFang SC", system-ui, sans-serif);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary, #737373);
  transition: color 0.15s;
}
.agent-tab:hover { color: var(--text-secondary, #404040); }
.agent-tab.active { color: var(--text-default, #171717); font-weight: 600; }
.agent-tab::after {
  content: '';
  position: absolute;
  left: 0; right: 0; bottom: -1px;
  height: 2px;
  border-radius: 1px;
  background: transparent;
  transition: background-color 0.2s;
}
.agent-tab.active::after { background: var(--text-default, #171717); }
.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--radius-full, 999px);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  color: var(--text-tertiary, #737373);
  transition: background-color 0.2s, color 0.2s;
}
.agent-tab.active .tab-count {
  background: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
}

/* ============ 内容区 ============ */
.agents-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacer-24, 24px);
}
.agents-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacer-8, 8px);
  color: var(--text-tertiary, #737373);
  font-size: 14px;
  padding: 88px 0;
  text-align: center;
}
.empty-icon {
  width: 64px; height: 64px;
  border-radius: var(--radius-16, 16px);
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  display: flex; align-items: center; justify-content: center;
  color: var(--text-tertiary, #737373);
  margin-bottom: var(--spacer-4, 4px);
}
.empty-title { margin: 0; font-size: 14px; font-weight: 500; color: var(--text-secondary, #404040); }
.empty-hint { margin: 0; font-size: 12px; color: var(--text-tertiary, #737373); }
.empty-action { margin-top: var(--spacer-12, 12px); }
.empty-spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-top-color: var(--text-default, #171717);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-bottom: var(--spacer-4, 4px);
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ============ 卡片网格 ============ */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacer-16, 16px);
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

/* ============ 智能体卡片 ============ */
.agent-card {
  background: var(--bg-base-default, #fff);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-radius: var(--radius-12, 12px);
  padding: var(--spacer-20, 20px);
  display: flex;
  flex-direction: column;
  gap: var(--spacer-10, 10px);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.2s, transform 0.15s;
  animation: card-in 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.agent-card:hover {
  border-color: var(--border-neutral-l2, rgba(115,115,115,0.18));
  box-shadow: 0 4px 16px rgba(23,23,23,0.06);
  transform: translateY(-1px);
}
.agent-card.disabled { opacity: 0.55; }

.agent-card-head { display: flex; align-items: center; gap: var(--spacer-12, 12px); }
.agent-avatar {
  width: 40px; height: 40px; border-radius: var(--radius-10, 10px);
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; flex-shrink: 0;
  color: var(--icon-secondary, #404040);
}
.agent-avatar.lg { width: 48px; height: 48px; border-radius: var(--radius-12, 12px); }
.agent-avatar img { width: 100%; height: 100%; object-fit: cover; }
.agent-avatar-default {
  display: inline-flex; align-items: center; justify-content: center;
  width: 100%; height: 100%;
  font-size: 16px; font-weight: 600;
  color: var(--icon-secondary, #404040);
}
.agent-avatar.lg .agent-avatar-default { font-size: 18px; }
/* 官方头像：黑底白图标 */
.official-avatar {
  background: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
}
.official-avatar .agent-avatar-default { color: var(--bg-base-default, #fff); }

.agent-card-titles {
  min-width: 0; flex: 1;
  display: flex; align-items: center; gap: var(--spacer-8, 8px);
}
.agent-card-title {
  margin: 0; font-size: 14px; font-weight: 600; color: var(--text-default, #171717);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  letter-spacing: -0.01em;
}
/* 官方徽章 */
.agent-badge-official {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: var(--radius-full, 999px);
  background: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
  flex-shrink: 0;
  letter-spacing: 0.02em;
}
/* 个人范围标签 */
.agent-scope {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: var(--radius-full, 999px);
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  color: var(--text-tertiary, #737373);
  flex-shrink: 0;
}

.agent-card-desc {
  margin: 0; font-size: 13px; color: var(--text-secondary, #404040); line-height: 1.55;
  min-height: 40px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.agent-card-meta {
  font-size: 12px; color: var(--text-tertiary, #737373);
  padding-top: var(--spacer-8, 8px);
  border-top: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.agent-switch {
  display: inline-flex; align-items: center; gap: 7px;
  cursor: pointer;
  user-select: none;
  color: var(--text-secondary, #404040);
}
.agent-switch input {
  width: 14px; height: 14px;
  accent-color: var(--text-default, #171717);
  cursor: pointer;
}
.agent-card-actions { display: flex; gap: var(--spacer-8, 8px); flex-wrap: wrap; }
.agent-btn {
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  background: var(--bg-base-default, #fff);
  border-radius: var(--radius-6, 6px);
  padding: 6px 13px;
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-family-default, inherit);
  cursor: pointer;
  color: var(--text-secondary, #404040);
  transition: background-color 0.12s, border-color 0.12s, color 0.12s;
}
.agent-btn:hover {
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  color: var(--text-default, #171717);
}
.agent-btn.danger { color: var(--status-error-default, #e8463a); }
.agent-btn.danger:hover {
  background: var(--status-error-surface-l1, rgba(232,70,58,0.12));
  border-color: var(--status-error-default, #e8463a);
  color: var(--status-error-default, #e8463a);
}

.agents-error {
  position: fixed; bottom: var(--spacer-24, 24px); right: var(--spacer-24, 24px);
  background: var(--text-default, #171717); color: var(--bg-base-default, #fff);
  padding: 10px 14px; border-radius: var(--radius-8, 8px);
  font-size: 13px; cursor: pointer; z-index: 50;
  box-shadow: 0 8px 24px rgba(23,23,23,0.16);
}

/* ============ 弹窗 ============ */
.modal-overlay {
  position: fixed; inset: 0;
  background: var(--bg-overlay-l4, rgba(115,115,115,0.2));
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 80; padding: var(--spacer-20, 20px);
}
.modal-dialog {
  width: min(560px, 100%); background: var(--bg-base-default, #fff);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-radius: var(--radius-16, 16px);
  max-height: 90vh; overflow: auto;
  box-shadow: 0 24px 64px rgba(23,23,23,0.14), 0 8px 24px rgba(23,23,23,0.08);
}
.modal-wide { width: min(760px, 100%); }
.modal-header {
  padding: var(--spacer-20, 20px);
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 16px; font-weight: 600;
  color: var(--text-default, #171717);
  border-bottom: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  letter-spacing: -0.01em;
}
.modal-body { padding: var(--spacer-20, 20px); display: flex; flex-direction: column; gap: var(--spacer-8, 8px); }
.modal-footer {
  padding: var(--spacer-16, 16px) var(--spacer-20, 20px);
  display: flex; justify-content: flex-end; gap: var(--spacer-8, 8px);
  border-top: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.form-label {
  font-size: 12px; font-weight: 600;
  color: var(--text-secondary, #404040);
  margin-top: var(--spacer-6, 6px);
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
}
.form-input, .form-textarea {
  width: 100%; border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-8, 8px); padding: 8px 10px;
  font-size: 13px; font-family: inherit; box-sizing: border-box;
  background: var(--bg-base-default, #fff);
  color: var(--text-default, #171717);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.form-input:focus, .form-textarea:focus {
  outline: none;
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  box-shadow: 0 0 0 3px rgba(115,115,115,0.12);
}
.form-input:disabled { background: var(--bg-overlay-l1, rgba(115,115,115,0.08)); color: var(--text-tertiary, #737373); }
.form-textarea { resize: vertical; line-height: 1.5; }

/* ============ 头像上传 ============ */
.avatar-uploader-input { display: none; }
.avatar-uploader {
  display: flex;
  align-items: center;
  gap: var(--spacer-14, 14px);
  cursor: pointer;
  padding: var(--spacer-12, 12px);
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  background: var(--bg-base-secondary, #f5f5f5);
  transition: border-color 0.15s, background-color 0.15s;
}
.avatar-uploader:hover {
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
}
.avatar-uploader-box {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: var(--radius-12, 12px);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-base-default, #fff);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.avatar-uploader-box img {
  width: 100%; height: 100%; object-fit: cover;
  display: block;
}
.avatar-uploader-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-tertiary, #737373);
}
.avatar-uploader-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: color-mix(in srgb, var(--text-default, #171717) 55%, transparent);
  color: var(--bg-base-default, #fff);
  font-size: 11px;
  font-weight: 500;
  opacity: 0;
  transition: opacity 0.15s;
}
.avatar-uploader:hover .avatar-uploader-mask,
.avatar-uploader:focus-within .avatar-uploader-mask { opacity: 1; }
.avatar-uploader-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.avatar-uploader-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-default, #171717);
}
.avatar-uploader-hint {
  font-size: 12px;
  color: var(--text-tertiary, #737373);
}

/* ============ 详情 ============ */
.detail-head { display: flex; align-items: center; gap: var(--spacer-12, 12px); }
.detail-head > div:last-child { min-width: 0; }
.detail-title-row {
  display: flex; align-items: center; gap: var(--spacer-8, 8px);
  font-size: 16px; font-weight: 600; color: var(--text-default, #171717);
  letter-spacing: -0.01em;
}
.detail-sub { font-size: 12px; color: var(--text-tertiary, #737373); font-weight: 400; margin-top: 3px; }
.detail-desc { margin: 0 0 var(--spacer-8, 8px); color: var(--text-secondary, #404040); font-size: 14px; line-height: 1.6; }
.detail-md {
  background: var(--bg-base-secondary, #f5f5f5);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-radius: var(--radius-8, 8px);
  padding: 14px 16px;
  max-height: 420px;
  overflow: auto;
}
.chip-row { display: flex; flex-wrap: wrap; gap: var(--spacer-6, 6px); }
.chip {
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  border-radius: var(--radius-full, 999px);
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-secondary, #404040);
  font-weight: 500;
}
.muted { color: var(--text-disabled, #a1a1a1); font-size: 12px; }
.skill-checks { display: flex; flex-direction: column; gap: var(--spacer-6, 6px); max-height: 140px; overflow: auto; }
.skill-check { display: flex; align-items: center; gap: var(--spacer-8, 8px); font-size: 13px; color: var(--text-secondary, #404040); cursor: pointer; }
.skill-check input { accent-color: var(--text-default, #171717); }

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .agents-head {
    padding: 0 var(--spacer-16, 16px);
    height: auto;
    min-height: 56px;
    flex-wrap: wrap;
    padding-top: var(--spacer-12, 12px);
    padding-bottom: var(--spacer-12, 12px);
    gap: var(--spacer-8, 8px);
  }
  .agents-head-left { flex: 1 0 100%; }
  .agents-desc { white-space: normal; }
  .agents-tabs { padding: 0 var(--spacer-16, 16px); }
  .agents-body { padding: var(--spacer-16, 16px); }
  .agents-grid { grid-template-columns: 1fr; }
}
</style>
