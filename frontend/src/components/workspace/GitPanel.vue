<template>
  <div class="git-panel">
    <div class="git-toolbar">
      <div class="git-branch">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
          <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
        </svg>
        <span class="branch-name">{{ branch || (isRepo ? 'unknown' : '未初始化仓库') }}</span>
      </div>
      <template v-if="isRepo">
        <button type="button" class="git-btn" title="刷新" @click="refresh">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/>
          </svg>
        </button>
        <button type="button" class="git-btn" title="拉取" @click="pull">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>
          </svg>
        </button>
        <button type="button" class="git-btn" title="推送" @click="push">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 21V9M7 14l5-5 5 5M5 3h14"/>
          </svg>
        </button>
      </template>
      <template v-else>
        <button type="button" class="git-btn" title="初始化仓库" @click="initRepo">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M12 5v14"/>
          </svg>
        </button>
      </template>
    </div>

    <div class="git-body">
      <div v-if="loading" class="git-loading">加载中...</div>
      <div v-else-if="!workDir" class="git-empty">请先选择工作目录</div>
      <div v-else-if="!isRepo" class="git-init-guide">
        <div class="git-init-guide-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
            <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
          </svg>
        </div>
        <div class="git-init-guide-title">当前打开的文件夹中没有 Git 存储库</div>
        <div class="git-init-guide-desc">可初始化一个仓库，它将实现 Git 提供支持的源代码管理功能。</div>
        <button class="git-init-guide-btn" @click="initRepo">初始化仓库</button>
      </div>

      <template v-else>
        <!-- 上半部分：提交 + 文件列表 -->
        <div class="git-changes-area">
          <div class="git-commit-area">
            <input
              v-model="commitMessage"
              class="git-commit-input"
              :placeholder="`提交更改内容 (Ctrl+Enter 在 '${branch || 'master'}' 上)`"
              @keydown.ctrl.enter="commit"
              @keydown.meta.enter="commit"
              ref="commitInputRef"
            />
            <button
              class="git-commit-btn"
              :disabled="!commitMessage.trim() || files.length === 0"
              @click="commit"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <span>提交 Ctrl+Enter</span>
            </button>
          </div>

          <div v-if="files.length === 0" class="git-empty">没有未提交的更改</div>
          <div v-else>
            <div class="git-section-header">
              <span class="git-section-title">更改</span>
              <span class="git-section-count">{{ files.length }}</span>
            </div>
            <div class="git-file-list">
              <div
                v-for="file in files"
                :key="file.path"
                class="git-file-item"
                :class="{ active: selectedFile === file.path }"
                @click="selectFile(file.path)"
              >
                <span class="git-file-status" :class="file.status">{{ file.status }}</span>
                <span class="git-file-path" :title="file.path">{{ file.path }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 拖动条 -->
        <div v-if="commits.length > 0" class="git-resize-handle" @mousedown="startResizeHistory"></div>

        <!-- 下半部分：提交历史 -->
        <div v-if="commits.length > 0" class="git-history-area" :style="{ height: historyHeight + 'px' }">
          <div class="git-section-header">
            <span class="git-section-title">历史记录</span>
            <span class="git-section-count">{{ commits.length }}</span>
          </div>
        <div class="git-commit-list">
            <div
              v-for="(c, idx) in commits"
              :key="c.hash"
              class="git-commit-wrapper"
            >
              <div
                class="git-commit-item"
                :class="{ expanded: expandedCommit === c.hash }"
                @click="toggleCommit(c.hash)"
              >
                <div class="git-commit-left">
                  <div class="git-commit-dot" :class="{ 'git-commit-dot-head': idx === 0 }"></div>
                  <div v-if="idx < commits.length - 1" class="git-commit-line"></div>
                </div>
                <div class="git-commit-body">
                  <div class="git-commit-message" :title="c.message">{{ c.message }}</div>
                  <div class="git-commit-meta">
                    <span class="git-commit-author">{{ c.author }}</span>
                    <span class="git-commit-date">{{ c.date }}</span>
                  </div>
                </div>
                <div class="git-commit-right">
                  <span v-if="idx === 0 && branch" class="git-commit-branch">{{ branch }}</span>
                  <span class="git-commit-hash">{{ c.short_hash }}</span>
                </div>
              </div>
              <!-- 展开的文件列表 -->
              <div v-if="expandedCommit === c.hash" class="git-commit-files">
                <div
                  v-for="f in commitFiles[c.hash]"
                  :key="f.path"
                  class="git-commit-file"
                  @click.stop="selectCommitFile(f.path, c.hash)"
                >
                  <span class="git-commit-file-status" :class="f.status">{{ f.status }}</span>
                  <span class="git-commit-file-path" :title="f.path">{{ f.path }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useModelStore } from '@/stores/model'
import { storeToRefs } from 'pinia'

const props = defineProps<{
  visible?: boolean
}>()

const emit = defineEmits<{
  showDiff: [filePath: string]
  showCommitDiff: [filePath: string, hash: string]
}>()

const workspace = useWorkspaceStore()
const { workDir } = storeToRefs(workspace)
const modelStore = useModelStore()

interface GitFile {
  path: string
  status: 'M' | 'A' | 'D' | 'R' | '?' | 'U'
}

interface GitCommit {
  hash: string
  short_hash: string
  message: string
  author: string
  email: string
  date: string
}

const branch = ref('')
const files = ref<GitFile[]>([])
const commits = ref<GitCommit[]>([])
const loading = ref(false)
const selectedFile = ref<string | null>(null)
const isRepo = ref(true)
const commitMessage = ref('')
const commitInputRef = ref<HTMLInputElement | null>(null)
const historyHeight = ref(200)
const expandedCommit = ref<string | null>(null)
const commitFiles = ref<Record<string, { path: string; status: string }[]>>({})

// 拖动调整历史记录区域高度
let resizingHistory = false
let startY = 0
let startHeight = 0

function startResizeHistory(e: MouseEvent) {
  resizingHistory = true
  startY = e.clientY
  startHeight = historyHeight.value
  document.addEventListener('mousemove', onResizeHistory)
  document.addEventListener('mouseup', stopResizeHistory)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onResizeHistory(e: MouseEvent) {
  if (!resizingHistory) return
  const delta = startY - e.clientY
  historyHeight.value = Math.min(Math.max(startHeight + delta, 100), 500)
}

function stopResizeHistory() {
  resizingHistory = false
  document.removeEventListener('mousemove', onResizeHistory)
  document.removeEventListener('mouseup', stopResizeHistory)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

function getBaseUrl() {
  return modelStore.getBaseUrl()
}

async function refresh() {
  if (!workDir.value) return
  loading.value = true
  try {
    const res = await fetch(`${getBaseUrl()}/git/repo-info?work_dir=${encodeURIComponent(workDir.value)}`)
    if (res.ok) {
      const data = await res.json()
      isRepo.value = data.is_repo
      branch.value = data.branch || ''
    }
    if (isRepo.value) {
      const [statusRes, logRes] = await Promise.all([
        fetch(`${getBaseUrl()}/git/status?work_dir=${encodeURIComponent(workDir.value)}`),
        fetch(`${getBaseUrl()}/git/log?work_dir=${encodeURIComponent(workDir.value)}&limit=30`),
      ])
      if (statusRes.ok) {
        const data = await statusRes.json()
        files.value = (data.files || []).map((f: any) => ({
          path: f.path,
          status: f.status,
        }))
      }
      if (logRes.ok) {
        const data = await logRes.json()
        commits.value = data.commits || []
      }
    } else {
      files.value = []
      commits.value = []
    }
  } catch (e) {
    console.error('Git 状态获取失败', e)
  } finally {
    loading.value = false
  }
}

function selectFile(path: string) {
  selectedFile.value = path
  emit('showDiff', path)
}

async function commit() {
  if (!commitMessage.value.trim() || !workDir.value || files.value.length === 0) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/commit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        work_dir: workDir.value,
        message: commitMessage.value.trim(),
      }),
    })
    if (res.ok) {
      commitMessage.value = ''
      await refresh()
    }
  } catch (e) {
    console.error('提交失败', e)
  }
}

