<template>
  <div
    class="file-edit-card"
    :class="{ 'file-edit-card--expanded': expanded, 'file-edit-card--delete': data.isDelete }"
    @click="$emit('click')"
  >
    <div class="file-edit-header">
      <svg
        v-if="!data.isDelete"
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
      <svg
        v-else
        class="file-edit-delete-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        <line x1="10" y1="11" x2="10" y2="17"/>
        <line x1="14" y1="11" x2="14" y2="17"/>
      </svg>
      <img
        v-if="!data.isDelete"
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
      <button
        v-if="!data.isDelete"
        type="button"
        class="view-diff-btn"
        title="查看变更"
        @click.stop="$emit('view-diff')"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <line x1="10" y1="9" x2="8" y2="9"/>
        </svg>
        <span>查看变更</span>
      </button>
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

const emit = defineEmits<{
  click: []
  'view-diff': []
}>()

const displayLines = computed(() => (
  props.expanded ? props.data.allLines : props.data.lines
))

function onIconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.src = `./file-icons/${DEFAULT_FILE}`
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

.file-edit-card--delete {
  border-color: #e5e7eb;
  background: #ffffff;
}

.file-edit-card--delete .file-edit-header {
  background: #ffffff;
  border-bottom: none;
}

.file-edit-delete-icon {
  flex-shrink: 0;
  color: #ef4444;
}

.file-edit-card--delete .file-edit-name {
  color: #1f2937;
}

.view-diff-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
  padding: 2px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
  color: #64748b;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.view-diff-btn:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  color: #334155;
}

.view-diff-btn svg {
  flex-shrink: 0;
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
