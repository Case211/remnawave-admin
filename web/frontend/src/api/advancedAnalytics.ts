import client from './client'

export interface GeoCountry {
  country: string
  country_code: string
  count: number
}

export interface GeoCity {
  city: string
  country: string
  lat: number
  lon: number
  count: number
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
  lifetime_used_traffic_bytes: number
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

export const advancedAnalyticsApi = {
  geo: async (period = '7d'): Promise<GeoData> => {
    const { data } = await client.get('/analytics/advanced/geo', { params: { period } })
    return data
  },

  topUsers: async (limit = 20): Promise<{ items: TopUser[] }> => {
    const { data } = await client.get('/analytics/advanced/top-users', { params: { limit } })
    return data
  },

  trends: async (metric = 'users', period = '30d'): Promise<TrendData> => {
    const { data } = await client.get('/analytics/advanced/trends', { params: { metric, period } })
    return data
  },
}
