import { useModelStore } from '@/stores/model'

function getBaseUrl(): string {
  return useModelStore().getBaseUrl()
}

export interface PetState {
  name: string
  row: number
  frames: number
}

export interface PetInfo {
  id: string
  name: string
  displayName?: string
  description?: string
  spritesheetUrl?: string
  previewUrl: string
  frameWidth?: number
  frameHeight?: number
  columns?: number
  rows?: number
  states?: PetState[]
  /** state-name → spritesheet 同一 URL（兼容旧版） */
  animations: Record<string, string>
}

export interface PetListResponse {
  pets: PetInfo[]
  total: number
}

export async function listPets(): Promise<PetListResponse> {
  const res = await fetch(`${getBaseUrl()}/pets/list`)
  if (!res.ok) {
    throw new Error('获取宠物列表失败')
  }
  return res.json()
}
