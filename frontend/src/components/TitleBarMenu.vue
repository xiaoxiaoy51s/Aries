<template>
  <div class="titlebar-menu-root" @mouseleave="onMouseLeave">
    <div
      v-for="menu in menus"
      :key="menu.key"
      class="titlebar-menu-item"
      :class="{ active: activeKey === menu.key }"
      @mouseenter="onMouseEnter(menu.key)"
      @click="onClickMenu(menu.key)"
    >
      {{ menu.label }}
      <Transition name="menu-fade">
        <div v-if="activeKey === menu.key" class="titlebar-menu-dropdown" @click.stop>
          <div
            v-for="(item, idx) in menu.items"
            :key="item.id || idx"
            class="titlebar-menu-row"
            :class="{ divider: item.divider }"
            @click="onItemClick(item)"
          >
            <template v-if="!item.divider">
              <span class="menu-row-label">{{ item.label }}</span>
              <span v-if="item.shortcut" class="menu-row-shortcut">{{ item.shortcut }}</span>
            </template>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

export interface MenuItem {
  id?: string
  label?: string
  shortcut?: string
  divider?: boolean
}

export interface MenuDef {
  key: string
  label: string
  items: MenuItem[]
}

const props = defineProps<{
  menus: MenuDef[]
}>()

const emit = defineEmits<{
  (e: 'select', menuKey: string, item: MenuItem): void
}>()

const activeKey = ref<string | null>(null)
let closeTimer: ReturnType<typeof setTimeout> | null = null

function clearTimer() {
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
}

function onMouseEnter(key: string) {
  clearTimer()
  activeKey.value = key
}

function onMouseLeave() {
  closeTimer = setTimeout(() => {
    activeKey.value = null
  }, 120)
}

function onClickMenu(key: string) {
  activeKey.value = activeKey.value === key ? null : key
}

function onItemClick(item: MenuItem) {
  if (item.divider) return
  const key = activeKey.value
  activeKey.value = null
  if (key) {
    emit('select', key, item)
  }
}
</script>

<style scoped>
.titlebar-menu-root {
  display: flex;
  align-items: center;
  height: 100%;
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.titlebar-menu-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
  border-radius: 4px;
  transition: background 0.12s;
}

.titlebar-menu-item:hover,
.titlebar-menu-item.active {
  background: var(--accent-hover);
}

.titlebar-menu-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  min-width: 220px;
  padding: 6px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  z-index: 1001;
}

.titlebar-menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.1s;
}

.titlebar-menu-row:hover:not(.divider) {
  background: var(--accent-hover);
}

.titlebar-menu-row.divider {
  height: 1px;
  padding: 0;
  margin: 6px 4px;
  background: var(--border);
  border-radius: 0;
  cursor: default;
}

.menu-row-label {
  flex: 1;
  white-space: nowrap;
}

.menu-row-shortcut {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 24px;
  white-space: nowrap;
}

.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}

.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
