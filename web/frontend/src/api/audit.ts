import client from './client'

export interface AuditLogEntry {
  id: number
  admin_id: number | null
  admin_username: string
  action: string
  resource: string | null
  resource_id: string | null
  details: string | null
  ip_address: string | null
  created_at: string | null
}

export interface AuditLogParams {
  limit?: number
  offset?: number
  admin_id?: number
  action?: string
  resource?: string
  resource_id?: string
  date_from?: string
  date_to?: string
  search?: string
}

export interface AuditStats {
  total: number
  today: number
  by_resource: Record<string, number>
  by_admin: { username: string; count: number }[]
}

export const auditApi = {
  list: async (params?: AuditLogParams): Promise<{ items: AuditLogEntry[]; total: number }> => {
    const { data } = await client.get('/audit', { params })
    return data
  },

  actions: async (): Promise<string[]> => {
    const { data } = await client.get('/audit/actions')
    return data
  },

  resourceHistory: async (
    resource: string,
    resourceId: string,
    limit = 50,
  ): Promise<{ items: AuditLogEntry[] }> => {
    const { data } = await client.get(`/audit/resource/${resource}/${resourceId}`, {
      params: { limit },
    })
    return data
  },

  stats: async (): Promise<AuditStats> => {
    const { data } = await client.get('/audit/stats')
    return data
  },
}
