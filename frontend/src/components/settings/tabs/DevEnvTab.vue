<template>
  <div class="settings-section">
    <p class="section-desc">检测和管理 Node.js、Python、Git 运行时，可下载内置版本或切换系统 / 本地路径。</p>

    <div v-if="loading" class="path-empty">检测中...</div>
    <div v-else-if="detected" class="path-empty" style="color: #52c41a;">检测成功</div>

    <!-- Node.js -->
    <div class="dev-env-card">
      <div class="dev-env-card-main">
        <div class="dev-env-card-header">
          <div class="dev-env-icon node">
            <svg t="1782390051279" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="11587" width="40" height="40"><path d="M487.904 6.528L88.128 238.208a48.32 48.32 0 0 0-24.032 41.952V743.68c0 17.248 9.184 33.28 24.064 41.888l399.776 231.904c14.944 8.672 33.28 8.672 48.224 0l399.616-231.808c14.944-8.736 24.064-24.672 24.096-41.888V280.16a48.64 48.64 0 0 0-24.16-41.984L536.192 6.496a47.936 47.936 0 0 0-48.224 0z" fill="#339933" p-id="11588"></path></svg>
          </div>
          <div class="dev-env-info">
            <span class="dev-env-name">Node.js</span>
            <span v-if="devEnv.node?.resolved?.source !== 'none'" class="dev-env-version">{{ devEnv.node?.resolved?.version }}</span>
          </div>
        </div>
        <div class="dev-env-status">
          <div v-if="devEnv.node?.resolved?.source !== 'none'" class="dev-env-status-row">
            <span class="dev-env-badge" :class="devEnv.node?.resolved?.source">{{ sourceLabel(devEnv.node?.resolved?.source) }}</span>
            <span class="dev-env-path">{{ devEnv.node?.resolved?.path }}</span>
          </div>
          <div v-else class="dev-env-status-row">
            <span class="dev-env-badge none">未安装</span>
          </div>
        </div>
      </div>
      <div class="dev-env-actions">
        <button
          type="button"
          class="dev-env-download-btn"
          @click="openDownloadModal('node')"
        >下载内置版本</button>
        <button
          type="button"
          class="dev-env-switch-btn"
          @click="openSwitchModal('node')"
        >切换版本</button>
        <button
          type="button"
          class="dev-env-redetect-btn"
          :disabled="downloading.node"
          @click="loadDevEnv"
        >重新检测</button>
      </div>
    </div>

    <!-- Python -->
    <div class="dev-env-card">
      <div class="dev-env-card-main">
        <div class="dev-env-card-header">
          <div class="dev-env-icon python">
            <svg t="1782390087522" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="12696" width="40" height="40"><path d="M366.635375 495.627875c8.93024999-1.488375 17.8605-2.480625 26.79075-2.48062499h-7.44187499 241.61287499c10.418625 0 20.341125-1.488375 30.26362501-3.969 44.65124999-12.403125 77.3955-52.093125 77.3955-101.20950002V185.053625c0-57.5505-49.116375-101.2095-107.65912501-110.63587501-37.209375-5.9535-91.287-8.93024999-128.00025-8.93024999-36.71325001 0-71.938125 3.472875-103.194 8.93024999C305.115875 90.29374999 288.74374999 123.534125 288.74374999 185.053625v66.48075h223.25625001V288.74374999H216.3095C133.456625 288.74374999 65.983625 387.96874999 65.4875 510.0155v1.9845c0 22.325625 1.9845 43.659 6.449625 63.504C90.29374999 667.78325001 147.84424999 735.25625001 216.3095 735.25625001h35.224875v-106.66687501c0-62.51174999 46.63574999-120.558375 115.101-132.9615z m23.814-283.7835c-22.325625 0-40.68225001-18.356625-40.18612499-40.68225 0-22.325625 17.8605-40.68225001 40.18612499-40.68225s40.68225001 18.356625 40.68225 40.68225c-0.496125 22.82175001-18.356625 40.68225001-40.68225 40.68225z" fill="#0075AA" p-id="12697"></path><path d="M949.086125 434.108375C927.75275001 349.271 872.682875 288.74374999 807.6905 288.74374999h-35.224875v94.75987501c0 78.883875-51.597 135.93825001-115.101 145.86075-6.449625 0.99224999-12.89925001 1.488375-19.34887499 1.48837501H396.402875c-10.418625 0-20.341125 1.488375-30.26362499 3.969-44.65124999 11.907-77.3955 48.62025001-77.3955 96.74437499V834.48125001c0 57.5505 58.046625 91.783125 115.10099998 108.15524999 67.969125 19.845 142.387875 23.317875 224.24850002 0 54.077625-15.379875 107.163-46.63574999 107.16299998-108.15525001v-61.5195h-223.25624999V735.25625001h295.6905c58.54275001 0 109.643625-49.6125 134.449875-122.04675001 10.418625-30.263625 16.372125-64.49625001 16.372125-101.2095 0-27.286875-3.472875-53.5815-9.426375-77.891625z m-316.52775 372.58987501c22.325625 0 40.186125 18.356625 40.186125 40.68224999 0 22.325625-18.356625 40.68225001-40.186125 40.68225001-22.325625 0-40.68225001-18.356625-40.68225-40.68225001 0.496125-22.325625 18.356625-40.68225001 40.68225-40.68225001z" fill="#FFD400" p-id="12698"></path></svg>
          </div>
          <div class="dev-env-info">
            <span class="dev-env-name">Python</span>
            <span v-if="devEnv.python?.resolved?.source !== 'none'" class="dev-env-version">{{ devEnv.python?.resolved?.version }}</span>
          </div>
        </div>
        <div class="dev-env-status">
          <div v-if="devEnv.python?.resolved?.source !== 'none'" class="dev-env-status-row">
            <span class="dev-env-badge" :class="devEnv.python?.resolved?.source">{{ sourceLabel(devEnv.python?.resolved?.source) }}</span>
            <span class="dev-env-path">{{ devEnv.python?.resolved?.path }}</span>
          </div>
          <div v-else class="dev-env-status-row">
            <span class="dev-env-badge none">未安装</span>
          </div>
        </div>
      </div>
      <div class="dev-env-actions">
        <button
          type="button"
          class="dev-env-download-btn"
          @click="openDownloadModal('python')"
        >下载内置版本</button>
        <button
          type="button"
          class="dev-env-switch-btn"
          @click="openSwitchModal('python')"
        >切换版本</button>
        <button
          type="button"
          class="dev-env-redetect-btn"
          :disabled="downloading.python"
          @click="loadDevEnv"
        >重新检测</button>
      </div>
    </div>

    <!-- Git -->
    <div class="dev-env-card">
      <div class="dev-env-card-main">
        <div class="dev-env-card-header">
          <div class="dev-env-icon git">
            <svg t="1782390150270" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="18374" width="40" height="40"><path d="M961.458 482.925c-13.678-14.072-88.557-88.562-170.593-170.016l0.34-0.699L544.76 68.261s-44.158-32.167-77.595 0.198c-8.985 8.698-42.567 42.207-86.868 86.557l108.797 109.458a72.513 72.513 0 0 1 23.23-3.817c40.111 0 72.628 32.517 72.628 72.628a72.431 72.431 0 0 1-3.961 23.655l100.452 101.072a72.443 72.443 0 0 1 25.488-4.611c40.111 0 72.628 32.518 72.628 72.629 0 40.112-32.517 72.629-72.628 72.629s-72.628-32.517-72.628-72.629a72.4 72.4 0 0 1 5.492-27.723l-97.053-97.671v250.96c23.844 12.917 40.038 38.156 40.038 67.179 0 42.168-34.185 76.354-76.353 76.354-42.168 0-76.353-34.186-76.353-76.354 0-30.508 17.898-56.826 43.762-69.056v-254.85c-20.499-12.838-34.142-35.612-34.142-61.584a72.322 72.322 0 0 1 6.435-29.878l-0.227-0.228-107.464-106.231C218.544 317.112 59.749 476.721 59.749 476.721l0.782 0.756-3.222 3.238s-32.28 44.075 0 77.595c13.729 14.259 89.458 90.288 171.954 172.96l-0.554 1.15 81.638 80.065c83 83.104 154.179 154.283 154.179 154.283l1.529-1.573 10.226 10.03s44.307 31.964 77.593-0.558c33.287-32.52 405.521-410.144 405.521-410.144l-0.785-0.753 3.206-3.251c-0.001 0.002 32.074-44.223-0.358-77.594z" fill="#E25034" p-id="18375"></path></svg>
          </div>
          <div class="dev-env-info">
            <span class="dev-env-name">Git</span>
            <span v-if="devEnv.git?.resolved?.source !== 'none'" class="dev-env-version">{{ devEnv.git?.resolved?.version }}</span>
          </div>
        </div>
        <div class="dev-env-status">
          <div v-if="devEnv.git?.resolved?.source !== 'none'" class="dev-env-status-row">
            <span class="dev-env-badge" :class="devEnv.git?.resolved?.source">{{ sourceLabel(devEnv.git?.resolved?.source) }}</span>
            <span class="dev-env-path">{{ devEnv.git?.resolved?.path }}</span>
          </div>
          <div v-else class="dev-env-status-row">
            <span class="dev-env-badge none">未安装</span>
          </div>
        </div>
      </div>
      <div class="dev-env-actions">
        <button
          type="button"
          class="dev-env-download-btn"
          @click="openDownloadModal('git')"
        >下载内置版本</button>
        <button
          type="button"
          class="dev-env-switch-btn"
          @click="openSwitchModal('git')"
        >切换版本</button>
        <button
          type="button"
          class="dev-env-redetect-btn"
          :disabled="downloading.git"
          @click="loadDevEnv"
        >重新检测</button>
      </div>
    </div>

    <!-- 下载弹窗 -->
    <div v-if="downloadModalVisible" class="modal-overlay" @click.self="closeDownloadModal">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">下载 {{ runtimeNames[downloadModalRuntime] }} SDK</div>
        <div class="modal-body">
          <div class="form-field">
            <label class="form-label">版本</label>
            <select v-model="downloadModalVersion" class="form-input">
              <option v-for="opt in devEnv[downloadModalRuntime]?.download?.versions || []" :key="opt.version" :value="opt.version">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label">位置</label>
            <input v-model="downloadModalPath" type="text" class="form-input" readonly />
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="closeDownloadModal">取消</button>
          <button
            class="modal-btn modal-btn-primary"
            :disabled="downloading[downloadModalRuntime]"
            @click="confirmDownload"
          >{{ downloading[downloadModalRuntime] ? '安装中...' : '安装' }}</button>
        </div>
      </div>
    </div>

    <!-- 切换版本弹窗 -->
    <div v-if="switchModalVisible" class="modal-overlay" @click.self="closeSwitchModal">
      <div class="modal-dialog" @click.stop>
        <div class="modal-header">切换 {{ runtimeNames[switchModalRuntime] }} 版本</div>
        <div class="modal-body">
          <div class="switch-options">
            <!-- 只显示当前在用的环境 -->
            <label
              v-if="switchSelected === 'system'"
              class="switch-option active"
            >
              <input v-model="switchSelected" type="radio" value="system" />
              <div class="switch-option-info">
                <span class="switch-option-name">系统已安装</span>
                <span class="switch-option-path">{{ devEnv[switchModalRuntime]?.system?.path }}</span>
              </div>
            </label>

            <label
              v-if="switchSelected.startsWith('builtin-')"
              class="switch-option active"
            >
              <input v-model="switchSelected" type="radio" :value="switchSelected" />
              <div class="switch-option-info">
                <span class="switch-option-name">内置版本 {{ switchSelected.replace('builtin-', '') }}</span>
                <span class="switch-option-path">{{ getCurrentBuiltinPath() }}</span>
              </div>
            </label>

            <label
              v-if="switchSelected === 'custom'"
              class="switch-option active"
            >
              <input v-model="switchSelected" type="radio" value="custom" />
              <div class="switch-option-info">
                <span class="switch-option-name">本地路径</span>
                <span class="switch-option-path">{{ switchCustomPath || devEnv[switchModalRuntime]?.resolved?.path }}</span>
              </div>
            </label>

            <!-- 未检测到环境时提示 -->
            <div v-if="!switchSelected" class="path-empty">当前未检测到可用环境</div>
          </div>
          <div v-if="switchSelected === 'custom'" class="form-field">
            <label class="form-label">可执行文件路径</label>
            <div class="custom-path-input">
              <input v-model="switchCustomPath" type="text" class="form-input" placeholder="如 C:\Program Files\nodejs\node.exe" />
              <button type="button" class="modal-btn modal-btn-cancel" @click="selectCustomTarget('file')">选文件</button>
              <button type="button" class="modal-btn modal-btn-cancel" @click="selectCustomTarget('folder')">选文件夹</button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-btn-cancel" @click="closeSwitchModal">取消</button>
          <button
            class="modal-btn modal-btn-primary"
            :disabled="!switchSelected || (switchSelected === 'custom' && !switchCustomPath) || switching[switchModalRuntime]"
            @click="confirmSwitch"
          >{{ switching[switchModalRuntime] ? '切换中...' : '切换' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive, watch } from 'vue'
import { selectDirectory } from '@/api/system'
import { useModelStore } from '@/stores/model'

const modelStore = useModelStore()
function devEnvApi(path: string) {
  return `${modelStore.getBaseUrl()}${path}`
}

interface DevEnvVersionOption {
  version: string
  label: string
}

interface DevEnvRuntimeInfo {
  installed: boolean
  version: string
  path: string
}

interface DevEnvBuiltinInfo {
  installed: boolean
  version: string
  path: string
}

interface DevEnvRuntime {
  resolved: {
    source: 'system' | 'builtin' | 'env' | 'none'
    version: string
    path: string
  }
  system?: DevEnvRuntimeInfo
  builtin?: DevEnvBuiltinInfo
  builtins?: { version: string; path: string }[]
  download?: {
    version: string
    versions: DevEnvVersionOption[]
    default_install_dir: string
    available: boolean
  }
}

interface DevEnvInfo {
  node: DevEnvRuntime | null
  python: DevEnvRuntime | null
  git: DevEnvRuntime | null
}

const devEnv = ref<DevEnvInfo>({ node: null, python: null, git: null })
const loading = ref(false)
const detected = ref(false)
const downloading = reactive({ node: false, python: false, git: false })
const switching = reactive({ node: false, python: false, git: false })

const downloadModalVisible = ref(false)
const downloadModalRuntime = ref<'node' | 'python' | 'git'>('node')
const downloadModalVersion = ref('')
const downloadModalPath = ref('')

const switchModalVisible = ref(false)
const switchModalRuntime = ref<'node' | 'python' | 'git'>('node')
const switchSelected = ref('')
const switchCustomPath = ref('')

const runtimeNames = {
  node: 'Node.js',
  python: 'Python',
  git: 'Git',
} as const

function sourceLabel(source: 'system' | 'builtin' | 'env' | 'none' | undefined) {
  if (source === 'system') return '系统'
  if (source === 'builtin') return '内置'
  if (source === 'env') return '已配置'
  return ''
}

function getCurrentBuiltinPath() {
  const info = devEnv.value[switchModalRuntime.value]
  if (!info) return ''
  const version = switchSelected.value.replace('builtin-', '')
  const builtin = info.builtins?.find(b => b.version === version)
  return builtin?.path || info.builtin?.path || ''
}

function openDownloadModal(runtime: 'node' | 'python' | 'git') {
  downloadModalRuntime.value = runtime
  const info = devEnv.value[runtime]
  const defaultVersion = info?.download?.version || ''
  downloadModalVersion.value = defaultVersion
  downloadModalPath.value = info?.download?.default_install_dir || ''
  downloadModalVisible.value = true
}

function closeDownloadModal() {
  downloadModalVisible.value = false
}

watch(downloadModalVersion, (version) => {
  if (!version) return
  const runtime = downloadModalRuntime.value
  const info = devEnv.value[runtime]
  if (!info?.download) return
  const baseDir = info.download.default_install_dir.replace(/\\[^\\]+$/, '')
  downloadModalPath.value = `${baseDir}\\${version}`
})

function openSwitchModal(runtime: 'node' | 'python' | 'git') {
  switchModalRuntime.value = runtime
  switchCustomPath.value = ''
  const info = devEnv.value[runtime]
  const resolved = info?.resolved
  if (resolved?.source === 'system') {
    switchSelected.value = 'system'
  } else if (resolved?.source === 'builtin' && info?.builtin?.installed) {
    switchSelected.value = `builtin-${info.builtin.version}`
  } else if (resolved?.source === 'env') {
    switchSelected.value = 'custom'
    switchCustomPath.value = resolved.path
  } else {
    switchSelected.value = ''
  }
  switchModalVisible.value = true
}

function closeSwitchModal() {
  switchModalVisible.value = false
}

async function selectCustomTarget(mode: 'file' | 'folder') {
  try {
    const electronAPI = (window as any).electronAPI
    const runtime = switchModalRuntime.value

    // 优先使用 Electron 原生对话框
    if (electronAPI?.selectDirectory && mode === 'folder') {
      const result = await electronAPI.selectDirectory({
        title: `选择 ${runtimeNames[runtime]} 运行时目录`,
      })
      if (!result.cancelled && result.path) {
        switchCustomPath.value = result.path
      }
      return
    }
    if (electronAPI?.selectFile && mode === 'file') {
      const result = await electronAPI.selectFile({
        title: `选择 ${runtimeNames[runtime]} 可执行文件`,
        filters: getFileFilters(runtime),
      })
      if (!result.cancelled && result.path) {
        switchCustomPath.value = result.path
      }
      return
    }

    // 回退到后端 API（只能选文件夹）
    const result = await selectDirectory()
    if (result.cancelled || !result.path) return
    switchCustomPath.value = result.path
  } catch (e: any) {
    alert(e.message || '选择失败')
  }
}

function getFileFilters(runtime: 'node' | 'python' | 'git') {
  if (runtime === 'node') return [{ name: 'Node.js', extensions: ['exe'] }]
  if (runtime === 'python') return [{ name: 'Python', extensions: ['exe'] }]
  if (runtime === 'git') return [{ name: 'Git', extensions: ['exe'] }]
  return undefined
}

async function loadDevEnv() {
  loading.value = true
  try {
    const res = await fetch(devEnvApi('/api/dev-env/detect'))
    const data = await res.json()
    devEnv.value = {
      node: data.node ?? null,
      python: data.python ?? null,
      git: data.git ?? null,
    }
    detected.value = true
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function confirmDownload() {
  const runtime = downloadModalRuntime.value
  downloading[runtime] = true
  try {
    const res = await fetch(devEnvApi('/api/dev-env/download'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runtime,
        version: downloadModalVersion.value,
        install_dir: downloadModalPath.value,
      }),
    })
    const data = await res.json()
    if (!data.success) {
      alert(`安装失败: ${data.error || '未知错误'}`)
    } else {
      closeDownloadModal()
      await loadDevEnv()
    }
  } catch (e: any) {
    alert(`安装失败: ${e.message || '网络错误'}`)
  } finally {
    downloading[runtime] = false
  }
}

async function confirmSwitch() {
  const runtime = switchModalRuntime.value
  switching[runtime] = true
  try {
    let body: any = { runtime }
    if (switchSelected.value === 'system') {
      body.source = 'system'
    } else if (switchSelected.value.startsWith('builtin-')) {
      body.source = 'builtin'
      body.version = switchSelected.value.replace('builtin-', '')
    } else if (switchSelected.value === 'custom') {
      body.source = 'env'
      body.path = switchCustomPath.value
      // 如果用户只选了目录，自动补全到可执行文件
      if (runtime === 'node' && !body.path.toLowerCase().endsWith('node.exe')) {
        body.path = body.path.replace(/\\+$/, '') + '\\node.exe'
      } else if (runtime === 'python' && !body.path.toLowerCase().endsWith('python.exe')) {
        body.path = body.path.replace(/\\+$/, '') + '\\python.exe'
      } else if (runtime === 'git' && !body.path.toLowerCase().endsWith('git.exe')) {
        body.path = body.path.replace(/\\+$/, '') + '\\cmd\\git.exe'
      }
    }
    const res = await fetch(devEnvApi('/api/dev-env/switch'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!data.success) {
      alert(`切换失败: ${data.error || '未知错误'}`)
    } else {
      closeSwitchModal()
      await loadDevEnv()
      // 提示用户重启以使新环境生效
      const shouldRestart = confirm('运行时环境已切换，需要重启软件才能完全生效。\n\n是否立即重启？')
      if (shouldRestart) {
        // 通过 Electron 重启应用
        const electronAPI = (window as any).electronAPI
        if (electronAPI?.relaunch) {
          electronAPI.relaunch()
        } else {
          // 非 Electron 环境，提示用户手动刷新
          window.location.reload()
        }
      }
    }
  } catch (e: any) {
    alert(`切换失败: ${e.message || '网络错误'}`)
  } finally {
    switching[runtime] = false
  }
}

onMounted(() => {
  loadDevEnv()
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

.path-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 12px;
}

.dev-env-card {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 16px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.dev-env-card-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.dev-env-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dev-env-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  flex-shrink: 0;
}

.dev-env-icon.node {
  background: rgba(104, 160, 99, 0.15);
  color: #68a063;
}

.dev-env-icon.python {
  background: rgba(55, 118, 171, 0.15);
  color: #3776ab;
}

.dev-env-icon.git {
  background: rgba(240, 80, 50, 0.15);
  color: #f05032;
}

.dev-env-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dev-env-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.dev-env-version {
  font-size: 12px;
  color: var(--text-muted);
}

.dev-env-status {
  min-height: 24px;
}

.dev-env-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dev-env-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  flex-shrink: 0;
}

.dev-env-badge.system {
  background: rgba(45, 122, 79, 0.15);
  color: #2d7a4f;
}

.dev-env-badge.builtin {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.dev-env-badge.env {
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
}

.dev-env-badge.none {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.dev-env-path {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-all;
}

.dev-env-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
  min-width: 140px;
  flex-shrink: 0;
}

.dev-env-download-btn {
  padding: 10px 16px;
  background: var(--send-bg, #1f2937);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.dev-env-download-btn:hover {
  opacity: 0.9;
}

.dev-env-switch-btn {
  padding: 10px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.dev-env-switch-btn:hover {
  background: var(--accent-hover);
}

.dev-env-redetect-btn {
  padding: 10px 16px;
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text);
  cursor: pointer;
  transition: all 0.15s;
}

.dev-env-redetect-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.dev-env-redetect-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 弹窗 */
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
  width: 420px;
  max-width: 90vw;
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
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
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

.custom-path-input {
  display: flex;
  gap: 8px;
}

.custom-path-input .form-input {
  flex: 1;
}

.modal-footer {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--border);
}

.modal-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.modal-btn:hover {
  opacity: 0.85;
}

.modal-btn-cancel {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
}

.modal-btn-primary {
  background: var(--send-bg, #1f2937);
  color: #fff;
}

/* 切换版本选项 */
.switch-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.switch-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.switch-option:hover {
  background: var(--accent-hover);
}

.switch-option.active {
  border-color: var(--send-bg, #1f2937);
  background: rgba(31, 41, 55, 0.06);
}

.switch-option input {
  margin-top: 3px;
}

.switch-option-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.switch-option-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.switch-option-path {
  font-size: 12px;
  color: var(--text-muted);
  word-break: break-all;
}
</style>
