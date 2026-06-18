<template>
  <div class="automation-page">
    <div class="page-header">
      <h2 class="page-title">自动任务</h2>
      <button type="button" class="btn-primary" @click="openCreateDialog">+ 新建自动任务</button>
    </div>

    <!-- 空状态 -->
    <div v-if="tasks.length === 0 && !loading" class="empty-state">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12,6 12,12 16,14"/>
      </svg>
      <p>暂无自动任务，点击上方按钮创建</p>
    </div>

    <!-- 任务卡片列表 -->
    <div v-else class="task-grid">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-card"
      >
        <div class="card-header">
          <span class="card-icon" :class="'status-' + task.status">
            <svg v-if="task.status === 'running'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
            <svg v-else-if="task.status === 'completed'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22,4 12,14.01 9,11.01"/>
            </svg>
            <svg v-else-if="task.status === 'cancelled'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
          </span>
          <h3 class="card-title">{{ task.title || '未命名' }}</h3>
          <!-- 推送标签 -->
          <span v-if="taskPushPlatform(task)" class="notify-badge">
            {{ notifyTypeLabel(taskPushPlatform(task)!) }}
          </span>
        </div>
        <p class="card-content">{{ task.task_content || '无执行内容' }}</p>
        <div class="card-meta">
          <span class="schedule-label">{{ formatScheduleLabel(task) }}</span>
          <button
            v-if="canOpenTaskSession(task)"
            type="button"
            class="session-link"
            @click="openTaskSession(task)"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            {{ sessionLinkLabel(task) }}
          </button>
        </div>
        <div class="card-footer">
          <span class="status-label" :class="'st-' + task.status">{{ statusLabel(task.status) }}</span>
          <div class="card-actions">
            <button
              v-if="task.status === 'pending'"
              type="button"
              class="btn-text btn-danger"
              @click="handleCancel(task.id)"
            >取消</button>
            <button
              type="button"
              class="btn-text"
              @click="openTaskDetail(task)"
            >详情</button>
            <button
              type="button"
              class="btn-text"
              @click="handleDelete(task.id)"
            >删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建任务弹窗 -->
    <div v-if="showDialog" class="modal-overlay" @click.self="closeDialog">
      <div class="modal-content">
        <div class="modal-header">
          <h3>新建自动任务</h3>
          <button type="button" class="btn-close" @click="closeDialog">&times;</button>
        </div>
        <div class="modal-body">
          <!-- 名称 -->
          <div class="form-group">
            <label>名称 <span class="required">*</span></label>
            <input
              v-model="form.title"
              type="text"
              placeholder="请输入任务名称"
              maxlength="50"
            />
            <span class="char-count">{{ form.title.length }}/50</span>
          </div>
          <!-- 要求说明 -->
          <div class="form-group">
            <label>要求说明 <span class="required">*</span></label>
            <textarea
              v-model="form.task_content"
              placeholder="请输入任务要求说明"
              maxlength="8000"
              rows="5"
            ></textarea>
            <span class="char-count">{{ form.task_content.length }}/8000</span>
          </div>
          <!-- 执行时间 -->
          <div class="form-group">
            <label>执行时间 <span class="required">*</span></label>
            <div class="schedule-row">
              <select v-model="form.schedule_type">
                <option value="once">单次</option>
                <option value="daily">每天</option>
                <option value="interval">每间隔</option>
              </select>

              <!-- 单次：日期选择 + 时间选择 -->
              <template v-if="form.schedule_type === 'once'">
                <input v-model="form.onceDate" type="date" />
                <input v-model="form.onceTime" type="time" />
              </template>

              <!-- 每天：时间选择 -->
              <template v-if="form.schedule_type === 'daily'">
                <select v-model="form.dailyHour">
                  <option v-for="h in hourOptions" :key="h" :value="h">{{ h }}时</option>
                </select>
                <select v-model="form.dailyMinute">
                  <option v-for="m in minuteOptions" :key="m" :value="m">{{ m }}分</option>
                </select>
              </template>

              <!-- 每间隔 -->
              <template v-if="form.schedule_type === 'interval'">
                <select v-model.number="form.intervalHours">
                  <option :value="1">每1小时</option>
                  <option :value="2">每2小时</option>
                  <option :value="6">每6小时</option>
                  <option :value="12">每12小时</option>
                  <option :value="24">每天</option>
                </select>
              </template>
            </div>
          </div>

          <!-- 结果推送（网页会话 与 手机推送 互斥） -->
          <div class="form-group">
            <label>结果推送 <span class="required">*</span></label>
            <select v-model="form.delivery_target" class="delivery-select">
              <option value="web_new">推送到新会话（网页聊天）</option>
              <option value="web_bind">推送到已有会话（网页聊天）</option>
              <option value="external">推送到手机（微信 / QQ / 飞书）</option>
            </select>

            <template v-if="form.delivery_target === 'web_bind'">
              <select v-model="form.session_id" class="session-select session-select--bind">
                <option value="">-- 请选择会话 --</option>
                <option v-for="s in sessions" :key="s.session_id" :value="s.session_id">
                  {{ formatSessionOption(s) }}
                </option>
              </select>
              <p v-if="sessions.length === 0" class="form-hint form-hint--warn">暂无可用会话，请先在「对话」页创建聊天</p>
              <p v-else class="form-hint">AI 将基于所选会话的历史上下文继续对话，结果写入该会话</p>
            </template>

            <template v-else-if="form.delivery_target === 'external'">
              <select v-model="form.notify_type" class="session-select session-select--bind">
                <option value="wechat">微信</option>
                <option value="qq">QQ</option>
                <option value="feishu">飞书</option>
              </select>
              <p class="form-hint">AI 回复会像平时聊天一样发到手机。需先在设置绑定对应平台，并用手机发过至少一条消息</p>
            </template>

            <p v-else class="form-hint">任务执行后自动创建新会话，可在「对话」页查看</p>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeDialog">取消</button>
          <button type="button" class="btn-primary" @click="handleSubmit" :disabled="!isFormValid">确定</button>
        </div>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <div v-if="showDetailDialog" class="modal-overlay" @click.self="closeDetailDialog">
      <div class="modal-content">
        <div class="modal-header">
          <h3>任务详情</h3>
          <button type="button" class="btn-close" @click="closeDetailDialog">&times;</button>
        </div>
        <div v-if="detailLoading" class="modal-body detail-loading">加载中...</div>
        <div v-else-if="detailTask" class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <div class="detail-value">{{ detailTask.title || '未命名' }}</div>
          </div>
          <div class="form-group">
            <label>要求说明</label>
            <div class="detail-text">{{ detailTask.task_content || '（无）' }}</div>
          </div>
          <div class="form-group">
            <label>执行时间</label>
            <div class="detail-value">{{ formatScheduleDetail(detailTask) }}</div>
            <p v-if="detailTask.scheduled_at" class="form-hint">下次/计划执行：{{ formatDateTimeDisplay(detailTask.scheduled_at) }}</p>
          </div>
          <div class="form-group">
            <label>结果推送</label>
            <div class="detail-value">{{ formatDeliveryTarget(detailTask) }}</div>
            <p v-if="detailTask.session_id" class="form-hint">会话 ID：{{ detailTask.session_id }}</p>
          </div>
          <div class="form-group">
            <label>任务状态</label>
            <div class="detail-value">
              <span class="status-label" :class="'st-' + detailTask.status">{{ statusLabel(detailTask.status) }}</span>
            </div>
          </div>
          <div class="form-group detail-meta-grid">
            <div>
              <label>创建时间</label>
              <div class="detail-value">{{ formatDateTimeDisplay(detailTask.created_at) || '—' }}</div>
            </div>
            <div>
              <label>更新时间</label>
              <div class="detail-value">{{ formatDateTimeDisplay(detailTask.updated_at) || '—' }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button
            v-if="detailTask && canOpenTaskSession(detailTask)"
            type="button"
            class="btn-secondary"
            @click="openTaskSession(detailTask!)"
          >{{ sessionLinkLabel(detailTask!) }}</button>
          <button type="button" class="btn-primary" @click="closeDetailDialog">关闭</button>
        </div>
      </div>
    </div>

    <!-- 底部模板区域 -->
    <div class="templates-section">
      <div class="section-title">快捷模板</div>
      <p class="section-desc">从模板快速创建常用自动化任务</p>
      <div class="template-grid">
        <div
          v-for="tmpl in templates"
          :key="tmpl.id"
          class="template-card"
          @click="applyTemplate(tmpl)"
        >
          <div class="template-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
          </div>
          <div class="template-info">
            <h4 class="template-name">{{ tmpl.name }}</h4>
            <p class="template-desc">{{ tmpl.desc }}</p>
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="template-arrow">
            <polyline points="9,18 15,12 9,6"/>
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  listScheduledTasks,
  createScheduledTask,
  cancelScheduledTask,
  deleteScheduledTask,
  getScheduledTask,
  listSessions,
  type ScheduledTask,
  type SessionItem,
} from '@/api/automation'

