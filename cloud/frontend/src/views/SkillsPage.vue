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
    <div class="skills-page">
      <header class="skills-head">
        <div class="skills-head-left">
          <h2 class="skills-title">{{ t('skills.title') }}</h2>
          <p class="skills-desc">{{ t('skills.desc') }}</p>
        </div>
        <div class="skills-head-actions">
          <div class="skills-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <input
              v-model="searchQuery"
              type="text"
              class="skills-search-input"
              :placeholder="t('skills.searchPlaceholder')"
            />
            <span v-if="searchQuery" class="skills-search-clear" @click="searchQuery = ''">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </span>
          </div>
          <button type="button" class="ds-btn ds-btn-primary skills-create-btn" @click="openCreate">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>
            {{ t('skills.create') }}
          </button>
        </div>
      </header>

      <!-- Tab 切换：官方 / 个人 -->
      <nav class="skills-tabs">
        <button
          type="button"
          class="skill-tab"
          :class="{ active: activeTab === 'official' }"
          @click="activeTab = 'official'"
        >
          {{ t('skills.official') }}
          <span class="tab-count">{{ officialSkills.length }}</span>
        </button>
        <button
          type="button"
          class="skill-tab"
          :class="{ active: activeTab === 'personal' }"
          @click="activeTab = 'personal'"
        >
          {{ t('skills.personal') }}
          <span class="tab-count">{{ personalSkills.length }}</span>
        </button>
      </nav>

      <div class="skills-body">
        <div v-if="loading && skills.length === 0" class="skills-empty">
          <div class="empty-spinner"></div>
          <span>{{ t('skills.loading') }}</span>
        </div>

        <div v-else-if="activeList.length === 0" class="skills-empty">
          <div class="empty-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <path d="m21 21-4.3-4.3"/>
            </svg>
          </div>
          <p class="empty-title">{{ searchQuery ? t('skills.noSearchResult') : (activeTab === 'official' ? t('skills.officialEmpty') : t('skills.personalEmpty')) }}</p>
          <p v-if="!searchQuery && activeTab === 'personal'" class="empty-hint">{{ t('skills.personalEmptyHint') }}</p>
          <button
            v-if="!searchQuery && activeTab === 'personal'"
            type="button"
            class="ds-btn ds-btn-primary empty-action"
            @click="openCreate"
          >
            {{ t('skills.create') }}
          </button>
        </div>

        <div v-else class="skills-grid">
          <div
            v-for="skill in activeList"
            :key="skill.folder_name"
            class="skill-card"
            @click="openDetail(skill)"
          >
            <div class="skill-card-head">
              <div class="skill-avatar" :class="{ 'official-avatar': isOfficial(skill) }">
                <img v-if="skill.avatar_data" :src="skill.avatar_data" :alt="skill.name" />
                <span v-else class="skill-avatar-default">
                  <svg v-if="isOfficial(skill)" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/>
                  </svg>
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9z"/>
                    <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>
                    <circle cx="5" cy="18" r="1.5"/>
                  </svg>
                </span>
              </div>
              <div class="skill-card-titles">
                <h3 class="skill-card-title">{{ skill.name }}</h3>
                <span v-if="isOfficial(skill)" class="skill-badge-official">
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>
                  {{ t('skills.officialBadge') }}
                </span>
              </div>
            </div>
            <p class="skill-card-desc">{{ skill.description || t('skills.noDesc') }}</p>
            <div class="skill-card-meta" @click.stop>
              <label class="skill-switch">
                <input
                  type="checkbox"
                  :checked="skill.main_enabled"
                  @change="(e) => toggleMain(skill, e.target.checked)"
                />
                <span>{{ t('skills.mainEnabled') }}</span>
              </label>
            </div>
            <div class="skill-card-actions" @click.stop>
              <button type="button" class="skill-btn" @click="openDetail(skill)">{{ t('skills.view') }}</button>
              <button
                v-if="!isOfficial(skill)"
                type="button"
                class="skill-btn danger"
                @click="removeSkill(skill)"
              >{{ t('skills.delete') }}</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="errorMessage" class="skills-error" @click="errorMessage = ''">{{ errorMessage }}</div>
    </div>

    <!-- 详情 -->
    <div v-if="detail" class="modal-overlay" @click="detail = null">
      <div class="modal-dialog modal-wide" @click.stop>
        <div class="modal-header">
          <div class="detail-head">
            <div class="skill-avatar lg" :class="{ 'official-avatar': isOfficial(detail) }">
              <img v-if="detail.avatar_data" :src="detail.avatar_data" :alt="detail.name" />
              <span v-else class="skill-avatar-default">
                <svg v-if="isOfficial(detail)" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/>
                </svg>
                <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9z"/>
                  <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>
                  <circle cx="5" cy="18" r="1.5"/>
                </svg>
              </span>
            </div>
            <div>
              <div class="detail-title-row">
                <span>{{ detail.name }}</span>
                <span v-if="isOfficial(detail)" class="skill-badge-official">
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>
                  {{ t('skills.officialBadge') }}
                </span>
              </div>
              <div class="detail-sub">
                {{ isOfficial(detail) ? t('skills.officialBadge') : t('skills.scopePrivate') }}
              </div>
            </div>
          </div>
        </div>
        <div class="modal-body">
          <p class="detail-desc">{{ detail.description || t('skills.noDesc') }}</p>
          <label class="form-label">{{ t('skills.tree') }}</label>
          <div class="chip-row">
            <span v-for="f in (detail.tree || []).filter(x => x !== '...')" :key="f" class="chip">{{ f }}</span>
            <span v-if="!(detail.tree || []).length" class="muted">—</span>
          </div>
          <label class="form-label">SKILL.md</label>
          <div class="detail-md">
            <MarkdownRenderer :content="detail.body || detail.content || ''" :show-actions="false" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="ds-btn" @click="detail = null">{{ t('skills.cancel') }}</button>
        </div>
      </div>
    </div>

    <!-- 上传技能包 -->
    <div v-if="uploadVisible" class="modal-overlay" @click="closeUpload">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">{{ t('skills.uploadTitle') }}</div>
        <div class="modal-body">
          <div
            class="upload-dropzone"
            :class="{ 'has-file': uploadFile, 'is-drag': isDragOver }"
            @click="$refs.fileInput.click()"
            @dragover.prevent="isDragOver = true"
            @dragleave.prevent="isDragOver = false"
            @drop.prevent="onDrop"
          >
            <input ref="fileInput" type="file" accept=".zip" class="upload-input-hidden" @change="onFilePick" />
            <template v-if="uploadFile">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>
              <span class="upload-filename">{{ uploadFile.name }}</span>
              <span class="upload-filesize">({{ (uploadFile.size / 1024).toFixed(1) }} KB)</span>
            </template>
            <template v-else>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
              <span class="upload-hint-text">{{ t('skills.uploadHint') }}</span>
            </template>
          </div>
          <p class="upload-tip">{{ t('skills.uploadTip') }}</p>

          <!-- 合规检测结果 -->
          <div v-if="complianceResult" class="compliance-result" :class="complianceResult.severity">
            <div class="compliance-header">
              <span v-if="complianceResult.passed" class="compliance-icon">&#10003;</span>
              <span v-else class="compliance-icon">&#10007;</span>
              <span class="compliance-title">{{ complianceResult.summary || (complianceResult.passed ? t('skills.compliancePassed') : t('skills.complianceFailed')) }}</span>
            </div>
            <div v-if="complianceResult.issues?.length" class="compliance-issues">
              <div
                v-for="(issue, idx) in complianceResult.issues"
                :key="idx"
                class="compliance-issue"
                :class="issue.severity"
              >
                <span class="issue-badge">{{ issue.severity }}</span>
                <span class="issue-category">[{{ issue.category }}]</span>
                <span class="issue-message">{{ issue.message }}</span>
                <span v-if="issue.suggestion" class="issue-suggestion">{{ issue.suggestion }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="ds-btn" @click="closeUpload">{{ t('skills.cancel') }}</button>
          <button
            type="button"
            class="ds-btn ds-btn-primary"
            :disabled="!uploadFile || uploading"
            @click="doUpload"
          >
            {{ uploading ? t('skills.uploading') : t('skills.uploadBtn') }}
          </button>
        </div>
      </div>
    </div>

    <SettingsModal v-if="settingsStore.settingsOpen" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useI18n } from '../i18n'
