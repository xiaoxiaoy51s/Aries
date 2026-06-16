<template>
  <section id="skillsPage" class="page">
    <div class="page-top">
      <div class="tab-bar">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'plugins' }"
          @click="activeTab = 'plugins'"
        >
          插件
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'skills' }"
          @click="activeTab = 'skills'"
        >
          技能
        </button>
      </div>
      <div class="top-actions">
        <button type="button" class="icon-action" title="添加" @click="showAddDialog = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
        </button>
        <button type="button" class="icon-action" title="刷新" :disabled="loading" @click="refresh">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"/>
            <path d="M21 3v6h-6"/>
          </svg>
        </button>
      </div>
    </div>

    <header class="page-header">
      <h1>{{ activeTab === 'plugins' ? '插件' : '技能' }}</h1>
      <p class="page-desc">
        {{ activeTab === 'plugins'
          ? '在 mcp.json 中配置 MCP 服务（支持 stdio / HTTP / SSE），启用后 Agent 可调用其工具'
          : '通过任务专用技能扩展 Agent 的能力' }}
      </p>
      <p v-if="activeTab === 'plugins' && configPath" class="config-path">
        配置文件：<code>{{ configPath }}</code>
        <span class="config-hint">（也可直接编辑该文件，参考同目录下的 mcp.example.json）</span>
      </p>
    </header>

    <div class="toolbar">
      <div class="search-box">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="m21 21-4.3-4.3"/>
        </svg>
        <input
          v-model="query"
          type="search"
          placeholder="搜索插件和技能"
        />
      </div>
      <button
        type="button"
        class="filter-btn"
        :class="{ active: filterEnabledOnly }"
        title="仅显示已启用"
        @click="filterEnabledOnly = !filterEnabledOnly"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>
        </svg>
      </button>
    </div>

    <div v-if="loading" class="state-msg">加载中...</div>
    <div v-else-if="error" class="state-msg error">{{ error }}</div>
    <div v-else class="content">
      <div v-if="activeTab === 'plugins' && currentItems.length === 0" class="empty-panel">
        <p>尚未配置 MCP 插件。</p>
        <p>请在 <code>{{ configPath || '~/.MIMOClaw/mcp.json' }}</code> 中自行添加，或点击右上角 + 通过界面添加。</p>
      </div>

      <section v-else class="group-section">
        <h2 v-if="activeTab === 'skills'" class="group-title">个人</h2>
        <h2 v-else class="group-title">已配置</h2>
        <ul class="item-list">
          <li
            v-for="item in visibleItems"
            :key="item.key"
            class="item-row"
            @click="openDetail(item)"
          >
            <div class="item-icon" :class="`kind-${item.kind}`">
              {{ item.icon }}
            </div>
            <div class="item-body">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-desc">
                {{ item.description || '无描述' }}
                <span v-if="item.toolCount" class="tool-count">{{ item.toolCount }} 个工具</span>
              </div>
            </div>
            <button
              type="button"
              class="status-btn"
              :class="{ enabled: item.enabled }"
              :title="item.enabled ? '已启用，点击关闭' : '已关闭，点击启用'"
              @click.stop="toggleItem(item)"
            >
              <svg v-if="item.enabled" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M20 6 9 17l-5-5"/>
              </svg>
            </button>
          </li>
        </ul>
        <button
          v-if="hiddenCount > 0"
          type="button"
          class="show-more"
          @click="expanded = true"
        >
          查看 {{ hiddenPreview }} 等另外 {{ hiddenCount }} 项
        </button>
      </section>
    </div>

    <div v-if="showAddDialog" class="modal-overlay" @click.self="showAddDialog = false">
      <div class="modal-card modal-card-wide">
        <div class="modal-header">
          <h3>{{ activeTab === 'plugins' ? '手动配置' : '添加技能' }}</h3>
          <button type="button" class="modal-close" @click="showAddDialog = false">&times;</button>
        </div>
        <div class="modal-body">
          <template v-if="activeTab === 'plugins'">
            <p class="hint-text">
              请从 MCP Servers 介绍页复制配置 JSON（优先使用 NPX 或 UVX 配置），粘贴到下方输入框。
              保存到 <code>{{ configPath || '~/.MIMOClaw/mcp.json' }}</code>，名称自动取 <code>mcpServers</code> 中的键名。
            </p>
            <label class="field">
              <textarea
                v-model="configJsonText"
                class="json-editor"
                rows="14"
                spellcheck="false"
                placeholder='{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}'
              />
            </label>
            <p class="warn-text">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              配置前请确认来源，甄别风险
            </p>
          </template>
          <template v-else>
            <p class="hint-text">
              请将技能目录放入 <code>~/.MIMOClaw/skills/available/</code>，并确保包含 <code>SKILL.md</code> 文件，然后点击刷新。
            </p>
          </template>
          <p v-if="addError" class="add-error">{{ addError }}</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="showAddDialog = false">取消</button>
          <button
            v-if="activeTab === 'plugins'"
            type="button"
            class="btn-primary"
            :disabled="addBusy"
            @click="submitImportPlugins"
          >
            {{ addBusy ? '保存中...' : '确认' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="closeDetail">
      <div class="detail-card">
        <div class="detail-header">
          <div class="detail-title-row">
            <div class="item-icon" :class="`kind-${detailKind}`">{{ detailIcon }}</div>
            <div class="detail-titles">
              <h3>{{ detailTitle }}</h3>
              <p class="detail-subtitle">{{ detailSubtitle }}</p>
            </div>
          </div>
          <div class="detail-header-actions">
            <label class="toggle-switch" :title="detailEnabled ? '已启用' : '已禁用'">
              <input
                type="checkbox"
                :checked="detailEnabled"
                :disabled="detailBusy"
                @change="toggleDetailEnabled"
              />
              <span class="toggle-slider" />
            </label>
            <button type="button" class="modal-close" @click="closeDetail">&times;</button>
          </div>
        </div>

        <div class="detail-body">
          <div v-if="detailLoading" class="state-msg">加载中...</div>
          <div v-else-if="detailError" class="state-msg error">{{ detailError }}</div>
          <template v-else>
            <p v-if="detailMeta" class="detail-meta">{{ detailMeta }}</p>
            <div v-if="detailContentType === 'markdown'" class="detail-markdown">
              <MarkdownRenderer :content="detailContent" :show-actions="false" :font-size="14" />
            </div>
            <pre v-else class="detail-json">{{ detailContent }}</pre>
          </template>
        </div>

        <div class="detail-footer">
          <p v-if="detailPathHint" class="detail-path">
            <code>{{ detailPathHint }}</code>
          </p>
          <button
            type="button"
            class="btn-open-path"
            :disabled="!detailOpenPath || detailLoading"
            @click="openDetailLocation"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            打开文件位置
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { getSkillDetail, listSkills, updateSkillStatus, type SkillItem } from '@/api/skills'
import { getPluginDetail, importPlugins, listPlugins, refreshPlugins, updatePluginStatus, type PluginItem } from '@/api/plugins'
import { openPath } from '@/api/system'

type TabKind = 'plugins' | 'skills'

interface ListItem {
  key: string
  kind: TabKind
  id: string
  name: string
  description: string
  enabled: boolean
  icon: string
  toolCount?: number
}

const SECTION_LIMIT = 5

const activeTab = ref<TabKind>('skills')
const query = ref('')
const filterEnabledOnly = ref(false)
const loading = ref(true)
const error = ref('')
const skills = ref<SkillItem[]>([])
const plugins = ref<PluginItem[]>([])
const configPath = ref('')
const cacheRoot = ref('')
const expanded = ref(false)
const showAddDialog = ref(false)
const addBusy = ref(false)
const addError = ref('')
const configJsonText = ref('')

const showDetail = ref(false)
const detailLoading = ref(false)
const detailBusy = ref(false)
const detailError = ref('')
const detailKind = ref<TabKind>('skills')
const detailId = ref('')
const detailTitle = ref('')
const detailSubtitle = ref('')
const detailEnabled = ref(false)
const detailContent = ref('')
const detailContentType = ref<'markdown' | 'json'>('markdown')
const detailOpenPath = ref('')
const detailPathHint = ref('')
const detailMeta = ref('')
const detailIcon = ref('⚡')

function skillIcon(name: string): string {
  const first = name.trim().charAt(0).toUpperCase()
  return first || '⚡'
}

function pluginIcon(id: string): string {
  return id.trim().charAt(0).toUpperCase() || '🔌'
}

function mapSkills(): ListItem[] {
  return skills.value.map((skill) => ({
    key: `skill:${skill.folder_name}`,
    kind: 'skills',
    id: skill.folder_name,
    name: skill.name,
    description: skill.description,
    enabled: skill.enabled,
    icon: skillIcon(skill.name),
  }))
}

function mapPlugins(): ListItem[] {
  return plugins.value.map((plugin) => ({
    key: `plugin:${plugin.id}`,
    kind: 'plugins',
    id: plugin.id,
    name: plugin.id,
    description: plugin.last_error
      ? `连接异常：${plugin.last_error}`
      : plugin.description,
    enabled: plugin.enabled,
    icon: pluginIcon(plugin.id),
    toolCount: plugin.tool_count,
  }))
}

const currentItems = computed(() => {
  const source = activeTab.value === 'skills' ? mapSkills() : mapPlugins()
  const normalized = query.value.trim().toLowerCase()
  return source.filter((item) => {
    if (filterEnabledOnly.value && !item.enabled) return false
    if (!normalized) return true
    return (
      item.name.toLowerCase().includes(normalized) ||
      item.description.toLowerCase().includes(normalized) ||
      item.id.toLowerCase().includes(normalized)
    )
  })
})

const visibleItems = computed(() => {
  if (expanded.value) return currentItems.value
  return currentItems.value.slice(0, SECTION_LIMIT)
})

const hiddenCount = computed(() => {
  if (expanded.value) return 0
  return Math.max(0, currentItems.value.length - SECTION_LIMIT)
})

const hiddenPreview = computed(() => {
  return currentItems.value
    .slice(SECTION_LIMIT, SECTION_LIMIT + 2)
    .map((item) => item.name)
    .join(', ')
})

async function fetchAll() {
  try {
    loading.value = true
    error.value = ''
    const [skillData, pluginResult] = await Promise.all([listSkills(), listPlugins()])
    skills.value = skillData
    plugins.value = pluginResult.plugins
    configPath.value = pluginResult.configPath
    cacheRoot.value = pluginResult.cacheRoot
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function refresh() {
  try {
    if (activeTab.value === 'plugins') {
      await refreshPlugins()
    }
    await fetchAll()
    error.value = ''
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '刷新失败'
  }
}

async function toggleItem(item: ListItem) {
  const nextEnabled = !item.enabled
  try {
    if (item.kind === 'skills') {
      await updateSkillStatus(item.id, nextEnabled)
      const target = skills.value.find((skill) => skill.folder_name === item.id)
      if (target) target.enabled = nextEnabled
    } else {
      await updatePluginStatus(item.id, nextEnabled)
      const target = plugins.value.find((plugin) => plugin.id === item.id)
      if (target) target.enabled = nextEnabled
    }
    if (showDetail.value && detailId.value === item.id && detailKind.value === item.kind) {
      detailEnabled.value = nextEnabled
    }
    error.value = ''
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '更新状态失败'
  }
}

function closeDetail() {
  showDetail.value = false
  detailError.value = ''
  detailContent.value = ''
}

async function openDetail(item: ListItem) {
  showDetail.value = true
  detailKind.value = item.kind
  detailId.value = item.id
  detailTitle.value = item.name
  detailSubtitle.value = item.description || (item.kind === 'plugins' ? 'MCP 插件' : 'Agent 技能')
  detailEnabled.value = item.enabled
  detailIcon.value = item.icon
  detailContent.value = ''
  detailContentType.value = item.kind === 'skills' ? 'markdown' : 'json'
  detailOpenPath.value = ''
  detailPathHint.value = ''
  detailMeta.value = ''
  detailLoading.value = true
  detailError.value = ''

  try {
    if (item.kind === 'skills') {
      const data = await getSkillDetail(item.id)
      detailTitle.value = data.name
      detailSubtitle.value = data.description || 'Agent 技能'
      detailEnabled.value = data.enabled
      detailContent.value = data.content
      detailOpenPath.value = data.skill_md_path
      detailPathHint.value = data.skill_md_path
    } else {
      const data = await getPluginDetail(item.id)
      detailTitle.value = data.name
      detailSubtitle.value = data.description || 'MCP 插件'
      detailEnabled.value = data.enabled
      detailContent.value = data.config_json
      detailOpenPath.value = data.config_path
      detailPathHint.value = data.config_path
      const parts: string[] = []
      if (data.tool_count != null) parts.push(`${data.tool_count} 个工具`)
      if (data.status) parts.push(`状态：${data.status}`)
      if (data.last_error) parts.push(`异常：${data.last_error}`)
      detailMeta.value = parts.join(' · ')
    }
  } catch (e: unknown) {
    detailError.value = e instanceof Error ? e.message : '加载详情失败'
  } finally {
    detailLoading.value = false
  }
}

async function toggleDetailEnabled() {
  if (!detailId.value || detailBusy.value) return
  const nextEnabled = !detailEnabled.value
  detailBusy.value = true
  try {
    if (detailKind.value === 'skills') {
      await updateSkillStatus(detailId.value, nextEnabled)
      const target = skills.value.find((skill) => skill.folder_name === detailId.value)
      if (target) target.enabled = nextEnabled
    } else {
      await updatePluginStatus(detailId.value, nextEnabled)
      const target = plugins.value.find((plugin) => plugin.id === detailId.value)
      if (target) target.enabled = nextEnabled
    }
    detailEnabled.value = nextEnabled
    error.value = ''
  } catch (e: unknown) {
    detailError.value = e instanceof Error ? e.message : '更新状态失败'
  } finally {
    detailBusy.value = false
  }
}

async function openDetailLocation() {
  if (!detailOpenPath.value) return
  try {
    await openPath(detailOpenPath.value)
  } catch (e: unknown) {
    detailError.value = e instanceof Error ? e.message : '打开路径失败'
  }
}

async function submitImportPlugins() {
  addError.value = ''
  if (!configJsonText.value.trim()) {
    addError.value = '请粘贴 MCP JSON 配置'
    return
  }
  addBusy.value = true
  try {
    await importPlugins(configJsonText.value.trim())
    configJsonText.value = ''
    showAddDialog.value = false
    await fetchAll()
  } catch (e: unknown) {
    addError.value = e instanceof Error ? e.message : '导入失败'
  } finally {
    addBusy.value = false
  }
}

watch(activeTab, () => {
  query.value = ''
  filterEnabledOnly.value = false
  expanded.value = false
  addError.value = ''
})

watch(showAddDialog, (open) => {
  if (!open) {
    addError.value = ''
  }
})

onMounted(fetchAll)
</script>

<style scoped>
.page {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  background: var(--bg-app);
}

.page-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px 0;
  flex-shrink: 0;
}

.tab-bar {
  display: inline-flex;
  padding: 4px;
  border-radius: 12px;
  background: #ececea;
}

.tab-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  padding: 8px 18px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tab-btn.active {
  background: var(--bg-panel);
  color: var(--text);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.top-actions {
  display: flex;
  gap: 8px;
}

.icon-action {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.icon-action:hover:not(:disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.icon-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-header {
  padding: 28px 32px 0;
  flex-shrink: 0;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 6px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-secondary);
}

.config-path {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.config-path code,
.hint-text code,
.empty-panel code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  background: #f3f3f1;
  padding: 1px 5px;
  border-radius: 4px;
}

.config-hint {
  margin-left: 6px;
  color: var(--text-muted);
}

.empty-panel {
  padding: 40px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.toolbar {
  display: flex;
  gap: 10px;
  padding: 20px 32px 0;
  flex-shrink: 0;
}

.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 42px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--bg-panel);
  color: var(--text-secondary);
}

.search-box input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  color: var(--text);
}

.filter-btn {
  width: 42px;
  height: 42px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.filter-btn.active {
  background: #eef4ff;
  border-color: #c8d9f8;
  color: #3b5bdb;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 32px 32px;
}

.group-section + .group-section {
  margin-top: 28px;
}

.group-title {
  font-size: 18px;
  font-weight: 600;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.item-list {
  list-style: none;
}

.item-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 72px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.12s;
}

.item-row:hover {
  background: rgba(0, 0, 0, 0.015);
}

.item-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #f1f1ef;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.item-icon.kind-plugins {
  background: #eef4ff;
}

.item-body {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 2px;
}

.item-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.status-btn {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
}

.status-btn.enabled {
  color: #8a8a84;
}

.show-more {
  margin-top: 8px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  padding: 6px 0;
}

.show-more:hover {
  color: var(--text);
}

.group-empty,
.state-msg {
  padding: 24px 0;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.state-msg.error,
.add-error {
  color: #d93025;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-card {
  width: min(480px, calc(100vw - 32px));
  background: var(--bg-panel);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
}

.modal-card-wide {
  width: min(640px, calc(100vw - 32px));
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.modal-close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
}

.modal-body {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.field input,
.field textarea,
.json-editor {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  color: var(--text);
  background: var(--bg-panel);
  outline: none;
  width: 100%;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1.5;
  resize: vertical;
}

.json-editor {
  min-height: 280px;
}

.warn-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #b45309;
}

.tool-count {
  margin-left: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.field input:focus,
.field textarea:focus {
  border-color: #c8d9f8;
}

.hint-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.hint-text code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  background: #f3f3f1;
  padding: 1px 5px;
  border-radius: 4px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px 18px;
}

.btn-secondary,
.btn-primary {
  border-radius: 10px;
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
}

.btn-secondary {
  border: 1px solid var(--border);
  background: var(--bg-panel);
  color: var(--text);
}

.btn-primary {
  border: none;
  background: var(--send-bg);
  color: #fff;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.detail-card {
  width: min(720px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  background: var(--bg-panel);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-panel);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.detail-titles {
  min-width: 0;
}

.detail-titles h3 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 4px;
}

.detail-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.detail-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.toggle-switch {
  position: relative;
  display: inline-flex;
  width: 44px;
  height: 24px;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: #d4d4d0;
  transition: background 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  top: 3px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.toggle-switch input:checked + .toggle-slider {
  background: #3b82f6;
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  min-height: 200px;
  max-height: min(520px, calc(100vh - 220px));
}

.detail-meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.detail-markdown {
  font-size: 14px;
  line-height: 1.6;
}

.detail-json {
  margin: 0;
  padding: 14px 16px;
  border-radius: 12px;
  background: #f6f6f4;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
}

.detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.detail-path {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.detail-path code {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #f3f3f1;
  padding: 4px 8px;
  border-radius: 6px;
}

.btn-open-path {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: none;
  border-radius: 10px;
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  background: var(--send-bg);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
}

.btn-open-path:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
