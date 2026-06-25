<template>
  <div class="settings-section">
    <p class="section-desc">配置代理服务器。AI 搜索、爬虫、npm/git 等操作访问匹配的域名或命令时自动走代理。</p>

    <!-- 启用开关 -->
    <div class="network-toggle-row">
      <div class="network-toggle-info">
        <span class="network-toggle-label">启用代理</span>
        <span class="network-toggle-hint">开启后，下方域名和命令将走代理访问</span>
      </div>
      <button
        type="button"
        class="network-switch"
        :class="{ on: networkConfig.enabled }"
        @click="networkConfig.enabled = !networkConfig.enabled"
      >
        <span class="network-switch-knob" />
      </button>
    </div>

    <!-- 代理地址 -->
    <div class="network-field">
      <label class="form-label">代理地址</label>
      <input
        v-model="networkConfig.proxy_url"
        type="text"
        class="form-input"
        placeholder="http://127.0.0.1:7890"
        :disabled="!networkConfig.enabled"
      />
    </div>

    <!-- 命令行代理开关 -->
    <div class="network-toggle-row">
      <div class="network-toggle-info">
        <span class="network-toggle-label">命令行代理</span>
        <span class="network-toggle-hint">npm install / git clone 等命令也注入代理环境变量</span>
      </div>
      <button
        type="button"
        class="network-switch"
        :class="{ on: networkConfig.command_proxy }"
        :disabled="!networkConfig.enabled"
        @click="networkConfig.command_proxy = !networkConfig.command_proxy"
      >
        <span class="network-switch-knob" />
      </button>
    </div>

    <!-- 代理域名列表 -->
    <div class="network-field">
      <label class="form-label">代理域名</label>
      <span class="network-field-hint">访问这些域名时走代理（子域名自动匹配，如 google.com 包含 www.google.com）</span>
      <div class="network-tag-input">
        <input
          v-model="networkDomainInput"
          type="text"
          class="form-input network-tag-input-field"
          placeholder="输入域名后回车，如 google.com"
          :disabled="!networkConfig.enabled"
          @keydown.enter.prevent="addNetworkDomain"
        />
        <button
          type="button"
          class="network-tag-add-btn"
          :disabled="!networkConfig.enabled || !networkDomainInput.trim()"
          @click="addNetworkDomain"
        >添加</button>
      </div>
      <div class="network-tag-list">
        <span
          v-for="(d, i) in networkConfig.proxy_domains"
          :key="'d' + i"
          class="network-tag"
        >
          {{ d }}
          <button
            type="button"
            class="network-tag-remove"
            :disabled="!networkConfig.enabled"
            @click="removeNetworkDomain(i)"
          >&times;</button>
        </span>
        <span v-if="networkConfig.proxy_domains.length === 0" class="network-tag-empty">暂无域名</span>
      </div>
    </div>

    <!-- 代理命令列表 -->
    <div class="network-field">
      <label class="form-label">代理命令</label>
      <span class="network-field-hint">以这些前缀开头的命令会注入代理环境变量</span>
      <div class="network-tag-input">
        <input
          v-model="networkCommandInput"
          type="text"
          class="form-input network-tag-input-field"
          placeholder="输入命令前缀后回车，如 npm install"
          :disabled="!networkConfig.enabled || !networkConfig.command_proxy"
          @keydown.enter.prevent="addNetworkCommand"
        />
        <button
          type="button"
          class="network-tag-add-btn"
          :disabled="!networkConfig.enabled || !networkConfig.command_proxy || !networkCommandInput.trim()"
          @click="addNetworkCommand"
        >添加</button>
      </div>
      <div class="network-tag-list">
        <span
          v-for="(c, i) in networkConfig.proxy_commands"
          :key="'c' + i"
          class="network-tag"
        >
          {{ c }}
          <button
            type="button"
            class="network-tag-remove"
            :disabled="!networkConfig.enabled || !networkConfig.command_proxy"
            @click="removeNetworkCommand(i)"
          >&times;</button>
        </span>
        <span v-if="networkConfig.proxy_commands.length === 0" class="network-tag-empty">暂无命令</span>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="network-actions">
      <button
        type="button"
        class="network-test-btn"
        :disabled="!networkConfig.enabled || networkTesting"
        @click="handleTestProxy"
      >{{ networkTesting ? '测试中...' : '测试代理' }}</button>
      <button
        type="button"
        class="form-submit-btn"
        :disabled="networkSaving"
        @click="handleSaveNetwork"
      >{{ networkSaving ? '保存中...' : '保存配置' }}</button>
    </div>

    <!-- 测试结果 -->
    <div v-if="networkTestResult" class="network-test-result" :class="{ success: networkTestResult.success, fail: !networkTestResult.success }">
      {{ networkTestResult.success ? '代理可用' : '代理不可用' }}{{ networkTestResult.error ? '：' + networkTestResult.error : '' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getNetworkConfig, saveNetworkConfig, testNetworkProxy, type NetworkConfig } from '@/api/network'

const networkConfig = ref<NetworkConfig>({
  enabled: false,
  proxy_url: 'http://127.0.0.1:7890',
  proxy_domains: [],
  proxy_commands: [],
  command_proxy: true,
})
const networkDomainInput = ref('')
const networkCommandInput = ref('')
const networkSaving = ref(false)
const networkTesting = ref(false)
const networkTestResult = ref<{ success: boolean; error?: string } | null>(null)

async function loadNetworkConfig() {
  try {
    const data = await getNetworkConfig()
    networkConfig.value = {
      enabled: data.enabled ?? false,
      proxy_url: data.proxy_url || 'http://127.0.0.1:7890',
      proxy_domains: data.proxy_domains || [],
      proxy_commands: data.proxy_commands || [],
      command_proxy: data.command_proxy ?? true,
    }
    networkTestResult.value = null
  } catch (e) {
    console.error('加载网络配置失败', e)
  }
}

function addNetworkDomain() {
  const val = networkDomainInput.value.trim().toLowerCase()
  if (!val) return
  if (networkConfig.value.proxy_domains.includes(val)) {
    networkDomainInput.value = ''
    return
  }
  networkConfig.value.proxy_domains.push(val)
  networkDomainInput.value = ''
}

function removeNetworkDomain(idx: number) {
  networkConfig.value.proxy_domains.splice(idx, 1)
}

function addNetworkCommand() {
  const val = networkCommandInput.value.trim()
  if (!val) return
  if (networkConfig.value.proxy_commands.includes(val)) {
    networkCommandInput.value = ''
    return
  }
  networkConfig.value.proxy_commands.push(val)
  networkCommandInput.value = ''
}

function removeNetworkCommand(idx: number) {
  networkConfig.value.proxy_commands.splice(idx, 1)
}

async function handleSaveNetwork() {
  networkSaving.value = true
  try {
    await saveNetworkConfig({ ...networkConfig.value })
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    networkSaving.value = false
  }
}

async function handleTestProxy() {
  networkTesting.value = true
  networkTestResult.value = null
  try {
    await saveNetworkConfig({ ...networkConfig.value })
    const res = await testNetworkProxy()
    networkTestResult.value = { success: res.success, error: res.error }
  } catch (e: any) {
    networkTestResult.value = { success: false, error: e.message || '测试失败' }
  } finally {
    networkTesting.value = false
  }
}

onMounted(() => {
  loadNetworkConfig()
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

.network-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.network-toggle-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.network-toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.network-toggle-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.network-switch {
  position: relative;
  width: 40px;
  height: 22px;
  background: var(--border-strong, #ccc);
  border: none;
  border-radius: 11px;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}

.network-switch.on {
  background: #2d7a4f;
}

.network-switch:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.network-switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.network-switch.on .network-switch-knob {
  transform: translateX(18px);
}

.network-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.network-field-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: var(--border-strong);
}

.form-input:disabled {
  opacity: 0.5;
}

.network-tag-input {
  display: flex;
  gap: 6px;
}

.network-tag-input-field {
  flex: 1;
}

.network-tag-add-btn {
  padding: 8px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
}

.network-tag-add-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.network-tag-add-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.network-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.network-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--accent-hover);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text);
}

.network-tag-remove {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
}

.network-tag-remove:hover {
  color: #ef4444;
}

.network-tag-empty {
  font-size: 12px;
  color: var(--text-muted);
}

.network-actions {
  display: flex;
  gap: 8px;
}

.network-test-btn {
  padding: 8px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.network-test-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.network-test-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.form-submit-btn {
  padding: 8px 16px;
  background: #2d7a4f;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.form-submit-btn:hover { opacity: 0.9; }
.form-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.network-test-result {
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.network-test-result.success {
  background: rgba(45, 122, 79, 0.1);
  color: #2d7a4f;
}

.network-test-result.fail {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
</style>
