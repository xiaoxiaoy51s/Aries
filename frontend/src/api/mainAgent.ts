import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface MainAgentConfig {
  allowed_skills: string[]
  allowed_mcps: string[]
}

export async function getMainAgentConfig() {
  const res = await fetch(`${getBaseUrl()}/main-agent/config`)
  if (!res.ok) throw new Error('获取主 Agent 配置失败')
  return res.json() as Promise<MainAgentConfig>
}

export async function saveMainAgentConfig(config: MainAgentConfig) {
  const res = await fetch(`${getBaseUrl()}/main-agent/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('保存主 Agent 配置失败')
  return res.json() as Promise<{ success: boolean; data: MainAgentConfig }>
}
