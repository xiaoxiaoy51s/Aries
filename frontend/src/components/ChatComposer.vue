<template>
  <div class="composer-shell" :class="{ 'composer-shell-bottom': isBottom }">
  <div class="composer" :class="{ 'composer-with-slash': true, 'composer-bottom': isBottom }">
    <!-- MCP 状态面板（覆盖在输入框上方，绝对定位） -->
    <div v-if="mcpPanelOpen" class="mcp-panel">
      <div class="mcp-panel-header">
        <span class="mcp-panel-title">MCP</span>
        <button type="button" class="mcp-panel-close" @click="closeMcpPanel">关闭</button>
      </div>
      <div v-if="mcpLoading" class="mcp-panel-loading">加载中…</div>
      <div v-else-if="!mcpPlugins.length" class="mcp-panel-empty">暂无 MCP 配置</div>
      <div v-else class="mcp-panel-list">
        <div
          v-for="plugin in mcpPlugins"
          :key="plugin.id"
          class="mcp-panel-item"
        >
          <div class="mcp-panel-item-info">
            <span class="mcp-panel-item-name">{{ plugin.id }}</span>
            <span class="mcp-panel-item-desc">{{ plugin.description || plugin.command || '无描述' }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="skillsPanelOpen" class="mcp-panel">
      <div class="mcp-panel-header">
        <span class="mcp-panel-title">技能</span>
        <button type="button" class="mcp-panel-close" @click="closeSkillsPanel">关闭</button>
      </div>
      <div v-if="!skillItems.length" class="mcp-panel-empty">暂无技能</div>
      <div v-else class="mcp-panel-list">
        <div
          v-for="skill in skillItems"
          :key="skill.id"
          class="mcp-panel-item mcp-panel-item--clickable"
          @click="applySkill(skill)"
        >
          <div class="mcp-panel-item-info">
            <span class="mcp-panel-item-name">{{ skill.label }}</span>
            <span class="mcp-panel-item-desc">{{ skill.description }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="reviewPanelOpen" class="review-panel" @mousedown.prevent>
      <button type="button" class="review-panel-item" @click="applyReviewPrompt('unstaged')">
        <span class="review-panel-title">审查未暂存更改</span>
        <span class="review-panel-desc">审查 git diff 的未暂存变更</span>
      </button>
      <button type="button" class="review-panel-item" @click="applyReviewPrompt('staged')">
        <span class="review-panel-title">审查已暂存更改</span>
        <span class="review-panel-desc">审查 git diff --cached 的已暂存变更</span>
      </button>
      <button type="button" class="review-panel-item" @click="applyReviewPrompt('branch')">
        <span class="review-panel-title">对比基础分支</span>
        <span class="review-panel-desc">审查当前分支相对基础分支的全部变更</span>
      </button>
      <button type="button" class="review-panel-item" @click="applyReviewPrompt('commit')">
        <span class="review-panel-title">审查最近提交</span>
        <span class="review-panel-desc">审查最近一次提交的代码变更</span>
      </button>
      <button type="button" class="review-panel-item" @click="applyReviewPrompt('full')">
        <span class="review-panel-title">全面审查</span>
        <span class="review-panel-desc">对当前工作目录做完整代码审查</span>
      </button>
    </div>
    <slot />
    <SlashComposerInput
      ref="composerRef"
      v-model:plain-text="plainTextProxy"
      v-model:active-command="activeSlashCommandProxy"
      v-model:objective="commandObjectiveProxy"
      v-model:plugin-menu-open="pluginMenuOpenProxy"
      v-model:attached-images="attachedImagesProxy"
      :rows="rows"
      :max-rows="5"
      :disabled="isSending"
      placeholder="随心输入"
      :plugin-items="pluginItems"
      :skill-items="skillItems"
      @send="handleSend"
      @plugin-select="onPluginClick"
      @slash-keydown="onPluginKeydown"
    />
    <div v-if="pluginMenuOpenProxy" class="plugin-menu" @mousedown.prevent>
      <div class="plugin-menu-body">
        <div class="plugin-menu-group">
          <div
            v-for="(item, idx) in filteredPluginItems"
            :key="item.id"
            class="plugin-menu-item"
            :class="{
              'plugin-menu-item--active': idx === pluginSelectedIndex,
              'plugin-menu-item--disabled': item.disabled,
            }"
            @click="onPluginClick(item)"
            @mouseenter="pluginSelectedIndex = idx"
          >
            <div class="plugin-menu-icon" v-html="pluginIconFor(item.icon)"></div>
            <div class="plugin-menu-text">
              <span class="plugin-menu-label">{{ item.label }}</span>
              <span class="plugin-menu-desc">{{ item.description }}</span>
            </div>
            <div v-if="item.badge" class="plugin-menu-badge">{{ item.badge }}</div>
          </div>
        </div>
        <div v-if="filteredSubagentItems.length" class="plugin-menu-divider"></div>
        <div v-if="filteredSubagentItems.length" class="plugin-menu-group">
          <div class="plugin-menu-group-title">子Agent</div>
          <div
            v-for="(agent, aIdx) in filteredSubagentItems"
            :key="agent.id"
            class="plugin-menu-item"
            :class="{
              'plugin-menu-item--active': filteredPluginItems.length + aIdx === pluginSelectedIndex,
              'plugin-menu-item--disabled': agent.disabled,
            }"
            @click="onSubagentClick(agent)"
            @mouseenter="pluginSelectedIndex = filteredPluginItems.length + aIdx"
          >
            <div class="plugin-menu-icon" v-html="pluginIconFor(agent.icon)"></div>
            <div class="plugin-menu-text">
              <span class="plugin-menu-label">{{ agent.label }}</span>
              <span class="plugin-menu-desc">{{ agent.description }}</span>
            </div>
            <div v-if="agent.badge" class="plugin-menu-badge">{{ agent.badge }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="composer-toolbar">
      <div class="composer-left">
        <button
          type="button"
          class="icon-btn"
          title="上传图片"
          :disabled="isSending || !!activeSlashCommandProxy"
          @click="$emit('openImagePicker')"
        >
          +
        </button>
        <div class="approval-picker">
          <button
            type="button"
            class="approval-trigger"
            :title="currentApprovalOption?.label || '请求批准'"
            @click="approvalMenuOpen = !approvalMenuOpen"
          >
            <span class="approval-trigger-icon" v-html="approvalIcon(currentApprovalOption?.icon || 'hand')"></span>
            <span class="approval-trigger-label">{{ currentApprovalOption?.label || '请求批准' }}</span>
            <svg class="approval-trigger-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </button>
          <div
            v-if="approvalMenuOpen"
            class="approval-menu"
            @mousedown.prevent
          >
            <div class="approval-menu-list">
              <button
                v-for="opt in approvalOptions"
                :key="opt.id"
                type="button"
                class="approval-menu-item"
                :class="{ 'approval-menu-item--active': opt.id === selectedApproval }"
                @click="selectApproval(opt.id)"
              >
                <span class="approval-menu-icon" v-html="approvalIcon(opt.icon)"></span>
                <span class="approval-menu-text">
                  <span class="approval-menu-label">{{ opt.label }}</span>
                  <span class="approval-menu-desc">{{ opt.description }}</span>
                </span>
                <svg
                  v-if="opt.id === selectedApproval"
                  class="approval-menu-check"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <path d="M20 6 9 17l-5-5"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="composer-right">
        <select
          :value="selectedModel"
          class="model-select"
          @change="$emit('update:selectedModel', ($event.target as HTMLSelectElement).value)"
        >
          <option v-if="modelList.length === 0" value="" disabled>暂无模型</option>
          <option v-for="model in modelList" :key="model.id" :value="model.model">
            {{ model.name }}
          </option>
        </select>
        <button
          v-if="!isSending"
          type="button"
          class="send-btn"
          :disabled="!canSend"
          @click="handleSend"
        >
          <span class="send-icon-inner">
            <svg class="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m5 12 7-7 7 7M12 19V5"/>
            </svg>
          </span>
        </button>
        <button
          v-else
          type="button"
          class="send-btn send-btn--streaming"
          title="停止生成"
          @click="$emit('stop')"
        >
          <span class="loading-spinner">
            <span class="spinner-circle"></span>
          </span>
        </button>
      </div>
    </div>
    </div>
    <!-- 工作目录未选择提示 -->
    <Transition name="fade">
      <div v-if="workDirWarnVisible" class="workdir-warn-toast">
        请先选择工作目录
      </div>
    </Transition>
    <!-- /composer 容器：边框仅包裹文本区与工具栏，底部标签栏脱离边框 -->
    <!-- 底部工具栏：仅在欢迎界面显示 -->
    <div v-if="!isBottom && showWorkDir" class="composer-bottom-bar">
      <div class="bottom-bar-item workdir-picker-bottom">
        <button
          type="button"
          class="bottom-bar-btn"
          :title="workDirLabel || '选择工作目录'"
          @click="workDirMenuOpen = !workDirMenuOpen"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span class="bottom-bar-label">{{ workDirLabel || '新建文件夹' }}</span>
        </button>
        <div v-if="workDirMenuOpen" class="workdir-menu" @click.stop>
          <div class="workdir-menu-title">历史工作目录</div>
          <ul v-if="(workDirHistory || []).length" class="workdir-menu-list">
            <li
              v-for="dir in (workDirHistory || [])"
              :key="dir"
              class="workdir-menu-item"
              :class="{ active: dir === workDir }"
              @click="onApplyWorkDir(dir)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span class="workdir-menu-path" :title="dir">{{ dir }}</span>
            </li>
          </ul>
          <div v-else class="workdir-menu-empty">暂无历史工作目录</div>
          <div class="workdir-menu-divider"></div>
          <button type="button" class="workdir-menu-new" @click="$emit('pickWorkDir')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            <span>新工作目录</span>
          </button>
        </div>
      </div>
      <div class="bottom-bar-item branch-picker-bottom">
        <button
          type="button"
          class="bottom-bar-btn"
          :title="branchInfo.current ? `当前分支：${branchInfo.current}${branchInfo.dirty ? '（有未提交改动）' : ''}` : '未检测到 Git 仓库'"
          @click="toggleBranchMenu"
        >
          <svg t="1782020391719" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="9260" width="14" height="14"><path d="M303.146667 648.96A128.042667 128.042667 0 1 1 213.333333 647.253333V376.746667a128.042667 128.042667 0 1 1 85.333334 0V512c35.669333-26.794667 79.957333-42.666667 128-42.666667h170.666666a128.042667 128.042667 0 0 0 123.52-94.293333 128.042667 128.042667 0 1 1 86.698667 2.730667A213.418667 213.418667 0 0 1 597.333333 554.666667h-170.666666a128.042667 128.042667 0 0 0-123.52 94.293333zM256 725.333333a42.666667 42.666667 0 1 0 0 85.333334 42.666667 42.666667 0 0 0 0-85.333334zM256 213.333333a42.666667 42.666667 0 1 0 0 85.333334 42.666667 42.666667 0 0 0 0-85.333334z m512 0a42.666667 42.666667 0 1 0 0 85.333334 42.666667 42.666667 0 0 0 0-85.333334z" fill="#000000" p-id="9261"></path></svg>
          <span class="bottom-bar-label">{{ branchInfo.current || '无分支' }}</span>
          <span v-if="branchInfo.dirty" class="branch-dirty-dot" title="工作区有未提交改动"></span>
        </button>
        <div v-if="branchMenuOpen" class="branch-menu" @click.stop>
          <div class="branch-menu-title">
            <span>分支</span>
            <span v-if="branchInfo.dirty" class="branch-menu-dirty">未提交改动</span>
          </div>
          <input
            v-if="branchInfo.is_repo && branchInfo.branches.length > 5"
            v-model="branchFilter"
            class="branch-menu-search"
            type="text"
            placeholder="搜索分支..."
          />
          <ul v-if="branchInfo.is_repo && filteredBranches.length" class="branch-menu-list">
            <li
              v-for="b in filteredBranches"
              :key="b"
              class="branch-menu-item"
              :class="{ active: b === branchInfo.current }"
            >
              <span class="branch-menu-name" :title="b" @click="onCheckoutBranch(b)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="6" y1="3" x2="6" y2="15"/>
                  <circle cx="18" cy="6" r="3"/>
                  <circle cx="6" cy="18" r="3"/>
                  <path d="M18 9a9 9 0 0 1-9 9"/>
                </svg>
                <span class="branch-menu-text">{{ b }}</span>
              </span>
              <button
                v-if="b !== branchInfo.current"
                type="button"
                class="branch-menu-action"
                :title="`将 ${b} 合并到当前分支 ${branchInfo.current}`"
                @click.stop="onMergeBranch(b)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="6" cy="6" r="3"/>
                  <circle cx="6" cy="18" r="3"/>
                  <circle cx="18" cy="12" r="3"/>
                  <path d="M6 9v6"/>
                  <path d="M6 18a12 12 0 0 0 12-6"/>
                </svg>
              </button>
            </li>
          </ul>
          <div v-else-if="!branchInfo.is_repo" class="branch-menu-empty">当前目录不是 Git 仓库</div>
          <div v-else class="branch-menu-empty">无匹配分支</div>
          <div v-if="branchInfo.is_repo" class="branch-menu-divider"></div>
          <div v-if="branchInfo.is_repo && !creatingBranch" class="branch-menu-footer">
            <button type="button" class="branch-menu-new" @click="creatingBranch = true">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              <span>基于当前分支新建</span>
            </button>
          </div>
          <form
            v-if="branchInfo.is_repo && creatingBranch"
            class="branch-menu-create"
            @submit.prevent="onCreateBranch"
          >
            <input
              ref="newBranchInputRef"
              v-model="newBranchName"
              class="branch-menu-input"
              type="text"
              placeholder="新分支名"
              @keydown.esc.prevent="cancelCreateBranch"
            />
            <button type="submit" class="branch-menu-confirm" :disabled="!newBranchName.trim()">创建</button>
            <button type="button" class="branch-menu-cancel" @click="cancelCreateBranch">取消</button>
          </form>
          <div v-if="branchActionMessage" class="branch-menu-message" :class="{ error: branchActionError }">
            {{ branchActionMessage }}
          </div>
        </div>
      </div>
    </div>
    <RoleEditorModal
      :visible="roleModalVisible"
      :work-dir="props.workDir || null"
      @close="roleModalVisible = false"
      @saved="() => {}"
    />
    <!-- 通用确认弹窗（分支切换/合并等） -->
    <Teleport to="body">
      <div
        v-if="confirmState.visible"
        class="branch-confirm-overlay"
        @mousedown.self="resolveConfirm(false)"
      >
        <div class="branch-confirm-dialog" @click.stop>
          <div class="branch-confirm-header">{{ confirmState.title }}</div>
          <div class="branch-confirm-body">
            <p>{{ confirmState.message }}</p>
          </div>
          <div class="branch-confirm-footer">
            <button class="branch-confirm-btn branch-confirm-btn-cancel" @click="resolveConfirm(false)">
              {{ confirmState.cancelText }}
            </button>
            <button
              class="branch-confirm-btn"
              :class="confirmState.kind === 'danger' ? 'branch-confirm-btn-danger' : 'branch-confirm-btn-primary'"
              @click="resolveConfirm(true)"
            >
              {{ confirmState.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
    <!-- 压缩确认弹窗 -->
    <Teleport to="body">
      <div v-if="compactModalOpen" class="compact-overlay" @mousedown.self="compactModalOpen = false">
        <div class="compact-modal">
          <div class="compact-modal-header">
            <span class="compact-modal-title">压缩会话上下文</span>
            <button type="button" class="compact-modal-close" @click="compactModalOpen = false">×</button>
          </div>
          <div class="compact-modal-body">
            <p class="compact-modal-desc">
              将较早的对话消息压缩为结构化记忆摘要，保留近期消息窗口。
              压缩后可显著降低上下文 token 占用，但历史细节会有损失。
            </p>
            <div class="compact-modal-info">
              <div class="compact-info-row">
                <span class="compact-info-label">会话 ID</span>
                <span class="compact-info-value compact-info-mono">{{ props.sessionId || '（无活动会话）' }}</span>
              </div>
              <div class="compact-info-row">
                <span class="compact-info-label">当前占用</span>
                <span class="compact-info-value compact-info-highlight">已使用 {{ props.contextUsagePercent ?? 0 }}%</span>
              </div>
            </div>
            <div v-if="contextUsageRows.length" class="context-usage-breakdown">
              <div class="context-usage-header">
                <span class="context-usage-title">Context Usage</span>
                <span class="context-usage-total">
                  ~{{ formatTokens(contextUsageInfo?.estimated_tokens ?? 0) }}
                  / {{ formatTokens(contextUsageInfo?.context_window ?? 200000) }} Tokens
                </span>
              </div>
              <div class="context-usage-bar">
                <span
                  v-for="row in contextUsageRows"
                  :key="row.key"
                  class="context-usage-bar-seg"
                  :style="{ width: row.percent + '%', background: row.color }"
                  :title="row.label + ': ' + formatTokens(row.tokens)"
                />
              </div>
              <ul class="context-usage-list">
                <li v-for="row in contextUsageRows" :key="row.key" class="context-usage-item">
                  <span class="context-usage-dot" :style="{ background: row.color }" />
                  <span class="context-usage-label">{{ row.label }}</span>
                  <span class="context-usage-value">{{ formatTokens(row.tokens) }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div class="compact-modal-footer">
            <button type="button" class="compact-btn compact-btn-cancel" @click="compactModalOpen = false" :disabled="compactLoading">取消</button>
            <button type="button" class="compact-btn compact-btn-confirm" @click="confirmCompact" :disabled="compactLoading || !props.sessionId">
              {{ compactLoading ? '压缩中…' : '确认压缩' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import SlashComposerInput, { type ComposerImage } from '@/components/SlashComposerInput.vue'
import RoleEditorModal from '@/components/RoleEditorModal.vue'
import { listPlugins, type PluginItem as McpPluginItem } from '@/api/plugins'
import { listPets } from '@/api/pets'
import { listSkills, type SkillItem as ApiSkillItem } from '@/api/skills'
import { listSubagents, type SubagentItem as ApiSubagentItem } from '@/api/subagents'
import { compactSession } from '@/api/sessions'
import { getApprovalMode, setApprovalMode, type ApprovalMode } from '@/api/pathPermissions'
import { useModelStore } from '@/stores/model'

interface SlashCommandDef {
  id: string
  label?: string
}

interface ModelItem {
  id: string
  model: string
  name: string
}

interface PluginItem {
  id: string
  icon: string
  label: string
  description: string
  badge?: string
  disabled?: boolean
}

const props = defineProps<{
  modelValue: string
  attachedImages: ComposerImage[]
  activeSlashCommand: SlashCommandDef | null
  commandObjective: string
  pluginMenuOpen: boolean
  isSending: boolean
  selectedModel: string
  modelList: ModelItem[]
  canSend: boolean
  showWorkDir?: boolean
  workDir?: string
  workDirLabel?: string
  workDirHistory?: string[]
  rows?: number
  isBottom?: boolean
  contextUsagePercent?: number
  contextUsageInfo?: {
    estimated_tokens?: number
    context_window?: number
    usage_percent?: number
    breakdown?: {
      system_prompt?: number
      tool_definitions?: number
      rules?: number
      skills?: number
      summarized_conversation?: number
      conversation?: number
    }
  } | null
  sessionId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:attachedImages': [value: ComposerImage[]]
  'update:activeSlashCommand': [value: SlashCommandDef | null]
  'update:commandObjective': [value: string]
  'update:pluginMenuOpen': [value: boolean]
  'update:selectedModel': [value: string]
  send: []
  stop: []
  openImagePicker: []
  pickWorkDir: []
  applyWorkDir: [path: string]
  toggleSideChat: []
  compactDone: []
}>()

const composerRef = ref<InstanceType<typeof SlashComposerInput>>()
const workDirMenuOpen = ref(false)
const roleModalVisible = ref(false)
const reviewPanelOpen = ref(false)
const workDirWarnVisible = ref(false)

function handleSend() {
  if (!props.workDir || !props.workDir.trim()) {
    workDirWarnVisible.value = true
    setTimeout(() => { workDirWarnVisible.value = false }, 3000)
    return
  }
  emit('send')
}
const mcpPanelOpen = ref(false)
const skillsPanelOpen = ref(false)
const mcpPlugins = ref<McpPluginItem[]>([])
const mcpLoading = ref(false)
const compactModalOpen = ref(false)
const compactLoading = ref(false)

// --- Git 分支选择器 -------------------------------------------------------
type BranchInfo = {
  is_repo: boolean
  current: string
  dirty: boolean
  branches: string[]
}
const branchMenuOpen = ref(false)
const branchInfo = ref<BranchInfo>({ is_repo: false, current: '', dirty: false, branches: [] })
const branchFilter = ref('')
const creatingBranch = ref(false)
const newBranchName = ref('')
const newBranchInputRef = ref<HTMLInputElement | null>(null)
const branchActionMessage = ref('')
const branchActionError = ref(false)
let branchMessageTimer: ReturnType<typeof setTimeout> | null = null

// 应用内确认弹窗（替代 window.confirm，与 SettingsPanel 删除/解绑弹窗风格一致）
type ConfirmKind = 'default' | 'danger'
type ConfirmState = {
  visible: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  kind: ConfirmKind
  resolve: ((v: boolean) => void) | null
}
const confirmState = ref<ConfirmState>({
  visible: false,
  title: '',
  message: '',
  confirmText: '确定',
  cancelText: '取消',
  kind: 'default',
  resolve: null,
})

function openConfirm(opts: {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  kind?: ConfirmKind
}): Promise<boolean> {
  return new Promise((resolve) => {
    confirmState.value = {
      visible: true,
      title: opts.title,
      message: opts.message,
      confirmText: opts.confirmText || '确定',
      cancelText: opts.cancelText || '取消',
      kind: opts.kind || 'default',
      resolve,
    }
  })
}

function resolveConfirm(value: boolean) {
  const fn = confirmState.value.resolve
  confirmState.value.visible = false
  confirmState.value.resolve = null
  if (fn) fn(value)
}

const filteredBranches = computed(() => {
  const q = branchFilter.value.trim().toLowerCase()
  const list = branchInfo.value.branches || []
  if (!q) return list
  return list.filter((b) => b.toLowerCase().includes(q))
})

function setBranchMessage(msg: string, isError = false) {
  branchActionMessage.value = msg
  branchActionError.value = isError
  if (branchMessageTimer) clearTimeout(branchMessageTimer)
  if (msg) {
    branchMessageTimer = setTimeout(() => {
      branchActionMessage.value = ''
      branchActionError.value = false
    }, 4000)
  }
}

async function refreshBranches() {
  try {
    const baseUrl = useModelStore().getBaseUrl()
    const url = `${baseUrl}/git/branches${props.workDir ? `?work_dir=${encodeURIComponent(props.workDir)}` : ''}`
    const res = await fetch(url)
    if (!res.ok) return
    const data = await res.json()
    branchInfo.value = {
      is_repo: !!data.is_repo,
      current: data.current || '',
      dirty: !!data.dirty,
      branches: Array.isArray(data.branches) ? data.branches : [],
    }
  } catch (e) {
    console.error('加载分支列表失败', e)
  }
}

async function toggleBranchMenu() {
  branchMenuOpen.value = !branchMenuOpen.value
  if (branchMenuOpen.value) {
    branchFilter.value = ''
    creatingBranch.value = false
    newBranchName.value = ''
    branchActionMessage.value = ''
    await refreshBranches()
  }
}

async function onCheckoutBranch(branch: string) {
  if (!branch || branch === branchInfo.value.current) return
  const baseUrl = useModelStore().getBaseUrl()
  let force = false
  if (branchInfo.value.dirty) {
    const ok = await openConfirm({
      title: '切换分支',
      message: `工作区存在未提交改动，切换到 "${branch}" 可能会让 Git 阻止操作或丢失改动。是否仍然尝试切换？`,
      confirmText: '仍要切换',
      cancelText: '取消',
      kind: 'danger',
    })
    if (!ok) return
    force = true
  }
  try {
    const res = await fetch(`${baseUrl}/git/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: props.workDir || '', branch, force }),
    })
    const data = await res.json()
    if (!data.success) {
      if (data.dirty) {
        const ok = await openConfirm({
          title: '切换分支',
          message: `${data.message || '工作区有未提交改动'}\n\n是否强制切换？`,
          confirmText: '强制切换',
          cancelText: '取消',
          kind: 'danger',
        })
        if (ok) {
          await fetch(`${baseUrl}/git/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ work_dir: props.workDir || '', branch, force: true }),
          })
        } else {
          return
        }
      } else {
        setBranchMessage(data.message || '切换失败', true)
        return
      }
    }
    setBranchMessage(`已切换到 ${branch}`)
    await refreshBranches()
  } catch (e) {
    console.error('切换分支失败', e)
    setBranchMessage('切换分支失败', true)
  }
}

