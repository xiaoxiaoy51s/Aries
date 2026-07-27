<template>
  <div class="tools-page">
    <header class="tools-header">
      <div class="tools-header-top">
        <h2 class="tools-title">CLI 工具</h2>
        <div class="tools-header-actions">
          <div class="tools-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input v-model="searchQuery" type="search" placeholder="搜索工具..." />
          </div>
          <button type="button" class="btn-primary" @click="showAddDialog = true">+ 添加自定义 CLI</button>
        </div>
      </div>
      <p class="tools-desc">
        检测系统 PATH 中的 AI 编码代理 CLI，手动连接未自动找到的工具。
      </p>
    </header>

    <div v-if="loading" class="tools-loading">检测中...</div>

    <template v-else>
      <section class="tools-section">
        <div class="tools-list-panel">
          <div v-for="tool in visibleBuiltin" :key="tool.id" class="agent-row">
            <div class="agent-row-main">
              <div class="agent-avatar" :class="{ dimmed: !tool.connected }">
                <img v-if="hasPlatformLogo(tool.id)" :src="resolvePlatformLogo(tool.id)" :alt="tool.name" />
                <span v-else>{{ tool.name.slice(0, 1) }}</span>
              </div>
              <div class="agent-meta">
                <div class="agent-name-line">
                  <span class="agent-name">{{ tool.name }}</span>
                  <span v-if="tool.custom" class="custom-tag">自定义</span>
                  <span class="status-tag" :class="tool.connected ? 'online' : 'missing'">
                    {{ tool.connected ? '已连接' : '未连接' }}
                  </span>
                </div>
                <div v-if="tool.path" class="agent-path" :title="tool.path">{{ tool.path }}</div>
                <div v-if="tool.routing_config && tool.connected" class="agent-routing">
                  <span class="routing-label">调用方式:</span>
                  <code class="routing-cmd">{{ buildCmdPreview(tool) }}</code>
                </div>
              </div>
            </div>
            <div class="agent-row-actions">
              <template v-if="tool.connected">
                <button type="button" class="btn-outline" @click="disconnect(tool.id)">断开</button>
              </template>
              <template v-else-if="tool.connectable">
                <button type="button" class="btn-outline" @click="startConnect(tool)">手动连接</button>
              </template>
            </div>
          </div>
          <div v-if="visibleBuiltin.length === 0" class="tools-empty">
            {{ searchQuery.trim() ? '没有匹配的工具' : '暂无工具' }}
          </div>
        </div>
      </section>

      <section v-if="visibleCustom.length" class="tools-section">
        <div class="tools-section-head">
          <div class="tools-section-title">自定义 CLI</div>
        </div>
        <div class="tools-list-panel">
          <div v-for="tool in visibleCustom" :key="tool.id" class="agent-row">
            <div class="agent-row-main">
              <div class="agent-avatar" :class="{ dimmed: !tool.connected }">
                <img v-if="hasPlatformLogo(tool.id)" :src="resolvePlatformLogo(tool.id)" :alt="tool.name" />
                <span v-else>{{ tool.name.slice(0, 1) }}</span>
              </div>
              <div class="agent-meta">
                <div class="agent-name-line">
                  <span class="agent-name">{{ tool.name }}</span>
                  <span class="custom-tag">自定义</span>
                  <span class="status-tag" :class="tool.connected ? 'online' : 'missing'">
                    {{ tool.connected ? '已连接' : '未连接' }}
                  </span>
                </div>
                <div class="agent-path" :title="buildCmdPreview(tool)">{{ buildCmdPreview(tool) }}</div>
              </div>
            </div>
            <div class="agent-row-actions">
              <button v-if="tool.connected" type="button" class="btn-outline" @click="disconnect(tool.id)">断开</button>
              <button type="button" class="btn-outline danger" @click="deleteCustomCLI(tool.id)">删除</button>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- 手动连接对话框 -->
    <Teleport to="body">
      <div v-if="connectDialog.visible" class="dialog-overlay" @click.self="closeConnectDialog">
        <div class="dialog-box">
          <h3>连接 {{ connectDialog.name }}</h3>
          <p class="dialog-desc">输入 {{ connectDialog.name }} 可执行文件的完整路径，或在文件管理器中选择。</p>
          <div class="input-row">
            <input
              v-model="connectDialog.path"
              type="text"
              class="input-box"
              placeholder="例如 C:\Users\You\.local\bin\claude.exe"
              @keyup.enter="confirmConnect"
            />
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn-text" @click="closeConnectDialog">取消</button>
            <button type="button" class="btn-primary sm" :disabled="!connectDialog.path.trim()" @click="confirmConnect">确认连接</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 添加自定义 CLI 对话框 -->
    <Teleport to="body">
      <div v-if="showAddDialog" class="dialog-overlay" @click.self="showAddDialog = false">
        <div class="dialog-box">
          <h3>添加自定义 CLI 工具</h3>
          <p class="dialog-desc">选择可执行文件（.exe / .cmd / .bat / .ps1），后端自动提取名称等信息。可直接粘贴路径。</p>
          <div class="input-row">
            <div class="input-with-btn">
              <input
                v-model="addPath"
                type="text"
                class="input-box"
                placeholder="例如 D:\vsCode\Microsoft VS Code\bin\code.CMD"
                @keyup.enter="confirmAddCLI"
              />
              <button type="button" class="btn-outline" @click="browseAddCLI">选择文件</button>
            </div>
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn-text" @click="showAddDialog = false">取消</button>
            <button type="button" class="btn-primary sm" :disabled="!addPath.trim()" @click="confirmAddCLI">添加</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useModelStore } from '@/stores/model'
