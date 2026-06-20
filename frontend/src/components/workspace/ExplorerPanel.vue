<template>
  <div class="explorer-panel">
    <!-- 左侧编辑器 -->
    <div class="explorer-main">
      <div class="explorer-toolbar">
        <!-- 分级面包屑 -->
        <div class="explorer-breadcrumb">
          <template v-if="breadcrumbSegments.length">
            <template v-for="(seg, idx) in breadcrumbSegments" :key="idx">
              <span class="bc-segment" :class="{ 'bc-active': idx === breadcrumbSegments.length - 1 }">{{ seg }}</span>
              <svg
                v-if="idx < breadcrumbSegments.length - 1"
                class="bc-sep"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </template>
          </template>
          <span v-else class="bc-empty">未选择文件</span>
        </div>
        <div class="explorer-toolbar-actions">
          <button
            type="button"
            class="tb-action"
            title="使用 VSCode 打开项目"
            @click="openInVSCode"
            :disabled="!workDir"
          >
            <svg t="1781955708153" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="2536" width="14" height="14"><path d="M0 0m184.32 0l655.36 0q184.32 0 184.32 184.32l0 655.36q0 184.32-184.32 184.32l-655.36 0q-184.32 0-184.32-184.32l0-655.36q0-184.32 184.32-184.32Z" fill="#FFFFFF" p-id="2537"></path><path d="M708.82304 161.9968l137.46176 67.24608c20.81792 10.62912 23.7056 18.28864 23.7056 29.29664l0.60416 506.23488c0 13.50656-7.30112 18.82112-27.42272 30.1568l-133.8368 67.08224c-5.5808 2.60096-10.04544 5.76512-43.47904 5.76512 0 0 28.93824 0.24576 28.93824-22.87616v-662.87616a25.15968 25.15968 0 0 0-24.13568-25.76384c29.6448 0 38.16448 5.7344 38.16448 5.7344z" fill="#4B9AE9" p-id="2538"></path><path d="M163.34848 613.02784a29.21472 29.21472 0 0 0 0 38.98368s35.11296 32.62464 45.4656 41.984 25.7024 5.12 35.64544-2.37568 450.29376-343.64416 450.29376-343.64416v-165.94944a25.06752 25.06752 0 0 0-24.13568-25.76384 18.11456 18.11456 0 0 0-12.3392 5.376z" fill="#2A63A4" p-id="2539"></path><path d="M208.92672 331.74528a23.17312 23.17312 0 0 1 32.45056 0l453.4272 343.61344v169.55392c0 23.25504-28.9792 22.8352-28.9792 22.8352a17.00864 17.00864 0 0 1-10.11712-5.53984l-495.77984-454.13376a22.31296 22.31296 0 0 1 0-31.54944z" fill="#3478C6" p-id="2540"></path></svg>
            <span>打开</span>
          </button>
          <button
            type="button"
            class="tb-action tb-icon"
            :title="sidebarCollapsed ? '展开文件树' : '收起文件树'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <svg v-if="sidebarCollapsed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
        </div>
      </div>
      <div class="explorer-editor-wrap">
        <!-- 文本文件：Monaco 编辑器 -->
        <div v-show="previewType === 'text'" class="explorer-editor" ref="editorContainerRef"></div>
        <!-- 图片预览 -->
        <div v-if="previewType === 'image'" class="explorer-image-preview">
          <img :src="previewImageSrc" :alt="selectedPath || ''" class="preview-img" />
        </div>
        <!-- 二进制文件提示 -->
        <div v-else-if="previewType === 'binary'" class="explorer-binary-info">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <p class="binary-title">二进制文件</p>
          <p class="binary-detail" v-if="previewBinaryInfo">
            类型: {{ previewBinaryInfo.ext || '未知' }} · 大小: {{ formatFileSize(previewBinaryInfo.size) }}
          </p>
          <p class="binary-hint">无法在文本编辑器中预览</p>
        </div>
        <!-- 浮动添加到对话按钮 -->
        <div v-if="showAddBtn" class="add-to-chat-float" :style="addBtnStyle">
          <button class="add-to-chat-btn" @click="addSelectionToChat">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            <span>添加到对话</span>
          </button>
        </div>
      </div>
      <div v-if="loading" class="explorer-loading">加载中...</div>
      <div v-else-if="!selectedPath" class="explorer-empty">从右侧选择文件查看内容</div>
    </div>

    <!-- 右侧文件树 -->
    <div v-show="!sidebarCollapsed" class="explorer-sidebar" :style="{ width: sidebarWidth + 'px' }">
      <div class="explorer-search">
        <input
          v-model="searchQuery"
          class="explorer-search-input"
          placeholder="筛选文件..."
          type="text"
        />
      </div>
      <div class="explorer-tree">
        <ExplorerTreeNode
          v-for="node in filteredRoots"
          :key="node.path"
          :node="node"
          :selected-path="selectedPath"
          :tree-data="treeData"
          :loading-folders="loadingFolders"
          @select="onSelectFile"
          @toggle="onToggleFolder"
          @contextmenu="onTreeContextMenu"
        />
      </div>
      <div class="explorer-resize-handle" @mousedown="startResizeSidebar"></div>
    </div>

    <!-- 右键上下文菜单 -->
    <Teleport to="body">
      <div
        v-if="contextMenu.open"
        class="ctx-menu"
        :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
        @mousedown.self="contextMenu.open = false"
      >
        <button class="ctx-item" @click="ctxAddToChat">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          <span>添加到对话</span>
        </button>
        <button class="ctx-item" @click="ctxStartRename">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
          <span>重命名</span>
        </button>
        <div class="ctx-divider"></div>
        <button class="ctx-item ctx-danger" @click="ctxStartDelete">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          <span>删除</span>
        </button>
      </div>
    </Teleport>

    <!-- 重命名弹窗 -->
    <Teleport to="body">
      <div v-if="renameModal.open" class="modal-overlay" @mousedown.self="renameModal.open = false">
        <div class="modal-dialog">
          <div class="modal-header">重命名</div>
          <input
            ref="renameInputRef"
            v-model="renameModal.newName"
            class="modal-input"
            @keydown.enter="confirmRename"
            @keydown.escape="renameModal.open = false"
          />
          <div class="modal-footer">
            <button class="modal-btn modal-btn-cancel" @click="renameModal.open = false">取消</button>
            <button class="modal-btn modal-btn-confirm" @click="confirmRename" :disabled="renameLoading">
              {{ renameLoading ? '处理中…' : '确认' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div v-if="deleteModal.open" class="modal-overlay" @mousedown.self="deleteModal.open = false">
        <div class="modal-dialog">
          <div class="modal-header">确认删除</div>
          <p class="modal-body-text">
            确定要删除「{{ deleteModal.name }}」吗？{{ deleteModal.isDir ? '该目录下的所有内容将被一并删除。' : '此操作不可撤销。' }}
          </p>
          <div class="modal-footer">
            <button class="modal-btn modal-btn-cancel" @click="deleteModal.open = false">取消</button>
            <button class="modal-btn modal-btn-danger" @click="confirmDelete" :disabled="deleteLoading">
              {{ deleteLoading ? '删除中…' : '删除' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useModelStore } from '@/stores/model'
import { storeToRefs } from 'pinia'
import ExplorerTreeNode from './ExplorerTreeNode.vue'

const props = defineProps<{
  visible?: boolean
}>()

const workspace = useWorkspaceStore()
const { workDir } = storeToRefs(workspace)
const modelStore = useModelStore()

const loading = ref(false)
const editorContainerRef = ref<HTMLElement | null>(null)
const selectedPath = ref<string | null>(null)
const searchQuery = ref('')
const sidebarWidth = ref(220)
const treeData = ref<Record<string, TreeNode>>({})
const showAddBtn = ref(false)
const addBtnStyle = ref({ top: '0px', left: '0px' })

// 非文本文件预览状态
const previewType = ref<'text' | 'image' | 'binary'>('text')
const previewImageSrc = ref<string>('')
const previewBinaryInfo = ref<{ ext: string; size: number } | null>(null)

// 右键菜单
const contextMenu = ref({ open: false, x: 0, y: 0, node: null as TreeNode | null })

// 重命名弹窗
const renameInputRef = ref<HTMLInputElement | null>(null)
const renameModal = ref({ open: false, path: '', newName: '' })
const renameLoading = ref(false)

// 删除确认弹窗
const deleteModal = ref({ open: false, path: '', name: '', isDir: false })
const deleteLoading = ref(false)

// 正在加载子目录的文件夹路径集合（用于显示加载中状态）
const loadingFolders = ref<Set<string>>(new Set())

let editor: any = null
let monacoPromise: Promise<any> | null = null
let currentModel: any = null
let selectionListener: any = null

interface TreeNode {
  name: string
  path: string
  isDir: boolean
  expanded?: boolean
  childrenLoaded?: boolean
}

async function loadMonaco() {
  if (monacoPromise) return monacoPromise
  monacoPromise = import('monaco-editor')
  return monacoPromise
}

async function loadRoot() {
  if (!workDir.value) return
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/list?work_dir=${encodeURIComponent(workDir.value)}`)
    if (!res.ok) return
    const data = await res.json()
    for (const e of data.entries || []) {
      treeData.value[e.path] = {
        name: e.name,
        path: e.path,
        isDir: e.is_dir,
        expanded: false,
        childrenLoaded: false,
      }
    }
  } catch (e) {
    console.error('加载文件列表失败', e)
  }
}

async function loadChildren(node: TreeNode) {
  if (!workDir.value || !node.isDir || node.childrenLoaded) return
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/list?work_dir=${encodeURIComponent(workDir.value)}&path=${encodeURIComponent(node.path)}`)
    if (!res.ok) return
    const data = await res.json()
    for (const e of data.entries || []) {
      if (!treeData.value[e.path]) {
        treeData.value[e.path] = {
          name: e.name,
          path: e.path,
          isDir: e.is_dir,
          expanded: false,
          childrenLoaded: false,
        }
      }
    }
    // 通过替换对象来标记子目录已加载（触发 Vue 响应式更新）
    treeData.value[node.path] = { ...node, childrenLoaded: true }
  } catch (e) {
    console.error('加载子目录失败', e)
  }
}

function buildTree(): TreeNode[] {
  const nodes = Object.values(treeData.value)
  const roots: TreeNode[] = []

  for (const n of nodes) {
    const parentPath = n.path.includes('/') ? n.path.substring(0, n.path.lastIndexOf('/')) : ''
    if (!parentPath || !treeData.value[parentPath]) {
      roots.push(n)
    }
  }

  return roots.sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

const filteredRoots = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return buildTree()

  const matched = new Set<string>()
  for (const n of Object.values(treeData.value)) {
    if (n.name.toLowerCase().includes(q)) {
      matched.add(n.path)
      let p = n.path
      while (p.includes('/')) {
        p = p.substring(0, p.lastIndexOf('/'))
        if (treeData.value[p]) matched.add(p)
      }
    }
  }

  return buildTree().filter(r => matched.has(r.path))
})