async function onCreateBranch() {
  const name = newBranchName.value.trim()
  if (!name) return
  try {
    const baseUrl = useModelStore().getBaseUrl()
    const res = await fetch(`${baseUrl}/git/create-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: props.workDir || '', name, checkout: true }),
    })
    const data = await res.json()
    if (!data.success) {
      setBranchMessage(data.message || '创建分支失败', true)
      return
    }
    setBranchMessage(`已创建并切换到 ${name}`)
    creatingBranch.value = false
    newBranchName.value = ''
    await refreshBranches()
  } catch (e) {
    console.error('创建分支失败', e)
    setBranchMessage('创建分支失败', true)
  }
}

function cancelCreateBranch() {
  creatingBranch.value = false
  newBranchName.value = ''
}

async function onMergeBranch(branch: string) {
  if (!branch || branch === branchInfo.value.current) return
  const ok = await openConfirm({
    title: '合并分支',
    message: `将分支 "${branch}" 合并到当前分支 "${branchInfo.value.current}"？\n\n如发生冲突，请到 Git 面板手动解决。`,
    confirmText: '合并',
    cancelText: '取消',
  })
  if (!ok) return
  try {
    const baseUrl = useModelStore().getBaseUrl()
    const res = await fetch(`${baseUrl}/git/merge-branch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: props.workDir || '', branch }),
    })
    const data = await res.json()
    if (!data.success) {
      setBranchMessage(data.message || '合并失败', true)
      return
    }
    setBranchMessage(`已合并 ${branch}`)
    await refreshBranches()
  } catch (e) {
    console.error('合并分支失败', e)
    setBranchMessage('合并分支失败', true)
  }
}

