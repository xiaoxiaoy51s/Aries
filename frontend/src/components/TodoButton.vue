<template>
  <div class="todo-button-root">
    <button
      type="button"
      class="todo-toggle"
      :class="{ 'has-todos': hasTodos }"
      title="任务清单"
      aria-label="任务清单"
      @click="togglePanel"
    >
      <svg class="todo-toggle-icon" width="18" height="18" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
        <path d="M774.656 774.656a371.2 371.2 0 1 0-524.8 0 371.2 371.2 0 0 0 524.8 0zM819.2 819.2a435.2 435.2 0 1 1 0-614.4 435.2 435.2 0 0 1 0 614.4z"/>
        <path d="M694.272 366.592a32.256 32.256 0 1 1 45.056 45.056l-249.856 249.856a37.376 37.376 0 0 1-51.2 0l-142.336-141.312a32.256 32.256 0 1 1 45.056-45.056L460.8 597.504z"/>
      </svg>
      <span v-if="hasTodos" class="todo-badge">{{ todoCount }}</span>
    </button>

    <Transition name="todo-panel">
      <div v-if="panelOpen" class="todo-panel">
        <div class="todo-header">
          <span class="todo-title">任务清单</span>
          <div class="todo-actions">
            <button
              v-if="hasTodos"
              type="button"
              class="todo-clear"
              title="清除任务清单"
              @click="handleClear"
            >
              清除
            </button>
            <button type="button" class="todo-close" title="关闭" @click="panelOpen = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>
        <div v-if="!hasTodos" class="todo-empty">暂无任务</div>
        <ul v-else class="todo-list">
          <li
            v-for="todo in sortedTodos"
            :key="todo.id"
            class="todo-item"
            :class="`todo-status-${todo.status}`"
          >
            <span class="todo-icon">
              <!-- completed -->
              <svg v-if="todo.status === 'completed'" width="18" height="18" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
                <path d="M774.656 774.656a371.2 371.2 0 1 0-524.8 0 371.2 371.2 0 0 0 524.8 0zM819.2 819.2a435.2 435.2 0 1 1 0-614.4 435.2 435.2 0 0 1 0 614.4z"/>
                <path d="M694.272 366.592a32.256 32.256 0 1 1 45.056 45.056l-249.856 249.856a37.376 37.376 0 0 1-51.2 0l-142.336-141.312a32.256 32.256 0 1 1 45.056-45.056L460.8 597.504z"/>
              </svg>
              <!-- in_progress -->
              <svg v-else-if="todo.status === 'in_progress'" width="18" height="18" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
                <path d="M509.761 798.429c33.04 0 59.823 26.767 59.823 59.785 0 33.019-26.784 59.786-59.823 59.786-33.04 0-59.823-26.767-59.823-59.786 0-33.018 26.784-59.785 59.823-59.785zM270.47 681.157c39.393 0 71.327 31.914 71.327 71.283 0 39.368-31.934 71.283-71.327 71.283s-71.327-31.915-71.327-71.283c0-39.369 31.934-71.283 71.327-71.283z m478.584 36.79c26.686 0 48.319 21.62 48.319 48.29 0 26.668-21.633 48.288-48.319 48.288-26.686 0-48.318-21.62-48.318-48.289s21.632-48.288 48.318-48.288z m-574.07-273.634c46.381 0 83.982 37.577 83.982 83.93 0 46.353-37.6 83.93-83.983 83.93-46.382 0-83.982-37.577-83.982-83.93 0-46.353 37.6-83.93 83.982-83.93z m660.353 45.99c19.697 0 35.664 15.956 35.664 35.64 0 19.685-15.967 35.642-35.664 35.642-19.696 0-35.663-15.957-35.663-35.641 0-19.685 15.967-35.642 35.663-35.642zM269.32 193.672c52.735 0 95.486 42.724 95.486 95.427 0 52.703-42.75 95.427-95.486 95.427-52.736 0-95.487-42.724-95.487-95.427 0-52.703 42.75-95.427 95.487-95.427zM509.76 81c66.079 0 119.646 53.534 119.646 119.571 0 66.038-53.567 119.572-119.646 119.572-66.079 0-119.646-53.534-119.646-119.572C390.115 134.534 443.682 81 509.761 81zM741 267.255c13.343 0 24.16 10.81 24.16 24.145 0 13.334-10.817 24.144-24.16 24.144s-24.16-10.81-24.16-24.144c0-13.335 10.817-24.145 24.16-24.145z"/>
              </svg>
              <!-- pending -->
              <svg v-else width="18" height="18" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
                <path d="M512 128A384 384 0 1 1 128 512 384 384 0 0 1 512 128m0-64A448 448 0 1 0 960 512 448 448 0 0 0 512 64z"/>
              </svg>
            </span>
            <span class="todo-content">{{ todo.content }}</span>
            <span class="todo-priority">{{ todo.priority }}</span>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getTodos, clearTodos } from '@/api/todos'

