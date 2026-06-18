<template>
  <div class="tree-node">
    <!-- 文件夹 -->
    <div
      v-if="node.children"
      class="tree-folder"
      :class="{ expanded: node.expanded }"
      @click="$emit('toggle', node)"
    >
      <span class="tree-arrow">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </span>
      <span class="tree-icon">
        <svg v-if="node.expanded" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M20 20v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"/>
          <path d="M4 10V6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v1"/>
        </svg>
      </span>
      <span class="tree-label">{{ node.name }}</span>
    </div>

    <!-- 文件 -->
    <div
      v-else
      class="tree-file"
      :class="{ active: selectedPath === node.path }"
      @click="$emit('select', node.path)"
    >
      <span class="tree-indent"></span>
      <span class="tree-icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
      </span>
      <span class="tree-label">{{ node.name }}</span>
      <span v-if="node.status" class="tree-status" :class="node.status">{{ node.status }}</span>
    </div>

    <!-- 子节点 -->
    <div v-if="node.children && node.expanded" class="tree-children">
      <DiffTreeNode
        v-for="child in node.children"
        :key="child.name"
        :node="child"
        :selected-path="selectedPath"
        @select="$emit('select', $event)"
        @toggle="$emit('toggle', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
interface TreeNode {
  name: string
  path: string
  status?: string
  children?: TreeNode[]
  expanded?: boolean
}

defineProps<{
  node: TreeNode
  selectedPath: string | null
}>()

defineEmits<{
  select: [path: string]
  toggle: [node: TreeNode]
}>()
</script>

<style scoped>
.tree-node {
  font-size: 12px;
}

.tree-folder {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background 0.12s;
  user-select: none;
}

.tree-folder:hover {
  background: var(--accent-hover);
}

.tree-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.15s;
}

.tree-folder.expanded .tree-arrow {
  transform: rotate(90deg);
}

.tree-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--text-muted);
}

.tree-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-file {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  cursor: pointer;
  color: var(--text);
  transition: background 0.12s;
  user-select: none;
}

.tree-file:hover {
  background: var(--accent-hover);
}

.tree-file.active {
  background: var(--accent-active);
}

.tree-indent {
  display: inline-block;
  width: 14px;
  flex-shrink: 0;
}

.tree-status {
  font-size: 10px;
  font-weight: 700;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}

.tree-status.M { color: #c19c00; }
.tree-status.A { color: #107c10; }
.tree-status.D { color: #c50f1f; }
.tree-status.R { color: #0037da; }
.tree-status.\?  { color: #881798; }
.tree-status.U { color: #c50f1f; }

.tree-children {
  padding-left: 10px;
}
</style>
