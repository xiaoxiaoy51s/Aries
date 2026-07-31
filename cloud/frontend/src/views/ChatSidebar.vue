<template>
  <aside class="chat-sidebar" :class="{ collapsed: !sidebarOpen }">
    <div class="sidebar-top">
      <div class="sidebar-brand">
        <img src="../assets/logo.png" alt="Aries Cloud" class="sidebar-brand-logo" />
        <span v-if="sidebarOpen" class="sidebar-brand-name">Aries Cloud</span>
      </div>
      <div class="sidebar-top-actions">
        <button
          type="button"
          class="sidebar-icon-btn sidebar-search-btn"
          :title="t('nav.searchOpen')"
          @click="$emit('open-search')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </button>
        <button
          type="button"
          class="sidebar-icon-btn sidebar-toggle"
          :title="sidebarOpen ? t('nav.collapse') : t('nav.expand')"
          @click="$emit('toggle-sidebar')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M9 3v18"/>
          </svg>
        </button>
      </div>
    </div>

    <div v-if="sidebarOpen" class="sidebar-body">
      <!-- 导航菜单 -->
      <nav class="sidebar-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="sidebar-nav-item"
          :class="{ active: activeNav === item.key }"
          @click="handleNavClick(item.key)"
        >
          <span class="sidebar-nav-icon" v-html="item.icon" />
          <span class="sidebar-nav-label">{{ item.label }}</span>
        </button>
      </nav>

      <!-- 文件浏览模式 -->
      <div v-if="fileView" class="sidebar-section sidebar-file-view">
        <div class="sidebar-file-header">
          <button
            type="button"
            class="sidebar-file-back"
            :title="t('workspace.backToTasks')"
            @click="exitFileView"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <span class="sidebar-file-title">{{ workspaceDisplayName(fileView.workspace) }}</span>
        </div>

        <div class="sidebar-file-list">
          <div v-if="fileView.loading" class="sidebar-empty">{{ t('workspace.loadingFiles') }}</div>
          <div v-else-if="!visibleTreeNodes.length" class="sidebar-empty">{{ t('workspace.emptyFiles') }}</div>
          <template v-else>
            <div
              v-for="node in visibleTreeNodes"
              :key="node.path"
              class="sidebar-tree-node-wrap sidebar-session-item-wrap"
              :class="{ 'has-active': openFileMenuId === node.path }"
            >
              <button
                type="button"
                class="sidebar-file-item sidebar-tree-node"
                :class="{ 'is-dir': node.is_dir, 'is-viewing': viewingFilePath === node.path }"
                :style="{ paddingLeft: 8 + node.depth * 14 + 'px' }"
                :title="node.name"
                @click="onTreeFileClick(node)"
              >
                <span class="sidebar-tree-chevron" v-if="node.is_dir">
                  <svg v-if="node.expanded" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                </span>
                <span v-else class="sidebar-tree-chevron-placeholder" />
                <span class="sidebar-file-icon">
                  <img v-if="node.is_dir" :src="getFolderIconUrl(node.expanded)" width="15" height="15" alt="" />
                  <img v-else :src="getFileIconUrl(node.name)" width="15" height="15" alt="" />
                </span>
                <span class="sidebar-file-name">{{ node.name }}</span>
              </button>
              <!-- 文件/文件夹操作菜单 -->
              <button
                type="button"
                class="sidebar-session-menu-trigger"
                :class="{ 'is-open': openFileMenuId === node.path }"
                @click.stop="toggleFileMenu(node.path)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
              </button>
              <div class="sidebar-session-menu sidebar-tree-menu" :class="{ show: openFileMenuId === node.path }">
                <button type="button" class="sidebar-menu-item" @click.stop="handleAddNodeToChat(node)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span>{{ t('workspace.addToChat') }}</span>
                </button>
                <button type="button" class="sidebar-menu-item" @click.stop="handleRenameNode(node)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                  <span>{{ t('session.rename') }}</span>
                </button>
                <button type="button" class="sidebar-menu-item sidebar-menu-item-danger" @click.stop="handleDeleteNode(node)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                  <span>{{ t('session.delete') }}</span>
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 任务列表（普通对话 + 工作目录分组） -->
      <div v-else class="sidebar-section">
        <div class="sidebar-section-label">{{ t('nav.taskList') }}</div>
        <div class="sidebar-session-list">
          <div v-if="sessions.length === 0" class="sidebar-empty">{{ t('nav.noTasks') }}</div>

          <!-- 工作目录分组（可折叠） -->
          <div
            v-for="group in groupedSessions"
            :key="group.name"
            class="sidebar-ws-group sidebar-session-item-wrap"
            :class="{ 'has-active': openWsMenuId === group.name }"
          >
            <button
              type="button"
              class="sidebar-ws-group-header"
              @click="toggleGroup(group.name)"
            >
              <svg
                class="sidebar-ws-chevron"
                :class="{ collapsed: isGroupCollapsed(group.name) }"
                width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
              <span class="sidebar-ws-group-name" :title="group.name">{{ workspaceDisplayName(group.name) }}</span>
              <button
                type="button"
                class="sidebar-ws-folder-btn"
                :title="t('workspace.viewFiles')"
                @click.stop="handleWsViewFiles(group.name)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              </button>
            </button>
            <button
              type="button"
              class="sidebar-ws-menu-trigger"
              :class="{ 'is-open': openWsMenuId === group.name }"
              @click.stop="toggleWsGroupMenu(group.name)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
            </button>
            <div class="sidebar-session-menu sidebar-ws-menu" :class="{ show: openWsMenuId === group.name }">
              <button type="button" class="sidebar-menu-item" @click.stop="handleWsViewFiles(group.name)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                <span>{{ t('workspace.viewFiles') }}</span>
              </button>
              <button type="button" class="sidebar-menu-item" @click.stop="handleWsRename(group.name)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                <span>{{ t('session.rename') }}</span>
              </button>
              <button type="button" class="sidebar-menu-item sidebar-menu-item-danger" @click.stop="handleWsDelete(group.name)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                <span>{{ t('session.delete') }}</span>
              </button>
            </div>
            <div v-show="!isGroupCollapsed(group.name)" class="sidebar-ws-group-body">
              <div
                v-for="s in group.sessions"
                :key="s.id"
                class="sidebar-session-item-wrap"
                :class="{ 'has-active': currentSessionId === s.id }"
              >
                <button
                  type="button"
                  class="sidebar-session-item"
                  :class="{ active: currentSessionId === s.id, pinned: s.is_pinned }"
                  :title="s.title"
                  @click="handleSelectSession(s)"
                >
                  <span class="sidebar-session-icon">
                    <svg v-if="s.is_pinned" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2l2.9 6.9L22 9.3l-5.2 4.5 1.6 7.1L12 17.8 5.6 20.9l1.6-7.1L2 9.3l7.1-.4L12 2z"/></svg>
                    <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  </span>
                  <span class="sidebar-session-title">{{ s.title }}</span>
                </button>
                <button
                  type="button"
                  class="sidebar-session-menu-trigger"
                  :class="{ 'is-open': openMenuId === s.id }"
                  @click.stop="toggleMenu(s.id)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
                </button>
                <div class="sidebar-session-menu" :class="{ show: openMenuId === s.id }">
                  <button type="button" class="sidebar-menu-item" @click.stop="handleViewFiles(s)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    <span>{{ t('session.viewFiles') }}</span>
                  </button>
                  <button type="button" class="sidebar-menu-item" @click.stop="handlePin(s)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2z"/></svg>
                    <span>{{ s.is_pinned ? t('session.unpin') : t('session.pin') }}</span>
                  </button>
                  <button type="button" class="sidebar-menu-item" @click.stop="handleRename(s)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                    <span>{{ t('session.rename') }}</span>
                  </button>
                  <button type="button" class="sidebar-menu-item sidebar-menu-item-danger" @click.stop="handleDelete(s)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                    <span>{{ t('session.delete') }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 普通对话：扁平列表，不分组 -->
          <template v-if="normalSessions.length">
            <div
              v-for="s in normalSessions"
              :key="s.id"
              class="sidebar-session-item-wrap"
              :class="{ 'has-active': currentSessionId === s.id }"
            >
              <button
                type="button"
                class="sidebar-session-item"
                :class="{ active: currentSessionId === s.id, pinned: s.is_pinned }"
                :title="s.title"
                @click="handleSelectSession(s)"
              >
                <span class="sidebar-session-icon">
                  <svg v-if="s.is_pinned" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2l2.9 6.9L22 9.3l-5.2 4.5 1.6 7.1L12 17.8 5.6 20.9l1.6-7.1L2 9.3l7.1-.4L12 2z"/></svg>
                  <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </span>
                <span class="sidebar-session-title">{{ s.title }}</span>
              </button>
              <button
                type="button"
                class="sidebar-session-menu-trigger"
                :class="{ 'is-open': openMenuId === s.id }"
                @click.stop="toggleMenu(s.id)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
              </button>
              <div class="sidebar-session-menu" :class="{ show: openMenuId === s.id }">
                <button type="button" class="sidebar-menu-item" @click.stop="handleViewFiles(s)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                  <span>{{ t('session.viewFiles') }}</span>
                </button>
                <button type="button" class="sidebar-menu-item" @click.stop="handlePin(s)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2z"/></svg>
                  <span>{{ s.is_pinned ? t('session.unpin') : t('session.pin') }}</span>
                </button>
                <button type="button" class="sidebar-menu-item" @click.stop="handleRename(s)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                  <span>{{ t('session.rename') }}</span>
                </button>
                <button type="button" class="sidebar-menu-item sidebar-menu-item-danger" @click.stop="handleDelete(s)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                  <span>{{ t('session.delete') }}</span>
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div v-if="sidebarOpen" class="sidebar-footer">
      <div class="sidebar-user">
        <div class="sidebar-user-avatar">
          {{ (user?.username || 'U').charAt(0).toUpperCase() }}
        </div>
        <div class="sidebar-user-meta">
          <div class="sidebar-user-name">{{ user?.username || 'User' }}</div>
          <div class="sidebar-user-plan">{{ membershipText(user?.membership_level) }}</div>
        </div>
        <button type="button" class="sidebar-user-settings" :title="t('nav.settings')" @click="settingsStore.openSettings()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <button type="button" class="sidebar-user-logout" :title="t('nav.logout')" @click="$emit('logout')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from '../i18n'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import { listWorkspaceFiles, deleteWorkspaceFile, renameWorkspaceFile, renameWorkspace, deleteWorkspace } from '../api/workspaces'
