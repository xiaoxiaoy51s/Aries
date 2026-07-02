<template>
  <div>
    <div class="header-row">
      <p style="font-size: 14px; color: #6b7280; margin: 0;">
        检测系统 PATH 中的 AI 编码代理 CLI，手动连接未自动找到的工具。
      </p>
      <button type="button" class="primary-btn sm" @click="showAddDialog = true">+ 添加自定义 CLI</button>
    </div>

    <!-- 检测中 -->
    <div v-if="loading" style="padding: 32px 0; text-align: center; color: #9ca3af; font-size: 14px;">检测中...</div>

    <!-- 工具网格 -->
    <div v-else class="tool-grid">
      <div
        v-for="tool in tools"
        :key="tool.id"
        class="tool-card"
        :class="{ connected: tool.connected }"
      >
        <div class="tool-top">
          <div
            class="tool-icon-wrap"
            :style="{
              background: tool.connected ? vendorBg(tool.vendor) : '#f3f4f6',
              color: tool.connected ? vendorColor(tool.vendor) : '#9ca3af',
            }"
          >
            <svg v-if="tool.connected" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <div class="tool-info">
            <div class="tool-name">
              {{ tool.name }}
              <span v-if="tool.custom" class="custom-tag">自定义</span>
            </div>
            <div class="tool-desc">{{ tool.description }}</div>
          </div>
          <span class="tool-badge" :class="tool.connected ? 'badge-on' : 'badge-off'">
            {{ tool.connected ? '已连接' : '未连接' }}
          </span>
        </div>

        <div class="tool-path">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span class="path-text">{{ tool.path || '未检测到路径' }}</span>
          <span v-if="tool.source === 'manual'" class="source-tag">手动</span>
        </div>

        <!-- 路由配置摘要 -->
        <div v-if="tool.routing_config && tool.connected" class="tool-routing">
          <span class="routing-label">调用方式:</span>
          <code class="routing-cmd">{{ buildCmdPreview(tool) }}</code>
        </div>

        <!-- 操作按钮 -->
        <div class="tool-actions" :class="{ 'space-between': tool.custom }">
          <template v-if="tool.custom">
            <button type="button" class="btn-text danger" @click="deleteCustomCLI(tool.id)">删除</button>
          </template>
          <div>
            <template v-if="tool.connected">
              <button type="button" class="btn-text danger" @click="disconnect(tool.id)">断开</button>
            </template>
            <template v-else>
              <button type="button" class="secondary-btn sm" @click="startConnect(tool)">手动连接</button>
            </template>
          </div>
        </div>
      </div>
    </div>

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
            <button type="button" class="primary-btn sm" :disabled="!connectDialog.path.trim()" @click="confirmConnect">确认连接</button>
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
              <button type="button" class="secondary-btn sm" @click="browseAddCLI">选择文件</button>
            </div>
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn-text" @click="showAddDialog = false">取消</button>
            <button type="button" class="primary-btn sm" :disabled="!addPath.trim()" @click="confirmAddCLI">添加</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'

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

/* 厂商配色 */
const VENDOR_COLORS: Record<string, string> = {
  anthropic:  '#d4a574',
  openai:     '#10a37f',
  opencode:   '#6366f1',
  xiaomi:     '#ff6700',
  bytedance:  '#3b82f6',
  tencent:    '#07c160',
  qoder:      '#8b5cf6',
  google:     '#4285f4',
  moonshot:   '#a855f7',
  microsoft:  '#0078d4',
  cursor:     '#f59e0b',
}

function vendorColor(vendor: string): string {
  return VENDOR_COLORS[vendor] || '#6b7280'
}
function vendorBg(vendor: string): string {
  const c = VENDOR_COLORS[vendor]
  if (!c) return 'rgba(107,114,128,0.1)'
  const r = parseInt(c.slice(1, 3), 16)
  const g = parseInt(c.slice(3, 5), 16)
  const b = parseInt(c.slice(5, 7), 16)
  return `rgba(${r},${g},${b},0.12)`
}

function buildCmdPreview(tool: ToolInfo): string {
  const rc = tool.routing_config
  if (!rc) return tool.id
  const parts = [tool.id]
  if (rc.extra_args?.length) parts.push(...rc.extra_args)
  if (rc.prompt_flag) parts.push(rc.prompt_flag)
  parts.push('{prompt}')
  return parts.join(' ')
}

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
    const resp = await fetch('/api/tools/detect')
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
    const resp = await fetch('/api/tools/connect', {
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
    await fetch('/api/tools/disconnect', {
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
    const resp = await fetch('/api/tools/custom', {
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
    const resp = await fetch(`/api/tools/custom/${cliId}`, { method: 'DELETE' })
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
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

/* 卡片：白色背景，与 Clutch 一致 */
.tool-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.tool-card.connected {
  border-color: #22c55e;
}
.tool-card:hover {
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.tool-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tool-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-name {
  font-size: 14px;
  font-weight: 500;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 6px;
}

.custom-tag {
  font-size: 10px;
  font-weight: 500;
  color: #8b5cf6;
  background: #f5f3ff;
  padding: 1px 6px;
  border-radius: 4px;
}

.tool-desc {
  font-size: 12px;
  color: #6b7280;
  margin-top: 1px;
}

/* 状态徽章 */
.tool-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
  flex-shrink: 0;
  font-weight: 500;
}
.badge-on {
  background: #f0fdf4;
  color: #16a34a;
}
.badge-off {
  background: #f9fafb;
  color: #9ca3af;
}

/* 路径栏 */
.tool-path {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6b7280;
  padding: 6px 8px;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  border-radius: 6px;
}
.path-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #fef3c7;
  color: #d97706;
  font-weight: 500;
}

/* 路由预览 */
.tool-routing {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 4px 8px;
  background: #f9fafb;
  border-radius: 6px;
}
.routing-label {
  color: #6b7280;
  white-space: nowrap;
}
.routing-cmd {
  font-family: 'JetBrains Mono', 'Cascadia Code', 'SF Mono', Consolas, monospace;
  font-size: 11px;
  color: #374151;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 2px;
}
.tool-actions.space-between {
  justify-content: space-between;
}

/* 按钮 */
.secondary-btn.sm {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.secondary-btn.sm:hover {
  background: #f9fafb;
  border-color: #9ca3af;
}

.btn-text.danger {
  color: #ef4444;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
  font-weight: 500;
}
.btn-text.danger:hover {
  background: #fef2f2;
}

.primary-btn.sm {
  padding: 6px 16px;
  font-size: 13px;
  background: #4f46e5;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  font-weight: 500;
}
.primary-btn.sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.primary-btn.sm:not(:disabled):hover {
  background: #4338ca;
}

.btn-text {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background 0.15s, color 0.15s;
}
.btn-text:hover {
  background: #f3f4f6;
  color: #374151;
}

/* 对话框 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.dialog-box {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 4px 24px rgba(0,0,0,0.12);
}
.dialog-box.wide {
  width: 600px;
}
.dialog-box h3 {
  margin: 0 0 6px;
  font-size: 16px;
  color: #111827;
}
.dialog-desc {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 16px;
}
.input-row {
  margin-bottom: 16px;
}
.input-with-btn {
  display: flex;
  gap: 8px;
}
.input-with-btn .input-box {
  flex: 1;
}
.input-box {
  width: 100%;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #111827;
  outline: none;
  box-sizing: border-box;
}
.input-box:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 2px rgba(79,70,229,0.12);
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 添加自定义的对话框不需要额外样式了 */
</style>