watch(creatingBranch, async (val) => {
  if (val) {
    await nextTick()
    newBranchInputRef.value?.focus()
  }
})

watch(() => props.workDir, () => {
  if (branchMenuOpen.value) refreshBranches()
})

// 请求批准（Approval）下拉菜单状态
type ApprovalOption = {
  id: ApprovalMode
  icon: 'hand' | 'shield-alert' | 'unlock'
  label: string
  description: string
}
const approvalOptions: ApprovalOption[] = [
  {
    id: 'request',
    icon: 'hand',
    label: '请求批准',
    description: '编辑外部文件和使用互联网时始终询问',
  },
  {
    id: 'review',
    icon: 'shield-alert',
    label: '替我审批',
    description: '仅对检测到的风险操作请求批准',
  },
  {
    id: 'full',
    icon: 'unlock',
    label: '完全访问权限',
    description: '可不受限制地访问互联网和您电脑上的任何文件',
  },
]
const approvalMenuOpen = ref(false)
const selectedApproval = ref<ApprovalOption['id']>('request')
const currentApprovalOption = computed(
  () => approvalOptions.find((o) => o.id === selectedApproval.value) || approvalOptions[0]
)
function selectApproval(id: ApprovalOption['id']) {
  const prev = selectedApproval.value
  selectedApproval.value = id
  approvalMenuOpen.value = false
  setApprovalMode(id).catch((err) => {
    // 失败回滚 UI，避免与后端不一致
    console.error('设置批准模式失败', err)
    selectedApproval.value = prev
  })
}
function approvalIcon(name: string): string {
  const ICON_PATHS: Record<string, string> = {
    hand:
      '<path d="M18 11V6a2 2 0 0 0-4 0v5"/><path d="M14 10V4a2 2 0 0 0-4 0v6"/><path d="M10 10.5V6a2 2 0 0 0-4 0v9"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>',
    'shield-alert':
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    unlock:
      '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
  }
  const inner = ICON_PATHS[name] || ICON_PATHS.hand
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block">${inner}</svg>`
}

