<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>{{ isEdit ? '编辑模型' : '新增模型' }}</h3>
          <button type="button" class="close-btn" @click="$emit('close')">×</button>
        </div>
        <div class="modal-body">
          <label class="form-label">模型名称</label>
          <input v-model="form.name" type="text" class="form-input" placeholder="例如: gpt-4o" />
          <label class="form-label">API 地址</label>
          <input v-model="form.baseUrl" type="text" class="form-input" placeholder="https://api.openai.com/v1" />
          <label class="form-label">API Key</label>
          <input v-model="form.apiKey" type="password" class="form-input" placeholder="sk-..." />
        </div>
        <div class="modal-footer">
          <button type="button" class="secondary-btn" @click="$emit('close')">取消</button>
          <button type="button" class="primary-btn" @click="onSave">保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  isEdit: boolean
  model?: any | null
}>()

const emit = defineEmits<{ close: []; save: [data: any] }>()

const form = ref({ name: '', baseUrl: '', apiKey: '' })

watch(() => props.visible, (val) => {
  if (val) {
    if (props.isEdit && props.model) {
      form.value = {
        name: props.model.name || props.model.model || '',
        baseUrl: props.model.baseUrl || '',
        apiKey: props.model.apiKey || '',
      }
    } else {
      form.value = { name: '', baseUrl: '', apiKey: '' }
    }
  }
})

function onSave() {
  const name = form.value.name.trim()
  emit('save', {
    name,
    model: name,
    baseUrl: form.value.baseUrl,
    apiKey: form.value.apiKey,
  })
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
  width: 420px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 { font-size: 16px; font-weight: 600; }

.close-btn {
  width: 28px; height: 28px;
  border: none; background: transparent;
  font-size: 18px; cursor: pointer;
  border-radius: 6px;
}

.close-btn:hover { background: var(--accent-hover); }

.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  outline: none;
}

.form-input:focus { border-color: var(--border-strong); }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}

.primary-btn {
  padding: 8px 16px;
  background: #2d7a4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.primary-btn:hover { opacity: 0.9; }

.secondary-btn {
  padding: 8px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.secondary-btn:hover { background: var(--accent-hover); }
</style>
