<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <!-- 左侧导航 -->
        <nav class="modal-nav">
          <div class="modal-nav-header">
            <h1>设置</h1>
          </div>
          <ul class="modal-nav-list">
            <li
              :class="{ active: activeTab === 'models' }"
              @click="activeTab = 'models'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
              模型管理
            </li>
            <li
              :class="{ active: activeTab === 'accounts' }"
              @click="activeTab = 'accounts'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              账号绑定
            </li>
            <li
              :class="{ active: activeTab === 'paths' }"
              @click="activeTab = 'paths'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              路径权限
            </li>
            <li
              :class="{ active: activeTab === 'pets' }"
              @click="activeTab = 'pets'"
            >
              <svg t="1781971061983" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg"
              p-id="3864" width="16" height="16">
              <path d="M636.589292 466.203569c-30.641231-33.988923-74.326646-53.492185-119.855261-53.492184-45.536492
              0-89.221908 19.495385-119.863139 53.492184L183.288123 703.188677c-46.355692 51.436308-55.6032
              124.463262-23.559877 186.045046 31.578585 60.675938 95.586462 94.538831 163.005046 86.244431l194.000739-23.835569
              194.000738 23.835569c6.750523 0.827077 13.469538 1.236677 20.133416 1.236677 59.809477 0 114.467446-32.886154
              142.879507-87.488985 32.043323-61.581785 22.795815-134.600862-23.567754-186.037169L636.589292 466.203569z
              m181.248 393.940677c-15.375754 29.538462-49.569477 58.927262-99.422523 52.791139l-197.844677-24.308185a31.373785
              31.373785 0 0 0-7.687877 0L315.045415 912.935385c-49.845169
              6.104615-84.046769-23.252677-99.422523-52.791139-15.745969-30.255262-20.204308-76.288 14.469908-114.766769l213.582769-236.985108c18.983385-21.062892 44.929969-32.657723 73.050585-32.657723 28.120615 0 54.0672 11.602708 73.050584 32.657723l213.58277 236.985108c34.682092 38.478769 30.215877 84.511508 14.477784 114.766769zM266.531446 364.016246c22.795815 18.660431 48.529723 28.349046 75.019816 28.349046 3.654892 0 7.325538-0.181169 11.004061-0.551384 74.988308-7.546092 126.282831-88.9856 116.791139-185.391262-5.293292-53.736369-28.900431-101.415385-64.779816-130.788431-25.560615-20.936862-56.083692-30.790892-86.031754-27.797661-74.980431 7.546092-126.282831 88.9856-116.791138 185.391261 5.301169 53.736369 28.908308 101.407508 64.787692 130.788431z m58.320739-253.487261c1.504492-0.157538 2.985354-0.220554 4.442584-0.220554 14.871631 0 27.277785 7.467323 35.351631 14.076061 22.677662 18.573785 38.376369 51.546585 41.984 88.213662 5.8368 59.273846-21.819077 112.632123-60.392369 116.515446-16.832985 1.693538-30.932677-6.592985-39.786339-13.847631-22.685538-18.573785-38.384246-51.546585-41.991877-88.213661-5.8368-59.281723 21.819077-112.64 60.39237-116.523323zM653.501046 391.806031c3.528862 0.354462 7.057723 0.527754 10.594462 0.527754 26.442831 0 52.877785-9.854031 75.429415-28.325416 35.871508-29.373046 59.486523-77.044185 64.779815-130.788431 9.491692-96.405662-41.810708-177.845169-116.791138-185.391261-30.286769-3.040492-60.085169 6.561477-86.023877 27.789785-35.879385 29.373046-59.486523 77.052062-64.787692 130.78843-9.483815 96.421415 41.818585 177.853046 116.799015 185.399139z m-54.082954-179.215754c3.607631-36.6592 19.306338-69.639877 41.991877-88.213662 8.861538-7.254646 22.992738-15.588431 39.786339-13.84763 38.573292 3.883323 66.229169 57.2416 60.392369 116.515446-3.607631 36.6592-19.306338 69.639877-41.984 88.213661-8.861538 7.254646-23.008492 15.556923-39.786339 13.847631-38.573292-3.875446-66.237046-57.2416-60.400246-116.515446zM231.077415 464.652985c0-3.387077 2.091323-6.411938 5.258547-7.585723 3.159385-1.181662 6.711138-.252062 8.916677 2.327877l30.829661 36.144246c2.835569 3.330954 4.419077 7.538215 4.419077 11.884308 0 4.353969-1.583508 8.561231-4.419077 11.892185l-30.829661 36.144246c-2.205539 2.579938-5.757292 3.509538-8.916677 2.327876-3.167224-1.173784-5.258547-4.198646-5.258547-7.585722v-85.049293z"
              fill="currentColor"></path>
              </svg>
              桌面宠物
            </li>
            <li
              :class="{ active: activeTab === 'network' }"
              @click="activeTab = 'network'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="2" y1="12" x2="22" y2="12"/>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
              </svg>
              网络代理
            </li>
            <li
              :class="{ active: activeTab === 'dev-env' }"
              @click="activeTab = 'dev-env'"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6"/>
                <polyline points="8 6 2 12 8 18"/>
              </svg>
              开发环境
            </li>
          </ul>
        </nav>

        <!-- 右侧内容 -->
        <div class="modal-body">
          <div class="modal-body-header">
            <h2>{{ tabTitle }}</h2>
            <button type="button" class="close-btn" @click="$emit('close')">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div class="modal-body-content">
            <ModelsTab v-if="activeTab === 'models'" />
            <AccountsTab v-else-if="activeTab === 'accounts'" />
            <PathsTab v-else-if="activeTab === 'paths'" />
            <PetsTab v-else-if="activeTab === 'pets'" />
            <NetworkTab v-else-if="activeTab === 'network'" />
            <DevEnvTab v-else-if="activeTab === 'dev-env'" />
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ModelsTab from './tabs/ModelsTab.vue'
import AccountsTab from './tabs/AccountsTab.vue'
import PathsTab from './tabs/PathsTab.vue'
import PetsTab from './tabs/PetsTab.vue'
import NetworkTab from './tabs/NetworkTab.vue'
import DevEnvTab from './tabs/DevEnvTab.vue'

defineProps<{ visible: boolean }>()
defineEmits<{ close: [] }>()

const activeTab = ref<'models' | 'accounts' | 'paths' | 'pets' | 'network' | 'dev-env'>('models')

const tabTitle = computed(() => {
  const map = {
    models: '模型管理',
    accounts: '账号绑定',
    paths: '路径权限',
    pets: '桌面宠物',
    network: '网络代理',
    'dev-env': '开发环境',
  } as const
  return map[activeTab.value]
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  display: flex;
  width: min(1080px, 92vw);
  height: min(720px, 86vh);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

/* 左侧导航 */
.modal-nav {
  width: 180px;
  min-width: 180px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0;
}

.modal-nav-header {
  padding: 0 20px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.modal-nav-header h1 {
  font-size: 18px;
  font-weight: 600;
}

.modal-nav-list {
  list-style: none;
  margin: 0;
  padding: 4px 8px;
}

.modal-nav-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-nav-list li:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-nav-list li.active {
  background: var(--accent-active);
  color: var(--text);
  font-weight: 500;
}

.modal-nav-list li svg {
  flex-shrink: 0;
}

/* 右侧内容 */
.modal-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.modal-body-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  flex-shrink: 0;
}

.modal-body-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--accent-hover);
  color: var(--text);
}

.modal-body-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
}
</style>