// Proxies for v-model bindings that need to be wired through props+emit
const plainTextProxy = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})
const activeSlashCommandProxy = computed({
  get: () => props.activeSlashCommand,
  set: (val) => emit('update:activeSlashCommand', val)
})
const commandObjectiveProxy = computed({
  get: () => props.commandObjective,
  set: (val) => emit('update:commandObjective', val)
})
const pluginMenuOpenProxy = computed({
  get: () => props.pluginMenuOpen,
  set: (val) => emit('update:pluginMenuOpen', val)
})
const attachedImagesProxy = computed({
  get: () => props.attachedImages,
  set: (val) => emit('update:attachedImages', val)
})

const pluginItems = computed<PluginItem[]>(() => {
  const percent = props.contextUsagePercent ?? 0
  const compactBadge = percent > 0 ? `已使用 ${percent}%` : undefined
  return [
    { id: 'ask', icon: 'message-circle', label: '问答', description: '回答问题、解释代码（只读）' },
    { id: 'explore', icon: 'compass', label: '探索', description: '快速扫描代码库、定位关键文件（只读）' },
    { id: 'plan', icon: 'map', label: '规划', description: '制定实现计划，不修改代码' },
    { id: 'role', icon: 'shield', label: '规则', description: '设置 AI 行为约束规则' },
    { id: 'mcp', icon: 'cpu', label: 'MCP', description: '显示 MCP 服务器状态' },
    { id: 'skill', icon: 'zap', label: '技能', description: '查看和调用可用技能' },
    { id: 'review', icon: 'code', label: '代码审查', description: '审查未暂存的更改' },
    { id: 'sidechat', icon: 'sidebar', label: '侧边聊天', description: '在临时分支中发起对话' },
    { id: 'compact', icon: 'zap', label: '压缩', description: '压缩此会话的上下文', badge: compactBadge },
    { id: 'pet', icon: 'brain', label: '宠物', description: '唤醒或收起桌面宠物' },
  ]
})

