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

const props = defineProps<{
  plainText: string
  rows?: number
  disabled?: boolean
  placeholder?: string
  activeCommand?: any
  objective?: string
  pluginMenuOpen?: boolean
  attachedImages?: ComposerImage[]
}>()

const emit = defineEmits<{
  'update:plainText': [value: string]
  'update:active-command': [value: any]
  'update:objective': [value: string]
  'update:plugin-menu-open': [value: boolean]
  'update:attached-images': [value: ComposerImage[]]
  send: []
}>()

const editorRef = ref<HTMLDivElement>()
let isUpdatingFromInput = false

const imagePreviews = computed(() => {
  return (props.attachedImages || []).map((img) => img.data)
})

const showPlaceholder = computed(() => !props.plainText)
const minRows = computed(() => props.rows || 3)
const fileRefPattern = /(?:[A-Za-z]:\\[^\s\n]+|\/[^\s\n]+)#L\d+-\d+/g

watch(() => props.plainText, (value) => {
  if (isUpdatingFromInput) return
  renderText(value || '')
}, { immediate: true })

watch(() => props.disabled, (value) => {
  if (editorRef.value) {
    editorRef.value.contentEditable = value ? 'false' : 'true'
  }
}, { immediate: true })

function renderText(text: string) {
  if (!editorRef.value) return
  editorRef.value.innerHTML = ''

  let lastIndex = 0
  for (const match of text.matchAll(fileRefPattern)) {
    const full = match[0]
    const index = match.index || 0
    if (index > lastIndex) appendPlainText(text.slice(lastIndex, index))
    editorRef.value.appendChild(createFileRefTag(full))
    lastIndex = index + full.length
  }

  if (lastIndex < text.length) appendPlainText(text.slice(lastIndex))
}

function appendPlainText(text: string) {
  if (!editorRef.value || !text) return
  const lines = text.split('\n')
  lines.forEach((line, index) => {
    if (index > 0) editorRef.value?.appendChild(document.createElement('br'))
    if (line) editorRef.value?.appendChild(document.createTextNode(line))
  })
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
  if (el.classList.contains('file-ref-tag')) return el.dataset.ref || ''

  let text = ''
  for (const child of el.childNodes) {
    text += extractNodeText(child)
  }
  if (el.tagName === 'DIV') text += '\n'
  return text
}

function onInput() {
  isUpdatingFromInput = true
  emit('update:plainText', extractText())
  nextTick(() => {
    isUpdatingFromInput = false
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
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    emit('send')
  }
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
  min-height: calc(1.5em * v-bind(minRows));
  padding: 10px 12px;
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
  caret-color: var(--accent, #3b82f6);
}

.composer-editor:empty::before {
  content: attr(data-placeholder);
  color: var(--text-muted);
  pointer-events: none;
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