// 预生成时/分选项
const hourOptions = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const minuteOptions = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

const tasks = ref<ScheduledTask[]>([])
const sessions = ref<SessionItem[]>([])
const loading = ref(false)
const showDialog = ref(false)
const showDetailDialog = ref(false)
const detailLoading = ref(false)
const detailTask = ref<ScheduledTask | null>(null)

const form = ref({
  title: '',
  task_content: '',
  schedule_type: 'once' as 'once' | 'daily' | 'interval',
  onceDate: '',
  onceTime: '',
  dailyHour: '09',
  dailyMinute: '00',
  intervalHours: 1,
  delivery_target: 'web_new' as 'web_new' | 'web_bind' | 'external',
  session_id: '',
  notify_type: 'wechat' as 'wechat' | 'qq' | 'feishu',
})

function platformFromSessionId(sessionId: string | undefined): string | null {
  if (!sessionId) return null
  const m = sessionId.match(/^__(wechat|qq|feishu)__$/)
  return m ? m[1] : null
}

function taskPushPlatform(task: ScheduledTask): string | null {
  const fromSession = platformFromSessionId(task.session_id)
  if (fromSession) return fromSession
  if (task.notify_type && task.notify_type !== 'none') return task.notify_type
  return null
}

const isFormValid = computed(() => {
  const f = form.value
  if (!f.title.trim() || !f.task_content.trim()) return false
  if (f.schedule_type === 'once' && (!f.onceDate || !f.onceTime)) return false
  if (f.delivery_target === 'web_bind' && !f.session_id) return false
  if (f.delivery_target === 'external' && !f.notify_type) return false
  return true
})

