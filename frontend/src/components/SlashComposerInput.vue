<template>
  <div class="slash-composer-input">
    <textarea
      :value="plainText"
      :rows="rows"
      :disabled="disabled"
      :placeholder="placeholder"
      class="composer-textarea"
      @input="onInput"
      @keydown="onKeydown"
      ref="textareaRef"
    />
    <div v-if="imagePreviews.length" class="image-previews">
      <div v-for="(img, i) in imagePreviews" :key="i" class="image-preview">
        <img :src="img" alt="" />
        <button type="button" class="image-remove" @click="removeImage(i)">×</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

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

function onInput(e: Event) {
  const target = e.target as HTMLTextAreaElement
  emit('update:plainText', target.value)
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

defineExpose({ openFilePicker, clearImages })
</script>

<style scoped>
.slash-composer-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
}

.composer-textarea::placeholder {
  color: var(--text-muted);
}

.image-previews {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.image-preview {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
