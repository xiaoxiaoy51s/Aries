import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export interface PlatformStatus {
  platform: string
  name: string
  enabled: boolean
  running: boolean
  configured: boolean
}

export interface ActivePlatform {
  platform: string
  name: string
  session_id: string
}

export interface QQConfigRequest {
  enabled: boolean
  app_id: string
  app_secret: string
  mode: string
  work_dir?: string
  system_prompt?: string
}

export interface FeishuConfigRequest {
  enabled: boolean
  app_id: string
  app_secret: string
  mode: string
  work_dir?: string
  system_prompt?: string
}

export interface WeChatConfigRequest {
  enabled: boolean
  mode: string
  work_dir?: string
  system_prompt?: string
}

// ---------- 列表与状态 ----------

export async function listActivePlatforms(): Promise<{ platforms: ActivePlatform[] }> {
  const res = await fetch(`${getBaseUrl()}/platforms/active`)
  if (!res.ok) throw new Error('获取活跃平台列表失败')
  return res.json()
}

export async function listPlatforms(): Promise<{ platforms: PlatformStatus[] }> {
  const res = await fetch(`${getBaseUrl()}/platforms/`)
  if (!res.ok) throw new Error('获取平台列表失败')
  return res.json()
}

export async function getPlatform(platform: string) {
  const res = await fetch(`${getBaseUrl()}/platforms/${platform}`)
  if (!res.ok) throw new Error('获取平台详情失败')
  return res.json()
}

// ---------- QQ ----------

export async function saveQQConfig(data: QQConfigRequest) {
  const res = await fetch(`${getBaseUrl()}/platforms/qq`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存 QQ 配置失败')
  return res.json()
}

export async function unbindQQ() {
  const res = await fetch(`${getBaseUrl()}/platforms/qq`, { method: 'DELETE' })
  if (!res.ok) throw new Error('解绑 QQ 失败')
  return res.json()
}

// ---------- 飞书 ----------

export async function saveFeishuConfig(data: FeishuConfigRequest) {
  const res = await fetch(`${getBaseUrl()}/platforms/feishu`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存飞书配置失败')
  return res.json()
}

export async function feishuQRCode() {
  const res = await fetch(`${getBaseUrl()}/platforms/feishu/qrcode`, { method: 'POST' })
  if (!res.ok) throw new Error('获取飞书二维码失败')
  return res.json()
}

export async function feishuQRCodePoll(deviceCode?: string) {
  const res = await fetch(`${getBaseUrl()}/platforms/feishu/qrcode/poll`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_code: deviceCode || null }),
  })
  if (!res.ok) throw new Error('轮询飞书授权状态失败')
  return res.json()
}

export async function unbindFeishu() {
  const res = await fetch(`${getBaseUrl()}/platforms/feishu`, { method: 'DELETE' })
  if (!res.ok) throw new Error('解绑飞书失败')
  return res.json()
}

export async function cancelFeishuRegistration() {
  const res = await fetch(`${getBaseUrl()}/platforms/feishu/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error('取消飞书注册失败')
  return res.json()
}

// ---------- 微信 ----------

export async function saveWeChatConfig(data: WeChatConfigRequest) {
  const res = await fetch(`${getBaseUrl()}/platforms/wechat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('保存微信配置失败')
  return res.json()
}

export async function wechatQRCode() {
  const res = await fetch(`${getBaseUrl()}/platforms/wechat/qrcode`, { method: 'POST' })
  if (!res.ok) throw new Error('获取微信二维码失败')
  return res.json()
}

export async function wechatQRCodePoll(qrcodeKey?: string) {
  const res = await fetch(`${getBaseUrl()}/platforms/wechat/qrcode/poll`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ qrcode_key: qrcodeKey || null }),
  })
  if (!res.ok) throw new Error('轮询微信授权状态失败')
  return res.json()
}

export async function unbindWeChat() {
  const res = await fetch(`${getBaseUrl()}/platforms/wechat`, { method: 'DELETE' })
  if (!res.ok) throw new Error('解绑微信失败')
  return res.json()
}

// ---------- 快捷切换 ----------

export async function togglePlatform(platform: string) {
  const res = await fetch(`${getBaseUrl()}/platforms/${platform}/toggle`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('切换平台状态失败')
  return res.json()
}
