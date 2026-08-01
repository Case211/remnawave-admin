/**
 * Types mirroring the block-radar plugin backend schemas
 * (``rwa_plugin_block_radar/schemas.py``).
 */

export interface RadarTick {
  at?: string
  ok?: boolean
  error?: string
  note?: string
  nodes_total?: number
  nodes_skipped?: number
  links_active?: number
  links_zero?: number
  cells?: number
  accepted?: number
  rejected?: number
  alerts_locked?: boolean
  alerts_new?: number
  alerts_resolved?: number
  notified?: number
}

export interface RadarStatus {
  last_tick: RadarTick | null
  open_alerts: number
  license_usable: boolean
}

export interface RadarAffected {
  nodes?: string[]
  online_now?: number | null
  lost?: boolean
}

export interface RadarAlert {
  id: number
  kind: 'block' | 'operator_outage'
  op_asn: number
  op_org?: string | null
  host_asn: number
  host_org?: string | null
  transport: string
  since: string
  resolved_at?: string | null
  panels?: number | null
  online?: number | null
  baseline?: number | null
  outage_summary?: string | null
  affected: RadarAffected
}

export interface RadarAlerts {
  items: RadarAlert[]
  total: number
}

export interface RadarSettings {
  notify_enabled: boolean
  notify_resolved: boolean
  online_window_minutes: number
  send_org_names: boolean
}

export type RadarSettingsPatch = Partial<RadarSettings>
