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

// ── Script Types ────────────────────────────────────────────────

export interface ScriptListItem {
  id: number
  name: string
  display_name: string
  description: string | null
  category: string
  timeout_seconds: number
  requires_root: boolean
  is_builtin: boolean
}

export interface ScriptDetail extends ScriptListItem {
  script_content: string
  source_url?: string | null
  imported_at?: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ScriptCreate {
  name: string
  display_name: string
  description?: string
  category: string
  script_content: string
  timeout_seconds: number
  requires_root: boolean
}

export interface ScriptUpdate {
  display_name?: string
  description?: string
  category?: string
  script_content?: string
  timeout_seconds?: number
  requires_root?: boolean
}

export interface ImportUrlRequest {
  url: string
  name: string
  display_name: string
  description?: string
  category: string
  timeout_seconds: number
  requires_root: boolean
}

export interface RepoFileItem {
  path: string
  name: string
  size: number
  download_url: string
}

export interface BrowseRepoResponse {
  repo: string
  files: RepoFileItem[]
  truncated: boolean
}

export interface BulkImportResponse {
  imported: number
  errors: string[]
  scripts: ScriptDetail[]
}

export interface ExecStatusResponse {
  id: number
  node_uuid: string
  status: string
  output: string | null
  exit_code: number | null
  started_at: string
  finished_at: string | null
  duration_ms: number | null
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

// ── Script API Functions ────────────────────────────────────────

export async function listScripts(category?: string): Promise<ScriptListItem[]> {
  const { data } = await client.get('/fleet/scripts', {
    params: category ? { category } : {},
  })
  return Array.isArray(data) ? data : []
}

export async function getScript(id: number): Promise<ScriptDetail> {
  const { data } = await client.get(`/fleet/scripts/${id}`)
  return data
}

export async function createScript(body: ScriptCreate): Promise<ScriptDetail> {
  const { data } = await client.post('/fleet/scripts', body)
  return data
}

export async function updateScript(id: number, body: ScriptUpdate): Promise<ScriptDetail> {
  const { data } = await client.patch(`/fleet/scripts/${id}`, body)
  return data
}

export async function deleteScript(id: number): Promise<void> {
  await client.delete(`/fleet/scripts/${id}`)
}

export async function execScript(
  scriptId: number,
  nodeUuid: string,
  envVars?: Record<string, string>,
) {
  const { data } = await client.post('/fleet/exec-script', {
    script_id: scriptId,
    node_uuid: nodeUuid,
    ...(envVars && Object.keys(envVars).length > 0 ? { env_vars: envVars } : {}),
  })
  return data
}

export async function getExecStatus(execId: number): Promise<ExecStatusResponse> {
  const { data } = await client.get(`/fleet/exec/${execId}`)
  return data
}

// ── Import API Functions ────────────────────────────────────────

export async function importScriptFromUrl(body: ImportUrlRequest): Promise<ScriptDetail> {
  const { data } = await client.post('/fleet/scripts/import-url', body)
  return data
}

export async function browseGithubRepo(repoUrl: string): Promise<BrowseRepoResponse> {
  const { data } = await client.post('/fleet/scripts/browse-repo', { repo_url: repoUrl })
  return data
}

export async function bulkImportScripts(files: ImportUrlRequest[]): Promise<BulkImportResponse> {
  const { data } = await client.post('/fleet/scripts/bulk-import', { files })
  return data
}
