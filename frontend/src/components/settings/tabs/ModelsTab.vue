<template>
  <div class="settings-section">
    <div class="section-header">
      <span class="section-desc">管理可用的 AI 模型</span>
      <button type="button" class="secondary-btn" @click="openAddModal">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        新增模型
      </button>
    </div>
    <div class="model-list">
      <div
        v-for="model in modelStore.modelList"
        :key="model.id"
        class="model-item"
        :class="{ active: model.isActive }"
        @click="handleSetActive(model.id)"
      >
        <div class="model-info">
          <span class="model-name">{{ model.name }}</span>
          <span v-if="model.isActive" class="model-tag">默认</span>
        </div>
        <div class="model-actions" @click.stop>
          <button type="button" class="icon-btn-sm" title="编辑" @click="openEditModal(model)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
          <button
            v-if="model.id !== 'default-vision'"
            type="button"
            class="icon-btn-sm delete"
            title="删除"
            @click="handleDelete(model.id)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 模型编辑弹窗 -->
    <ModelEditModal
      :visible="modalVisible"
      :is-edit="isEditMode"
      :model="editingModel"
      @close="closeModal"
      @save="handleSave"
    />

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click="cancelDelete">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">确认删除</div>
        <div class="modal-body">
          <p>确定要删除这个模型吗？</p>
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
import { ref, onMounted } from 'vue'
import { useModelStore, type ModelItem } from '@/stores/model'
import ModelEditModal from '../ModelEditModal.vue'

const modelStore = useModelStore()

const modalVisible = ref(false)
const isEditMode = ref(false)
const editingModel = ref<ModelItem | null>(null)

function openAddModal() {
  isEditMode.value = false
  editingModel.value = null
  modalVisible.value = true
}

function openEditModal(model: ModelItem) {
  isEditMode.value = true
  editingModel.value = model
  modalVisible.value = true
}

function closeModal() {
  modalVisible.value = false
  editingModel.value = null
}

async function handleSave(data: Omit<ModelItem, 'id'>) {
  if (isEditMode.value && editingModel.value) {
    await modelStore.updateModel(editingModel.value.id, data)
  } else {
    await modelStore.addModel(data)
  }
  closeModal()
}

async function handleSetActive(id: string) {
  await modelStore.setActiveModel(id)
}

const showDeleteModal = ref(false)
const modelToDelete = ref<string | null>(null)

function handleDelete(id: string) {
  modelToDelete.value = id
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (modelToDelete.value) {
    await modelStore.deleteModel(modelToDelete.value)
    showDeleteModal.value = false
    modelToDelete.value = null
  }
}

function cancelDelete() {
  showDeleteModal.value = false
  modelToDelete.value = null
}

onMounted(() => {
  modelStore.loadModels()
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

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.secondary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.secondary-btn:hover {
  background: var(--accent-hover);
  border-color: var(--border);
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}

.model-item:hover {
  border-color: var(--border-strong);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.model-item.active {
  border-color: #2d7a4f;
  background: #f8fdfb;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.model-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: #e8f5ee;
  color: #2d7a4f;
  border-radius: 4px;
  font-weight: 500;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn-sm {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn-sm:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.icon-btn-sm.delete:hover {
  background: #fee2e2;
  color: #991b1b;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
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

.modal-btn-danger {
  background: #1f2937;
  color: #ffffff;
}
</style>
