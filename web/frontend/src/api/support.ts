import client from './client'

export interface SupportQueues {
  sla_enabled: boolean
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

export interface SupportWatcher {
  admin_id: number
  username: string
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

  getTicket: async (id: number): Promise<{ ticket: SupportTicket; messages: SupportMessage[]; watchers: SupportWatcher[] }> => {
    const { data } = await client.get(`/support/tickets/${id}`)
    return data
  },

  reply: async (
    id: number,
    messageText: string,
    close = false,
    extra?: { set_status?: string | null; add_tag_id?: number | null },
  ) => {
    const { data } = await client.post(`/support/tickets/${id}/reply`, {
      message_text: messageText,
      close,
      set_status: extra?.set_status ?? undefined,
      add_tag_id: extra?.add_tag_id ?? undefined,
    })
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

  attach: async (id: number, file: File, messageText = '', close = false) => {
    const form = new FormData()
    form.append('file', file)
    form.append('message_text', messageText)
    form.append('close', String(close))
    const { data } = await client.post(`/support/tickets/${id}/attach`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data as { success: boolean; media_type: string; warnings: string[] }
  },

  /** Вложение приходит потоком через админку: ссылка бота содержит его токен. */
  mediaBlobUrl: async (ticketId: number, messageId: number): Promise<string> => {
    const { data } = await client.get(`/support/tickets/${ticketId}/messages/${messageId}/media`, {
      responseType: 'blob',
    })
    return URL.createObjectURL(data as Blob)
  },

  presence: async (id: number): Promise<{ watchers: SupportWatcher[] }> => {
    const { data } = await client.post(`/support/tickets/${id}/presence`)
    return data
  },

  sync: async (full = false) => {
    const { data } = await client.post('/support/sync', null, { params: { full } })
    return data as { scanned: number; updated: number; skipped: number }
  },
}

export interface SupportMacro {
  id: number
  title: string
  body: string
  shortcut: string | null
  set_status: string | null
  add_tag_id: number | null
  sort_order: number
}

export interface SupportTag {
  id: number
  name: string
  color: string
}

export interface SupportMetrics {
  days: number
  sla_enabled: boolean
  sla_minutes: number
  created: number
  answered: number
  still_waiting: number
  closed: number
  avg_first_response_minutes: number
  breached: number | null
  breached_percent: number | null
  by_admin: Array<{ admin_id: number; tickets: number }>
}

export const supportExtraApi = {
  listMacros: async (): Promise<{ items: SupportMacro[] }> => {
    const { data } = await client.get('/support/macros')
    return data
  },

  listTags: async (): Promise<{ items: SupportTag[] }> => {
    const { data } = await client.get('/support/tags')
    return data
  },

  attachTag: async (ticketId: number, tagId: number) => {
    await client.post(`/support/tickets/${ticketId}/tags/${tagId}`)
  },

  detachTag: async (ticketId: number, tagId: number) => {
    await client.delete(`/support/tickets/${ticketId}/tags/${tagId}`)
  },

  snooze: async (ticketId: number, minutes: number) => {
    const { data } = await client.post(`/support/tickets/${ticketId}/snooze`, { minutes })
    return data as { success: boolean; snooze_to: string }
  },

  unsnooze: async (ticketId: number) => {
    await client.delete(`/support/tickets/${ticketId}/snooze`)
  },

  metrics: async (days = 7): Promise<SupportMetrics> => {
    const { data } = await client.get('/support/metrics', { params: { days } })
    return data
  },
}