function notifyTypeLabel(type: string): string {
  const map: Record<string, string> = { wechat: '微信', qq: 'QQ', feishu: '飞书', webhook: 'Hook' }
  return map[type] || type
}

function statusLabel(status: string): string {
  const map: Record<string, string> = { pending: '待执行', running: '执行中', completed: '已完成', cancelled: '已取消', failed: '失败' }
  return map[status] || status
}

function formatIntervalLabel(minutes: number): string {
  if (minutes >= 1440 && minutes % 1440 === 0) {
    const days = minutes / 1440
    return days === 1 ? '每天' : `每${days}天`
  }
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60
    return `每${hours}小时`
  }
  return `每${minutes}分钟`
}

function formatScheduleLabel(task: ScheduledTask): string {
  const st = task.schedule_type || 'once'

  if (st === 'once') {
    if (task.scheduled_at) {
      const d = new Date(task.scheduled_at)
      if (!isNaN(d.getTime())) {
        return '单次 ' + d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      }
    }
    return '单次'
  }
  if (st === 'daily') {
    if (task.scheduled_at) {
      const d = new Date(task.scheduled_at)
      if (!isNaN(d.getTime())) {
        const hh = String(d.getHours()).padStart(2, '0')
        const mm = String(d.getMinutes()).padStart(2, '0')
        return `每天 ${hh}:${mm}`
      }
    }
    return '每天'
  }
  if (st === 'interval') {
    const mins = Number(task.interval_minutes) || 60
    return formatIntervalLabel(mins)
  }
  return '未知'
}

function formatSessionOption(s: SessionItem): string {
  const title = (s.title || s.last_user_message || '').trim()
  if (title) return title.length > 40 ? title.slice(0, 40) + '…' : title
  return s.session_id.substring(0, 16) + '…'
}

function canOpenTaskSession(task: ScheduledTask): boolean {
  if (taskPushPlatform(task)) return true
  return !!task.session_id
}

function sessionLinkLabel(task: ScheduledTask): string {
  const platform = taskPushPlatform(task)
  if (platform) return `查看${notifyTypeLabel(platform)}`
  return '查看会话'
}

function formatScheduleDetail(task: ScheduledTask): string {
  const st = task.schedule_type || 'once'
  if (st === 'once') return '单次执行'
  if (st === 'daily') {
    if (task.scheduled_at) {
      const d = new Date(task.scheduled_at)
      if (!isNaN(d.getTime())) {
        const hh = String(d.getHours()).padStart(2, '0')
        const mm = String(d.getMinutes()).padStart(2, '0')
        return `每天 ${hh}:${mm}`
      }
    }
    return '每天'
  }
  if (st === 'interval') {
    const mins = Number(task.interval_minutes) || 60
    return `每间隔 · ${formatIntervalLabel(mins)}`
  }
  return formatScheduleLabel(task)
}

