<template>
  <div class="codex-confirm">
    <p class="codex-confirm-desc">{{ description }}</p>
    <pre class="codex-confirm-cmd">{{ command }}</pre>

    <ul class="codex-confirm-options" role="listbox" aria-label="确认选项">
      <li
        role="option"
        :aria-selected="selected === 1"
        class="codex-option"
        :class="{ active: selected === 1 }"
        @click="selected = 1"
      >
        <span class="option-num">1</span>
        <span class="option-text">是</span>
      </li>
      <li
        role="option"
        :aria-selected="selected === 2"
        class="codex-option"
        :class="{ active: selected === 2 }"
        @click="selected = 2"
      >
        <span class="option-num">2</span>
        <span class="option-text">否</span>
      </li>
    </ul>

    <div class="codex-confirm-footer">
      <span class="codex-timer">{{ countdown }}s</span>
      <div class="codex-footer-actions">
        <button type="button" class="codex-skip" @click="$emit('skip')">跳过</button>
        <button type="button" class="codex-submit" @click="submit">
          提交
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  description: string
  command: string
  countdown: number
}>()

const emit = defineEmits<{
  submit: [mode: 'yes' | 'no']
  skip: []
}>()

const selected = ref<1 | 2>(1)

watch(
  () => props.command,
  () => {
    selected.value = 1
  }
)

function submit() {
  if (selected.value === 1) emit('submit', 'yes')
  else emit('submit', 'no')
}
</script>

<style scoped>
.codex-confirm {
  padding: 16px 18px 14px;
  margin-bottom: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
}

.codex-confirm-desc {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--text);
}

.codex-confirm-cmd {
  margin: 0 0 14px;
  padding: 10px 12px;
  background: #f7f7f5;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
}

.codex-confirm-options {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.codex-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
}

.codex-option:hover,
.codex-option.active {
  background: var(--accent-hover);
}

.option-num {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-app);
  border: 1px solid var(--border);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}

.codex-option.active .option-num {
  background: var(--send-bg);
  color: #fff;
  border-color: var(--send-bg);
}

.option-text {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  padding-top: 1px;
}

.option-text code {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.05);
  padding: 0 4px;
  border-radius: 4px;
}

.codex-confirm-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}

.codex-timer {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.codex-footer-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.codex-skip {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  padding: 6px 4px;
}

.codex-skip:hover {
  color: var(--text);
}

.codex-submit {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: var(--send-bg);
  color: #fff;
  transition: background 0.15s;
}

.codex-submit:hover {
  background: var(--send-hover);
}
</style>
