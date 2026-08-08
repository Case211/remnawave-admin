/**
 * API client for the block-radar plugin endpoints (mounted by the
 * panel's plugin loader under ``/api/v2/plugins/block_radar``).
 */
import client from '@/api/client'

import type {
  RadarAlerts,
  RadarHosters,
  RadarOverview,
  RadarSettings,
  RadarSettingsPatch,
  RadarStatus,
} from './types'

export { asLicenseError } from '@/components/plugins/license'

const BASE = '/plugins/block_radar'

export async function fetchStatus(): Promise<RadarStatus> {
  const { data } = await client.get<RadarStatus>(`${BASE}/status`)
  return data
}

export async function fetchAlerts(
  params: { active?: boolean; limit?: number; offset?: number } = {},
): Promise<RadarAlerts> {
  const { data } = await client.get<RadarAlerts>(`${BASE}/alerts`, { params })
  return data
}

export async function fetchSettings(): Promise<RadarSettings> {
  const { data } = await client.get<RadarSettings>(`${BASE}/settings`)
  return data
}

export async function updateSettings(patch: RadarSettingsPatch): Promise<RadarSettings> {
  const { data } = await client.put<RadarSettings>(`${BASE}/settings`, patch)
  return data
}

export async function fetchHosters(): Promise<RadarHosters> {
  const { data } = await client.get<RadarHosters>(`${BASE}/hosters`)
  return data
}

export async function fetchOverview(): Promise<RadarOverview> {
  const { data } = await client.get<RadarOverview>(`${BASE}/overview`)
  return data
}
