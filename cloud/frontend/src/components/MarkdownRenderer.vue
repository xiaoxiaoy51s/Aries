<template>
  <div class="markdown-content">
    <!-- 渲染后的 Markdown -->
    <div
      ref="markdownContainer"
      class="markdown-body"
      :style="{ fontSize: fontSize + 'px', color: textColor }"
      v-html="sanitizedHtml"
    />

    <!-- 操作按钮区域 -->
    <div v-if="showActions && content && !isStreaming" class="action-buttons">
      <button class="action-btn" @click="copyAllContent" :title="copiedAll ? t('chat.copied') : t('chat.copy')">
        <svg v-if="copiedAll" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import 'github-markdown-css/github-markdown.css'
import DOMPurify from 'dompurify'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { useI18n } from '../i18n'
import { getFileIconUrl } from '../utils/fileIcons'

const { t } = useI18n()

const props = defineProps({
  content: { type: String, default: '' },
  textColor: { type: String, default: 'var(--text-default)' },
  fontSize: { type: Number, default: 15 },
  showActions: { type: Boolean, default: true },
  isStreaming: { type: Boolean, default: false },
})

const copiedAll = ref(false)
let copyResetTimer = null

onBeforeUnmount(() => {
  if (copyResetTimer) clearTimeout(copyResetTimer)
})