import { resolvePlatformLogo, hasPlatformLogo } from '@/utils/platformLogo'

const modelStore = useModelStore()
function getBaseUrl(): string {
  return modelStore.getBaseUrl()
}

interface RoutingConfig {
  prompt_flag?: string
  extra_args?: string[]
  conversation_mode?: string
}

interface ToolInfo {
  id: string
  name: string
  description: string
  vendor: string
  connectable: boolean
  system_installed: boolean
  system_path: string | null
  connected: boolean
  path: string | null
  source: string | null
  routing_config?: RoutingConfig
  custom?: boolean
}

const loading = ref(true)
const tools = ref<ToolInfo[]>([])
const showAddDialog = ref(false)
const searchQuery = ref('')

const connectDialog = reactive<{
  visible: boolean
  cliId: string
  name: string
  path: string
}>({
  visible: false,
  cliId: '',
  name: '',
  path: '',
})

const addPath = ref('')

const filteredTools = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return tools.value
  return tools.value.filter((t) =>
    t.name.toLowerCase().includes(q) ||
    (t.description || '').toLowerCase().includes(q) ||
    (t.id || '').toLowerCase().includes(q)
  )
})

const visibleBuiltin = computed(() => filteredTools.value.filter((t) => !t.custom))
const visibleCustom = computed(() => filteredTools.value.filter((t) => t.custom))

function buildCmdPreview(tool: ToolInfo): string {
  const rc = tool.routing_config
  if (!rc) return tool.id
  const parts = [tool.id]
  if (rc.extra_args?.length) parts.push(...rc.extra_args)
  if (rc.prompt_flag) parts.push(rc.prompt_flag)
  parts.push('{prompt}')
  return parts.join(' ')
}

async function browseAddCLI() {
  const electronAPI = (window as any).electronAPI
  if (electronAPI?.selectFile) {
    const result = await electronAPI.selectFile({
      title: '选择可执行文件',
      filters: [
        { name: '可执行文件', extensions: ['exe', 'cmd', 'bat', 'ps1'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    })
    if (result.cancelled || !result.path) return
    addPath.value = result.path
  }
}

async function fetchTools() {
  loading.value = true
  try {
    const resp = await fetch(`${getBaseUrl()}/api/tools/detect`)
    const data = await resp.json()
    tools.value = Object.values(data.tools) as ToolInfo[]
  } catch (e) {
    console.error('检测工具失败', e)
  } finally {
    loading.value = false
  }
}

function startConnect(tool: ToolInfo) {
  connectDialog.visible = true
  connectDialog.cliId = tool.id
  connectDialog.name = tool.name
  connectDialog.path = ''
}

function closeConnectDialog() {
  connectDialog.visible = false
  connectDialog.cliId = ''
  connectDialog.name = ''
  connectDialog.path = ''
}

async function confirmConnect() {
  const path = connectDialog.path.trim()
  if (!path) return
  try {
    const resp = await fetch(`${getBaseUrl()}/api/tools/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cli_id: connectDialog.cliId, path }),
    })
    const data = await resp.json()
    if (data.success) {
      await fetchTools()
    } else {
      alert(data.error || '连接失败')
    }
  } catch (e) {
    console.error('连接失败', e)
  } finally {
    closeConnectDialog()
  }
}

async function disconnect(cliId: string) {
  try {
    await fetch(`${getBaseUrl()}/api/tools/disconnect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cli_id: cliId }),
    })
    await fetchTools()
  } catch (e) {
    console.error('断开失败', e)
  }
}

