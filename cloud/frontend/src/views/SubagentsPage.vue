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
        <button type="button" class="ds-btn ds-btn-primary" @click="openCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('agents.create') }}
        </button>
      </header>

      <div class="agents-body">
        <div v-if="loading && agents.length === 0" class="agents-empty">{{ t('agents.loading') }}</div>
        <div v-else-if="!loading && agents.length === 0" class="agents-empty">
          <p>{{ t('agents.empty') }}</p>
        </div>
        <div v-else class="agents-grid">
          <div
            v-for="agent in agents"
            :key="agent.name"
            class="agent-card"
            :class="{ disabled: !agent.enabled }"
            @click="openDetail(agent)"
          >
            <div class="agent-card-head">
              <div class="agent-avatar">
                <img v-if="agent.avatar_data" :src="agent.avatar_data" :alt="agent.name" />
                <span v-else>{{ (agent.name || '?').charAt(0).toUpperCase() }}</span>
              </div>
              <div class="agent-card-titles">
                <h3 class="agent-card-title">{{ agent.name }}</h3>
                <span class="agent-scope" :class="agent.scope">
                  {{ agent.scope === 'private' ? t('agents.scopePrivate') : t('agents.scopeShared') }}
                </span>
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
              <button
                v-if="agent.scope === 'private'"
                type="button"
                class="agent-btn"
                @click="openEdit(agent)"
              >{{ t('agents.edit') }}</button>
              <button
                v-if="agent.scope === 'private'"
                type="button"
                class="agent-btn danger"
                @click="removeAgent(agent)"
              >{{ t('agents.delete') }}</button>
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
            <div class="agent-avatar lg">
              <img v-if="detail.avatar_data" :src="detail.avatar_data" :alt="detail.name" />
              <span v-else>{{ (detail.name || '?').charAt(0).toUpperCase() }}</span>
            </div>
            <div>
              <div>{{ detail.name }}</div>
              <div class="detail-sub">
                {{ detail.scope === 'private' ? t('agents.scopePrivate') : t('agents.scopeShared') }}
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
            v-if="detail.scope === 'private'"
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
          <label class="form-label">{{ t('agents.avatar') }}</label>
          <input type="file" accept="image/*" @change="onAvatarPick" />
          <div v-if="form.avatarPreview" class="avatar-preview">
            <img :src="form.avatarPreview" alt="avatar" />
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
</template>

<script setup>
import { ref, onMounted } from 'vue'
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
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { ElMessageBox } from 'element-plus'
import './ChatPage.css'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

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
.agents-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-base-secondary, #f7f7f8);
}
.agents-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 28px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #fff;
}
.agents-title { margin: 0; font-size: 20px; font-weight: 600; color: #111827; }
.agents-desc { margin: 6px 0 0; font-size: 13px; color: #6b7280; max-width: 560px; line-height: 1.45; }
.agents-body { flex: 1; overflow: auto; padding: 20px 28px 40px; }
.agents-empty { color: #9ca3af; font-size: 14px; padding: 48px 0; text-align: center; }
.agents-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.agent-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
}
.agent-card:hover { border-color: #c7cdd6; }
.agent-card.disabled { opacity: 0.55; }
.agent-card-head { display: flex; align-items: center; gap: 10px; }
.agent-avatar {
  width: 40px; height: 40px; border-radius: 10px;
  background: #f3f4f6; display: flex; align-items: center; justify-content: center;
  overflow: hidden; font-weight: 600; color: #6b7280; flex-shrink: 0;
}
.agent-avatar.lg { width: 48px; height: 48px; }
.agent-avatar img { width: 100%; height: 100%; object-fit: cover; }
.agent-card-titles { min-width: 0; flex: 1; display: flex; align-items: center; gap: 8px; }
.agent-card-title {
  margin: 0; font-size: 15px; font-weight: 600; color: #111827;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.agent-scope {
  font-size: 11px; color: #6b7280; background: #f3f4f6;
  border-radius: 4px; padding: 2px 6px; flex-shrink: 0;
}
.agent-card-desc {
  margin: 0; font-size: 13px; color: #6b7280; line-height: 1.45; min-height: 38px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.agent-card-meta { font-size: 12px; color: #6b7280; }
.agent-switch { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.agent-card-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.agent-btn {
  border: 1px solid #e5e7eb; background: #fff; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; cursor: pointer; color: #374151;
}
.agent-btn:hover { background: #f9fafb; }
.agent-btn.danger { color: #b91c1c; }
.agents-error {
  position: fixed; bottom: 24px; right: 24px; background: #111827; color: #fff;
  padding: 10px 14px; border-radius: 8px; font-size: 13px; cursor: pointer; z-index: 50;
}
.modal-overlay {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 80; padding: 20px;
}
.modal-dialog {
  width: min(560px, 100%); background: #fff; border-radius: 12px;
  max-height: 90vh; overflow: auto; box-shadow: 0 20px 50px rgba(0,0,0,.18);
}
.modal-wide { width: min(760px, 100%); }
.modal-header { padding: 16px 20px; font-weight: 600; border-bottom: 1px solid #eee; }
.modal-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
.modal-footer { padding: 12px 20px 16px; display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid #eee; }
.form-label { font-size: 12px; color: #6b7280; margin-top: 6px; }
.form-input, .form-textarea {
  width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 10px;
  font-size: 13px; font-family: inherit; box-sizing: border-box;
}
.form-textarea { resize: vertical; line-height: 1.5; }
.detail-head { display: flex; align-items: center; gap: 12px; }
.detail-sub { font-size: 12px; color: #9ca3af; font-weight: 400; }
.detail-desc { margin: 0 0 8px; color: #4b5563; font-size: 14px; }
.detail-md {
  background: #f9fafb;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px 14px;
  max-height: 420px;
  overflow: auto;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { background: #f3f4f6; border-radius: 999px; padding: 2px 8px; font-size: 12px; color: #374151; }
.muted { color: #9ca3af; font-size: 12px; }
.skill-checks { display: flex; flex-direction: column; gap: 6px; max-height: 140px; overflow: auto; }
.skill-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #374151; }
.avatar-preview { width: 56px; height: 56px; border-radius: 10px; overflow: hidden; }
.avatar-preview img { width: 100%; height: 100%; object-fit: cover; }
</style>
