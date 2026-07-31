<template>
  <div class="chat-app">
    <ChatSidebar
      :sidebar-open="sidebarOpen"
      :sessions="sessions"
      :current-session-id="null"
      :user="auth.user"
      @toggle-sidebar="sidebarOpen = !sidebarOpen"
      @create-new-chat="goToChat"
      @select-session="goToSession"
      @logout="handleLogout"
    />
    <div class="auto-page">
      <!-- 头部 -->
      <header class="auto-head">
        <div class="auto-head-left">
          <h2 class="auto-title">定时任务</h2>
        </div>
        <button type="button" class="ds-btn ds-btn-primary" @click="openCreateDialog">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          新建任务
        </button>
      </header>

      <!-- 内容区 -->
      <div class="auto-body">
      <!-- 空状态 -->
      <div v-if="tasks.length === 0 && !loading" class="auto-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <p>暂无定时任务，点击上方按钮或下方模板快速创建</p>
      </div>

      <!-- 已配置任务卡片 -->
      <div v-else class="auto-grid">
        <div v-for="task in tasks" :key="task.id" class="auto-card">
          <div class="auto-card-head">
            <span class="auto-card-icon" :class="'st-' + task.status">
              <svg v-if="task.status === 'running'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <svg v-else-if="task.status === 'completed'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              <svg v-else-if="task.status === 'failed'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </span>
            <h3 class="auto-card-title">{{ task.title || '未命名' }}</h3>
          </div>
          <p class="auto-card-content">{{ task.task_content || '无执行内容' }}</p>
          <div class="auto-card-meta">
            <span class="auto-schedule-label">{{ formatScheduleLabel(task) }}</span>
            <button v-if="task.session_id && !isPlatformSession(task.session_id)" type="button" class="auto-session-link" @click="openTaskSession(task)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              查看会话
            </button>
          </div>
          <div class="auto-card-footer">
            <span class="auto-status" :class="'st-' + task.status">{{ statusLabel(task.status) }}</span>
            <div class="auto-card-actions">
              <button v-if="task.status === 'pending'" type="button" class="auto-btn-text auto-btn-danger" @click="handleCancel(task.id)">取消</button>
              <button type="button" class="auto-btn-text" @click="openTaskDetail(task)">详情</button>
              <button type="button" class="auto-btn-text" @click="handleDelete(task.id)">删除</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 模板区域 -->
      <div class="auto-templates">
        <div class="auto-templates-head">
          <div class="auto-templates-title">快捷模板</div>
          <div class="auto-templates-desc">从模板快速创建常用自动化任务</div>
        </div>
        <div class="auto-template-grid">
          <div v-for="tmpl in templates" :key="tmpl.id" class="auto-template-card" @click="applyTemplate(tmpl)">
            <div class="auto-template-icon" :class="tmpl.color">
              <span v-html="tmpl.icon" />
            </div>
            <div class="auto-template-info">
              <div class="auto-template-name">{{ tmpl.name }}</div>
              <div class="auto-template-desc">{{ tmpl.desc }}</div>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="auto-template-arrow"><polyline points="9 18 15 12 9 6"/></svg>
          </div>
        </div>
      </div>
    </div> <!-- /auto-body -->
  </div> <!-- /auto-page -->

  <!-- 新建任务弹窗 -->
  <div v-if="showDialog" class="auto-overlay auto-form-overlay" @click.self="closeDialog">
      <div class="auto-form-modal">
        <header class="auto-head">
          <h2 class="auto-title">新建定时任务</h2>
          <button type="button" class="auto-close" @click="closeDialog">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </header>
        <form class="auto-form" @submit.prevent="handleSubmit">
          <div class="auto-field">
            <label class="auto-field-label">名称 <span class="auto-req">*</span></label>
            <input v-model="form.title" type="text" class="ds-input" placeholder="请输入任务名称" maxlength="50" />
          </div>
          <div class="auto-field">
            <label class="auto-field-label">要求说明 <span class="auto-req">*</span></label>
            <textarea v-model="form.task_content" class="ds-input auto-textarea" placeholder="请输入任务要求说明，到点后会发送给 AI 执行" maxlength="8000" rows="4"></textarea>
          </div>
          <div class="auto-field">
            <label class="auto-field-label">执行时间 <span class="auto-req">*</span></label>
            <div class="auto-schedule-row">
              <select v-model="form.schedule_type" class="ds-input auto-select">
                <option value="once">单次</option>
                <option value="daily">每天</option>
                <option value="interval">固定间隔</option>
              </select>
              <template v-if="form.schedule_type === 'once'">
                <input v-model="form.onceDate" type="date" class="ds-input auto-date-input" />
                <input v-model="form.onceTime" type="time" class="ds-input auto-date-input" />
              </template>
              <template v-if="form.schedule_type === 'daily'">
                <select v-model="form.dailyHour" class="ds-input auto-date-input">
                  <option v-for="h in hourOptions" :key="h" :value="h">{{ h }}时</option>
                </select>
                <select v-model="form.dailyMinute" class="ds-input auto-date-input">
                  <option v-for="m in minuteOptions" :key="m" :value="m">{{ m }}分</option>
                </select>
              </template>
              <template v-if="form.schedule_type === 'interval'">
                <select v-model.number="form.intervalHours" class="ds-input auto-date-input">
                  <option :value="1">每1小时</option>
                  <option :value="2">每2小时</option>
                  <option :value="6">每6小时</option>
                  <option :value="12">每12小时</option>
                  <option :value="24">每天</option>
                </select>
              </template>
            </div>
          </div>
          <div class="auto-field">
            <label class="auto-field-label">结果推送</label>
            <div class="auto-radio-group">
              <label class="auto-radio" :class="{ active: form.delivery_target === 'web_new' }">
                <input type="radio" value="web_new" v-model="form.delivery_target" />
                <span>推送到新会话</span>
              </label>
              <label class="auto-radio" :class="{ active: form.delivery_target === 'web_bind' }">
                <input type="radio" value="web_bind" v-model="form.delivery_target" />
                <span>推送到已有会话</span>
              </label>
            </div>
            <template v-if="form.delivery_target === 'web_bind'">
              <select v-model="form.session_id" class="ds-input auto-session-select">
                <option value="">-- 请选择会话 --</option>
                <option v-for="s in sessions" :key="s.id" :value="s.id">{{ s.title || s.id.substring(0, 16) }}</option>
              </select>
              <p v-if="sessions.length === 0" class="auto-hint auto-hint-warn">暂无可用会话，请先在对话页创建聊天</p>
            </template>
            <p v-else class="auto-hint">任务执行后自动创建新会话，可在对话页查看</p>
          </div>
          <footer class="auto-form-foot">
            <button type="button" class="ds-btn ds-btn-secondary" @click="closeDialog">取消</button>
            <button type="submit" class="ds-btn ds-btn-primary" :disabled="!isFormValid || saving">
              <span v-if="saving">创建中…</span>
              <span v-else>创建任务</span>
            </button>
          </footer>
        </form>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <div v-if="showDetailDialog" class="auto-overlay auto-form-overlay" @click.self="closeDetailDialog">
      <div class="auto-form-modal">
        <header class="auto-head">
          <h2 class="auto-title">任务详情</h2>
          <button type="button" class="auto-close" @click="closeDetailDialog">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </header>
        <div v-if="detailLoading" class="auto-detail-loading">加载中…</div>
        <div v-else-if="detailTask" class="auto-form auto-detail-body">
          <div class="auto-field">
            <label class="auto-field-label">名称</label>
            <div class="auto-detail-value">{{ detailTask.title || '未命名' }}</div>
          </div>
          <div class="auto-field">
            <label class="auto-field-label">要求说明</label>
            <div class="auto-detail-text">{{ detailTask.task_content || '（无）' }}</div>
          </div>
          <div class="auto-field">
            <label class="auto-field-label">执行时间</label>
            <div class="auto-detail-value">{{ formatScheduleDetail(detailTask) }}</div>
            <p v-if="detailTask.scheduled_at" class="auto-hint">计划执行：{{ formatDateTime(detailTask.scheduled_at) }}</p>
          </div>
          <div class="auto-field">
            <label class="auto-field-label">任务状态</label>
            <span class="auto-status" :class="'st-' + detailTask.status">{{ statusLabel(detailTask.status) }}</span>
          </div>
          <div class="auto-detail-meta">
            <div class="auto-field">
              <label class="auto-field-label">创建时间</label>
              <div class="auto-detail-value">{{ formatDateTime(detailTask.created_at) || '-' }}</div>
            </div>
            <div class="auto-field">
              <label class="auto-field-label">更新时间</label>
              <div class="auto-detail-value">{{ formatDateTime(detailTask.updated_at) || '-' }}</div>
            </div>
          </div>
        </div>
        <footer class="auto-form-foot">
          <button v-if="detailTask && detailTask.session_id && !isPlatformSession(detailTask.session_id)" type="button" class="ds-btn ds-btn-secondary" @click="openTaskSession(detailTask)">查看会话</button>
          <button type="button" class="ds-btn ds-btn-primary" @click="closeDetailDialog">关闭</button>
        </footer>
      </div>
    </div> <!-- /detail modal -->
    <SettingsModal v-if="settingsStore.settingsOpen" />
  </div> <!-- /chat-app -->
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '../stores/settings'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import ChatSidebar from './ChatSidebar.vue'
import SettingsModal from '../components/SettingsModal.vue'
import './ChatPage.css'

