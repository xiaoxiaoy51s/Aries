export interface Provider {
  id: string
  icon: string
  label: string
  model: string
  baseUrl: string
  keywords: string[]
}

export const PROVIDERS: Provider[] = [
  { id: 'chatgpt', icon: 'chatgpt.svg', label: 'ChatGPT', model: 'gpt-5.4-mini', baseUrl: 'https://api.openai.com/v1', keywords: ['gpt', 'openai', 'chatgpt'] },
  { id: 'claude', icon: 'claude.svg', label: 'Claude', model: 'Claude Sonnet 5', baseUrl: '', keywords: ['claude', 'anthropic'] },
  { id: 'gemini', icon: 'gemini.svg', label: 'Gemini', model: 'gemini-3.5-flash', baseUrl: '', keywords: ['gemini'] },
  { id: 'deepseek', icon: 'deepseek.svg', label: 'DeepSeek', model: 'deepseek-v4-flash', baseUrl: 'https://api.deepseek.com', keywords: ['deepseek'] },
  { id: 'qwen', icon: 'qwen.svg', label: '通义千问', model: 'qwen3.7-plus', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', keywords: ['qwen', 'tongyi'] },
  { id: 'glm', icon: 'glm.svg', label: '智谱 GLM', model: 'glm-5.2', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', keywords: ['glm', 'chatglm', 'zhipu'] },
  { id: 'kimi', icon: 'kimi.svg', label: 'Kimi', model: 'kimi-k2.7-code', baseUrl: 'https://api.moonshot.cn/v1', keywords: ['kimi', 'moonshot'] },
  { id: 'doubao', icon: 'doubao.svg', label: '豆包', model: 'doubao-pro-32k', baseUrl: 'https://ark.cn-beijing.volces.com/api/v3', keywords: ['doubao', 'ark'] },
  { id: 'grok', icon: 'grok.svg', label: 'Grok', model: 'grok-4.5', baseUrl: 'https://api.x.ai/v1', keywords: ['grok'] },
  { id: 'hunyun', icon: 'hunyun.svg', label: '混元', model: 'hunyuan-pro', baseUrl: 'https://tokenhub.tencentmaas.com/v1', keywords: ['hunyuan', 'hy'] },
  { id: 'minimax', icon: 'minimax.svg', label: 'MiniMax', model: 'MiniMax M3', baseUrl: 'https://api.minimaxi.com/v1', keywords: ['minimax'] },
  { id: 'mimo', icon: 'mimo.svg', label: 'MiMo', model: 'mimo-v2.5', baseUrl: 'https://api.xiaomimimo.com/v1', keywords: ['mimo'] },
  { id: 'openrouter', icon: 'openrouter.svg', label: 'OpenRouter', model: 'tencent/hy3:free', baseUrl: 'https://openrouter.ai/api/v1', keywords: ['openrouter'] },
  { id: 'custom', icon: 'Custom.svg', label: '其他', model: '', baseUrl: '', keywords: [] },
]

export function detectProvider(modelName: string): Provider {
  const lower = (modelName || '').toLowerCase()
  for (const p of PROVIDERS) {
    if (p.id === 'custom') continue
    if (p.keywords.some(kw => lower.includes(kw))) return p
  }
  return PROVIDERS.find(p => p.id === 'custom')!
}
