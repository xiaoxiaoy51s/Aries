<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <!-- 左侧导航 -->
        <nav class="modal-nav">
          <div class="modal-nav-header">
            <h1>设置</h1>
          </div>
          <ul class="modal-nav-list">
            <li
              :class="{ active: activeTab === 'models' }"
              @click="activeTab = 'models'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
              模型管理
            </li>
            <li
              :class="{ active: activeTab === 'accounts' }"
              @click="activeTab = 'accounts'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              账号绑定
            </li>
            <li
              :class="{ active: activeTab === 'paths' }"
              @click="activeTab = 'paths'; loadPathPermissions()"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              路径权限
            </li>
          </ul>
        </nav>

        <!-- 右侧内容 -->
        <div class="modal-body">
          <div class="modal-body-header">
            <h2>{{ tabTitle }}</h2>
            <button type="button" class="close-btn" @click="$emit('close')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div class="modal-body-content">
            <!-- 模型管理 -->
            <div v-if="activeTab === 'models'" class="settings-section">
              <div class="section-header">
                <span class="section-desc">管理可用的 AI 模型</span>
                <button type="button" class="secondary-btn" @click="openAddModal">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14"/>
                  </svg>
                  新增模型
                </button>
              </div>
              <div class="model-list">
                <div
                  v-for="model in modelStore.modelList"
                  :key="model.id"
                  class="model-item"
                  :class="{ active: model.isActive }"
                  @click="handleSetActive(model.id)"
                >
                  <div class="model-info">
                    <span class="model-name">{{ model.name }}</span>
                    <span v-if="model.isActive" class="model-tag">默认</span>
                  </div>
                  <div class="model-actions" @click.stop>
                    <button type="button" class="icon-btn-sm" title="编辑" @click="openEditModal(model)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                    <button
                      v-if="model.id !== 'default-vision'"
                      type="button"
                      class="icon-btn-sm delete"
                      title="删除"
                      @click="handleDelete(model.id)"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 账号绑定 -->
            <div v-if="activeTab === 'accounts' && !configPanel" class="settings-section">
              <p class="section-desc">绑定第三方账号以启用消息推送</p>
              <div class="account-bind-list">
                <div v-for="account in accountStore.accounts" :key="account.platform" class="account-item">
                  <div class="account-icon" :class="account.platform">
                    <img v-if="account.platform === 'feishu'" src="@/assets/feishu.svg" alt="飞书" />
                    <img v-else-if="account.platform === 'qq'" src="@/assets/qq.svg" alt="QQ" />
                    <img v-else src="@/assets/weixin.svg" alt="微信" />
                  </div>
                  <div class="account-info">
                    <span class="account-name">{{ account.name }}</span>
                    <span class="account-status" :class="{ bound: account.enabled && account.running }">
                      {{ account.enabled && account.running ? '已连接' : account.enabled ? '已启用' : account.configured ? '未启用' : '未配置' }}
                    </span>
                  </div>
                  <div class="account-actions">
                    <button
                      v-if="!account.configured"
                      type="button"
                      class="bind-btn"
                      @click="openConfigPanel(account.platform)"
                    >
                      配置
                    </button>
                    <template v-else>
                      <button
                        type="button"
                        class="bind-btn"
                        :class="{ bound: account.enabled }"
                        @click="handleBind(account.platform)"
                      >
                        {{ account.enabled ? '禁用' : '启用' }}
                      </button>
                      <button
                        type="button"
                        class="unbind-btn"
                        title="解绑账号"
                        @click="handleUnbind(account.platform)"
                      >
                        解绑
                      </button>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- QQ 配置面板 -->
            <div v-if="activeTab === 'accounts' && configPanel === 'qq'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>QQ 机器人配置</h3>
              </div>
              <div class="config-form">
                <label class="form-label">App ID</label>
                <input v-model="qqForm.app_id" type="text" class="form-input" placeholder="请输入 QQ 机器人 App ID" />
                <label class="form-label">App Secret</label>
                <input v-model="qqForm.app_secret" type="password" class="form-input" placeholder="请输入 App Secret" />
                <button type="button" class="form-submit-btn" :disabled="!qqForm.app_id || !qqForm.app_secret || configLoading" @click="saveQQ">
                  {{ configLoading ? '保存中...' : '保存并启用' }}
                </button>
              </div>
            </div>

            <!-- 微信配置面板（扫码） -->
            <div v-if="activeTab === 'accounts' && configPanel === 'wechat'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>微信绑定</h3>
              </div>
              <div class="qrcode-area">
                <template v-if="wechatQRImg">
                  <img :src="wechatQRImg" alt="微信二维码" class="qrcode-img" />
                  <p class="qrcode-tip">{{ wechatPollStatus === 'scaned' ? '已扫码，请在手机上确认' : '请使用微信扫码绑定' }}</p>
                </template>
                <template v-else>
                  <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startWechatQR">
                    {{ configLoading ? '获取中...' : '获取二维码' }}
                  </button>
                </template>
              </div>
            </div>

            <!-- 飞书配置面板（扫码） -->
            <div v-if="activeTab === 'accounts' && configPanel === 'feishu'" class="config-panel">
              <div class="config-panel-header">
                <button type="button" class="back-btn" @click="closeConfigPanel">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <h3>飞书绑定</h3>
              </div>
              <div class="qrcode-area">
                <template v-if="feishuQRImg">
                  <img :src="feishuQRImg" alt="飞书二维码" class="qrcode-img" />
                  <p class="qrcode-tip">{{ feishuPollStatus === 'pending' ? '请使用飞书 App 扫码授权' : '授权成功' }}</p>
                </template>
                <template v-else>
                  <button type="button" class="form-submit-btn" :disabled="configLoading" @click="startFeishuQR">
                    {{ configLoading ? '获取中...' : '获取二维码' }}
                  </button>
                </template>
              </div>
            </div>

            <!-- 路径权限 -->
            <div v-if="activeTab === 'paths'" class="settings-section">
              <p class="section-desc">管理 AI 可访问的路径。白名单路径 AI 可自由操作，黑名单路径 AI 无法访问（直接拒绝并告知用户限制）。</p>

              <!-- 白名单 -->
              <div class="path-section">
                <div class="path-section-header">
                  <h4>白名单（可访问路径）</h4>
                  <button type="button" class="add-path-btn" @click="handleAddPath('whitelist')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 5v14M5 12h14"/>
                    </svg>
                    添加
                  </button>
                </div>
                <div class="path-list">
                  <div v-for="p in whitelistPaths" :key="p.id" class="path-item">
                    <span class="path-value">{{ p.path }}</span>
                    <button type="button" class="remove-path-btn" title="移除" @click="handleRemovePath(p.path)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                  <div v-if="whitelistPaths.length === 0" class="path-empty">暂无白名单路径</div>
                </div>
              </div>

              <!-- 黑名单 -->
              <div class="path-section">
                <div class="path-section-header">
                  <h4>黑名单（禁止访问路径）</h4>
                  <button type="button" class="add-path-btn danger" @click="handleAddPath('blacklist')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 5v14M5 12h14"/>
                    </svg>
                    添加
                  </button>
                </div>
                <div class="path-list">
                  <div v-for="p in blacklistPaths" :key="p.id" class="path-item danger">
                    <span class="path-value">{{ p.path }}</span>
                    <button type="button" class="remove-path-btn" title="移除" @click="handleRemovePath(p.path)">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                  <div v-if="blacklistPaths.length === 0" class="path-empty">暂无黑名单路径</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 模型编辑弹窗 -->
        <ModelEditModal
          :visible="modalVisible"
          :is-edit="isEditMode"
          :model="editingModel"
          @close="closeModal"
          @save="handleSave"
        />

        <!-- 删除确认弹窗 -->
        <div v-if="showDeleteModal" class="modal-overlay" @click="cancelDelete">
          <div class="modal-dialog" @click.stop>
            <div class="modal-header">确认删除</div>
            <div class="modal-body">
              <p>确定要删除这个模型吗？</p>
            </div>
            <div class="modal-footer">
              <button class="modal-btn modal-btn-cancel" @click="cancelDelete">取消</button>
              <button class="modal-btn modal-btn-danger" @click="confirmDelete">删除</button>
            </div>
          </div>
        </div>

        <!-- 解绑确认弹窗 -->
        <div v-if="showUnbindModal" class="modal-overlay" @click="cancelUnbind">
          <div class="modal-dialog" @click.stop>
            <div class="modal-header">确认解绑</div>
            <div class="modal-body">
              <p>确定要解绑{{ unbindPlatform === 'qq' ? 'QQ' : unbindPlatform === 'wechat' ? '微信' : unbindPlatform === 'feishu' ? '飞书' : unbindPlatform }}吗？此操作会清除该平台的所有配置。</p>
            </div>
            <div class="modal-footer">
              <button class="modal-btn modal-btn-cancel" @click="cancelUnbind">取消</button>
              <button class="modal-btn modal-btn-danger" @click="confirmUnbind">解绑</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useModelStore, type ModelItem } from '@/stores/model'