async function pull() {
  if (!workDir.value) return
  try {
    await fetch(`${getBaseUrl()}/git/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    await refresh()
  } catch (e) {
    console.error('拉取失败', e)
  }
}

async function push() {
  if (!workDir.value) return
  try {
    await fetch(`${getBaseUrl()}/git/push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    await refresh()
  } catch (e) {
    console.error('推送失败', e)
  }
}

async function initRepo() {
  if (!workDir.value) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    if (res.ok) {
      await refresh()
    }
  } catch (e) {
    console.error('初始化仓库失败', e)
  }
}

async function toggleCommit(hash: string) {
  if (expandedCommit.value === hash) {
    expandedCommit.value = null
    return
  }
  expandedCommit.value = hash
  if (!commitFiles.value[hash] && workDir.value) {
    try {
      const res = await fetch(`${getBaseUrl()}/git/commit-files?work_dir=${encodeURIComponent(workDir.value)}&hash=${encodeURIComponent(hash)}`)
      if (res.ok) {
        const data = await res.json()
        commitFiles.value[hash] = data.files || []
      }
    } catch (e) {
      console.error('加载 commit 文件失败', e)
    }
  }
}

function selectCommitFile(path: string, hash: string) {
  emit('showCommitDiff', path, hash)
}

watch(workDir, () => refresh())