async function confirmAddCLI() {
  const path = addPath.value.trim()
  if (!path) return
  try {
    const resp = await fetch(`${getBaseUrl()}/api/tools/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    const data = await resp.json()
    if (data.success) {
      showAddDialog.value = false
      addPath.value = ''
      await fetchTools()
    } else {
      alert(data.error || '添加失败')
    }
  } catch (e) {
    console.error('添加自定义CLI失败', e)
    alert('添加失败: 网络错误')
  }
}

async function deleteCustomCLI(cliId: string) {
  if (!confirm(`确定要删除自定义工具 "${cliId}" 吗？`)) return
  try {
    const resp = await fetch(`${getBaseUrl()}/api/tools/custom/${cliId}`, { method: 'DELETE' })
    const data = await resp.json()
    if (data.success) {
      await fetchTools()
    }
  } catch (e) {
    console.error('删除自定义CLI失败', e)
  }
}

onMounted(fetchTools)
</script>

<style scoped>
.tools-page { display: flex; flex-direction: column; gap: 16px; }
.tools-header-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.tools-title { margin: 0; font-size: 22px; font-weight: 700; color: #111827; }
.tools-header-actions { display: flex; align-items: center; gap: 8px; }
.tools-search {
  display: flex; align-items: center; gap: 6px; width: 200px; height: 32px;
  padding: 0 10px; border: 1px solid #e5e7eb; border-radius: 8px; color: #9ca3af;
}
.tools-search input { flex: 1; border: none; outline: none; font-size: 13px; color: #111827; background: transparent; }
.tools-desc { margin: 8px 0 0; font-size: 13px; line-height: 1.5; color: #6b7280; }
.tools-loading, .tools-empty { padding: 24px 12px; text-align: center; font-size: 12px; color: #9ca3af; }
.tools-section { display: flex; flex-direction: column; gap: 8px; }
.tools-section-title { font-size: 13px; font-weight: 500; color: #4b5563; }
.tools-list-panel {
  display: flex; flex-direction: column; gap: 8px; padding: 8px;
  border: 1px solid #e5e7eb; border-radius: 12px; background: #f9fafb;
}
.agent-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border-radius: 12px; border: 1px solid transparent; background: #fff;
}
.agent-row:hover { border-color: #e5e7eb; }
.agent-row-main { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
.agent-avatar {
  width: 32px; height: 32px; border-radius: 8px; overflow: hidden; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; background: #f3f4f6;
  font-size: 13px; font-weight: 700; color: #6b7280;
}
.agent-avatar.dimmed { opacity: 0.5; }
.agent-avatar img { width: 100%; height: 100%; object-fit: cover; }
.agent-meta { min-width: 0; flex: 1; }
.agent-name-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.agent-name {
  font-size: 14px; font-weight: 500; color: #111827;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.agent-path {
  margin-top: 2px; font-size: 11px; color: #9ca3af;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.agent-routing {
  display: flex; align-items: center; gap: 6px;
  margin-top: 4px; font-size: 11px;
}
.routing-label { color: #6b7280; white-space: nowrap; }
.routing-cmd {
  font-family: 'JetBrains Mono', 'Cascadia Code', 'SF Mono', Consolas, monospace;
  color: #374151; background: #f3f4f6; padding: 1px 5px; border-radius: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.status-tag {
  flex-shrink: 0; font-size: 11px; font-weight: 500; padding: 1px 8px;
  border-radius: 999px; line-height: 18px;
}
.status-tag.online { background: #f0fdf4; color: #16a34a; }
.status-tag.missing { background: #fef2f2; color: #dc2626; }
.status-tag.offline { background: #fff7ed; color: #ea580c; }
.status-tag.unchecked { background: #f3f4f6; color: #6b7280; }
.custom-tag {
  font-size: 10px; font-weight: 500; color: #8b5cf6; background: #f5f3ff;
  padding: 1px 6px; border-radius: 4px;
}
.agent-row-actions { display: flex; gap: 8px; flex-shrink: 0; }
.btn-outline {
  height: 30px; padding: 0 10px; border: 1px solid #e5e7eb; border-radius: 8px;
  background: #fff; color: #111827; font-size: 12px; font-weight: 500; cursor: pointer;
}
.btn-outline:hover:not(:disabled) { background: #f9fafb; }
.btn-outline:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-outline.danger { color: #dc2626; border-color: #fecaca; }
.btn-primary {
  height: 32px; padding: 0 14px; border: none; border-radius: 8px;
  background: #374151; color: #fff; font-size: 13px; font-weight: 500; cursor: pointer;
}
.btn-primary.sm { height: 30px; font-size: 12px; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-text { border: none; background: none; color: #6b7280; cursor: pointer; font-size: 13px; padding: 6px 12px; }
.dialog-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 2000;
}
.dialog-box {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
  padding: 24px; width: 480px; max-width: 90vw;
}
.dialog-box h3 { margin: 0 0 6px; font-size: 16px; }
.dialog-desc { font-size: 13px; color: #6b7280; margin: 0 0 16px; }
.input-row { margin-bottom: 16px; }
.input-with-btn { display: flex; gap: 8px; }
.input-with-btn .input-box { flex: 1; }
.input-box {
  width: 100%; padding: 8px 12px; font-size: 13px; border: 1px solid #d1d5db;
  border-radius: 6px; box-sizing: border-box;
}
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
