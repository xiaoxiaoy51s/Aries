<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>{{ isEdit ? '编辑模型' : '新增模型' }}</h3>
          <button type="button" class="close-btn" @click="$emit('close')">×</button>
        </div>
        <div class="modal-body">
          <div class="compat-notice">
            仅兼容 <strong>OpenAI 格式</strong>的 API。Claude / Gemini 等原生 API 暂不支持，
            请使用对应的 OpenAI 兼容网关地址（如 <code>/v1</code> 结尾）。
          </div>

          <!-- 模型图标选择 -->
          <label class="form-label">模型类型</label>
          <div class="provider-row">
            <button
              v-for="p in PROVIDERS"
              :key="p.id"
              type="button"
              class="provider-chip"
              :class="{ active: selectedProvider === p.id }"
              :title="p.label"
              @click="selectProvider(p)"
            >
              <img :src="`./model/${p.icon}`" :alt="p.label" class="provider-chip-icon" />
            </button>
          </div>

          <label class="form-label">模型名称</label>
          <input v-model="form.name" type="text" class="form-input" placeholder="例如: gpt-4o" />

          <label class="form-label">API 地址</label>
          <input v-model="form.baseUrl" type="text" class="form-input" placeholder="https://api.openai.com/v1" />

          <label class="form-label">API Key</label>
          <div class="input-with-actions">
            <input
              v-model="form.apiKey"
              :type="showApiKey ? 'text' : 'password'"
              class="form-input"
              placeholder="sk-..."
            />
            <button
              type="button"
              class="text-btn"
              :title="showApiKey ? '隐藏' : '显示'"
              @click="showApiKey = !showApiKey"
            >{{ showApiKey ? '隐藏' : '显示' }}</button>
            <button
              type="button"
              class="text-btn"
              title="复制"
              :disabled="!form.apiKey"
              @click="copyApiKey"
            >{{ copied ? '已复制' : '复制' }}</button>
          </div>

          <div class="advanced-section">
            <button type="button" class="advanced-toggle" @click="showAdvanced = !showAdvanced">
              <span>高级设置</span>
              <span class="arrow" :class="{ expanded: showAdvanced }">&#9654;</span>
            </button>
            <div v-if="showAdvanced" class="advanced-fields">
              <div class="field-row">
                <label class="form-label">上下文长度</label>
                <input
                  v-model.number="form.context_window"
                  type="number"
                  class="form-input"
                  placeholder="200000"
                  min="1000"
                />
                <span class="field-hint">模型上下文窗口大小（token）</span>
              </div>
              <div class="field-row">
                <label class="form-label">工具调用轮次</label>
                <input
                  v-model.number="form.max_tool_rounds"
                  type="number"
                  class="form-input"
                  placeholder="100"
                  min="1"
                />
                <span class="field-hint">单次对话中最大工具调用轮数</span>
              </div>
            </div>
          </div>
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
import { PROVIDERS, detectProvider, type Provider } from '@/utils/modelProviders'

const props = defineProps<{
  visible: boolean
  isEdit: boolean
  model?: any | null
}>()

const emit = defineEmits<{ close: []; save: [data: any] }>()

const form = ref({ name: '', baseUrl: '', apiKey: '', context_window: 200000, max_tool_rounds: 100 })
const selectedProvider = ref('custom')
const showApiKey = ref(false)
const showAdvanced = ref(false)
const copied = ref(false)

function selectProvider(p: Provider) {
  selectedProvider.value = p.id
  if (p.model) form.value.name = p.model
  form.value.baseUrl = p.baseUrl
}

async function copyApiKey() {
  if (!form.value.apiKey) return
  try {
    await navigator.clipboard.writeText(form.value.apiKey)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = form.value.apiKey
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    if (props.model && (props.model.name || props.model.model)) {
      form.value = {
        name: props.model.name || props.model.model || '',
        baseUrl: props.model.baseUrl || '',
        apiKey: props.model.apiKey || '',
        context_window: props.model.context_window ?? 200000,
        max_tool_rounds: props.model.max_tool_rounds ?? 100,
      }
      showAdvanced.value = !!(props.model.context_window && props.model.context_window !== 200000) ||
        !!(props.model.max_tool_rounds && props.model.max_tool_rounds !== 100)
    } else {
      form.value = { name: '', baseUrl: '', apiKey: '', context_window: 200000, max_tool_rounds: 100 }
      showAdvanced.value = false
    }
    selectedProvider.value = detectProvider(form.value.name).id
  }
})

function onSave() {
  const name = form.value.name.trim()
  emit('save', {
    name,
    model: name,
    baseUrl: form.value.baseUrl,
    apiKey: form.value.apiKey,
    context_window: form.value.context_window || 200000,
    max_tool_rounds: form.value.max_tool_rounds || 100,
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

.compat-notice {
  padding: 10px 12px;
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.4);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}

.compat-notice strong { color: #b45309; }

.compat-notice code {
  padding: 1px 5px;
  background: var(--bg);
  border-radius: 3px;
  font-size: 11px;
}

.provider-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.provider-chip {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  cursor: pointer;
  padding: 0;
  transition: all 0.15s;
}

.provider-chip:hover {
  border-color: var(--border-strong);
  background: var(--accent-hover);
}

.provider-chip.active {
  border-color: #2d7a4f;
  background: rgba(45, 122, 79, 0.08);
  box-shadow: 0 0 0 1px #2d7a4f;
}

.provider-chip-icon {
  width: 24px;
  height: 24px;
  object-fit: contain;
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

.input-with-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.input-with-actions .form-input {
  flex: 1;
}

.icon-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  cursor: pointer;
  font-size: 14px;
  padding: 0;
}

.icon-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.text-btn {
  flex-shrink: 0;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  cursor: pointer;
  font-size: 11px;
  color: var(--text-muted);
}

.text-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.text-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}

.advanced-section {
  border-top: 1px solid var(--border);
  padding-top: 8px;
  margin-top: 4px;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 0;
}

.advanced-toggle:hover { color: var(--text); }

.advanced-toggle .arrow {
  font-size: 9px;
  transition: transform 0.15s;
}

.advanced-toggle .arrow.expanded {
  transform: rotate(90deg);
}

.advanced-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 8px;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-row .form-label {
  font-size: 12px;
}

.field-hint {
  font-size: 11px;
  color: var(--text-muted);
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
