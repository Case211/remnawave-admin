import client from './client'

export interface ReportViolator {
  user_uuid: string
  username: string | null
  email?: string | null
  violations_count: number
  max_score: number | null
  avg_score?: number | null
}

export interface ViolationReport {
  id: number
  report_type: string
  /** Начало периода (включительно) и конец (не включительно), ISO с поясом */
  period_start: string
  period_end: string
  total_violations: number
  critical_count: number
  warning_count: number
  monitor_count: number
  unique_users: number
  prev_total_violations: number | null
  trend_percent: number | null
  top_violators: ReportViolator[] | null
  by_country: Record<string, number> | null
  by_action: Record<string, number> | null
  by_asn_type: Record<string, number> | null
  message_text: string | null
  generated_at: string
  sent_at: string | null
  /** Ограниченный админ: в топе только его юзеры, общие цифры — по всем */
  scoped?: boolean
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

  generateReport: async (reportType: string, startDate?: string, endDate?: string): Promise<{ id: number | null }> => {
    const { data } = await client.post('/reports/generate', {
      report_type: reportType,
      start_date: startDate,
      end_date: endDate,
    })
    return data
  },

  /** Отправить отчёт в Telegram — туда же, куда шлёт расписание. */
  sendReport: async (id: number) => {
    const { data } = await client.post(`/reports/${id}/send`)
    return data
  },

  deleteReport: async (id: number) => {
    const { data } = await client.delete(`/reports/${id}`)
    return data
  },
}
