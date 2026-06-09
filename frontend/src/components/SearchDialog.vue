<template>
  <Teleport to="body">
    <div v-if="visible" class="search-overlay" @click.self="$emit('close')">
      <div class="search-modal">
        <div class="search-header">
          <input
            ref="searchInput"
            v-model="query"
            type="text"
            class="search-input"
            placeholder="搜索对话..."
            @keydown.escape="$emit('close')"
          />
        </div>
        <div class="search-results">
          <div v-if="!query" class="search-empty">输入关键词搜索对话</div>
          <div v-else-if="results.length === 0" class="search-empty">无结果</div>
          <div
            v-for="r in results"
            :key="r.id"
            class="search-result-item"
            @click="$emit('select', r.id)"
          >
            {{ r.title || '未命名对话' }}
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { listProjects } from '@/api/sessions'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: []; select: [id: string] }>()

const query = ref('')
const results = ref<{ id: string; title: string }[]>([])
const searchInput = ref<HTMLInputElement>()

watch(() => props.visible, async (val) => {
  if (val) {
    query.value = ''
    results.value = []
    await nextTick()
    searchInput.value?.focus()
  }
})

watch(query, async (q) => {
  if (!q.trim()) {
    results.value = []
    return
  }
  try {
    const data = await listProjects()
    const all: { id: string; title: string }[] = []
    for (const p of data.projects || []) {
      for (const s of p.sessions || []) {
        if ((s.title || '').toLowerCase().includes(q.toLowerCase())) {
          all.push({ id: s.session_id, title: s.title })
        }
      }
    }
    results.value = all.slice(0, 20)
  } catch {
    results.value = []
  }
})
</script>

<style scoped>
.search-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 80px;
  z-index: 2000;
}

.search-modal {
  width: 480px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.search-header {
  padding: 16px;
}

.search-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: var(--bg);
  color: var(--text);
}

.search-input:focus {
  border-color: var(--border-strong);
}

.search-results {
  max-height: 300px;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.search-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.search-result-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
}

.search-result-item:hover {
  background: var(--accent-hover);
}
</style>
