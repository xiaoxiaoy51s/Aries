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

// 使用 ##...## 包裹的精确匹配
//   1. 带行号: ##D:\path\file.py#L1-20##
//   2. 纯文件: ##D:\path\file.py##
//   3. 文件夹: ##D:\path\folder\##
const fileRefWithLinesPattern = /##((?:[A-Za-z]:\\[^\s\n#]+|\/[^\s\n#]+)#L\d+-\d+)##/g
const plainFileRefPattern = /##((?:[A-Za-z]:\\[^\s\n#]+\.[a-zA-Z0-9_]+|\/[^\s\n#]+\.[a-zA-Z0-9_]+))##/g
const folderRefPattern = /##((?:[A-Za-z]:\\[^\s\n#]*|\/[^\s\n#]*)[\\/])##/g
const codeReviewPattern = /^@code_review(?:\s+(?:branch|full))?/
const agentModePattern = /^@(ask|explore|plan)/
const agentModeLabels: Record<string, string> = { ask: '问答', explore: '探索', plan: '规划' }
// 技能引用：@skill:<folder_name>
const skillRefPattern = /@skill:([A-Za-z0-9._-]+)/g
// 子 Agent 引用：@subagent:<name>
const subagentRefPattern = /@subagent:([A-Za-z0-9._-]+)/g

function renderContent() {
  if (!contentRef.value) return
  const text = props.content || ''
  contentRef.value.innerHTML = ''

  const matches: { type: 'file' | 'plain-file' | 'folder' | 'code-review' | 'agent-mode' | 'skill' | 'subagent'; value: string; index: number; end: number }[] = []

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
    matches.push({ type: 'skill', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  for (const m of text.matchAll(subagentRefPattern)) {
    matches.push({ type: 'subagent', value: m[1], index: m.index || 0, end: (m.index || 0) + m[0].length })
  }
  const codeReviewMatch = text.match(codeReviewPattern)
  if (codeReviewMatch && codeReviewMatch.index !== undefined) {
    matches.push({
      type: 'code-review',
      value: codeReviewMatch[0],
      index: codeReviewMatch.index,
      end: codeReviewMatch.index + codeReviewMatch[0].length,
    })
  }
  const agentModeMatch = text.match(agentModePattern)
  if (agentModeMatch && agentModeMatch.index !== undefined) {
    const fullMarker = agentModeMatch[0]
    matches.push({
      type: 'agent-mode',
      value: fullMarker,
      index: agentModeMatch.index,
      end: agentModeMatch.index + fullMarker.length,
    })
  }

  // 去重：类型优先级高 + 区间长 的优先保留
  const typePriority: Record<string, number> = { 'file': 5, 'folder': 4, 'plain-file': 3, 'code-review': 2, 'agent-mode': 2, 'skill': 1, 'subagent': 1 }
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
    contentRef.value.appendChild(
      match.type === 'file'
        ? createFileRefTag(match.value)
        : match.type === 'plain-file'
          ? createPlainFileRefTag(match.value)
          : match.type === 'folder'
            ? createFolderRefTag(match.value)
            : match.type === 'skill'
              ? createSkillTag(match.value)
              : match.type === 'subagent'
                ? createSubagentTag(match.value)
                : match.type === 'agent-mode'
                  ? createAgentModeTag(match.value)
                  : createCodeReviewTag(match.value)
    )
    lastIndex = match.end
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

function createCodeReviewTag(value: string) {
  const tag = document.createElement('span')
  tag.className = 'code-review-tag'
  tag.textContent = value
  return tag
}

function createAgentModeTag(label: string) {
  const tag = document.createElement('span')
  tag.className = 'agent-mode-tag'
  tag.textContent = label
  return tag
}

function createSkillTag(folderName: string) {
  const tag = document.createElement('span')
  tag.className = 'skill-tag'

  const name = document.createElement('span')
  name.className = 'skill-tag-name'
  name.textContent = folderName
  tag.appendChild(name)

  return tag
}

function createSubagentTag(agentName: string) {
  const tag = document.createElement('span')
  tag.className = 'subagent-tag'

  const icon = document.createElement('span')
  icon.className = 'subagent-tag-icon'
  icon.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
  tag.appendChild(icon)

  const name = document.createElement('span')
  name.className = 'subagent-tag-name'
  name.textContent = agentName
  tag.appendChild(name)

  return tag
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

function createPlainFileRefTag(full: string) {
  const filePath = full.replace(/\\/g, '/')
  const fileName = filePath.split('/').pop() || filePath

  const tag = document.createElement('span')
  tag.className = 'file-ref-tag plain-file-tag'

  const icon = document.createElement('span')
  icon.className = 'file-ref-icon'
  icon.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>'
  tag.appendChild(icon)

  const name = document.createElement('span')
  name.className = 'file-ref-name'
  name.textContent = fileName
  tag.appendChild(name)

  return tag
}

function createFolderRefTag(full: string) {
  const folderPath = full.replace(/\\/g, '/')
  const folderName = folderPath.split('/').filter(Boolean).pop() || folderPath

  const tag = document.createElement('span')
  tag.className = 'folder-ref-tag'

  const icon = document.createElement('span')
  icon.className = 'folder-ref-icon'
  icon.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
  tag.appendChild(icon)

  const name = document.createElement('span')
  name.className = 'folder-ref-name'
  name.textContent = folderName
  tag.appendChild(name)

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

:deep(.agent-mode-tag) {
  display: inline-flex;
  align-items: center;
  height: 24px;
  margin: 0 2px;
  padding: 0 8px;
  border-radius: 6px;
  background: rgba(139, 92, 246, 0.1);
  color: #7c3aed;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
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
  padding: 0 8px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

/* 子 Agent chip（@subagent:xxx），紫色系 */
:deep(.subagent-tag) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  max-width: 100%;
  height: 26px;
  margin: 0 2px;
  padding: 0;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.25);
  border-radius: 6px;
  color: #7c3aed;
  font-size: 13px;
  line-height: 1;
  vertical-align: middle;
  white-space: nowrap;
  cursor: default;
  user-select: none;
  overflow: hidden;
}

:deep(.subagent-tag-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-left: 6px;
  flex-shrink: 0;
  opacity: 0.85;
}

:deep(.subagent-tag-name) {
  padding: 0 6px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
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

/* 纯文件路径 chip（无行号） */
:deep(.plain-file-tag) {
  background: #fafafa;
  border-color: #e5e5e5;
}

:deep(.file-ref-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding-left: 6px;
  flex-shrink: 0;
  opacity: 0.6;
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
