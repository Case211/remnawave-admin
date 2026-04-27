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

export interface AIExtraHypothesis {
  rule_id: string
  title: string
  detail?: string | null
  severity: 'low' | 'medium' | 'high'
  confidence: number
  suggested_action?: string | null
}

export interface AIAnalysis {
  summary: string
  extra_hypotheses: AIExtraHypothesis[]
  confidence: 'low' | 'medium' | 'high'
  provider_used: string
  model?: string | null
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
  ai_analysis?: AIAnalysis | null
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

/**
 * Mirrors ``ThresholdSettings`` in ``schemas.py`` — every key is optional
 * because PUT accepts a partial payload, and GET returns a fully resolved
 * (defaults + DB overrides) view.
 */
export interface ThresholdSettings {
  node_cpu_high?: number | null
  node_cpu_critical?: number | null
  node_memory_high?: number | null
  node_metrics_stale_seconds?: number | null
  traffic_high?: number | null
  traffic_full?: number | null
  traffic_full_confidence?: number | null
  traffic_high_confidence?: number | null
  cluster_node_window_minutes?: number | null
  cluster_node_reconnects_per_user?: number | null
  cluster_node_min_affected?: number | null
  cluster_asn_window_minutes?: number | null
  cluster_asn_min_affected?: number | null
  correlation_recompute_seconds?: number | null
  correlation_max_age_minutes?: number | null
}

export interface AISettingsOut {
  enabled: boolean
  provider_chain: string[]
  gemini_key_set: boolean
  groq_key_set: boolean
  openrouter_key_set: boolean
  gemini_model?: string | null
  groq_model?: string | null
  openrouter_model?: string | null
}

export interface AISettingsIn {
  enabled?: boolean
  provider_chain?: string[]
  gemini_api_key?: string
  groq_api_key?: string
  openrouter_api_key?: string
  gemini_model?: string
  groq_model?: string
  openrouter_model?: string
}

export interface AIProviderStatus {
  name: string
  available: boolean
  cooldown_seconds_remaining: number
  last_error?: string | null
}

export interface AIStatusResponse {
  enabled: boolean
  chain: AIProviderStatus[]
}

export interface ActionParamSpec {
  name: string
  type: 'number' | 'boolean' | 'string'
  default?: number | boolean | string | null
  label_i18n?: string | null
  min?: number | null
  max?: number | null
}

export interface ActionMetadata {
  id: string
  title_i18n: string
  severity: 'safe' | 'destructive'
  requires_confirmation: boolean
  params: ActionParamSpec[]
}

export interface ActionListResponse {
  actions: ActionMetadata[]
}

export interface ActionExecuteIn {
  user_uuid: string
  params?: Record<string, unknown>
  triggered_by_rule_id?: string | null
}

export interface ActionExecuteOut {
  ok: boolean
  message: string
  data?: Record<string, unknown> | null
}

export interface SessionEntry {
  id: number
  opened_at: string
  admin_username?: string | null
  target_user_uuid?: string | null
  triggered_by_rule_id?: string | null
  action_id?: string | null
  ok?: boolean | null
  message?: string | null
  params: Record<string, unknown>
}

export interface SessionListResponse {
  items: SessionEntry[]
  total: number
}
