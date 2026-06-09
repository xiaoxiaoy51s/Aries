/**
 * Terminal WebSocket API
 */
export function getTerminalWsUrl(workDir: string, sessionId: string): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//localhost:2026/ws/terminal?work_dir=${encodeURIComponent(workDir)}&session_id=${encodeURIComponent(sessionId)}`
}
