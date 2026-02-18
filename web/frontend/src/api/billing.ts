import client from './client'

export interface Provider {
  uuid: string
  name: string
  faviconLink: string | null
  loginUrl: string | null
  billingHistory?: { totalAmount: number; totalBills: number }
  billingNodes?: unknown[]
}

export interface BillingRecord {
  uuid: string
  provider: { uuid: string; name: string }
  amount: number
  billedAt: string
  createdAt: string
}

export interface BillingNode {
  uuid: string
  provider: { uuid: string; name: string }
  node: { uuid: string; name: string; countryCode: string }
  nextBillingAt: string
  createdAt: string
}

export interface BillingNodesResponse {
  billingNodes: BillingNode[]
  totalBillingNodes: number
  stats: {
    upcomingNodesCount: number
    currentMonthPayments: number | string
    totalSpent: number | string
  }
}

export const billingApi = {
  getProviders: async (): Promise<Provider[]> => {
    const { data } = await client.get('/billing/providers')
    return Array.isArray(data?.items) ? data.items : []
  },
  createProvider: async (payload: { name: string; faviconLink?: string; loginUrl?: string }) => {
    const { data } = await client.post('/billing/providers', payload)
    return data
  },
  updateProvider: async (payload: { uuid: string; name?: string; faviconLink?: string; loginUrl?: string }) => {
    const { data } = await client.patch('/billing/providers', payload)
    return data
  },
  deleteProvider: async (uuid: string) => {
    await client.delete(`/billing/providers/${uuid}`)
  },
  getHistory: async (): Promise<BillingRecord[]> => {
    const { data } = await client.get('/billing/history')
    return Array.isArray(data?.items) ? data.items : []
  },
  createRecord: async (payload: { providerUuid: string; amount: number; billedAt: string }) => {
    const { data } = await client.post('/billing/history', payload)
    return data
  },
  deleteRecord: async (uuid: string) => {
    await client.delete(`/billing/history/${uuid}`)
  },
  getNodes: async (): Promise<BillingNodesResponse> => {
    const { data } = await client.get('/billing/nodes')
    return data
  },
  createNode: async (payload: { providerUuid: string; nodeUuid: string; nextBillingAt?: string }) => {
    const { data } = await client.post('/billing/nodes', payload)
    return data
  },
  updateNodes: async (payload: { uuids: string[]; nextBillingAt: string }) => {
    const { data } = await client.patch('/billing/nodes', payload)
    return data
  },
  deleteNode: async (uuid: string) => {
    await client.delete(`/billing/nodes/${uuid}`)
  },
}
