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
  ClientReferenceResponse,
  SubmissionIn,
  SubmissionListResponse,
  ActionExecuteOut,
  ActionListResponse,
  ReportResponse,
  SearchResponse,
  SessionListResponse,
  ThresholdSettings,
} from './types'

// Общая для всех платных плагинов расшифровка 402 — реэкспорт, чтобы
// страницы плагина продолжали импортировать из './api'.
export { asLicenseError } from '@/components/plugins/license'

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


// ── общий справочник клиентских приложений ────────────────────────────────

export async function fetchClientReference(): Promise<ClientReferenceResponse> {
  const { data } = await client.get<ClientReferenceResponse>(`${BASE}/clients`)
  return data
}

export async function fetchSubmissions(
  status: 'open' | 'all' = 'open',
): Promise<SubmissionListResponse> {
  const { data } = await client.get<SubmissionListResponse>(`${BASE}/clients/submissions`, {
    params: { status },
  })
  return data
}

export async function proposeChange(body: SubmissionIn): Promise<{ id: number }> {
  const { data } = await client.post<{ id: number }>(`${BASE}/clients/submissions`, body)
  return data
}

export async function voteSubmission(
  id: number,
  vote: number,
): Promise<{ votes_up: number; votes_down: number; my_vote: number }> {
  const { data } = await client.post(`${BASE}/clients/submissions/${id}/vote`, { vote })
  return data
}
