import client from './client'

/** Запись справочника ASN (РФ, из RIPE). Синхронизация — в «Настройки → Синхронизация». */
export interface ASNRecord {
  asn: number
  org_name: string
  org_name_en: string | null
  provider_type: string | null
  region: string | null
  city: string | null
  country_code: string
  description: string | null
  is_active: boolean
}

export interface ASNStats {
  total: number
  by_type: Record<string, number>
}

export const asnApi = {
  search: async (orgName: string): Promise<ASNRecord[]> => {
    const { data } = await client.get('/asn/search', { params: { org_name: orgName } })
    return data.items
  },

  getByType: async (providerType: string): Promise<ASNRecord[]> => {
    const { data } = await client.get(`/asn/by-type/${encodeURIComponent(providerType)}`)
    return data.items
  },

  getStats: async (): Promise<ASNStats> => {
    const { data } = await client.get('/asn/stats')
    return data
  },

  getAsn: async (asn: number): Promise<ASNRecord> => {
    const { data } = await client.get(`/asn/${asn}`)
    return data
  },
}