// ── markdown-it 实例 ──────────────────────────────────
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
  highlight(str, lang) {
    const codeContent = md.utils.escapeHtml(str)
    const langLabel = md.utils.escapeHtml(lang || 'code')
    const copyBtn = `<button class="copy-btn" data-copy-btn title="${t('chat.copy')}" style="display:flex;align-items:center;justify-content:center;padding:4px;background:none;border:none;cursor:pointer;font-size:13px;color:inherit"><svg viewBox="0 0 1024 1024" width="11" height="11"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="currentColor"></path></svg></button>`
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<div class="code-block-wrapper"><div class="code-header"><span class="code-lang">${langLabel}</span>${copyBtn}</div><pre class="hljs"><code>${highlighted}</code></pre></div>`
      } catch (_) {}
    }
    return `<div class="code-block-wrapper"><div class="code-header"><span class="code-lang">${langLabel}</span>${copyBtn}</div><pre class="hljs"><code>${codeContent}</code></pre></div>`
  },
})

// 关闭模糊链接匹配，避免 hello.py / test.go 等文件名被误识别为链接（.py 等是顶级域名）
md.linkify.set({ fuzzyLink: false, fuzzyEmail: false })

// ── KaTeX 渲染辅助 ──────────────────────────────────
const katexPlaceholders = []
// 文件引用 [@file:path#L3] 占位符
const filerefPlaceholders = []

function escapeRefHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c])
}

// 把 [@file:path#L3] 构造成消息内联 chip HTML
function buildFilerefChip(ref) {
  const hashIdx = ref.lastIndexOf('#L')
  const fullPath = hashIdx >= 0 ? ref.slice(0, hashIdx) : ref
  const lines = hashIdx >= 0 ? ref.slice(hashIdx + 1) : ''
  const name = fullPath.includes('/') ? fullPath.slice(fullPath.lastIndexOf('/') + 1) : fullPath
  const icon = getFileIconUrl(name)
  return (
    `<span class="msg-file-ref-chip" data-ref="${escapeRefHtml(ref)}">` +
    `<img src="${escapeRefHtml(icon)}" width="13" height="13" alt="" class="msg-file-ref-icon" />` +
    `<span class="msg-file-ref-name">${escapeRefHtml(name)}</span>` +
    (lines ? `<span class="msg-file-ref-lines">${escapeRefHtml(lines)}</span>` : '') +
    `</span>`
  )
}

function restoreFilerefPlaceholders(html) {
  return html.replace(/§FILEREF(\d+)§/g, (_m, i) => filerefPlaceholders[Number(i)] ?? _m)
}

function renderKatex(formula, displayMode) {
  try {
    const html = katex.renderToString(formula.trim(), { displayMode, throwOnError: false, strict: 'ignore' })
    katexPlaceholders.push(html)
    return `§KATEX${katexPlaceholders.length - 1}§`
  } catch {
    return displayMode ? `$$${formula}$$` : `$${formula}$`
  }
}

function restoreKatexPlaceholders(html) {
  return html.replace(/§KATEX(\d+)§/g, (_m, i) => katexPlaceholders[Number(i)] ?? _m)
}

const LATEX_HINT = /\\(?:frac|sqrt|sum|int|cdot|times|implies|text|left|right|begin|end|alpha|beta|gamma|pi|theta|leq|geq|neq|pm|mp|infty|partial|nabla)/

function looksLikeLatex(body) {
  const s = body.trim()
  if (!s) return false
  if (LATEX_HINT.test(s)) return true
  if (/[\^_]\{/.test(s)) return true
  if (/\\[a-zA-Z]+/.test(s)) return true
  if (/[=+\-*/^_{}()[\]\\]/.test(s)) return true
  if (/^[A-Za-z](?:'[A-Za-z])?(?:\([^)]*\))?$/.test(s)) return true
  return false
}

function normalizeMathDelimiters(raw) {
  return raw
    .replace(/\uFF04/g, '$')
    .replace(/\uFE69/g, '$')
}

/** 在 markdown-it 之前统一处理各类 LaTeX 定界符 */
function preprocessMath(raw) {
  const codeBlocks = []
  let text = raw.replace(/```[\s\S]*?```/g, (m) => {
    codeBlocks.push(m)
    return `\x00CODE${codeBlocks.length - 1}\x00`
  })
  const inlineCodes = []
  text = text.replace(/`[^`\n]+`/g, (m) => {
    inlineCodes.push(m)
    return `\x00INLINE${inlineCodes.length - 1}\x00`
  })

  // 先提取文件引用 [@file:path#L3]，避免被后续规则破坏
  text = text.replace(/\[@file:([^\]]+?)\]/g, (_m, ref) => {
    filerefPlaceholders.push(buildFilerefChip(ref))
    return `§FILEREF${filerefPlaceholders.length - 1}§`
  })

  // 块级：\[ ... \]、$$ ... $$
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_m, f) => renderKatex(f, true))
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_m, f) => renderKatex(f, true))

  // 块级：单独一行的 [ ... ]（模型常用）
  text = text.replace(/^\[\s*\n([\s\S]*?)\n\s*\]\s*$/gm, (match, f) =>
    looksLikeLatex(f) ? renderKatex(f, true) : match,
  )
  text = text.replace(/^\[\s*((?:\\[\s\S]|[^\]])+?)\s*\]\s*$/gm, (match, f) =>
    looksLikeLatex(f) ? renderKatex(f, true) : match,
  )

  // 行内：\( ... \)
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_m, f) => renderKatex(f, false))

  // 行内：$ ... $（不含换行）
  text = text.replace(/(?<!\$)\$(?!\$)([^\$\n]+?)(?<!\$)\$(?!\$)/g, (match, f) => {
    const body = f.trim()
    if (!body || /^\d+(?:\.\d{1,2})?$/.test(body)) return match
    return renderKatex(f, false)
  })

  // 兜底：仍残留的 $...$（兼容不支持 lookbehind 的环境）
  text = text.replace(/\$([^\$\n]+?)\$/g, (match, f) => {
    if (match.includes('§KATEX')) return match
    const body = f.trim()
    if (!body || /^\d+(?:\.\d{1,2})?$/.test(body)) return match
    if (!looksLikeLatex(body)) return match
    return renderKatex(f, false)
  })

  // 行内：( \frac{...} ) 等带 LaTeX 命令的圆括号
  text = text.replace(/\(\s*((?:\\(?:[a-zA-Z]+|\{[^}]*\})|[\^_{}\d\s=+\-*/().,|<>!:])+?)\s*\)/g, (match, f) =>
    looksLikeLatex(f) ? renderKatex(f, false) : match,
  )

  text = text.replace(/\x00INLINE(\d+)\x00/g, (_m, i) => inlineCodes[Number(i)] ?? _m)
  text = text.replace(/\x00CODE(\d+)\x00/g, (_m, i) => codeBlocks[Number(i)] ?? _m)
  return text
}

