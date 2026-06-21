<template>
  <div class="slash-composer-input" :class="{ 'has-images': imagePreviews.length > 0 }">
    <div v-if="imagePreviews.length" class="image-previews">
      <div v-for="(img, i) in imagePreviews" :key="i" class="image-preview">
        <img :src="img" alt="" />
        <button type="button" class="image-remove" @click="removeImage(i)">×</button>
      </div>
    </div>

    <div
      ref="editorRef"
      class="composer-editor"
      contenteditable="true"
      :data-placeholder="showPlaceholder ? placeholder : ''"
      @input="onInput"
      @keydown="onKeydown"
      @focus="onFocus"
      @paste="onPaste"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

export interface ComposerImage {
  id: string
  data: string
  name: string
}

export interface PluginMenuItem {
  id: string
  icon: string
  label: string
  description: string
  badge?: string
  disabled?: boolean
}

const props = defineProps<{
  plainText: string
  rows?: number
  maxRows?: number
  disabled?: boolean
  placeholder?: string
  activeCommand?: any
  objective?: string
  pluginMenuOpen?: boolean
  attachedImages?: ComposerImage[]
  pluginItems?: PluginMenuItem[]
  skillItems?: PluginMenuItem[]
}>()

const emit = defineEmits<{
  'update:plainText': [value: string]
  'update:active-command': [value: any]
  'update:objective': [value: string]
  'update:plugin-menu-open': [value: boolean]
  'update:attached-images': [value: ComposerImage[]]
  send: []
  'plugin-select': [item: PluginMenuItem]
  'slash-keydown': [e: KeyboardEvent]
}>()

const editorRef = ref<HTMLDivElement>()
let isUpdatingFromInput = false

const imagePreviews = computed(() => {
  return (props.attachedImages || []).map((img) => img.data)
})

const showPlaceholder = computed(() => !props.plainText)
const minRows = computed(() => props.rows || 3)
const maxRows = computed(() => props.maxRows || 5)

// 使用 ##...## 包裹的精确匹配（文件和文件夹添加对话时使用此格式）
// 匹配三种类型：
//   1. 带行号: ##D:\path\file.py#L1-20##
//   2. 纯文件: ##D:\path\file.py##
//   3. 文件夹: ##D:\path\folder\##
const fileRefWithLinesPattern = /##((?:[A-Za-z]:\\[^\s\n#]+|\/[^\s\n#]+)#L\d+-\d+)##/g
const plainFileRefPattern = /##((?:[A-Za-z]:\\[^\s\n#]+\.[a-zA-Z0-9_]+|\/[^\s\n#]+\.[a-zA-Z0-9_]+))##/g
const folderRefPattern = /##((?:[A-Za-z]:\\[^\s\n#]*|\/[^\s\n#]*)[\\/])##/g
const codeReviewPattern = /^@code_review(?:\s+(?:unstaged|staged|branch|full))?/
const codeReviewAnyPattern = /@code_review(?:\s+(?:unstaged|staged|branch|commit|full))?/
// 技能引用：@skill:<folder_name>，folder_name 由字母/数字/-/_/. 组成
const skillRefPattern = /@skill:([A-Za-z0-9._-]+)/g

// Slash menu state - delegated to ChatComposer; only emit open/close flags
const showSlashMenu = computed(() => {
  if (!props.plainText) return false
  const lines = props.plainText.split('\n')
  const last = lines[lines.length - 1]
  return last.startsWith('/') && !last.includes(' ')
})

watch(showSlashMenu, (val) => {
  emit('update:plugin-menu-open', val)
})

watch(() => props.plainText, (value) => {
  if (isUpdatingFromInput) return
  const normalized = normalizeCodeReviewText(value || '')
  if (normalized !== (value || '')) {
    emit('update:plainText', normalized)
    return
  }
  renderText(normalized)
}, { immediate: true })

watch(() => props.disabled, (value) => {
  if (editorRef.value) {
    editorRef.value.contentEditable = value ? 'false' : 'true'
  }
}, { immediate: true })

