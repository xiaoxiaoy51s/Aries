<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <div class="modal-header">
          <h3>Role 约束</h3>
          <button type="button" class="close-btn" @click="$emit('close')">×</button>
        </div>
        <div class="modal-body">
          <textarea
            v-model="content"
            class="rules-editor"
            :placeholder="placeholder"
            :disabled="polishing"
          ></textarea>
          <div v-if="polishing" class="polishing-hint">AI 正在润色...</div>
        </div>
        <div class="modal-footer">
          <button type="button" class="secondary-btn" @click="onPolish" :disabled="polishing || !content.trim()">
            {{ polishing ? '润色中...' : 'AI 润色' }}
          </button>
          <div class="footer-right">
            <button type="button" class="secondary-btn" @click="$emit('close')">取消</button>
            <button type="button" class="primary-btn" @click="onSave" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { getRoleRules, saveRoleRules, getRoleGuide, polishRoleRules } from '@/api/memory'

const props = defineProps<{
  visible: boolean
  workDir: string | null
}>()

const emit = defineEmits<{ close: []; saved: [] }>()

const content = ref('')
const placeholder = ref('')
const polishing = ref(false)
const saving = ref(false)

watch(() => props.visible, async (val) => {
  if (val) {
    polishing.value = false
    saving.value = false
    try {
      const [rulesRes, guideRes] = await Promise.all([
        getRoleRules(props.workDir),
        getRoleGuide(),
      ])
      content.value = rulesRes.content || ''
      placeholder.value = guideRes.guide || ''
    } catch (e) {
      console.error('加载约束失败', e)
    }
  }
})

async function onPolish() {
  polishing.value = true
  try {
    const res = await polishRoleRules(props.workDir, content.value)
    if (res.success && res.content) {
      content.value = res.content
    }
  } catch (e: any) {
    console.error('润色失败', e)
    alert(e.message || 'AI 润色失败')
  } finally {
    polishing.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await saveRoleRules(props.workDir, content.value)
    emit('saved')
    emit('close')
  } catch (e: any) {
    console.error('保存失败', e)
    alert(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2100;
}

.modal-container {
  width: 640px;
  max-height: 80vh;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0 4px;
}

.close-btn:hover {
  color: var(--text);
}

.modal-body {
  padding: 16px 20px;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rules-editor {
  width: 100%;
  min-height: 360px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text);
  font-size: 14px;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.6;
  resize: vertical;
  outline: none;
}

.rules-editor:focus {
  border-color: var(--accent);
}

.rules-editor:disabled {
  opacity: 0.6;
}

.polishing-hint {
  font-size: 12px;
  color: var(--accent);
  text-align: center;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}

.footer-right {
  display: flex;
  gap: 8px;
}

.secondary-btn,
.primary-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--border);
}

.secondary-btn {
  background: var(--bg-panel);
  color: var(--text);
}

.secondary-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.primary-btn {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.primary-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.secondary-btn:disabled,
.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
