/**
 * API client for the live-flow plugin endpoints (mounted by the panel's
 * plugin loader under ``/api/v2/plugins/live_flow``).
 */
import client from '@/api/client'

import type { FlowData } from './types'

export { asLicenseError } from '@/components/plugins/license'

const BASE = '/plugins/live_flow'

export async function fetchFlow(): Promise<FlowData> {
  const { data } = await client.get<FlowData>(`${BASE}/data`)
  return data
}