const breadcrumb = computed(() => {
  if (!selectedPath.value) return '未选择文件'
  return selectedPath.value
})

// 分级面包屑：[工作目录最后一段, ...路径分段]
const breadcrumbSegments = computed<string[]>(() => {
  const segs: string[] = []
  if (workDir.value) {
    const wdName = workDir.value.replace(/[\\/]+$/, '').split(/[\\/]/).filter(Boolean).pop()
    if (wdName) segs.push(wdName)
  }
  if (selectedPath.value) {
    const parts = selectedPath.value.split('/').filter(Boolean)
    segs.push(...parts)
  }
  return segs
})

// 文件树侧栏折叠状态
const sidebarCollapsed = ref(false)

async function openInVSCode() {
  if (!workDir.value) return
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/open-in-editor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, editor: 'vscode' }),
    })
    const data = await res.json()
    if (data.error) {
      window.dispatchEvent(new CustomEvent('aries:toast', {
        detail: { message: data.error, type: 'error' },
      }))
    }
  } catch (e: any) {
    console.error('打开 VSCode 失败', e)
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: e.message || '打开 VSCode 失败', type: 'error' },
    }))
  }
}

async function onSelectFile(path: string) {
  selectedPath.value = path
  await loadFileContent()
}

async function onToggleFolder(node: TreeNode) {
  if (!node.isDir) return
  // 如果正在加载，忽略重复点击
  if (loadingFolders.value.has(node.path)) return

  const newExpanded = !node.expanded
  // 通过替换对象来触发 Vue 响应式更新（直接修改属性不会触发更新）
  treeData.value[node.path] = { ...node, expanded: newExpanded }

  if (newExpanded && !node.childrenLoaded) {
    loadingFolders.value.add(node.path)
    try {
      await loadChildren(treeData.value[node.path])
    } finally {
      loadingFolders.value.delete(node.path)
    }
  }
}

