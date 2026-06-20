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

    <!-- 文本：Monaco diff -->
    <div v-show="previewType === 'text'" class="diff-body" ref="diffContainerRef"></div>

    <!-- 图片：只展示修改后版本 -->
    <div v-if="previewType === 'image'" class="diff-image-compare">
      <div class="diff-image-side">
        <div class="diff-image-frame">
          <img v-if="imageModifiedSrc" :src="imageModifiedSrc" :alt="selectedPath || ''" class="diff-image" />
          <div v-else class="diff-image-empty">（已删除）</div>
        </div>
      </div>
    </div>

    <!-- 二进制：提示 -->
    <div v-else-if="previewType === 'binary'" class="diff-binary-info">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <p class="binary-title">二进制文件</p>
      <p class="binary-detail" v-if="binaryInfo">
        类型: {{ binaryInfo.ext || '未知' }} · 大小: {{ formatFileSize(binaryInfo.size) }}
      </p>
      <p class="binary-hint">无法在文本编辑器中预览差异</p>
    </div>

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

// 预览类型：text → Monaco diff；image → 单图（修改后）；binary → 提示
const previewType = ref<'text' | 'image' | 'binary'>('text')
const imageModifiedSrc = ref<string>('')
const binaryInfo = ref<{ ext: string; size: number } | null>(null)

let editor: any = null
let monacoPromise: Promise<any> | null = null
let currentOriginalModel: any = null
let currentModifiedModel: any = null

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico'])
const BINARY_EXTS = new Set([
  'pdf', 'zip', 'tar', 'gz', 'rar', '7z',
  'exe', 'dll', 'so', 'dylib', 'class', 'pyc',
  'mp3', 'mp4', 'wav', 'flac', 'ogg', 'mov', 'avi', 'mkv',
  'ttf', 'otf', 'woff', 'woff2',
  'db', 'sqlite',
])

function getExt(path: string): string {
  const i = path.lastIndexOf('.')
  return i >= 0 ? path.slice(i + 1).toLowerCase() : ''
}

async function loadMonaco() {
  if (monacoPromise) return monacoPromise
  monacoPromise = import('monaco-editor')
  return monacoPromise
}

function disposeModels() {
  if (currentOriginalModel) {
    currentOriginalModel.dispose()
    currentOriginalModel = null
  }
  if (currentModifiedModel) {
    currentModifiedModel.dispose()
    currentModifiedModel = null
  }
}

async function fetchShowFile(ref: string): Promise<any | null> {
  if (!selectedPath.value || !workDir.value) return null
  const url =
    `${modelStore.getBaseUrl()}/git/show-file?work_dir=${encodeURIComponent(workDir.value)}` +
    `&ref=${encodeURIComponent(ref)}` +
    `&file_path=${encodeURIComponent(selectedPath.value)}`
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function loadDiff() {
  if (!selectedPath.value || !workDir.value) return
  loading.value = true
  imageModifiedSrc.value = ''
  binaryInfo.value = null
  try {
    const ext = getExt(selectedPath.value)
    const isImage = IMAGE_EXTS.has(ext)
    const isBinary = BINARY_EXTS.has(ext) || isImage

    if (isImage || isBinary) {
      const modifiedRef = props.commitHash ? props.commitHash : 'WORKTREE'
      const modData = await fetchShowFile(modifiedRef)

      if (isImage) {
        previewType.value = 'image'
        if (modData?.exists && modData.is_image) {
          imageModifiedSrc.value = `data:${modData.mime};base64,${modData.content}`
        }
        // 释放 monaco 模型，避免占内存
        disposeModels()
        return
      }

      // 其他二进制：拿当前版本元信息即可
      previewType.value = 'binary'
      binaryInfo.value = modData?.exists
        ? { ext: modData.ext || ext, size: modData.size || 0 }
        : { ext, size: 0 }
      disposeModels()
      return
    }

    // 文本：走原 Monaco diff 流程
    previewType.value = 'text'
    if (!diffContainerRef.value) return
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

    disposeModels()

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

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function disposeEditor() {
  disposeModels()
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

.diff-image-compare {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
  padding: 12px;
  overflow: auto;
  background: #f7f7f5;
}

.diff-image-side {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.diff-image-frame {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  min-height: 200px;
}

.diff-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}

.diff-image-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.diff-binary-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  padding: 24px;
}

.diff-binary-info .binary-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.diff-binary-info .binary-detail {
  margin: 0;
  font-size: 12px;
}

.diff-binary-info .binary-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
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