// Context Usage 分项配置（与 Claude Code Context Usage 视图对齐）
const CONTEXT_USAGE_ROWS: { key: string; label: string; color: string }[] = [
  { key: 'system_prompt', label: 'System prompt', color: '#a3a3a3' },
  { key: 'tool_definitions', label: 'Tool definitions', color: '#7c3aed' },
  { key: 'rules', label: 'Rules', color: '#16a34a' },
  { key: 'skills', label: 'Skills', color: '#d97706' },
  { key: 'summarized_conversation', label: 'Summarized conversation', color: '#dc2626' },
  { key: 'conversation', label: 'Conversation', color: '#f59e0b' },
]

const contextUsageRows = computed(() => {
  const breakdown = props.contextUsageInfo?.breakdown
  if (!breakdown) return [] as Array<{ key: string; label: string; color: string; tokens: number; percent: number }>
  const window = props.contextUsageInfo?.context_window || 200000
  return CONTEXT_USAGE_ROWS.map((row) => {
    const tokens = (breakdown as Record<string, number | undefined>)[row.key] ?? 0
    const percent = window > 0 ? (tokens / window) * 100 : 0
    return { ...row, tokens, percent }
  }).filter((r) => r.tokens > 0)
})

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K'
  return String(n)
}

// 技能列表：从后端 /api/skills 获取，与 SkillsPage 数据源保持一致
const skillItems = ref<PluginItem[]>([])
const subagentItems = ref<PluginItem[]>([])

function skillIcon(name: string): string {
  const ch = (name || '').trim().charAt(0).toUpperCase()
  return ch || 'sparkles'
}

async function loadSkillItems() {
  try {
    const list = await listSkills()
    skillItems.value = list.map((s: ApiSkillItem) => ({
      id: s.folder_name,
      icon: skillIcon(s.name),
      label: s.name,
      description: s.description || '无描述',
      badge: s.enabled
        ? (s.group === 'system' ? '系统' : '个人')
        : '未启用',
      disabled: !s.enabled,
    }))
  } catch (e) {
    console.error('加载技能列表失败', e)
    skillItems.value = []
  }
}

async function loadSubagentItems() {
  try {
    const list = await listSubagents()
    subagentItems.value = list.map((a: ApiSubagentItem) => ({
      id: a.name,
      icon: 'user',
      label: a.name,
      description: a.description || '无描述',
      badge: a.enabled ? (a.available ? '可用' : '不可用') : '未启用',
      disabled: !a.enabled || !a.available,
    }))
  } catch (e) {
    console.error('加载子Agent列表失败', e)
    subagentItems.value = []
  }
}

function onApplyWorkDir(dir: string) {
  workDirMenuOpen.value = false
  emit('applyWorkDir', dir)
}

const pluginSelectedIndex = ref(0)

const currentSlashQuery = computed(() => {
  const text = props.modelValue || ''
  const lines = text.split('\n')
  const last = lines[lines.length - 1] || ''
  return last.startsWith('/') ? last.slice(1).toLowerCase() : ''
})

const filteredPluginItems = computed(() => {
  const q = currentSlashQuery.value
  if (!q) return pluginItems.value
  return pluginItems.value.filter(
    (i) => i.id.toLowerCase().includes(q) || i.label.toLowerCase().includes(q)
  )
})

const filteredSubagentItems = computed(() => {
  const q = currentSlashQuery.value
  if (!q) return subagentItems.value
  return subagentItems.value.filter(
    (i) => i.id.toLowerCase().includes(q) || i.label.toLowerCase().includes(q)
  )
})

const totalPluginItems = computed(
  () => filteredPluginItems.value.length + filteredSubagentItems.value.length
)

watch([filteredPluginItems, filteredSubagentItems], () => {
  if (pluginSelectedIndex.value >= totalPluginItems.value) {
    pluginSelectedIndex.value = 0
  }
})

