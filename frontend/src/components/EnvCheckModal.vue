<template>
  <div v-if="visible" class="env-check-page">
    <div class="env-check-inner">
      <h2 class="env-check-title">环境检测</h2>
      <p class="env-check-desc">
        以下运行时未检测到，需要安装后才能正常使用 Aries 的全部功能。
      </p>

      <div class="env-list">
        <div
          v-for="rt in runtimeList"
          :key="rt.id"
          class="env-card"
          :class="{ installed: !missing.includes(rt.id) }"
        >
          <div class="env-card-icon" v-html="rt.icon"></div>
          <div class="env-card-info">
            <span class="env-card-name">{{ rt.name }}</span>
            <span v-if="!missing.includes(rt.id)" class="env-card-status ok">已安装</span>
            <span v-else class="env-card-status missing">未安装</span>
          </div>
          <button
            v-if="missing.includes(rt.id)"
            type="button"
            class="env-install-btn"
            :disabled="installing[rt.id]"
            @click="installRuntime(rt.id)"
          >
            {{ installing[rt.id] ? '安装中...' : '下载内置版本' }}
          </button>
        </div>
      </div>

      <div class="env-check-footer">
        <button
          type="button"
          class="env-recheck-btn"
          :disabled="rechecking"
          @click="recheck"
        >
          {{ rechecking ? '检测中...' : '重新检测' }}
        </button>
        <button
          v-if="missing.length > 0"
          type="button"
          class="env-skip-btn"
          @click="$emit('skip')"
        >
          稍后安装
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useModelStore } from '@/stores/model'

const props = defineProps<{
  visible: boolean
  missing: string[]
}>()

const emit = defineEmits<{
  skip: []
  'all-installed': []
}>()

const modelStore = useModelStore()
function devEnvApi(path: string) {
  return `${modelStore.getBaseUrl()}${path}`
}

const installing = reactive<Record<string, boolean>>({ node: false, python: false, git: false, officecli: false })
const rechecking = ref(false)

const runtimeList = [
  {
    id: 'node',
    name: 'Node.js',
    icon: '<svg width="32" height="32" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M487.904 6.528L88.128 238.208a48.32 48.32 0 0 0-24.032 41.952V743.68c0 17.248 9.184 33.28 24.064 41.888l399.776 231.904c14.944 8.672 33.28 8.672 48.224 0l399.616-231.808c14.944-8.736 24.064-24.672 24.096-41.888V280.16a48.64 48.64 0 0 0-24.16-41.984L536.192 6.496a47.936 47.936 0 0 0-48.224 0z" fill="#339933"/></svg>',
  },
  {
    id: 'python',
    name: 'Python',
    icon: '<svg width="32" height="32" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M366.635 495.628c8.93-1.488 17.86-2.481 26.79-2.481h-7.442 241.613c10.419 0 20.341-1.488 30.264-3.969 44.651-12.403 77.395-52.093 77.395-101.21V185.054c0-57.55-49.116-101.21-107.659-110.636-37.209-5.954-91.287-8.93-128-8.93-36.713 0-71.938 3.473-103.194 8.93C305.116 90.294 288.744 123.534 288.744 185.054v66.48h223.256V288.744H216.31C133.457 288.744 65.984 387.969 65.488 510.016v1.984c0 22.326 1.984 43.659 6.45 63.504C90.294 667.783 147.844 735.256 216.31 735.256h35.225v-106.667c0-62.512 46.636-120.558 115.101-132.961z" fill="#0075AA"/><path d="M949.086 434.108C927.753 349.271 872.683 288.744 807.69 288.744h-35.225v94.76c0 78.884-51.597 135.938-115.101 145.861-6.45 0.992-12.899 1.488-19.349 1.488H396.403c-10.419 0-20.341 1.488-30.264 3.969-44.651 11.907-77.395 48.62-77.395 96.744V834.481c0 57.551 58.047 91.783 115.101 108.155 67.969 19.845 142.388 23.318 224.249 0 54.077-15.38 107.163-46.636 107.163-108.155v-61.52H512.1V735.256h295.691c58.542 0 109.643-49.613 134.449-122.047 10.419-30.264 16.372-64.496 16.372-101.209 0-27.287-3.473-53.582-9.426-77.892z" fill="#FFD400"/></svg>',
  },
  {
    id: 'git',
    name: 'Git',
    icon: '<svg width="32" height="32" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg"><path d="M961.458 482.925c-13.678-14.072-88.557-88.562-170.593-170.016l0.34-0.699L544.76 68.261s-44.158-32.167-77.595 0.198c-8.985 8.698-42.567 42.207-86.868 86.557l108.797 109.458a72.513 72.513 0 0 1 23.23-3.817c40.111 0 72.628 32.517 72.628 72.628a72.431 72.431 0 0 1-3.961 23.655l100.452 101.072a72.443 72.443 0 0 1 25.488-4.611c40.111 0 72.628 32.518 72.628 72.629 0 40.112-32.517 72.629-72.628 72.629s-72.628-32.517-72.628-72.629a72.4 72.4 0 0 1 5.492-27.723l-97.053-97.671v250.96c23.844 12.917 40.038 38.156 40.038 67.179 0 42.168-34.185 76.354-76.353 76.354-42.168 0-76.353-34.186-76.353-76.354 0-30.508 17.898-56.826 43.762-69.056v-254.85c-20.499-12.838-34.142-35.612-34.142-61.584a72.322 72.322 0 0 1 6.435-29.878l-0.227-0.228-107.464-106.231C218.544 317.112 59.749 476.721 59.749 476.721l0.782 0.756-3.222 3.238s-32.28 44.075 0 77.595c13.729 14.259 89.458 90.288 171.954 172.96l-0.554 1.15 81.638 80.065c83 83.104 154.179 154.283 154.179 154.283l1.529-1.573 10.226 10.03s44.307 31.964 77.593-0.558c33.287-32.52 405.521-410.144 405.521-410.144l-0.785-0.753 3.206-3.251c-0.001 0.002 32.074-44.223-0.358-77.594z" fill="#E25034"/></svg>',
  },
  {
    id: 'officecli',
    name: 'OfficeCLI',
    icon: '<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="5" width="26" height="22" rx="3" fill="#2b579a"/><path d="M8 11h16M8 16h16M8 21h10" stroke="#fff" stroke-width="2" stroke-linecap="round" fill="none"/></svg>',
  },
]

