import client from './client'

export interface ShaperPenalty {
  enabled: boolean
  mb: number
  window_sec: number
  kbit: number
  minutes: number
}

export interface ShaperSettings {
  enabled: boolean
  ports: number[]
  down_kbit: number
  up_kbit: number
  penalty: ShaperPenalty
}

/** Ответ агента на последнюю команду: что реально стоит на ноде. */
export interface ShaperStatus {
  enabled?: boolean
  active: boolean
  interface?: string | null
  /** kept:<kind> | installed:<kind> | foreign:<kind> | restored */
  root?: string | null
  download_exact?: boolean
  error?: string | null
}

export interface ShaperState {
  settings: ShaperSettings
  status: ShaperStatus | null
  status_at: string | null
  updated_at: string | null
  updated_by: string | null
  configured: boolean
  agent: { connected: boolean; version: string | null; supported: boolean; min_version: string }
  suggested_ports: number[]
}

export const nodeShaperApi = {
  get: async (nodeUuid: string): Promise<ShaperState> => {
    const { data } = await client.get(`/nodes/${nodeUuid}/shaper`)
    return data
  },
  save: async (nodeUuid: string, settings: ShaperSettings): Promise<{ success: boolean; pushed: boolean }> => {
    const { data } = await client.put(`/nodes/${nodeUuid}/shaper`, settings)
    return data
  },
}