async function loadFileContent() {
  if (!selectedPath.value || !workDir.value || !editorContainerRef.value) return
  loading.value = true
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/read?work_dir=${encodeURIComponent(workDir.value)}&path=${encodeURIComponent(selectedPath.value)}`)
    if (!res.ok) return
    const data = await res.json()

    // 图片文件：显示 <img> 预览
    if (data.is_image) {
      previewType.value = 'image'
      previewImageSrc.value = `data:${data.mime};base64,${data.content}`
      previewBinaryInfo.value = null
      // 隐藏 Monaco 编辑器内容
      if (currentModel) {
        currentModel.dispose()
        currentModel = null
      }
      loading.value = false
      return
    }

    // 其他二进制文件：显示提示信息
    if (data.is_binary) {
      previewType.value = 'binary'
      previewBinaryInfo.value = { ext: data.file_type || '', size: data.size || 0 }
      previewImageSrc.value = ''
      if (currentModel) {
        currentModel.dispose()
        currentModel = null
      }
      loading.value = false
      return
    }

    // 文本文件：用 Monaco 编辑器渲染
    previewType.value = 'text'
    previewImageSrc.value = ''
    previewBinaryInfo.value = null

    const monaco = await loadMonaco()
    if (!monaco) return

    if (currentModel) {
      currentModel.dispose()
      currentModel = null
    }

    if (!editor) {
      editor = monaco.editor.create(editorContainerRef.value, {
        readOnly: true,
        automaticLayout: true,
        fontSize: 13,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        lineNumbers: 'on',
      })

      // 监听选区变化
      selectionListener = editor.onDidChangeCursorSelection((e: any) => {
        updateAddButton(e.selection)
      })
    }

    const language = getLanguageFromPath(selectedPath.value)
    currentModel = monaco.editor.createModel(data.content || '', language)
    editor.setModel(currentModel)
  } catch (e) {
    console.error('加载文件内容失败', e)
  } finally {
    loading.value = false
  }
}

function updateAddButton(selection: any) {
  if (!editor || !selectedPath.value || !workDir.value || previewType.value !== 'text') {
    showAddBtn.value = false
    return
  }
  const startLine = selection.startLineNumber
  const endLine = selection.endLineNumber
  if (startLine === endLine && selection.startColumn === selection.endColumn) {
    showAddBtn.value = false
    return
  }
  // 计算按钮位置：在选区结束位置上方显示
  const endPos = editor.getScrolledVisiblePosition({ lineNumber: endLine, column: selection.endColumn })
  if (endPos) {
    addBtnStyle.value = {
      top: `${Math.max(endPos.top - 36, 4)}px`,
      left: `${Math.min(endPos.left + 20, 200)}px`,
    }
    showAddBtn.value = true
  }
}

function addSelectionToChat() {
  if (!editor || !selectedPath.value || !workDir.value) return
  const selection = editor.getSelection()
  if (!selection) return
  const startLine = selection.startLineNumber
  const endLine = selection.endLineNumber
  const fullPath = `${workDir.value}\\${selectedPath.value.replace(/\//g, '\\')}#L${startLine}-${endLine}`
  window.dispatchEvent(new CustomEvent('aries:add-to-chat', { detail: `##${fullPath}##` }))
  showAddBtn.value = false
}

function getLanguageFromPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
    vue: 'html', html: 'html', css: 'css', scss: 'scss',
    json: 'json', md: 'markdown', py: 'python',
    go: 'go', rs: 'rust', java: 'java', c: 'c', cpp: 'cpp',
    sh: 'shell', yml: 'yaml', yaml: 'yaml', xml: 'xml',
  }
  return map[ext] || 'plaintext'
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function disposeEditor() {
  if (selectionListener) {
    selectionListener.dispose()
    selectionListener = null
  }
  if (currentModel) {
    currentModel.dispose()
    currentModel = null
  }
  if (editor) {
    editor.dispose()
    editor = null
  }
}

let resizing = false
let startX = 0
let startWidth = 0

function startResizeSidebar(e: MouseEvent) {
  resizing = true
  startX = e.clientX
  startWidth = sidebarWidth.value
  document.addEventListener('mousemove', onResizeSidebar)
  document.addEventListener('mouseup', stopResizeSidebar)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onResizeSidebar(e: MouseEvent) {
  if (!resizing) return
  const delta = startX - e.clientX // 向左拖动增大宽度（因为sidebar在右边）
  sidebarWidth.value = Math.min(Math.max(startWidth + delta, 160), 400)
}

function stopResizeSidebar() {
  resizing = false
  document.removeEventListener('mousemove', onResizeSidebar)
  document.removeEventListener('mouseup', stopResizeSidebar)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

watch(workDir, () => {
  treeData.value = {}
  selectedPath.value = null
  showAddBtn.value = false
  if (props.visible) loadRoot()
})

watch(() => props.visible, (val) => {
  if (val && Object.keys(treeData.value).length === 0) loadRoot()
})

onMounted(() => {
  if (props.visible) loadRoot()
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', closeContextMenu)
})

onUnmounted(() => {
  disposeEditor()
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', closeContextMenu)
})

function closeContextMenu() {
  contextMenu.value.open = false
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
    if (showAddBtn.value) {
      e.preventDefault()
      addSelectionToChat()
    }
  }
}

// ---------- 右键菜单 ----------

function onTreeContextMenu(payload: { node: TreeNode; event: MouseEvent }) {
  contextMenu.value = {
    open: true,
    x: payload.event.clientX,
    y: payload.event.clientY,
    node: payload.node,
  }
}

function ctxAddToChat() {
  const node = contextMenu.value.node
  contextMenu.value.open = false
  if (!node || !workDir.value) return
  let fullPath: string
  if (node.isDir) {
    // 文件夹：路径以 \ 结尾，无行号
    fullPath = `${workDir.value}\\${node.path.replace(/\//g, '\\')}\\`
  } else {
    // 文件：完整路径（无行号，右键菜单无法选中行范围）
    fullPath = `${workDir.value}\\${node.path.replace(/\//g, '\\')}`
  }
  window.dispatchEvent(new CustomEvent('aries:add-to-chat', { detail: `##${fullPath}##` }))
}

async function ctxStartRename() {
  const node = contextMenu.value.node
  contextMenu.value.open = false
  if (!node) return
  renameModal.value = { open: true, path: node.path, newName: node.name }
  await nextTick()
  renameInputRef.value?.focus()
  renameInputRef.value?.select()
}

function ctxStartDelete() {
  const node = contextMenu.value.node
  contextMenu.value.open = false
  if (!node) return
  deleteModal.value = { open: true, path: node.path, name: node.name, isDir: node.isDir }
}

async function confirmRename() {
  if (renameLoading.value) return
  const { path, newName } = renameModal.value
  if (!path || !newName.trim()) return
  renameLoading.value = true
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/rename`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, path, new_name: newName.trim() }),
    })
    const data = await res.json()
    if (data.error) {
      console.error('重命名失败:', data.error)
      return
    }
    renameModal.value.open = false
    await refreshTree()
    // 如果重命名的是当前选中的文件，更新选中路径
    if (selectedPath.value === path && data.new_path) {
      selectedPath.value = data.new_path
      await loadFileContent()
    }
  } catch (e) {
    console.error('重命名失败', e)
  } finally {
    renameLoading.value = false
  }
}

async function confirmDelete() {
  if (deleteLoading.value) return
  const { path } = deleteModal.value
  if (!path) return
  deleteLoading.value = true
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/delete`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, path }),
    })
    const data = await res.json()
    if (data.error) {
      console.error('删除失败:', data.error)
      return
    }
    deleteModal.value.open = false
    // 如果删除的是当前选中的文件，清空预览
    if (selectedPath.value === path) {
      selectedPath.value = null
      previewType.value = 'text'
      if (currentModel) {
        currentModel.dispose()
        currentModel = null
      }
    }
    await refreshTree()
  } catch (e) {
    console.error('删除失败', e)
  } finally {
    deleteLoading.value = false
  }
}

