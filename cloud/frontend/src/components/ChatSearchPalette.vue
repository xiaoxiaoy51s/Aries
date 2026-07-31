<template>
  <Teleport to="body">
    <Transition name="chat-search-fade">
      <div
        v-if="open"
        class="chat-search-overlay"
        @click.self="close"
      >
        <div class="chat-search-palette" role="dialog" aria-modal="true" :aria-label="t('nav.searchOpen')">
          <div class="chat-search-palette-input-row">
            <svg class="chat-search-palette-search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              ref="inputRef"
              v-model="query"
              type="search"
              class="chat-search-palette-input"
              :placeholder="t('nav.searchPalettePlaceholder')"
              autocomplete="off"
              @input="scheduleSearch"
              @keydown="handleKeydown"
            />
          </div>

          <div class="chat-search-palette-divider" />

          <div ref="resultsRef" class="chat-search-palette-results">
            <div v-if="loading" class="chat-search-palette-status">{{ t('nav.searchLoading') }}</div>
            <div v-else-if="error" class="chat-search-palette-status chat-search-palette-error">{{ error }}</div>
            <div v-else-if="query.trim() && results.length === 0 && done" class="chat-search-palette-status">
              {{ t('nav.searchEmpty') }}
            </div>
            <div v-else-if="!query.trim()" class="chat-search-palette-status chat-search-palette-hint">
              {{ t('nav.searchHint') }}
            </div>

            <button
              v-for="(item, index) in results"
              :key="item.match_key || `${item.log_path}-${index}`"
              type="button"
              class="chat-search-palette-item"
              :class="{ active: index === activeIndex }"
              @mouseenter="activeIndex = index"
              @click="selectItem(item)"
            >
              <span class="chat-search-palette-item-type">{{ eventTypeLabel(item) }}</span>
              <span class="chat-search-palette-item-text" v-html="highlightText(displayText(item), query)" />
              <span class="chat-search-palette-item-source" :title="sourceLabel(item)">
                {{ sourceLabel(item) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../i18n'
import api from '../api'
import { highlightHtml } from '../utils/textHighlight'
import './ChatSearchPalette.css'

const { t } = useI18n()

const open = defineModel('open', { type: Boolean, default: false })

const props = defineProps({
  sessions: { type: Array, default: () => [] },
})

const emit = defineEmits(['select-result'])

const inputRef = ref(null)
const resultsRef = ref(null)
const query = ref('')
const results = ref([])
const loading = ref(false)
const error = ref('')
const done = ref(false)
const activeIndex = ref(0)
let searchTimer = null

function eventTypeLabel(item) {
  const type = item?.event_type || 'raw'
  const key = `search.event.${type}`
  const translated = t(key)
  if (translated !== key) return translated
  return item?.event_label || type
}

function highlightText(text, q) {
  return highlightHtml(text, q, 'text-highlight')
}

function displayText(item) {
  const text = (item.snippet || item.text || '').replace(/\s+/g, ' ').trim()
  return text || item.session_title || t('nav.searchUntitled')
}

function sourceLabel(item) {
  if (item.session_id) {
    const session = props.sessions.find(s => s.id === item.session_id)
    if (session?.title) return session.title
  }
  const title = (item.session_title || '').trim()
  if (title) return title
  return t('nav.searchUntitled')
}

function resetState() {
  query.value = ''
  results.value = []
  error.value = ''
  done.value = false
  activeIndex.value = 0
  loading.value = false
}

function close() {
  open.value = false
}

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(runSearch, 280)
}

async function runSearch() {
  const q = query.value.trim()
  done.value = false
  error.value = ''
  activeIndex.value = 0
  if (!q) {
    results.value = []
    loading.value = false
    return
  }
  loading.value = true
  try {
    const res = await api.get('/api/chat/search', { params: { q, limit: 40 } })
    results.value = res.data?.results || []
  } catch (err) {
    results.value = []
    error.value = err.response?.data?.detail || t('nav.searchFailed')
  } finally {
    loading.value = false
    done.value = true
  }
}

function selectItem(item) {
  if (!item.session_id || !item.message_id) {
    close()
    return
  }
  close()
  emit('select-result', {
    session_id: item.session_id,
    message_id: String(item.message_id),
    query: query.value.trim(),
    event_type: item.event_type,
  })
}

function scrollActiveIntoView() {
  nextTick(() => {
    const container = resultsRef.value
    if (!container) return
    const active = container.querySelector('.chat-search-palette-item.active')
    active?.scrollIntoView({ block: 'nearest' })
  })
}

function handleKeydown(e) {
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!results.value.length) return
    activeIndex.value = (activeIndex.value + 1) % results.value.length
    scrollActiveIntoView()
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (!results.value.length) return
    activeIndex.value = (activeIndex.value - 1 + results.value.length) % results.value.length
    scrollActiveIntoView()
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    const item = results.value[activeIndex.value]
    if (item) selectItem(item)
  }
}

watch(open, (val) => {
  if (val) {
    nextTick(() => inputRef.value?.focus())
  } else {
    resetState()
  }
})

function onGlobalKeydown(e) {
  const isMac = navigator.platform.toUpperCase().includes('MAC')
  const mod = isMac ? e.metaKey : e.ctrlKey
  if (mod && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
}

onMounted(() => {
  document.addEventListener('keydown', onGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onGlobalKeydown)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>
