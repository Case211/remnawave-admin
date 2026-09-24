/**
 * Notifications API module.
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

  /** Удалить все прочитанные уведомления любого возраста; возвращает число удалённых. */
  deleteRead: async (): Promise<{ deleted: number }> => {
    const { data } = await client.delete('/notifications/read')
    return data
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
}