function onPluginKeydown(e: KeyboardEvent) {
  if (!pluginMenuOpenProxy.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    const n = totalPluginItems.value
    if (n > 0) pluginSelectedIndex.value = (pluginSelectedIndex.value + 1) % n
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    const n = totalPluginItems.value
    if (n > 0) pluginSelectedIndex.value = (pluginSelectedIndex.value - 1 + n) % n
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    const list = [...filteredPluginItems.value, ...filteredSubagentItems.value]
    const item = list[pluginSelectedIndex.value]
    if (item) {
      e.preventDefault()
      onPluginClick(item)
    } else if (totalPluginItems.value > 0) {
      e.preventDefault()
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    const lines = (props.modelValue || '').split('\n')
    if (lines.length && lines[lines.length - 1].startsWith('/')) {
      lines.pop()
      plainTextProxy.value = lines.join('\n')
    }
  }
}

function pluginIconFor(name: string): string {
  const ICON_PATHS: Record<string, string> = {
    'file-text':
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    cpu:
      '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/>',
    zap:
      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    code:
      '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    target:
      '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    sidebar:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
    brain:
      '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44"/><path d="M12 2a8 8 0 0 0-8 8c0 3.866 2.582 7.13 6.12 8.18"/><path d="M12 22a8 8 0 0 0 8-8c0-3.866-2.582-7.13-6.12-8.18"/>',
    maximize:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="12" y1="8" x2="12" y2="16"/>',
    package:
      '<line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    layers:
      '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    user:
      '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    lightbulb:
      '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z"/>',
  }
  const inner = ICON_PATHS[name] || ICON_PATHS['file-text']
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:block">${inner}</svg>`
}

async function onPluginClick(item: PluginItem) {
  if (item.disabled) return
  // 移除当前以 / 开头的最后一行（来自斜杠菜单）
  const lines = (props.modelValue || '').split('\n')
  if (lines.length && lines[lines.length - 1].startsWith('/')) {
    lines.pop()
  }
  // 计算清理后的文本（同步可见，不依赖 props 回流）
  const cleaned = lines.join('\n')
  plainTextProxy.value = cleaned
  pluginMenuOpenProxy.value = false

  if (item.id === 'ask' || item.id === 'explore' || item.id === 'plan') {
    plainTextProxy.value = `@${item.id}`
    nextTick(() => composerRef.value?.focus?.())
    return
  }
  if (item.id === 'role') {
    roleModalVisible.value = true
    pluginMenuOpenProxy.value = false
    return
  }
  if (item.id === 'mcp') {
    mcpPanelOpen.value = true
    skillsPanelOpen.value = false
    reviewPanelOpen.value = false
    pluginMenuOpenProxy.value = false
    loadMcpPlugins()
    return
  }
  if (item.id === 'skill') {
    skillsPanelOpen.value = true
    mcpPanelOpen.value = false
    reviewPanelOpen.value = false
    pluginMenuOpenProxy.value = false
    return
  }
  if (item.id === 'review') {
    reviewPanelOpen.value = true
    mcpPanelOpen.value = false
    skillsPanelOpen.value = false
    pluginMenuOpenProxy.value = false
    return
  }
  if (item.id === 'pet') {
    togglePet()
    return
  }
  if (item.id === 'sidechat') {
    emit('toggleSideChat')
    return
  }
  if (item.id === 'compact') {
    compactModalOpen.value = true
    pluginMenuOpenProxy.value = false
    return
  }
  console.log('[Plugin] clicked:', item.id)
}

// ---------- 会话压缩 ----------
async function confirmCompact() {
  const sid = props.sessionId
  if (!sid || compactLoading.value) return
  compactLoading.value = true
  try {
    await compactSession(sid)
    compactModalOpen.value = false
    emit('compactDone')
  } catch (e) {
    console.error('压缩会话失败', e)
  } finally {
    compactLoading.value = false
  }
}

// ---------- 宠物开关 ----------
async function togglePet() {
  const api = window.electronAPI
  if (!api) return
  const visible = await api.isPetVisible()
  if (visible) {
    api.hidePet()
    // 用户主动关闭，持久化"已关闭"，启动时不再自动恢复
    localStorage.setItem('pet:enabled', '0')
  } else {
    // 从 localStorage 读取上次选中的宠物
    const saved = localStorage.getItem('pet:active')
    if (!saved) {
      // 没有保存过，从后端拉取第一个宠物
      try {
        const res = await listPets()
        const pet = res.pets?.[0]
        if (pet) {
          const spec = buildPetSpec(pet)
          if (spec) {
            api.showPet(spec)
            localStorage.setItem('pet:active', JSON.stringify(spec))
            localStorage.setItem('pet:enabled', '1')
          }
        }
      } catch (e) {
        console.error('加载宠物列表失败', e)
      }
    } else {
      const spec = JSON.parse(saved)
      api.showPet(spec)
      localStorage.setItem('pet:enabled', '1')
    }
  }
}

/** 把后端 PetInfo 转成 pet.html 期望的 spec（含 spritesheet metadata） */
function buildPetSpec(pet: any): any | null {
  const baseUrl = useModelStore().getBaseUrl()
  const spriteRel = pet.spritesheetUrl || pet.animations?.idle
  if (!spriteRel) return null
  // 用 JSON 反复解包，确保传入 IPC 的是纯 plain object（避免 Vue Proxy 不可克隆）
  return JSON.parse(JSON.stringify({
    url: `${baseUrl}${spriteRel}`,
    name: pet.displayName || pet.name,
    frameWidth: pet.frameWidth || 192,
    frameHeight: pet.frameHeight || 208,
    columns: pet.columns || 8,
    rows: pet.rows || 9,
    states: pet.states || undefined,
  }))
}

function applyReviewPrompt(mode: 'unstaged' | 'staged' | 'branch' | 'commit' | 'full') {
  reviewPanelOpen.value = false
  plainTextProxy.value = `@code_review ${mode}`
  nextTick(() => composerRef.value?.focus?.())
}

async function loadMcpPlugins() {
  mcpLoading.value = true
  try {
    const res = await listPlugins()
    mcpPlugins.value = res.plugins
  } catch (e) {
    console.error('加载 MCP 列表失败', e)
  } finally {
    mcpLoading.value = false
  }
}

function closeMcpPanel() {
  mcpPanelOpen.value = false
}

function closeSkillsPanel() {
  skillsPanelOpen.value = false
}

function applySkill(skill: PluginItem) {
  skillsPanelOpen.value = false
  const lines = (props.modelValue || '').split('\n')
  const cleaned = lines.join('\n')
  const sep = cleaned && !cleaned.endsWith('\n') && !cleaned.endsWith(' ') ? ' ' : ''
  plainTextProxy.value = `${cleaned}${sep}@skill:${skill.id} `
  nextTick(() => composerRef.value?.focus?.())
}

function onSubagentClick(agent: PluginItem) {
  if (agent.disabled) return
  pluginMenuOpenProxy.value = false
  const lines = (props.modelValue || '').split('\n')
  if (lines.length && lines[lines.length - 1].startsWith('/')) {
    lines.pop()
  }
  const cleaned = lines.join('\n')
  const sep = cleaned && !cleaned.endsWith('\n') && !cleaned.endsWith(' ') ? ' ' : ''
  plainTextProxy.value = `${cleaned}${sep}@subagent:${agent.id} `
  nextTick(() => composerRef.value?.focus?.())
}

function closeMenus(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  if (!target) return
  if (!target.closest('.workdir-picker-bottom')) {
    workDirMenuOpen.value = false
  }
  if (!target.closest('.branch-picker-bottom')) {
    branchMenuOpen.value = false
  }
  if (!target.closest('.mcp-panel')) {
    mcpPanelOpen.value = false
    skillsPanelOpen.value = false
  }
  if (!target.closest('.review-panel')) {
    reviewPanelOpen.value = false
  }
}

function onGlobalKeydown(e: KeyboardEvent) {
  if (pluginMenuOpenProxy.value) {
    onPluginKeydown(e)
    if (e.defaultPrevented) return
  }
  if (e.key === 'Escape') {
    if (workDirMenuOpen.value) workDirMenuOpen.value = false
    if (branchMenuOpen.value) branchMenuOpen.value = false
    if (mcpPanelOpen.value) mcpPanelOpen.value = false
    if (skillsPanelOpen.value) skillsPanelOpen.value = false
    if (reviewPanelOpen.value) reviewPanelOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', closeMenus)
  document.addEventListener('keydown', onGlobalKeydown)
  // 首次加载技能列表和子Agent列表
  loadSkillItems()
  loadSubagentItems()
  // 同步全局批准模式
  getApprovalMode()
    .then(({ mode }) => {
      if (mode) selectedApproval.value = mode
    })
    .catch((err) => console.error('获取批准模式失败', err))
})

// 每次打开插件/技能菜单时刷新一次，确保与设置页同步
watch(pluginMenuOpenProxy, (open) => {
  if (open) {
    loadSkillItems()
    loadSubagentItems()
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', closeMenus)
  document.removeEventListener('keydown', onGlobalKeydown)
})

function openFilePicker() {
  composerRef.value?.openFilePicker()
}

function clearImages() {
  composerRef.value?.clearImages()
}

function focus() {
  composerRef.value?.focus?.()
}

defineExpose({
  openFilePicker,
  clearImages,
  focus,
})
</script>

<style scoped>
.composer-shell {
  width: 100%;
  max-width: 760px;
  display: flex;
  flex-direction: column;
  background: transparent;
  border: none;
  border-radius: var(--radius-lg);
  padding: 0px 0px 0;
  box-shadow: none;
}

.composer-shell-bottom {
  max-width: 900px;
}

.workdir-warn-toast {
  position: absolute;
  top: -36px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(239, 68, 68, 0.95);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  padding: 6px 16px;
  border-radius: 8px;
  white-space: nowrap;
  z-index: 100;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.composer {
  width: 100%;
  position: relative;
  border: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  border-radius: calc(var(--radius-lg) - 4px);
  background: var(--bg-panel);
  box-shadow: none;
  overflow: visible;
}

.composer-bottom-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: transparent;
  border: none;
  border-radius: 0;
  width: 100%;
  box-sizing: border-box;
}

.composer-with-slash {
  position: relative;
}

.composer-bottom {
  width: 100%;
  flex-shrink: 0;
}

.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 12px 6px;
  gap: 12px;
}

.mcp-panel,
.review-panel {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 6px);
  max-height: 360px;
  background: color-mix(in srgb, var(--bg-panel) 90%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  z-index: 200;
}

.mcp-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.review-panel {
  padding: 6px;
  overflow-y: auto;
}

.review-panel-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 10px 12px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.review-panel-item:hover {
  background: var(--accent-hover);
}

.review-panel-title {
  font-size: 14px;
  font-weight: 500;
}

.review-panel-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.mcp-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  flex-shrink: 0;
}

