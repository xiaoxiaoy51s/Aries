<template>
  <div class="markdown-content">
    <div v-for="(block, index) in parsedBlocks" :key="index">
      <!-- 代码块 -->
      <div v-if="block.type === 'code'" class="code-block">
        <div class="code-header">
          <span class="code-lang">{{ block.lang || 'code' }}</span>
          <button class="copy-btn" @click="copyCode(block.content, index)" :title="copiedIndex === index ? '已复制' : '复制'">
            <svg v-if="copiedIndex === index" t="1780846687143" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="6050" width="11" height="11"><path d="M896 288a32 32 0 0 0-54.656-22.592L418.656 688.096 184.992 396l-0.112 0.08a31.872 31.872 0 1 0-49.76 39.824l-0.112 0.096 256 320 0.112-0.08a31.872 31.872 0 0 0 47.52 2.688l447.952-447.952c5.824-5.808 9.408-13.808 9.408-22.656z" fill="#231815" p-id="6051"></path></svg>
            <svg v-else t="1780846643473" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5009" width="11" height="11"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="#000000" p-id="5010"></path><path d="M875.52 745.984h-52.736V220.672H297.984V168.448H875.52z" fill="#000000" p-id="5011"></path></svg>
          </button>
        </div>
        <div class="code-content">
          <pre class="code-text">{{ block.content }}</pre>
        </div>
      </div>
      
      <!-- 表格 -->
      <div v-else-if="block.type === 'table'" class="table-block">
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th v-for="(cell, cellIndex) in block.headers" :key="cellIndex" :style="{ textAlign: block.aligns[cellIndex] || 'left' }">
                  <span v-if="getCellImages(cell).length > 0">
                    <img v-for="(img, imgIdx) in getCellImages(cell)" :key="imgIdx" :src="img.url" class="cell-image" @click="previewImage(img.url)" />
                  </span>
                  <span v-else v-html="renderMarkdown(cell)"></span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
                <td v-for="(cell, cellIndex) in row" :key="cellIndex" :style="{ textAlign: block.aligns[cellIndex] || 'left' }">
                  <span v-if="getCellImages(cell).length > 0">
                    <img v-for="(img, imgIdx) in getCellImages(cell)" :key="imgIdx" :src="img.url" class="cell-image" @click="previewImage(img.url)" />
                  </span>
                  <span v-else v-html="renderMarkdown(cell)"></span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 图片网格 -->
      <div v-else-if="block.type === 'image-grid'" class="image-grid-block">
        <div class="image-grid">
          <div v-for="(img, imgIndex) in block.images" :key="imgIndex" class="image-grid-item" @click="previewImage(img.url)">
            <img class="grid-image" :src="img.url" loading="lazy" />
            <span v-if="img.title" class="image-title">{{ img.title }}</span>
          </div>
        </div>
      </div>

      <!-- 普通文本 -->
      <div v-else class="text-block">
        <!-- 如果有下载链接，使用自定义渲染 -->
        <template v-if="block.hasDownloadLink">
          <template v-for="(part, pIndex) in block.parts" :key="pIndex">
            <!-- 下载链接组件 -->
            <a v-if="part.type === 'download'" class="file-download-wrapper" :href="part.url" download>
              <span class="file-download-icon">📄</span>
              <span class="file-download-name">{{ part.fileName }}</span>
              <span class="file-download-btn">下载</span>
            </a>
            <!-- 普通文本 -->
            <span v-else class="rich-text-content" v-html="part.content"></span>
          </template>
        </template>
        <!-- 没有下载链接，正常渲染 -->
        <span v-else class="rich-text-content" v-html="renderMarkdown(block.content)"></span>
      </div>
    </div>
    
    <!-- 操作按钮区域 -->
    <div v-if="showActions && content && !isStreaming" class="action-buttons">
      <button class="action-btn" @click="copyAllContent" title="复制">
        <svg v-if="copiedAll" t="1780846687143" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="6050" width="12" height="12"><path d="M896 288a32 32 0 0 0-54.656-22.592L418.656 688.096 184.992 396l-0.112 0.08a31.872 31.872 0 1 0-49.76 39.824l-0.112 0.096 256 320 0.112-0.08a31.872 31.872 0 0 0 47.52 2.688l447.952-447.952c5.824-5.808 9.408-13.808 9.408-22.656z" fill="#231815" p-id="6051"></path></svg>
        <svg v-else t="1780846643473" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5009" width="12" height="12"><path d="M761.344 867.328H157.696v-604.16h603.648v604.16zM209.92 814.592h498.688V315.904H209.92v498.688z" fill="#000000" p-id="5010"></path><path d="M875.52 745.984h-52.736V220.672H297.984V168.448H875.52z" fill="#000000" p-id="5011"></path></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
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