import { useAccountStore } from '@/stores/account'
import {
  saveQQConfig,
  wechatQRCode,
  wechatQRCodePoll,
  feishuQRCode,
  feishuQRCodePoll,
  cancelFeishuRegistration,
} from '@/api/platform'
import {
  listPathPermissions,
  addPathPermission as apiAddPathPermission,
  removePathPermission as apiRemovePathPermission,
  type PathPermission,
} from '@/api/pathPermissions'
import { selectDirectory } from '@/api/system'
import ModelEditModal from './ModelEditModal.vue'

const props = defineProps<{ visible: boolean }>()
defineEmits<{ close: [] }>()

const modelStore = useModelStore()
const accountStore = useAccountStore()

// 弹窗打开时加载数据
watch(() => props.visible, (val) => {
  if (val) {
    modelStore.loadModels()
    accountStore.fetchAccounts()
    configPanel.value = ''
  }
})

function handleBind(platform: string) {
  accountStore.togglePlatform(platform)
}

function handleUnbind(platform: string) {
  unbindPlatform.value = platform
  showUnbindModal.value = true
}

async function confirmUnbind() {
  if (unbindPlatform.value) {
    await accountStore.unbind(unbindPlatform.value)
    showUnbindModal.value = false
    unbindPlatform.value = null
  }
}

