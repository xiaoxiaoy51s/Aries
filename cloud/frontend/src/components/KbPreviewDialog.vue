<template>
  <el-dialog
    class="kb-preview-dialog"
    :model-value="visible"
    :title="t('kb.previewTitle')"
    :width="pdfUrl ? '1200px' : '720px'"
    top="6vh"
    :close-on-click-modal="false"
    @update:model-value="onUpdateVisible"
  >
    <div class="kb-preview-body" :class="{ 'has-pdf': !!pdfUrl }">
      <!-- 左侧：提取内容（编辑区） -->
      <div class="kb-preview-col kb-preview-left">
        <div class="kb-preview-pane-label">{{ t('kb.extract') }}</div>

        <!-- 标题 -->
        <h3 v-if="displayTitle" class="kb-preview-title">{{ displayTitle }}</h3>

        <!-- 关键词 -->
        <div v-if="keywordList.length" class="kb-preview-row">
          <span class="kb-preview-label">{{ t('kb.keywords') }}</span>
          <span class="kb-keyword-list">
            <span v-for="(kw, idx) in keywordList" :key="idx" class="kb-keyword-chip">{{ kw }}</span>
          </span>
        </div>

        <!-- 原链接 -->
        <div v-if="originalUrl" class="kb-preview-row">
          <span class="kb-preview-label">{{ t('kb.originalUrl') }}</span>
          <a class="kb-preview-link" :href="originalUrl" target="_blank" rel="noopener">{{ originalUrl }}</a>
        </div>

        <!-- 正文编辑区 -->
        <div class="kb-preview-editor">
          <textarea
            v-model="draft"
            class="kb-preview-textarea"
            :placeholder="t('kb.previewPlaceholder')"
            spellcheck="false"
          />
          <p v-if="!draft.trim()" class="kb-preview-empty">{{ t('kb.previewEmpty') }}</p>
        </div>
      </div>

      <!-- 右侧：PDF 预览（链接提取场景，便于与提取内容对比） -->
      <div v-if="pdfUrl" class="kb-preview-col kb-preview-right">
        <div class="kb-preview-pane-label">{{ t('kb.pdfPreview') }}</div>
        <iframe v-if="pdfSrc" class="kb-preview-pdf" :src="pdfSrc" title="PDF preview" />
        <div v-else class="kb-preview-pdf-loading">{{ t('kb.pdfLoading') }}</div>
      </div>
    </div>

    <template #footer>
      <el-button class="kb-btn kb-btn-ghost" @click="emitCancel">{{ t('settings.cancel') }}</el-button>
      <el-button class="kb-btn kb-btn-primary" :loading="submitting" :disabled="!draft.trim()" @click="emitConfirm">
        {{ t('kb.previewConfirm') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from '../i18n'
import api from '../api'

const props = defineProps({
  visible: { type: Boolean, default: false },
  meta: { type: Object, default: () => ({}) },      // 来源元信息（平台/URL/文件名/标题/关键词）
  initialText: { type: String, default: '' },       // 提取出的原始文本
  submitting: { type: Boolean, default: false },
  pdfUrl: { type: String, default: '' },            // 渲染后 PDF 下载 URL（链接提取场景）
})

const emit = defineEmits(['update:visible', 'confirm', 'cancel'])

const { t } = useI18n()
const draft = ref('')

watch(
  () => [props.visible, props.initialText],
  () => {
    if (props.visible) {
      draft.value = props.initialText || ''
    }
  },
)

const displayTitle = computed(() => props.meta?.title || '')

const originalUrl = computed(() => normalizeUrl(props.meta?.original_url || props.meta?.url || ''))

const pdfUrl = computed(() => props.pdfUrl || props.meta?.pdf_url || '')

const keywordList = computed(() => {
  const v = props.meta?.keywords
  if (Array.isArray(v)) return v.filter(Boolean)
  if (typeof v === 'string' && v.trim()) return v.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  return []
})

function normalizeUrl(url) {
  if (!url) return ''
  if (url.startsWith('//')) return 'https:' + url
  return url
}

// PDF 预览：需要带 Authorization header，用 blob 拉取后生成 objectURL
const pdfSrc = ref('')
let pdfObjectUrl = ''
watch(
  () => pdfUrl.value,
  async (url) => {
    if (pdfObjectUrl) {
      URL.revokeObjectURL(pdfObjectUrl)
      pdfObjectUrl = ''
    }
    pdfSrc.value = ''
    if (!url) return
    try {
      const res = await api.get(url, { responseType: 'blob', timeout: 60000 })
      pdfObjectUrl = URL.createObjectURL(res.data)
      pdfSrc.value = pdfObjectUrl
    } catch {
      // PDF 拉取失败时右侧保持加载态
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl)
})

function onUpdateVisible(v) {
  emit('update:visible', v)
  if (!v) emit('cancel')
}

function emitCancel() {
  emit('cancel')
  emit('update:visible', false)
}

function emitConfirm() {
  emit('confirm', draft.value)
}
</script>

<style scoped>
.kb-preview-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacer-4, 4px);
}
.kb-preview-body.has-pdf {
  flex-direction: row;
  gap: var(--spacer-16, 16px);
  align-items: stretch;
}
.kb-preview-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.kb-preview-left {
  flex: 1;
}
.kb-preview-right {
  width: 46%;
  flex-shrink: 0;
}
.kb-preview-pane-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary, #737373);
  margin-bottom: var(--spacer-8, 8px);
  letter-spacing: 0.02em;
}

