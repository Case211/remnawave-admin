import client from './client'

export interface ViolationReport {
  id: number
  report_type: string
  period_start: string
  period_end: string
  total_violations: number
  critical_count: number
  warning_count: number
  monitor_count: number
  unique_users: number
  prev_total_violations: number | null
  trend_percent: number | null
  top_violators: Array<{
    username: string
    uuid: string
    score: number
    violations_count: number
    country: string
  }> | null
  by_country: Record<string, number> | null
  by_action: Record<string, number> | null
  by_asn_type: Record<string, number> | null
  message_text: string | null
  generated_at: string
  sent_at: string | null
}

export interface ASNRecord {
  asn: number
  org_name: string
  org_name_en: string | null
  provider_type: string | null
  region: string | null
  city: string | null
  country_code: string
  description: string | null
  is_active: boolean
}

export interface ASNStats {
  total: number
  by_type: Record<string, number>
}

export const reportsApi = {
  getReports: async (reportType?: string, limit = 50): Promise<ViolationReport[]> => {
    const params = new URLSearchParams()
    if (reportType) params.set('report_type', reportType)
    params.set('limit', String(limit))
    const { data } = await client.get(`/reports?${params}`)
    return data.items
  },

  getReport: async (id: number): Promise<ViolationReport> => {
    const { data } = await client.get(`/reports/${id}`)
    return data
  },

  generateReport: async (reportType: string, startDate?: string, endDate?: string) => {
    const { data } = await client.post('/reports/generate', {
      report_type: reportType,
      start_date: startDate,
      end_date: endDate,
    })
    return data
  },
}

export const asnApi = {
  search: async (orgName: string): Promise<ASNRecord[]> => {
    const { data } = await client.get(`/asn/search?org_name=${encodeURIComponent(orgName)}`)
    return data.items
  },

  getByType: async (providerType: string): Promise<ASNRecord[]> => {
    const { data } = await client.get(`/asn/by-type/${providerType}`)
    return data.items
  },

  getStats: async (): Promise<ASNStats> => {
    const { data } = await client.get('/asn/stats')
    return data
  },

  getAsn: async (asn: number): Promise<ASNRecord> => {
    const { data } = await client.get(`/asn/${asn}`)
    return data
  },

  sync: async (limit?: number) => {
    const { data } = await client.post('/asn/sync', { limit })
    return data
  },
}
