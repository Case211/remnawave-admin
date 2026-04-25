/**
 * TypeScript shapes mirrored from the plugin's Pydantic models in
 * ``rwa_plugin_smart_support_tool/schemas.py``.
 *
 * Whenever a field is added or removed there, update the matching type
 * here too — there is no codegen step. Keep the order of fields the same
 * to make diffs easy to follow.
 */

export type LicenseState = 'valid' | 'expired' | 'missing' | 'not_required'

export type MatchedBy =
  | 'uuid'
  | 'short_uuid'
  | 'telegram_id'
  | 'email'
  | 'ip'
  | 'username'
  | 'fallback'

export interface SearchHit {
  uuid: string
  short_uuid?: string | null
  username?: string | null
  email?: string | null
  telegram_id?: number | null
  status?: string | null
  expire_at?: string | null
  last_connection_at?: string | null
  last_country?: string | null
  last_asn?: string | null
}

export interface SearchResponse {
  query: string
  matched_by: MatchedBy
  total: number
  hits: SearchHit[]
}

export interface TrafficUsage {
  limit_bytes?: number | null
  used_bytes?: number | null
  percent?: number | null
}

export interface HwidDevice {
  hwid: string
  platform?: string | null
  last_seen_at?: string | null
  is_blacklisted: boolean
}

export interface UserSection {
  uuid: string
  short_uuid?: string | null
  username?: string | null
  email?: string | null
  telegram_id?: number | null
  status?: string | null
  created_at?: string | null
  expire_at?: string | null
  days_until_expire?: number | null
  subscription_uuid?: string | null
  subscription_url?: string | null
  traffic: TrafficUsage
  active_squads: string[]
  hwid_limit?: number | null
  hwid_devices: HwidDevice[]
}

export interface ConnectionEvent {
  connected_at: string
  disconnected_at?: string | null
  duration_seconds?: number | null
  ip?: string | null
  country?: string | null
  city?: string | null
  asn?: string | null
  asn_org?: string | null
  node_uuid?: string | null
  node_name?: string | null
}

export interface HistorySection {
  total_connections: number
  unique_ips: number
  unique_countries: number
  unique_asns: number
  anomalies: string[]
  timeline: ConnectionEvent[]
}

export interface ClientSection {
  last_app?: string | null
  last_version?: string | null
  raw_user_agent?: string | null
  last_request_at?: string | null
  is_outdated?: boolean | null
  days_since_last_request?: number | null
}

export interface NodeCard {
  uuid: string
  name?: string | null
  address?: string | null
  is_connected: boolean
  is_disabled: boolean
  cpu_usage?: number | null
  memory_usage?: number | null
  disk_usage?: number | null
  metrics_age_seconds?: number | null
  user_active_here: boolean
}

export interface CorrelationCluster {
  kind: 'asn' | 'node' | 'asn_node'
  key: string
  label?: string | null
  affected_users: number
  window_start: string
  window_end: string
}

export interface ViolationCard {
  id: number
  created_at: string
  score?: number | null
  confidence?: number | null
  reason?: string | null
  action?: string | null
  is_resolved: boolean
}

export interface Hypothesis {
  rule_id: string
  title: string
  detail?: string | null
  severity: 'low' | 'medium' | 'high'
  confidence: number
  suggested_action?: string | null
}

export interface ReportResponse {
  generated_at: string
  user: UserSection
  history_24h: HistorySection
  client: ClientSection
  nodes: NodeCard[]
  correlations: CorrelationCluster[]
  violations_recent: ViolationCard[]
  hypotheses: Hypothesis[]
  session_id?: number | null
}

/**
 * 402 payload shape returned by the plugin's license-stub router.
 */
export interface LicenseError {
  plugin: string
  license_state: 'expired' | 'missing'
  code: 'license_expired' | 'license_required'
}
