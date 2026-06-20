<template>
  <div class="explorer-node">
    <!-- 文件夹 -->
    <div
      v-if="node.isDir"
      class="explorer-folder"
      :class="{ expanded: node.expanded, loading: isLoading }"
      @click="$emit('toggle', node)"
      @contextmenu.prevent="$emit('contextmenu', { node, event: $event })"
    >
      <span class="explorer-arrow">
        <svg v-if="!isLoading" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
        <span v-else class="arrow-spinner"></span>
      </span>
      <span class="explorer-icon">
        <img :src="folderIconSrc" width="16" height="16" alt="" @error="(e: Event) => (e.target as HTMLImageElement).style.display = 'none'" />
      </span>
      <span class="explorer-label">{{ node.name }}</span>
    </div>

    <!-- 文件 -->
    <div
      v-else
      class="explorer-file"
      :class="{ active: selectedPath === node.path }"
      @click="$emit('select', node.path)"
      @contextmenu.prevent="$emit('contextmenu', { node, event: $event })"
    >
      <span class="explorer-indent"></span>
      <span class="explorer-icon">
        <img :src="fileIconSrc" width="16" height="16" alt="" @error="(e: Event) => (e.target as HTMLImageElement).style.display = 'none'" />
      </span>
      <span class="explorer-label">{{ node.name }}</span>
    </div>

    <!-- 子节点 -->
    <div v-if="node.isDir && node.expanded" class="explorer-children">
      <ExplorerTreeNode
        v-for="child in childNodes"
        :key="child.path"
        :node="child"
        :selected-path="selectedPath"
        :tree-data="treeData"
        :loading-folders="loadingFolders"
        @select="$emit('select', $event)"
        @toggle="$emit('toggle', $event)"
        @contextmenu="$emit('contextmenu', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getIconForFile, getIconForFolder, getIconForOpenFolder, DEFAULT_FILE, DEFAULT_FOLDER_OPENED } from 'vscode-icons-js'

const ICON_CDN = '/file-icons'

interface TreeNode {
  name: string
  path: string
  isDir: boolean
  expanded?: boolean
  childrenLoaded?: boolean
}

const props = defineProps<{
  node: TreeNode
  selectedPath: string | null
  treeData?: Record<string, TreeNode>
  loadingFolders?: Set<string>
}>()

defineEmits<{
  select: [path: string]
  toggle: [node: TreeNode]
  contextmenu: [payload: { node: TreeNode; event: MouseEvent }]
}>()

const childNodes = computed(() => {
  const data = props.treeData || {}
  const prefix = props.node.path + '/'
  return Object.values(data).filter(n => {
    if (!n.path.startsWith(prefix)) return false
    const rest = n.path.slice(prefix.length)
    return !rest.includes('/')
  }).sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
    return a.name.localeCompare(b.name)
  })
})

const fileIconSrc = computed(() => {
  const iconName = getIconForFile(props.node.name) || DEFAULT_FILE
  return `${ICON_CDN}/${iconName}`
})

const folderIconSrc = computed(() => {
  const iconName = props.node.expanded
    ? (getIconForOpenFolder(props.node.name) || DEFAULT_FOLDER_OPENED)
    : (getIconForFolder(props.node.name) || DEFAULT_FOLDER_OPENED)
  return `${ICON_CDN}/${iconName}`
})

const isLoading = computed(() => {
  return props.loadingFolders?.has(props.node.path) || false
})
</script>

<style scoped>
.explorer-node {
  font-size: 12px;
}

.explorer-folder {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  cursor: pointer;
  color: var(--text);
  transition: background 0.12s;
  user-select: none;
}

.explorer-folder:hover {
  background: var(--accent-hover);
}

.explorer-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: transform 0.15s;
  color: var(--text-secondary, #888);
  border-radius: 2px;
}

.explorer-arrow:hover {
  background: rgba(0, 0, 0, 0.06);
}

.explorer-folder.expanded .explorer-arrow {
  transform: rotate(90deg);
}

.explorer-folder.loading {
  opacity: 0.7;
  pointer-events: none;
}

.arrow-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--text-muted, #999);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.explorer-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.explorer-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.explorer-file {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  cursor: pointer;
  color: var(--text);
  transition: background 0.12s;
  user-select: none;
}

.explorer-file:hover {
  background: var(--accent-hover);
}

.explorer-file.active {
  background: var(--accent-active);
}

.explorer-indent {
  display: inline-block;
  width: 14px;
  flex-shrink: 0;
}

.explorer-children {
  padding-left: 10px;
}
</style>
