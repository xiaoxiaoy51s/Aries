<template>
  <div class="settings-section">
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
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  listPathPermissions,
  addPathPermission as apiAddPathPermission,
  removePathPermission as apiRemovePathPermission,
  type PathPermission,
} from '@/api/pathPermissions'
import { selectDirectory } from '@/api/system'

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

async function handleAddPath(type: 'whitelist' | 'blacklist') {
  try {
    let path = ''

    // 优先使用 Electron 原生文件浏览器
    const electronAPI = (window as any).electronAPI
    if (electronAPI?.selectDirectory) {
      const result = await electronAPI.selectDirectory({
        title: type === 'whitelist' ? '选择白名单路径' : '选择黑名单路径',
      })
      if (result.cancelled || !result.path) return
      path = result.path
    } else {
      // 回退到后端 API
      const result = await selectDirectory()
      if (result.cancelled || !result.path) return
      if (result.error) {
        alert(result.error)
        return
      }
      path = result.path
    }

    const res = await apiAddPathPermission(path, type)
    if (res.success) {
      await loadPathPermissions()
    } else {
      alert(res.error || '添加失败')
    }
  } catch (e: any) {
    alert(e.message || '添加失败')
  }
}

onMounted(() => {
  loadPathPermissions()
})
</script>

<style scoped>
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
