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
        <button type="button" class="ds-btn ds-btn-primary" @click="openCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('skills.create') }}
        </button>
      </header>

      <div class="skills-body">
        <div v-if="loading && skills.length === 0" class="skills-empty">{{ t('skills.loading') }}</div>
        <div v-else-if="!loading && skills.length === 0" class="skills-empty">
          <p>{{ t('skills.empty') }}</p>
        </div>
        <div v-else class="skills-grid">
          <div
            v-for="skill in skills"
            :key="skill.folder_name"
            class="skill-card"
            @click="openDetail(skill)"
          >
            <div class="skill-card-head">
              <div class="skill-avatar">
                <img v-if="skill.avatar_data" :src="skill.avatar_data" :alt="skill.name" />
                <span v-else>{{ (skill.name || '?').charAt(0).toUpperCase() }}</span>
              </div>
              <div class="skill-card-titles">
                <h3 class="skill-card-title">{{ skill.name }}</h3>
                <span class="skill-scope" :class="skill.scope">
                  {{ skill.scope === 'private' ? t('skills.scopePrivate') : t('skills.scopeShared') }}
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
                v-if="skill.scope === 'private'"
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
            <div class="skill-avatar lg">
              <img v-if="detail.avatar_data" :src="detail.avatar_data" :alt="detail.name" />
              <span v-else>{{ (detail.name || '?').charAt(0).toUpperCase() }}</span>
            </div>
            <div>
              <div>{{ detail.name }}</div>
              <div class="detail-sub">
                {{ detail.scope === 'private' ? t('skills.scopePrivate') : t('skills.scopeShared') }}
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
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>
              <span class="upload-filename">{{ uploadFile.name }}</span>
              <span class="upload-filesize">({{ (uploadFile.size / 1024).toFixed(1) }} KB)</span>
            </template>
            <template v-else>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
              <span>{{ t('skills.uploadHint') }}</span>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
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
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { ElMessageBox } from 'element-plus'
import './ChatPage.css'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const sidebarOpen = ref(true)
const sessions = ref([])
const skills = ref([])
const loading = ref(false)
const errorMessage = ref('')
const detail = ref(null)

// 上传相关
const uploadVisible = ref(false)
const uploadFile = ref(null)
const uploading = ref(false)
const isDragOver = ref(false)
const complianceResult = ref(null)

function iconSrc(skill) {
  return skill.avatar_data || ''
}

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
    const detail = e?.response?.data?.detail || e.message || '上传失败'
    errorMessage.value = detail
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
.skills-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-base-secondary, #f7f7f8);
}
.skills-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 28px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #fff;
}
.skills-title { margin: 0; font-size: 20px; font-weight: 600; color: #111827; }
.skills-desc { margin: 6px 0 0; font-size: 13px; color: #6b7280; max-width: 560px; line-height: 1.45; }
.skills-body { flex: 1; overflow: auto; padding: 20px 28px 40px; }
.skills-empty { color: #9ca3af; font-size: 14px; padding: 48px 0; text-align: center; }
.skills-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.skill-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
}
.skill-card:hover { border-color: #c7cdd6; }
.skill-card-head { display: flex; align-items: center; gap: 10px; }
.skill-avatar {
  width: 40px; height: 40px; border-radius: 10px;
  background: #f3f4f6; display: flex; align-items: center; justify-content: center;
  overflow: hidden; font-weight: 600; color: #6b7280; flex-shrink: 0;
}
.skill-avatar.lg { width: 48px; height: 48px; }
.skill-avatar img { width: 100%; height: 100%; object-fit: cover; }
.skill-card-titles { min-width: 0; flex: 1; display: flex; align-items: center; gap: 8px; }
.skill-card-title { margin: 0; font-size: 15px; font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-scope { font-size: 11px; color: #6b7280; background: #f3f4f6; border-radius: 4px; padding: 2px 6px; flex-shrink: 0; }
.skill-card-desc {
  margin: 0; font-size: 13px; color: #6b7280; line-height: 1.45; min-height: 38px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.skill-card-meta { font-size: 12px; color: #6b7280; }
.skill-switch { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.skill-card-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.skill-btn {
  border: 1px solid #e5e7eb; background: #fff; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; cursor: pointer; color: #374151;
}
.skill-btn:hover { background: #f9fafb; }
.skill-btn.danger { color: #b91c1c; }
.skills-error {
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
.avatar-preview { width: 56px; height: 56px; border-radius: 10px; overflow: hidden; }
.avatar-preview img { width: 100%; height: 100%; object-fit: cover; }

/* 上传 dropzone */
.upload-input-hidden { display: none; }
.upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 20px;
  border: 2px dashed var(--border-neutral-l2, #d1d5db);
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  color: var(--text-tertiary, #9ca3af);
  text-align: center;
}
.upload-dropzone:hover, .upload-dropzone.is-drag {
  border-color: var(--primary, #3b82f6);
  background: var(--bg-overlay-l1, rgba(59,130,246,0.04));
}
.upload-dropzone.has-file {
  border-style: solid;
  border-color: var(--status-success-default, #15a877);
  color: var(--text-secondary, #404040);
}
.upload-filename { font-size: 14px; font-weight: 500; color: var(--text-default, #111827); }
.upload-filesize { font-size: 12px; color: var(--text-tertiary, #9ca3af); }
.upload-tip { font-size: 12px; color: var(--text-tertiary, #9ca3af); margin: 4px 0 0; line-height: 1.4; }

/* 合规检测结果 */
.compliance-result {
  margin-top: 12px;
  border-radius: 8px;
  padding: 12px 14px;
  border: 1px solid var(--border-neutral-l1, #e5e7eb);
}
.compliance-result.pass { border-color: var(--status-success-default, #15a877); background: var(--status-success-surface-l1, rgba(21,168,119,0.06)); }
.compliance-result.warning { border-color: #f59e0b; background: rgba(245,158,11,0.06); }
.compliance-result.critical { border-color: var(--status-error-default, #e8463a); background: var(--status-error-surface-l1, rgba(232,70,58,0.06)); }
.compliance-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.compliance-icon { font-size: 16px; font-weight: 700; }
.compliance-result.pass .compliance-icon { color: var(--status-success-default, #15a877); }
.compliance-result.warning .compliance-icon { color: #f59e0b; }
.compliance-result.critical .compliance-icon { color: var(--status-error-default, #e8463a); }
.compliance-title { font-size: 14px; font-weight: 500; color: var(--text-default, #111827); }
.compliance-issues { display: flex; flex-direction: column; gap: 6px; }
.compliance-issue {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px;
  font-size: 13px;
  line-height: 1.5;
  padding: 4px 0;
}
.issue-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}
.compliance-issue.critical .issue-badge { background: var(--status-error-default, #e8463a); color: #fff; }
.compliance-issue.warning .issue-badge { background: #f59e0b; color: #fff; }
.compliance-issue.info .issue-badge { background: var(--bg-overlay-l2, #d1d5db); color: var(--text-default, #374151); }
.issue-category { font-weight: 600; color: var(--text-secondary, #6b7280); flex-shrink: 0; }
.issue-message { color: var(--text-default, #374151); }
.issue-suggestion { width: 100%; color: var(--text-tertiary, #9ca3af); font-size: 12px; padding-left: 4px; }
</style>
