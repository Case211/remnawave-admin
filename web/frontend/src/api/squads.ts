import client from './client'

export interface InternalSquad {
  uuid: string
  name: string
  viewPosition?: number
  info?: { membersCount: number; inboundsCount: number }
  inbounds?: { uuid: string; tag: string; type: string }[]
  createdAt?: string
  updatedAt?: string
  allowed_actions?: string[] | null
}

export interface ExternalSquad {
  uuid: string
  name: string
  viewPosition?: number
  info?: { membersCount: number }
  createdAt?: string
  updatedAt?: string
  allowed_actions?: string[] | null
}

export const squadsApi = {
  listInternal: async (): Promise<InternalSquad[]> => {
    const { data } = await client.get('/squads/internal')
    return Array.isArray(data) ? data : []
  },

  createInternal: async (name: string, inbounds: string[] = []): Promise<InternalSquad> => {
    const { data } = await client.post('/squads/internal', { name, inbounds })
    return data
  },

  updateInternal: async (uuid: string, payload: { name?: string; inbounds?: string[] }): Promise<InternalSquad> => {
    const { data } = await client.patch(`/squads/internal/${uuid}`, payload)
    return data
  },

  deleteInternal: async (uuid: string): Promise<void> => {
    await client.delete(`/squads/internal/${uuid}`)
  },

  listExternal: async (): Promise<ExternalSquad[]> => {
    const { data } = await client.get('/squads/external')
    return Array.isArray(data) ? data : []
  },

  createExternal: async (name: string): Promise<ExternalSquad> => {
    const { data } = await client.post('/squads/external', { name })
    return data
  },

  updateExternal: async (uuid: string, payload: { name?: string }): Promise<ExternalSquad> => {
    const { data } = await client.patch(`/squads/external/${uuid}`, payload)
    return data
  },

  deleteExternal: async (uuid: string): Promise<void> => {
    await client.delete(`/squads/external/${uuid}`)
  },

  listInbounds: async (): Promise<{ uuid: string; tag: string; type: string }[]> => {
    const { data } = await client.get('/squads/inbounds')
    return Array.isArray(data) ? data : []
  },
}

export interface SubscriptionInfo {
  isFound: boolean
  user?: {
    shortUuid: string
    daysLeft: number
    trafficUsed: string
    trafficLimit: string
    lifetimeTrafficUsed: string
    username: string
    expiresAt: string
    isActive: boolean
    userStatus: string
    trafficLimitStrategy: string
  }
  links?: string[]
  subscriptionUrl?: string
}

export const subscriptionApi = {
  getInfo: async (userUuid: string): Promise<SubscriptionInfo> => {
    const { data } = await client.get(`/users/${userUuid}/subscription-info`)
    return data
  },
}
