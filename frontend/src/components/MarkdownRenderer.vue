<template>
  <div class="markdown-content">
    <!-- 渲染后的 Markdown（带有 github-markdown-css 的 markdown-body 类） -->
    <div
      ref="markdownContainer"
      class="markdown-body"
      :style="{
        fontSize: fontSize + 'px',
        color: textColor,
      }"
      v-html="sanitizedHtml"
    />

    <!-- 操作按钮区域 -->
    <div v-if="showActions && content && !isStreaming" class="action-buttons">
      <button class="action-btn" @click="copyAllContent" title="复制">
        <svg v-if="copiedAll" t="1782397384882" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="" p-id="19463" width="12" height="12"><path d="M833.33 767.96h-91.9c-21.73 0-39.34-17.6-39.34-39.34s17.62-39.34 39.34-39.34h91.9c8.82 0 15.98-7.18 15.98-15.98V193.8c0-8.8-7.17-15.98-15.98-15.98H353.84c-8.82 0-15.98 7.18-15.98 15.98v90.86c0 21.75-17.62 39.34-39.34 39.34s-39.34-17.6-39.34-39.34V193.8c0-52.21 42.47-94.67 94.67-94.67h479.49c52.19 0 94.67 42.45 94.67 94.67v479.49c-0.01 52.21-42.49 94.67-94.68 94.67z" fill="#333333" p-id="19464"></path><path d="M675.96 925.33H196.47c-52.19 0-94.67-42.45-94.67-94.67V351.17c0-52.21 42.47-94.67 94.67-94.67h479.49c52.19 0 94.67 42.45 94.67 94.67v479.49c-0.01 52.22-42.48 94.67-94.67 94.67zM196.47 335.19c-8.82 0-15.98 7.18-15.98 15.98v479.49c0 8.8 7.17 15.98 15.98 15.98h479.49c8.82 0 15.98-7.18 15.98-15.98V351.17c0-8.8-7.17-15.98-15.98-15.98H196.47z" fill="#333333" p-id="19465"></path></svg>
        <svg v-else <svg t="1782397489476" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="20511" width="12" height="12"><path d="M896 288a32 32 0 0 0-54.656-22.592L418.656 688.096 184.992 396l-0.112 0.08a31.872 31.872 0 1 0-49.76 39.824l-0.112 0.096 256 320 0.112-0.08a31.872 31.872 0 0 0 47.52 2.688l447.952-447.952c5.824-5.808 9.408-13.808 9.408-22.656z" fill="#231815" p-id="20512"></path></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import 'github-markdown-css/github-markdown.css'
import DOMPurify from 'dompurify'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = withDefaults(defineProps<{
  content: string
  textColor?: string
  fontSize?: number
  showActions?: boolean
  isStreaming?: boolean
}>(), {
  textColor: '#1a1a1a',
  fontSize: 15,
  showActions: true,
  isStreaming: false
})

const copiedAll = ref(false)
let copyResetTimer: ReturnType<typeof setTimeout> | null = null

onBeforeUnmount(() => {
  if (copyResetTimer) clearTimeout(copyResetTimer)
})

// ── markdown-it 实例（单例） ──────────────────────────────
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    const codeContent = md.utils.escapeHtml(str)
    const langLabel = md.utils.escapeHtml(lang || 'code')
    const copyBtn = `<button class="copy-btn" data-copy-btn title="复制" style="display:flex;align-items:center;justify-content:center;padding:4px;background:none;border:none;cursor:pointer;font-size:13px;color:inherit"><svg t="1780846643473" class="icon" viewBox="0 0 1024 1024" width="11" height="11"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="#000000"></path></svg></button>`
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, {
          language: lang,
          ignoreIllegals: true,
        }).value
        return `<div class="code-block-wrapper"><div class="code-header"><span class="code-lang">${langLabel}</span>${copyBtn}</div><pre class="hljs"><code>${highlighted}</code></pre></div>`
      } catch (_) {}
    }
    return `<div class="code-block-wrapper"><div class="code-header"><span class="code-lang">${langLabel}</span>${copyBtn}</div><pre class="hljs"><code>${codeContent}</code></pre></div>`
  },
})