const router = useRouter()
const settingsStore = useSettingsStore()
const auth = useAuthStore()

const sidebarOpen = ref(true)
const hourOptions = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const minuteOptions = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

const tasks = ref([])
const sessions = ref([])
const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)
const showDetailDialog = ref(false)
const detailLoading = ref(false)
const detailTask = ref(null)

const form = ref({
  title: '',
  task_content: '',
  schedule_type: 'once',
  onceDate: '',
  onceTime: '',
  dailyHour: '09',
  dailyMinute: '00',
  intervalHours: 1,
  delivery_target: 'web_new',
  session_id: '',
})

const isFormValid = computed(() => {
  const f = form.value
  if (!f.title.trim() || !f.task_content.trim()) return false
  if (f.schedule_type === 'once' && (!f.onceDate || !f.onceTime)) return false
  if (f.delivery_target === 'web_bind' && !f.session_id) return false
  return true
})

// ============ 模板 ============
const templates = [
  {
    id: 'daily-summary',
    name: '每日摘要报告',
    desc: '每天定时汇总当日工作，生成日报',
    title: '每日工作摘要',
    task_content: '请汇总今天的工作进展，包括完成的任务、遇到的问题和明天的计划，生成一份简洁的工作日报。',
    schedule_type: 'daily',
    scheduleTime: '18:00',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    color: 'blue',
  },
  {
    id: 'weekly-review',
    name: '每周复盘总结',
    desc: '回顾本周完成情况，输出周报',
    title: '本周工作复盘',
    task_content: '回顾本周所有已完成的工作事项，分析进度达成情况，总结经验教训并列出下周重点工作计划。',
    schedule_type: 'daily',
    scheduleTime: '17:00',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    color: 'green',
  },
  {
    id: 'code-check',
    name: '代码质量检查',
    desc: '定期扫描项目代码，发现潜在问题',
    title: '代码质量扫描',
    task_content: '检查当前项目的代码质量，包括：1. 潜在的 bug 和逻辑问题 2. 代码风格一致性 3. 性能优化建议。输出具体的文件路径、问题描述和修复建议。',
    schedule_type: 'interval',
    intervalHours: 6,
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    color: 'purple',
  },
  {
    id: 'news-briefing',
    name: '行业资讯早报',
    desc: '每天早上获取最新科技动态',
    title: '今日科技资讯',
    task_content: '搜索今天最新的科技/人工智能/编程领域的重要新闻和动态，整理成简明的早报格式，每条新闻包含标题和一句话摘要。',
    schedule_type: 'daily',
    scheduleTime: '08:30',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8z"/></svg>',
    color: 'orange',
  },
  {
    id: 'competitor-watch',
    name: '竞品动态监控',
    desc: '定时监控竞品官网/社交媒体更新',
    title: '竞品动态巡检',
    task_content: '搜索以下竞品的最新动态和产品更新：1. 主要功能变化 2. 定价策略调整 3. 用户反馈趋势。整理成简要的竞品监控报告，突出值得关注的信号。',
    schedule_type: 'interval',
    intervalHours: 12,
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    color: 'red',
  },
  {
    id: 'server-health',
    name: '服务器健康巡检',
    desc: '定期检查服务器资源与服务状态',
    title: '服务器健康检查',
    task_content: '执行服务器健康检查：1. 检查 CPU/内存/磁盘使用率 2. 查看关键服务运行状态 3. 检查最近的重要错误日志。输出健康报告，如有异常请标注严重级别和建议操作。',
    schedule_type: 'interval',
    intervalHours: 2,
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
    color: 'cyan',
  },
  {
    id: 'meeting-notes',
    name: '会议纪要整理',
    desc: '每天定时整理当日会议记录',
    title: '会议纪要汇总',
    task_content: '整理今天的会议记录，提取每个会议的关键信息：1. 会议主题与参会人员 2. 讨论的核心议题 3. 达成的决策与结论 4. 待跟进的行动项及负责人。输出结构化的会议纪要汇总。',
    schedule_type: 'daily',
    scheduleTime: '20:00',
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    color: 'blue',
  },
  {
    id: 'project-progress',
    name: '项目进度跟踪',
    desc: '定时汇总项目里程碑与风险',
    title: '项目进度报告',
    task_content: '跟踪当前项目的进度状态：1. 各里程碑完成情况 2. 关键路径上的任务进展 3. 识别延期风险与阻塞项 4. 资源使用与偏差分析。输出项目进度简报，标注需要关注的预警项。',
    schedule_type: 'interval',
    intervalHours: 24,
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
    color: 'green',
  },
]

