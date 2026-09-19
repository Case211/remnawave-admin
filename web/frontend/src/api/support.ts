import client from './client'

export interface SupportQueues {
  wait_us: number
  mine: number
  late: number
  wait_client: number
  snoozed: number
  all: number
  sla_minutes: number
}

export interface SupportTicket {
  id: number
  bot_user_id: number
  telegram_id: number | null
  customer_name: string | null
  title: string
  status: string
  priority: string
  messages_count: number
  last_message_at: string | null
  last_message_from: 'user' | 'admin' | null
  last_message_text: string | null
  first_response_at: string | null
  waiting_since: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
  assignee_id: number | null
  snooze_to: string | null
  unread_count?: number
  customer_note?: string | null
}

export interface SupportMessage {
  id: number
  ticket_id: number
  is_from_admin: boolean
  author_name: string | null
  text: string
  has_media: boolean
  media_type: string | null
  created_at: string
}

export interface SupportTicketList {
  items: SupportTicket[]
  total: number
  limit: number
  offset: number
}

export const supportApi = {
  getQueues: async (): Promise<SupportQueues> => {
    const { data } = await client.get('/support/queues')
    return data
  },

  listTickets: async (params: {
    queue: string
    search?: string
    priority?: string
    limit?: number
    offset?: number
  }): Promise<SupportTicketList> => {
    const { data } = await client.get('/support/tickets', { params })
    return data
  },

  getTicket: async (id: number): Promise<{ ticket: SupportTicket; messages: SupportMessage[] }> => {
    const { data } = await client.get(`/support/tickets/${id}`)
    return data
  },

  reply: async (id: number, messageText: string, close = false) => {
    const { data } = await client.post(`/support/tickets/${id}/reply`, { message_text: messageText, close })
    return data as { success: boolean; closed: boolean }
  },

  setStatus: async (id: number, status: string) => {
    const { data } = await client.post(`/support/tickets/${id}/status`, { status })
    return data
  },

  setPriority: async (id: number, priority: string) => {
    const { data } = await client.post(`/support/tickets/${id}/priority`, { priority })
    return data
  },

  assign: async (id: number) => {
    const { data } = await client.post(`/support/tickets/${id}/assign`)
    return data as { success: boolean; assignee_id: number }
  },

  unassign: async (id: number) => {
    await client.delete(`/support/tickets/${id}/assign`)
  },

  markRead: async (id: number, lastMessageId = 0) => {
    await client.post(`/support/tickets/${id}/read`, { last_message_id: lastMessageId })
  },

  sync: async (full = false) => {
    const { data } = await client.post('/support/sync', null, { params: { full } })
    return data as { scanned: number; updated: number; skipped: number }
  },
}
