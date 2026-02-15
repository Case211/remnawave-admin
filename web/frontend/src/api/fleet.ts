/**
 * Fleet management API module.
 *
 * Provides methods for listing agent v2 connection statuses
 * and querying the command execution log.
 */
import client from './client'

// ── Types ──────────────────────────────────────────────────────

export interface FleetAgentItem {
  uuid: string
  name: string
  address: string
  agent_v2_connected: boolean
  agent_v2_last_ping: string | null
}

export interface FleetAgentsResponse {
  nodes: FleetAgentItem[]
  connected_count: number
  total_count: number
}

export interface CommandLogEntry {
  id: number
  node_uuid: string
  admin_username: string | null
  command_type: string
  command_data: string | null
  status: string
  output: string | null
  exit_code: number | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
}

export interface CommandLogResponse {
  entries: CommandLogEntry[]
  total: number
  page: number
  per_page: number
}

// ── API Functions ──────────────────────────────────────────────

export async function getFleetAgents(): Promise<FleetAgentsResponse> {
  const { data } = await client.get('/fleet/agents')
  return data
}

export async function getCommandLog(params?: {
  page?: number
  per_page?: number
  node_uuid?: string
  command_type?: string
}): Promise<CommandLogResponse> {
  const { data } = await client.get('/fleet/command-log', { params })
  return data
}

export async function getNodeCommandLog(nodeUuid: string, params?: {
  page?: number
  per_page?: number
}): Promise<CommandLogResponse> {
  const { data } = await client.get('/fleet/command-log', {
    params: { ...params, node_uuid: nodeUuid },
  })
  return data
}
