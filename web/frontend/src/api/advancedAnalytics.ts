import client from './client'

export interface GeoCountry {
  country: string
  country_code: string
  count: number
}

export interface GeoCityUser {
  username: string
  uuid: string
  status: string
  connections: number
  ips: string[]
}

export interface GeoCity {
  city: string
  country: string
  lat: number
  lon: number
  count: number
  unique_users: number
  users: GeoCityUser[]
}

export interface GeoData {
  countries: GeoCountry[]
  cities: GeoCity[]
}

export interface TopUser {
  uuid: string
  username: string
  status: string
  used_traffic_bytes: number
  traffic_limit_bytes: number | null
  usage_percent: number | null
  online_at: string | null
}

export interface TrendPoint {
  date: string
  value: number
}

export interface TrendData {
  series: TrendPoint[]
  metric: string
  period: string
  total_growth: number
}

export interface SharedHwidUser {
  uuid: string
  username: string
  status: string
  created_at: string | null
  hwid_first_seen: string | null
  expire_date: string | null
  is_active: boolean
  is_trial: boolean
}

export interface SharedHwidGroup {
  hwid: string
  platform: string | null
  device_model: string | null
  user_count: number
  users: SharedHwidUser[]
}

export interface SharedHwidsData {
  items: SharedHwidGroup[]
  total_shared_hwids: number
}

export interface TimeseriesPoint {
  timestamp: string
  value: number
}

export interface TimeseriesResponse {
  points: TimeseriesPoint[]
  node_points?: { timestamp: string; nodes: Record<string, number> }[]
  node_names?: Record<string, string>
}

export interface NodeFleetItem {
  uuid: string
  name: string
  is_connected: boolean
  is_disabled: boolean
  cpu_usage: number | null
  memory_usage: number | null
  disk_usage: number | null
  users_online: number
  traffic_today_bytes: number
  traffic_total_bytes: number
  uptime_seconds: number | null
  download_speed_bps: number
  upload_speed_bps: number
}

export interface NodeFleetResponse {
  nodes: NodeFleetItem[]
  total: number
  online: number
  offline?: number
  disabled?: number
}

export interface ProviderTypeItem {
  type: string
  count: number
  percent: number
}

export interface TopAsnItem {
  asn: number
  org: string
  count: number
  percent: number
}

export interface ProviderFlags {
  vpn: { count: number; percent: number }
  proxy: { count: number; percent: number }
  tor: { count: number; percent: number }
  hosting: { count: number; percent: number }
}

export interface ProvidersData {
  connection_types: ProviderTypeItem[]
  top_asn: TopAsnItem[]
  flags: ProviderFlags
  total?: number
}

export interface RetentionCohort {
  week: string
  total_users: number
  active_users: number
  retention_percent: number
  with_traffic_percent: number
  with_active_sub_percent: number
}

export interface RetentionData {
  cohorts: RetentionCohort[]
  overall_retention: number
  total_registered: number
  total_retained: number
}