// ── KaTeX 插件：渲染 $$...$$ 和 $...$ ─────────────────────
const defaultFence = md.renderer.rules.fence
md.renderer.rules.fence = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : ''
  if (info === 'math' || info === 'latex') {
    try {
      return katex.renderToString(token.content, {
        displayMode: true,
        throwOnError: false,
      })
    } catch (_) {
      return `<pre>${md.utils.escapeHtml(token.content)}</pre>`
    }
  }
  return defaultFence ? defaultFence(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options)
}

// 行内公式 $...$ 交给 markdown-it 的 inline 规则
const defaultInline = md.renderer.rules.text
md.renderer.rules.text = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  const text = token.content
  if (text && text.includes('$')) {
    // 用 katex 替换行内公式
    const rendered = text.replace(/(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/g, (_m, formula) => {
      try {
        return katex.renderToString(formula.trim(), {
          displayMode: false,
          throwOnError: false,
        })
      } catch (_) {
        return _m
      }
    })
    if (rendered !== text) return rendered
  }
  return defaultInline ? defaultInline(tokens, idx, options, env, self) : md.utils.escapeHtml(text)
}

// ── 渲染管道 ──────────────────────────────────────────
function renderMarkdownToHtml(raw: string): string {
  if (!raw) return ''
  // 预提取代码块，避免 KaTeX 干扰
  let html = raw
  // 块级公式
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (_m, formula) => {
    try {
      return katex.renderToString(formula.trim(), {
        displayMode: true,
        throwOnError: false,
      })
    } catch (_) {
      return _m
    }
  })
  const rendered = md.render(html)

  // DOMPurify 过滤 XSS
  return DOMPurify.sanitize(rendered, {
    ADD_ATTR: ['target', 'rel'],
    ADD_TAGS: ['use'],
  })
}

const sanitizedHtml = computed(() => renderMarkdownToHtml(props.content))

// 代码块复制：用事件委托绑定，避免 inline onclick 被转义
const markdownContainer = ref<HTMLElement | null>(null)
const copiedCodeBtn = ref<HTMLElement | null>(null)
let codeCopyResetTimer: ReturnType<typeof setTimeout> | null = null

async function onCopyCodeClick(e: Event) {
  const path = (e as any).composedPath ? (e as any).composedPath() : []
  const btn = path.find((el: any) => el instanceof Element && el.hasAttribute && el.hasAttribute('data-copy-btn')) as HTMLElement | null
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
        copiedCodeBtn.value.innerHTML = '<svg t="1780846643473" class="icon" viewBox="0 0 1024 1024" width="11" height="11"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="#000000"></path></svg>'
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
    copyResetTimer = setTimeout(() => {
      copiedAll.value = false
    }, 1500)
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
}

.markdown-body :deep(.katex) {
  font-size: 1.05em;
}

/* 代码块样式 */
.markdown-body :deep(.code-block-wrapper) {
  background-color: #f4f4f5;
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
  background-color: #e4e4e7;
  min-height: 24px;
}

.markdown-body :deep(.code-lang) {
  font-size: 11px;
  color: #71717a;
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
  color: #52525b;
}

.markdown-body :deep(.copy-btn:hover) {
  color: #18181b;
}

.markdown-body :deep(pre) {
  padding: 10px;
  overflow-x: auto;
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
  color: #27272a;
}

.markdown-body :deep(code:not(pre code)) {
  background: rgba(110, 118, 129, 0.10);
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
  border-collapse: collapse;
  border: none;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 8px;
  font-size: 14px;
  border: none;
  text-align: left;
}

.markdown-body :deep(th) {
  font-weight: bold;
  background: var(--bg-secondary);
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--accent);
  padding: 0 1em;
  color: var(--text-secondary);
  margin: 8px 0;
}

.markdown-body :deep(hr) {
  height: 1px;
  background: var(--border);
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
  border-top: 1px solid var(--border);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}
</style>