<template>
  <div class="explorer-node">
    <!-- 文件夹 -->
    <div
      v-if="node.isDir"
      class="explorer-folder"
      :class="{ expanded: node.expanded }"
      @click="$emit('toggle', node)"
    >
      <span class="explorer-arrow">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </span>
      <span class="explorer-icon" :style="{ color: '#7b8fa3' }">
        <svg v-if="node.expanded" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M20 20v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"/>
          <path d="M4 10V6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v1"/>
        </svg>
      </span>
      <span class="explorer-label">{{ node.name }}</span>
    </div>

    <!-- 文件 -->
    <div
      v-else
      class="explorer-file"
      :class="{ active: selectedPath === node.path }"
      @click="$emit('select', node.path)"
    >
      <span class="explorer-indent"></span>
      <span class="explorer-icon" :style="{ color: iconColor }">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
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
        @select="$emit('select', $event)"
        @toggle="$emit('toggle', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

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
}>()

defineEmits<{
  select: [path: string]
  toggle: [node: TreeNode]
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

const iconColor = computed(() => {
  const ext = props.node.name.split('.').pop()?.toLowerCase() || ''
  const colors: Record<string, string> = {
    js: '#f1e05a', ts: '#3178c6', tsx: '#3178c6', jsx: '#61dafb',
    vue: '#42b883', html: '#e34c26', css: '#563d7c', scss: '#c6538c',
    json: '#f1e05a', md: '#083fa1', py: '#3572A5',
    go: '#00ADD8', rs: '#dea584', java: '#b07219', c: '#555555', cpp: '#f34b7d',
    sh: '#89e051', yml: '#cb171e', yaml: '#cb171e', xml: '#0060ac',
  }
  return colors[ext] || '#6e7681'
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
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.15s;
  color: var(--text-muted);
}

.explorer-folder.expanded .explorer-arrow {
  transform: rotate(90deg);
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
