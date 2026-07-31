<template>
  <div class="file-viewer-panel">
    <!-- 工具栏 -->
    <div class="file-viewer-toolbar">
      <button type="button" class="file-viewer-back" :title="t('workspace.backToChat')" @click="$emit('back')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <img v-if="fileIconUrl" :src="fileIconUrl" class="file-viewer-toolbar-icon" alt="" />
      <span class="file-viewer-name" :title="file?.name || ''">{{ file?.name || '' }}</span>
      <span class="file-viewer-path" :title="file?.path || ''">{{ file?.path || '' }}</span>
      <button
        v-if="isHtml && !editing"
        type="button"
        class="file-viewer-action"
        :class="{ 'file-viewer-action-primary': htmlPreview }"
        :title="htmlPreview ? t('workspace.viewCode') : t('workspace.previewPage')"
        @click="htmlPreview = !htmlPreview"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        <span>{{ htmlPreview ? t('workspace.viewCode') : t('workspace.previewPage') }}</span>
      </button>
      <button
        v-if="previewType === 'text' && !editing"
        type="button"
        class="file-viewer-action"
        :title="t('workspace.editFile')"
        @click="startEdit"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
        <span>{{ t('workspace.editFile') }}</span>
      </button>
      <template v-if="previewType === 'text' && editing">
        <button
          type="button"
          class="file-viewer-action file-viewer-action-primary"
          :disabled="saving"
          :title="t('workspace.saveFile')"
          @click="saveEdit"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          <span>{{ saving ? t('workspace.saving') : t('workspace.saveFile') }}</span>
        </button>
        <button
          type="button"
          class="file-viewer-action"
          :disabled="saving"
          :title="t('settings.cancel')"
          @click="cancelEdit"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          <span>{{ t('settings.cancel') }}</span>
        </button>
      </template>
      <button
        v-if="file"
        type="button"
        class="file-viewer-download"
        :title="t('workspace.download')"
        @click="downloadFile"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      </button>
    </div>

    <!-- 内容区 -->
    <div class="file-viewer-body" ref="bodyRef">
      <!-- 加载中 -->
      <div v-if="loading" class="file-viewer-center">
        <div class="file-viewer-spinner" />
        <span>{{ t('workspace.loadingFiles') }}</span>
      </div>

      <!-- 文本/代码 -->
      <div v-else-if="previewType === 'text'" class="file-viewer-text" :class="{ 'file-viewer-text-preview': htmlPreview }" @mouseup="!editing && !htmlPreview && onCodeMouseUp()">
        <textarea
          v-if="editing"
          v-model="editingContent"
          class="file-viewer-edit-area"
          spellcheck="false"
          @keydown="onEditKeydown"
        ></textarea>
        <template v-else-if="htmlPreview">
          <iframe
            :src="previewUrl"
            class="file-viewer-html-iframe"
            :title="file?.name || 'HTML'"
          />
          <button type="button" class="file-viewer-share-btn" @click="copyShareLink">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            <span>{{ t('workspace.copyShareLink') }}</span>
          </button>
        </template>
        <template v-else>
          <table class="file-viewer-code-table">
            <tbody>
              <tr v-for="(line, i) in codeLines" :key="i" :data-line="i + 1">
                <td class="file-viewer-line-num">{{ i + 1 }}</td>
                <td class="file-viewer-line-code"><span v-html="line || '&nbsp;'"></span></td>
              </tr>
            </tbody>
          </table>

          <!-- 浮动添加到对话按钮 -->
          <div v-if="showAddBtn" class="file-viewer-add-float" :style="addBtnStyle">
            <button class="file-viewer-add-btn" @click="addSelectionToChat">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
              <span>{{ t('workspace.addToChat') }}</span>
            </button>
          </div>
        </template>
      </div>

      <!-- 图片 -->
      <div v-else-if="previewType === 'image'" class="file-viewer-image-wrap">
        <img v-if="previewSrc" :src="previewSrc" :alt="file?.name || ''" class="file-viewer-image" />
        <div v-else class="file-viewer-center"><span>{{ t('workspace.loadingFiles') }}</span></div>
      </div>

      <!-- PDF -->
      <iframe
        v-else-if="previewType === 'pdf'"
        :src="previewSrc"
        class="file-viewer-pdf"
        :title="file?.name || 'PDF'"
      />

      <!-- Office 文档预览 -->
      <div v-else-if="previewType === 'office'" class="file-viewer-office-frame">
        <div v-if="!officePreviewUrl" class="file-viewer-center">
          <div class="file-viewer-spinner" />
          <span>{{ t('workspace.loadingFiles') }}</span>
        </div>
        <iframe
          v-else
          :src="officePreviewUrl"
          class="file-viewer-office-iframe"
          :title="file?.name || 'Office'"
        />
      </div>

      <!-- 二进制 / 不支持预览 -->
      <div v-else-if="previewType === 'binary'" class="file-viewer-center">
        <img v-if="fileIconUrl" :src="fileIconUrl" class="file-viewer-binary-icon" alt="" />
        <p class="file-viewer-binary-title">{{ t('workspace.binaryFile') }}</p>
        <p class="file-viewer-binary-detail" v-if="file">
          {{ (ext || '').toUpperCase() || '-' }} · {{ formatSize(file.size) }}
        </p>
        <button type="button" class="file-viewer-binary-download" @click="downloadFile">
          {{ t('workspace.download') }}
        </button>
      </div>

      <!-- 空状态 -->
      <div v-else class="file-viewer-center file-viewer-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <p>{{ t('workspace.selectFileHint') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import java from 'highlight.js/lib/languages/java'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import sql from 'highlight.js/lib/languages/sql'