async function installRuntime(runtime: string) {
  installing[runtime] = true
  try {
    const res = await fetch(devEnvApi('/api/dev-env/download'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ runtime }),
    })
    const data = await res.json()
    if (!data.success) {
      alert(`安装失败: ${data.error || '未知错误'}`)
    } else {
      await recheck()
    }
  } catch (e: any) {
    alert(`安装失败: ${e.message || '网络错误'}`)
  } finally {
    installing[runtime] = false
  }
}

async function recheck() {
  rechecking.value = true
  try {
    const res = await fetch(devEnvApi('/api/dev-env/missing'))
    const data = await res.json()
    if (data.all_installed) {
      emit('all-installed')
    }
  } catch {
    // ignore
  } finally {
    rechecking.value = false
  }
}
</script>

<style scoped>
.env-check-page {
  position: fixed;
  top: 40px;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 900;
  display: flex;
  flex-direction: column;
  background: var(--boot-bg-image, #f8fafc);
  overflow-y: auto;
}

.env-check-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 560px;
  width: 100%;
  margin: 0 auto;
  padding: 48px 32px;
}

.env-check-title {
  font-size: 24px;
  font-weight: 500;
  color: var(--text);
  margin: 0 0 8px;
}

.env-check-desc {
  font-size: 14px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
  margin: 0 0 32px;
}

.env-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.env-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  background: var(--bg-panel, #fff);
  transition: border-color 0.15s;
}

.env-card.installed {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.04);
}

.env-card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}

.env-card-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.env-card-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--text);
}

.env-card-status {
  font-size: 12px;
}

.env-card-status.ok {
  color: #16a34a;
}

.env-card-status.missing {
  color: #dc2626;
}

.env-install-btn {
  flex-shrink: 0;
  padding: 8px 16px;
  border: 1px solid #2d7a4f;
  border-radius: 8px;
  background: #2d7a4f;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.env-install-btn:hover:not(:disabled) {
  background: #246340;
}

.env-install-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.env-check-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding-top: 32px;
  margin-top: auto;
}

.env-recheck-btn {
  padding: 8px 20px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  background: var(--bg-panel, #fff);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.env-recheck-btn:hover:not(:disabled) {
  background: var(--bg-secondary, #f8fafc);
}

.env-recheck-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.env-skip-btn {
  padding: 8px 20px;
  background: transparent;
  border: none;
  font-size: 13px;
  color: var(--text-muted, #9ca3af);
  cursor: pointer;
}

.env-skip-btn:hover {
  color: var(--text);
}
</style>
