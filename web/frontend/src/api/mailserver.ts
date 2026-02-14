/**
 * Mail Server API module.
 */
import client from './client'

// ── Types ────────────────────────────────────────────────────────

export interface MailDomain {
  id: number
  domain: string
  is_active: boolean
  dkim_selector: string
  dkim_public_key: string | null
  from_name: string | null
  inbound_enabled: boolean
  outbound_enabled: boolean
  max_send_per_hour: number
  dns_mx_ok: boolean
  dns_spf_ok: boolean
  dns_dkim_ok: boolean
  dns_dmarc_ok: boolean
  dns_ptr_ok: boolean
  dns_checked_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DnsRecord {
  record_type: string
  host: string
  value: string
  purpose: string
  is_configured: boolean
  current_value: string | null
}

export interface DnsCheckResult {
  domain: string
  mx_ok: boolean
  spf_ok: boolean
  dkim_ok: boolean
  dmarc_ok: boolean
}

export interface EmailQueueItem {
  id: number
  from_email: string
  to_email: string
  subject: string
  status: string
  category: string | null
  priority: number
  attempts: number
  max_attempts: number
  last_error: string | null
  message_id: string | null
  created_at: string | null
  sent_at: string | null
}

export interface QueueStats {
  pending: number
  sending: number
  sent: number
  failed: number
  total: number
}

export interface InboxItem {
  id: number
  mail_from: string | null
  rcpt_to: string
  from_header: string | null
  subject: string | null
  date_header: string | null
  is_read: boolean
  is_spam: boolean
  has_attachments: boolean
  attachment_count: number
  created_at: string | null
}

export interface InboxDetail extends InboxItem {
  to_header: string | null
  message_id: string | null
  in_reply_to: string | null
  body_text: string | null
  body_html: string | null
  remote_ip: string | null
  remote_hostname: string | null
  spam_score: number
}

export interface SmtpCredential {
  id: number
  username: string
  description: string | null
  is_active: boolean
  allowed_from_domains: string[]
  max_send_per_hour: number
  last_login_at: string | null
  last_login_ip: string | null
  created_at: string | null
  updated_at: string | null
}

// ── API ──────────────────────────────────────────────────────────

export const mailserverApi = {
  // ── Domains ───────────────────────────────────────────────────
  listDomains: async (): Promise<MailDomain[]> => {
    const { data } = await client.get('/mailserver/domains')
    return data
  },

  getDomain: async (id: number): Promise<MailDomain> => {
    const { data } = await client.get(`/mailserver/domains/${id}`)
    return data
  },

  createDomain: async (payload: {
    domain: string
    from_name?: string
    inbound_enabled?: boolean
    outbound_enabled?: boolean
    max_send_per_hour?: number
  }): Promise<MailDomain> => {
    const { data } = await client.post('/mailserver/domains', payload)
    return data
  },

  updateDomain: async (id: number, payload: Partial<MailDomain>): Promise<MailDomain> => {
    const { data } = await client.put(`/mailserver/domains/${id}`, payload)
    return data
  },

  deleteDomain: async (id: number): Promise<void> => {
    await client.delete(`/mailserver/domains/${id}`)
  },

  checkDns: async (id: number): Promise<DnsCheckResult> => {
    const { data } = await client.post(`/mailserver/domains/${id}/check-dns`)
    return data
  },

  getDnsRecords: async (id: number): Promise<DnsRecord[]> => {
    const { data } = await client.get(`/mailserver/domains/${id}/dns-records`)
    return data
  },

  // ── Queue ─────────────────────────────────────────────────────
  listQueue: async (params?: {
    status?: string
    category?: string
    limit?: number
    offset?: number
  }): Promise<EmailQueueItem[]> => {
    const { data } = await client.get('/mailserver/queue', { params })
    return data
  },

  getQueueStats: async (): Promise<QueueStats> => {
    const { data } = await client.get('/mailserver/queue/stats')
    return data
  },

  retryQueueItem: async (id: number): Promise<void> => {
    await client.post(`/mailserver/queue/${id}/retry`)
  },

  cancelQueueItem: async (id: number): Promise<void> => {
    await client.post(`/mailserver/queue/${id}/cancel`)
  },

  clearOldQueue: async (days?: number): Promise<void> => {
    await client.delete('/mailserver/queue', { params: { days: days || 30 } })
  },

  // ── Inbox ─────────────────────────────────────────────────────
  listInbox: async (params?: {
    is_read?: boolean
    limit?: number
    offset?: number
  }): Promise<InboxItem[]> => {
    const { data } = await client.get('/mailserver/inbox', { params })
    return data
  },

  getInboxItem: async (id: number): Promise<InboxDetail> => {
    const { data } = await client.get(`/mailserver/inbox/${id}`)
    return data
  },

  markRead: async (ids: number[]): Promise<void> => {
    await client.post('/mailserver/inbox/mark-read', { ids })
  },

  deleteInboxItem: async (id: number): Promise<void> => {
    await client.delete(`/mailserver/inbox/${id}`)
  },

  // ── Compose / Send ────────────────────────────────────────────
  sendEmail: async (payload: {
    to_email: string
    subject: string
    body_text?: string
    body_html?: string
    from_email?: string
    from_name?: string
    domain_id?: number
  }): Promise<{ ok: boolean; queue_id: number }> => {
    const { data } = await client.post('/mailserver/send', payload)
    return data
  },

  sendTestEmail: async (payload: {
    to_email: string
    subject?: string
    body_text?: string
    from_email?: string
    from_name?: string
  }): Promise<{ ok: boolean; queue_id: number }> => {
    const { data } = await client.post('/mailserver/send/test', payload)
    return data
  },

  // ── SMTP Credentials ──────────────────────────────────────────
  listSmtpCredentials: async (): Promise<SmtpCredential[]> => {
    const { data } = await client.get('/mailserver/smtp-credentials')
    return data
  },

  createSmtpCredential: async (payload: {
    username: string
    password: string
    description?: string
    allowed_from_domains?: string[]
    max_send_per_hour?: number
  }): Promise<SmtpCredential> => {
    const { data } = await client.post('/mailserver/smtp-credentials', payload)
    return data
  },

  updateSmtpCredential: async (id: number, payload: {
    password?: string
    description?: string
    is_active?: boolean
    allowed_from_domains?: string[]
    max_send_per_hour?: number
  }): Promise<SmtpCredential> => {
    const { data } = await client.put(`/mailserver/smtp-credentials/${id}`, payload)
    return data
  },

  deleteSmtpCredential: async (id: number): Promise<void> => {
    await client.delete(`/mailserver/smtp-credentials/${id}`)
  },
}