interface Todo {
  id: string
  content: string
  priority: 'high' | 'medium' | 'low'
  status: 'pending' | 'in_progress' | 'completed'
}

const todos = ref<Todo[]>([])
const panelOpen = ref(false)
const currentSessionId = ref('')

const hasTodos = computed(() => todos.value.length > 0)
const todoCount = computed(() => todos.value.length)

const statusOrder = {
  in_progress: 0,
  pending: 1,
  completed: 2,
}

const sortedTodos = computed(() => {
  return [...todos.value].sort((a, b) => {
    const oa = statusOrder[a.status] ?? 1
    const ob = statusOrder[b.status] ?? 1
    if (oa !== ob) return oa - ob
    return a.id.localeCompare(b.id)
  })
})

function togglePanel() {
  panelOpen.value = !panelOpen.value
}

async function handleClear() {
  if (!currentSessionId.value) {
    todos.value = []
    return
  }
  try {
    await clearTodos(currentSessionId.value)
    todos.value = []
  } catch (e) {
    console.error('清除任务清单失败', e)
  }
}

function onTodoUpdate(e: Event) {
  const detail = (e as CustomEvent).detail as { sessionId: string; todos: Todo[] }
  if (!detail) return
  currentSessionId.value = detail.sessionId || currentSessionId.value
  todos.value = detail.todos || []
}

async function onLoadSession(e: Event) {
  const id = (e as CustomEvent).detail as string
  if (id) {
    currentSessionId.value = id
    try {
      todos.value = await getTodos(id)
    } catch {
      todos.value = []
    }
  }
}

function onNewChat() {
  currentSessionId.value = ''
  todos.value = []
}

function onOpenTodoPanel() {
  panelOpen.value = true
}

onMounted(() => {
  window.addEventListener('aries:todo-update', onTodoUpdate)
  window.addEventListener('aries:load-session', onLoadSession)
  window.addEventListener('aries:new-chat', onNewChat)
  window.addEventListener('aries:open-todo-panel', onOpenTodoPanel)
})

onUnmounted(() => {
  window.removeEventListener('aries:todo-update', onTodoUpdate)
  window.removeEventListener('aries:load-session', onLoadSession)
  window.removeEventListener('aries:new-chat', onNewChat)
  window.removeEventListener('aries:open-todo-panel', onOpenTodoPanel)
})
</script>

<style scoped>
.todo-button-root {
  position: relative;
}

.todo-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-panel);
  transition: background 0.15s, color 0.15s;
  position: relative;
}

.todo-toggle:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.todo-toggle.has-todos {
  color: var(--text);
}

.todo-toggle-icon {
  fill: currentColor;
}

.todo-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}

.todo-panel {
  position: absolute;
  top: 44px;
  right: 0;
  width: 320px;
  max-height: 420px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-panel);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.todo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.todo-title {
  font-weight: 600;
  font-size: 14px;
}

.todo-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.todo-clear {
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.todo-clear:hover {
  background: #fee2e2;
  color: #dc2626;
}

.todo-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.todo-close:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.todo-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.todo-list {
  list-style: none;
  overflow-y: auto;
  padding: 8px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.4;
}

.todo-item:hover {
  background: var(--bg-app);
}

.todo-icon {
  flex-shrink: 0;
  width: 18px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
}

.todo-icon svg {
  fill: var(--text-muted);
}

.todo-status-completed .todo-icon svg {
  fill: #16a34a;
}

.todo-status-in_progress .todo-icon svg {
  fill: #f59e0b;
}

.todo-content {
  flex: 1;
  word-break: break-word;
}

.todo-priority {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
}

.todo-status-completed .todo-content {
  text-decoration: line-through;
  color: var(--text-muted);
}

.todo-panel-enter-active,
.todo-panel-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.todo-panel-enter-from,
.todo-panel-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
