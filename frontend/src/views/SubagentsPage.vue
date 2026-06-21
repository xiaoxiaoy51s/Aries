<template>
  <div class="subagents-page">
    <div class="page-header">
      <h2 class="page-title">智能体</h2>
      <div class="header-actions">
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadAll">
          刷新
        </button>
        <button type="button" class="btn-primary" @click="openCreateDialog">+ 新建智能体</button>
      </div>
    </div>

    <p class="page-desc">
      智能体是带有专属技能与 MCP 组合的子 Agent。主 Agent 会根据描述选择委派任务；
      被引用的技能 / MCP 即使在全局未启用，也会在该智能体内部强制激活。
    </p>

    <!-- 空状态 -->
    <div v-if="!loading && subagents.length === 0" class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
        <line x1="9" y1="9" x2="9.01" y2="9"/>
        <line x1="15" y1="9" x2="15.01" y2="9"/>
      </svg>
      <p>暂无智能体，点击上方按钮创建</p>
    </div>

    <!-- 加载状态 -->
    <div v-else-if="loading && subagents.length === 0" class="empty-state">
      <p>加载中…</p>
    </div>

    <!-- 智能体卡片列表 -->
    <div v-else class="subagent-grid">
      <div
        v-for="agent in subagents"
        :key="agent.name"
        class="subagent-card"
        :class="{ 'is-disabled': !agent.enabled, 'is-unavailable': agent.enabled && !agent.available }"
      >
        <div class="card-header">
          <span class="card-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="4"/>
              <circle cx="9" cy="10" r="1"/>
              <circle cx="15" cy="10" r="1"/>
              <path d="M9 16h6"/>
            </svg>
          </span>
          <h3 class="card-title" :title="agent.name">{{ agent.name }}</h3>
          <span class="status-pill" :class="statusPillClass(agent)">{{ statusPillLabel(agent) }}</span>
        </div>
        <p class="card-content">{{ agent.description || '（无描述）' }}</p>

        <div class="card-meta">
          <span class="meta-item">
            <span class="meta-label">模型</span>
            <span class="meta-value">{{ agent.model || agent.fallback_model || '—' }}</span>
          </span>
        </div>

        <div class="card-tags">
          <span v-for="s in agent.allowed_skills" :key="'sk-' + s" class="tag tag-skill">
            技能 · {{ s }}
          </span>
          <span v-for="m in agent.allowed_mcps" :key="'mcp-' + m" class="tag tag-mcp">
            MCP · {{ m }}
          </span>
          <span v-if="!agent.allowed_skills.length && !agent.allowed_mcps.length" class="tag tag-empty">
            未配置技能与 MCP
          </span>
        </div>

        <div v-if="agent.enabled && !agent.available" class="warn-line">
          ⚠ {{ agent.unavailable_reason || '依赖检查未通过' }}
        </div>

        <div class="card-footer">
          <label class="switch">
            <input
              type="checkbox"
              :checked="agent.enabled"
              :disabled="busyName === agent.name"
              @change="(e) => toggleEnabled(agent, (e.target as HTMLInputElement).checked)"
            />
            <span class="slider"></span>
            <span class="switch-label">{{ agent.enabled ? '已启用' : '已禁用' }}</span>
          </label>
          <div class="card-actions">
            <button type="button" class="btn-text" @click="openEditDialog(agent)">编辑</button>
            <button type="button" class="btn-text btn-danger" @click="confirmDelete(agent)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMessage" class="error-toast" @click="errorMessage = ''">{{ errorMessage }}</div>

    <!-- 新建/编辑弹窗 -->
    <div v-if="dialogVisible" class="modal-overlay" @click="closeDialog">
      <div class="modal-dialog modal-large" @click.stop>
        <div class="modal-header">
          {{ dialogMode === 'create' ? '新建智能体' : `编辑智能体：${form.name}` }}
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label class="form-label">名称<span class="required">*</span></label>
            <input
              v-model="form.name"
              type="text"
              class="form-input"
              :disabled="dialogMode === 'edit'"
              placeholder="仅允许字母、数字、点、下划线、短横线"
            />
          </div>

          <div class="form-row">
            <label class="form-label">职责描述<span class="required">*</span></label>
            <input
              v-model="form.description"
              type="text"
              class="form-input"
              placeholder="一句话说明：何时调用，能做什么"
            />
          </div>

          <div class="form-row form-row-2">
            <div>
              <label class="form-label">主模型</label>
              <select v-model="form.model" class="form-input">
                <option value="">使用默认（fallback）</option>
                <option v-for="m in availableModels" :key="m.id" :value="m.model">{{ m.model }}</option>
              </select>
            </div>
            <div>
              <label class="form-label">Fallback 模型</label>
              <select v-model="form.fallback_model" class="form-input">
                <option value="default">default（系统默认）</option>
                <option v-for="m in availableModels" :key="m.id" :value="m.model">{{ m.model }}</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label">可使用技能</label>
            <div class="checkbox-list">
              <div v-if="skills.length === 0" class="checkbox-empty">未发现任何技能</div>
              <label v-for="sk in skills" :key="sk.folder_name" class="checkbox-item">
                <input
                  type="checkbox"
                  :value="sk.folder_name"
                  :checked="form.allowed_skills.includes(sk.folder_name)"
                  @change="toggleSkill(sk.folder_name)"
                />
                <span class="cb-name">{{ sk.name }}</span>
                <span class="cb-tag" :class="sk.enabled ? 'tag-on' : 'tag-off'">
                  {{ sk.enabled ? '已启用' : '未启用' }}
                </span>
                <span class="cb-desc" :title="sk.description">{{ sk.description || '（无描述）' }}</span>
              </label>
            </div>
            <p class="form-hint">
              勾选后无论该技能在全局是否启用，本智能体都可使用。
            </p>
          </div>

          <div class="form-row">
            <label class="form-label">可使用 MCP</label>
            <div class="checkbox-list">
              <div v-if="plugins.length === 0" class="checkbox-empty">未发现任何 MCP</div>
              <label v-for="mc in plugins" :key="mc.id" class="checkbox-item">
                <input
                  type="checkbox"
                  :value="mc.id"
                  :checked="form.allowed_mcps.includes(mc.id)"
                  @change="toggleMcp(mc.id)"
                />
                <span class="cb-name">{{ mc.name }}</span>
                <span class="cb-tag" :class="mc.enabled ? 'tag-on' : 'tag-off'">
                  {{ mc.enabled ? '已启用' : '未启用' }}
                </span>
                <span class="cb-desc" :title="mc.description">{{ mc.description || '（无描述）' }}</span>
              </label>
            </div>
            <p class="form-hint">
              勾选后即使 mcp.json 中 enabled=false，本智能体也会强制激活。
            </p>
          </div>

          <div class="form-row">
            <label class="form-label">详细职责（System Prompt）</label>
            <textarea
              v-model="form.system_prompt"
              class="form-textarea"
              rows="6"
              placeholder="提供给该智能体的系统提示词，描述它的工作方式、规则、输出格式等"
            />
          </div>

          <div class="form-row">
            <label class="checkbox-item">
              <input v-model="form.enabled" type="checkbox" />
              <span class="cb-name">立即启用</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="closeDialog">取消</button>
          <button class="modal-btn modal-btn-confirm" :disabled="saving" @click="saveForm">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认 -->
    <div v-if="deleteTarget" class="modal-overlay" @click="deleteTarget = null">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">确认删除</div>
        <div class="modal-body">
          <p>确定删除智能体「{{ deleteTarget.name }}」？该操作不可恢复。</p>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="deleteTarget = null">取消</button>
          <button class="modal-btn modal-btn-danger" :disabled="saving" @click="doDelete">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  listSubagents,
  createSubagent,
  updateSubagent,
  deleteSubagent,
  updateSubagentStatus,
  type SubagentItem,
  type SubagentPayload,
} from '@/api/subagents'
import { listSkills, type SkillItem } from '@/api/skills'
import { listPlugins, type PluginItem } from '@/api/plugins'
import { useModelStore } from '@/stores/model'

