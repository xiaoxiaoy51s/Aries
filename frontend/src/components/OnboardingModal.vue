<template>
  <div v-if="visible" class="onboarding-page">
    <div class="onboarding-inner">
      <div class="compat-notice">
        仅兼容 <strong>OpenAI 格式</strong>的 API。Claude / Gemini 等原生 API 需使用对应的 OpenAI 兼容网关地址（如 <code>/v1</code> 结尾）。
      </div>

      <label class="form-label">选择模型提供商</label>
      <div class="provider-grid">
        <button
          v-for="p in PROVIDERS"
          :key="p.id"
          type="button"
          class="provider-card"
          @click="openProviderModal(p)"
        >
          <img :src="`./model/${p.icon}`" :alt="p.label" class="provider-icon" />
          <span class="provider-name">{{ p.label }}</span>
        </button>
      </div>

      <div class="onboarding-footer">
        <button type="button" class="skip-btn" @click="$emit('skip')">稍后配置</button>
      </div>
    </div>

    <!-- 复用 ModelEditModal 组件 -->
    <ModelEditModal
      :visible="modalVisible"
      :is-edit="false"
      :model="selectedPreset"
      @close="modalVisible = false"
      @save="handleSave"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ModelEditModal from '@/components/settings/ModelEditModal.vue'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ skip: []; save: [data: { model: string; baseUrl: string; apiKey: string }] }>()

interface Provider {
  id: string
  icon: string
  label: string
  model: string
}

const PROVIDERS: Provider[] = [
  { id: 'chatgpt', icon: 'chatgpt.svg', label: 'ChatGPT', model: 'gpt-4o' },
  { id: 'claude', icon: 'claude.svg', label: 'Claude', model: 'claude-3-5-sonnet-20241022' },
  { id: 'gemini', icon: 'gemini.svg', label: 'Gemini', model: 'gemini-1.5-pro' },
  { id: 'deepseek', icon: 'deepseek.svg', label: 'DeepSeek', model: 'deepseek-chat' },
  { id: 'qwen', icon: 'qwen.svg', label: '通义千问', model: 'qwen-plus' },
  { id: 'glm', icon: 'glm.svg', label: '智谱 GLM', model: 'glm-4' },
  { id: 'kimi', icon: 'kimi.svg', label: 'Kimi', model: 'moonshot-v1-8k' },
  { id: 'doubao', icon: 'doubao.svg', label: '豆包', model: 'doubao-pro-32k' },
  { id: 'grok', icon: 'grok.svg', label: 'Grok', model: 'grok-beta' },
  { id: 'hunyun', icon: 'hunyun.svg', label: '混元', model: 'hunyuan-pro' },
  { id: 'minimax', icon: 'minimax.svg', label: 'MiniMax', model: 'abab6.5-chat' },
  { id: 'openrouter', icon: 'openrouter.svg', label: 'OpenRouter', model: 'openai/gpt-4o' },
  { id: 'custom', icon: 'Custom.svg', label: '自定义', model: '' },
]

const modalVisible = ref(false)
// 传递给 ModelEditModal 的预设数据（点击图标时填充模型名称）
const selectedPreset = ref<any>(null)

function openProviderModal(p: Provider) {
  selectedPreset.value = {
    name: p.model,
    model: p.model,
    baseUrl: '',
    apiKey: '',
  }
  modalVisible.value = true
}

function handleSave(data: any) {
  modalVisible.value = false
  emit('save', {
    model: data.model || data.name || '',
    baseUrl: data.baseUrl || '',
    apiKey: data.apiKey || '',
  })
}
</script>

<style scoped>
.onboarding-page {
  position: fixed;
  top: 40px;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 900;
  display: flex;
  flex-direction: column;
  background: var(--boot-bg-image, #f8fafc);
  overflow-y: auto;
}

.onboarding-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  padding: 32px;
}

.compat-notice {
  padding: 10px 14px;
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.4);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 24px;
}

.compat-notice strong { color: #b45309; }

.compat-notice code {
  padding: 1px 5px;
  background: var(--bg);
  border-radius: 3px;
  font-size: 11px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 12px;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 12px;
}

.provider-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 108px;
  padding: 16px 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-panel);
  cursor: pointer;
  transition: all 0.15s;
}

.provider-card:hover {
  border-color: #2d7a4f;
  background: rgba(45, 122, 79, 0.06);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.provider-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.provider-name {
  font-size: 12px;
  color: var(--text);
  text-align: center;
  white-space: nowrap;
}

.onboarding-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 32px;
  margin-top: auto;
}

.skip-btn {
  padding: 8px 20px;
  background: transparent;
  border: none;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
}

.skip-btn:hover { color: var(--text); }
</style>
