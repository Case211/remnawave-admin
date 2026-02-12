/**
 * Notifications & Alerts API module.
 */
import client from './client'

// ── Types ────────────────────────────────────────────────────────

export interface Notification {
  id: number
  admin_id: number | null
  type: string
  severity: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  source: string | null
  source_id: string | null
  group_key: string | null
  created_at: string | null
}

export interface NotificationChannel {
  id: number
  admin_id: number
  channel_type: string
  is_enabled: boolean
  config: Record<string, string>
  created_at: string | null
  updated_at: string | null
}

export interface SmtpConfig {
  id: number
  host: string
  port: number
  username: string | null
  from_email: string
  from_name: string
  use_tls: boolean
  use_ssl: boolean
  is_enabled: boolean
  updated_at: string | null
}

export interface AlertRule {
  id: number
  name: string
  description: string | null
  is_enabled: boolean
  rule_type: string
  metric: string | null
  operator: string | null
  threshold: number | null
  duration_minutes: number
  channels: string[]
  severity: string
  cooldown_minutes: number
  group_key: string | null
  escalation_admin_id: number | null
  escalation_minutes: number
  title_template: string
  body_template: string
  last_triggered_at: string | null
  last_value: number | null
  trigger_count: number
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AlertLog {
  id: number
  rule_id: number | null
  rule_name: string | null
  metric_value: number | null
  threshold_value: number | null
  severity: string | null
  channels_notified: string[]
  acknowledged: boolean
  acknowledged_by: number | null
  acknowledged_at: string | null
  details: string | null
  created_at: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

// ── API ──────────────────────────────────────────────────────────

export const notificationsApi = {
  // ── Notifications ───────────────────────────────────────────
  list: async (params?: {
    page?: number
    per_page?: number
    is_read?: boolean
    type?: string
    severity?: string
  }): Promise<PaginatedResponse<Notification>> => {
    const { data } = await client.get('/notifications', { params })
    return data
  },

  unreadCount: async (): Promise<{ count: number }> => {
    const { data } = await client.get('/notifications/unread-count')
    return data
  },

  markRead: async (ids?: number[]): Promise<void> => {
    await client.post('/notifications/mark-read', { ids: ids || [] })
  },

  delete: async (id: number): Promise<void> => {
    await client.delete(`/notifications/${id}`)
  },

  deleteOld: async (days: number = 30): Promise<void> => {
    await client.delete('/notifications', { params: { days } })
  },

  create: async (payload: {
    title: string
    body?: string
    type?: string
    severity?: string
    admin_id?: number | null
    link?: string
  }): Promise<void> => {
    await client.post('/notifications/create', payload)
  },

  // ── Channels ────────────────────────────────────────────────
  listChannels: async (): Promise<NotificationChannel[]> => {
    const { data } = await client.get('/notification-channels')
    return data
  },

  createChannel: async (payload: {
    channel_type: string
    is_enabled?: boolean
    config: Record<string, string>
  }): Promise<NotificationChannel> => {
    const { data } = await client.post('/notification-channels', payload)
    return data
  },

  updateChannel: async (
    id: number,
    payload: { is_enabled?: boolean; config?: Record<string, string> }
  ): Promise<NotificationChannel> => {
    const { data } = await client.put(`/notification-channels/${id}`, payload)
    return data
  },

  deleteChannel: async (id: number): Promise<void> => {
    await client.delete(`/notification-channels/${id}`)
  },

  // ── SMTP Config ─────────────────────────────────────────────
  getSmtpConfig: async (): Promise<SmtpConfig> => {
    const { data } = await client.get('/smtp-config')
    return data
  },

  updateSmtpConfig: async (payload: Partial<SmtpConfig> & { password?: string }): Promise<SmtpConfig> => {
    const { data } = await client.put('/smtp-config', payload)
    return data
  },

  testSmtp: async (to_email: string): Promise<{ success: boolean; to: string }> => {
    const { data } = await client.post('/smtp-config/test', { to_email })
    return data
  },

  // ── Alert Rules ─────────────────────────────────────────────
  listAlertRules: async (): Promise<AlertRule[]> => {
    const { data } = await client.get('/alert-rules')
    return data
  },

  createAlertRule: async (payload: Partial<AlertRule>): Promise<AlertRule> => {
    const { data } = await client.post('/alert-rules', payload)
    return data
  },

  updateAlertRule: async (id: number, payload: Partial<AlertRule>): Promise<AlertRule> => {
    const { data } = await client.put(`/alert-rules/${id}`, payload)
    return data
  },

  deleteAlertRule: async (id: number): Promise<void> => {
    await client.delete(`/alert-rules/${id}`)
  },

  toggleAlertRule: async (id: number): Promise<AlertRule> => {
    const { data } = await client.post(`/alert-rules/${id}/toggle`)
    return data
  },

  // ── Alert Logs ──────────────────────────────────────────────
  listAlertLogs: async (params?: {
    page?: number
    per_page?: number
    rule_id?: number
    acknowledged?: boolean
  }): Promise<PaginatedResponse<AlertLog>> => {
    const { data } = await client.get('/alert-logs', { params })
    return data
  },

  acknowledgeAlerts: async (ids?: number[]): Promise<void> => {
    await client.post('/alert-logs/acknowledge', { ids: ids || [] })
  },
}
