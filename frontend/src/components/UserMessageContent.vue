<template>
  <div class="user-message-content">
    <div v-if="resolvedImages.length" class="user-images">
      <img
        v-for="(src, index) in resolvedImages"
        :key="index"
        :src="src"
        alt="用户上传图片"
        class="user-image"
      />
    </div>
    <div ref="contentRef" class="message-text"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useModelStore } from '@/stores/model'

const props = defineProps<{
  content: string
  slashCommand?: string
  slashBody?: string
  images?: string[]
}>()

const modelStore = useModelStore()
const contentRef = ref<HTMLDivElement>()

const resolvedImages = computed(() => {
  return (props.images || []).map((src) => {
    if (src.startsWith('data:') || src.startsWith('http://') || src.startsWith('https://')) {
      return src
    }
    const path = src.startsWith('/') ? src : `/${src}`
    return `${modelStore.getBaseUrl()}${path}`
  })
})

const fileRefPattern = /(?:[A-Za-z]:\\[^\s\n]+|\/[^\s\n]+)#L\d+-\d+/g

function renderContent() {
  if (!contentRef.value) return
  const text = props.content || ''
  contentRef.value.innerHTML = ''

  let lastIndex = 0
  for (const match of text.matchAll(fileRefPattern)) {
    const full = match[0]
    const index = match.index || 0
    if (index > lastIndex) appendPlainText(text.slice(lastIndex, index))
    contentRef.value.appendChild(createFileRefTag(full))
    lastIndex = index + full.length
  }

  if (lastIndex < text.length) appendPlainText(text.slice(lastIndex))
}

function appendPlainText(text: string) {
  if (!contentRef.value || !text) return
  const lines = text.split('\n')
  lines.forEach((line, index) => {
    if (index > 0) contentRef.value?.appendChild(document.createElement('br'))
    if (line) contentRef.value?.appendChild(document.createTextNode(line))
  })
}

function createFileRefTag(full: string) {
  const match = full.match(/^(.+?)#L(\d+)-(\d+)$/)
  const filePath = match?.[1] || full
  const fileName = filePath.replace(/\\/g, '/').split('/').pop() || filePath
  const lineRange = match ? `#L${match[2]}-${match[3]}` : ''

  const tag = document.createElement('span')
  tag.className = 'file-ref-tag'

  const name = document.createElement('span')
  name.className = 'file-ref-name'
  name.textContent = fileName
  tag.appendChild(name)

  const lines = document.createElement('span')
  lines.className = 'file-ref-lines'
  lines.textContent = lineRange
  tag.appendChild(lines)

  return tag
}

watch(() => props.content, () => {
  renderContent()
}, { immediate: true })

onMounted(() => {
  renderContent()
})
</script>

<style scoped>
.user-message-content {
  word-break: break-word;
}

.message-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
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

.user-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.user-image {
  max-width: 240px;
  max-height: 180px;
  border-radius: 10px;
  border: 1px solid var(--border);
  object-fit: cover;
}
</style>