const modelStore = useModelStore()

const subagents = ref<SubagentItem[]>([])
const skills = ref<SkillItem[]>([])
const plugins = ref<PluginItem[]>([])
const loading = ref(false)
const saving = ref(false)
const busyName = ref<string | null>(null)
const errorMessage = ref('')

const availableModels = computed(() => modelStore.modelList)

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const deleteTarget = ref<SubagentItem | null>(null)

const defaultForm = (): SubagentPayload & { allowed_skills: string[]; allowed_mcps: string[] } => ({
  name: '',
  description: '',
  model: '',
  fallback_model: 'default',
  enabled: true,
  allowed_skills: [],
  allowed_mcps: [],
  system_prompt: '',
})

const form = reactive(defaultForm())

function statusPillClass(agent: SubagentItem) {
  if (!agent.enabled) return 'pill-disabled'
  if (!agent.available) return 'pill-warn'
  return 'pill-ok'
}

function statusPillLabel(agent: SubagentItem) {
  if (!agent.enabled) return '已禁用'
  if (!agent.available) return '依赖异常'
  return '可用'
}

async function loadAll() {
  loading.value = true
  try {
    const [agents, sk, pl] = await Promise.all([
      listSubagents(),
      listSkills(),
      listPlugins(),
    ])
    subagents.value = agents
    skills.value = sk
    plugins.value = pl.plugins
  } catch (e) {
    errorMessage.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  Object.assign(form, defaultForm())
  dialogMode.value = 'create'
  dialogVisible.value = true
}

function openEditDialog(agent: SubagentItem) {
  Object.assign(form, {
    name: agent.name,
    description: agent.description,
    model: agent.model,
    fallback_model: agent.fallback_model || 'default',
    enabled: agent.enabled,
    allowed_skills: [...agent.allowed_skills],
    allowed_mcps: [...agent.allowed_mcps],
    system_prompt: agent.system_prompt,
  })
  dialogMode.value = 'edit'
  dialogVisible.value = true
}

function closeDialog() {
  if (saving.value) return
  dialogVisible.value = false
}

function toggleSkill(folderName: string) {
  const idx = form.allowed_skills.indexOf(folderName)
  if (idx >= 0) form.allowed_skills.splice(idx, 1)
  else form.allowed_skills.push(folderName)
}

function toggleMcp(id: string) {
  const idx = form.allowed_mcps.indexOf(id)
  if (idx >= 0) form.allowed_mcps.splice(idx, 1)
  else form.allowed_mcps.push(id)
}

async function saveForm() {
  const name = (form.name || '').trim()
  if (!name) {
    errorMessage.value = '名称不能为空'
    return
  }
  if (!/^[A-Za-z0-9._-]+$/.test(name)) {
    errorMessage.value = '名称只允许字母、数字、点、下划线、短横线'
    return
  }
  if (!(form.description || '').trim()) {
    errorMessage.value = '职责描述不能为空'
    return
  }

  saving.value = true
  try {
    const payload: SubagentPayload = {
      name,
      description: form.description?.trim() || '',
      model: (form.model || '').trim(),
      fallback_model: (form.fallback_model || 'default').trim() || 'default',
      enabled: !!form.enabled,
      allowed_skills: [...form.allowed_skills],
      allowed_mcps: [...form.allowed_mcps],
      system_prompt: form.system_prompt || '',
    }
    if (dialogMode.value === 'create') {
      await createSubagent(payload)
    } else {
      await updateSubagent(name, payload)
    }
    dialogVisible.value = false
    await loadAll()
  } catch (e) {
    errorMessage.value = (e as Error).message || '保存失败'
  } finally {
    saving.value = false
  }
}

function confirmDelete(agent: SubagentItem) {
  deleteTarget.value = agent
}

async function doDelete() {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await deleteSubagent(deleteTarget.value.name)
    deleteTarget.value = null
    await loadAll()
  } catch (e) {
    errorMessage.value = (e as Error).message || '删除失败'
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(agent: SubagentItem, enabled: boolean) {
  busyName.value = agent.name
  try {
    await updateSubagentStatus(agent.name, enabled)
    await loadAll()
  } catch (e) {
    errorMessage.value = (e as Error).message || '更新状态失败'
  } finally {
    busyName.value = null
  }
}

onMounted(() => {
  loadAll()
  if (modelStore.modelList.length === 0) {
    modelStore.loadModels().catch(() => undefined)
  }
})
</script>

<style scoped>
.subagents-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 28px;
  overflow-y: auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.page-desc {
  font-size: 13px;
  color: var(--text-muted, #888);
  margin: 0 0 20px;
  line-height: 1.55;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  padding: 8px 20px;
  background: var(--accent, #4a90d9);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-primary:hover { opacity: 0.88; }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-secondary {
  padding: 8px 16px;
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.btn-secondary:hover { background: var(--bg-hover, rgba(0,0,0,0.04)); }
.btn-secondary:disabled { opacity: 0.45; cursor: not-allowed; }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--text-muted);
  gap: 12px;
}
.empty-state p { margin: 0; font-size: 14px; }

.subagent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.subagent-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: box-shadow 0.2s, opacity 0.2s;
}
.subagent-card:hover { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08); }
.subagent-card.is-disabled { opacity: 0.62; }
.subagent-card.is-unavailable { border-color: rgba(255, 149, 0, 0.5); }

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(74, 144, 217, 0.12);
  color: #4a90d9;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-pill {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.pill-ok { background: rgba(52, 199, 89, 0.12); color: #34c759; }
.pill-warn { background: rgba(255, 149, 0, 0.12); color: #ff9500; }
.pill-disabled { background: rgba(128, 128, 128, 0.15); color: #888; }

.card-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.55;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: var(--text-muted);
}
.meta-item { display: inline-flex; gap: 4px; }
.meta-label { opacity: 0.7; }
.meta-value { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary);
}
.tag-skill { background: rgba(74, 144, 217, 0.1); color: #4a90d9; }
.tag-mcp { background: rgba(155, 89, 182, 0.12); color: #9b59b6; }
.tag-empty { background: transparent; color: var(--text-muted); font-style: italic; }

.warn-line {
  font-size: 12px;
  color: #ff9500;
  background: rgba(255, 149, 0, 0.08);
  padding: 6px 10px;
  border-radius: 6px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.card-actions { display: flex; gap: 6px; }

.btn-text {
  background: transparent;
  border: none;
  color: var(--accent, #4a90d9);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.btn-text:hover { background: rgba(74, 144, 217, 0.08); }
.btn-text.btn-danger { color: #ff3b30; }
.btn-text.btn-danger:hover { background: rgba(255, 59, 48, 0.08); }

/* Toggle switch */
.switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.switch input { display: none; }
.slider {
  position: relative;
  width: 32px;
  height: 18px;
  background: rgba(128, 128, 128, 0.3);
  border-radius: 10px;
  transition: background 0.2s;
}
.slider::before {
  content: "";
  position: absolute;
  width: 14px;
  height: 14px;
  background: #fff;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
}
.switch input:checked + .slider { background: #4a90d9; }
.switch input:checked + .slider::before { transform: translateX(14px); }
.switch-label { font-size: 12px; color: var(--text-secondary); }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal-dialog {
  background: var(--bg-card, #fff);
  border-radius: 12px;
  width: 480px;
  max-width: 92vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.22);
}
.modal-large { width: 640px; }
.modal-header {
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}
.modal-body {
  padding: 16px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.modal-footer {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.modal-btn {
  padding: 7px 18px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
.modal-btn-cancel:hover { background: rgba(0, 0, 0, 0.04); }
.modal-btn-confirm {
  background: #4a90d9;
  color: #fff;
  border-color: #4a90d9;
}
.modal-btn-confirm:hover { opacity: 0.88; }
.modal-btn-confirm:disabled { opacity: 0.45; cursor: not-allowed; }
.modal-btn-danger {
  background: #ff3b30;
  color: #fff;
  border-color: #ff3b30;
}
.modal-btn-danger:hover { opacity: 0.88; }
.modal-btn-danger:disabled { opacity: 0.45; cursor: not-allowed; }

/* Form */
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.form-row-2 > div { display: flex; flex-direction: column; gap: 6px; }
.form-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.required { color: #ff3b30; margin-left: 2px; }
.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-input, #fafafa);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  box-sizing: border-box;
}
.form-textarea { resize: vertical; min-height: 100px; }
.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #4a90d9;
}
.form-input:disabled { opacity: 0.6; cursor: not-allowed; }
.form-hint { font-size: 11px; color: var(--text-muted); margin: 0; }

.checkbox-list {
  border: 1px solid var(--border);
  border-radius: 6px;
  max-height: 180px;
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.checkbox-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.checkbox-item:hover { background: rgba(74, 144, 217, 0.06); }
.checkbox-item input[type="checkbox"] { cursor: pointer; }
.cb-name { font-weight: 500; color: var(--text); }
.cb-desc {
  color: var(--text-muted);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cb-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
}
.tag-on { background: rgba(52, 199, 89, 0.12); color: #34c759; }
.tag-off { background: rgba(128, 128, 128, 0.15); color: #888; }

.error-toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #ff3b30;
  color: #fff;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 300;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(255, 59, 48, 0.3);
}
</style>
