<template>
  <div class="git-panel">
    <div class="git-toolbar">
      <div
        v-if="isRepo"
        class="git-branch-selector"
        :class="{ expanded: branchDropdownVisible }"
        @click.stop="toggleBranchDropdown"
         title="点击查看分支列表"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
          <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
        </svg>
        <span class="branch-name">{{ branch || 'unknown' }}</span>
        <svg class="dropdown-arrow" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </div>
      <div v-else class="git-branch-selector">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
          <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
        </svg>
        <span class="branch-name">未初始化仓库</span>
      </div>
      <template v-if="isRepo">
        <button type="button" class="git-text-btn" :class="{ active: branchDropdownVisible }" title="Branches" @click.stop="toggleBranchDropdown">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
            <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
          </svg>
          Branches
        </button>
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

    <!-- 分支下拉列表 -->
    <div v-if="branchDropdownVisible && isRepo" class="git-branch-dropdown">
      <div class="branch-dropdown-header">
        <span class="branch-dropdown-title">Branches</span>
        <button type="button" class="branch-create-btn" @click="startCreateBranch">New Branch</button>
      </div>
      <div class="branch-list">
        <div
          v-for="b in allBranches"
          :key="b.name"
          class="branch-item"
          :class="{ active: b.name === branch, remote: b.isRemote }"
          @click="checkoutBranch(b.name)"
          @contextmenu.prevent="showBranchContextMenu($event, b)"
        >
          <svg
            v-if="b.name === branch"
            class="branch-check-icon"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          <svg
            v-else-if="b.isRemote"
            class="branch-remote-icon"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/><path d="M2 12h3M19 12h3"/>
          </svg>
          <svg
            v-else
            class="branch-local-icon"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/>
            <path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/>
          </svg>
          <span class="branch-item-name" :title="b.name">{{ b.name }}</span>
        </div>
      </div>
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
                <span class="git-file-icon">
                  <img
                    :src="getFileIconSrc(file.path)"
                    width="16"
                    height="16"
                    alt=""
                    @error="(e: Event) => ((e.target as HTMLImageElement).style.display = 'none')"
                  />
                </span>
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
                @contextmenu.prevent="showCommitContextMenu($event, c)"
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
                  <span class="git-commit-file-icon">
                    <img
                      :src="getFileIconSrc(f.path)"
                      width="16"
                      height="16"
                      alt=""
                      @error="(e: Event) => ((e.target as HTMLImageElement).style.display = 'none')"
                    />
                  </span>
                  <span class="git-commit-file-path" :title="f.path">{{ f.path }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 提交右键菜单 -->
    <Teleport to="body">
      <div
        v-if="commitContextMenu.visible"
        class="git-context-menu"
        :style="{ left: commitContextMenu.x + 'px', top: commitContextMenu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-item" @click="openCommitOnGithub">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          Open on GitHub
        </div>
        <div class="ctx-item" @click="copyCommitHash">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy commit ID
        </div>
        <div class="ctx-item" @click="copyCommitMessage">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy commit message
        </div>
      </div>
    </Teleport>

    <!-- 分支右键菜单 -->
    <Teleport to="body">
      <div
        v-if="branchContextMenu.visible"
        class="git-context-menu"
        :style="{ left: branchContextMenu.x + 'px', top: branchContextMenu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-item" @click="checkoutBranchFromMenu">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/><path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/></svg>
          Checkout
        </div>
        <div class="ctx-item" @click="createBranchFrom">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          New branch from...
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item" @click="mergeBranchIntoCurrent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="12" r="3"/><path d="M6 9v6M9 6h6a3 3 0 0 1 3 3v0"/></svg>
          Merge into current
        </div>
        <div class="ctx-item" @click="pushBranch">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21V9M7 14l5-5 5 5M5 3h14"/></svg>
          Push...
        </div>
        <div class="ctx-item" @click="pullBranch">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>
          Pull
        </div>
        <div class="ctx-divider"></div>
        <div class="ctx-item" @click="renameBranch">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          Rename...
        </div>
        <div class="ctx-item ctx-item-danger" @click="deleteBranch">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          Delete
        </div>
      </div>
    </Teleport>

    <!-- 新建分支弹窗 -->
    <Teleport to="body">
      <div v-if="createBranchModal.visible" class="modal-overlay" @click="closeCreateBranchModal">
        <div class="modal-dialog" @click.stop>
          <div class="modal-header">{{ createBranchModal.fromBranch ? `New branch from '${createBranchModal.fromBranch}'` : 'New Branch' }}</div>
          <div class="modal-body">
            <input
              v-model="createBranchModal.name"
              type="text"
              class="form-input"
              placeholder="Enter branch name"
              @keyup.enter="confirmCreateBranch"
            />
          </div>
          <div class="modal-footer">
            <button class="modal-btn modal-btn-cancel" @click="closeCreateBranchModal">Cancel</button>
            <button class="modal-btn modal-btn-primary" :disabled="!createBranchModal.name.trim()" @click="confirmCreateBranch">Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 重命名分支弹窗 -->
    <Teleport to="body">
      <div v-if="renameBranchModal.visible" class="modal-overlay" @click="closeRenameBranchModal">
        <div class="modal-dialog" @click.stop>
          <div class="modal-header">Rename Branch</div>
          <div class="modal-body">
            <input
              v-model="renameBranchModal.newName"
              type="text"
              class="form-input"
              placeholder="Enter new branch name"
              @keyup.enter="confirmRenameBranch"
            />
          </div>
          <div class="modal-footer">
            <button class="modal-btn modal-btn-cancel" @click="closeRenameBranchModal">Cancel</button>
            <button class="modal-btn modal-btn-primary" :disabled="!renameBranchModal.newName.trim()" @click="confirmRenameBranch">Rename</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useModelStore } from '@/stores/model'
