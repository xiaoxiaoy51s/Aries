import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export async function openPath(path: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/system/open-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '打开路径失败')
  }
  const data = await res.json()
  if (!data.ok) {
    throw new Error(data.error || '打开路径失败')
  }
}