import { getFileIconUrl, getFolderIconUrl } from '../utils/fileIcons'

const { t, tm } = useI18n()
const settingsStore = useSettingsStore()
const router = useRouter()
const route = useRoute()

const props = defineProps({
  sidebarOpen: Boolean,
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: [String, null], default: null },
  user: Object,
  viewingFilePath: { type: String, default: '' },
})

const emit = defineEmits([
  'toggle-sidebar',
  'create-new-chat',
  'select-session',
  'logout',
  'open-search',
  'sessions-changed',
  'session-deleted',
  'view-file',
  'exit-file-view',
  'add-to-chat',
])

const activeNav = computed(() => {
  if (route.name === 'agents') return 'agent'
  if (route.name === 'skills') return 'skills'
  if (route.name === 'automation') return 'schedule'
  return 'chat'
})
const openMenuId = ref(null)
const openWsMenuId = ref(null)
const collapsedGroups = ref({})

function workspaceDisplayName(name) {
  return (!name || name === 'default') ? t('workspace.normal') : name
}

// 普通对话（default）直接作为扁平列表展示
const normalSessions = computed(() =>
  sortSessions(props.sessions.filter(s => !s.workspace_dir || s.workspace_dir === 'default'))
)

// 按工作目录分组，过滤掉 default（普通对话），组内置顶会话在前
const groupedSessions = computed(() => {
  const map = new Map()
  for (const s of props.sessions) {
    const key = s.workspace_dir || 'default'
    if (key === 'default') continue
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(s)
  }
  const groups = []
  for (const [name, list] of map) {
    groups.push({ name, sessions: sortSessions(list) })
  }
  return groups
})

