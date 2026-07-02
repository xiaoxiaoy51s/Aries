let petStatusPhase = ''
let petReasoningBuf = ''
let petContentBuf = ''

export function sendPetStatus(text: string) {
  try {
    window.electronAPI?.sendPetStatus(text)
  } catch {
    // 非 Electron 环境忽略
  }
}

export function clearPetStatus() {
  petStatusPhase = ''
  petReasoningBuf = ''
  petContentBuf = ''
  try {
    window.electronAPI?.clearPetStatus()
    window.electronAPI?.setPetState?.('idle')
  } catch {
    // 非 Electron 环境忽略
  }
}

function flushPetStatus(oldPhase: string) {
  if (oldPhase === 'reasoning' && petReasoningBuf.trim()) {
    const text = petReasoningBuf.trim()
    sendPetStatus(text.length > 200 ? text.slice(0, 200) + '…' : text)
    petReasoningBuf = ''
  } else if (oldPhase === 'content' && petContentBuf.trim()) {
    const text = petContentBuf.trim()
    sendPetStatus(text.length > 200 ? text.slice(0, 200) + '…' : text)
    petContentBuf = ''
  }
}

export function onStreamContentDelta(data: string) {
  if (petStatusPhase !== 'content') {
    flushPetStatus(petStatusPhase)
    petStatusPhase = 'content'
    window.electronAPI?.setPetState?.('waving')
  }
  petContentBuf += data
}

export function onStreamReasoningDelta(data: string) {
  if (petStatusPhase !== 'reasoning') {
    flushPetStatus(petStatusPhase)
    petStatusPhase = 'reasoning'
    window.electronAPI?.setPetState?.('waiting')
  }
  petReasoningBuf += data
}

export function onStreamToolPhase() {
  flushPetStatus(petStatusPhase)
  petStatusPhase = 'tool'
  window.electronAPI?.setPetState?.('review')
}

export function flushPetStatusForComplete() {
  flushPetStatus(petStatusPhase)
}
