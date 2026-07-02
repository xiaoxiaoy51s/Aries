<template>
  <div v-if="showTerminal || showTodo || showStop || showBackground" :class="['tool-action-bar', plain && 'tool-action-bar--plain']">
    <button
      v-if="showTerminal"
      type="button"
      class="action-chip"
      title="在控制台查看命令执行过程"
      @click.stop="$emit('openTerminal')"
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="4 17 10 11 4 5"/>
        <line x1="12" y1="19" x2="20" y2="19"/>
      </svg>
      在终端查看
      <svg class="action-external" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M7 17 17 7"/>
        <path d="M7 7h10v10"/>
      </svg>
    </button>
    <button
      v-if="showTodo"
      type="button"
      class="action-chip"
      title="查看任务清单"
      @click.stop="$emit('openTodos')"
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 11 12 14 22 4"/>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
      查看任务
    </button>
    <button
      v-if="showStop"
      type="button"
      class="action-chip action-chip--danger"
      title="终止当前命令"
      @click.stop="$emit('stopCommand')"
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <rect x="6" y="6" width="12" height="12" rx="1"/>
      </svg>
      终止运行
    </button>
    <button
      v-if="showBackground"
      type="button"
      class="action-chip"
      :title="autoDetached ? '停止后台服务' : '转入后台运行'"
      @click.stop="$emit('toggleBackground')"
    >
      <svg v-if="!autoDetached" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="5 3 19 12 5 21 5 3"/>
      </svg>
      <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <rect x="6" y="6" width="12" height="12" rx="1"/>
      </svg>
      {{ autoDetached ? '停止服务' : '后台运行' }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  showTerminal?: boolean
  showTodo?: boolean
  showStop?: boolean
  showBackground?: boolean
  autoDetached?: boolean
  plain?: boolean
}>()

defineEmits<{
  openTerminal: []
  openTodos: []
  stopCommand: []
  toggleBackground: []
}>()
</script>

<style scoped>
.tool-action-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.tool-action-bar--plain {
  gap: 12px;
}

.action-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.3px;
  color: #374151;
  background: #ffffff;
  border: 1px solid #d1d5db;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
  line-height: 1.4;
  white-space: nowrap;
}

.action-chip:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.tool-action-bar--plain .action-chip {
  background: transparent;
  border: none;
  padding: 0;
  color: #6b7280;
  font-weight: 400;
}

.tool-action-bar--plain .action-chip:hover {
  color: #111827;
  background: transparent;
}

.action-external {
  margin-left: 1px;
  opacity: 0.7;
}

.action-chip--danger {
  color: #b91c1c;
  border-color: #fca5a5;
}
.action-chip--danger:hover {
  background: #fef2f2;
  border-color: #f87171;
}

.tool-action-bar--plain .action-chip--danger {
  color: #dc2626;
  border: none;
  background: transparent;
}

.tool-action-bar--plain .action-chip--danger:hover {
  color: #991b1b;
  background: transparent;
}
</style>