function formatDeliveryTarget(task: ScheduledTask): string {
  const platform = taskPushPlatform(task)
  if (platform) return `推送到手机 · ${notifyTypeLabel(platform)}`
  if (task.session_id) return '推送到已有会话（网页聊天）'
  return '推送到新会话（网页聊天）'
}

function formatDateTimeDisplay(value: string): string {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

async function openTaskDetail(task: ScheduledTask) {
  showDetailDialog.value = true
  detailLoading.value = true
  detailTask.value = task
  try {
    detailTask.value = await getScheduledTask(task.id)
  } catch (e) {
    console.error('加载任务详情失败', e)
    detailTask.value = task
  } finally {
    detailLoading.value = false
  }
}

function closeDetailDialog() {
  showDetailDialog.value = false
  detailTask.value = null
}

function openTaskSession(task: ScheduledTask) {
  const sessionId = task.session_id || (taskPushPlatform(task) ? `__${taskPushPlatform(task)}__` : '')
  if (!sessionId) return
  window.dispatchEvent(new CustomEvent('aries:open-session', { detail: sessionId }))
}

function openCreateDialog() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const hour = String(now.getHours()).padStart(2, '0')
  const minute = String(now.getMinutes()).padStart(2, '0')

  form.value = {
    title: '',
    task_content: '',
    schedule_type: 'once',
    onceDate: year + '-' + month + '-' + day,
    onceTime: hour + ':' + minute,
    dailyHour: '09',
    dailyMinute: '00',
    intervalHours: 1,
    delivery_target: 'web_new',
    session_id: '',
    notify_type: 'wechat',
  }
  if (form.value.delivery_target === 'web_bind') {
    loadSessions()
  }
  showDialog.value = true
}

// 模板数据
interface Template {
  id: string
  name: string
  desc: string
  title: string
  task_content: string
  schedule_type: 'once' | 'daily' | 'interval'
  intervalHours?: number
  scheduleConfig?: { time?: string }
}

const templates: Template[] = [
  {
    id: 'daily-summary',
    name: '每日摘要报告',
    desc: '每天定时汇总当日工作内容，生成日报',
    title: '每日工作摘要',
    task_content: '请汇总今天的工作进展，包括完成的任务、遇到的问题和明天的计划，生成一份简洁的工作日报。',
    schedule_type: 'daily',
    scheduleConfig: { time: '18:00' },
  },
  {
    id: 'weekly-review',
    name: '每周复盘总结',
    desc: '每天自动回顾本周完成情况，输出周报',
    title: '本周工作复盘',
    task_content: '回顾本周所有已完成的工作事项，分析进度达成情况，总结经验教训并列出下周重点工作计划。',
    schedule_type: 'daily',
    scheduleConfig: { time: '17:00' },
  },
  {
    id: 'code-check',
    name: '代码质量检查',
    desc: '定期检查项目代码质量，发现潜在问题',
    title: '代码质量扫描',
    task_content: '检查当前项目的代码质量，包括：1. 潜在的 bug 和逻辑问题 2. 代码风格一致性 3. 性能优化建议。输出具体的文件路径、问题描述和修复建议。',
    schedule_type: 'interval',
    intervalHours: 6,
  },
  {
    id: 'news-briefing',
    name: '行业资讯早报',
    desc: '每天早上获取最新行业动态和技术资讯',
    title: '今日科技资讯',
    task_content: '搜索今天最新的科技/人工智能/编程领域的重要新闻和动态，整理成简明的早报格式，每条新闻包含标题和一句话摘要。',
    schedule_type: 'daily',
    scheduleConfig: { time: '08:30' },
  },
]