async function refreshTree() {
  // 保留已展开的目录状态，重新加载
  const expandedPaths = new Set<string>()
  for (const node of Object.values(treeData.value)) {
    if (node.expanded) expandedPaths.add(node.path)
  }
  treeData.value = {}
  await loadRoot()
  // 恢复展开状态并重新加载子目录
  for (const path of expandedPaths) {
    const node = treeData.value[path]
    if (node && node.isDir) {
      // 通过替换对象来触发 Vue 响应式更新
      treeData.value[path] = { ...node, expanded: true }
      await loadChildren(treeData.value[path])
    }
  }
}
</script>

<style scoped>
.explorer-panel {
  display: flex;
  flex: 1;
  min-height: 0;
  background: #fff;
  overflow: hidden;
}

.explorer-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  position: relative;
}

.explorer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px 4px 10px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.explorer-breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.bc-segment {
  padding: 1px 4px;
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
  max-width: 160px;
}

.bc-segment.bc-active {
  color: var(--text);
  font-weight: 500;
}

.bc-sep {
  flex-shrink: 0;
  opacity: 0.5;
}

.bc-empty {
  color: var(--text-muted);
}

.explorer-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.tb-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #ffffff;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.tb-action:hover:not(:disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.tb-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tb-action.tb-icon {
  padding: 3px 5px;
}

