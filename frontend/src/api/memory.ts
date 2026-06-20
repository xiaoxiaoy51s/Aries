import { useModelStore } from '@/stores/model'

function getBaseUrl() {
  const store = useModelStore()
  return store.getBaseUrl()
}

export async function getRoleRules(workDir: string | null) {
  const params = workDir ? `?work_dir=${encodeURIComponent(workDir)}` : ''
  const res = await fetch(`${getBaseUrl()}/memory/rules${params}`)
  if (!res.ok) throw new Error('读取约束失败')
  return res.json()
}

export async function saveRoleRules(workDir: string | null, content: string) {
  const res = await fetch(`${getBaseUrl()}/memory/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ work_dir: workDir, content }),
  })
  if (!res.ok) throw new Error('保存约束失败')
  return res.json()
}

export async function getRoleGuide() {
  const res = await fetch(`${getBaseUrl()}/memory/guide`)
  if (!res.ok) throw new Error('获取说明失败')
  return res.json()
}

export async function getInitPrompt() {
  const res = await fetch(`${getBaseUrl()}/memory/init-prompt`)
  if (!res.ok) throw new Error('获取 Init Prompt 失败')
  return res.json()
}

export async function polishRoleRules(workDir: string | null, content: string) {
  const store = useModelStore()
  const model = store.activeModel
  const res = await fetch(`${getBaseUrl()}/memory/rules/polish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      work_dir: workDir,
      content,
      baseUrl: model?.baseUrl || '',
      apiKey: model?.apiKey || '',
      model: model?.model || '',
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'AI 润色失败')
  }
  return res.json()
}