function sortSessions(list) {
  return [...list].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1
    if (!a.is_pinned && b.is_pinned) return 1
    return 0
  })
}

function toggleGroup(name) {
  collapsedGroups.value = { ...collapsedGroups.value, [name]: !isGroupCollapsed(name) }
}

// 所有工作目录组默认折叠；显式切换后记住状态
function isGroupCollapsed(name) {
  if (name in collapsedGroups.value) return collapsedGroups.value[name]
  return true
}

function toggleMenu(id) {
  openMenuId.value = openMenuId.value === id ? null : id
}

function closeMenu() {
  openMenuId.value = null
}

// ============ 工作目录分组菜单 ============

function toggleWsGroupMenu(name) {
  openWsMenuId.value = openWsMenuId.value === name ? null : name
}

function closeWsMenu() {
  openWsMenuId.value = null
}

function handleWsViewFiles(name) {
  closeWsMenu()
  // 找到该组第一个 session 的完整对象，借用 handleViewFiles 逻辑
  const group = groupedSessions.value.find(g => g.name === name)
  if (!group || !group.sessions.length) return
  handleViewFiles(group.sessions[0])
}

async function handleWsRename(name) {
  closeWsMenu()
  let value
  try {
    const result = await ElMessageBox.prompt(
      t('session.renamePrompt'),
      t('session.rename'),
      {
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
        inputValue: name || '',
        inputValidator: (val) => {
          if (!val?.trim()) return t('session.renameEmpty')
          return true
        },
      },
    )
    value = result.value
  } catch {
    return
  }
  const clean = value.trim()
  if (clean === name) return
  try {
    await renameWorkspace(name, clean)
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

async function handleWsDelete(name) {
  closeWsMenu()
  try {
    await ElMessageBox.confirm(
      t('workspace.deleteConfirmWs', { name }),
      t('session.delete'),
      {
        type: 'warning',
        confirmButtonText: t('session.delete'),
        cancelButtonText: t('settings.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await deleteWorkspace(name)
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

// ============ 文件浏览（树形展开，参考 ExplorerPanel） ============
// fileView: null | { workspace, loading }
const fileView = ref(null)
// treeData: 扁平 map，path -> { name, path, is_dir, expanded, children_loaded, children: string[] }
const treeData = ref({})
const treeLoadingFolders = ref(new Set())

async function handleViewFiles(s) {
  closeMenu()
  const ws = s.workspace_dir || 'default'
  fileView.value = { workspace: ws, loading: true }
  treeData.value = {}
  await loadTreeRoot()
}

async function loadTreeRoot() {
  if (!fileView.value) return
  fileView.value.loading = true
  try {
    const res = await listWorkspaceFiles(fileView.value.workspace, '')
    const files = res.data.files || []
    const map = {}
    for (const f of files) {
      map[f.path] = { name: f.name, path: f.path, is_dir: f.is_dir, expanded: false, children_loaded: false, children: [] }
    }
    treeData.value = map
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
    treeData.value = {}
  } finally {
    fileView.value.loading = false
  }
}

async function loadTreeChildren(node) {
  if (!fileView.value || !node.is_dir || node.children_loaded) return
  treeLoadingFolders.value.add(node.path)
  try {
    const res = await listWorkspaceFiles(fileView.value.workspace, node.path)
    const files = res.data.files || []
    const newChildren = []
    for (const f of files) {
      if (!treeData.value[f.path]) {
        treeData.value[f.path] = { name: f.name, path: f.path, is_dir: f.is_dir, expanded: false, children_loaded: false, children: [] }
      }
      newChildren.push(f.path)
    }
    // 标记子目录已加载（替换对象触发响应式）
    treeData.value[node.path] = { ...node, children_loaded: true, children: newChildren }
  } catch {
    // ignore
  } finally {
    treeLoadingFolders.value.delete(node.path)
  }
}

async function toggleTreeFolder(node) {
  if (!node.is_dir) return
  if (treeLoadingFolders.value.has(node.path)) return
  const newExpanded = !node.expanded
  treeData.value[node.path] = { ...node, expanded: newExpanded }
  if (newExpanded && !node.children_loaded) {
    await loadTreeChildren(treeData.value[node.path])
  }
}

// 构建根节点列表（文件夹优先，再按名称排序）
function buildTreeRoots() {
  const nodes = Object.values(treeData.value)
  const roots = nodes.filter((n) => {
    const parentPath = n.path.includes('/') ? n.path.substring(0, n.path.lastIndexOf('/')) : ''
    return !parentPath || !treeData.value[parentPath]
  })
  return roots.sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

// 扁平化为可见节点列表（带 depth），仅展开的文件夹的子节点可见
const visibleTreeNodes = computed(() => {
  const result = []
  function walk(nodes, depth) {
    for (const n of nodes) {
      result.push({ ...n, depth })
      if (n.is_dir && n.expanded && n.children_loaded) {
        const children = n.children
          .map((p) => treeData.value[p])
          .filter(Boolean)
          .sort((a, b) => {
            if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
            return a.name.localeCompare(b.name)
          })
        walk(children, depth + 1)
      }
    }
  }
  walk(buildTreeRoots(), 0)
  return result
})

function exitFileView() {
  fileView.value = null
  treeData.value = {}
  emit('exit-file-view')
}

function onTreeFileClick(node) {
  if (node.is_dir) {
    toggleTreeFolder(node)
  } else if (fileView.value) {
    emit('view-file', { workspace: fileView.value.workspace, file: { name: node.name, path: node.path, is_dir: false, size: 0 } })
  }
}

// ============ 文件夹操作菜单 ============
const openFileMenuId = ref(null)

function toggleFileMenu(path) {
  openFileMenuId.value = openFileMenuId.value === path ? null : path
}

function closeFileMenu() {
  openFileMenuId.value = null
}

// 添加文件/文件夹到对话（作为引用传入输入框）
function handleAddNodeToChat(node) {
  closeFileMenu()
  emit('add-to-chat', node.path)
}

// 重命名文件夹/文件
async function handleRenameNode(node) {
  closeFileMenu()
  let value
  try {
    const result = await ElMessageBox.prompt(
      t('session.renamePrompt'),
      t('session.rename'),
      {
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
        inputValue: node.name || '',
        inputValidator: (val) => {
          if (!val?.trim()) return t('session.renameEmpty')
          return true
        },
      },
    )
    value = result.value
  } catch {
    return
  }
  try {
    await renameWorkspaceFile(fileView.value.workspace, node.path, value.trim())
    const parentPath = node.path.includes('/') ? node.path.slice(0, node.path.lastIndexOf('/')) : ''
    await reloadNodeChildren(parentPath)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

// 删除文件夹/文件
async function handleDeleteNode(node) {
  closeFileMenu()
  try {
    await ElMessageBox.confirm(
      t('workspace.deleteConfirm', { name: node.name }),
      t('session.delete'),
      {
        type: 'warning',
        confirmButtonText: t('session.delete'),
        cancelButtonText: t('settings.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await deleteWorkspaceFile(fileView.value.workspace, node.path)
    const parentPath = node.path.includes('/') ? node.path.slice(0, node.path.lastIndexOf('/')) : ''
    await reloadNodeChildren(parentPath)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

// 重新加载某目录的子节点（parentPath 为空则重载根）
async function reloadNodeChildren(parentPath) {
  if (!fileView.value) return
  if (!parentPath) {
    await loadTreeRoot()
    return
  }
  const node = treeData.value[parentPath]
  if (!node) {
    await loadTreeRoot()
    return
  }
  treeData.value[parentPath] = { ...node, children_loaded: false, children: [] }
  await loadTreeChildren(treeData.value[parentPath])
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function handleSelectSession(s) {
  closeMenu()
  emit('select-session', s)
}

async function handlePin(s) {
  closeMenu()
  try {
    await api.put(`/api/chat/sessions/${s.id}/pin`, { is_pinned: !s.is_pinned })
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

async function handleRename(s) {
  closeMenu()
  let value
  try {
    const result = await ElMessageBox.prompt(
      t('session.renamePrompt'),
      t('session.rename'),
      {
        confirmButtonText: t('settings.save'),
        cancelButtonText: t('settings.cancel'),
        inputValue: s.title || '',
        inputValidator: (val) => {
          if (!val?.trim()) return t('session.renameEmpty')
          return true
        },
      },
    )
    value = result.value
  } catch {
    return
  }
  const clean = value.trim()
  try {
    await api.put(`/api/chat/sessions/${s.id}/title`, { title: clean })
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

async function handleDelete(s) {
  closeMenu()
  try {
    await ElMessageBox.confirm(
      t('session.deleteConfirm', { title: s.title || s.id }),
      t('session.delete'),
      {
        type: 'warning',
        confirmButtonText: t('session.delete'),
        cancelButtonText: t('settings.cancel'),
      },
    )
  } catch {
    return
  }
  try {
    await api.delete(`/api/chat/sessions/${s.id}`)
    emit('session-deleted', s)
    emit('sessions-changed')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t('session.actionFailed'))
  }
}

// 点击外部关闭菜单
function handleDocumentClick(e) {
  if (openMenuId.value !== null) {
    if (!e.target.closest('.sidebar-session-item-wrap')) {
      closeMenu()
    }
  }
  if (openFileMenuId.value !== null) {
    if (!e.target.closest('.sidebar-tree-node-wrap')) {
      closeFileMenu()
    }
  }
  if (openWsMenuId.value !== null) {
    if (!e.target.closest('.sidebar-ws-group')) {
      closeWsMenu()
    }
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
})
onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
})

function handleNavClick(key) {
  if (key === 'chat') {
    emit('create-new-chat')
  } else if (key === 'schedule') {
    router.push({ name: 'automation' })
  } else if (key === 'agent') {
    router.push({ name: 'agents' })
  } else if (key === 'skills') {
    router.push({ name: 'skills' })
  }
}

const navItems = computed(() => [
  {
    key: 'chat',
    label: t('nav.newChat'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`
  },
  {
    key: 'agent',
    label: t('nav.agent'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>`
  },
  {
    key: 'skills',
    label: t('nav.skills'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`
  },
  {
    key: 'schedule',
    label: t('nav.schedule'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`
  },
  {
    key: 'knowledge',
    label: t('nav.knowledge'),
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`
  },
])

function membershipText(level) {
  const map = tm('settings.membership')
  return map[level] ?? map[0]
}
</script>
