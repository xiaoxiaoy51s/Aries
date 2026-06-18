<template>
  <div class="diff-panel">
    <div class="diff-toolbar">
      <span class="diff-file-name" :title="selectedPath || ''">{{ selectedPath || '未选择文件' }}</span>
      <button type="button" class="diff-btn" title="刷新" @click="loadDiff" :disabled="!selectedPath">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/>
        </svg>
      </button>
    </div>
    <div class="diff-body" ref="diffContainerRef"></div>
    <div v-if="loading" class="diff-loading">加载中...</div>
    <div v-else-if="!selectedPath" class="diff-empty">从 Git 面板选择文件查看差异</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useModelStore } from '@/stores/model'
import { storeToRefs } from 'pinia'

const props = defineProps<{
  visible?: boolean
  filePath?: string | null
  commitHash?: string | null
}>()

const workspace = useWorkspaceStore()
const { workDir } = storeToRefs(workspace)
const modelStore = useModelStore()

const loading = ref(false)
const diffContainerRef = ref<HTMLElement | null>(null)
const selectedPath = ref<string | null>(props.filePath || null)
let editor: any = null
let monacoLoaded = false
let monacoPromise: Promise<any> | null = null
let currentOriginalModel: any = null
let currentModifiedModel: any = null

async function loadMonaco() {
  if (monacoPromise) return monacoPromise
  monacoPromise = import('monaco-editor')
  const monaco = await monacoPromise
  monacoLoaded = true
  return monaco
}

async function loadDiff() {
  if (!selectedPath.value || !workDir.value || !diffContainerRef.value) return
  loading.value = true
  try {
    const monaco = await loadMonaco()
    if (!monaco) return

    let url: string
    if (props.commitHash) {
      url = `${modelStore.getBaseUrl()}/git/commit-diff?work_dir=${encodeURIComponent(workDir.value)}&hash=${encodeURIComponent(props.commitHash)}&file_path=${encodeURIComponent(selectedPath.value)}`
    } else {
      url = `${modelStore.getBaseUrl()}/git/diff?work_dir=${encodeURIComponent(workDir.value)}&file_path=${encodeURIComponent(selectedPath.value)}`
    }
    const res = await fetch(url)
    if (!res.ok) return
    const data = await res.json()

    // 释放旧的 model
    if (currentOriginalModel) {
      currentOriginalModel.dispose()
      currentOriginalModel = null
    }
    if (currentModifiedModel) {
      currentModifiedModel.dispose()
      currentModifiedModel = null
    }

    // 复用 editor，只切换 model
    if (!editor) {
      editor = monaco.editor.createDiffEditor(diffContainerRef.value, {
        readOnly: true,
        renderSideBySide: true,
        automaticLayout: true,
        fontSize: 13,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
      })
    }

    const language = getLanguageFromPath(selectedPath.value)
    currentOriginalModel = monaco.editor.createModel(data.original || '', language)
    currentModifiedModel = monaco.editor.createModel(data.modified || '', language)

    editor.setModel({
      original: currentOriginalModel,
      modified: currentModifiedModel,
    })
  } catch (e) {
    console.error('加载 diff 失败', e)
  } finally {
    loading.value = false
  }
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
  if (currentOriginalModel) {
    currentOriginalModel.dispose()
    currentOriginalModel = null
  }
  if (currentModifiedModel) {
    currentModifiedModel.dispose()
    currentModifiedModel = null
  }
  if (editor) {
    editor.dispose()
    editor = null
  }
}

watch(() => props.filePath, (val) => {
  if (val) {
    selectedPath.value = val
    if (props.visible) nextTick(() => loadDiff())
  }
})

watch(() => props.commitHash, () => {
  if (props.visible && selectedPath.value) nextTick(() => loadDiff())
})

watch(() => props.visible, (val) => {
  if (val && selectedPath.value) nextTick(() => loadDiff())
})

watch(workDir, () => {
  if (props.visible && selectedPath.value) loadDiff()
})

onMounted(() => {
  if (props.visible && props.filePath) {
    selectedPath.value = props.filePath
    nextTick(() => loadDiff())
  }
})

onUnmounted(() => {
  disposeEditor()
})
</script>

<style scoped>
.diff-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #fff;
  position: relative;
}

.diff-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.diff-file-name {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 6px;
}

.diff-btn {
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
}

.diff-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.diff-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.diff-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.diff-loading,
.diff-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-muted);
  font-size: 12px;
  pointer-events: none;
}
</style>
