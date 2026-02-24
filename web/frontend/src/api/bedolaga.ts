import client from './client'

// ── Types ────────────────────────────────────────────────────────

export interface BedolagaStatus {
  enabled: boolean
  connected: boolean
  base_url: string | null
  bot_version: string | null
  sync_running: boolean
  initial_sync_done: boolean
  sync_entities: Array<{
    key: string
    last_sync_at: string | null
    sync_status: string
    records_synced: number
    error_message: string | null
  }>
}

export interface BedolagaOverview {
  total_users: number
  active_subscriptions: number
  total_revenue: number
  total_transactions: number
  open_tickets: number
  snapshot_at: string | null
  raw_data: Record<string, unknown> | null
}

export interface BedolagaUser {
  id: number
  telegram_id: number | null
  username: string | null
  first_name: string | null
  last_name: string | null
  status: string | null
  balance_rubles: number
  referral_code: string | null
  has_had_paid_subscription: boolean
  created_at: string | null
  last_activity: string | null
  synced_at: string | null
}

export interface BedolagaSubscription {
  id: number
  user_id: number | null
  user_telegram_id: number | null
  plan_name: string | null
  status: string | null
  is_trial: boolean
  started_at: string | null
  expires_at: string | null
  traffic_limit_bytes: number | null
  traffic_used_bytes: number | null
  payment_amount: number | null
  payment_provider: string | null
  synced_at: string | null
}

export interface BedolagaTransaction {
  id: number
  user_id: number | null
  user_telegram_id: number | null
  amount: number
  currency: string | null
  provider: string | null
  status: string | null
  type: string | null
  created_at: string | null
  synced_at: string | null
}

export interface BedolagaTransactionStats {
  total_amount: number
  total_count: number
  by_provider: Record<string, { amount: number; count: number }>
  by_day: Array<{ day: string; amount: number; count: number }>
}

export interface BedolagaRevenue {
  total_revenue: number
  revenue_today: number
  revenue_week: number
  revenue_month: number
  by_provider: Record<string, number>
  daily_chart: Array<{ day: string; amount: number }>
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ── API ──────────────────────────────────────────────────────────

export const bedolagaApi = {
  // Status & Health
  getStatus: async (): Promise<BedolagaStatus> => {
    const { data } = await client.get('/bedolaga/status')
    return data
  },

  // Sync
  triggerSync: async (entity?: string) => {
    const params = entity ? { entity } : {}
    const { data } = await client.post('/bedolaga/sync', null, { params })
    return data
  },

  getSyncStatus: async () => {
    const { data } = await client.get('/bedolaga/sync/status')
    return data
  },

  // Overview (from cache)
  getOverview: async (): Promise<BedolagaOverview> => {
    const { data } = await client.get('/bedolaga/overview')
    return data
  },

  getOverviewHistory: async (limit = 30) => {
    const { data } = await client.get('/bedolaga/overview/history', { params: { limit } })
    return data
  },

  // Users (from cache)
  getUsers: async (params: {
    limit?: number
    offset?: number
    status?: string
    search?: string
  } = {}): Promise<PaginatedResponse<BedolagaUser>> => {
    const { data } = await client.get('/bedolaga/users', { params })
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: data?.total || 0,
      limit: data?.limit || 50,
      offset: data?.offset || 0,
    }
  },

  getUser: async (userId: number): Promise<BedolagaUser> => {
    const { data } = await client.get(`/bedolaga/users/${userId}`)
    return data
  },

  // Subscriptions (from cache)
  getSubscriptions: async (params: {
    limit?: number
    offset?: number
    status?: string
    user_id?: number
    is_trial?: boolean
  } = {}): Promise<PaginatedResponse<BedolagaSubscription>> => {
    const { data } = await client.get('/bedolaga/subscriptions', { params })
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: data?.total || 0,
      limit: data?.limit || 50,
      offset: data?.offset || 0,
    }
  },

  // Transactions (from cache)
  getTransactions: async (params: {
    limit?: number
    offset?: number
    user_id?: number
    provider?: string
    status?: string
    type?: string
  } = {}): Promise<PaginatedResponse<BedolagaTransaction>> => {
    const { data } = await client.get('/bedolaga/transactions', { params })
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      total: data?.total || 0,
      limit: data?.limit || 50,
      offset: data?.offset || 0,
    }
  },

  getTransactionStats: async (): Promise<BedolagaTransactionStats> => {
    const { data } = await client.get('/bedolaga/transactions/stats')
    return data
  },

  // Revenue (computed from cache)
  getRevenue: async (): Promise<BedolagaRevenue> => {
    const { data } = await client.get('/bedolaga/revenue')
    return data
  },

  // Tickets (real-time)
  getTickets: async (params: {
    limit?: number
    offset?: number
    status?: string
    priority?: string
    user_id?: number
  } = {}) => {
    const { data } = await client.get('/bedolaga/tickets', { params })
    return data
  },

  getTicket: async (ticketId: number) => {
    const { data } = await client.get(`/bedolaga/tickets/${ticketId}`)
    return data
  },

  updateTicketStatus: async (ticketId: number, status: string) => {
    const { data } = await client.post(`/bedolaga/tickets/${ticketId}/status`, { status })
    return data
  },

  replyToTicket: async (ticketId: number, text: string) => {
    const { data } = await client.post(`/bedolaga/tickets/${ticketId}/reply`, { text })
    return data
  },

  // Promo Codes (real-time)
  getPromoCodes: async (params: { limit?: number; offset?: number; is_active?: boolean } = {}) => {
    const { data } = await client.get('/bedolaga/promo-codes', { params })
    return data
  },

  createPromoCode: async (payload: Record<string, unknown>) => {
    const { data } = await client.post('/bedolaga/promo-codes', payload)
    return data
  },

  deletePromoCode: async (promocodeId: number) => {
    await client.delete(`/bedolaga/promo-codes/${promocodeId}`)
  },

  // Partners (real-time)
  getPartners: async (params: { limit?: number; offset?: number; search?: string } = {}) => {
    const { data } = await client.get('/bedolaga/partners', { params })
    return data
  },

  getPartnerStats: async (days = 30) => {
    const { data } = await client.get('/bedolaga/partners/stats', { params: { days } })
    return data
  },

  // Polls (real-time)
  getPolls: async (params: { limit?: number; offset?: number } = {}) => {
    const { data } = await client.get('/bedolaga/polls', { params })
    return data
  },

  // Broadcasts (real-time)
  getBroadcasts: async (params: { limit?: number; offset?: number } = {}) => {
    const { data } = await client.get('/bedolaga/broadcasts', { params })
    return data
  },

  // Settings (real-time)
  getSettings: async () => {
    const { data } = await client.get('/bedolaga/settings')
    return data
  },

  updateSetting: async (key: string, value: unknown) => {
    const { data } = await client.put(`/bedolaga/settings/${key}`, { value })
    return data
  },
}