const copiedIndex = ref(-1)
const copiedAll = ref(false)
let copyResetTimer: ReturnType<typeof setTimeout> | null = null

const textColor = computed(() => props.textColor || '#1a1a1a')
const fontSize = computed(() => props.fontSize || 15)

onBeforeUnmount(() => {
  if (copyResetTimer) clearTimeout(copyResetTimer)
})

function parseMarkdown(text: string) {
  const blocks: any[] = []
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g
  const tableRegex = /^\|.+\|[\r\n]+\|[-:| ]+\|[\r\n]+(\|.+\|[\r\n]*)+/gm
  
  let lastIndex = 0
  let match

  // 先处理代码块
  const codeMatches: any[] = []
  while ((match = codeBlockRegex.exec(text)) !== null) {
    codeMatches.push({
      type: 'code',
      start: match.index,
      end: match.index + match[0].length,
      lang: match[1].trim(),
      content: match[2].trim()
    })
  }

  // 处理表格
  const tableMatches: any[] = []
  let tableMatch
  while ((tableMatch = tableRegex.exec(text)) !== null) {
    tableMatches.push({
      type: 'table',
      start: tableMatch.index,
      end: tableMatch.index + tableMatch[0].length,
      raw: tableMatch[0].trim()
    })
  }

  // 合并并排序所有匹配
  const allMatches = [...codeMatches, ...tableMatches].sort((a, b) => a.start - b.start)

  // 构建块
  allMatches.forEach(m => {
    // 添加匹配之前的文本
    if (m.start > lastIndex) {
      const textContent = text.substring(lastIndex, m.start).trim()
      if (textContent) {
        blocks.push({
          type: 'text',
          content: textContent
        })
      }
    }

    // 添加匹配的块
    if (m.type === 'code') {
      blocks.push({
        type: 'code',
        lang: m.lang,
        content: m.content
      })
    } else if (m.type === 'table') {
      const parsed = parseTable(m.raw)
      blocks.push(parsed)
    }

    lastIndex = m.end
  })

  // 添加剩余的文本
  if (lastIndex < text.length) {
    const textContent = text.substring(lastIndex).trim()
    if (textContent) {
      const downloadRegex = /(?:https?:\/\/[^\/]+)?(\/api\/files\/download\/([\d-]+\/[^?]+)\?([^\s<>*`]+))/g
      const hasDownloadLink = downloadRegex.test(textContent)
      
      if (hasDownloadLink) {
        const parts: any[] = []
        let lastMatchEnd = 0
        let match2
        
        downloadRegex.lastIndex = 0
        
        while ((match2 = downloadRegex.exec(textContent)) !== null) {
          if (match2.index > lastMatchEnd) {
            const beforeText = textContent.substring(lastMatchEnd, match2.index).trim()
            if (beforeText) {
              parts.push({
                type: 'text',
                content: renderMarkdown(beforeText)
              })
            }
          }
          
          const fullPath = match2[1]
          const filePath = match2[2]
          const fileName = filePath.split('/').pop() || '未知文件'
          const downloadUrl = match2[0].startsWith('http') ? match2[0] : `${window.location.origin}${fullPath}`
          
          parts.push({
            type: 'download',
            url: downloadUrl,
            fileName: fileName
          })
          
          lastMatchEnd = match2.index + match2[0].length
        }
        
        if (lastMatchEnd < textContent.length) {
          const afterText = textContent.substring(lastMatchEnd).trim()
          if (afterText) {
            parts.push({
              type: 'text',
              content: renderMarkdown(afterText)
            })
          }
        }
        
        blocks.push({
          type: 'text',
          hasDownloadLink: true,
          parts: parts
        })
      } else {
        blocks.push({
          type: 'text',
          content: textContent
        })
      }
    }
  }

  if (blocks.length === 0) {
    blocks.push({
      type: 'text',
      content: text
    })
  }

  return extractImageBlocks(blocks)
}

function extractImageBlocks(blocks: any[]) {
  const result: any[] = []
  let currentImages: any[] = []

  for (const block of blocks) {
    if (block.type === 'text' && !block.hasDownloadLink) {
      const imageData = extractImagesFromText(block.content)

      if (imageData.images.length > 0) {
        if (imageData.beforeText) {
          result.push({
            type: 'text',
            content: imageData.beforeText
          })
        }

        currentImages.push(...imageData.images)

        if (imageData.afterText) {
          if (currentImages.length > 0) {
            result.push({
              type: 'image-grid',
              images: currentImages
            })
            currentImages = []
          }
          result.push({
            type: 'text',
            content: imageData.afterText
          })
        }
      } else {
        if (currentImages.length > 0) {
          result.push({
            type: 'image-grid',
            images: currentImages
          })
          currentImages = []
        }
        result.push(block)
      }
    } else {
      if (currentImages.length > 0) {
        result.push({
          type: 'image-grid',
          images: currentImages
        })
        currentImages = []
      }
      result.push(block)
    }
  }

  if (currentImages.length > 0) {
    result.push({
      type: 'image-grid',
      images: currentImages
    })
  }

  return result
}

function extractImagesFromText(text: string) {
  const imageRegex = /(https?:\/\/[^\s<>"'`]+\.(?:jpg|jpeg|png|gif|webp|svg|bmp))(?:\?[^\s<>"'`]*)?/gi
  const images: any[] = []
  let beforeText = text
  let afterText = ''

  let match
  let lastIndex = 0
  const matches: any[] = []

  while ((match = imageRegex.exec(text)) !== null) {
    matches.push({
      url: match[1],
      index: match.index,
      length: match[0].length
    })
  }

  if (matches.length === 0) {
    return { images: [], beforeText: text, afterText: '' }
  }

  const firstMatch = matches[0]
  const lastMatch = matches[matches.length - 1]

  beforeText = text.substring(0, firstMatch.index).trim()
  afterText = text.substring(lastMatch.index + lastMatch.length).trim()

  for (const m of matches) {
    let title = ''
    const beforeChunk = text.substring(lastIndex, m.index)
    const titleMatch = beforeChunk.match(/\[([^\]]+)\]\s*$/)
    if (titleMatch) {
      title = titleMatch[1]
    }

    images.push({
      url: m.url,
      title: title
    })
    lastIndex = m.index + m.length
  }

  return { images, beforeText, afterText }
}

function getCellImages(cell: string) {
  if (!cell) return []
  const images: any[] = []
  const imageRegex = /(https?:\/\/[^\s<>"'`]+\.(?:jpg|jpeg|png|gif|webp|svg|bmp))(?:\?[^\s<>"'`]*)?/gi
  let match
  while ((match = imageRegex.exec(cell)) !== null) {
    images.push({
      url: match[1],
      title: ''
    })
  }
  return images
}

function parseTable(tableText: string) {
  const lines = tableText.trim().split(/[\r\n]+/)
  if (lines.length < 2) {
    return { type: 'text', content: tableText }
  }
  
  const headerLine = lines[0]
  const separatorLine = lines[1]
  const bodyLines = lines.slice(2)
  
  const headers = headerLine.split('|').filter(cell => cell.trim()).map(cell => cell.trim())
  const separators = separatorLine.split('|').filter(cell => cell.trim())
  const aligns = separators.map(sep => getTableAlign(sep))
  
  const rows = bodyLines.map(line => {
    return line.split('|').filter(cell => cell.trim()).map(cell => cell.trim())
  }).filter(row => row.length > 0)
  
  return {
    type: 'table',
    headers,
    aligns,
    rows
  }
}

function renderLatex(latex: string, displayMode = false) {
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      strict: false,
      output: 'html'
    })
  } catch (e) {
    console.error('LaTeX render error:', e)
    return latex
  }
}

function renderMarkdown(text: string) {
  let html = text
  
  html = html.replace(/<br\s*\/?>/gi, '\n')
  
  const blockFormulas: string[] = []
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (match, formula) => {
    const index = blockFormulas.length
    blockFormulas.push(formula.trim())
    return `__BLOCK_FORMULA_${index}__`
  })
  
  const inlineFormulas: string[] = []
  html = html.replace(/(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)/g, (match, formula) => {
    const index = inlineFormulas.length
    inlineFormulas.push(formula.trim())
    return `__INLINE_FORMULA_${index}__`
  })

  // 链接占位符化：在 escape `<>&` 之前提取，避免 url 中的字符被破坏
  // 1) markdown 显式链接 [text](url)
  // 2) 裸 URL（http/https 开头）
  const linkTokens: { text: string; url: string }[] = []
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, text: string, url: string) => {
    const i = linkTokens.length
    linkTokens.push({ text, url })
    return `__LINK_TOKEN_${i}__`
  })
  html = html.replace(/(^|[\s(<])((?:https?:\/\/)[^\s<>()]+)/g, (_m, prefix: string, url: string) => {
    const i = linkTokens.length
    linkTokens.push({ text: url, url })
    return `${prefix}__LINK_TOKEN_${i}__`
  })

  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  const tc = textColor.value
  const fs = fontSize.value

  // Codex 风格标题层级：相对正文 1em / 1.125em / 1.25em / 1.5em
  html = html.replace(/^####\s+(.+)$/gm, `<h4 style="font-size:${fs}px;font-weight:600;margin:14px 0 6px;color:${tc};line-height:1.4;">$1</h4>`)
  html = html.replace(/^###\s+(.+)$/gm, `<h3 style="font-size:${Math.round(fs * 1.125)}px;font-weight:600;margin:16px 0 6px;color:${tc};line-height:1.4;">$1</h3>`)
  html = html.replace(/^##\s+(.+)$/gm, `<h2 style="font-size:${Math.round(fs * 1.25)}px;font-weight:600;margin:20px 0 8px;color:${tc};line-height:1.35;">$1</h2>`)
  html = html.replace(/^#\s+(.+)$/gm, `<h1 style="font-size:${Math.round(fs * 1.5)}px;font-weight:600;margin:24px 0 10px;color:${tc};line-height:1.3;letter-spacing:-0.01em;">$1</h1>`)
  
  html = html.replace(/\*\*(.*?)\*\*/g, `<strong style="color:${tc};">$1</strong>`)
  html = html.replace(/\*(.*?)\*/g, `<em style="color:${tc};">$1</em>`)
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(110,118,129,0.10);padding:2px 6px;border-radius:5px;font-family:ui-monospace,SFMono-Regular,SF Mono,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace;font-size:0.875em;color:#1f2328;font-weight:500;">$1</code>')
  // 段落处理：连续两个以上换行 → 段落分隔（轻微间距），单换行 → 段内换行（无空行）
  html = html.replace(/\n{2,}/g, '</p><p style="margin:6px 0;">')
  html = html.replace(/\n/g, '<br>')
  html = `<p style="margin:6px 0;">${html}</p>`
  html = html.replace(/<p[^>]*>\s*<\/p>/g, '') // 移除空段落
  html = html.replace(/^(\d+)\.\s+(.+)$/gm, `<div style="margin:4px 0;padding-left:12px;"><span style="color:${tc};margin-right:4px;">$1.</span><span style="color:${tc};">$2</span></div>`)
  html = html.replace(/^[-*]\s+(.+)$/gm, `<div style="margin:4px 0;padding-left:12px;"><span style="color:${tc};margin-right:4px;">•</span><span style="color:${tc};">$1</span></div>`)
  
  inlineFormulas.forEach((formula, i) => {
    const rendered = renderLatex(formula, false)
    html = html.replace(`__INLINE_FORMULA_${i}__`, rendered)
  })
  
  blockFormulas.forEach((formula, i) => {
    const rendered = renderLatex(formula, true)
    html = html.replace(`__BLOCK_FORMULA_${i}__`, rendered)
  })

  // 还原链接占位符为 <a>（浅蓝色 + 下划线 + 鼠标手型；点击由父级事件委托接管）
  linkTokens.forEach((tk, i) => {
    const safeUrl = tk.url.replace(/"/g, '&quot;')
    const safeText = tk.text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    const anchor = `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" style="color:#3b82f6;text-decoration:underline;cursor:pointer;word-break:break-all;">${safeText}</a>`
    html = html.split(`__LINK_TOKEN_${i}__`).join(anchor)
  })

  return html
}

function getTableAlign(separator: string) {
  if (!separator) return 'left'
  if (separator.trim().startsWith(':') && separator.trim().endsWith(':')) return 'center'
  if (separator.trim().endsWith(':')) return 'right'
  return 'left'
}

async function copyCode(code: string, index: number) {
  try {
    await navigator.clipboard.writeText(code)
    copiedIndex.value = index
    setTimeout(() => {
      copiedIndex.value = -1
    }, 2000)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}

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

function previewImage(url: string) {
  window.open(url, '_blank')
}

const parsedBlocks = computed(() => {
  if (!props.content) return []
  return parseMarkdown(props.content)
})
</script>

<style scoped>
.markdown-content {
  width: 100%;
}

.text-block {
  margin-bottom: 8px;
}

.rich-text-content {
  font-size: v-bind('fontSize + "px"');
  line-height: 1.65;
  letter-spacing: -0.003em;
  color: v-bind('textColor');
  font-family: 'Inter', 'Noto Sans SC', ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.rich-text-content :deep(p) {
  margin: 6px 0;
}

.rich-text-content :deep(p:first-child) {
  margin-top: 0;
}

.rich-text-content :deep(p:last-child) {
  margin-bottom: 0;
}

.rich-text-content :deep(a) {
  color: #3b82f6 !important;
  text-decoration: underline;
  cursor: pointer;
  word-break: break-all;
}

.rich-text-content :deep(a:hover) {
  color: #2563eb !important;
}

.rich-text-content :deep(.katex-display) {
  margin: 6px 0;
  overflow-x: auto;
}

.rich-text-content :deep(.katex) {
  font-size: 14px;
}

.code-block {
  background-color: var(--bg-panel);
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
  border: 1px solid var(--border);
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 10px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  min-height: 24px;
}

.code-lang {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: lowercase;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
}

.code-content {
  padding: 10px;
  overflow-x: auto;
}

.code-text {
  font-size: 13px;
  line-height: 1.55;
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-feature-settings: 'liga' 0;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.table-block {
  margin: 8px 0;
  overflow-x: auto;
}

.table-container {
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.table-container table {
  width: 100%;
  border-collapse: collapse;
}

.table-container th,
.table-container td {
  padding: 8px;
  font-size: 14px;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.table-container th {
  font-weight: bold;
  background: var(--bg-secondary);
}

.table-container th:last-child,
.table-container td:last-child {
  border-right: none;
}

.table-container tr:last-child td {
  border-bottom: none;
}

.cell-image {
  max-width: 80px;
  max-height: 60px;
  border-radius: 4px;
  cursor: pointer;
}

.image-grid-block {
  margin: 8px 0;
}

.image-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-grid-item {
  flex: 0 0 calc(33.333% - 6px);
  max-width: calc(33.333% - 6px);
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-secondary);
  cursor: pointer;
}

.grid-image {
  width: 100%;
  height: 120px;
  object-fit: cover;
  display: block;
}

.image-title {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 12px;
  padding: 4px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-download-wrapper {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 4px 0;
  text-decoration: none;
  color: var(--text);
  cursor: pointer;
}

.file-download-icon {
  margin-right: 8px;
}

.file-download-name {
  flex: 1;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-download-btn {
  padding: 4px 12px;
  background: var(--accent);
  color: #fff;
  border-radius: 4px;
  margin-left: 8px;
  font-size: 12px;
}

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

.action-icon {
  font-size: 14px;
}
</style>