import { storeToRefs } from 'pinia'
import { getIconForFile, DEFAULT_FILE } from 'vscode-icons-js'

const ICON_CDN = './file-icons'

function getFileIconSrc(path: string): string {
  // 与 ExplorerTreeNode.vue 保持一致：基于文件名匹配 VSCode 图标
  const name = path.split('/').pop() || path
  const iconName = getIconForFile(name) || DEFAULT_FILE
  return `${ICON_CDN}/${iconName}`
}

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

// 右键菜单
const commitContextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  commit: null as GitCommit | null,
})
const remoteUrl = ref<string | null>(null)

// 分支
interface BranchInfo {
  name: string
  isRemote: boolean
}

const branchDropdownVisible = ref(false)
const localBranches = ref<string[]>([])
const remoteBranches = ref<string[]>([])
const allBranches = computed(() => {
  const list: BranchInfo[] = []
  localBranches.value.forEach((name) => list.push({ name, isRemote: false }))
  remoteBranches.value.forEach((name) => list.push({ name, isRemote: true }))
  return list
})

const branchContextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  branch: null as BranchInfo | null,
})

const createBranchModal = ref({
  visible: false,
  fromBranch: '',
  name: '',
})

const renameBranchModal = ref({
  visible: false,
  oldName: '',
  newName: '',
})

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
      const [statusRes, logRes, branchesRes, remoteBranchesRes] = await Promise.all([
        fetch(`${getBaseUrl()}/git/status?work_dir=${encodeURIComponent(workDir.value)}`),
        fetch(`${getBaseUrl()}/git/log?work_dir=${encodeURIComponent(workDir.value)}&limit=30`),
        fetch(`${getBaseUrl()}/git/branches?work_dir=${encodeURIComponent(workDir.value)}`),
        fetch(`${getBaseUrl()}/git/remote-branches?work_dir=${encodeURIComponent(workDir.value)}`),
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
      if (branchesRes.ok) {
        const data = await branchesRes.json()
        localBranches.value = (data.branches || []).filter((name: string) => name !== branch.value)
        // 当前分支放最前面
        if (branch.value) {
          localBranches.value.unshift(branch.value)
        }
      }
      if (remoteBranchesRes.ok) {
        const data = await remoteBranchesRes.json()
        remoteBranches.value = data.branches || []
      }
    } else {
      files.value = []
      commits.value = []
      localBranches.value = []
      remoteBranches.value = []
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
    const res = await fetch(`${getBaseUrl()}/git/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    const data = await res.json()
    if (!data.success) {
      showGitError(data, '拉取')
    }
    await refresh()
  } catch (e) {
    console.error('拉取失败', e)
  }
}

async function push() {
  if (!workDir.value) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    const data = await res.json()
    if (!data.success) {
      showGitError(data, '推送')
    }
    await refresh()
  } catch (e) {
    console.error('推送失败', e)
  }
}

/** 根据后端返回的 auth_error / github_connected 给出友好提示 */
function showGitError(data: any, action: string) {
  if (data.auth_error) {
    if (!data.github_connected) {
      alert(`${action} failed: GitHub not connected.\n\nPlease connect your GitHub account in Settings -> Account Binding -> GitHub.`)
    } else {
      alert(`${action} failed: GitHub authentication failed. Token may have expired.\n\nPlease reconnect your GitHub account in Settings -> Account Binding -> GitHub.`)
    }
  } else {
    alert(`${action} failed: ${data.message}`)
  }
}

// ---------- 提交右键菜单 ----------

function showCommitContextMenu(e: MouseEvent, commit: GitCommit) {
  commitContextMenu.value = {
    visible: true,
    x: e.clientX,
    y: e.clientY,
    commit,
  }
}

function hideContextMenu() {
  commitContextMenu.value.visible = false
  branchContextMenu.value.visible = false
  branchDropdownVisible.value = false
}

async function openCommitOnGithub() {
  const commit = commitContextMenu.value.commit
  hideContextMenu()
  if (!commit) return

  // 如果还没获取 remoteUrl，先获取
  if (remoteUrl.value === null && workDir.value) {
    try {
      const res = await fetch(`${getBaseUrl()}/git/remote-url?work_dir=${encodeURIComponent(workDir.value)}`)
      const data = await res.json()
      remoteUrl.value = data.url
    } catch {
      remoteUrl.value = null
    }
  }

  if (!remoteUrl.value) {
    alert('No remote repository URL found, cannot open on GitHub.')
    return
  }

  const url = `${remoteUrl.value}/commit/${commit.hash}`
  const electronAPI = (window as any).electronAPI
  if (electronAPI?.openExternal) {
    electronAPI.openExternal(url)
  } else {
    window.open(url, '_blank')
  }
}

async function copyCommitHash() {
  const commit = commitContextMenu.value.commit
  hideContextMenu()
  if (!commit) return
  await navigator.clipboard.writeText(commit.hash)
}

async function copyCommitMessage() {
  const commit = commitContextMenu.value.commit
  hideContextMenu()
  if (!commit) return
  await navigator.clipboard.writeText(commit.message)
}

// ---------- 分支操作 ----------

function toggleBranchDropdown() {
  branchDropdownVisible.value = !branchDropdownVisible.value
}

function hideBranchDropdown() {
  branchDropdownVisible.value = false
}

function showBranchContextMenu(e: MouseEvent, branchInfo: BranchInfo) {
  branchContextMenu.value = {
    visible: true,
    x: e.clientX,
    y: e.clientY,
    branch: branchInfo,
  }
}

function hideBranchContextMenu() {
  branchContextMenu.value.visible = false
}

async function checkoutBranch(name: string) {
  if (!workDir.value || name === branch.value) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, branch: name }),
    })
    const data = await res.json()
    if (data.success) {
      branchDropdownVisible.value = false
      await refresh()
    } else {
      alert(`Checkout failed: ${data.message}`)
    }
  } catch (e) {
    console.error('切换分支失败', e)
  }
}

async function checkoutBranchFromMenu() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b) return
  await checkoutBranch(b.name)
}

function startCreateBranch() {
  createBranchModal.value = {
    visible: true,
    fromBranch: '',
    name: '',
  }
  branchDropdownVisible.value = false
}

function createBranchFrom() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b) return
  createBranchModal.value = {
    visible: true,
    fromBranch: b.name,
    name: '',
  }
}

function closeCreateBranchModal() {
  createBranchModal.value.visible = false
}

async function confirmCreateBranch() {
  if (!workDir.value || !createBranchModal.value.name.trim()) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/create-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        work_dir: workDir.value,
        name: createBranchModal.value.name.trim(),
        checkout: true,
      }),
    })
    const data = await res.json()
    if (data.success) {
      closeCreateBranchModal()
      await refresh()
    } else {
      alert(`Create branch failed: ${data.message}`)
    }
  } catch (e) {
    console.error('创建分支失败', e)
  }
}

async function mergeBranchIntoCurrent() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b || !workDir.value) return
  if (b.name === branch.value) {
    alert('Cannot merge a branch into itself')
    return
  }
  if (!confirm(`Merge '${b.name}' into current branch '${branch.value}'?`)) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/merge-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, branch: b.name }),
    })
    const data = await res.json()
    if (data.success) {
      await refresh()
    } else {
      alert(`Merge failed: ${data.message}`)
    }
  } catch (e) {
    console.error('Merge branch failed', e)
  }
}

async function pushBranch() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b || !workDir.value) return
  const isRemote = b.isRemote
  const branchName = isRemote ? b.name.replace(/^origin\//, '') : b.name
  if (!confirm(`Push branch '${branchName}' to origin?`)) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/push-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        work_dir: workDir.value,
        branch: branchName,
        set_upstream: !isRemote,
      }),
    })
    const data = await res.json()
    if (data.success) {
      await refresh()
    } else {
      if (data.auth_error) {
        showGitError(data, 'Push')
      } else {
        alert(`Push failed: ${data.message}`)
      }
    }
  } catch (e) {
    console.error('Push branch failed', e)
  }
}

async function pullBranch() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b || !workDir.value) return
  const branchName = b.isRemote ? b.name.replace(/^origin\//, '') : b.name
  try {
    const res = await fetch(`${getBaseUrl()}/git/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value }),
    })
    const data = await res.json()
    if (!data.success) {
      if (data.auth_error) {
        showGitError(data, 'Pull')
      } else {
        alert(`Pull failed: ${data.message}`)
      }
    }
    await refresh()
  } catch (e) {
    console.error('Pull failed', e)
  }
}