.mcp-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.mcp-panel-close {
  font-size: 12px;
  color: var(--text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  transition: color 0.12s;
}

.mcp-panel-close:hover {
  color: var(--text);
}

.mcp-panel-loading,
.mcp-panel-empty {
  padding: 16px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.mcp-panel-list {
  padding: 4px 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.mcp-panel-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  gap: 12px;
}

.mcp-panel-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.mcp-panel-item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.mcp-panel-item-desc {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mcp-panel-item-status {
  padding: 0;
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  cursor: pointer;
}

.mcp-panel-item-status:hover {
  color: var(--text);
}

.mcp-panel-item-status:disabled {
  cursor: default;
  opacity: 0.6;
}

.mcp-panel-item--clickable {
  cursor: pointer;
  transition: background 0.12s;
}

.mcp-panel-item--clickable:hover {
  background: var(--accent-hover);
}

.mcp-panel-item-status--enabled {
  color: var(--accent);
}

.bottom-bar-item {
  position: relative;
}

.bottom-bar-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11.5px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
}

.bottom-bar-btn svg {
  opacity: 0.75;
}

.bottom-bar-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text);
}

.bottom-bar-label {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer-left,
.composer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.15s, color 0.15s;
}

.icon-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text);
}

.icon-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}


.model-select {
  appearance: none;
  border: none;
  border-radius: 7px;
  padding: 4px 24px 4px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  background: transparent url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239a9a94' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 6px center;
  cursor: pointer;
  max-width: 200px;
  transition: background 0.15s, color 0.15s;
}

.model-select:hover {
  background-color: rgba(0, 0, 0, 0.04);
  color: var(--text);
}

.send-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: #ececea;
  color: #4a4a46;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
  position: relative;
}

.send-btn:hover:not(:disabled) {
  background: #dededb;
  color: #1a1a18;
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.send-icon {
  stroke-width: 1.8;
}

/* 发送中保留深色实心圆作为可见的视觉锚点（spinner 需要） */
.send-btn--streaming {
  background: var(--send-bg);
  color: #fff;
}

.send-btn--streaming:hover:not(:disabled) {
  background: var(--send-hover);
  color: #fff;
}

/* Slash command menu */
.plugin-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 6px);
  max-height: 360px;
  overflow-y: auto;
  background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  padding: 6px;
  z-index: 200;
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
}

.plugin-menu-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.plugin-menu-group {
  display: flex;
  flex-direction: column;
}

.plugin-menu-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 8px 10px 4px;
  user-select: none;
}

.plugin-menu-item {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  transition: background 0.12s, color 0.12s;
  min-height: 36px;
}

.plugin-menu-item--active,
.plugin-menu-item:hover {
  background: var(--accent-hover);
}

.plugin-menu-item--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.plugin-menu-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
  width: 16px;
  height: 16px;
}

.plugin-menu-icon :deep(svg) {
  display: block;
}

.plugin-menu-text {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.plugin-menu-label {
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  flex-shrink: 0;
}

.plugin-menu-desc {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plugin-menu-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 999px;
  white-space: nowrap;
}

.plugin-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 4px;
}

/* 请求批准下拉（玻璃感） */
.approval-picker {
  position: relative;
  display: flex;
  align-items: center;
}

.approval-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.approval-trigger:hover {
  background: rgba(0, 0, 0, 0.04);
}

.approval-trigger-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.approval-trigger-label {
  font-weight: 500;
  white-space: nowrap;
}

.approval-trigger-caret {
  color: var(--text-muted);
  flex-shrink: 0;
}

.approval-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  width: 380px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  z-index: 220;
}

.approval-menu-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 6px;
}

