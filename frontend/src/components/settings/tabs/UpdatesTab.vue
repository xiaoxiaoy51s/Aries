<template>
  <div class="settings-section">
    <p class="section-desc">
      对比 GitHub Releases 检查是否有新版本；也可自行拉取源码本地修改与运行。
    </p>

    <!-- 当前版本 -->
    <div class="update-card">
      <div class="update-card-header">
        <span class="update-label">当前版本</span>
        <span class="update-version">{{ currentVersion }}</span>
      </div>
    </div>

    <!-- 源代码仓库 -->
    <div class="update-card source-card">
      <div class="source-card-header">
        <span class="update-label">源代码仓库</span>
        <button type="button" class="source-open-btn" @click="openRepoPage">在浏览器打开</button>
      </div>
      <a class="source-repo-link" href="#" @click.prevent="openRepoPage">{{ repoUrl }}</a>
      <p class="source-hint">
        项目开源，你可以自行克隆或拉取最新代码，在本地修改、调试或二次开发。
      </p>
      <div class="source-commands">
        <div class="source-cmd-row">
          <span class="source-cmd-label">首次克隆</span>
          <code class="source-cmd-code">{{ cloneCommand }}</code>
        </div>
        <div class="source-cmd-row">
          <span class="source-cmd-label">已有仓库更新</span>
          <code class="source-cmd-code">git pull</code>
        </div>
      </div>
    </div>

    <!-- 检查状态 -->
    <div class="update-actions">
      <button
        type="button"
        class="update-check-btn"
        :disabled="checking || downloading"
        @click="handleCheck(true)"
      >{{ checking ? '检查中...' : '检查更新' }}</button>
    </div>

    <!-- 错误 -->
    <div v-if="checkError" class="update-result fail">
      {{ checkError }}
    </div>
    <div v-else-if="updateStore.updateError" class="update-result fail">
      {{ updateStore.updateError }}
    </div>

    <!-- 有新版本 -->
    <div v-else-if="updateInfo && updateInfo.update_available" class="update-result available">
      <div class="update-result-header">
        <span class="update-badge">有新版本</span>
        <span class="update-latest">v{{ updateInfo.latest_version }}</span>
        <span v-if="updateInfo.release_name" class="update-release-name">{{ updateInfo.release_name }}</span>
      </div>
      <p v-if="updateInfo.published_at" class="update-published">
        发布于 {{ formatDate(updateInfo.published_at) }}
      </p>
      <div v-if="updateInfo.release_notes" class="update-notes">
        <div class="update-notes-title">更新说明</div>
        <div class="update-notes-body" v-html="sanitizedNotes"></div>
      </div>

      <!-- 下载中 -->
      <div v-if="updateStore.downloading" class="update-download-progress">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: updateStore.downloadProgress + '%' }"></div>
        </div>
        <span class="progress-text">{{ updateStore.downloadProgress }}%</span>
      </div>

      <!-- 下载完成 -->
      <div v-else-if="updateStore.downloaded" class="update-install-section">
        <p class="update-ready-text">更新已下载完成，点击安装并重启。</p>
        <button type="button" class="update-install-btn" @click="handleInstall">
          安装并重启
        </button>
      </div>

      <!-- 未下载 -->
      <div v-else class="update-download-section">
        <button type="button" class="update-download-btn" @click="handleDownload">
          下载更新
        </button>
        <button type="button" class="update-manual-btn" @click="openReleasePage">
          前往 GitHub 手动下载
        </button>
      </div>
    </div>

    <div v-else-if="updateInfo && !updateInfo.error" class="update-result success">
      已是最新版本
      <span v-if="updateInfo.latest_version">（v{{ updateInfo.latest_version }}）</span>
    </div>

    <div v-else-if="updateInfo?.error && !updateInfo.latest_version" class="update-result warn">
      {{ updateInfo.error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import DOMPurify from 'dompurify'
import { useUpdateStore } from '@/stores/update'
import { getAppVersion } from '@/api/update'
import { openUrl } from '@/api/system'

const updateStore = useUpdateStore()

const REPO_SLUG = 'xiaoxiaoy51s/Aries'
const repoUrl = `https://github.com/${REPO_SLUG}`
const cloneCommand = `git clone ${repoUrl}.git`

const currentVersion = ref('...')
const checkError = ref<string | null>(null)

const checking = computed(() => updateStore.checking)
const updateInfo = computed(() => updateStore.result)
const sanitizedNotes = computed(() => {
  const raw = updateInfo.value?.release_notes
  if (!raw) return ''
  return DOMPurify.sanitize(raw.trim(), { USE_PROFILES: { html: true } })
})

async function loadCurrentVersion() {
  try {
    const info = await getAppVersion()
    currentVersion.value = info.version
  } catch {
    currentVersion.value = '未知'
  }
}

async function handleCheck(force = false) {
  checkError.value = null
  const data = await updateStore.check(force)
  if (!data) {
    checkError.value = '无法连接更新服务，请稍后重试'
  }
}

function handleDownload() {
  updateStore.download()
}

function handleInstall() {
  updateStore.install()
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function openReleasePage() {
  const url = updateInfo.value?.release_url
  if (url) void openUrl(url)
}

function openRepoPage() {
  void openUrl(repoUrl)
}

onMounted(async () => {
  await loadCurrentVersion()
  if (!updateStore.checked) {
    await handleCheck(false)
  }
})
</script>

<style scoped>
.settings-section {
  max-width: 640px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 20px;
}

.section-desc code {
  font-size: 12px;
  background: var(--accent-hover);
  padding: 1px 5px;
  border-radius: 4px;
}

.update-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  background: var(--bg-sidebar);
  margin-bottom: 16px;
}

.update-card-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.update-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.update-version {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.source-card {
  margin-bottom: 16px;
}

.source-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.source-open-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
}

.source-open-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.source-repo-link {
  display: inline-block;
  font-size: 14px;
  font-weight: 500;
  color: #2563eb;
  text-decoration: none;
  word-break: break-all;
}

.source-repo-link:hover {
  text-decoration: underline;
}

.source-hint {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.source-commands {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-cmd-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.source-cmd-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.source-cmd-code {
  display: block;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  word-break: break-all;
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
}

.update-actions {
  margin-bottom: 16px;
}

.update-check-btn {
  padding: 8px 18px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
}

.update-check-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.update-check-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.update-result {
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.5;
}

.update-result.success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.update-result.fail {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.update-result.warn {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}

.update-result.available {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: var(--text);
}

.update-result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.update-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  background: #2563eb;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.update-latest {
  font-size: 18px;
  font-weight: 600;
}

.update-release-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.update-published {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.update-notes {
  margin: 12px 0;
}

.update-notes-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.update-notes-body {
  margin: 0;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  font-family: inherit;
}

.update-notes-body :deep(h1),
.update-notes-body :deep(h2),
.update-notes-body :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.update-notes-body :deep(ul),
.update-notes-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.update-notes-body :deep(li) {
  margin: 2px 0;
}

.update-notes-body :deep(p) {
  margin: 4px 0;
}

.update-notes-body :deep(a) {
  color: var(--accent, #4f8cff);
  text-decoration: underline;
}

.update-notes-body :deep(code) {
  font-family: ui-monospace, monospace;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 4px;
  border-radius: 3px;
}

.update-download-section {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.update-download-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: none;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}

.update-download-btn:hover {
  background: #1d4ed8;
}

.update-manual-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s;
}

.update-manual-btn:hover {
  background: var(--accent-hover);
}

.update-download-progress {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: rgba(37, 99, 235, 0.15);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #2563eb;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  font-weight: 600;
  color: #2563eb;
  font-variant-numeric: tabular-nums;
  min-width: 40px;
  text-align: right;
}

.update-install-section {
  margin-top: 14px;
}

.update-ready-text {
  font-size: 13px;
  color: #166534;
  margin-bottom: 10px;
}

.update-install-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: none;
  border-radius: 8px;
  background: #16a34a;
  color: #fff;
  cursor: pointer;
  transition: background 0.15s;
}

.update-install-btn:hover {
  background: #15803d;
}
</style>