function renameBranch() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b || b.isRemote) return
  renameBranchModal.value = {
    visible: true,
    oldName: b.name,
    newName: '',
  }
}

function closeRenameBranchModal() {
  renameBranchModal.value.visible = false
}

async function confirmRenameBranch() {
  if (!workDir.value || !renameBranchModal.value.newName.trim()) return
  try {
    const res = await fetch(`${getBaseUrl()}/git/rename-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        work_dir: workDir.value,
        old_name: renameBranchModal.value.oldName,
        new_name: renameBranchModal.value.newName.trim(),
      }),
    })
    const data = await res.json()
    if (data.success) {
      closeRenameBranchModal()
      await refresh()
    } else {
      alert(`Rename failed: ${data.message}`)
    }
  } catch (e) {
    console.error('Rename branch failed', e)
  }
}

async function deleteBranch() {
  const b = branchContextMenu.value.branch
  hideBranchContextMenu()
  if (!b || !workDir.value) return
  if (b.isRemote) {
    alert('Deleting remote branches is not supported yet')
    return
  }
  if (b.name === branch.value) {
    alert('Cannot delete the current branch')
    return
  }
  if (!confirm(`Delete branch '${b.name}'?`)) return
  try {
    const res = await fetch(
      `${getBaseUrl()}/git/branch?work_dir=${encodeURIComponent(workDir.value)}&branch=${encodeURIComponent(b.name)}`,
      { method: 'DELETE' }
    )
    const data = await res.json()
    if (data.success) {
      await refresh()
    } else {
      alert(`Delete failed: ${data.message}`)
    }
  } catch (e) {
    console.error('Delete branch failed', e)
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

watch(workDir, () => {
  remoteUrl.value = null
  refresh()
})

onMounted(() => {
  document.addEventListener('click', hideContextMenu)
  if (props.visible) refresh()
})

onUnmounted(() => {
  document.removeEventListener('click', hideContextMenu)
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
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.git-branch-selector {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text, #333);
  background: #fff;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}

.git-branch-selector:hover {
  background: var(--accent-hover, #f0f0f0);
}

.git-branch-selector.expanded {
  background: var(--accent-active, #e0e0e0);
  border-color: var(--border-strong, #ccc);
}

.branch-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.dropdown-arrow {
  margin-left: auto;
  transition: transform 0.15s;
}

.git-branch-selector.expanded .dropdown-arrow {
  transform: rotate(180deg);
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

.git-text-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.git-text-btn:hover {
  background: var(--accent-hover, #f0f0f0);
  color: var(--text, #333);
}

.git-text-btn.active {
  background: var(--accent-active, #e0e0e0);
  color: var(--text, #333);
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

.git-file-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

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

.git-commit-file-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

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

/* ---------- 右键菜单 ---------- */
.git-context-menu {
  position: fixed;
  z-index: 10000;
  min-width: 160px;
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 4px;
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text, #333);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.ctx-item:hover {
  background: var(--accent-hover, #f0f0f0);
}

.ctx-item svg {
  flex-shrink: 0;
  opacity: 0.7;
}

.ctx-item-danger {
  color: #991b1b;
}

.ctx-item-danger:hover {
  background: #fee2e2;
}

.ctx-divider {
  height: 1px;
  background: var(--border, #e0e0e0);
  margin: 4px 0;
}

/* ---------- 分支下拉 ---------- */
.git-branch-dropdown {
  position: absolute;
  top: 36px;
  left: 8px;
  min-width: 220px;
  max-width: 320px;
  max-height: 360px;
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 100;
  display: flex;
  flex-direction: column;
}

.branch-dropdown-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border, #e0e0e0);
}

.branch-dropdown-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.branch-create-btn {
  padding: 3px 10px;
  font-size: 12px;
  color: #2d7a4f;
  background: transparent;
  border: 1px solid #b8dfc8;
  border-radius: 4px;
  cursor: pointer;
}

.branch-create-btn:hover {
  background: #e8f5ee;
}

.branch-list {
  overflow-y: auto;
  padding: 4px;
}

.branch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text, #333);
}

.branch-item:hover {
  background: var(--accent-hover, #f0f0f0);
}

.branch-item.active {
  color: #2d7a4f;
  background: #e8f5ee;
}

.branch-item.remote {
  color: var(--text-secondary, #666);
}

.branch-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.branch-check-icon,
.branch-local-icon,
.branch-remote-icon {
  flex-shrink: 0;
}

/* ---------- 弹窗 ---------- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
}

.modal-dialog {
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  min-width: 280px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #e0e0e0);
}

.modal-body {
  padding: 16px;
}

.modal-body .form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}

.modal-footer {
  padding: 12px 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border, #e0e0e0);
}

.modal-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.modal-btn-cancel {
  background: var(--accent-hover, #f0f0f0);
  color: var(--text, #333);
}

.modal-btn-primary {
  background: #2d7a4f;
  color: #fff;
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
