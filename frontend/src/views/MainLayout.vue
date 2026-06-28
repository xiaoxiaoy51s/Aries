<template>
  <div class="app-container" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-actions">
        <button type="button" class="sidebar-action" @click="createNewChat">
          <svg t="1782021300109" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="11940" width="16" height="16"><path d="M512 304.2816c24.1664 0 43.8784 19.6096 43.8784 43.776v120.0128h120.0128a43.9296 43.9296 0 0 1 0 87.8592l-120.1152-0.2048v120.0128a43.8784 43.8784 0 0 1-87.808 0v-119.8592H348.16a44.032 44.032 0 0 1-45.7728-43.9296 43.9296 43.9296 0 0 1 45.7728-43.8784h120.1152V348.0064c0-24.064 19.5072-43.6736 43.7248-43.7248z" p-id="11941"></path><path d="M512 51.2a460.8512 460.8512 0 0 1 176.3328 886.4768A460.9536 460.9536 0 0 1 511.9488 972.8H137.5744a46.08 46.08 0 0 1-38.1952-71.7824l40.8576-60.8768a50.944 50.944 0 0 0-2.1504-59.6992l-6.8608-8.9088A460.7488 460.7488 0 0 1 512 51.2z m0 78.9504a381.9008 381.9008 0 0 0-317.6448 593.92l5.9392 7.68a130.048 130.048 0 0 1 5.5296 152.4224l-6.6048 9.6768H512a381.952 381.952 0 0 0 381.5936-367.2064l0.3072-14.6432a381.8496 381.8496 0 0 0-381.9008-381.8496z" p-id="11942"></path></svg>
          <span>新对话</span>
        </button>
        <button type="button" class="sidebar-action" @click="showSearch = true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
          </svg>
          <span>搜索</span>
        </button>
        <button
          type="button"
          class="sidebar-action"
          :class="{ active: currentPage === 'skills' }"
          @click="currentPage = 'skills'"
        >
          <svg t="1782021373626" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="15025" width="16" height="16"><path d="M702.836 1021.673H104.727c-53.527 0-95.418-44.218-95.418-95.418V779.636c0-11.636 4.655-20.945 13.964-27.927 9.309-6.982 20.945-9.309 30.254-6.982 11.637 2.328 23.273 4.655 32.582 4.655 67.491 0 123.346-55.855 123.346-123.346S153.6 502.691 86.109 502.691c-9.309 0-20.945 2.327-32.582 4.654-11.636 2.328-20.945 0-30.254-6.981S9.309 484.073 9.309 472.436V325.818c0-53.527 44.218-95.418 95.418-95.418h107.055c-2.327-11.636-2.327-23.273-2.327-34.91 0-107.054 86.109-193.163 193.163-193.163s193.164 86.11 193.164 193.164c0 11.636 0 23.273-2.327 34.909h107.054c53.527 0 95.418 44.218 95.418 95.418v107.055h20.946c107.054 0 193.163 86.109 193.163 193.163S923.927 819.2 816.873 819.2h-20.946v107.055c4.655 51.2-39.563 95.418-93.09 95.418zM79.127 819.2v104.727c0 13.964 11.637 25.6 25.6 25.6h598.11c13.963 0 25.6-11.636 25.6-25.6V772.655c0-11.637 4.654-23.273 13.963-27.928 9.31-6.982 20.945-6.982 32.582-4.654 13.963 4.654 27.927 9.309 41.89 9.309 67.492 0 123.346-55.855 123.346-123.346s-55.854-123.345-123.345-123.345c-13.964 0-27.928 2.327-41.891 9.309-11.637 4.655-23.273 2.327-32.582-4.655-9.31-6.981-13.964-16.29-13.964-27.927v-153.6c0-13.963-11.636-25.6-25.6-25.6H546.91c-11.636 0-23.273-6.982-30.254-16.29-6.982-9.31-6.982-23.273-2.328-32.583 9.31-18.618 11.637-34.909 11.637-53.527 0-67.49-55.855-123.345-123.346-123.345s-123.345 55.854-123.345 123.345c0 18.618 4.654 37.237 11.636 53.527 4.655 11.637 4.655 23.273-2.327 32.582-6.982 9.31-18.618 16.291-30.255 16.291h-153.6c-13.963 0-25.6 11.637-25.6 25.6v104.727c109.382-4.654 200.146 83.782 200.146 193.164 0 107.055-86.11 193.164-193.164 193.164-2.327 2.327-4.654 2.327-6.982 2.327z" fill="" p-id="15026"></path></svg>
          <span>技能</span>
        </button>
        <button
          type="button"
          class="sidebar-action"
          :class="{ active: currentPage === 'scheduled-tasks' }"
          @click="currentPage = 'scheduled-tasks'"
        >
          <svg t="1782021412102" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" 
          p-id="16139" width="16" height="16"><path d="M491.287273 915.316364c-224.581818 0-407.272727-182.690909-407.272728-407.272728 
          0-156.392727 87.272727-296.494545 227.607273-365.614545 11.403636-5.585455 25.367273-0.930909 31.185455 
          10.705454 5.585455 11.636364 0.930909 25.367273-10.705455 31.185455-124.276364 61.207273-201.541818 185.250909-201.541818 
          323.723636 0 198.981818 161.745455 360.727273 360.727273 360.727273s360.727273-161.745455 360.727272-360.727273-161.745455-360.727273-360.727272-360.727272c-12.8 0-23.272727-10.472727-23.272728-23.272728s10.472727-23.272727 23.272728-23.272727c224.581818 0 407.272727 182.690909 407.272727 407.272727s-182.690909 407.272727-407.272727 407.272728z" fill="#040000" p-id="16140"></path><path d="M491.287273 531.316364c-12.8 0-23.272727-10.472727-23.272728-23.272728l-0.232727-279.272727c0-12.8 10.472727-23.272727 23.272727-23.272727s23.272727 10.472727 23.272728 23.272727l0.232727 279.272727c0 12.8-10.472727 23.272727-23.272727 23.272728z" fill="#040000" p-id="16141"></path><path d="M688.407273 531.316364h-197.12c-12.8 0-23.272727-10.472727-23.272728-23.272728s10.472727-23.272727 23.272728-23.272727h197.12c12.8 0 23.272727 10.472727 23.272727 23.272727s-10.472727 23.272727-23.272727 23.272728z" fill="#040000" p-id="16142"></path></svg>
          <span>定时任务</span>
        </button>
      </div>

      <div class="sidebar-section projects-section">
        <div class="section-label">项目</div>
        <div v-if="projects.length === 0" class="project-empty">暂无项目</div>
        <div v-else class="projects-scroll">
          <div
            v-for="project in projects"
            :key="project.work_dir"
            class="project-item"
            :class="{ active: currentProject?.work_dir === project.work_dir }"
          >
            <button type="button" class="project-row" @click="selectProject(project)">
              <span class="project-expand">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: isExpanded(project.work_dir) }">
                  <path d="m9 18 6-6-6-6"/>
                </svg>
              </span>
              <span class="project-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
              </span>
              <span class="project-name" :title="project.name">{{ project.name }}</span>
              <span class="project-actions">
                <span class="project-btn" title="新建对话" @click.stop="createNewChatInProject(project)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14"/>
                  </svg>
                </span>
                <span class="project-btn" title="打开文件夹" @click.stop="openProjectDir(project)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                </span>
              </span>
            </button>
            <ul v-if="project.sessions?.length && isExpanded(project.work_dir)" class="session-list project-sessions">
              <li
                v-for="session in project.sessions"
                :key="session.session_id"
                class="session-item session-sub"
                :class="{
                  active: currentSessionId === session.session_id,
                  working: workingSessionIds.has(session.session_id),
                }"
                :title="session.title"
                @click="selectSession(session.session_id)"
                @contextmenu.prevent="onSessionContextMenu($event, session)"
              >
                <SessionLoadingDots v-if="workingSessionIds.has(session.session_id)" />
                <span class="session-title">{{ session.title || '空对话' }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div class="sidebar-footer">
        <button 
          type="button" 
          class="sidebar-action"
          @click="showSettings = true"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>设置</span>
        </button>
      </div>
    </aside>

    <!-- 主工作区 -->
    <main class="workspace">
      <div class="workspace-panel">
        <!-- 对话页面 -->
        <ChatPage
          v-if="currentPage === 'chat'"
          :session-id-to-load="sessionIdToLoad"
          @session-loaded="sessionIdToLoad = null"
        />

        <!-- 技能页面 -->
        <SkillsPage v-else-if="currentPage === 'skills'" />

        <!-- 定时任务页面 -->
        <AutomationPage v-else-if="currentPage === 'scheduled-tasks'" />


      </div>
    </main>

    <!-- 设置弹窗 -->
    <SettingsPanel :visible="showSettings" @close="showSettings = false" />

    <!-- 搜索弹窗 -->
    <SearchDialog :visible="showSearch" @close="showSearch = false" @select="onSearchSelect" />

    <!-- 会话右键菜单 -->
    <Teleport to="body">
      <div
        v-if="sessionContextMenu.open"
        class="session-ctx-menu"
        :style="{ top: sessionContextMenu.y + 'px', left: sessionContextMenu.x + 'px' }"
      >
        <button class="session-ctx-item" @click="ctxRename">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
          </svg>
          <span>重命名</span>
        </button>
        <div class="session-ctx-divider"></div>
        <button class="session-ctx-item session-ctx-danger" @click="ctxDelete">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          <span>删除</span>
        </button>
      </div>
    </Teleport>

    <!-- 重命名弹窗 -->
    <div v-if="showRenameModal" class="modal-overlay" @click="cancelRename">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">重命名会话</div>
        <div class="modal-body">
          <input
            v-model="renameInput"
            type="text"
            class="modal-input"
            placeholder="请输入新标题"
            @keydown.enter="confirmRename"
            @keydown.esc="cancelRename"
            ref="renameInputRef"
          />
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="cancelRename">取消</button>
          <button class="modal-btn modal-btn-confirm" @click="confirmRename">确定</button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click="cancelDelete">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">确认删除</div>
        <div class="modal-body">
          <p>确定删除对话「{{ sessionToDelete?.title || '空对话' }}」?</p>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="cancelDelete">取消</button>
          <button class="modal-btn modal-btn-danger" @click="confirmDelete">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import ChatPage from './chatPage.vue'
import SkillsPage from './SkillsPage.vue'
import AutomationPage from './AutomationPage.vue'
import SettingsPanel from '@/components/settings/SettingsPanel.vue'
import SearchDialog from '@/components/SearchDialog.vue'
import SessionLoadingDots from '@/components/SessionLoadingDots.vue'
import { listProjects, updateSessionMeta, deleteSession } from '@/api/sessions'
import { workingSessionIds } from '@/utils/sessionWorkStore'
import { useModelStore } from '@/stores/model'
import { useSidebar } from '@/composables/useSidebar'

const modelStore = useModelStore()
const { sidebarOpen } = useSidebar()

interface ProjectSession {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

interface Project {
  work_dir: string
  name: string
  archived?: boolean
  created_at?: string
  updated_at?: string
  sessions: ProjectSession[]
}

const currentPage = ref<'chat' | 'skills' | 'scheduled-tasks'>('chat')
const showSettings = ref(false)
const showSearch = ref(false)

const currentSessionId = ref<string | null>(null)
const sessionIdToLoad = ref<string | null>(null)
const projects = ref<Project[]>([])
const currentProject = ref<Project | null>(null)
const expandedProjects = ref<Set<string>>(new Set())

// 重命名弹窗状态
const showRenameModal = ref(false)
const renameInput = ref('')
const sessionToRename = ref<ProjectSession | null>(null)
const renameInputRef = ref<HTMLInputElement | null>(null)

// 删除弹窗状态
const showDeleteModal = ref(false)
const sessionToDelete = ref<ProjectSession | null>(null)

// 会话右键菜单状态
const sessionContextMenu = ref<{
  open: boolean
  x: number
  y: number
  session: ProjectSession | null
}>({ open: false, x: 0, y: 0, session: null })

function onSessionContextMenu(e: MouseEvent, session: ProjectSession) {
  // 简单边界处理：菜单宽 ~140，高 ~80，避免溢出窗口
  const menuWidth = 150
  const menuHeight = 84
  const x = Math.min(e.clientX, window.innerWidth - menuWidth - 4)
  const y = Math.min(e.clientY, window.innerHeight - menuHeight - 4)
  sessionContextMenu.value = { open: true, x, y, session }
}

function closeSessionContextMenu() {
  if (sessionContextMenu.value.open) {
    sessionContextMenu.value = { open: false, x: 0, y: 0, session: null }
  }
}

function ctxRename() {
  const s = sessionContextMenu.value.session
  closeSessionContextMenu()
  if (s) renameSession(s)
}

function ctxDelete() {
  const s = sessionContextMenu.value.session
  closeSessionContextMenu()
  if (s) deleteSessionItem(s)
}

function isPlatformId(id: string) {
  return id === '__feishu__' || id === '__qq__' || id === '__wechat__'
}

async function loadProjects(retries = 5, delay = 1500) {
  for (let i = 0; i < retries; i++) {
    try {
      const data = await listProjects()
      projects.value = (data.projects || []) as Project[]
      return
    } catch (e) {
      if (i < retries - 1) {
        console.warn(`加载项目失败，${delay}ms 后重试 (${i + 1}/${retries})`, e)
        await new Promise(r => setTimeout(r, delay))
      } else {
        console.error('加载项目失败（已重试耗尽）', e)
        projects.value = []
      }
    }
  }
}

function onRefreshProjects() {
  void loadProjects()
}

function onGlobalCloseCtxMenu(e: MouseEvent | KeyboardEvent) {
  // 任何点击 / Esc 都关闭菜单（菜单按钮自身的点击会先调到 ctxRename/ctxDelete 然后再触发这里）
  if (e instanceof KeyboardEvent && e.key !== 'Escape') return
  closeSessionContextMenu()
}

onMounted(async () => {
  await Promise.all([loadProjects(), modelStore.loadModels()])
  window.addEventListener('aries:refresh-sessions', onRefreshProjects)
  window.addEventListener('aries:workdir-changed', onRefreshProjects)
  window.addEventListener('aries:open-session', onOpenSession)
  window.addEventListener('aries:open-settings', onOpenSettings)
  window.addEventListener('click', onGlobalCloseCtxMenu)
  window.addEventListener('keydown', onGlobalCloseCtxMenu)
  window.addEventListener('contextmenu', (e) => {
    // 在非会话项上右键也要关掉旧菜单（会话项 onSessionContextMenu 会重新打开）
    const target = e.target as HTMLElement | null
    if (!target?.closest('.session-sub')) closeSessionContextMenu()
  })
})

onUnmounted(() => {
  window.removeEventListener('aries:refresh-sessions', onRefreshProjects)
  window.removeEventListener('aries:workdir-changed', onRefreshProjects)
  window.removeEventListener('aries:open-session', onOpenSession)
  window.removeEventListener('aries:open-settings', onOpenSettings)
  window.removeEventListener('click', onGlobalCloseCtxMenu)
  window.removeEventListener('keydown', onGlobalCloseCtxMenu)
})

function createNewChat() {
  currentPage.value = 'chat'
  currentSessionId.value = null
  currentProject.value = null
  window.dispatchEvent(new CustomEvent('aries:new-chat'))
}

function selectProject(project: Project) {
  currentProject.value = project
  currentPage.value = 'chat'
  // 切换展开/收起
  if (expandedProjects.value.has(project.work_dir)) {
    expandedProjects.value.delete(project.work_dir)
  } else {
    expandedProjects.value.add(project.work_dir)
  }
}

function isExpanded(workDir: string): boolean {
  return expandedProjects.value.has(workDir)
}

function createNewChatInProject(project: Project) {
  currentPage.value = 'chat'
  currentProject.value = project
  currentSessionId.value = null
  window.dispatchEvent(new CustomEvent('aries:new-chat', {
    detail: { workDir: project.work_dir }
  }))
}

async function openProjectDir(project: Project) {
  if (!project.work_dir) return
  try {
    const baseUrl = modelStore.getBaseUrl()
    const res = await fetch(`${baseUrl}/system/open-path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: project.work_dir }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (data.error) throw new Error(data.error)
  } catch (e) {
    console.error('打开文件夹失败', e)
    alert('无法打开文件夹：' + (e as Error).message)
  }
}

async function selectSession(id: string) {
  currentSessionId.value = id
  sessionIdToLoad.value = id
  currentPage.value = 'chat'
  if (isPlatformId(id)) {
    currentProject.value = null
  } else {
    const proj = projects.value.find(p => p.sessions.some(s => s.session_id === id))
    currentProject.value = proj || null
  }
  // 通知 Todo 等组件；ChatPage 通过 sessionIdToLoad prop 加载，避免重复请求
  window.dispatchEvent(new CustomEvent('aries:load-session', { detail: id }))
}

function onOpenSession(e: Event) {
  const id = (e as CustomEvent<string>).detail
  if (id) {
    showSettings.value = false
    void selectSession(id)
  }
}

function onOpenSettings() {
  showSettings.value = true
}

function onSearchSelect(sessionId: string) {
  selectSession(sessionId)
}

function renameSession(session: ProjectSession) {
  sessionToRename.value = session
  renameInput.value = session.title || ''
  showRenameModal.value = true
  nextTick(() => {
    renameInputRef.value?.focus()
    renameInputRef.value?.select()
  })
}

async function confirmRename() {
  if (!sessionToRename.value) return
  const trimmed = renameInput.value.trim()
  if (!trimmed || trimmed === sessionToRename.value.title) {
    cancelRename()
    return
  }
  try {
    await updateSessionMeta(sessionToRename.value.session_id, { title: trimmed })
    sessionToRename.value.title = trimmed
    showRenameModal.value = false
    sessionToRename.value = null
  } catch (e) {
    console.error('重命名失败', e)
    alert('重命名失败：' + (e as Error).message)
  }
}

function cancelRename() {
  showRenameModal.value = false
  sessionToRename.value = null
}

function deleteSessionItem(session: ProjectSession) {
  sessionToDelete.value = session
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (!sessionToDelete.value) return
  try {
    await deleteSession(sessionToDelete.value.session_id)
    // 如果删除的是当前会话，清空选中状态
    if (currentSessionId.value === sessionToDelete.value.session_id) {
      currentSessionId.value = null
    }
    showDeleteModal.value = false
    sessionToDelete.value = null
    await loadProjects()
  } catch (e) {
    console.error('删除失败', e)
    alert('删除失败：' + (e as Error).message)
  }
}

function cancelDelete() {
  showDeleteModal.value = false
  sessionToDelete.value = null
}
</script>

<style scoped>
.app-container {
  display: block;
  height: 100vh;
  width: 100%;
  padding-top: 40px;
  box-sizing: border-box;
  position: relative;
}

.app-container.sidebar-collapsed .sidebar {
  transform: translateX(calc(-1 * var(--sidebar-width)));
  opacity: 0;
  pointer-events: none;
  border-right-color: transparent;
}

.app-container.sidebar-collapsed .workspace {
  padding-left: 12px;
}

/* —— 侧边栏（浮层叠在内容区上方，才能透出模糊） —— */
.sidebar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 50;
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  background: var(--glass-surface);
  border-right: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  display: flex;
  flex-direction: column;
  /* 40px 标题栏 + 12px 内边距，避免顶部按钮被标题栏遮住 */
  padding: 52px 10px 12px;
  gap: 4px;
  box-sizing: border-box;
  transition: transform 0.25s ease, opacity 0.2s ease, border-color 0.2s ease;
  flex-shrink: 0;
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
}

.sidebar::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    155deg,
    rgba(255, 255, 255, 0.55) 0%,
    rgba(255, 255, 255, 0.12) 42%,
    transparent 72%
  );
  pointer-events: none;
  z-index: 0;
}

.sidebar > * {
  position: relative;
  z-index: 1;
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}

.sidebar-action {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px 8px 16px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

.sidebar-action:hover {
  background: var(--accent-hover);
}

.sidebar-action.active {
  background: var(--accent-active);
  font-weight: 500;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.sidebar-action svg {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.sidebar-section {
  margin-top: 8px;
}

.projects-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.projects-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-right: 2px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 4px 10px 6px;
}

.project-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 12px;
}

.project-item {
  margin: 2px 0 4px;
}

.project-item.active .project-row {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.project-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.project-row:hover {
  background: var(--accent-hover);
}

.project-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.project-expand {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: transform 0.15s ease;
}

.project-expand svg.rotated {
  transform: rotate(90deg);
}

.project-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-actions {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.project-row:hover .project-actions,
.project-item.active .project-actions {
  display: inline-flex;
}

.project-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.project-btn:hover {
  background: var(--bg-panel);
  color: var(--text);
}

.project-sessions {
  list-style: none;
  margin: 2px 0 4px;
  padding: 0 0 0 24px;
  max-height: 280px;
  overflow-y: auto;
  scrollbar-width: none;
}

.project-sessions::-webkit-scrollbar {
  display: none;
}

.session-sub {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 4px;
  padding: 5px 8px 5px 12px;
  font-size: 12px;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  margin-left: 28px;
}

.session-sub.working .session-title {
  color: var(--text);
}

.session-sub:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.session-sub.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.session-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 会话右键菜单 */
.session-ctx-menu {
  position: fixed;
  z-index: 10000;
  min-width: 140px;
  padding: 4px;
  background: var(--bg-panel, #fff);
  border: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  gap: 1px;
  user-select: none;
}

.session-ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: var(--text, #222);
  font-size: 13px;
  text-align: left;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.session-ctx-item:hover {
  background: var(--accent-hover, rgba(0, 0, 0, 0.05));
}

.session-ctx-item svg {
  flex-shrink: 0;
  opacity: 0.75;
}

.session-ctx-divider {
  height: 1px;
  background: var(--border, rgba(0, 0, 0, 0.08));
  margin: 2px 4px;
}

.session-ctx-danger {
  color: #dc2626;
}

.session-ctx-danger:hover {
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
}

.session-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0 4px;
  max-height: 280px;
  overflow-y: auto;
}

.session-item {
  display: block;
  width: 100%;
  padding: 7px 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.15s, color 0.15s;
}

.session-item:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.session-item.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.session-item .time {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  font-weight: 400;
}

/* 平台对话项 */
.platform-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.platform-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.platform-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.platform-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* —— 主工作区 —— */
.workspace {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 10px 12px 12px calc(var(--sidebar-width) + 10px);
  box-sizing: border-box;
  transition: padding 0.25s ease;
  position: relative;
}

.workspace-panel {
  flex: 1;
  background: var(--bg-content);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-panel);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  min-width: 0;
}

/* —— 模态框 —— */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
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

.modal-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 14px;
  background: var(--bg-sidebar);
  color: var(--text);
  outline: none;
  transition: border-color 0.2s;
}

.modal-input:focus {
  border-color: var(--accent);
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

.modal-btn-confirm {
  background: #1f2937;
  color: #ffffff;
}

.modal-btn-danger {
  background: #1f2937;
  color: #ffffff;
}
</style>
