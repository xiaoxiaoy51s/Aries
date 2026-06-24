<template>
  <div class="diff-panel">
    <div class="diff-toolbar">
      <span class="diff-file-name" :title="selectedPath || ''">{{ selectedPath || '未选择文件' }}</span>
      <div class="diff-toolbar-actions">
        <button
          type="button"
          class="tb-action"
          title="使用 VSCode 打开文件"
          @click="openFileInVSCode"
          :disabled="!canOpenExternally"
        >
          <svg t="1781955708153" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="2536" width="14" height="14"><path d="M0 0m184.32 0l655.36 0q184.32 0 184.32 184.32l0 655.36q0 184.32-184.32 184.32l-655.36 0q-184.32 0-184.32-184.32l0-655.36q0-184.32 184.32-184.32Z" fill="#FFFFFF" p-id="2537"></path><path d="M708.82304 161.9968l137.46176 67.24608c20.81792 10.62912 23.7056 18.28864 23.7056 29.29664l0.60416 506.23488c0 13.50656-7.30112 18.82112-27.42272 30.1568l-133.8368 67.08224c-5.5808 2.60096-10.04544 5.76512-43.47904 5.76512 0 0 28.93824 0.24576 28.93824-22.87616v-662.87616a25.15968 25.15968 0 0 0-24.13568-25.76384c29.6448 0 38.16448 5.7344 38.16448 5.7344z" fill="#4B9AE9" p-id="2538"></path><path d="M163.34848 613.02784a29.21472 29.21472 0 0 0 0 38.98368s35.11296 32.62464 45.4656 41.984 25.7024 5.12 35.64544-2.37568 450.29376-343.64416 450.29376-343.64416v-165.94944a25.06752 25.06752 0 0 0-24.13568-25.76384 18.11456 18.11456 0 0 0-12.3392 5.376z" fill="#2A63A4" p-id="2539"></path><path d="M208.92672 331.74528a23.17312 23.17312 0 0 1 32.45056 0l453.4272 343.61344v169.55392c0 23.25504-28.9792 22.8352-28.9792 22.8352a17.00864 17.00864 0 0 1-10.11712-5.53984l-495.77984-454.13376a22.31296 22.31296 0 0 1 0-31.54944z" fill="#3478C6" p-id="2540"></path></svg>
          <span>打开</span>
        </button>
        <button type="button" class="diff-btn" title="刷新" @click="loadDiff" :disabled="!selectedPath">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/>
          </svg>
        </button>
      </div>
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
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useModelStore } from '@/stores/model'
import { storeToRefs } from 'pinia'

const props = defineProps<{
  visible?: boolean
  filePath?: string | null
  commitHash?: string | null
  inlineOriginal?: string
  inlineModified?: string
  inlinePath?: string
  inlineKey?: number
}>()

const workspace = useWorkspaceStore()
const { workDir } = storeToRefs(workspace)
const modelStore = useModelStore()

const loading = ref(false)
const diffContainerRef = ref<HTMLElement | null>(null)
const selectedPath = ref<string | null>(props.filePath || null)
const inlineMode = ref(false)

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

/** 将绝对/相对路径转为 API 所需的相对 work_dir 路径 */
function getRelativeFilePath(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  if (!workDir.value) return normalized
  const wd = workDir.value.replace(/\\/g, '/').replace(/\/+$/, '')
  const lowerPath = normalized.toLowerCase()
  const lowerWd = wd.toLowerCase()
  if (lowerPath === lowerWd) return ''
  if (lowerPath.startsWith(lowerWd + '/')) {
    return normalized.slice(wd.length).replace(/^\/+/, '')
  }
  if (!/^[a-zA-Z]:/.test(normalized) && !normalized.startsWith('/')) {
    return normalized
  }
  return normalized
}

const canOpenExternally = computed(() => !!(selectedPath.value && workDir.value))

async function openFileInVSCode() {
  if (!selectedPath.value || !workDir.value) return
  const path = getRelativeFilePath(selectedPath.value)
  try {
    const res = await fetch(`${modelStore.getBaseUrl()}/files/open-in-editor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: workDir.value, path, editor: 'vscode-file' }),
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
  if (!selectedPath.value) return
  // 内联内容模式：直接用传入的 original/modified，不走 git API
  const hasInline = inlineMode.value && (props.inlineOriginal !== undefined || props.inlineModified !== undefined)
  if (hasInline && !workDir.value) {
    // 无 workDir 时只能走内联模式
  } else if (!workDir.value) {
    return
  }
  loading.value = true
  imageModifiedSrc.value = ''
  binaryInfo.value = null
  try {
    const ext = getExt(selectedPath.value)
    const isImage = IMAGE_EXTS.has(ext)
    const isBinary = BINARY_EXTS.has(ext) || isImage

    if (isImage || isBinary) {
      if (hasInline) {
        // 内联模式下无法获取 base64 图片数据，显示为二进制提示
        previewType.value = 'binary'
        binaryInfo.value = { ext, size: props.inlineModified?.length || 0 }
        disposeModels()
        return
      }
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

    // 文本：走 Monaco diff 流程
    previewType.value = 'text'
    if (!diffContainerRef.value) return
    const monaco = await loadMonaco()
    if (!monaco) return

    let originalContent = ''
    let modifiedContent = ''

    if (hasInline) {
      originalContent = props.inlineOriginal || ''
      modifiedContent = props.inlineModified || ''
    } else {
      let url: string
      if (props.commitHash) {
        url = `${modelStore.getBaseUrl()}/git/commit-diff?work_dir=${encodeURIComponent(workDir.value!)}&hash=${encodeURIComponent(props.commitHash)}&file_path=${encodeURIComponent(selectedPath.value)}`
      } else {
        url = `${modelStore.getBaseUrl()}/git/diff?work_dir=${encodeURIComponent(workDir.value!)}&file_path=${encodeURIComponent(selectedPath.value)}`
      }
      const res = await fetch(url)
      if (!res.ok) return
      const data = await res.json()
      originalContent = data.original || ''
      modifiedContent = data.modified || ''
    }

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
    currentOriginalModel = monaco.editor.createModel(originalContent, language)
    currentModifiedModel = monaco.editor.createModel(modifiedContent, language)

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
    inlineMode.value = false
    if (props.visible) nextTick(() => loadDiff())
  }
})

watch(() => props.commitHash, () => {
  if (props.visible && selectedPath.value) nextTick(() => loadDiff())
})

watch(() => props.inlineKey, () => {
  if (props.inlinePath) {
    selectedPath.value = props.inlinePath
    inlineMode.value = true
    if (props.visible) nextTick(() => loadDiff())
  }
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
  gap: 8px;
  padding: 4px 6px 4px 10px;
  background: #f7f7f5;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  min-height: 32px;
}

.diff-toolbar-actions {
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
