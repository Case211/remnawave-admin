export interface Violation {
  id: number
  user_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  score: number
  severity: string
  recommended_action: string
  confidence: number
  action_taken: string | null
  notified: boolean
  detected_at: string
  reasons?: string[]
  countries?: string[]
  status?: string
}

export interface ViolationDetail {
  id: number
  user_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  score: number
  recommended_action: string
  confidence: number
  detected_at: string
  temporal_score: number
  geo_score: number
  asn_score: number
  profile_score: number
  device_score: number
  hwid_score: number
  reasons: string[]
  countries: string[]
  asn_types: string[]
  ips: string[]
  action_taken: string | null
  action_taken_at: string | null
  action_taken_by: number | null
  notified_at: string | null
  raw_data: Record<string, unknown> | null
}

export interface ViolationStats {
  total: number
  critical: number
  high: number
  medium: number
  low: number
  unique_users: number
  avg_score: number
  max_score: number
  by_action: Record<string, number>
  by_country: Record<string, number>
}

export interface PaginatedResponse {
  items: Violation[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface TopViolator {
  user_uuid: string
  username: string | null
  violations_count: number
  max_score: number
  avg_score: number
  last_violation_at: string
  actions: string[]
}

export interface IPInfo {
  ip: string
  asn_org: string | null
  country: string | null
  city: string | null
  connection_type: string | null
  is_vpn: boolean
  is_proxy: boolean
  is_hosting: boolean
  is_mobile: boolean
}

export interface WhitelistItem {
  id: number
  user_uuid: string
  username: string | null
  email: string | null
  reason: string | null
  added_by_username: string | null
  added_at: string
  expires_at: string | null
  excluded_analyzers: string[] | null
}
