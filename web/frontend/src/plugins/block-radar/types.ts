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

/**
 * Локальная просадка: онлайн ноды обвалился, а панель в целом жива.
 * Считается по доле ноды в общем онлайне, поэтому ночной спад — когда
 * проседают все ноды разом — сюда не попадает.
 */
export interface RadarNodeDip {
  node_uuid: string
  node_name: string | null
  since: string
  online: number
  baseline_online: number
  share: number
  baseline_share: number
  node_alive: boolean
}

export interface RadarStatus {
  last_tick: RadarTick | null
  open_alerts: number
  license_usable: boolean
  open_dips: RadarNodeDip[]
  license_state: string | null
  license_tier: string | null
  /** Unix-время окончания подписки: нужно, чтобы предупредить до отключения. */
  license_paid_until: number | null
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
  /** Быстрое локальное правило по просадке доли ноды. */
  dip_enabled: boolean
  /** Слать ли уведомление, когда просевшая нода не на связи (плановый ребут). */
  dip_notify_offline: boolean
  dip_frac: number
  dip_min_users: number
  dip_confirm_ticks: number
  dip_history_days: number
}

export type RadarSettingsPatch = Partial<RadarSettings>
