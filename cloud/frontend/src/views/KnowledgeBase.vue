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
    <div class="kb-page">
      <header class="kb-head">
        <div class="kb-head-left">
          <h2 class="kb-title">{{ t('kb.title') }}</h2>
          <p class="kb-desc">{{ t('kb.desc') }}</p>
        </div>
      </header>

      <div class="kb-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="kb-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="kb-body">
        <!-- ===== Wiki 文档 ===== -->
        <div v-if="activeTab === 'wiki'" class="kb-wiki">
          <div class="kb-wiki-side">
            <div class="kb-wiki-side-head">
              <span>{{ t('kb.wiki') }}</span>
              <span class="kb-wiki-count">{{ t('kb.pageCount', { count: pages.length }) }}</span>
            </div>
            <div v-if="loadingPages" class="kb-empty">{{ t('skills.loading') }}</div>
            <div v-else-if="pages.length === 0" class="kb-empty">{{ t('kb.emptyWiki') }}</div>
            <div v-else class="kb-page-list">
              <template v-for="g in pageGroups" :key="g.dir">
                <div class="kb-folder-head">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
                  <span class="kb-folder-name" :title="g.dir">{{ g.dir || t('kb.rootFolder') }}</span>
                  <button
                    v-if="g.dir"
                    type="button"
                    class="kb-folder-del"
                    :title="t('kb.folderDelete')"
                    @click.stop="deleteFolder(g.dir)"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
                  </button>
                </div>
                <button
                  v-for="p in g.pages"
                  :key="p.path"
                  type="button"
                  class="kb-page-item"
                  :class="{ active: selectedPage?.path === p.path }"
                  @click="selectPage(p)"
                >
                  <span class="kb-page-title" :title="p.title">{{ p.title }}</span>
                </button>
              </template>
            </div>
          </div>
          <div class="kb-wiki-main">
            <div v-if="!selectedPage" class="kb-empty kb-empty-main">{{ t('kb.noPageSelected') }}</div>
            <template v-else>
              <div class="kb-page-detail-head">
                <h3 class="kb-page-detail-title">{{ selectedPage.title || selectedPage.path }}</h3>
                <div class="kb-page-detail-actions">
                  <button
                    v-if="selectedMeta.raw_file || selectedMeta.original_url"
                    type="button"
                    class="ds-btn"
                    @click="downloadOriginal"
                  >
                    {{ t('kb.viewOriginal') }}
                  </button>
                  <button type="button" class="ds-btn" @click="renameSelected">
                    {{ t('kb.rename') }}
                  </button>
                  <button type="button" class="ds-btn" @click="moveSelected">
                    {{ t('kb.move') }}
                  </button>
                  <button type="button" class="ds-btn danger" @click="deleteSelected">
                    {{ t('session.delete') }}
                  </button>
                </div>
              </div>
              <div v-if="selectedMetaFields.length" class="kb-page-meta">
                <span v-for="f in selectedMetaFields" :key="f[0]" class="kb-meta-chip">
                  {{ f[0] }}: {{ f[1] }}
                </span>
              </div>
              <div class="kb-page-content">
                <MarkdownRenderer :content="renderContent" :show-actions="false" />
              </div>
            </template>
          </div>
        </div>

        <!-- ===== 导入 ===== -->
        <div v-else-if="activeTab === 'import'" class="kb-import">
          <!-- 左列：手动粘贴文字 -->
          <div class="kb-import-col kb-import-col-left">
            <section class="kb-import-card">
              <div class="kb-import-card-head">
                <div class="kb-import-card-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h6"/></svg>
                </div>
                <div>
                  <h4 class="kb-import-title">{{ t('kb.pasteImport') }}</h4>
                  <p class="kb-import-hint">{{ t('kb.pasteHint') }}</p>
                </div>
              </div>
              <textarea
                v-model="pasteText"
                class="kb-textarea"
                rows="10"
                :placeholder="t('kb.pastePlaceholder')"
                spellcheck="false"
              />
              <div class="kb-import-grid">
                <div class="kb-field">
                  <label class="kb-field-label">{{ t('kb.sourceTitle') }}</label>
                  <input v-model="pasteTitle" type="text" class="kb-input" :placeholder="t('kb.sourceTitle')" />
                </div>
                <div class="kb-field">
                  <label class="kb-field-label">{{ t('kb.keywords') }}</label>
                  <input v-model="pasteKeywords" type="text" class="kb-input" :placeholder="t('kb.keywordsHint')" />
                </div>
              </div>
              <div class="kb-import-foot">
                <span v-if="pasteText.trim()" class="kb-import-charcount">{{ pasteText.length }} chars</span>
                <button
                  type="button"
                  class="ds-btn ds-btn-primary"
                  :disabled="!pasteText.trim() || extracting"
                  @click="submitPaste"
                >
                  {{ extracting ? t('kb.importing') : t('kb.pasteSubmit') }}
                </button>
              </div>
            </section>
          </div>

          <!-- 右列：链接导入 + 文件上传 -->
          <div class="kb-import-col kb-import-col-right">
            <!-- 链接导入 -->
            <section class="kb-import-card">
              <div class="kb-import-card-head">
                <div class="kb-import-card-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                </div>
                <div>
                  <h4 class="kb-import-title">{{ t('kb.linkImport') }}</h4>
                  <p class="kb-import-hint">{{ t('kb.linkHint') }}</p>
                </div>
              </div>
              <div class="kb-import-row">
                <input
                  v-model="linkUrl"
                  type="text"
                  class="kb-input"
                  :placeholder="t('kb.linkPlaceholder')"
                />
                <button
                  type="button"
                  class="ds-btn ds-btn-primary"
                  :disabled="!linkUrl.trim() || extracting"
                  @click="submitLink"
                >
                  {{ extracting ? t('kb.extracting') : t('kb.extract') }}
                </button>
              </div>
            </section>

            <!-- 文件上传（支持 zip 压缩包） -->
            <section class="kb-import-card">
              <div class="kb-import-card-head">
                <div class="kb-import-card-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                </div>
                <div>
                  <h4 class="kb-import-title">{{ t('kb.fileUpload') }}</h4>
                  <p class="kb-import-hint">{{ t('kb.fileHint') }}</p>
                </div>
              </div>
              <div
                class="kb-dropzone"
                :class="{ dragging: isDragOver }"
                @dragover.prevent="isDragOver = true"
                @dragleave.prevent="isDragOver = false"
                @drop.prevent="onDropFile"
              >
                <input
                  ref="fileInputRef"
                  type="file"
                  hidden
                  :accept="acceptTypes"
                  @change="onFilePick"
                />
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                <p class="kb-dropzone-text">
                  {{ pendingFile ? pendingFile.name : t('kb.uploadHint') }}
                </p>
                <div v-if="!pendingFile" class="kb-dropzone-actions">
                  <button type="button" class="ds-btn" @click="fileInputRef?.click()">
                    {{ t('kb.selectFile') }}
                  </button>
                </div>
                <div v-else class="kb-dropzone-actions">
                  <button
                    type="button"
                    class="ds-btn ds-btn-primary"
                    :disabled="extracting"
                    @click="submitFile"
                  >
                    {{ extracting ? t('kb.extracting') : t('kb.extract') }}
                  </button>
                  <button type="button" class="ds-btn" @click="pendingFile = null">×</button>
                </div>
              </div>
            </section>
          </div>
        </div>

        <!-- ===== 任务 ===== -->
        <div v-else-if="activeTab === 'jobs'" class="kb-jobs">
          <div class="kb-jobs-head">
            <button type="button" class="ds-btn" @click="loadJobs">{{ t('kb.refresh') }}</button>
          </div>
          <div v-if="jobs.length === 0" class="kb-empty">{{ t('kb.jobsEmpty') }}</div>
          <table v-else class="kb-jobs-table">
            <thead>
              <tr>
                <th>{{ t('kb.jobType') }}</th>
                <th>{{ t('kb.jobStatus') }}</th>
                <th>{{ t('kb.jobCreated') }}</th>
                <th>{{ t('kb.jobError') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="j in jobs" :key="j.id">
                <td>{{ jobTypeLabel(j.type) }}</td>
                <td>
                  <span class="kb-job-status" :class="'st-' + j.status">{{ jobStatusLabel(j.status) }}</span>
                </td>
                <td>{{ fmtTime(j.created_at) }}</td>
                <td class="kb-job-error" :title="j.error">{{ j.error || '' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="jobsTotal > jobsPageSize" class="kb-jobs-pager">
            <el-pagination
              background
              layout="prev, pager, next, total"
              :total="jobsTotal"
              :page-size="jobsPageSize"
              :current-page="jobsPage"
              @current-change="onJobsPageChange"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
  <SettingsModal v-if="settingsStore.settingsOpen" />
  <KbPreviewDialog
    v-model:visible="previewVisible"
    :meta="previewMeta"
    :initial-text="previewText"
    :submitting="previewSubmitting"
    @confirm="handlePreviewConfirm"
    @cancel="previewVisible = false"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { useI18n } from '../i18n'
import ChatSidebar from './ChatSidebar.vue'
import SettingsModal from '../components/SettingsModal.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import KbPreviewDialog from '../components/KbPreviewDialog.vue'
import {
  listKbPages, getKbPage, deleteKbPage, moveKbPage, deleteKbFolder, getJobs, getRawFileUrl,
} from '../api/kb'
import './ChatPage.css'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const settingsStore = useSettingsStore()

const sidebarOpen = ref(true)
const sessions = ref([])

const tabs = computed(() => [
  { key: 'wiki', label: t('kb.wiki') },
  { key: 'import', label: t('kb.import') },
  { key: 'jobs', label: t('kb.jobs') },
])
const activeTab = ref('wiki')

// ===== Wiki =====
const pages = ref([])
const loadingPages = ref(false)
const selectedPage = ref(null)
const selectedMeta = ref({})
const selectedMetaFields = computed(() => Object.entries(selectedMeta.value))

// 按文件夹分组（dir 为空表示根目录）
const pageGroups = computed(() => {
  const map = {}
  for (const p of pages.value) {
    const d = p.dir || ''
    ;(map[d] = map[d] || []).push(p)
  }
  return Object.keys(map).sort().map(dir => ({ dir, pages: map[dir] }))
})

// 原始文件溯源：本地文件 -> 下载原文件；线上素材 -> 打开原链接
async function downloadOriginal() {
  if (selectedMeta.value.raw_file) {
    try {
      const res = await api.get(getRawFileUrl(selectedMeta.value.raw_file), { responseType: 'blob' })
      const blobUrl = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = selectedMeta.value.file_name || 'original'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || '下载失败')
    }
  } else if (selectedMeta.value.original_url) {
    window.open(selectedMeta.value.original_url, '_blank', 'noopener')
  }
}

async function loadPages() {
  loadingPages.value = true
  try {
    const res = await listKbPages()
    pages.value = res.data || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loadingPages.value = false
  }
}

async function selectPage(p) {
  try {
    const res = await getKbPage(p.path)
    const content = res.data.content_md || ''
    selectedPage.value = res.data
    selectedMeta.value = parseFrontmatter(content)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

function parseFrontmatter(content) {
  const meta = {}
  const m = content.match(/^---\n([\s\S]*?)\n---/)
  if (!m) return meta
  for (const line of m[1].split('\n')) {
    const idx = line.indexOf(':')
    if (idx <= 0) continue
    const key = line.slice(0, idx).trim()
    let val = line.slice(idx + 1).trim().replace(/^["']|["']$/g, '')
    if (val.startsWith('[')) val = val.slice(1, -1).split(',').map(s => s.trim()).join(', ')
    meta[key] = val
  }
  return meta
}

const renderContent = computed(() => {
  const body = (selectedPage.value?.content_md || '').replace(/^---\n[\s\S]*?\n---\n?/, '')
  return body.replace(/\[\[([^\]]+)\]\]/g, '**$1**')
})

async function deleteSelected() {
  if (!selectedPage.value) return
  try {
    await ElMessageBox.confirm(
      t('kb.deleteConfirm', { title: selectedPage.value.title || selectedPage.value.path }),
      t('session.delete'),
      { type: 'warning', confirmButtonText: t('session.delete'), cancelButtonText: t('settings.cancel') },
    )
  } catch {
    return
  }
  try {
    await deleteKbPage(selectedPage.value.path)
    ElMessage.success('deleted')
    selectedPage.value = null
    selectedMeta.value = {}
    await loadPages()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

function curDir(path) {
  const idx = path.lastIndexOf('/')
  return idx > 0 ? path.slice(0, idx) : ''
}

// 重命名：改标题 + 文件名，同步 frontmatter title
async function renameSelected() {
  if (!selectedPage.value) return
  let value
  try {
    const res = await ElMessageBox.prompt(
      t('kb.renamePrompt'),
      t('kb.rename'),
      {
        inputValue: selectedPage.value.title || selectedPage.value.path.split('/').pop().replace(/\.md$/, ''),
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
      },
    )
    value = res.value
  } catch {
    return
  }
  const title = (value || '').trim()
  if (!title) return
  const safeTitle = title.replace(/[\\/:*?"<>|]/g, '-')
  const dir = curDir(selectedPage.value.path)
  const newPath = (dir ? dir + '/' : '') + safeTitle + '.md'
  try {
    await moveKbPage(selectedPage.value.path, newPath, title)
    ElMessage.success('renamed')
    selectedPage.value = null
    selectedMeta.value = {}
    await loadPages()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '重命名失败')
  }
}

// 移动：输入目标文件夹（相对路径，根目录留空）
async function moveSelected() {
  if (!selectedPage.value) return
  let value
  try {
    const res = await ElMessageBox.prompt(
      t('kb.movePrompt'),
      t('kb.move'),
      {
        inputValue: curDir(selectedPage.value.path),
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
      },
    )
    value = res.value
  } catch {
    return
  }
  const targetDir = String(value || '').trim().replace(/^\/+|\/+$/g, '')
  const name = selectedPage.value.path.split('/').pop()
  const newPath = targetDir ? targetDir + '/' + name : name
  if (newPath === selectedPage.value.path) return
  try {
    await moveKbPage(selectedPage.value.path, newPath)
    ElMessage.success('moved')
    selectedPage.value = null
    selectedMeta.value = {}
    await loadPages()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '移动失败')
  }
}

// 删除整个文件夹（含内部所有文档）
async function deleteFolder(dir) {
  try {
    await ElMessageBox.confirm(
      t('kb.folderDeleteConfirm', { dir }),
      t('kb.folderDelete'),
      { type: 'warning', confirmButtonText: t('session.delete'), cancelButtonText: t('settings.cancel') },
    )
  } catch {
    return
  }
  try {
    await deleteKbFolder(dir)
    if (selectedPage.value && (selectedPage.value.path === dir || selectedPage.value.path.startsWith(dir + '/'))) {
      selectedPage.value = null
      selectedMeta.value = {}
    }
    ElMessage.success('deleted')
    await loadPages()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

// ===== 导入（提取预览 -> 确认整理） =====
const linkUrl = ref('')
const extracting = ref(false)
const pendingFile = ref(null)
const isDragOver = ref(false)
const fileInputRef = ref(null)
const acceptTypes = '.pdf,.docx,.pptx,.xlsx,.xls,.txt,.csv,.html,.md,.zip'

// 手动粘贴文字
const pasteText = ref('')
const pasteTitle = ref('')
const pasteKeywords = ref('')

function submitPaste() {
  const text = pasteText.value.trim()
  if (!text || extracting.value) return
  const keywords = pasteKeywords.value
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
  extracting.value = true
  const payload = {
    text,
    source_type: 'personal',
    source_label: pasteTitle.value.trim() || '用户输入',
    title: pasteTitle.value.trim() || '',
    keywords,
  }
  api.post('/api/kb/ingest', payload)
    .then(() => {
      ElMessage.success(t('kb.jobQueued'))
      pasteText.value = ''
      pasteTitle.value = ''
      pasteKeywords.value = ''
    })
    .catch(e => {
      ElMessage.error(e?.response?.data?.detail || '提交失败')
    })
    .finally(() => {
      extracting.value = false
    })
}

// 预览弹窗状态
const previewVisible = ref(false)
const previewSubmitting = ref(false)
const previewMeta = ref({})   // 直接存 IngestRequest 源字段（保证溯源字段完整传递）
const previewText = ref('')

function openPreview(text, meta) {
  previewText.value = text || ''
  previewMeta.value = meta || {}
  previewVisible.value = true
}

async function submitLink() {
  if (!linkUrl.value.trim()) return
  extracting.value = true
  try {
    const res = await api.post('/api/kb/extract/link', {
      url: linkUrl.value.trim(),
    }, { timeout: 180000 })
    const d = res.data || {}
    openPreview(d.text, {
      source_type: 'online',
      platform: d.platform || '',
      original_url: d.url || linkUrl.value.trim(),
      source_label: d.url || linkUrl.value.trim(),
      title: d.title || '',
      keywords: d.keywords || [],
      video: d.video || '',
      images: d.images || [],
      pdf_url: d.pdf_url || '',
    })
    if (d.error) ElMessage.warning(d.error)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提取失败')
  } finally {
    extracting.value = false
  }
}

function onFilePick(e) {
  const file = e.target.files?.[0]
  if (file) pendingFile.value = file
  e.target.value = ''
}

function onDropFile(e) {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) pendingFile.value = file
}

async function submitFile() {
  if (!pendingFile.value) return
  extracting.value = true
  try {
    const fd = new FormData()
    fd.append('file', pendingFile.value)
    const isZip = /\.zip$/i.test(pendingFile.value.name)
    // zip 压缩包：直接入队批量导入（后台解压逐个整理），不做单文件提取预览
    if (isZip) {
      const res = await api.post('/api/kb/ingest/zip', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      })
      const d = res.data || {}
      ElMessage.success(d.count ? `${d.count} 个文件已加入后台任务` : t('kb.jobQueued'))
      pendingFile.value = null
      return
    }
    const res = await api.post('/api/kb/extract/file', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    const d = res.data || {}
    openPreview(d.text, {
      source_type: 'local_file',
      file_name: d.file_name || pendingFile.value.name,
      file_type: d.file_type || '',
      file_digest: d.file_digest || '',
      raw_file: d.raw_file || '',
      source_label: d.file_name || pendingFile.value.name,
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提取失败')
  } finally {
    extracting.value = false
  }
}

// 预览确认：文本 + 来源元信息 -> 交给 AI 整理（入队）
async function handlePreviewConfirm(text) {
  const p = previewMeta.value
  const payload = { text, source_type: p.source_type || 'personal', source_label: p.source_label || '用户输入' }
  for (const k of ['platform', 'original_url', 'file_name', 'file_type', 'file_digest', 'raw_file', 'title', 'keywords', 'video', 'images']) {
    if (p[k] !== undefined && p[k] !== null && p[k] !== '') payload[k] = p[k]
  }
  previewSubmitting.value = true
  try {
    await api.post('/api/kb/ingest', payload)
    ElMessage.success(t('kb.jobQueued'))
    previewVisible.value = false
    linkUrl.value = ''
    pendingFile.value = null
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    previewSubmitting.value = false
  }
}

// ===== 任务 =====
const jobs = ref([])
const jobsTotal = ref(0)
const jobsPage = ref(1)
const jobsPageSize = ref(20)

async function loadJobs() {
  try {
    const res = await getJobs(jobsPage.value, jobsPageSize.value)
    jobs.value = res.data.items || []
    jobsTotal.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

function onJobsPageChange(p) {
  jobsPage.value = p
  loadJobs()
}

function fmtTime(v) {
  if (!v) return ''
  const d = new Date(v)
  if (isNaN(d.getTime())) return String(v)
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

function jobTypeLabel(t) {
  return ({ ingest_text: '文本导入', ingest_file: '文件导入', ingest_link: '链接导入', build_graph: '图谱构建' })[t] || t
}

function jobStatusLabel(s) {
  return ({ queued: '排队中', running: '执行中', done: '完成', failed: '失败' })[s] || s
}

// ===== 通用 =====
async function loadSessions() {
  try {
    const res = await api.get('/api/chat/sessions')
    sessions.value = res.data || []
  } catch {
    sessions.value = []
  }
}

function goToChat() { router.push({ name: 'chat' }) }
function goToSession(s) { router.push({ name: 'chat-session', params: { sessionId: s.id } }) }
function handleLogout() { auth.logout(); router.push({ name: 'login' }) }

onMounted(() => {
  loadSessions()
  loadPages()
  loadJobs()
})
</script>

<style scoped>
.kb-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-base-secondary, #f7f7f8);
}
.kb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 28px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #fff;
}
.kb-title { margin: 0; font-size: 20px; font-weight: 600; color: #111827; }
.kb-desc { margin: 6px 0 0; font-size: 13px; color: #6b7280; max-width: 560px; line-height: 1.45; }
.kb-head-left { min-width: 0; flex-shrink: 0; }

.kb-tabs {
  display: flex;
  gap: 4px;
  padding: 0 28px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.kb-tab {
  padding: 10px 14px;
  font-size: 14px;
  color: #6b7280;
  border: none;
  background: transparent;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.kb-tab:hover { color: #111827; }
.kb-tab.active { color: #111827; font-weight: 600; border-bottom-color: #2563eb; }

.kb-body { flex: 1; overflow: hidden; padding: 16px 28px 20px; }
.kb-empty { color: #9ca3af; font-size: 14px; padding: 40px 0; text-align: center; }
.kb-empty-main { padding: 60px 0; }
.kb-empty-main .ds-btn { margin-top: 12px; }

/* ===== Wiki ===== */
.kb-wiki {
  display: flex;
  gap: 14px;
  height: 100%;
}
.kb-wiki-side {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
}
.kb-wiki-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid #f0f0f0;
}
.kb-wiki-count { font-size: 12px; color: #9ca3af; font-weight: 400; }
.kb-page-list { flex: 1; overflow: auto; }
.kb-folder-head {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px 3px;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid #f7f7f8;
}
.kb-folder-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-folder-del {
  display: none;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  padding: 3px;
  border-radius: 4px;
  flex-shrink: 0;
}
.kb-folder-head:hover .kb-folder-del { display: inline-flex; }
.kb-folder-del:hover { color: #dc2626; background: #fef2f2; }
.kb-page-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 12px 7px 28px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.kb-page-item:hover { background: #f9fafb; }
.kb-page-item.active { background: #eff6ff; }
.kb-page-title {
  font-size: 13px;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.kb-wiki-main {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 18px 22px;
  overflow: auto;
}
.kb-page-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.kb-page-detail-title { margin: 0; font-size: 17px; font-weight: 600; color: #111827; }
.kb-page-detail-actions { display: flex; gap: 8px; flex-shrink: 0; }
.kb-page-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.kb-meta-chip {
  font-size: 11px;
  color: #374151;
  background: #f3f4f6;
  border-radius: 6px;
  padding: 3px 8px;
}
.kb-page-content { font-size: 14px; }

/* ===== Import ===== */
.kb-import {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--spacer-16, 16px);
  align-items: start;
  width: 100%;
  box-sizing: border-box;
}
.kb-import-col {
  display: flex;
  flex-direction: column;
  gap: var(--spacer-16, 16px);
  min-width: 0;
}
@media (max-width: 900px) {
  .kb-import {
    grid-template-columns: minmax(0, 1fr);
  }
}
.kb-import-card {
  background: var(--bg-base-default, #fff);
  border: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
  border-radius: var(--radius-12, 12px);
  padding: var(--spacer-20, 20px) var(--spacer-24, 24px);
  display: flex;
  flex-direction: column;
  gap: var(--spacer-14, 14px);
}
.kb-import-card-head {
  display: flex;
  align-items: flex-start;
  gap: var(--spacer-12, 12px);
}
.kb-import-card-icon {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-9, 9px);
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  color: var(--icon-secondary, #404040);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kb-import-title {
  margin: 0;
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-default, #171717);
  letter-spacing: -0.01em;
}
.kb-import-hint {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, #737373);
  line-height: 1.5;
}
.kb-textarea {
  width: 100%;
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.65;
  font-family: inherit;
  box-sizing: border-box;
  color: var(--text-default, #171717);
  background: var(--bg-base-default, #fff);
  resize: vertical;
  min-height: 120px;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.kb-textarea:focus {
  outline: none;
  border-color: var(--text-default, #171717);
  box-shadow: 0 0 0 3px rgba(23, 23, 23, 0.08);
}
.kb-import-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacer-12, 12px);
}
.kb-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacer-6, 6px);
}
.kb-field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #404040);
}
.kb-import-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacer-12, 12px);
}
.kb-import-charcount {
  font-size: 12px;
  color: var(--text-tertiary, #737373);
  font-family: var(--font-family-mono, ui-monospace, monospace);
}
.kb-import-row {
  display: flex;
  gap: var(--spacer-10, 10px);
}
.kb-input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-8, 8px);
  padding: 9px 12px;
  font-size: 13px;
  font-family: inherit;
  box-sizing: border-box;
  color: var(--text-default, #171717);
  background: var(--bg-base-default, #fff);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.kb-input:focus {
  outline: none;
  border-color: var(--text-default, #171717);
  box-shadow: 0 0 0 3px rgba(23, 23, 23, 0.08);
}
.kb-input::placeholder {
  color: var(--text-tertiary, #737373);
}
.kb-dropzone {
  border: 1.5px dashed var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  padding: 36px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacer-10, 10px);
  color: var(--text-tertiary, #737373);
  background: var(--bg-base-secondary, #f5f5f5);
  transition: border-color 150ms ease, background-color 150ms ease;
}
.kb-dropzone.dragging {
  border-color: var(--text-default, #171717);
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
}
.kb-dropzone-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary, #404040);
}
.kb-dropzone-actions {
  display: flex;
  gap: var(--spacer-8, 8px);
}

/* 主按钮黑色 */
.kb-import .ds-btn-primary {
  background-color: var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
  border-color: var(--text-default, #171717);
}
.kb-import .ds-btn-primary:hover:not(:disabled) {
  background-color: var(--icon-default-hover, #171717);
  border-color: var(--icon-default-hover, #171717);
}
.kb-import .ds-btn-primary:disabled {
  background-color: var(--bg-overlay-l2, rgba(115,115,115,0.12));
  border-color: var(--border-neutral-l1, rgba(115,115,115,0.12));
  color: var(--text-tertiary, #737373);
}

/* ===== Jobs ===== */
.kb-jobs { display: flex; flex-direction: column; gap: 12px; }
.kb-jobs-head { display: flex; justify-content: flex-end; }
.kb-jobs-pager { display: flex; justify-content: center; margin-top: 4px; }
.kb-jobs-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
  font-size: 13px;
}
.kb-jobs-table th, .kb-jobs-table td {
  padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
  color: #374151;
}
.kb-jobs-table th { background: #f9fafb; font-weight: 600; color: #6b7280; }
.kb-job-status {
  font-size: 11px;
  border-radius: 4px;
  padding: 2px 8px;
  font-weight: 600;
}
.kb-job-status.st-queued { background: #fef3c7; color: #b45309; }
.kb-job-status.st-running { background: #dbeafe; color: #1d4ed8; }
.kb-job-status.st-done { background: #d1fae5; color: #047857; }
.kb-job-status.st-failed { background: #fee2e2; color: #b91c1c; }
.kb-job-error {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #b91c1c;
}
</style>
