/**
 * API client for the smart-support plugin endpoints.
 *
 * The panel's axios client (``@/api/client``) is configured with the base
 * URL ``/api/v2`` — we mount the plugin's calls under
 * ``/plugins/smart_support/*`` so they match the FastAPI prefix declared
 * by the panel's plugin loader.
 */
import client from '@/api/client'

import type {
  LicenseError,
  ReportResponse,
  SearchResponse,
  ThresholdSettings,
} from './types'

const BASE = '/plugins/smart_support'

export async function searchUsers(q: string, limit = 20): Promise<SearchResponse> {
  const { data } = await client.get<SearchResponse>(`${BASE}/search`, {
    params: { q, limit },
  })
  return data
}

export async function fetchReport(uuid: string): Promise<ReportResponse> {
  const { data } = await client.get<ReportResponse>(`${BASE}/report/${uuid}`)
  return data
}

export async function fetchSettings(): Promise<ThresholdSettings> {
  const { data } = await client.get<ThresholdSettings>(`${BASE}/settings`)
  return data
}

export async function updateSettings(
  patch: Partial<ThresholdSettings>,
): Promise<ThresholdSettings> {
  const { data } = await client.put<ThresholdSettings>(`${BASE}/settings`, patch)
  return data
}

/**
 * Decode a 402 axios error into the plugin's structured payload, if it
 * matches. Returns ``null`` for other error shapes so callers can tell
 * "license blocked" apart from "user not found" or network errors.
 */
export function asLicenseError(err: unknown): LicenseError | null {
  if (typeof err !== 'object' || err === null) return null
  const anyErr = err as { response?: { status?: number; data?: { detail?: unknown } } }
  if (anyErr.response?.status !== 402) return null
  const detail = anyErr.response.data?.detail
  if (typeof detail !== 'object' || detail === null) return null
  const d = detail as Partial<LicenseError>
  if (typeof d.plugin !== 'string' || typeof d.license_state !== 'string') return null
  return detail as LicenseError
}