.explorer-editor-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.explorer-editor {
  width: 100%;
  height: 100%;
}

/* 图片预览 */
.explorer-image-preview {
  width: 100%;
  height: 100%;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 16px;
  background: #f7f7f5;
}

.preview-img {
  max-width: 100%;
  height: auto;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.1);
}

/* 二进制文件提示 */
.explorer-binary-info {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted, #999);
}

.explorer-binary-info svg {
  opacity: 0.4;
}

.binary-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary, #666);
  margin: 0;
}

.binary-detail {
  font-size: 12px;
  margin: 0;
}

.binary-hint {
  font-size: 12px;
  margin: 0;
  opacity: 0.7;
}

.add-to-chat-float {
  position: absolute;
  z-index: 50;
  pointer-events: auto;
}

.add-to-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: #fff;
  background: #1a1a1a;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  white-space: nowrap;
}

.add-to-chat-btn:hover {
  opacity: 0.85;
}

.add-to-chat-shortcut {
  font-size: 10px;
  opacity: 0.7;
  margin-left: 2px;
}

.explorer-loading,
.explorer-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-muted);
  font-size: 12px;
  pointer-events: none;
}

.explorer-sidebar {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: #fafafa;
  min-width: 160px;
  max-width: 400px;
  position: relative;
}