function normalizeCodeReviewText(text: string) {
  const match = text.match(codeReviewAnyPattern)
  if (!match || match.index === undefined || match.index === 0) return text
  const marker = match[0]
  const before = text.slice(0, match.index).trim()
  const after = text.slice(match.index + marker.length).trimStart()
  return [marker, before, after].filter(Boolean).join(' ')
}

function renderText(text: string) {
  if (!editorRef.value) return
  editorRef.value.innerHTML = ''

  // 收集所有 ##包裹## 格式的匹配
  // value 存储捕获组（不带 ##），但区间是 ##...## 整体的长度
  const matches: { type: 'file' | 'plain-file' | 'folder' | 'code-review' | 'skill'; value: string; index: number; end: number }[] = []

  for (const m of text.matchAll(fileRefWithLinesPattern)) {
    matches.push({ type: 'file', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  for (const m of text.matchAll(folderRefPattern)) {
    matches.push({ type: 'folder', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  for (const m of text.matchAll(plainFileRefPattern)) {
    matches.push({ type: 'plain-file', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  for (const m of text.matchAll(skillRefPattern)) {
    // value 存 folder_name；区间覆盖 "@skill:xxx"
    matches.push({ type: 'skill', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  const codeReviewMatch = text.match(codeReviewPattern)
  if (codeReviewMatch && codeReviewMatch.index !== undefined) {
    matches.push({ type: 'code-review', value: codeReviewMatch[0], index: codeReviewMatch.index, end: codeReviewMatch.index + codeReviewMatch[0].length })
  }

  // 去重：区间长 + 类型优先级高 的优先保留
  // 优先级：file(带行号) > folder > plain-file > code-review > skill
  const typePriority: Record<string, number> = { 'file': 5, 'folder': 4, 'plain-file': 3, 'code-review': 2, 'skill': 1 }
  const sorted = matches.sort((a, b) => {
    const pa = typePriority[a.type] || 0
    const pb = typePriority[b.type] || 0
    if (pa !== pb) return pb - pa
    const la = a.end - a.index
    const lb = b.end - b.index
    if (la !== lb) return lb - la
    return a.index - b.index
  })
  const filtered: typeof sorted = []
  for (const m of sorted) {
    const overlap = filtered.some(f => {
      const mStart = m.index
      const mEnd = m.end
      const fStart = f.index
      const fEnd = f.end
      return mStart < fEnd && mEnd > fStart
    })
    if (overlap) continue
    filtered.push(m)
  }
  filtered.sort((a, b) => a.index - b.index)

  let lastIndex = 0
  for (const match of filtered) {
    if (match.index < lastIndex) continue
    if (match.index > lastIndex) appendPlainText(text.slice(lastIndex, match.index))
    editorRef.value.appendChild(
      match.type === 'file'
        ? createFileRefTag(match.value)
        : match.type === 'plain-file'
          ? createPlainFileRefTag(match.value)
          : match.type === 'folder'
            ? createFolderRefTag(match.value)
            : match.type === 'skill'
              ? createSkillTag(match.value)
              : createCodeReviewTag(match.value)
    )
    lastIndex = match.end
  }

  if (lastIndex < text.length) appendPlainText(text.slice(lastIndex))

  // 移除浏览器可能自动生成的链接
  removeAutoLinks()
}

function appendPlainText(text: string) {
  if (!editorRef.value || !text) return
  const lines = text.split('\n')
  lines.forEach((line, index) => {
    if (index > 0) editorRef.value?.appendChild(document.createElement('br'))
    if (line) editorRef.value?.appendChild(document.createTextNode(line))
  })
}

function createCodeReviewTag(value: string) {
  const tag = document.createElement('span')
  tag.className = 'code-review-tag'
  tag.contentEditable = 'false'
  tag.dataset.ref = value
  tag.textContent = value
  return tag
}

function createSkillTag(folderName: string) {
  // 找到对应技能的 label / icon（若 props.skillItems 提供）
  const skill = (props.skillItems || []).find((s) => s.id === folderName)
  const label = skill?.label || folderName

  const tag = document.createElement('span')
  tag.className = 'skill-tag'
  tag.contentEditable = 'false'
  tag.dataset.ref = folderName

  const name = document.createElement('span')
  name.className = 'skill-tag-name'
  name.textContent = label
  tag.appendChild(name)

  const remove = document.createElement('button')
  remove.type = 'button'
  remove.className = 'file-ref-remove'
  remove.textContent = '\u00d7'
  remove.addEventListener('click', (e) => {
    e.stopPropagation()
    tag.remove()
    emit('update:plainText', extractText())
  })
  tag.appendChild(remove)

  return tag
}

function createFileRefTag(full: string) {
  const match = full.match(/^(.+?)#L(\d+)-(\d+)$/)
  const filePath = match?.[1] || full
  const fileName = filePath.replace(/\\/g, '/').split('/').pop() || filePath
  const lineRange = match ? `#L${match[2]}-${match[3]}` : ''

  const tag = document.createElement('span')
  tag.className = 'file-ref-tag'
  tag.contentEditable = 'false'
  tag.dataset.ref = full

  const name = document.createElement('span')
  name.className = 'file-ref-name'
  name.textContent = fileName
  tag.appendChild(name)

  const lines = document.createElement('span')
  lines.className = 'file-ref-lines'
  lines.textContent = lineRange
  tag.appendChild(lines)

  const remove = document.createElement('button')
  remove.type = 'button'
  remove.className = 'file-ref-remove'
  remove.textContent = '×'
  remove.addEventListener('click', (e) => {
    e.stopPropagation()
    tag.remove()
    emit('update:plainText', extractText())
  })
  tag.appendChild(remove)

  return tag
}

function createPlainFileRefTag(full: string) {
  // full 格式: "D:\path\to\file.py" 或 "/path/to/file.py"
  const filePath = full.replace(/\\/g, '/')
  const fileName = filePath.split('/').pop() || filePath

  const tag = document.createElement('span')
  tag.className = 'file-ref-tag plain-file-tag'
  tag.contentEditable = 'false'
  tag.dataset.ref = full

  // 文件图标
  const icon = document.createElement('span')
  icon.className = 'file-ref-icon'
  icon.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>'
  tag.appendChild(icon)

  // 文件名
  const name = document.createElement('span')
  name.className = 'file-ref-name'
  name.textContent = fileName
  tag.appendChild(name)

  // 删除按钮
  const remove = document.createElement('button')
  remove.type = 'button'
  remove.className = 'file-ref-remove'
  remove.textContent = '\u00d7'
  remove.addEventListener('click', (e) => {
    e.stopPropagation()
    tag.remove()
    emit('update:plainText', extractText())
  })
  tag.appendChild(remove)

  return tag
}

function createFolderRefTag(full: string) {
  // full 格式: "D:\work_dir\path\folder/" 或 "/path/to/folder/"
  const folderPath = full.replace(/\\/g, '/')
  const folderName = folderPath.split('/').filter(Boolean).pop() || folderPath

  const tag = document.createElement('span')
  tag.className = 'folder-ref-tag'
  tag.contentEditable = 'false'
  tag.dataset.ref = full

  // 文件夹图标
  const icon = document.createElement('span')
  icon.className = 'folder-ref-icon'
  icon.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
  tag.appendChild(icon)

  // 文件夹名称
  const name = document.createElement('span')
  name.className = 'folder-ref-name'
  name.textContent = folderName
  tag.appendChild(name)

  // 删除按钮
  const remove = document.createElement('button')
  remove.type = 'button'
  remove.className = 'file-ref-remove'
  remove.textContent = '\u00d7'
  remove.addEventListener('click', (e) => {
    e.stopPropagation()
    tag.remove()
    emit('update:plainText', extractText())
  })
  tag.appendChild(remove)

  return tag
}

function extractText() {
  if (!editorRef.value) return ''
  let text = ''
  for (const node of editorRef.value.childNodes) {
    text += extractNodeText(node)
  }
  return text.replace(/\n$/, '')
}

function extractNodeText(node: ChildNode): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
  if (node.nodeType !== Node.ELEMENT_NODE) return ''

  const el = node as HTMLElement
  if (el.tagName === 'BR') return '\n'
  if (el.classList.contains('skill-tag')) {
    return `@skill:${el.dataset.ref || ''}`
  }
  if (el.classList.contains('file-ref-tag') || el.classList.contains('code-review-tag') || el.classList.contains('folder-ref-tag')) {
    const ref = el.dataset.ref || ''
    // 文件/文件夹引用统一用 ##...## 包裹，方便后续正则匹配
    if (el.classList.contains('code-review-tag')) return ref
    return `##${ref}##`
  }

  let text = ''
  for (const child of el.childNodes) {
    text += extractNodeText(child)
  }
  if (el.tagName === 'DIV') text += '\n'
  return text
}

function onInput() {
  isUpdatingFromInput = true
  // 将浏览器自动生成的链接转换为纯文本
  removeAutoLinks()
  const text = normalizeCodeReviewText(extractText())
  emit('update:plainText', text)
  if (text !== extractText()) {
    renderText(text)
  }
  nextTick(() => {
    isUpdatingFromInput = false
    // 再次清理，防止 Chrome 延迟生成的链接
    if (editorRef.value) {
      removeAutoLinks()
      const cleaned = normalizeCodeReviewText(extractText())
      if (cleaned !== props.plainText) {
        emit('update:plainText', cleaned)
      }
    }
  })
}

function onPaste(e: ClipboardEvent) {
  e.preventDefault()
  // 粘贴纯文本，避免浏览器自动将 URL 转为 <a> 标签
  const text = e.clipboardData?.getData('text/plain') || ''
  if (!text) return
  const selection = window.getSelection()
  if (!selection || !editorRef.value) return
  // 删除当前选区内容
  selection.deleteFromDocument()
  // 插入纯文本
  document.execCommand('insertText', false, text)
}

function removeAutoLinks() {
  if (!editorRef.value) return
  const links = editorRef.value.querySelectorAll('a[href^="http"]')
  links.forEach((link) => {
    const text = document.createTextNode(link.textContent || '')
    link.parentNode?.replaceChild(text, link)
  })
}

function onFocus() {
  if (!editorRef.value) return
  const selection = window.getSelection()
  if (!selection || editorRef.value.childNodes.length > 0) return
  const range = document.createRange()
  range.selectNodeContents(editorRef.value)
  range.collapse(false)
  selection.removeAllRanges()
  selection.addRange(range)
}

function onKeydown(e: KeyboardEvent) {
  if (showSlashMenu.value) {
    // 让父级 ChatComposer 处理方向键/Enter/Tab/Escape
    if (
      e.key === 'ArrowDown' ||
      e.key === 'ArrowUp' ||
      e.key === 'Enter' ||
      e.key === 'Tab' ||
      e.key === 'Escape'
    ) {
      emit('slash-keydown', e)
      if (e.defaultPrevented) return
    }
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    emit('send')
  }
}

function iconFor(name: string): string {
  const ICON_PATHS: Record<string, string> = {
    'file-text':
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    cpu:
      '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/>',
    smile:
      '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>',
    'git-branch':
      '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    zap:
      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    'message-square':
      '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    code:
      '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    target:
      '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    sidebar:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
    brain:
      '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44"/><path d="M12 2a8 8 0 0 0-8 8c0 3.866 2.582 7.13 6.12 8.18"/><path d="M12 22a8 8 0 0 0 8-8c0-3.866-2.582-7.13-6.12-8.18"/>',
    compass:
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 13l-2-4 4-2-2 4z"/>',
    list:
      '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    maximize:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="12" y1="8" x2="12" y2="16"/>',
    package:
      '<line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    layers:
      '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    user:
      '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    lightbulb:
      '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z"/>',
  }
  const inner = ICON_PATHS[name] || ICON_PATHS['file-text']
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
}

function removeImage(index: number) {
  const imgs = [...(props.attachedImages || [])]
  imgs.splice(index, 1)
  emit('update:attached-images', imgs)
}

function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.multiple = true
  input.onchange = () => {
    const files = Array.from(input.files || [])
    Promise.all(
      files.map(
        (f) =>
          new Promise<ComposerImage>((resolve) => {
            const reader = new FileReader()
            reader.onload = () =>
              resolve({ id: crypto.randomUUID(), data: reader.result as string, name: f.name })
            reader.readAsDataURL(f)
          })
      )
    ).then((imgs) => {
      emit('update:attached-images', [...(props.attachedImages || []), ...imgs])
    })
  }
  input.click()
}

function clearImages() {
  emit('update:attached-images', [])
}

function focus() {
  editorRef.value?.focus()
}

defineExpose({ openFilePicker, clearImages, focus })
</script>

<style scoped>
.slash-composer-input {
  display: flex;
  flex-direction: column;
}

.composer-editor {
  width: 100%;
  min-height: calc(1.25em * v-bind(minRows));
  max-height: calc(1.25em * v-bind(maxRows));
  padding: 8px 10px;
  box-sizing: border-box;
  outline: none;
  border: none;
  background: transparent;
  color: inherit;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
  caret-color: var(--accent, #3b82f6);
}

/* 覆盖浏览器自动链接样式，让 URL 显示为普通文本 */
.composer-editor a[href^="http"] {
  color: inherit;
  text-decoration: none;
  cursor: text;
  pointer-events: none;
}

.composer-editor:empty::before {
  content: attr(data-placeholder);
  color: var(--text-muted);
  pointer-events: none;
}

.slash-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 6px);
  max-height: 360px;
  overflow-y: auto;
  background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  padding: 6px;
  z-index: 200;
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
}

.slash-composer-input {
  position: relative;
}

.slash-menu-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.slash-menu-group {
  display: flex;
  flex-direction: column;
}

.slash-menu-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 8px 10px 4px;
  user-select: none;
}

.slash-menu-item {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  transition: background 0.12s, color 0.12s;
  min-height: 36px;
}

.slash-menu-item--active,
.slash-menu-item:hover {
  background: var(--accent-hover);
}

.slash-menu-item--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.slash-menu-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.slash-menu-text {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.slash-menu-label {
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  flex-shrink: 0;
}

.slash-menu-desc {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slash-menu-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 999px;
  white-space: nowrap;
}

.slash-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 4px;
}

:deep(.code-review-tag) {
  display: inline-flex;
  align-items: center;
  height: 24px;
  margin: 0 2px;
  padding: 0 8px;
  border-radius: 6px;
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
}

:deep(.file-ref-tag) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  max-width: 100%;
  height: 26px;
  margin: 0 2px;
  padding: 0;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  color: #333;
  font-size: 13px;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
  overflow: hidden;
}

:deep(.file-ref-name) {
  padding: 0 6px 0 8px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

:deep(.file-ref-lines) {
  color: #666;
  font-size: 12px;
  flex-shrink: 0;
  padding-right: 2px;
}

:deep(.file-ref-remove) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 4px;
  margin-right: 3px;
  padding: 0;
  border: none;
  background: #e8e8e8;
  color: #555;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
  transition: background 0.15s;
}

:deep(.file-ref-remove:hover) {
  background: #d5d5d5;
  color: #333;
}

/* 文件夹路径 chip */
:deep(.folder-ref-tag) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  max-width: 100%;
  height: 26px;
  margin: 0 2px;
  padding: 0;
  background: #f0f4ff;
  border: 1px solid #c7d6fe;
  border-radius: 6px;
  color: #3b5998;
  font-size: 13px;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
  overflow: hidden;
}

:deep(.folder-ref-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-left: 6px;
  flex-shrink: 0;
  opacity: 0.65;
}

:deep(.folder-ref-name) {
  padding: 0 6px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

/* 技能 chip（@skill:xxx），与 code-review 同色系（蓝） */
:deep(.skill-tag) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  max-width: 100%;
  height: 26px;
  margin: 0 2px;
  padding: 0;
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.25);
  border-radius: 6px;
  color: #2563eb;
  font-size: 13px;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
  overflow: hidden;
}

:deep(.skill-tag-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-left: 6px;
  flex-shrink: 0;
  opacity: 0.85;
}

:deep(.skill-tag-name) {
  padding: 0 4px 0 8px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

/* 纯文件路径 chip（无行号） */
:deep(.plain-file-tag) {
  background: #fafafa;
  border-color: #e5e5e5;
}

:deep(.plain-file-tag .file-ref-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-left: 6px;
  flex-shrink: 0;
  opacity: 0.6;
}

.image-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 12px 0;
}

.image-preview {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: #f6f6f4;
  flex-shrink: 0;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