import shell from 'highlight.js/lib/languages/bash'
import ini from 'highlight.js/lib/languages/ini'
import plaintext from 'highlight.js/lib/languages/plaintext'
import 'highlight.js/styles/github.css'
import { useI18n } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { getFileIconUrl } from '../utils/fileIcons'
import { downloadWorkspaceFile, readWorkspaceFile, saveWorkspaceFileContent } from '../api/workspaces'
import api from '../api'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('go', go)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('java', java)
hljs.registerLanguage('c', c)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('shell', shell)
hljs.registerLanguage('bash', shell)
hljs.registerLanguage('ini', ini)
hljs.registerLanguage('plaintext', plaintext)

const { t } = useI18n()
const auth = useAuthStore()

const props = defineProps({
  workspace: { type: String, required: true },
  file: { type: Object, default: null },
})

const emit = defineEmits(['back', 'add-to-chat'])

const loading = ref(false)
const textContent = ref('')
const previewType = ref('empty') // 'text' | 'image' | 'pdf' | 'office' | 'binary' | 'empty'
const bodyRef = ref(null)
const previewSrc = ref('') // base64 data URL for image/pdf
const officePreviewUrl = ref('') // officecli preview URL
const currentOfficeWs = ref('') // 当前 office 预览的工作目录
const currentOfficePath = ref('') // 当前 office 预览的文件路径
// 文本编辑状态
const editing = ref(false)
const editingContent = ref('')
const saving = ref(false)
// HTML 预览状态
const htmlPreview = ref(false)

// 选中行范围 -> 浮动按钮
const showAddBtn = ref(false)
const addBtnStyle = ref({ top: '0px' })

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico', 'avif'])
const PDF_EXTS = new Set(['pdf'])
const OFFICE_EXTS = new Set(['docx', 'xlsx', 'pptx'])
const BINARY_EXTS = new Set([
  'zip', 'tar', 'gz', 'rar', '7z',
  'exe', 'dll', 'so', 'dylib', 'class', 'pyc',
  'mp3', 'mp4', 'wav', 'flac', 'ogg', 'mov', 'avi', 'mkv',
  'ttf', 'otf', 'woff', 'woff2',
  'db', 'sqlite',
  'doc', 'xls', 'ppt',
  'odt', 'ods', 'odp',
])
const HTML_EXTS = new Set(['html', 'htm'])
const TEXT_EXTS = new Set([
  'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'vue',
  'html', 'htm', 'css', 'scss', 'less',
  'json', 'json5', 'jsonc',
  'md', 'markdown', 'txt', 'text',
  'py', 'go', 'rs', 'java', 'c', 'h', 'cpp', 'cxx', 'hpp', 'cc',
  'sh', 'bash', 'zsh',
  'yml', 'yaml', 'xml', 'sql',
  'toml', 'ini', 'cfg', 'conf', 'env',
  'log', 'gitignore', 'dockerfile',
  'csv', 'tsv',
])