import api from '../api'
import {
  listSkills,
  getSkill,
  uploadSkill,
  deleteSkill,
  setSkillMainEnabled,
} from '../api/skills'
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
const skills = ref([])
const loading = ref(false)
const errorMessage = ref('')
const detail = ref(null)
const searchQuery = ref('')
const activeTab = ref('official')

// 上传相关
const uploadVisible = ref(false)
const uploadFile = ref(null)
const uploading = ref(false)
const isDragOver = ref(false)
const complianceResult = ref(null)

// 判断是否为官方技能：scope 不为 private 的视为官方
function isOfficial(skill) {
  return skill && skill.scope !== 'private'
}

// 搜索过滤
const filteredSkills = computed(() => {
  if (!searchQuery.value.trim()) return skills.value
  const q = searchQuery.value.trim().toLowerCase()
  return skills.value.filter(s =>
    (s.name || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})

const officialSkills = computed(() => filteredSkills.value.filter(isOfficial))
const personalSkills = computed(() => filteredSkills.value.filter(s => !isOfficial(s)))

// 当前 tab 列表
const activeList = computed(() =>
  activeTab.value === 'official' ? officialSkills.value : personalSkills.value
)

// 官方为空时自动切到个人 tab；个人为空时切回官方
watch([officialSkills, personalSkills], ([o, p]) => {
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

async function loadSkills() {
  loading.value = true
  errorMessage.value = ''
  try {
    skills.value = await listSkills()
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
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

async function openDetail(skill) {
  try {
    detail.value = await getSkill(skill.folder_name || skill.name)
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '加载失败'
  }
}

function openCreate() {
  uploadVisible.value = true
  uploadFile.value = null
  complianceResult.value = null
  isDragOver.value = false
}

function closeUpload() {
  uploadVisible.value = false
  uploadFile.value = null
  complianceResult.value = null
}

function onFilePick(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploadFile.value = file
  complianceResult.value = null
}

function onDrop(e) {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) {
    errorMessage.value = t('skills.zipOnly')
    return
  }
  uploadFile.value = file
  complianceResult.value = null
}

async function doUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  errorMessage.value = ''
  complianceResult.value = null
  try {
    const result = await uploadSkill(uploadFile.value)
    complianceResult.value = result.compliance
    if (result.success) {
      await loadSkills()
      closeUpload()
    }
  } catch (e) {
    const d = e?.response?.data?.detail || e.message || '上传失败'
    errorMessage.value = d
    if (e?.response?.data?.compliance) {
      complianceResult.value = e.response.data.compliance
    }
  } finally {
    uploading.value = false
  }
}

async function toggleMain(skill, enabled) {
  try {
    const updated = await setSkillMainEnabled(skill.folder_name || skill.name, enabled)
    const idx = skills.value.findIndex((s) => s.folder_name === skill.folder_name)
    if (idx >= 0) skills.value[idx] = updated
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '更新失败'
    await loadSkills()
  }
}

async function removeSkill(skill) {
  try {
    await ElMessageBox.confirm(
      t('skills.deleteConfirm', { name: skill.name }),
      t('skills.deleteTitle'),
      {
        type: 'warning',
        confirmButtonText: t('skills.delete'),
        cancelButtonText: t('skills.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await deleteSkill(skill.folder_name || skill.name)
    await loadSkills()
  } catch (e) {
    errorMessage.value = e?.response?.data?.detail || e.message || '删除失败'
  }
}

onMounted(async () => {
  await Promise.all([loadSessions(), loadSkills()])
})
</script>

<style scoped>
/* ============ 页面容器 ============ */
.skills-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-base-secondary, #f5f5f5);
  overflow: hidden;
}

/* ============ 头部 ============ */
.skills-head {
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
.skills-head-left { min-width: 0; flex-shrink: 0; }
.skills-head-actions {
  display: flex;
  align-items: center;
  gap: var(--spacer-10, 10px);
  flex-shrink: 0;
}
.skills-title {
  margin: 0;
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-default, #171717);
  letter-spacing: -0.02em;
  line-height: 1.3;
}
.skills-desc {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, #737373);
  max-width: 560px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 搜索框 */
.skills-search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 240px;
  height: 34px;
  padding: 0 10px;
  border-radius: var(--radius-8, 8px);
  background-color: var(--bg-base-secondary, #f5f5f5);
  border: 1px solid transparent;
  color: var(--text-tertiary, #737373);
  transition: border-color 0.15s, background-color 0.15s, box-shadow 0.15s;
}
.skills-search:hover { background-color: var(--bg-overlay-l1, rgba(115,115,115,0.08)); }
.skills-search:focus-within {
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  background-color: var(--bg-base-default, #fff);
  box-shadow: 0 0 0 3px rgba(115,115,115,0.12);
}
.skills-search svg { flex-shrink: 0; }
.skills-search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-default, #171717);
  min-width: 0;
}
.skills-search-input::placeholder { color: var(--text-tertiary, #737373); }
.skills-search-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px; height: 18px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-tertiary, #737373);
  transition: background-color 0.12s, color 0.12s;
  flex-shrink: 0;
}
.skills-search-clear:hover {
  background-color: var(--bg-overlay-l2, rgba(115,115,115,0.12));
  color: var(--text-default, #171717);
}

.skills-create-btn {
  height: 34px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

/* 黑白主色按钮 */
.skills-page .ds-btn-primary,
.modal-dialog .ds-btn-primary {
  background-color: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
  border-color: var(--text-default, #171717);
}
.skills-page .ds-btn-primary:hover:not(:disabled),
.modal-dialog .ds-btn-primary:hover:not(:disabled) {
  background-color: var(--icon-default-hover, #171717);
  border-color: var(--icon-default-hover, #171717);
}
.skills-page .ds-btn-primary:active:not(:disabled),
.modal-dialog .ds-btn-primary:active:not(:disabled) {
  background-color: var(--text-default, #171717);
  border-color: var(--text-default, #171717);
}

/* ============ Tab 栏 ============ */
.skills-tabs {
  display: flex;
  align-items: stretch;
  gap: var(--spacer-4, 4px);
  height: 46px;
  padding: 0 var(--spacer-24, 24px);
  flex-shrink: 0;
  background-color: var(--bg-base-default, #fff);
  border-bottom: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.skill-tab {
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
.skill-tab:hover { color: var(--text-secondary, #404040); }
.skill-tab.active { color: var(--text-default, #171717); font-weight: 600; }
.skill-tab::after {
  content: '';
  position: absolute;
  left: 0; right: 0; bottom: -1px;
  height: 2px;
  border-radius: 1px;
  background: transparent;
  transition: background-color 0.2s;
}
.skill-tab.active::after { background: var(--text-default, #171717); }
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
.skill-tab.active .tab-count {
  background: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
}

/* ============ 内容区 ============ */
.skills-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacer-24, 24px);
}
.skills-empty {
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
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacer-16, 16px);
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

/* ============ 技能卡片 ============ */
.skill-card {
  position: relative;
  background-color: var(--bg-base-default, #fff);
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
.skill-card:hover {
  border-color: var(--border-neutral-l2, rgba(115,115,115,0.18));
  box-shadow: 0 4px 16px rgba(23,23,23,0.06);
  transform: translateY(-1px);
}

.skill-card-head { display: flex; align-items: center; gap: var(--spacer-12, 12px); }
.skill-avatar {
  width: 40px; height: 40px; border-radius: var(--radius-10, 10px);
  background-color: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; flex-shrink: 0;
  color: var(--icon-secondary, #404040);
}
.skill-avatar.lg { width: 48px; height: 48px; border-radius: var(--radius-12, 12px); }
.skill-avatar img { width: 100%; height: 100%; object-fit: cover; }
.skill-avatar-default {
  display: inline-flex; align-items: center; justify-content: center;
  width: 100%; height: 100%;
  color: var(--icon-secondary, #404040);
}
/* 官方头像：黑底白图标 */
.official-avatar {
  background: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
}
.official-avatar .skill-avatar-default { color: var(--bg-base-default, #fff); }

.skill-card-titles {
  min-width: 0; flex: 1;
  display: flex; align-items: center; gap: var(--spacer-8, 8px);
}
.skill-card-title {
  margin: 0;
  font-size: 14px; font-weight: 600; color: var(--text-default, #171717);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  letter-spacing: -0.01em;
}
/* 官方徽章 */
.skill-badge-official {
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

.skill-card-desc {
  margin: 0;
  font-size: 13px; color: var(--text-secondary, #404040); line-height: 1.55;
  min-height: 40px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.skill-card-meta {
  font-size: 12px; color: var(--text-tertiary, #737373);
  padding-top: var(--spacer-8, 8px);
  border-top: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.skill-switch {
  display: inline-flex; align-items: center; gap: 7px;
  cursor: pointer;
  user-select: none;
  color: var(--text-secondary, #404040);
}
.skill-switch input {
  width: 14px; height: 14px;
  accent-color: var(--text-default, #171717);
  cursor: pointer;
}
.skill-card-actions { display: flex; gap: var(--spacer-8, 8px); flex-wrap: wrap; }
.skill-btn {
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  background-color: var(--bg-base-default, #fff);
  border-radius: var(--radius-6, 6px);
  padding: 6px 13px;
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-family-default, inherit);
  cursor: pointer;
  color: var(--text-secondary, #404040);
  transition: background-color 0.12s, border-color 0.12s, color 0.12s;
}
.skill-btn:hover {
  background-color: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  color: var(--text-default, #171717);
}
.skill-btn.danger { color: var(--status-error-default, #e8463a); }
.skill-btn.danger:hover {
  background-color: var(--status-error-surface-l1, rgba(232,70,58,0.12));
  border-color: var(--status-error-default, #e8463a);
  color: var(--status-error-default, #e8463a);
}

.skills-error {
  position: fixed; bottom: var(--spacer-24, 24px); right: var(--spacer-24, 24px);
  background-color: var(--text-default, #171717); color: var(--bg-base-default, #fff);
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
  width: min(560px, 100%);
  background-color: var(--bg-base-default, #fff);
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
.modal-body { padding: var(--spacer-20, 20px); display: flex; flex-direction: column; gap: var(--spacer-10, 10px); }
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
  width: 100%;
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-8, 8px);
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  box-sizing: border-box;
  background-color: var(--bg-base-default, #fff);
  color: var(--text-default, #171717);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.form-input:focus, .form-textarea:focus {
  outline: none;
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  box-shadow: 0 0 0 3px rgba(115,115,115,0.12);
}
.form-textarea { resize: vertical; line-height: 1.5; }
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
  background-color: var(--bg-base-secondary, #f5f5f5);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-radius: var(--radius-8, 8px);
  padding: 14px 16px;
  max-height: 420px;
  overflow: auto;
}
.chip-row { display: flex; flex-wrap: wrap; gap: var(--spacer-6, 6px); }
.chip {
  background-color: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  border-radius: var(--radius-full, 999px);
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-secondary, #404040);
  font-weight: 500;
}
.muted { color: var(--text-disabled, #a1a1a1); font-size: 12px; }

/* ============ 上传 dropzone ============ */
.upload-input-hidden { display: none; }
.upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacer-8, 8px);
  padding: 40px var(--spacer-20, 20px);
  border: 2px dashed var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-12, 12px);
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
  color: var(--text-tertiary, #737373);
  text-align: center;
  background-color: var(--bg-base-secondary, #f5f5f5);
}
.upload-dropzone:hover, .upload-dropzone.is-drag {
  border-color: var(--text-default, #171717);
  background-color: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  color: var(--text-secondary, #404040);
}
.upload-dropzone.is-drag { border-style: solid; }
.upload-dropzone.has-file {
  border-style: solid;
  border-color: var(--status-success-default, #15a877);
  background-color: var(--status-success-surface-l1, rgba(21,168,119,0.12));
  color: var(--text-secondary, #404040);
}
.upload-hint-text { font-size: 14px; font-weight: 500; }
.upload-filename {
  font-size: 14px; font-weight: 600; color: var(--text-default, #171717);
  max-width: 100%;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.upload-filesize { font-size: 12px; color: var(--text-tertiary, #737373); }
.upload-tip { font-size: 12px; color: var(--text-tertiary, #737373); margin: var(--spacer-4, 4px) 0 0; line-height: 1.5; }

/* ============ 合规检测 ============ */
.compliance-result {
  margin-top: var(--spacer-12, 12px);
  border-radius: var(--radius-8, 8px);
  padding: 14px 16px;
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
.compliance-result.pass { border-color: var(--status-success-default, #15a877); background-color: var(--status-success-surface-l1, rgba(21,168,119,0.12)); }
.compliance-result.warning { border-color: var(--status-alert-default, #fea900); background-color: var(--status-alert-surface-l1, rgba(254,169,0,0.14)); }
.compliance-result.critical { border-color: var(--status-error-default, #e8463a); background-color: var(--status-error-surface-l1, rgba(232,70,58,0.12)); }
.compliance-header { display: flex; align-items: center; gap: var(--spacer-8, 8px); margin-bottom: var(--spacer-8, 8px); }
.compliance-icon { font-size: 16px; font-weight: 700; }
.compliance-result.pass .compliance-icon { color: var(--status-success-default, #15a877); }
.compliance-result.warning .compliance-icon { color: var(--status-alert-default, #fea900); }
.compliance-result.critical .compliance-icon { color: var(--status-error-default, #e8463a); }
.compliance-title { font-size: 14px; font-weight: 600; color: var(--text-default, #171717); }
.compliance-issues { display: flex; flex-direction: column; gap: var(--spacer-6, 6px); }
.compliance-issue {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--spacer-4, 4px);
  font-size: 13px;
  line-height: 1.5;
  padding: var(--spacer-4, 4px) 0;
}
.issue-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: var(--radius-4, 4px);
  flex-shrink: 0;
  letter-spacing: 0.03em;
}
.compliance-issue.critical .issue-badge { background: var(--status-error-default, #e8463a); color: #fff; }
.compliance-issue.warning .issue-badge { background: var(--status-alert-default, #fea900); color: #fff; }
.compliance-issue.info .issue-badge { background: var(--bg-overlay-l2, rgba(115,115,115,0.12)); color: var(--text-default, #171717); }
.issue-category { font-weight: 600; color: var(--text-secondary, #404040); flex-shrink: 0; }
.issue-message { color: var(--text-default, #171717); }
.issue-suggestion { width: 100%; color: var(--text-tertiary, #737373); font-size: 12px; padding-left: 4px; }

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .skills-head {
    padding: 0 var(--spacer-16, 16px);
    height: auto;
    min-height: 56px;
    flex-wrap: wrap;
    padding-top: var(--spacer-12, 12px);
    padding-bottom: var(--spacer-12, 12px);
    gap: var(--spacer-8, 8px);
  }
  .skills-head-left { flex: 1 0 100%; }
  .skills-desc { white-space: normal; }
  .skills-head-actions { width: 100%; }
  .skills-search { width: 100%; }
  .skills-tabs { padding: 0 var(--spacer-16, 16px); }
  .skills-body { padding: var(--spacer-16, 16px); }
  .skills-grid { grid-template-columns: 1fr; }
}
</style>
