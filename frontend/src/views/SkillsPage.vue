<template>
  <section id="skillsPage" class="page">
    <header class="page-header">
      <h1>技能管理</h1>
      <p class="page-desc">启用或禁用 Agent 可用的技能</p>
    </header>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="skills-list">
      <div v-for="skill in skills" :key="skill.folder_name" class="skill-card">
        <div class="skill-header">
          <div class="skill-title">
            <span class="skill-icon">⚡</span>
            <h3>{{ skill.name }}</h3>
          </div>
          <button 
            type="button" 
            class="toggle-btn"
            :class="{ enabled: skill.enabled }"
            @click="toggleSkill(skill)"
          >
            {{ skill.enabled ? '已启用' : '已禁用' }}
          </button>
        </div>
        <p>{{ truncate(skill.description) }}</p>
      </div>
      <div v-if="skills.length === 0" class="empty">暂无技能</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listSkills, updateSkillStatus, type SkillItem } from '@/api/skills'

const skills = ref<SkillItem[]>([])
const loading = ref(true)
const error = ref('')

async function fetchSkills() {
  try {
    loading.value = true
    error.value = ''
    const data = await listSkills()
    skills.value = data
  } catch (e: any) {
    error.value = e.message || '获取技能列表失败'
  } finally {
    loading.value = false
  }
}

async function toggleSkill(skill: SkillItem) {
  const newEnabled = !skill.enabled
  try {
    await updateSkillStatus(skill.folder_name, newEnabled)
    skill.enabled = newEnabled
  } catch (e: any) {
    error.value = e.message || '更新技能状态失败'
  }
}

onMounted(fetchSkills)

function truncate(text: string | undefined, max = 20): string {
  if (!text) return '无描述'
  return text.length > max ? text.slice(0, max) + '...' : text
}
</script>

<style scoped>
.page {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.page-header {
  padding: 28px 32px 0;
  flex-shrink: 0;
}

.page-header h1 {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
}

.skills-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px 32px 32px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  align-content: start;
}

.skill-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  background: var(--bg-panel);
  transition: box-shadow 0.15s;
}

.skill-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.skill-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.skill-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.skill-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.skill-card:hover .toggle-btn {
  opacity: 1;
}

.skill-card h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 0;
}

.skill-card p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 0;
  line-height: 1.5;
}

.toggle-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  transition: all 0.15s;
  opacity: 0;
  flex-shrink: 0;
}

.toggle-btn.enabled {
  background: #e8f5ee;
  border-color: #b8dfc8;
  color: #2d7a4f;
}

.loading,
.error,
.empty {
  padding: 40px 32px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.error {
  color: #d93025;
}
</style>