.kb-preview-title {
  margin: 0 0 var(--spacer-6, 6px);
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-default, #171717);
  letter-spacing: -0.02em;
  line-height: 1.4;
  word-break: break-word;
}

.kb-preview-row {
  display: flex;
  align-items: flex-start;
  gap: var(--spacer-8, 8px);
  margin-top: var(--spacer-6, 6px);
  font-size: 13px;
  line-height: 1.6;
}
.kb-preview-label {
  flex-shrink: 0;
  color: var(--text-tertiary, #737373);
  min-width: 56px;
}
.kb-keyword-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacer-6, 6px);
}
.kb-keyword-chip {
  display: inline-block;
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  color: var(--text-secondary, #404040);
  border-radius: var(--radius-full, 999px);
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 500;
}
.kb-preview-link {
  color: var(--text-secondary, #404040);
  word-break: break-all;
  text-decoration: none;
  border-bottom: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  transition: color 120ms ease, border-color 120ms ease;
}
.kb-preview-link:hover {
  color: var(--text-default, #171717);
  border-color: var(--text-default, #171717);
}

.kb-preview-editor {
  margin-top: var(--spacer-16, 16px);
  display: flex;
  flex-direction: column;
  gap: var(--spacer-6, 6px);
  flex: 1;
}
.kb-preview-textarea {
  width: 100%;
  height: 62vh;
  min-height: 440px;
  flex: 1;
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.65;
  font-family: inherit;
  color: var(--text-default, #171717);
  background: var(--bg-base-default, #fff);
  box-sizing: border-box;
  resize: vertical;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.kb-preview-textarea:focus {
  outline: none;
  border-color: var(--text-default, #171717);
  box-shadow: 0 0 0 3px rgba(23, 23, 23, 0.08);
}
.kb-preview-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary, #737373);
}

.kb-preview-pdf {
  width: 100%;
  height: 68vh;
  min-height: 460px;
  flex: 1;
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  background: #f5f5f5;
  box-sizing: border-box;
}
.kb-preview-pdf-loading {
  flex: 1;
  min-height: 460px;
  border: 1px dashed var(--border-neutral-l2, rgba(115,115,115,0.18));
  border-radius: var(--radius-10, 10px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-tertiary, #737373);
}

/* ============ el-dialog 外壳（teleport 到 body，用 :global 限定作用域） ============ */
:global(.kb-preview-dialog) {
  border-radius: var(--radius-16, 16px);
  overflow: hidden;
}
:global(.kb-preview-dialog .el-dialog__header) {
  padding: 18px 24px 14px;
  margin-right: 0;
  border-bottom: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
:global(.kb-preview-dialog .el-dialog__title) {
  font-family: var(--font-family-heading, "SF Pro", "PingFang SC", system-ui, sans-serif);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-default, #171717);
  letter-spacing: -0.01em;
}
:global(.kb-preview-dialog .el-dialog__body) {
  padding: 20px 24px;
}
:global(.kb-preview-dialog .el-dialog__footer) {
  padding: 14px 24px 18px;
  border-top: 1px solid var(--border-neutral-l1, rgba(115,115,115,0.12));
}
:global(.kb-preview-dialog .el-dialog__headerbtn) {
  top: 18px;
  right: 20px;
  color: var(--icon-secondary, #404040);
}
:global(.kb-preview-dialog .el-dialog__headerbtn:hover) {
  color: var(--text-default, #171717);
}

/* ============ 按钮（自定义 class，避免污染全局 el-button） ============ */
:global(.kb-preview-dialog .kb-btn) {
  height: 34px;
  padding: 0 16px;
  border-radius: var(--radius-8, 8px);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}
:global(.kb-preview-dialog .kb-btn-ghost) {
  background: var(--bg-base-default, #fff);
  border: 1px solid var(--border-neutral-l2, rgba(115,115,115,0.18));
  color: var(--text-secondary, #404040);
}
:global(.kb-preview-dialog .kb-btn-ghost:hover) {
  background: var(--bg-overlay-l1, rgba(115,115,115,0.08));
  border-color: var(--border-neutral-l3, rgba(115,115,115,0.36));
  color: var(--text-default, #171717);
}
:global(.kb-preview-dialog .kb-btn-primary) {
  background: var(--text-default, #171717);
  border: 1px solid var(--text-default, #171717);
  color: var(--bg-base-default, #fff);
}
:global(.kb-preview-dialog .kb-btn-primary:hover:not(.is-disabled)) {
  background: var(--icon-default-hover, #171717);
  border-color: var(--icon-default-hover, #171717);
}
:global(.kb-preview-dialog .kb-btn-primary.is-disabled) {
  background: var(--bg-overlay-l2, rgba(115,115,115,0.12));
  border-color: var(--border-neutral-l1, rgba(115,115,115,0.12));
  color: var(--text-tertiary, #737373);
}
</style>