// ============ 工具函数 ============
function isPlatformSession(sessionId) {
  return /^__(wechat|qq|feishu)__$/.test(sessionId || '')
}

function statusLabel(status) {
  return { pending: '待执行', running: '执行中', completed: '已完成', cancelled: '已取消', failed: '失败' }[status] || status
}

function formatIntervalLabel(minutes) {
  if (minutes >= 1440 && minutes % 1440 === 0) return minutes / 1440 === 1 ? '每天' : `每${minutes / 1440}天`
  if (minutes >= 60 && minutes % 60 === 0) return `每${minutes / 60}小时`
  return `每${minutes}分钟`
}

function formatScheduleLabel(task) {
  const st = task.schedule_type || 'once'
  if (st === 'once') {
    if (task.scheduled_at) {
      const d = new Date(task.scheduled_at)
      if (!isNaN(d.getTime())) return '单次 ' + d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return '单次'
  }
  if (st === 'daily') {
    if (task.scheduled_at) {
      const d = new Date(task.scheduled_at)
      if (!isNaN(d.getTime())) return `每天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    }
    return '每天'
  }
  if (st === 'interval') return formatIntervalLabel(Number(task.interval_minutes) || 60)
  return '未知'
}

function formatScheduleDetail(task) {
  const st = task.schedule_type || 'once'
  if (st === 'once') return '单次执行'
  if (st === 'daily') return formatScheduleLabel(task)
  if (st === 'interval') return `固定间隔 · ${formatIntervalLabel(Number(task.interval_minutes) || 60)}`
  return formatScheduleLabel(task)
}

function formatDateTime(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDateForInput(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}

// ============ 侧边栏操作 ============
function goToChat() {
  router.push({ name: 'chat' })
}

function goToSession(s) {
  if (s.id) {
    settingsStore.closeAutomation()
    router.push({ name: 'chat-session', params: { sessionId: s.id } })
  }
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

// ============ 操作 ============
function openCreateDialog() {
  const now = new Date()
  form.value = {
    title: '',
    task_content: '',
    schedule_type: 'once',
    onceDate: formatDateForInput(now),
    onceTime: String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'),
    dailyHour: '09',
    dailyMinute: '00',
    intervalHours: 1,
    delivery_target: 'web_new',
    session_id: '',
  }
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
}

function applyTemplate(tmpl) {
  if (tmpl.schedule_type === 'daily') {
    const timeStr = tmpl.scheduleTime || '09:00'
    form.value = {
      title: tmpl.title, task_content: tmpl.task_content, schedule_type: 'daily',
      onceDate: '', onceTime: '', dailyHour: timeStr.split(':')[0], dailyMinute: timeStr.split(':')[1] || '00',
      intervalHours: 1, delivery_target: 'web_new', session_id: '',
    }
  } else if (tmpl.schedule_type === 'interval') {
    form.value = {
      title: tmpl.title, task_content: tmpl.task_content, schedule_type: 'interval',
      onceDate: '', onceTime: '', dailyHour: '09', dailyMinute: '00',
      intervalHours: tmpl.intervalHours || 1, delivery_target: 'web_new', session_id: '',
    }
  } else {
    const now = new Date()
    form.value = {
      title: tmpl.title, task_content: tmpl.task_content, schedule_type: 'once',
      onceDate: formatDateForInput(now), onceTime: '09:00',
      dailyHour: '09', dailyMinute: '00', intervalHours: 1, delivery_target: 'web_new', session_id: '',
    }
  }
  showDialog.value = true
}

async function handleSubmit() {
  if (!isFormValid.value) return
  saving.value = true
  const f = form.value
  let scheduled_at, interval_minutes
  if (f.schedule_type === 'once') {
    scheduled_at = f.onceDate + 'T' + f.onceTime + ':00'
  } else if (f.schedule_type === 'daily') {
    const now = new Date()
    const timeStr = f.dailyHour.padStart(2, '0') + ':' + f.dailyMinute.padStart(2, '0') + ':00'
    scheduled_at = formatDateForInput(now) + 'T' + timeStr
    if (new Date(scheduled_at) <= now) {
      const tomorrow = new Date(now.getTime() + 86400000)
      scheduled_at = formatDateForInput(tomorrow) + 'T' + timeStr
    }
  } else if (f.schedule_type === 'interval') {
    interval_minutes = f.intervalHours * 60
  }
  const payload = {
    title: f.title.trim(),
    task_content: f.task_content.trim(),
    schedule_type: f.schedule_type,
    scheduled_at,
    interval_minutes,
    session_id: f.delivery_target === 'web_bind' ? f.session_id : null,
    session_mode: f.delivery_target === 'web_bind' ? 'bind' : 'new',
  }
  try {
    await api.post('/api/scheduled-tasks', payload)
    ElMessage.success('定时任务已创建')
    closeDialog()
    await loadTasks()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '创建失败')
  } finally {
    saving.value = false
  }
}

async function handleCancel(id) {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '', { type: 'warning' })
    await api.put(`/api/scheduled-tasks/${id}/cancel`)
    ElMessage.success('已取消')
    await loadTasks()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.response?.data?.detail || '取消失败')
  }
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定要删除该任务吗？删除后不可恢复。', '', { type: 'warning' })
    await api.delete(`/api/scheduled-tasks/${id}`)
    ElMessage.success('已删除')
    await loadTasks()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.response?.data?.detail || '删除失败')
  }
}

async function openTaskDetail(task) {
  showDetailDialog.value = true
  detailLoading.value = true
  detailTask.value = task
  try {
    const res = await api.get(`/api/scheduled-tasks/${task.id}`)
    detailTask.value = res.data
  } catch {
    detailTask.value = task
  } finally {
    detailLoading.value = false
  }
}

function closeDetailDialog() {
  showDetailDialog.value = false
  detailTask.value = null
}

function openTaskSession(task) {
  if (!task.session_id) return
  settingsStore.closeAutomation()
  router.push({ name: 'chat-session', params: { sessionId: task.session_id } })
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await api.get('/api/scheduled-tasks', { params: { page: 1, page_size: 50 } })
    tasks.value = res.data.tasks || []
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function loadSessions() {
  try {
    const res = await api.get('/api/chat/sessions')
    sessions.value = (res.data || []).filter(s => !s.id.startsWith('__'))
  } catch {
    sessions.value = []
  }
}

watch(() => form.value.delivery_target, (target) => {
  if (target === 'web_bind') {
    form.value.session_id = ''
    loadSessions()
  }
})

onMounted(async () => {
  await loadTasks()
  await loadSessions()
})
</script>

<style scoped>
/* ============ 遮罩 ============ */
.auto-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--bg-overlay-l4);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}
.auto-form-overlay { z-index: 2001; }

/* ============ 页面容器 ============ */
.auto-page {
  flex: 1; height: 100%; min-height: 0; display: flex; flex-direction: column;
  background-color: var(--bg-base-secondary); overflow: hidden;
}

/* ============ 页面内容（除头部外滚动） ============ */
.auto-body {
  flex: 1; overflow-y: auto; padding: var(--spacer-32);
}
.auto-grid, .auto-templates, .auto-empty {
  max-width: 1200px; margin-left: auto; margin-right: auto;
}

/* ============ 头部（页面 + 弹窗共用） ============ */
.auto-head {
  display: flex; align-items: center; justify-content: space-between;
  height: 60px; padding: 0 var(--spacer-24); flex-shrink: 0;
  background-color: var(--bg-base-default);
  border-bottom: 1px solid var(--border-neutral-l1);
}
.auto-head-left { display: flex; align-items: center; gap: var(--spacer-8); }
.auto-back {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; background: transparent;
  border-radius: var(--radius-8); color: var(--icon-secondary); cursor: pointer;
  transition: background-color .12s, color .12s;
}
.auto-back:hover { background-color: var(--bg-overlay-l1); color: var(--icon-default); }
.auto-title {
  font-family: var(--font-family-heading); font-size: 18px; font-weight: 600;
  color: var(--text-default); margin: 0; letter-spacing: -0.01em;
}
.auto-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; background: transparent;
  border-radius: var(--radius-8); color: var(--icon-secondary); cursor: pointer;
  transition: background-color .12s, color .12s;
}
.auto-close:hover { background-color: var(--bg-overlay-l1); color: var(--icon-default); }

/* ============ 黑白主色按钮 / 输入焦点（覆盖品牌紫） ============ */
.auto-page .ds-btn-primary,
.auto-form-modal .ds-btn-primary {
  background-color: var(--text-default);
  color: var(--bg-base-default);
  border-color: var(--text-default);
}
.auto-page .ds-btn-primary:hover:not(:disabled),
.auto-form-modal .ds-btn-primary:hover:not(:disabled) {
  background-color: var(--icon-default);
  border-color: var(--icon-default);
}
.auto-page .ds-btn-primary:active:not(:disabled),
.auto-form-modal .ds-btn-primary:active:not(:disabled) {
  background-color: var(--text-default);
  border-color: var(--text-default);
}
.auto-page .ds-input:focus,
.auto-form-modal .ds-input:focus {
  border-color: var(--text-default);
  box-shadow: 0 0 0 3px var(--bg-overlay-l2);
}

/* ============ 空状态 ============ */
.auto-empty {
  display: flex; flex-direction: column; align-items: center; gap: var(--spacer-12);
  padding: var(--spacer-48) 0; color: var(--text-tertiary); text-align: center;
}
.auto-empty svg { color: var(--text-disabled); }
.auto-empty p { margin: 0; font-size: 13px; }

/* ============ 任务卡片 ============ */
.auto-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: var(--spacer-16);
}
.auto-card {
  background-color: var(--bg-base-default);
  border: 1px solid var(--border-neutral-l1);
  border-radius: var(--radius-12);
  padding: var(--spacer-20);
  transition: border-color .15s, box-shadow .15s, transform .15s;
}
.auto-card:hover {
  border-color: var(--border-neutral-l2);
  box-shadow: 0 4px 16px rgba(12,13,14,.06);
  transform: translateY(-1px);
}

.auto-card-head { display: flex; align-items: center; gap: var(--spacer-12); margin-bottom: var(--spacer-10); }
.auto-card-icon {
  flex-shrink: 0; width: 32px; height: 32px; border-radius: var(--radius-8);
  display: flex; align-items: center; justify-content: center;
  background-color: var(--bg-overlay-l1); color: var(--icon-secondary);
}
.auto-card-icon.st-pending { background-color: var(--bg-overlay-l1); color: var(--icon-tertiary); }
.auto-card-icon.st-running { background-color: var(--bg-overlay-l2); color: var(--icon-default); }
.auto-card-icon.st-completed { background-color: var(--text-default); color: var(--bg-base-default); }
.auto-card-icon.st-failed { background-color: var(--status-error-surface-l1); color: var(--status-error-default); }
.auto-card-icon.st-cancelled { background-color: var(--bg-overlay-l1); color: var(--text-disabled); }

.auto-card-title {
  font-size: 14px; font-weight: 600; color: var(--text-default); margin: 0; flex: 1;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.auto-card-content {
  font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin: 0 0 var(--spacer-12);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.auto-card-meta { display: flex; align-items: center; gap: var(--spacer-10); margin-bottom: var(--spacer-12); }
.auto-schedule-label { font-size: 12px; color: var(--text-tertiary); }
.auto-session-link {
  display: inline-flex; align-items: center; gap: 4px; font-size: 11px;
  color: var(--text-secondary); background-color: var(--bg-overlay-l1);
  padding: 3px 8px; border-radius: var(--radius-6); border: none; cursor: pointer;
  transition: background-color .12s, color .12s;
}
.auto-session-link:hover { background-color: var(--bg-overlay-l2); color: var(--text-default); }

.auto-card-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding-top: var(--spacer-12); border-top: 1px solid var(--border-neutral-l1);
}
.auto-status {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500;
}
.auto-status::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; flex-shrink: 0;
}
.auto-status.st-pending { color: var(--text-tertiary); }
.auto-status.st-running { color: var(--text-secondary); }
.auto-status.st-completed { color: var(--text-default); }
.auto-status.st-cancelled { color: var(--text-disabled); }
.auto-status.st-failed { color: var(--status-error-default); }

.auto-card-actions { display: flex; gap: var(--spacer-2); }
.auto-btn-text {
  background: none; border: none; color: var(--text-secondary);
  font-size: 12px; cursor: pointer; padding: 6px 10px; border-radius: var(--radius-6);
  transition: all .12s;
}
.auto-btn-text:hover { background-color: var(--bg-overlay-l1); color: var(--text-default); }
.auto-btn-danger:hover { color: var(--status-error-default); background-color: var(--status-error-surface-l1); }

/* ============ 模板区域 ============ */
.auto-templates { margin-top: var(--spacer-40); padding-top: var(--spacer-24); border-top: 1px solid var(--border-neutral-l1); }
.auto-templates-head { margin-bottom: var(--spacer-16); }
.auto-templates-title {
  font-family: var(--font-family-heading); font-size: 16px; font-weight: 600; color: var(--text-default);
}
.auto-templates-desc { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; }

.auto-template-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--spacer-12);
}
.auto-template-card {
  display: flex; align-items: center; gap: var(--spacer-12);
  padding: var(--spacer-16);
  background-color: var(--bg-base-default);
  border: 1px solid var(--border-neutral-l1);
  border-radius: var(--radius-12);
  cursor: pointer; transition: border-color .15s, box-shadow .15s, transform .15s;
}
.auto-template-card:hover {
  border-color: var(--border-neutral-l3);
  box-shadow: 0 4px 16px rgba(12,13,14,.06);
  transform: translateY(-1px);
}

.auto-template-icon {
  flex-shrink: 0; width: 38px; height: 38px; border-radius: var(--radius-10);
  display: flex; align-items: center; justify-content: center;
  background-color: var(--bg-overlay-l1); color: var(--icon-default);
}
/* 所有彩色变体统一为单色 */
.auto-template-icon.blue,
.auto-template-icon.green,
.auto-template-icon.purple,
.auto-template-icon.orange,
.auto-template-icon.red,
.auto-template-icon.cyan {
  background-color: var(--bg-overlay-l1); color: var(--icon-default);
}

.auto-template-info { flex: 1; min-width: 0; }
.auto-template-name { font-size: 13px; font-weight: 600; color: var(--text-default); margin-bottom: 2px; }
.auto-template-desc {
  font-size: 11px; color: var(--text-tertiary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.auto-template-arrow { flex-shrink: 0; color: var(--text-tertiary); opacity: .4; transition: all .15s; }
.auto-template-card:hover .auto-template-arrow { opacity: 1; color: var(--text-default); transform: translateX(2px); }

/* ============ 表单弹窗 ============ */
.auto-form-modal {
  width: 100%; max-width: 540px; max-height: 85vh; overflow-y: auto;
  background-color: var(--bg-base-default);
  border: 1px solid var(--border-neutral-l1);
  border-radius: var(--radius-16);
  box-shadow: 0 24px 64px rgba(12,13,14,.16), 0 8px 24px rgba(12,13,14,.08);
}
.auto-form { padding: var(--spacer-24); display: flex; flex-direction: column; gap: var(--spacer-16); }

.auto-field { display: flex; flex-direction: column; gap: var(--spacer-6); }
.auto-field-label {
  font-family: var(--font-family-heading); font-size: 13px; font-weight: 600; color: var(--text-default);
}
.auto-req { color: var(--status-error-default); }
.auto-textarea { resize: vertical; min-height: 80px; font-family: inherit; }
.auto-hint { font-size: 11px; color: var(--text-tertiary); margin: 0; }
.auto-hint-warn { color: var(--status-error-default); }

.auto-schedule-row { display: flex; gap: var(--spacer-8); flex-wrap: wrap; }
.auto-select { min-width: 110px; }
.auto-date-input { min-width: 110px; }
.auto-session-select { margin-top: var(--spacer-8); }

.auto-radio-group { display: flex; gap: var(--spacer-10); }
.auto-radio {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 16px; border: 1px solid var(--border-neutral-l2);
  border-radius: var(--radius-8); font-size: 13px; color: var(--text-secondary);
  cursor: pointer; transition: all .12s;
}
.auto-radio:hover { border-color: var(--border-neutral-l3); }
.auto-radio.active {
  border-color: var(--text-default); background-color: var(--bg-overlay-l1);
  color: var(--text-default); font-weight: 500;
}
.auto-radio input { position: absolute; opacity: 0; pointer-events: none; }

.auto-form-foot {
  display: flex; justify-content: flex-end; gap: var(--spacer-8);
  padding-top: var(--spacer-8);
}

/* ============ 详情 ============ */
.auto-detail-loading { padding: 40px 0; text-align: center; color: var(--text-tertiary); }
.auto-detail-body { gap: var(--spacer-14); }
.auto-detail-value {
  padding: 10px 14px; border: 1px solid var(--border-neutral-l1);
  border-radius: var(--radius-8); font-size: 13px; color: var(--text-default);
  background-color: var(--bg-base-secondary);
}
.auto-detail-text {
  padding: 10px 14px; border: 1px solid var(--border-neutral-l1);
  border-radius: var(--radius-8); font-size: 13px; color: var(--text-default);
  background-color: var(--bg-base-secondary);
  white-space: pre-wrap; word-break: break-word; line-height: 1.55;
  min-height: 60px; max-height: 200px; overflow-y: auto;
}
.auto-detail-meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacer-12); }

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .auto-body { padding: var(--spacer-16); }
  .auto-grid { grid-template-columns: 1fr; }
  .auto-template-grid { grid-template-columns: 1fr; }
  .auto-detail-meta { grid-template-columns: 1fr; }
  .auto-head { padding: 0 var(--spacer-16); height: 56px; }
}
</style>