function applyTemplate(tmpl: Template) {
  const now = new Date()

  if (tmpl.schedule_type === 'once') {
    form.value = {
      title: tmpl.title,
      task_content: tmpl.task_content,
      schedule_type: 'once',
      onceDate: formatDateForInput(now),
      onceTime: String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'),
      dailyHour: '09',
      dailyMinute: '00',
      intervalHours: 1,
      delivery_target: 'web_new',
      session_id: '',
      notify_type: 'wechat',
    }
  } else if (tmpl.schedule_type === 'daily') {
    const timeStr = (tmpl.scheduleConfig?.time as string) || '09:00'
    form.value = {
      title: tmpl.title,
      task_content: tmpl.task_content,
      schedule_type: 'daily',
      onceDate: '',
      onceTime: '',
      dailyHour: timeStr.split(':')[0],
      dailyMinute: timeStr.split(':')[1] || '00',
      intervalHours: 1,
      delivery_target: 'web_new',
      session_id: '',
      notify_type: 'wechat',
    }
  } else if (tmpl.schedule_type === 'interval') {
    const hours = Number(tmpl.intervalHours) || 1
    form.value = {
      title: tmpl.title,
      task_content: tmpl.task_content,
      schedule_type: 'interval',
      onceDate: '',
      onceTime: '',
      dailyHour: '09',
      dailyMinute: '00',
      intervalHours: hours,
      delivery_target: 'web_new',
      session_id: '',
      notify_type: 'wechat',
    }
  }

  if (form.value.delivery_target === 'web_bind') {
    loadSessions()
  }
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
}

function formatDateForInput(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return year + '-' + month + '-' + day
}

async function handleSubmit() {
  if (!isFormValid.value) return

  let scheduled_at: string | undefined
  let interval_minutes: number | undefined
  const f = form.value

  if (f.schedule_type === 'once') {
    scheduled_at = f.onceDate + 'T' + f.onceTime + ':00'
  } else if (f.schedule_type === 'daily') {
    const now = new Date()
    const timeStr = f.dailyHour.padStart(2, '0') + ':' + f.dailyMinute.padStart(2, '0') + ':00'
    const today = formatDateForInput(now)
    scheduled_at = today + 'T' + timeStr
    if (new Date(scheduled_at) <= now) {
      const tomorrow = new Date(now.getTime() + 86400000)
      scheduled_at = formatDateForInput(tomorrow) + 'T' + timeStr
    }
  } else if (f.schedule_type === 'interval') {
    interval_minutes = f.intervalHours * 60
  }

  let session_mode: 'new' | 'bind' | undefined
  let session_id: string | undefined

  if (f.delivery_target === 'external') {
    session_id = `__${f.notify_type}__`
  } else if (f.delivery_target === 'web_bind') {
    session_mode = 'bind'
    session_id = f.session_id
  } else {
    session_mode = 'new'
  }

  try {
    await createScheduledTask({
      title: f.title.trim(),
      task_content: f.task_content.trim(),
      schedule_type: f.schedule_type,
      scheduled_at,
      interval_minutes,
      session_mode,
      session_id,
    })
    closeDialog()
    await loadTasks()
  } catch (e) {
    console.error('创建任务失败', e)
  }
}

async function handleCancel(id: number) {
  if (!confirm('确定要取消该任务吗？')) return
  try {
    await cancelScheduledTask(id)
    await loadTasks()
  } catch (e) {
    console.error('取消任务失败', e)
  }
}

async function handleDelete(id: number) {
  if (!confirm('确定要删除该任务吗？删除后不可恢复。')) return
  try {
    await deleteScheduledTask(id)
    await loadTasks()
  } catch (e) {
    console.error('删除任务失败', e)
  }
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await listScheduledTasks()
    tasks.value = res.tasks || []
  } catch (e) {
    console.error('加载任务失败', e)
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function loadSessions() {
  try {
    const res = await listSessions()
    sessions.value = (res.sessions || []).filter(
      s => !(s.session_id.startsWith('__') && s.session_id.endsWith('__'))
    )
  } catch (e) {
    console.error('加载会话列表失败', e)
    sessions.value = []
  }
}

watch(() => form.value.delivery_target, (target) => {
  if (target === 'web_bind') {
    form.value.session_id = ''
    loadSessions()
  } else if (target === 'external') {
    form.value.session_id = ''
  }
})

onMounted(() => {
  loadTasks()
})
</script>

<style scoped>
.automation-page {
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
  margin-bottom: 24px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
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

.btn-primary:hover {
  opacity: 0.88;
}

.btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--text-muted);
  gap: 12px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.task-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  transition: box-shadow 0.2s;
}

.task-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.card-icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(74, 144, 217, 0.1);
  color: #4a90d9;
}

.card-icon.status-completed {
  background: rgba(52, 199, 89, 0.1);
  color: #34c759;
}

.card-icon.status-cancelled {
  background: rgba(255, 59, 48, 0.1);
  color: #ff3b30;
}

.card-icon.status-running {
  background: rgba(255, 149, 0, 0.1);
  color: #ff9500;
}