.approval-menu-title {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.approval-menu-link {
  font-size: 12px;
  color: var(--text-secondary);
  text-decoration: none;
}

.approval-menu-link:hover {
  color: var(--text);
  text-decoration: underline;
}

.approval-menu-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.approval-menu-item {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  color: var(--text);
  transition: background 0.12s;
}

.approval-menu-item:hover,
.approval-menu-item--active {
  background: var(--accent-hover);
}

.approval-menu-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.approval-menu-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.approval-menu-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.2;
}

.approval-menu-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.35;
  white-space: normal;
}

.approval-menu-check {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.send-btn--streaming {
  cursor: pointer;
}

.send-btn--streaming:hover {
  background: var(--send-hover);
}

.send-icon-inner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.spinner-circle {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin-send 0.75s linear infinite;
}

@keyframes spin-send {
  to { transform: rotate(360deg); }
}

.workdir-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  min-width: 280px;
  max-width: 420px;
  background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  padding: 6px;
  z-index: 200;
  overflow: visible;
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
}

.workdir-menu-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 6px 10px 4px;
}

.workdir-menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 200px;
  overflow-y: auto;
}

.workdir-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.12s, color 0.12s;
}

.workdir-menu-item:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.workdir-menu-item.active {
  background: var(--accent-active);
  color: var(--text);
}

.workdir-menu-item svg {
  flex-shrink: 0;
  color: var(--text-muted);
}

.workdir-menu-path {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: ui-monospace, monospace;
}

.workdir-menu-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 10px 10px;
}

.workdir-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 4px;
}

.workdir-menu-new {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.workdir-menu-new:hover {
  background: var(--accent-hover);
}

/* ---------- 分支选择菜单 ---------- */
.branch-picker-bottom {
  position: relative;
}

.branch-dirty-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
  margin-left: 2px;
  flex-shrink: 0;
}

.branch-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  min-width: 260px;
  max-width: 360px;
  background: color-mix(in srgb, var(--bg-panel) 82%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  padding: 6px;
  z-index: 200;
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
}

.branch-menu-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 6px 10px 4px;
}

.branch-menu-dirty {
  font-size: 10px;
  font-weight: 500;
  color: #f59e0b;
  text-transform: none;
  letter-spacing: 0;
}

.branch-menu-search {
  width: calc(100% - 12px);
  margin: 2px 6px 4px;
  padding: 5px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input, #fff);
  color: var(--text);
  outline: none;
}

.branch-menu-search:focus {
  border-color: var(--accent, #4f8cff);
}

.branch-menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}

.branch-menu-item {
  display: flex;
  align-items: center;
  padding: 0 4px 0 0;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.12s, color 0.12s;
}

.branch-menu-item:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.branch-menu-item.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
}

.branch-menu-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  cursor: pointer;
}

.branch-menu-name svg {
  flex-shrink: 0;
  color: var(--text-muted);
}

.branch-menu-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: ui-monospace, monospace;
}

.branch-menu-action {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.12s, background 0.12s, color 0.12s;
}

.branch-menu-item:hover .branch-menu-action {
  opacity: 1;
}

.branch-menu-action:hover {
  background: var(--accent-active);
  color: var(--text);
}

.branch-menu-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 10px 10px;
}

.branch-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 4px;
}

.branch-menu-footer {
  padding: 0;
}

.branch-menu-new {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.branch-menu-new:hover {
  background: var(--accent-hover);
}

.branch-menu-create {
  display: flex;
  gap: 4px;
  padding: 4px 4px 2px;
}

.branch-menu-input {
  flex: 1;
  min-width: 0;
  padding: 5px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input, #fff);
  color: var(--text);
  outline: none;
  font-family: ui-monospace, monospace;
}

.branch-menu-input:focus {
  border-color: var(--accent, #4f8cff);
}

.branch-menu-confirm,
.branch-menu-cancel {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.branch-menu-confirm {
  background: var(--accent, #4f8cff);
  border-color: var(--accent, #4f8cff);
  color: #fff;
}

.branch-menu-confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.branch-menu-cancel:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.branch-menu-message {
  margin: 4px 6px 2px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--accent-hover);
  border-radius: 4px;
  word-break: break-all;
}

.branch-menu-message.error {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.1);
}

/* ---------- 分支操作确认弹窗（与 SettingsPanel 删除/解绑弹窗风格保持一致） ---------- */
.branch-confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
}

.branch-confirm-dialog {
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 360px;
  max-width: 480px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.branch-confirm-header {
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}

.branch-confirm-body {
  padding: 20px;
  color: var(--text);
}

.branch-confirm-body p {
  margin: 0;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.branch-confirm-footer {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.branch-confirm-btn {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.branch-confirm-btn:hover {
  opacity: 0.85;
}

.branch-confirm-btn-cancel {
  background: #e5e7eb;
  color: #374151;
}

.branch-confirm-btn-primary {
  background: #1f2937;
  color: #ffffff;
}

.branch-confirm-btn-danger {
  background: #1f2937;
  color: #ffffff;
}

/* ---------- 压缩确认弹窗 ---------- */
.compact-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.compact-modal {
  width: 440px;
  max-width: 92vw;
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  font-size: 14px;
}
.compact-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, #eee);
}
.compact-modal-title {
  font-weight: 600;
  font-size: 15px;
}
.compact-modal-close {
  background: none;
  border: none;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  color: var(--text-secondary, #999);
  padding: 0 4px;
}
.compact-modal-close:hover {
  color: var(--text-primary, #333);
}
.compact-modal-body {
  padding: 18px 20px;
}
.compact-modal-desc {
  margin: 0 0 16px;
  color: var(--text-secondary, #666);
  line-height: 1.6;
}
.compact-modal-info {
  background: var(--bg-secondary, #f7f7f8);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.compact-info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.compact-info-label {
  color: var(--text-secondary, #888);
  flex-shrink: 0;
}
.compact-info-value {
  font-weight: 500;
  text-align: right;
}
.compact-info-mono {
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}
.compact-info-highlight {
  color: var(--accent, #4f7cff);
}
.context-usage-breakdown {
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--bg-secondary, #f7f7f8);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.context-usage-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}
.context-usage-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #222);
}
.context-usage-total {
  font-size: 12px;
  color: var(--text-secondary, #888);
}
.context-usage-bar {
  display: flex;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--border-color, #e5e5e5);
}
.context-usage-bar-seg {
  display: block;
  height: 100%;
}
.context-usage-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.context-usage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.context-usage-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.context-usage-label {
  flex: 1;
  color: var(--text-secondary, #555);
}
.context-usage-value {
  color: var(--text-primary, #222);
  font-variant-numeric: tabular-nums;
}
.compact-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-color, #eee);
}
.compact-btn {
  padding: 7px 18px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
}
.compact-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.compact-btn-cancel {
  background: var(--bg-secondary, #f0f0f0);
  color: var(--text-primary, #333);
}
.compact-btn-cancel:hover:not(:disabled) {
  background: var(--bg-tertiary, #e5e5e5);
}
.compact-btn-confirm {
  background: var(--accent, #4f7cff);
  color: #fff;
}
.compact-btn-confirm:hover:not(:disabled) {
  background: var(--accent-hover, #3a66e0);
}
</style>