// ── KaTeX 插件：渲染 ```math / ```latex 代码块 ─────────────
const defaultFence = md.renderer.rules.fence
md.renderer.rules.fence = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : ''
  if (info === 'math' || info === 'latex') {
    try {
      return renderKatex(token.content, true)
    } catch (_) {
      return `<pre>${md.utils.escapeHtml(token.content)}</pre>`
    }
  }
  return defaultFence ? defaultFence(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options)
}

// ── 渲染管道 ──────────────────────────────────────────
function renderMarkdownToHtml(raw) {
  if (!raw) return ''
  katexPlaceholders.length = 0
  filerefPlaceholders.length = 0
  const html = preprocessMath(normalizeMathDelimiters(raw))
  const rendered = md.render(html)
  const sanitized = DOMPurify.sanitize(rendered, {
    ADD_ATTR: ['target', 'rel', 'class', 'style', 'aria-hidden', 'xmlns', 'data-ref'],
    ADD_TAGS: [
      'span', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'mspace',
      'annotation', 'svg', 'path', 'line', 'rect', 'g', 'use', 'msqrt', 'mtext', 'mtable', 'mtr',
      'mtd', 'mstyle', 'mpadded', 'menclose', 'mover', 'munder', 'munderover', 'ms', 'mglyph',
    ],
  })
  return restoreFilerefPlaceholders(restoreKatexPlaceholders(sanitized))
}

// ── 流式节流渲染 ──────────────────────────────────────
const RENDER_THROTTLE_MS = 80
const displayContent = ref(props.content)
let renderThrottleTimer = null
let lastRenderAt = 0

function flushDisplayContent() {
  if (renderThrottleTimer) {
    clearTimeout(renderThrottleTimer)
    renderThrottleTimer = null
  }
  lastRenderAt = Date.now()
  displayContent.value = props.content
}

watch(() => props.content, (val) => {
  const now = Date.now()
  const elapsed = now - lastRenderAt
  if (elapsed >= RENDER_THROTTLE_MS) {
    lastRenderAt = now
    displayContent.value = val
    if (renderThrottleTimer) {
      clearTimeout(renderThrottleTimer)
      renderThrottleTimer = null
    }
  } else if (!renderThrottleTimer) {
    renderThrottleTimer = setTimeout(() => {
      renderThrottleTimer = null
      lastRenderAt = Date.now()
      displayContent.value = props.content
    }, RENDER_THROTTLE_MS - elapsed)
  }
})

// 流式结束：立即补齐完整内容
watch(() => props.isStreaming, (streaming, prev) => {
  if (prev && !streaming) flushDisplayContent()
})

const sanitizedHtml = computed(() => renderMarkdownToHtml(displayContent.value))

// 代码块复制：用事件委托绑定
const markdownContainer = ref(null)
const copiedCodeBtn = ref(null)
let codeCopyResetTimer = null

async function onCopyCodeClick(e) {
  const path = e.composedPath ? e.composedPath() : []
  const btn = path.find((el) => el instanceof Element && el.hasAttribute && el.hasAttribute('data-copy-btn'))
  if (!btn || !markdownContainer.value) return
  const wrapper = btn.closest('.code-block-wrapper')
  const code = wrapper?.querySelector('code')
  if (!code) return
  e.preventDefault()
  e.stopPropagation()
  const text = code.textContent || ''
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    btn.innerHTML = '✓'
    copiedCodeBtn.value = btn
    if (codeCopyResetTimer) clearTimeout(codeCopyResetTimer)
    codeCopyResetTimer = setTimeout(() => {
      if (copiedCodeBtn.value) {
        copiedCodeBtn.value.innerHTML = '<svg viewBox="0 0 1024 1024" width="11" height="11"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="currentColor"></path></svg>'
        copiedCodeBtn.value = null
      }
    }, 2000)
  } catch (err) {
    console.error('Copy code failed:', err)
  }
}

onMounted(() => {
  nextTick(() => {
    markdownContainer.value?.addEventListener('click', onCopyCodeClick)
  })
})

onBeforeUnmount(() => {
  markdownContainer.value?.removeEventListener('click', onCopyCodeClick)
  if (codeCopyResetTimer) clearTimeout(codeCopyResetTimer)
  if (renderThrottleTimer) clearTimeout(renderThrottleTimer)
})

watch(sanitizedHtml, () => {
  nextTick(() => {
    markdownContainer.value?.removeEventListener('click', onCopyCodeClick)
    markdownContainer.value?.addEventListener('click', onCopyCodeClick)
  })
})