.card-icon.status-failed {
  background: rgba(255, 59, 48, 0.1);
  color: #ff3b30;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.notify-badge {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(74, 144, 217, 0.1);
  color: #4a90d9;
  font-weight: 500;
}

.card-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.55;
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.schedule-label {
  font-size: 12px;
  color: var(--text-muted);
}

.session-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--accent, #4a90d9);
  background: rgba(74, 144, 217, 0.08);
  padding: 2px 8px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
}

.session-link:hover {
  background: rgba(74, 144, 217, 0.16);
}

.delivery-select,
.session-select--bind {
  margin-top: 8px;
}

.form-hint--warn {
  color: #c50f1f;
}

.detail-loading {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 0;
}

.detail-value {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-panel);
}

.detail-text {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-panel);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
  min-height: 100px;
  max-height: 240px;
  overflow-y: auto;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.detail-meta-grid label {
  margin-bottom: 6px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.status-label {
  font-size: 12px;
  font-weight: 500;
}

.status-label.st-pending { color: #4a90d9; }
.status-label.st-running { color: #ff9500; }
.status-label.st-completed { color: #34c759; }
.status-label.st-cancelled { color: var(--text-muted); }
.status-label.st-failed { color: #ff3b30; }

.card-actions {
  display: flex;
  gap: 8px;
}

.btn-text {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.12s;
}

.btn-text:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.btn-text.btn-danger:hover {
  color: #ff3b30;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-panel, #fff);
  border-radius: 16px;
  width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}

.modal-header h3 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
}

.btn-close {
  background: none;
  border: none;
  font-size: 22px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
  padding: 4px;
}

.btn-close:hover {
  color: var(--text);
}

.modal-body {
  padding: 20px 24px;
  flex: 1;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 20px;
  position: relative;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 8px;
}

.required {
  color: #ff3b30;
}

.form-group input[type="text"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-panel);
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
  font-family: inherit;
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
  border-color: var(--accent, #4a90d9);
}

.form-group textarea {
  resize: vertical;
  min-height: 100px;
}

.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 6px 0 0;
}

.char-count {
  position: absolute;
  right: 0;
  bottom: -20px;
  font-size: 11px;
  color: var(--text-muted);
}

.schedule-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.schedule-row select,
.schedule-row input[type="date"],
.schedule-row input[type="time"] {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-panel);
  outline: none;
  min-width: 120px;
  cursor: pointer;
  font-family: inherit;
}

.schedule-row select:focus,
.schedule-row input:focus {
  border-color: var(--accent, #4a90d9);
}

.schedule-row select:first-child {
  min-width: 100px;
}

/* 会话选择 */
.session-row {
  display: flex;
  gap: 10px;
}

.session-mode-select {
  min-width: 130px !important;
  flex-shrink: 0;
}

.session-select {
  flex: 1;
  min-width: 0;
}

/* 推送配置子表单 */
.advanced-section {
  margin-bottom: 16px;
}

.advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 6px 0;
  transition: color 0.15s;
}

.advanced-toggle:hover {
  color: var(--text);
}

.advanced-toggle svg {
  transition: transform 0.2s;
}

.advanced-toggle svg.rotated {
  transform: rotate(180deg);
}

.notify-select {
  margin-top: 8px;
}

.sub-form {
  margin-top: 10px;
}

.sub-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
  display: block;
}

.sub-form input,
.sub-form select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text);
  background: var(--bg-panel);
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
}

.sub-form input:focus,
.sub-form select:focus {
  border-color: var(--accent, #4a90d9);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px 20px;
}

.btn-secondary {
  padding: 8px 24px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.12s;
}

.btn-secondary:hover {
  background: var(--accent-hover);
}

/* 模板区域 */
.templates-section {
  margin-top: auto;
  padding-top: 28px;
  border-top: 1px solid var(--border);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 6px;
}

.section-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 16px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.template-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.template-card:hover {
  border-color: var(--accent, #4a90d9);
  box-shadow: 0 2px 8px rgba(74, 144, 217, 0.1);
}

.template-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(74, 144, 217, 0.08);
  color: #4a90d9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.template-info {
  flex: 1;
  min-width: 0;
}

.template-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 2px;
}

.template-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.template-arrow {
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0.5;
  transition: transform 0.15s, opacity 0.15s;
}

.template-card:hover .template-arrow {
  opacity: 1;
  transform: translateX(2px);
}
</style>
