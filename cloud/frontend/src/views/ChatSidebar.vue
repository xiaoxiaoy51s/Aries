<template>
  <aside class="chat-sidebar" :class="{ collapsed: !sidebarOpen }">
    <div class="sidebar-top">
      <div class="sidebar-brand">
        <img src="../assets/logo.png" alt="Aries Cloud" class="sidebar-brand-logo" />
        <span v-if="sidebarOpen" class="sidebar-brand-name">Aries Cloud</span>
      </div>
      <button
        type="button"
        class="sidebar-toggle"
        :title="sidebarOpen ? t('nav.collapse') : t('nav.expand')"
        @click="$emit('toggle-sidebar')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <path d="M9 3v18"/>
        </svg>
      </button>
    </div>

    <div v-if="sidebarOpen" class="sidebar-body">
      <!-- 独立的新对话入口 -->
      <div class="sidebar-group-label">{{ t('nav.newChat') }}</div>
      <button
        type="button"
        class="sidebar-nav-item sidebar-chat-entry"
        :class="{ active: activeNav === 'chat' && !currentSessionId }"
        @click="handleNewChat"
      >
        <span class="sidebar-nav-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </span>
        <span class="sidebar-nav-label">{{ t('nav.chat') }}</span>
      </button>

      <nav class="sidebar-nav">
        <div v-for="group in navGroups" :key="group.title" class="sidebar-nav-group">
          <div class="sidebar-nav-group-label">{{ group.title }}</div>
          <button
            v-for="item in group.items"
            :key="item.key"
            type="button"
            class="sidebar-nav-item"
            :class="{ active: activeNav === item.key }"
            @click="handleNavClick(item.key)"
          >
            <span class="sidebar-nav-icon" v-html="item.icon" />
            <span class="sidebar-nav-label">{{ item.label }}</span>
          </button>
        </div>
      </nav>

      <div class="sidebar-section">
        <div class="sidebar-section-label">{{ t('nav.taskList') }}</div>
        <div class="sidebar-session-list">
          <div v-if="sessions.length === 0" class="sidebar-empty">{{ t('nav.noTasks') }}</div>
          <div
            v-for="s in sessions"
            :key="s.id"
            class="sidebar-session-item-wrap"
          >
            <button
              type="button"
              class="sidebar-session-item"
              :class="{ active: currentSessionId === s.id }"
              :title="s.title"
              @click="$emit('select-session', s)"
            >
              <span class="sidebar-session-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              </span>
              <span class="sidebar-session-title">{{ s.title }}</span>
              <span class="sidebar-session-menu-trigger" tabindex="0">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
              </span>
            </button>
            <div class="sidebar-session-menu">
              <button type="button" class="sidebar-menu-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2z"/></svg>
                <span>置顶</span>
              </button>
              <button type="button" class="sidebar-menu-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                <span>重命名</span>
              </button>
              <button type="button" class="sidebar-menu-item sidebar-menu-item-danger">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                <span>删除</span>
              </button>
            </div>
          </div>
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
import { ref, computed } from 'vue'
import { useI18n } from '../i18n'
import { useSettingsStore } from '../stores/settings'

const { t, tm } = useI18n()
const settingsStore = useSettingsStore()

const props = defineProps({
  sidebarOpen: Boolean,
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: [String, null], default: null },
  user: Object,
})

const emit = defineEmits(['toggle-sidebar', 'create-new-chat', 'select-session', 'logout'])

const activeNav = ref('chat')

function handleNewChat() {
  activeNav.value = 'chat'
  if (props.currentSessionId) {
    emit('create-new-chat')
  }
}

function handleNavClick(key) {
  if (key === 'settings') {
    settingsStore.openSettings()
  } else {
    activeNav.value = key
  }
}

const navGroups = computed(() => [
  {
    title: t('nav.workspace'),
    items: [
      {
        key: 'agent',
        label: t('nav.agent'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>`
      },
      {
        key: 'workflow',
        label: t('nav.workflow'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h6a3 3 0 0 1 3 3v6"/></svg>`
      },
      {
        key: 'schedule',
        label: t('nav.schedule'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`
      },
    ],
  },
  {
    title: t('nav.resources'),
    items: [
      {
        key: 'knowledge',
        label: t('nav.knowledge'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`
      },
      {
        key: 'remote',
        label: t('nav.remote'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`
      },
    ],
  },
  {
    title: t('nav.system'),
    items: [
      {
        key: 'settings',
        label: t('nav.settings'),
        icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`
      },
    ],
  },
])

function membershipText(level) {
  const map = tm('settings.membership')
  return map[level] ?? map[0]
}
</script>
