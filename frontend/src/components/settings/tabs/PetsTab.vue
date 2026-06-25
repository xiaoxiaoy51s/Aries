<template>
  <div class="settings-section">
    <div class="section-header">
      <span class="section-desc">桌面宠物（Codex 兼容格式：spritesheet.webp + pet.json）。宠物目录：{{ petsDir }}/</span>
      <div class="section-header-actions">
        <button type="button" class="icon-btn" :disabled="petsLoading" title="打开宠物文件夹" @click="openPetsFolder">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          </svg>
        </button>
        <button type="button" class="icon-btn" :disabled="petsLoading" :title="petsLoading ? '加载中…' : '刷新'" @click="loadPets">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin': petsLoading }">
            <path d="M3 12a9 9 0 1 0 9-9"/><path d="M3 3v6h6"/>
          </svg>
        </button>
      </div>
    </div>
    <div v-if="petsLoading && petsList.length === 0" class="path-empty">加载中...</div>
    <div v-else-if="petsList.length === 0" class="path-empty">
      暂无宠物，请将 Codex 宠物（spritesheet.webp + pet.json）放入 {{ petsDir }}/&lt;宠物名&gt;/ 目录
    </div>
    <div v-else class="pet-grid">
      <div
        v-for="pet in petsList"
        :key="pet.id"
        class="pet-card"
        @click="showPetOnDesktop(pet)"
      >
        <div class="pet-preview">
          <div class="pet-preview-sprite" :style="getPetPreviewStyle(pet)" />
        </div>
        <div class="pet-name" :title="pet.displayName || pet.name">{{ pet.displayName || pet.name }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useModelStore } from '@/stores/model'
import { listPets, type PetInfo } from '@/api/pets'
import { petsDir, initPaths } from '@/utils/paths'

const petsList = ref<PetInfo[]>([])
const petsLoading = ref(false)

async function loadPets() {
  petsLoading.value = true
  try {
    const res = await listPets()
    petsList.value = res.pets || []
  } catch (e) {
    console.error('加载宠物列表失败', e)
    petsList.value = []
  } finally {
    petsLoading.value = false
  }
}

function getPetFullUrl(url: string): string {
  return `${useModelStore().getBaseUrl()}${url}`
}

function getPetPreviewStyle(pet: PetInfo): Record<string, string> {
  const cols = pet.columns || 8
  const rows = pet.rows || 9
  const idle = pet.states?.find(s => s.name === 'idle')
  const row = idle?.row ?? 0
  const url = pet.spritesheetUrl || pet.previewUrl
  if (!url) return {}
  const xPct = 0
  const yPct = rows > 1 ? (row / (rows - 1)) * 100 : 0
  return {
    backgroundImage: `url("${getPetFullUrl(url)}")`,
    backgroundSize: `${cols * 100}% ${rows * 100}%`,
    backgroundPosition: `${xPct}% ${yPct}%`,
    backgroundRepeat: 'no-repeat',
    imageRendering: 'pixelated',
  }
}

async function openPetsFolder() {
  try {
    const res = await fetch(`${useModelStore().getBaseUrl()}/files/open-in-editor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ work_dir: petsDir.value, editor: 'explorer' }),
    })
    const data = await res.json()
    if (data.error) {
      window.dispatchEvent(new CustomEvent('aries:toast', {
        detail: { message: data.error, type: 'error' },
      }))
    }
  } catch (e: any) {
    window.dispatchEvent(new CustomEvent('aries:toast', {
      detail: { message: e?.message || '打开文件夹失败', type: 'error' },
    }))
  }
}

function showPetOnDesktop(pet: PetInfo) {
  const spriteRel = pet.spritesheetUrl || pet.animations?.idle
  if (!spriteRel) return
  const spec = JSON.parse(JSON.stringify({
    url: getPetFullUrl(spriteRel),
    name: pet.displayName || pet.name,
    frameWidth: pet.frameWidth || 192,
    frameHeight: pet.frameHeight || 208,
    columns: pet.columns || 8,
    rows: pet.rows || 9,
    states: pet.states || undefined,
  }))
  window.electronAPI?.showPet(spec)
  localStorage.setItem('pet:active', JSON.stringify(spec))
  localStorage.setItem('pet:enabled', '1')
}

onMounted(() => {
  loadPets()
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

.section-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-strong, #ddd);
  border-radius: 6px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  color: var(--text);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.path-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 12px;
}

.pet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.pet-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.pet-card:hover {
  border-color: var(--accent, #3b82f6);
  background: var(--accent-hover, rgba(59, 130, 246, 0.08));
}

.pet-preview {
  width: 96px;
  height: 104px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 6px;
  overflow: hidden;
}

.pet-preview-sprite {
  width: 100%;
  height: 100%;
}

.pet-name {
  font-size: 12px;
  color: var(--text);
  text-align: center;
  word-break: break-all;
  line-height: 1.3;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