export const advancedAnalyticsApi = {
  /** Fetch provider/ASN analytics. */
  providers: async (period = '7d'): Promise<ProvidersData> => {
    const { data } = await client.get('/analytics/advanced/providers', { params: { period } })
    return data
  },

  /** Fetch node fleet analytics. */
  nodeFleet: async (): Promise<NodeFleetResponse> => {
    const { data } = await client.get('/analytics/node-fleet')
    return data
  },

  /** Fetch real traffic timeseries from /analytics/timeseries (daily consumption). */
  timeseries: async (period = '30d', metric = 'traffic'): Promise<TimeseriesResponse> => {
    const { data } = await client.get('/analytics/timeseries', { params: { period, metric } })
    return data
  },

  geo: async (period = '7d', dateFrom?: string, dateTo?: string): Promise<GeoData> => {
    const params: Record<string, string> = { period }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const { data } = await client.get('/analytics/advanced/geo', { params })
    return data
  },

  topUsers: async (limit = 20, dateFrom?: string, dateTo?: string): Promise<{ items: TopUser[]; period?: { from: string; to: string } }> => {
    const params: Record<string, string | number> = { limit }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const { data } = await client.get('/analytics/advanced/top-users', { params })
    return data
  },

  nodesTraffic: async (dateFrom: string, dateTo: string): Promise<{
    items: { uuid: string; name: string; traffic_bytes: number; percent: number }[]
    total_bytes: number
    period: { from: string; to: string }
  }> => {
    const { data } = await client.get('/analytics/advanced/nodes-traffic', {
      params: { date_from: dateFrom, date_to: dateTo },
    })
    return data
  },

  trends: async (metric = 'users', period = '30d', dateFrom?: string, dateTo?: string): Promise<TrendData> => {
    const params: Record<string, string> = { metric, period }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const { data } = await client.get('/analytics/advanced/trends', { params })
    return data
  },

  sharedHwids: async (minUsers = 2, limit = 50): Promise<SharedHwidsData> => {
    const { data } = await client.get('/analytics/advanced/shared-hwids', {
      params: { min_users: minUsers, limit },
    })
    return data
  },

  retention: async (weeks = 12): Promise<RetentionData> => {
    const { data } = await client.get('/analytics/advanced/retention', { params: { weeks } })
    return data
  },

  nodeMetricsHistory: async (period = '24h', nodeUuid?: string): Promise<NodeMetricsHistoryResponse> => {
    const params: Record<string, string> = { period }
    if (nodeUuid) params.node_uuid = nodeUuid
    const { data } = await client.get('/analytics/advanced/node-metrics-history', { params })
    return data
  },

  torrentStats: async (days = 7): Promise<TorrentStatsResponse> => {
    const { data } = await client.get('/analytics/advanced/torrent-stats', { params: { days } })
    return data
  },

  geoBalance: async (days = 7): Promise<GeoBalanceData> => {
    const { data } = await client.get('/analytics/advanced/geo-balance', { params: { days } })
    return data
  },

  cohortMatrix: async (granularity = 'week', months = 3): Promise<CohortMatrixData> => {
    const { data } = await client.get('/analytics/advanced/cohort-matrix', { params: { granularity, months } })
    return data
  },

  churn: async (period = 'month', months = 6): Promise<ChurnData> => {
    const { data } = await client.get('/analytics/advanced/churn', { params: { period, months } })
    return data
  },

  ltv: async (): Promise<LtvData> => {
    const { data } = await client.get('/analytics/advanced/ltv')
    return data
  },
}

export interface NodeMetricsHistoryItem {
  node_uuid: string
  node_name: string
  avg_cpu: number | null
  avg_memory: number | null
  avg_disk: number | null
  max_cpu: number | null
  max_memory: number | null
  max_disk: number | null
  samples_count: number
}

export interface NodeMetricsTimeseriesPoint {
  timestamp: string
  nodes: Record<string, { cpu: number | null; memory: number | null; disk: number | null }>
}

export interface NodeMetricsHistoryResponse {
  nodes: NodeMetricsHistoryItem[]
  timeseries: NodeMetricsTimeseriesPoint[]
  node_names: Record<string, string>
}

export interface CohortMatrixData {
  cohorts: {
    cohort: string
    total_users: number
    periods: Record<string, { active_users: number; retention_percent: number }>
  }[]
  periods: string[]
  granularity: string
}

export interface ChurnData {
  series: {
    period: string
    active_users: number
    new_users: number
    churned_users: number
    churn_rate: number
  }[]
  avg_churn: number
  period: string
}

export interface LtvData {
  avg_lifetime_days: number
  sample_size: number
  estimated_ltv: number
}

export interface GeoBalanceNode {
  uuid: string
  name: string
  is_connected: boolean
  is_disabled: boolean
  cpu_usage: number
  memory_usage: number
  disk_usage: number
  users_online: number
  is_overloaded: boolean
  top_countries: { country_code: string; country_name: string; user_count: number; connection_count: number }[]
}

export interface GeoBalanceRecommendation {
  type: string
  severity: string
  node: string
  node_uuid: string
  message: string
}

export interface GeoBalanceRegion {
  country_code: string
  country_name: string
  user_count: number
}

export interface GeoBalanceData {
  nodes: GeoBalanceNode[]
  recommendations: GeoBalanceRecommendation[]
  regions: GeoBalanceRegion[]
  median_users_online: number
  overloaded_count: number
}

export interface TorrentStatsResponse {
  summary: {
    total_events: number
    unique_users: number
    unique_destinations: number
    affected_nodes: number
  }
  timeseries: { date: string; events: number; users: number }[]
  top_users: { user_uuid: string; event_count: number }[]
  top_destinations: { destination: string; events: number; users: number }[]
}
