<template>
  <div
    class="file-edit-card"
    :class="{ 'file-edit-card--expanded': expanded }"
    @click="$emit('click')"
  >
    <div class="file-edit-header">
      <svg
        class="file-edit-chevron"
        :class="{ expanded }"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="m9 18 6-6-6-6"/>
      </svg>
      <img
        class="file-edit-icon"
        :src="data.iconSrc"
        width="16"
        height="16"
        alt=""
        @error="onIconError"
      />
      <span class="file-edit-name">{{ data.fileName }}</span>
      <span class="file-edit-stats">
        <span v-if="data.added > 0" class="stat-add">+{{ data.added }}</span>
        <span v-if="data.removed > 0" class="stat-remove">-{{ data.removed }}</span>
      </span>
    </div>
    <div v-if="displayLines.length > 0" class="file-edit-diff" :class="{ 'file-edit-diff--expanded': expanded }">
      <div
        v-for="(line, idx) in displayLines"
        :key="idx"
        class="diff-line"
        :class="`diff-line--${line.type}`"
      >
        <span class="diff-gutter" aria-hidden="true"></span>
        <code class="diff-text">
          <template v-if="line.type === 'add' && line.highlight">
            {{ linePrefix(line) }}<mark class="diff-highlight">{{ line.highlight }}</mark>{{ lineSuffix(line) }}
          </template>
          <template v-else>{{ line.text || ' ' }}</template>
        </code>
      </div>
    </div>
    <div v-if="expanded && error" class="file-edit-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DEFAULT_FILE } from 'vscode-icons-js'
import type { FileEditPreviewData, DiffPreviewLine } from '@/utils/fileEditPreview'

const props = defineProps<{
  data: FileEditPreviewData
  expanded?: boolean
  error?: string
}>()

defineEmits<{
  click: []
}>()

const displayLines = computed(() => (
  props.expanded ? props.data.allLines : props.data.lines
))

function onIconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.src = `/file-icons/${DEFAULT_FILE}`
}

function linePrefix(line: DiffPreviewLine): string {
  if (!line.highlight) return line.text
  const idx = line.text.indexOf(line.highlight)
  return idx >= 0 ? line.text.slice(0, idx) : line.text
}

function lineSuffix(line: DiffPreviewLine): string {
  if (!line.highlight) return ''
  const idx = line.text.indexOf(line.highlight)
  return idx >= 0 ? line.text.slice(idx + line.highlight.length) : ''
}
</script>

<style scoped>
.file-edit-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.file-edit-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.file-edit-card--expanded {
  border-color: #cbd5e1;
}

.file-edit-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #f1f5f9;
  min-width: 0;
  background: #fff;
}

.file-edit-chevron {
  flex-shrink: 0;
  color: #64748b;
  transition: transform 0.15s ease;
}

.file-edit-chevron.expanded {
  transform: rotate(90deg);
}

.file-edit-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
}

.file-edit-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-edit-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.stat-add {
  color: #16a34a;
}

.stat-remove {
  color: #dc2626;
}

.file-edit-diff {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.45;
}

.file-edit-diff--expanded {
  max-height: 420px;
  overflow: auto;
}

.diff-line {
  display: flex;
  min-height: 20px;
}

.diff-gutter {
  width: 4px;
  flex-shrink: 0;
}

.diff-text {
  flex: 1;
  padding: 2px 12px 2px 8px;
  white-space: pre;
  margin: 0;
  font-family: inherit;
  font-size: inherit;
}

.file-edit-diff:not(.file-edit-diff--expanded) .diff-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-edit-diff--expanded .diff-text {
  white-space: pre-wrap;
  word-break: break-word;
  overflow: visible;
  text-overflow: unset;
}

.diff-line--remove {
  background: #ffeef0;
}

.diff-line--remove .diff-gutter {
  background: #f85149;
}

.diff-line--remove .diff-text {
  color: #82071e;
}

.diff-line--add {
  background: #e6ffed;
}

.diff-line--add .diff-gutter {
  background: #2ea043;
}

.diff-line--add .diff-text {
  color: #116329;
}

.diff-line--context {
  background: #fff;
}

.diff-line--context .diff-text {
  color: #64748b;
}

.diff-highlight {
  background: rgba(46, 160, 67, 0.25);
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}

.file-edit-error {
  padding: 8px 12px;
  font-size: 12px;
  color: #c2410c;
  border-top: 1px solid #fecaca;
  background: #fff7ed;
}
</style>
