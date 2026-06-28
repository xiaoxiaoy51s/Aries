<template>
  <div class="settings-section">
    <div class="section-header">
      <span class="section-desc">管理主 Agent 与各个子智能体可使用的技能和 MCP</span>
      <button type="button" class="secondary-btn" @click="openCreateDialog">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        新建智能体
      </button>
    </div>

    <!-- 主 Agent 配置 -->
    <div class="main-agent-card">
      <div class="card-header">
        <span class="card-icon main-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v6m0 10v6m11-11h-6m-10 0H1m17.5-6.5l-4.24 4.24M9.74 14.26 5.5 18.5m13 0-4.24-4.24M9.74 9.74 5.5 5.5"/>
          </svg>
        </span>
        <h3 class="card-title">主 Agent</h3>
        <span class="status-pill pill-ok">核心</span>
        <button type="button" class="btn-text" @click="openMainAgentDialog">配置</button>
      </div>
      <p class="card-content">主 Agent 可使用的技能与 MCP。未勾选的技能/MCP 不会加载到主 Agent 的工具列表中。</p>
      <div class="card-tags">
        <span v-for="s in mainAgentSkills" :key="'ms-' + s" class="tag tag-skill">技能 · {{ s }}</span>
        <span v-for="m in mainAgentMcps" :key="'mm-' + m" class="tag tag-mcp">MCP · {{ m }}</span>
        <span v-if="mainAgentSkills.length === 0 && mainAgentMcps.length === 0" class="tag tag-empty">未配置（无技能与 MCP）</span>
      </div>
    </div>

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
            <span class="meta-value">{{ agent.model || '—' }}</span>
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
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          {{ agent.unavailable_reason || '依赖检查未通过' }}
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

          <div class="form-row">
            <label class="form-label">主模型</label>
            <select v-model="form.model" class="form-input">
              <option value="">使用默认模型</option>
              <option v-for="m in availableModels" :key="m.id" :value="m.model">{{ m.model }}</option>
            </select>
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
                <span class="cb-tag tag-on">有效</span>
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

    <!-- 主 Agent 配置弹窗 -->
    <div v-if="mainAgentDialogVisible" class="modal-overlay" @click="mainAgentDialogVisible = false">
      <div class="modal-dialog modal-large" @click.stop>
        <div class="modal-header">主 Agent 配置</div>
        <div class="modal-body">
          <div class="form-row">
            <label class="form-label">可使用技能</label>
            <div class="checkbox-list">
              <div v-if="skills.length === 0" class="checkbox-empty">未发现任何技能</div>
              <label v-for="sk in skills" :key="sk.folder_name" class="checkbox-item">
                <input
                  type="checkbox"
                  :value="sk.folder_name"
                  :checked="mainAgentForm.allowed_skills.includes(sk.folder_name)"
                  @change="toggleMainAgentSkill(sk.folder_name)"
                />
                <span class="cb-name">{{ sk.name }}</span>
                <span class="cb-desc" :title="sk.description">{{ sk.description || '（无描述）' }}</span>
              </label>
            </div>
            <p class="form-hint">不勾选任何技能 = 主 Agent 无技能可用。勾选后主 Agent 只能使用选中的技能。</p>
          </div>

          <div class="form-row">
            <label class="form-label">可使用 MCP</label>
            <div class="checkbox-list">
              <div v-if="plugins.length === 0" class="checkbox-empty">未发现任何 MCP</div>
              <label v-for="mc in plugins" :key="mc.id" class="checkbox-item">
                <input
                  type="checkbox"
                  :value="mc.id"
                  :checked="mainAgentForm.allowed_mcps.includes(mc.id)"
                  @change="toggleMainAgentMcp(mc.id)"
                />
                <span class="cb-name">{{ mc.name }}</span>
                <span class="cb-desc" :title="mc.description">{{ mc.description || '（无描述）' }}</span>
              </label>
            </div>
            <p class="form-hint">不勾选任何 MCP = 主 Agent 无 MCP 可用。勾选后主 Agent 只能使用选中的 MCP。</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="mainAgentDialogVisible = false">取消</button>
          <button class="modal-btn modal-btn-confirm" :disabled="saving" @click="saveMainAgent">
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
import { getMainAgentConfig, saveMainAgentConfig, type MainAgentConfig } from '@/api/mainAgent'

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

// ---------- 主 Agent 配置 ----------
const mainAgentConfig = ref<MainAgentConfig>({ allowed_skills: [], allowed_mcps: [] })
const mainAgentSkills = computed(() => mainAgentConfig.value.allowed_skills)
const mainAgentMcps = computed(() => mainAgentConfig.value.allowed_mcps)
const mainAgentDialogVisible = ref(false)
const mainAgentForm = reactive<{ allowed_skills: string[]; allowed_mcps: string[] }>({
  allowed_skills: [],
  allowed_mcps: [],
})

async function loadMainAgentConfig() {
  try {
    mainAgentConfig.value = await getMainAgentConfig()
  } catch (e) {
    console.error('加载主 Agent 配置失败', e)
  }
}

