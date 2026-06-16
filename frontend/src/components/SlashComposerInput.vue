<template>
  <div class="slash-composer-input" :class="{ 'has-images': imagePreviews.length > 0 }">
    <div v-if="imagePreviews.length" class="image-previews">
      <div v-for="(img, i) in imagePreviews" :key="i" class="image-preview">
        <img :src="img" alt="" />
        <button type="button" class="image-remove" @click="removeImage(i)">×</button>
      </div>
    </div>
    <textarea
      :value="plainText"
      :rows="computedRows"
      :disabled="disabled"
      :placeholder="placeholder"
      class="composer-textarea"
      @input="onInput"
      @keydown="onKeydown"
      @focus="onFocus"
      ref="textareaRef"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

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

const textareaRef = ref<HTMLTextAreaElement>()

const imagePreviews = computed(() => {
  return (props.attachedImages || []).map((img) => img.data)
})

// 自动计算行数：根据内容行数动态调整，最少 rows 行，最多 12 行
const computedRows = computed(() => {
  const minRows = props.rows || 3
  if (!props.plainText) return minRows
  const lineCount = props.plainText.split('\n').length
  // 限制最大行数避免无限增高
  return Math.min(Math.max(minRows, lineCount), 12)
})

// 记录光标位置，用于修复焦点问题
let lastSelectionStart = 0
let lastSelectionEnd = 0

function saveSelection() {
  const el = textareaRef.value
  if (el) {
    lastSelectionStart = el.selectionStart
    lastSelectionEnd = el.selectionEnd
  }
}

function restoreSelection() {
  const el = textareaRef.value
  if (el) {
    el.selectionStart = lastSelectionStart
    el.selectionEnd = lastSelectionEnd
  }
}

function onInput(e: Event) {
  const target = e.target as HTMLTextAreaElement
  saveSelection()
  emit('update:plainText', target.value)
  // 输入后恢复光标位置（防止某些情况下光标跳到末尾）
  nextTick(() => {
    restoreSelection()
  })
}

function onFocus() {
  // 聚焦时恢复上次光标位置
  restoreSelection()
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
  textareaRef.value?.focus()
}

defineExpose({ openFilePicker, clearImages, focus })
</script>

<style scoped>
.slash-composer-input {
  display: flex;
  flex-direction: column;
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

.composer-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.5;
  color: inherit;
  font-family: inherit;
  min-height: calc(1.5em * v-bind(computedRows));
  transition: min-height 0.15s ease;
  overflow-y: auto;
  caret-color: var(--accent, #3b82f6);
  padding: 10px 12px;
  box-sizing: border-box;
}

.composer-textarea::placeholder {
  color: var(--text-muted);
}

.slash-composer-input.has-images .composer-textarea {
  padding-top: 8px;
}
</style>