onMounted(() => {
  if (props.visible) refresh()
})

watch(() => props.visible, (val) => {
  if (val) refresh()
})
</script>

<style scoped>
.git-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #fff;
}

.git-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.git-branch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
}

.branch-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.git-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
  flex-shrink: 0;
}

.git-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.git-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.git-changes-area {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.git-resize-handle {
  height: 6px;
  cursor: row-resize;
  flex-shrink: 0;
  background: transparent;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  transition: background 0.12s;
}

.git-resize-handle:hover {
  background: rgba(0, 120, 212, 0.15);
}

.git-history-area {
  overflow-y: auto;
  min-height: 100px;
  max-height: 500px;
  flex-shrink: 0;
}

.git-loading,
.git-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
}

.git-commit-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 10px 8px;
  border-bottom: 1px solid var(--border);
}

.git-commit-input {
  width: 100%;
  padding: 5px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
  background: #fff;
  color: var(--text);
  font-family: inherit;
}

.git-commit-input::placeholder {
  color: var(--text-muted);
}

.git-commit-input:focus {
  border-color: var(--accent, #0078d4);
}

.git-commit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  background: #1a1a1a;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: opacity 0.12s;
  flex-shrink: 0;
}

.git-commit-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.git-commit-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.git-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.git-section-count {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}

.git-file-list {
  padding: 2px 0;
}

.git-file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  cursor: pointer;
  transition: background 0.12s;
  font-size: 12px;
}

.git-file-item:hover {
  background: var(--accent-hover);
}

.git-file-item.active {
  background: var(--accent-active);
}

.git-file-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 10px;
  font-weight: 700;
  border-radius: 3px;
  flex-shrink: 0;
}

.git-file-status.M { color: #c19c00; }
.git-file-status.A { color: #107c10; }
.git-file-status.D { color: #c50f1f; }
.git-file-status.R { color: #0037da; }
.git-file-status.\?  { color: #881798; }
.git-file-status.U { color: #c50f1f; }

.git-file-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.git-init-guide {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  gap: 12px;
}

.git-init-guide-icon {
  color: var(--text-muted);
  margin-bottom: 4px;
}

.git-init-guide-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}

.git-init-guide-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  max-width: 280px;
}

.git-init-guide-btn {
  margin-top: 8px;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  background: var(--accent-hover, #f0f0f0);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.12s;
}

.git-init-guide-btn:hover {
  background: var(--accent-active, #e0e0e0);
}

.git-commit-list {
  padding: 2px 0;
}

.git-commit-wrapper {
  font-size: 12px;
}

.git-commit-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.12s;
}

.git-commit-item:hover {
  background: var(--accent-hover);
}

.git-commit-item.expanded {
  background: var(--accent-active);
}

.git-commit-files {
  padding-left: 28px;
  padding-bottom: 4px;
}

.git-commit-file {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11px;
  transition: background 0.12s;
  border-radius: 3px;
}

.git-commit-file:hover {
  background: var(--accent-hover);
}

.git-commit-file-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  font-size: 9px;
  font-weight: 700;
  border-radius: 2px;
  flex-shrink: 0;
}

.git-commit-file-status.M { color: #c19c00; }
.git-commit-file-status.A { color: #107c10; }
.git-commit-file-status.D { color: #c50f1f; }
.git-commit-file-status.R { color: #0037da; }
.git-commit-file-status.\? { color: #881798; }
.git-commit-file-status.U { color: #c50f1f; }

.git-commit-file-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.git-commit-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 14px;
  flex-shrink: 0;
  padding-top: 5px;
}

.git-commit-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}

.git-commit-dot-head {
  background: var(--accent, #0078d4);
  box-shadow: 0 0 0 2px rgba(0, 120, 212, 0.2);
}

.git-commit-line {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: var(--border);
  margin-top: 2px;
}

.git-commit-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
}

.git-commit-message {
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.git-commit-meta {
  display: flex;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.git-commit-author {
  font-weight: 500;
}

.git-commit-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding-top: 2px;
}

.git-commit-branch {
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  background: var(--accent, #0078d4);
  padding: 1px 6px;
  border-radius: 10px;
}

.git-commit-hash {
  font-size: 11px;
  color: var(--text-muted);
  font-family: monospace;
}
</style>
