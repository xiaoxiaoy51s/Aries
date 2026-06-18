<template>
  <div class="explorer-panel">
    <!-- 左侧编辑器 -->
    <div class="explorer-main">
      <div class="explorer-toolbar">
        <span class="explorer-breadcrumb">{{ breadcrumb }}</span>
      </div>
      <div class="explorer-editor-wrap">
        <div class="explorer-editor" ref="editorContainerRef"></div>
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
    <div class="explorer-sidebar" :style="{ width: sidebarWidth + 'px' }">
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
          @select="onSelectFile"
          @toggle="onToggleFolder"
        />
      </div>
      <div class="explorer-resize-handle" @mousedown="startResizeSidebar"></div>
    </div>
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
    node.childrenLoaded = true
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

async function onSelectFile(path: string) {
  selectedPath.value = path
  await loadFileContent()
}

async function onToggleFolder(node: TreeNode) {
  if (!node.isDir) return
  node.expanded = !node.expanded
  if (node.expanded && !node.childrenLoaded) {
    await loadChildren(node)
  }
}

async function loadFileContent() {
  if (!selectedPath.value || !workDir.value || !editorContainerRef.value) return
  loading.value = true
  try {
    const monaco = await loadMonaco()
    if (!monaco) return

    const res = await fetch(`${modelStore.getBaseUrl()}/files/read?work_dir=${encodeURIComponent(workDir.value)}&path=${encodeURIComponent(selectedPath.value)}`)
    if (!res.ok) return
    const data = await res.json()

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
  if (!editor || !selectedPath.value || !workDir.value) {
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
  window.dispatchEvent(new CustomEvent('mimo:add-to-chat', { detail: fullPath }))
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
})

onUnmounted(() => {
  disposeEditor()
  document.removeEventListener('keydown', onKeydown)
})

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
    if (showAddBtn.value) {
      e.preventDefault()
      addSelectionToChat()
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
  padding: 4px 10px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.explorer-breadcrumb {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
</style>
