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
  AISettingsIn,
  AISettingsOut,
  AIStatusResponse,
  ActionExecuteIn,
  ActionExecuteOut,
  ActionListResponse,
  LicenseError,
  ReportResponse,
  SearchResponse,
  SessionListResponse,
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

export async function fetchAISettings(): Promise<AISettingsOut> {
  const { data } = await client.get<AISettingsOut>(`${BASE}/ai-settings`)
  return data
}

export async function updateAISettings(patch: AISettingsIn): Promise<AISettingsOut> {
  const { data } = await client.put<AISettingsOut>(`${BASE}/ai-settings`, patch)
  return data
}

export async function fetchAIStatus(): Promise<AIStatusResponse> {
  const { data } = await client.get<AIStatusResponse>(`${BASE}/ai-status`)
  return data
}

export async function resetAICooldown(): Promise<void> {
  await client.post(`${BASE}/ai-reset-cooldown`)
}

export async function fetchActions(): Promise<ActionListResponse> {
  const { data } = await client.get<ActionListResponse>(`${BASE}/actions`)
  return data
}

export async function executeAction(
  actionId: string,
  payload: ActionExecuteIn,
): Promise<ActionExecuteOut> {
  const { data } = await client.post<ActionExecuteOut>(
    `${BASE}/actions/${actionId}/execute`,
    payload,
  )
  return data
}

export async function fetchSessionsForUser(
  userUuid: string,
  params: { limit?: number; offset?: number } = {},
): Promise<SessionListResponse> {
  const { data } = await client.get<SessionListResponse>(
    `${BASE}/sessions/user/${userUuid}`,
    { params },
  )
  return data
}

export async function fetchRecentSessions(
  params: {
    limit?: number
    offset?: number
    action_id?: string
    admin_username?: string
  } = {},
): Promise<SessionListResponse> {
  const { data } = await client.get<SessionListResponse>(
    `${BASE}/sessions/recent`,
    { params },
  )
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
