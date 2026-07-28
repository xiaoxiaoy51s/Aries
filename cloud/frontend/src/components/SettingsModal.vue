<template>
  <Teleport to="body">
    <div class="settings-backdrop" @click.self="handleClose">
      <div class="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <!-- 头部 -->
        <header class="settings-head">
          <h2 id="settings-title" class="settings-title">{{ t('settings.title') }}</h2>
          <button type="button" class="settings-close" :title="t('settings.cancel')" @click="handleClose">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </header>

        <!-- 标签栏 -->
        <nav class="settings-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            class="settings-tab"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </nav>

        <!-- 内容区 -->
        <div class="settings-body">
          <!-- 模型管理 -->
          <section v-if="activeTab === 'models'" class="settings-section">
            <div class="settings-section-head">
              <div class="settings-section-meta">
                <div class="settings-section-title">{{ t('settings.models') }}</div>
                <div class="settings-section-desc">{{ t('settings.noModels') }}</div>
              </div>
              <button type="button" class="ds-btn ds-btn-primary" @click="openAddForm">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                {{ t('settings.addModel') }}
              </button>
            </div>

            <div v-if="models.length === 0" class="settings-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <p>{{ t('settings.noModels') }}</p>
            </div>

            <div v-else class="settings-model-list">
              <div v-for="m in models" :key="m.id" class="settings-model-card">
                <div class="settings-model-info">
                  <div class="settings-model-name">
                    {{ m.name }}
                    <span v-if="m.isActive" class="settings-tag settings-tag-success">{{ t('settings.active') }}</span>
                  </div>
                  <div class="settings-model-meta">
                    <span class="settings-model-id">{{ m.model }}</span>
                    <span class="settings-model-sep">·</span>
                    <span class="settings-model-url">{{ m.baseUrl }}</span>
                  </div>
                </div>
                <div class="settings-model-actions">
                  <label class="settings-switch" :title="t('settings.active')">
                    <input type="checkbox" :checked="m.isActive" @change="(e) => toggleActive(m, e.target.checked)" />
                    <span class="settings-switch-thumb" />
                  </label>
                  <button type="button" class="ds-btn ds-btn-secondary" @click="openEditForm(m)">{{ t('settings.editModel') }}</button>
                  <button type="button" class="settings-icon-btn settings-icon-btn-danger" :title="t('settings.delete')" @click="handleDelete(m)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                      <path d="M10 11v6M14 11v6"/>
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </section>

          <!-- 通用设置 -->
          <section v-else-if="activeTab === 'general'" class="settings-section">
            <div class="settings-form">
              <div class="settings-field">
                <label class="settings-field-label">{{ t('settings.language') }}</label>
                <div class="settings-radio-group">
                  <label class="settings-radio">
                    <input type="radio" value="zh" :checked="settingsStore.language === 'zh'" @change="settingsStore.setLanguage('zh')" />
                    <span class="settings-radio-dot" />
                    <span>中文</span>
                  </label>
                  <label class="settings-radio">
                    <input type="radio" value="en" :checked="settingsStore.language === 'en'" @change="settingsStore.setLanguage('en')" />
                    <span class="settings-radio-dot" />
                    <span>English</span>
                  </label>
                </div>
              </div>

              <div class="settings-field">
                <label class="settings-field-label">{{ t('settings.theme') }}</label>
                <div class="settings-radio-group">
                  <label class="settings-radio">
                    <input type="radio" value="light" :checked="settingsStore.theme === 'light'" @change="settingsStore.setTheme('light')" />
                    <span class="settings-radio-dot" />
                    <span>{{ t('settings.themeLight') }}</span>
                  </label>
                  <label class="settings-radio">
                    <input type="radio" value="dark" :checked="settingsStore.theme === 'dark'" @change="settingsStore.setTheme('dark')" />
                    <span class="settings-radio-dot" />
                    <span>{{ t('settings.themeDark') }}</span>
                  </label>
                  <label class="settings-radio">
                    <input type="radio" value="system" :checked="settingsStore.theme === 'system'" @change="settingsStore.setTheme('system')" />
                    <span class="settings-radio-dot" />
                    <span>{{ t('settings.themeSystem') }}</span>
                  </label>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 模型新增/编辑表单 -->
  <Teleport to="body">
    <div v-if="formVisible" class="settings-backdrop" @click.self="formVisible = false">
      <div class="settings-dialog settings-dialog-form" role="dialog" aria-modal="true">
        <header class="settings-head">
          <h2 class="settings-title">{{ editingModel ? t('settings.editModel') : t('settings.addModel') }}</h2>
          <button type="button" class="settings-close" :title="t('settings.cancel')" @click="formVisible = false">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </header>

        <form class="settings-form" @submit.prevent="handleSave">
          <div class="settings-field">
            <label class="settings-field-label">{{ t('settings.modelName') }}</label>
            <input v-model="formData.name" type="text" class="ds-input" :placeholder="t('settings.modelNameHint')" />
          </div>
          <div class="settings-field">
            <label class="settings-field-label">{{ t('settings.modelId') }}</label>
            <input v-model="formData.model" type="text" class="ds-input" :placeholder="t('settings.modelIdHint')" />
          </div>
          <div class="settings-field">
            <label class="settings-field-label">{{ t('settings.apiKey') }}</label>
            <input v-model="formData.apiKey" type="password" class="ds-input" placeholder="sk-..." autocomplete="off" />
          </div>
          <div class="settings-field">
            <label class="settings-field-label">{{ t('settings.baseUrl') }}</label>
            <input v-model="formData.baseUrl" type="text" class="ds-input" placeholder="https://api.openai.com/v1" />
          </div>
          <div class="settings-field-row">
            <div class="settings-field">
              <label class="settings-field-label">{{ t('settings.toolRounds') }}</label>
              <input v-model.number="formData.max_tool_rounds" type="number" min="1" max="500" class="ds-input" />
            </div>
            <div class="settings-field">
              <label class="settings-field-label">{{ t('settings.contextWindow') }}</label>
              <input v-model.number="formData.context_window" type="number" min="1" class="ds-input" placeholder="200000" />
            </div>
          </div>
          <div class="settings-field settings-field-inline">
            <label class="settings-field-label">{{ t('settings.active') }}</label>
            <label class="settings-switch">
              <input type="checkbox" v-model="formData.isActive" />
              <span class="settings-switch-thumb" />
            </label>
          </div>

          <footer class="settings-foot">
            <button type="button" class="ds-btn ds-btn-secondary" @click="formVisible = false">{{ t('settings.cancel') }}</button>
            <button type="submit" class="ds-btn ds-btn-primary" :disabled="saving">
              <span v-if="saving">保存中…</span>
              <span v-else>{{ t('settings.save') }}</span>
            </button>
          </footer>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '../stores/settings'
