export function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function escapeRegex(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function highlightHtml(text, query, className = 'text-highlight') {
  const raw = String(text ?? '')
  const q = String(query ?? '').trim()
  if (!raw || !q) return escapeHtml(raw)
  const pattern = new RegExp(escapeRegex(q), 'gi')
  let result = ''
  let lastIndex = 0
  for (const match of raw.matchAll(pattern)) {
    const start = match.index ?? 0
    result += escapeHtml(raw.slice(lastIndex, start))
    result += `<mark class="${className}">${escapeHtml(match[0])}</mark>`
    lastIndex = start + match[0].length
  }
  result += escapeHtml(raw.slice(lastIndex))
  return result
}
