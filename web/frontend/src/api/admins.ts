import client from './client'

export interface Permission {
  resource: string
  action: string
}

export interface Role {
  id: number
  name: string
  display_name: string
  description: string | null
  is_system: boolean
  permissions: Permission[]
  permissions_count?: number
  admins_count?: number
  created_at?: string
}

export interface AdminAccount {
  id: number
  username: string
  telegram_id: number | null
  role_id: number | null
  role_name: string | null
  role_display_name: string | null
  max_users: number | null
  max_traffic_gb: number | null
  max_nodes: number | null
  max_hosts: number | null
  users_created: number
  traffic_used_bytes: number
  nodes_created: number
  hosts_created: number
  is_active: boolean
  is_generated_password: boolean
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AdminAccountCreate {
  username: string
  telegram_id?: number | null
  role_id: number
  password?: string | null
  max_users?: number | null
  max_traffic_gb?: number | null
  max_nodes?: number | null
  max_hosts?: number | null
}

export interface AdminAccountUpdate {
  username?: string
  telegram_id?: number | null
  role_id?: number
  password?: string | null
  max_users?: number | null
  max_traffic_gb?: number | null
  max_nodes?: number | null
  max_hosts?: number | null
  is_active?: boolean
}

export interface RoleCreate {
  name: string
  display_name: string
  description?: string | null
  permissions: Permission[]
}

export interface RoleUpdate {
  display_name?: string
  description?: string | null
  permissions?: Permission[]
}

export type AvailableResources = Record<string, string[]>

export const adminsApi = {
  list: async (): Promise<{ items: AdminAccount[]; total: number }> => {
    const { data } = await client.get('/admins')
    return data
  },

  get: async (id: number): Promise<AdminAccount> => {
    const { data } = await client.get(`/admins/${id}`)
    return data
  },

  create: async (payload: AdminAccountCreate): Promise<AdminAccount> => {
    const { data } = await client.post('/admins', payload)
    return data
  },

  update: async (id: number, payload: AdminAccountUpdate): Promise<AdminAccount> => {
    const { data } = await client.put(`/admins/${id}`, payload)
    return data
  },

  delete: async (id: number): Promise<void> => {
    await client.delete(`/admins/${id}`)
  },
}

export const rolesApi = {
  list: async (): Promise<Role[]> => {
    const { data } = await client.get('/roles')
    return data
  },

  get: async (id: number): Promise<Role> => {
    const { data } = await client.get(`/roles/${id}`)
    return data
  },

  getResources: async (): Promise<AvailableResources> => {
    const { data } = await client.get('/roles/resources')
    return data
  },

  create: async (payload: RoleCreate): Promise<Role> => {
    const { data } = await client.post('/roles', payload)
    return data
  },

  update: async (id: number, payload: RoleUpdate): Promise<Role> => {
    const { data } = await client.put(`/roles/${id}`, payload)
    return data
  },

  delete: async (id: number): Promise<void> => {
    await client.delete(`/roles/${id}`)
  },
}