import { useI18n } from '../i18n'
import api from '../api'
import './SettingsModal.css'

const settingsStore = useSettingsStore()
const { t } = useI18n()

const visible = ref(true)
const activeTab = ref('models')

const tabs = [
  { key: 'models', label: t('settings.models') },
  { key: 'general', label: t('settings.general') },
]

// 模型列表
const models = ref([])
const loading = ref(false)

async function fetchModels() {
  loading.value = true
  try {
    const res = await api.get('/api/models')
    models.value = res.data
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Failed to load models')
  } finally {
    loading.value = false
  }
}

onMounted(fetchModels)

// 新增/编辑表单
const formVisible = ref(false)
const editingModel = ref(null)
const saving = ref(false)
const formData = reactive({
  name: '',
  model: '',
  apiKey: '',
  baseUrl: '',
  max_tool_rounds: 100,
  context_window: 200000,
  isActive: false,
})

function resetForm() {
  formData.name = ''
  formData.model = ''
  formData.apiKey = ''
  formData.baseUrl = ''
  formData.max_tool_rounds = 100
  formData.context_window = 200000
  formData.isActive = false
}

function openAddForm() {
  editingModel.value = null
  resetForm()
  formVisible.value = true
}

function openEditForm(m) {
  editingModel.value = m
  formData.name = m.name
  formData.model = m.model
  formData.apiKey = m.apiKey
  formData.baseUrl = m.baseUrl
  formData.max_tool_rounds = m.max_tool_rounds
  formData.context_window = m.context_window
  formData.isActive = m.isActive
  formVisible.value = true
}

async function handleSave() {
  if (!formData.name || !formData.model || !formData.apiKey || !formData.baseUrl) {
    ElMessage.warning('Please fill in all required fields')
    return
  }
  saving.value = true
  try {
    if (editingModel.value) {
      await api.put(`/api/models/${editingModel.value.id}`, { ...formData })
      ElMessage.success('Updated')
    } else {
      await api.post('/api/models', { ...formData })
      ElMessage.success('Created')
    }
    formVisible.value = false
    await fetchModels()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Save failed')
  } finally {
    saving.value = false
  }
}

async function handleDelete(m) {
  try {
    await ElMessageBox.confirm(t('settings.deleteConfirm'), '', { type: 'warning' })
    await api.delete(`/api/models/${m.id}`)
    ElMessage.success('Deleted')
    await fetchModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.detail || 'Delete failed')
    }
  }
}

async function toggleActive(m, val) {
  try {
    await api.put(`/api/models/${m.id}`, { isActive: val })
    await fetchModels()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || 'Update failed')
  }
}

function handleClose() {
  settingsStore.closeSettings()
}
</script>