function copyAllContent() {
  if (!props.content) return
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(props.content)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = props.content
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    copiedAll.value = true
    if (copyResetTimer) clearTimeout(copyResetTimer)
    copyResetTimer = setTimeout(() => { copiedAll.value = false }, 1500)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}
</script>

<style scoped>
.markdown-content {
  width: 100%;
}

.markdown-body {
  --md-color: v-bind('textColor');
  font-family: 'Inter', 'Noto Sans SC', ui-sans-serif, -apple-system, BlinkMacSystemFont,
    'Segoe UI', 'Helvetica Neue', Arial, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  line-height: 1.65;
  color: v-bind('textColor');
  background-color: transparent !important;
}

/* 覆盖 github-markdown-css 的默认颜色 */
.markdown-body :deep(p) {
  margin: 6px 0;
  color: v-bind('textColor');
  line-height: 1.65;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  color: v-bind('textColor');
  margin-top: 20px;
  margin-bottom: 8px;
}

.markdown-body :deep(a) {
  color: #3b82f6 !important;
}

.markdown-body :deep(li) {
  color: v-bind('textColor');
}

.markdown-body :deep(.katex-display) {
  margin: 6px 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.markdown-body :deep(.katex-display > .katex) {
  max-width: none;
}

.markdown-body :deep(.katex) {
  font-size: 1.05em;
}

/* 代码块样式 */
.markdown-body :deep(.code-block-wrapper) {
  background-color: var(--bg-base-tertiary, #f4f4f5);
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
  border: none;
}

.markdown-body :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 10px;
  background-color: var(--bg-overlay-l2, #e4e4e7);
  min-height: 24px;
}

.markdown-body :deep(.code-lang) {
  font-size: 11px;
  color: var(--text-tertiary, #71717a);
  text-transform: lowercase;
}

.markdown-body :deep(.copy-btn) {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-tertiary, #52525b);
}

.markdown-body :deep(.copy-btn:hover) {
  color: var(--text-default, #18181b);
}

.markdown-body :deep(pre) {
  padding: 10px;
  overflow-x: auto;
  overflow-y: hidden;
  background: transparent !important;
  border: none;
  margin: 0;
}

.markdown-body :deep(pre code) {
  font-size: 13px;
  line-height: 1.55;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas,
    'Liberation Mono', 'Courier New', monospace;
  font-feature-settings: 'liga' 0;
  background: transparent !important;
  padding: 0;
  color: var(--text-default, #27272a);
}

.markdown-body :deep(code:not(pre code)) {
  background: var(--bg-overlay-l2, rgba(110, 118, 129, 0.10));
  padding: 2px 6px;
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas,
    'Liberation Mono', 'Courier New', monospace;
  font-size: 0.875em;
  font-weight: 500;
}

.markdown-body :deep(table) {
  display: block;
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  border-collapse: collapse;
  border: none;
  background: transparent !important;
}

.markdown-body :deep(table thead),
.markdown-body :deep(table tbody),
.markdown-body :deep(table tr) {
  background: transparent !important;
}

.markdown-body :deep(table tr:nth-child(2n)) {
  background: var(--bg-overlay-l1) !important;
}

.markdown-body :deep(table th),
.markdown-body :deep(table td) {
  padding: 8px;
  font-size: 14px;
  border: none;
  text-align: left;
  color: var(--text-default);
}

.markdown-body :deep(table th) {
  font-weight: bold;
  background: var(--bg-base-tertiary) !important;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--border-brand);
  padding: 0 1em;
  color: var(--text-secondary);
  margin: 8px 0;
}

.markdown-body :deep(hr) {
  height: 1px;
  background: var(--border-neutral-l1);
  border: none;
  margin: 16px 0;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 4px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin: 6px 0;
}

.markdown-body :deep(li) {
  margin: 3px 0;
}

.markdown-body :deep(input[type='checkbox']) {
  margin-right: 6px;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  justify-content: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border-neutral-l1);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-base-secondary);
  border: 1px solid var(--border-neutral-l1);
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: background 0.12s, color 0.12s;
}

.action-btn:hover {
  background: var(--bg-overlay-l1);
  color: var(--text-secondary);
}
</style>