.explorer-search {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.explorer-search-input {
  width: 100%;
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
  background: #fff;
  color: var(--text);
  font-family: inherit;
}

.explorer-search-input::placeholder {
  color: var(--text-muted);
}

.explorer-tree {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 2px 0;
}

.explorer-resize-handle {
  position: absolute;
  left: -3px;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 10;
}

.explorer-resize-handle:hover {
  background: rgba(0, 120, 212, 0.2);
}

/* ---------- 右键上下文菜单 ---------- */
.ctx-menu {
  position: fixed;
  z-index: 10000;
  min-width: 140px;
  background: #fff;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  padding: 4px;
  font-size: 13px;
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: none;
  color: var(--text, #333);
  cursor: pointer;
  border-radius: 4px;
  text-align: left;
  transition: background 0.1s;
}

.ctx-item:hover {
  background: var(--accent-hover, #f0f0f0);
}

.ctx-item svg {
  opacity: 0.6;
  flex-shrink: 0;
}

.ctx-danger {
  color: #dc2626;
}

.ctx-danger:hover {
  background: #fef2f2;
}

.ctx-divider {
  height: 1px;
  background: var(--border, #eee);
  margin: 4px 0;
}

/* ---------- 弹窗 ---------- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
}

.modal-dialog {
  width: 380px;
  max-width: 92vw;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.modal-header {
  padding: 14px 18px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #eee);
}

.modal-body-text {
  padding: 16px 18px;
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #666);
  line-height: 1.6;
}

.modal-input {
  width: 100%;
  margin: 14px 18px;
  width: calc(100% - 36px);
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  outline: none;
  font-family: inherit;
}

.modal-input:focus {
  border-color: var(--accent, #4f7cff);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border, #eee);
}

.modal-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-btn-cancel {
  background: #f0f0f0;
  color: #333;
}

.modal-btn-cancel:hover:not(:disabled) {
  background: #e5e5e5;
}

.modal-btn-confirm {
  background: var(--accent, #4f7cff);
  color: #fff;
}

.modal-btn-confirm:hover:not(:disabled) {
  background: var(--accent-hover, #3a66e0);
}

.modal-btn-danger {
  background: #dc2626;
  color: #fff;
}

.modal-btn-danger:hover:not(:disabled) {
  background: #b91c1c;
}
</style>
