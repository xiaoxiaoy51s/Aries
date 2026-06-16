<template>
  <div class="app-container" :class="{ 'sidebar-collapsed': !sidebarOpen }">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-actions">
        <button type="button" class="sidebar-action" @click="createNewChat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
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
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7"/>
            <rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/>
          </svg>
          <span>技能</span>
        </button>
        <button
          type="button"
          class="sidebar-action"
          :class="{ active: currentPage === 'scheduled-tasks' }"
          @click="currentPage = 'scheduled-tasks'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/>
            <path d="M12 7v5l3 2"/>
          </svg>
          <span>定时任务</span>
        </button>
      </div>

      <div class="sidebar-section">
        <div class="section-label">项目</div>
        <div v-if="projects.length === 0" class="project-empty">暂无项目</div>
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
              :class="{ active: currentSessionId === session.session_id }"
              :title="session.title"
              @click="selectSession(session.session_id)"
            >
              <span class="session-title">{{ session.title || '空对话' }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="sidebar-section">
        <div class="section-label">对话</div>
        <ul class="session-list">
          <li
            v-for="p in platformSessions"
            :key="p.id"
            class="session-item platform-item"
            :class="{ active: currentSessionId === p.id }"
            @click="selectSession(p.id)"
          >
            <span class="platform-icon" :class="`platform-${p.platform}`">
              <img v-if="p.platform === 'feishu'" src="@/assets/feishu.svg" alt="飞书" />
              <img v-else-if="p.platform === 'qq'" src="@/assets/qq.svg" alt="QQ" />
              <img v-else src="@/assets/weixin.svg" alt="微信" />
            </span>
            <span class="platform-name">{{ p.name }}</span>
          </li>
        </ul>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import ChatPage from './chatPage.vue'
import SkillsPage from './SkillsPage.vue'
import AutomationPage from './AutomationPage.vue'
import SettingsPanel from '@/components/settings/SettingsPanel.vue'
import SearchDialog from '@/components/SearchDialog.vue'
import { listProjects } from '@/api/sessions'
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

// 三个平台固定的固定 session id（与后端 platform_chat.session_id_for 对应）
const platformSessions = [
  { id: '__feishu__', name: '飞书', platform: 'feishu' },
  { id: '__qq__', name: 'QQ', platform: 'qq' },
  { id: '__wechat__', name: '微信', platform: 'wechat' },
]

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

onMounted(async () => {
  await Promise.all([loadProjects(), modelStore.loadModels()])
  window.addEventListener('mimo:refresh-sessions', onRefreshProjects)
  window.addEventListener('mimo:workdir-changed', onRefreshProjects)
  window.addEventListener('mimo:open-session', onOpenSession)
})

onUnmounted(() => {
  window.removeEventListener('mimo:refresh-sessions', onRefreshProjects)
  window.removeEventListener('mimo:workdir-changed', onRefreshProjects)
  window.removeEventListener('mimo:open-session', onOpenSession)
})

function createNewChat() {
  currentPage.value = 'chat'
  currentSessionId.value = null
  currentProject.value = null
  window.dispatchEvent(new CustomEvent('mimo:new-chat'))
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
  window.dispatchEvent(new CustomEvent('mimo:new-chat', {
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
  await nextTick()
  window.dispatchEvent(new CustomEvent('mimo:load-session', { detail: id }))
}

function onOpenSession(e: Event) {
  const id = (e as CustomEvent<string>).detail
  if (id) void selectSession(id)
}

function onSearchSelect(sessionId: string) {
  selectSession(sessionId)
}
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  width: 100%;
}

.app-container.sidebar-collapsed .sidebar {
  width: 0;
  min-width: 0;
  padding-left: 0;
  padding-right: 0;
  border-right-color: transparent;
  overflow: hidden;
  pointer-events: none;
}

.app-container.sidebar-collapsed .workspace {
  padding-left: 12px;
}

/* —— 侧边栏 —— */
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 44px 10px 12px;
  gap: 4px;
  transition: width 0.2s ease, min-width 0.2s ease, padding 0.2s ease, border-color 0.2s ease;
  flex-shrink: 0;
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
}

.sidebar-action svg {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.sidebar-section {
  margin-top: 8px;
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
  gap: 6px;
  padding: 5px 8px 5px 12px;
  font-size: 12px;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  margin-left: 28px;
}

.session-sub:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.session-sub.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
}

.session-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* —— 主工作区 —— */
.workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 10px 12px 12px 0;
  transition: padding 0.2s ease;
}

.workspace-panel {
  flex: 1;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-panel);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}
</style>