const EXT_LANG_MAP = {
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript', jsx: 'javascript',
  vue: 'xml',
  html: 'html', htm: 'html',
  css: 'css', scss: 'css', less: 'css',
  json: 'json', json5: 'json', jsonc: 'json',
  md: 'markdown', markdown: 'markdown',
  py: 'python', go: 'go', rs: 'rust',
  java: 'java', c: 'c', h: 'c', cpp: 'cpp', cxx: 'cpp', hpp: 'cpp', cc: 'cpp',
  sh: 'shell', bash: 'shell', zsh: 'shell',
  yml: 'yaml', yaml: 'yaml',
  xml: 'xml', sql: 'sql',
  toml: 'ini', ini: 'ini', cfg: 'ini', conf: 'ini', env: 'ini',
}

const TEXT_PREVIEW_MAX_SIZE = 1024 * 1024 // 1MB

const ext = computed(() => {
  if (!props.file?.name) return ''
  const i = props.file.name.lastIndexOf('.')
  return i >= 0 ? props.file.name.slice(i + 1).toLowerCase() : ''
})

const isHtml = computed(() => HTML_EXTS.has(ext.value))

const fileIconUrl = computed(() => {
  if (!props.file?.name) return ''
  return getFileIconUrl(props.file.name)
})

const fileUrl = computed(() => {
  if (!props.workspace || !props.file?.path) return ''
  return downloadWorkspaceFile(props.workspace, props.file.path)
})

const previewUrl = computed(() => {
  if (!props.workspace || !props.file?.path) return ''
  const email = encodeURIComponent(auth.user?.email || '')
  if (!email) return ''
  const ws = encodeURIComponent(props.workspace)
  const segs = props.file.path.split('/').map(encodeURIComponent).join('/')
  return `/api/preview/${email}/${ws}/${segs}`
})

const hlLang = computed(() => EXT_LANG_MAP[ext.value] || 'plaintext')

// 按行高亮代码，返回每行的 HTML
const codeLines = computed(() => {
  if (!textContent.value) return []
  const lang = hlLang.value
  // 先整体高亮，再按行拆分（保留行内 span 结构）
  let highlighted
  try {
    highlighted = hljs.highlight(textContent.value, { language: lang }).value
  } catch {
    highlighted = textContent.value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
  // 按换行拆分，注意 hljs 输出可能跨行 span
  // 用一个临时容器解析，再逐行取 innerHTML
  return highlighted.split('\n')
})

function getPreviewType(fileName, size) {
  const e = ext.value
  if (IMAGE_EXTS.has(e)) return 'image'
  if (PDF_EXTS.has(e)) return 'pdf'
  if (OFFICE_EXTS.has(e)) return 'office'
  if (TEXT_EXTS.has(e)) return 'text'
  if (BINARY_EXTS.has(e)) return 'binary'
  if (size && size > 0 && size <= TEXT_PREVIEW_MAX_SIZE) return 'text'
  return 'binary'
}

async function loadFile() {
  // 停止之前的 office 预览
  if (officePreviewUrl.value) {
    await stopOfficePreview()
  }
  showAddBtn.value = false
  previewSrc.value = ''
  officePreviewUrl.value = ''
  editing.value = false
  editingContent.value = ''
  htmlPreview.value = false
  if (!props.file) {
    previewType.value = 'empty'
    return
  }

  const type = getPreviewType(props.file.name, props.file.size)
  previewType.value = type

  if (type === 'text') {
    loading.value = true
    textContent.value = ''
    try {
      const res = await api.get(fileUrl.value, { responseType: 'text' })
      textContent.value = typeof res.data === 'string' ? res.data : ''
      if (!textContent.value) previewType.value = 'binary'
    } catch {
      previewType.value = 'binary'
    } finally {
      loading.value = false
    }
  } else if (type === 'image' || type === 'pdf') {
    loading.value = true
    previewSrc.value = ''
    try {
      const res = await readWorkspaceFile(props.workspace, props.file.path)
      const data = res.data
      if (data?.is_image || data?.is_binary) {
        previewSrc.value = `data:${data.mime};base64,${data.content}`
      }
    } catch {
      // ignore
    } finally {
      loading.value = false
    }
  } else if (type === 'office') {
    loading.value = true
    try {
      const res = await api.post('/api/office/preview/start', {
        workspace: props.workspace,
        path: props.file.path,
      })
      if (res.data?.url) {
        officePreviewUrl.value = res.data.url
        currentOfficeWs.value = props.workspace
        currentOfficePath.value = props.file.path
      }
    } catch {
      previewType.value = 'binary'
    } finally {
      loading.value = false
    }
  } else {
    textContent.value = ''
    loading.value = false
  }
}

async function stopOfficePreview() {
  if (!currentOfficeWs.value || !currentOfficePath.value) return
  try {
    await api.post('/api/office/preview/stop', {
      workspace: currentOfficeWs.value,
      path: currentOfficePath.value,
    })
  } catch {
    // ignore
  }
  officePreviewUrl.value = ''
  currentOfficeWs.value = ''
  currentOfficePath.value = ''
}

function downloadFile() {
  if (fileUrl.value) window.open(fileUrl.value, '_blank')
}

function copyShareLink() {
  if (!previewUrl.value) return
  const url = window.location.origin + previewUrl.value
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(url).then(() => {
      window.dispatchEvent(new CustomEvent('aries:toast', {
        detail: { message: t('workspace.shareLinkCopied'), type: 'success' },
      }))
    }).catch(() => {})
  } else {
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: url, type: 'info' },
    }))
  }
}

