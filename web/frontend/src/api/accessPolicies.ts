import client from './client'

export type ResourceType = 'node' | 'host' | 'squad'
export type ScopeType = 'uuid' | 'tag'
export type PolicyAction = 'view' | 'edit' | 'delete'

export interface PolicyRule {
  id?: number
  resource_type: ResourceType
  scope_type: ScopeType
  scope_value: string
  actions: PolicyAction[]
}

export interface PolicyListItem {
  id: number
  name: string
  description: string | null
  rules_count: number
  roles_count: number
  admins_count: number
}

export interface PolicyDetail {
  id: number
  name: string
  description: string | null
  rules: PolicyRule[]
  role_ids: number[]
  admin_ids: number[]
}

export const accessPoliciesApi = {
  list: async (): Promise<PolicyListItem[]> => {
    const { data } = await client.get('/access-policies')
    return Array.isArray(data) ? data : []
  },
  get: async (id: number): Promise<PolicyDetail> => {
    const { data } = await client.get(`/access-policies/${id}`)
    return data
  },
  create: async (body: {
    name: string
    description?: string | null
    rules: PolicyRule[]
  }): Promise<PolicyDetail> => {
    const { data } = await client.post('/access-policies', body)
    return data
  },
  update: async (id: number, body: {
    name?: string
    description?: string | null
    rules?: PolicyRule[]
  }): Promise<PolicyDetail> => {
    const { data } = await client.patch(`/access-policies/${id}`, body)
    return data
  },
  remove: async (id: number): Promise<void> => {
    await client.delete(`/access-policies/${id}`)
  },
  attachToRole: async (roleId: number, policyIds: number[]): Promise<void> => {
    await client.post(`/access-policies/_roles/${roleId}/attach`, { policy_ids: policyIds })
  },
  attachToAdmin: async (adminId: number, policyIds: number[]): Promise<void> => {
    await client.post(`/access-policies/_admins/${adminId}/attach`, { policy_ids: policyIds })
  },
}