function cancelUnbind() {
  showUnbindModal.value = false
  unbindPlatform.value = null
}

// ---------- 配置面板 ----------
const configPanel = ref('')
const configLoading = ref(false)

// QQ 表单
const qqForm = ref({ app_id: '', app_secret: '' })

function openConfigPanel(platform: string) {
  // 离开飞书配置时取消后端注册流程
  if (configPanel.value === 'feishu' && platform !== 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  configPanel.value = platform
  qqForm.value = { app_id: '', app_secret: '' }
  wechatQRImg.value = ''
  wechatQRKey.value = ''
  wechatPollStatus.value = ''
  feishuQRImg.value = ''
  feishuPollStatus.value = ''
}

function closeConfigPanel() {
  if (configPanel.value === 'feishu') {
    cancelFeishuRegistration().catch(() => {})
  }
  stopWechatPoll()
  stopFeishuPoll()
  configPanel.value = ''
}

async function saveQQ() {
  configLoading.value = true
  try {
    await saveQQConfig({
      enabled: true,
      app_id: qqForm.value.app_id,
      app_secret: qqForm.value.app_secret,
      mode: 'agent',
    })
    configPanel.value = ''
    await accountStore.fetchAccounts()
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    configLoading.value = false
  }
}

// 微信扫码
const wechatQRImg = ref('')
const wechatQRKey = ref('')
const wechatPollStatus = ref('')
let wechatPollTimer: ReturnType<typeof setInterval> | null = null

async function startWechatQR() {
  configLoading.value = true
  try {
    const res = await wechatQRCode()
    if (res.success && res.qrcode_img) {
      wechatQRImg.value = res.qrcode_img
      wechatQRKey.value = res.qrcode_key || ''
      wechatPollStatus.value = 'pending'
      startWechatPoll()
    } else {
      alert(res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startWechatPoll() {
  stopWechatPoll()
  wechatPollTimer = setInterval(async () => {
    try {
      const res = await wechatQRCodePoll(wechatQRKey.value || undefined)
      wechatPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopWechatPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'expired') {
        stopWechatPoll()
        wechatQRImg.value = ''
      }
    } catch {
      // ignore poll errors
    }
  }, 3000)
}

function stopWechatPoll() {
  if (wechatPollTimer) {
    clearInterval(wechatPollTimer)
    wechatPollTimer = null
  }
}

// 飞书扫码
const feishuQRImg = ref('')
const feishuPollStatus = ref('')
let feishuPollTimer: ReturnType<typeof setInterval> | null = null

async function startFeishuQR() {
  configLoading.value = true
  try {
    const res = await feishuQRCode()
    if (res.success && res.qrcode_img) {
      feishuQRImg.value = res.qrcode_img
      feishuPollStatus.value = 'pending'
      startFeishuPoll()
    } else if (res.phase === 'configured' || res.phase === 'authorized') {
      feishuPollStatus.value = 'confirmed'
      configPanel.value = ''
      await accountStore.fetchAccounts()
    } else {
      alert(res.message || res.error || '获取二维码失败')
    }
  } catch (e: any) {
    alert(e.message || '获取二维码失败')
  } finally {
    configLoading.value = false
  }
}

function startFeishuPoll() {
  stopFeishuPoll()
  feishuPollTimer = setInterval(async () => {
    try {
      const res = await feishuQRCodePoll()
      feishuPollStatus.value = res.status || ''
      if (res.status === 'confirmed') {
        stopFeishuPoll()
        configPanel.value = ''
        await accountStore.fetchAccounts()
      } else if (res.status === 'error') {
        stopFeishuPoll()
        feishuQRImg.value = ''
      }
    } catch {
      // ignore poll errors
    }
  }, 3000)
}

function stopFeishuPoll() {
  if (feishuPollTimer) {
    clearInterval(feishuPollTimer)
    feishuPollTimer = null
  }
}

onUnmounted(() => {
  stopWechatPoll()
  stopFeishuPoll()
})

const activeTab = ref<'models' | 'accounts' | 'paths'>('models')

const tabTitle = computed(() => {
  const map = { models: '模型管理', accounts: '账号绑定', paths: '路径权限' } as const
  return map[activeTab.value]
})

// 模型编辑弹窗
const modalVisible = ref(false)
const isEditMode = ref(false)
const editingModel = ref<ModelItem | null>(null)

function openAddModal() {
  isEditMode.value = false
  editingModel.value = null
  modalVisible.value = true
}

function openEditModal(model: ModelItem) {
  isEditMode.value = true
  editingModel.value = model
  modalVisible.value = true
}

function closeModal() {
  modalVisible.value = false
  editingModel.value = null
}

async function handleSave(data: Omit<ModelItem, 'id'>) {
  if (isEditMode.value && editingModel.value) {
    await modelStore.updateModel(editingModel.value.id, data)
  } else {
    await modelStore.addModel(data)
  }
  closeModal()
}

async function handleSetActive(id: string) {
  await modelStore.setActiveModel(id)
}

// 删除确认弹窗
const showDeleteModal = ref(false)
const modelToDelete = ref<string | null>(null)

// 解绑确认弹窗
const showUnbindModal = ref(false)
const unbindPlatform = ref<string | null>(null)

function handleDelete(id: string) {
  modelToDelete.value = id
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (modelToDelete.value) {
    await modelStore.deleteModel(modelToDelete.value)
    showDeleteModal.value = false
    modelToDelete.value = null
  }
}

function cancelDelete() {
  showDeleteModal.value = false
  modelToDelete.value = null
}

// ---------- 路径权限 ----------
const pathPermissions = ref<PathPermission[]>([])
const whitelistPaths = computed(() => pathPermissions.value.filter(p => p.type === 'whitelist'))
const blacklistPaths = computed(() => pathPermissions.value.filter(p => p.type === 'blacklist'))

async function loadPathPermissions() {
  try {
    const res = await listPathPermissions()
    pathPermissions.value = res.permissions || []
  } catch (e) {
    console.error('加载路径权限失败', e)
    pathPermissions.value = []
  }
}

async function handleRemovePath(path: string) {
  try {
    await apiRemovePathPermission(path)
    pathPermissions.value = pathPermissions.value.filter(p => p.path !== path)
  } catch (e: any) {
    alert(e.message || '删除失败')
  }
}

// 添加路径（使用文件夹选择对话框）
async function handleAddPath(type: 'whitelist' | 'blacklist') {
  try {
    const result = await selectDirectory()
    if (result.cancelled || !result.path) {
      return
    }
    if (result.error) {
      alert(result.error)
      return
    }
    const res = await apiAddPathPermission(result.path, type)
    if (res.success) {
      await loadPathPermissions()
    } else {
      alert(res.error || '添加失败')
    }
  } catch (e: any) {
    alert(e.message || '添加失败')
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
  z-index: 1000;
}

.modal-container {
  display: flex;
  width: 720px;
  height: 42vh;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

/* 左侧导航 */
.modal-nav {
  width: 180px;
  min-width: 180px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0;
}

.modal-nav-header {
  padding: 0 20px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.modal-nav-header h1 {
  font-size: 18px;
  font-weight: 600;
}

.modal-nav-list {
  list-style: none;
  margin: 0;
  padding: 4px 8px;
}

.modal-nav-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-nav-list li:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-nav-list li.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
}

.modal-nav-list li svg {
  flex-shrink: 0;
}

/* 右侧内容 */
.modal-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.modal-body-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  flex-shrink: 0;
}

.modal-body-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-body-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
}

/* 通用 */
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}

.model-item:hover {
  border-color: var(--border-strong);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.model-item.active {
  border-color: #2d7a4f;
  background: #f8fdfb;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.model-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: #e8f5ee;
  color: #2d7a4f;
  border-radius: 4px;
  font-weight: 500;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn-sm {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn-sm:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.icon-btn-sm.delete:hover {
  background: #fee2e2;
  color: #991b1b;
}

/* 账号绑定 */
.account-bind-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.account-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.account-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.account-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.account-icon.feishu,
.account-icon.qq,
.account-icon.wechat { }

.account-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.account-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.account-status {
  font-size: 12px;
  color: var(--text-muted);
}

.account-status.bound { color: #2d7a4f; }

.bind-btn {
  padding: 6px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.bind-btn:hover { background: var(--accent-hover); }
.bind-btn.bound { background: #e8f5ee; border-color: #b8dfc8; color: #2d7a4f; }
.bind-btn.disabled { opacity: 0.4; cursor: not-allowed; }

.account-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.unbind-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.unbind-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
}

/* 配置面板 */
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-panel-header h3 {
  font-size: 15px;
  font-weight: 600;
}

.back-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.back-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.config-form {
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
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: var(--border-strong);
}

.form-submit-btn {
  padding: 8px 16px;
  background: #2d7a4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
  margin-top: 4px;
}

.form-submit-btn:hover { opacity: 0.9; }
.form-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 二维码区域 */
.qrcode-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.qrcode-img {
  width: 180px;
  height: 180px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.qrcode-tip {
  font-size: 13px;
  color: var(--text-secondary);
}

.qrcode-tip {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 删除确认弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-dialog {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 320px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.modal-header {
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.modal-body {
  padding: 20px;
  color: var(--text);
}

.modal-body p {
  margin: 0;
  line-height: 1.5;
}

.modal-footer {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.modal-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.modal-btn:hover {
  opacity: 0.85;
}

.modal-btn-cancel {
  background: #e5e7eb;
  color: #374151;
}

.modal-btn-danger {
  background: #1f2937;
  color: #ffffff;
}

/* 路径权限 */
.path-section {
  margin-bottom: 16px;
}

.path-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.path-section-header h4 {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.add-path-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
}

.add-path-btn:hover {
  background: var(--accent-hover);
}

.add-path-btn.danger {
  border-color: #ef4444;
  color: #ef4444;
}

.add-path-btn.danger:hover {
  background: #fef2f2;
}

.path-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.path-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.path-item.danger {
  border-color: #fca5a5;
  background: #fef2f2;
}

.path-value {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-path-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
}

.remove-path-btn:hover {
  background: var(--accent-hover);
  color: #ef4444;
}

.path-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 12px;
}
</style>
