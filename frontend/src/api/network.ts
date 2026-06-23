import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface NetworkConfig {
  enabled: boolean
  proxy_url: string
  proxy_domains: string[]
  proxy_commands: string[]
  command_proxy: boolean
}

export async function getNetworkConfig() {
  const res = await fetch(`${getBaseUrl()}/network/config`)
  if (!res.ok) throw new Error('获取网络配置失败')
  return res.json() as Promise<NetworkConfig>
}

export async function saveNetworkConfig(config: NetworkConfig) {
  const res = await fetch(`${getBaseUrl()}/network/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('保存网络配置失败')
  return res.json() as Promise<{ success: boolean; data: NetworkConfig }>
}

export async function testNetworkProxy() {
  const res = await fetch(`${getBaseUrl()}/network/test`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('测试代理失败')
  return res.json() as Promise<{ success: boolean; status_code?: number; proxy_url?: string; error?: string }>
}