// ============ 文本编辑 ============
function startEdit() {
  if (previewType.value !== 'text') return
  editingContent.value = textContent.value
  editing.value = true
  showAddBtn.value = false
  nextTick(() => {
    const ta = bodyRef.value?.querySelector('.file-viewer-edit-area')
    ta?.focus()
  })
}

function cancelEdit() {
  editing.value = false
  editingContent.value = ''
}

function onEditKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    saveEdit()
  }
}

async function saveEdit() {
  if (!props.file || saving.value) return
  saving.value = true
  try {
    await saveWorkspaceFileContent(props.workspace, props.file.path, editingContent.value)
    editing.value = false
    // 保存后重新加载内容
    await loadFile()
  } catch (err) {
    console.error('保存失败', err)
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: err.response?.data?.detail || '保存失败', type: 'error' },
    }))
  } finally {
    saving.value = false
  }
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// ============ 选中行 -> 添加到对话 ============
function onCodeMouseUp() {
  if (previewType.value !== 'text') return
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) {
    showAddBtn.value = false
    return
  }
  // 从选区中找到起止行号
  const range = sel.getRangeAt(0)
  const startLine = getLineFromNode(range.startContainer)
  const endLine = getLineFromNode(range.endContainer)
  if (startLine == null || endLine == null) {
    showAddBtn.value = false
    return
  }
  const minLine = Math.min(startLine, endLine)
  const maxLine = Math.max(startLine, endLine)
  if (minLine === maxLine && range.startContainer === range.endContainer) {
    // 同一行且无实际选中范围
    const rect = range.getBoundingClientRect()
    if (rect.width === 0 && rect.height === 0) {
      showAddBtn.value = false
      return
    }
  }
  // 计算按钮位置：选区结束位置的上方
  const rect = range.getBoundingClientRect()
  const containerRect = bodyRef.value?.getBoundingClientRect()
  if (!containerRect) return
  const top = rect.top - containerRect.top - 32
  addBtnStyle.value = {
    top: Math.max(top, 4) + 'px',
    right: '12px',
  }
  showAddBtn.value = true
}

function getLineFromNode(node) {
  let el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement
  while (el && el !== bodyRef.value) {
    if (el.tagName === 'TR') {
      const lineAttr = el.getAttribute('data-line')
      if (lineAttr) return parseInt(lineAttr, 10)
    }
    el = el.parentElement
  }
  return null
}

function addSelectionToChat() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) {
    showAddBtn.value = false
    return
  }
  const range = sel.getRangeAt(0)
  const startLine = getLineFromNode(range.startContainer)
  const endLine = getLineFromNode(range.endContainer)
  if (startLine == null || endLine == null) {
    showAddBtn.value = false
    return
  }
  const minLine = Math.min(startLine, endLine)
  const maxLine = Math.max(startLine, endLine)
  // 相对工作目录的文件路径 + 行范围（AI 在 workspace 上下文中可读取）
  const filePath = props.file?.path || ''
  const fullRef = minLine === maxLine
    ? `${filePath}#L${minLine}`
    : `${filePath}#L${minLine}-${maxLine}`
  emit('add-to-chat', fullRef)
  showAddBtn.value = false
  sel.removeAllRanges()
}

watch(() => props.file, loadFile, { immediate: true })

// 组件销毁时停止 office 预览
onBeforeUnmount(() => {
  if (officePreviewUrl.value) {
    stopOfficePreview()
  }
})
</script>
