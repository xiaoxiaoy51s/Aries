/** 平台 id → /agent-logos 静态资源 */
const PLATFORM_LOGOS: Record<string, string> = {
  aries: '/agent-logos/aries.png',
  gemini: '/agent-logos/gemini.png',
  codex: '/agent-logos/codex.png',
  claude: '/agent-logos/claude.png',
  opencode: '/agent-logos/opencode.png',
  qoder: '/agent-logos/qoder.png',
  trae: '/agent-logos/trae.png',
  kimi: '/agent-logos/kimi.png',
  cursor: '/agent-logos/cursor.png',
  mimocode: '/agent-logos/mimocode.png',
  codebuddy: '/agent-logos/codeBuddy.png',
}

export function resolvePlatformLogo(platform?: string | null): string {
  const id = (platform || 'aries').trim().toLowerCase() || 'aries'
  return PLATFORM_LOGOS[id] || `/agent-logos/${id}.png`
}

export function normalizeSessionPlatform(platform?: string | null): string {
  const id = (platform || 'aries').trim().toLowerCase()
  return id || 'aries'
}

export function hasPlatformLogo(platform?: string | null): boolean {
  const id = (platform || '').trim().toLowerCase()
  return id ? id in PLATFORM_LOGOS : false
}