function openMainAgentDialog() {
  mainAgentForm.allowed_skills = [...mainAgentConfig.value.allowed_skills]
  mainAgentForm.allowed_mcps = [...mainAgentConfig.value.allowed_mcps]
  mainAgentDialogVisible.value = true
}

function toggleMainAgentSkill(folderName: string) {
  const idx = mainAgentForm.allowed_skills.indexOf(folderName)
  if (idx >= 0) mainAgentForm.allowed_skills.splice(idx, 1)
  else mainAgentForm.allowed_skills.push(folderName)
}

function toggleMainAgentMcp(id: string) {
  const idx = mainAgentForm.allowed_mcps.indexOf(id)
  if (idx >= 0) mainAgentForm.allowed_mcps.splice(idx, 1)
  else mainAgentForm.allowed_mcps.push(id)
}

async function saveMainAgent() {
  saving.value = true
  try {
    await saveMainAgentConfig({
      allowed_skills: [...mainAgentForm.allowed_skills],
      allowed_mcps: [...mainAgentForm.allowed_mcps],
    })
    mainAgentConfig.value = {
      allowed_skills: [...mainAgentForm.allowed_skills],
      allowed_mcps: [...mainAgentForm.allowed_mcps],
    }
    mainAgentDialogVisible.value = false
  } catch (e) {
    errorMessage.value = (e as Error).message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [agents, sk, pl] = await Promise.all([
      listSubagents(),
      listSkills().then((r) => r.skills),
      listPlugins(),
    ])
    subagents.value = agents
    skills.value = sk
    plugins.value = pl.plugins
    await loadMainAgentConfig()
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
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.secondary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.secondary-btn:hover {
  background: var(--accent-hover);
  border-color: var(--border);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 220px;
  color: var(--text-muted);
  gap: 12px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.subagent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.subagent-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.15s;
}

.subagent-card:hover {
  border-color: var(--border-strong);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.subagent-card.is-disabled {
  opacity: 0.62;
}

.subagent-card.is-unavailable {
  border-color: rgba(255, 149, 0, 0.5);
}

/* 主 Agent 卡片 */
.main-agent-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.main-icon {
  background: rgba(45, 122, 79, 0.12) !important;
  color: #2d7a4f !important;
}

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

.pill-ok {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

.pill-warn {
  background: rgba(255, 149, 0, 0.12);
  color: #ff9500;
}

.pill-disabled {
  background: rgba(128, 128, 128, 0.15);
  color: #888;
}

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

.meta-item {
  display: inline-flex;
  gap: 4px;
}

.meta-label {
  opacity: 0.7;
}

.meta-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

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

.tag-skill {
  background: rgba(74, 144, 217, 0.1);
  color: #4a90d9;
}

.tag-mcp {
  background: rgba(155, 89, 182, 0.12);
  color: #9b59b6;
}

.tag-empty {
  background: transparent;
  color: var(--text-muted);
  font-style: italic;
}

.warn-line {
  display: flex;
  align-items: center;
  gap: 6px;
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

.card-actions {
  display: flex;
  gap: 6px;
}

.btn-text {
  background: transparent;
  border: none;
  color: var(--accent, #4a90d9);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.btn-text:hover {
  background: rgba(74, 144, 217, 0.08);
}

.btn-text.btn-danger {
  color: #ff3b30;
}

.btn-text.btn-danger:hover {
  background: rgba(255, 59, 48, 0.08);
}

/* Toggle switch */
.switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.switch input {
  display: none;
}

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

.switch input:checked + .slider {
  background: #4a90d9;
}

.switch input:checked + .slider::before {
  transform: translateX(14px);
}

.switch-label {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
}

.modal-dialog {
  background: var(--bg-panel, #fff);
  border-radius: 12px;
  width: 480px;
  max-width: 92vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.22);
}

.modal-large {
  width: 640px;
}

.modal-header {
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  color: var(--text);
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

.modal-btn-cancel:hover {
  background: rgba(0, 0, 0, 0.04);
}

.modal-btn-confirm {
  background: #4a90d9;
  color: #fff;
  border-color: #4a90d9;
}

.modal-btn-confirm:hover {
  opacity: 0.88;
}

.modal-btn-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.modal-btn-danger {
  background: #ff3b30;
  color: #fff;
  border-color: #ff3b30;
}

.modal-btn-danger:hover {
  opacity: 0.88;
}

.modal-btn-danger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Form */
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.required {
  color: #ff3b30;
  margin-left: 2px;
}

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

.form-textarea {
  resize: vertical;
  min-height: 100px;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #4a90d9;
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

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

.checkbox-item:hover {
  background: rgba(74, 144, 217, 0.06);
}

.checkbox-item input[type="checkbox"] {
  cursor: pointer;
}

.cb-name {
  font-weight: 500;
  color: var(--text);
}

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

.tag-on {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

.tag-off {
  background: rgba(128, 128, 128, 0.15);
  color: #888;
}

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
  z-index: 1200;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(255, 59, 48, 0.3);
}
</style>
