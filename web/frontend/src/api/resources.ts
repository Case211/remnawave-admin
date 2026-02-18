import client from './client'

// Types
export interface ApiToken {
  uuid: string
  token: string
  tokenName: string
  createdAt: string
}

export interface Template {
  uuid: string
  name: string
  templateType: string // XRAY_JSON, XRAY_BASE64, MIHOMO, STASH, CLASH, SINGBOX
  templateJson: Record<string, unknown> | null
  viewPosition: number
  createdAt: string
  updatedAt: string
}

export interface Snippet {
  name: string
  snippet: unknown[] | Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface ConfigProfile {
  uuid: string
  name: string
  viewPosition: number
  createdAt: string
  updatedAt: string
}

// API functions
export const resourcesApi = {
  // Tokens
  getTokens: async (): Promise<ApiToken[]> => {
    const { data } = await client.get('/tokens')
    return data.items || []
  },
  createToken: async (tokenName: string) => {
    const { data } = await client.post('/tokens', { tokenName })
    return data
  },
  deleteToken: async (uuid: string) => {
    await client.delete(`/tokens/${uuid}`)
  },

  // Templates
  getTemplates: async (): Promise<Template[]> => {
    const { data } = await client.get('/templates')
    return data.items || []
  },
  getTemplate: async (uuid: string): Promise<Template> => {
    const { data } = await client.get(`/templates/${uuid}`)
    return data
  },
  createTemplate: async (name: string, templateType: string) => {
    const { data } = await client.post('/templates', { name, templateType })
    return data
  },
  updateTemplate: async (uuid: string, updates: { name?: string; templateJson?: Record<string, unknown> }) => {
    const { data } = await client.patch(`/templates/${uuid}`, updates)
    return data
  },
  deleteTemplate: async (uuid: string) => {
    await client.delete(`/templates/${uuid}`)
  },
  reorderTemplates: async (items: { uuid: string; viewPosition: number }[]) => {
    await client.post('/templates/reorder', { items })
  },

  // Snippets
  getSnippets: async (): Promise<Snippet[]> => {
    const { data } = await client.get('/snippets')
    return data.items || []
  },
  createSnippet: async (name: string, snippet: unknown) => {
    const { data } = await client.post('/snippets', { name, snippet })
    return data
  },
  updateSnippet: async (name: string, snippet: unknown) => {
    const { data } = await client.patch('/snippets', { name, snippet })
    return data
  },
  deleteSnippet: async (name: string) => {
    await client.delete('/snippets', { data: { name } })
  },

  // Config Profiles
  getConfigProfiles: async (): Promise<ConfigProfile[]> => {
    const { data } = await client.get('/config-profiles')
    return data.items || []
  },
  getConfigProfile: async (uuid: string) => {
    const { data } = await client.get(`/config-profiles/${uuid}`)
    return data
  },
  getComputedConfig: async (uuid: string) => {
    const { data } = await client.get(`/config-profiles/${uuid}/computed-config`)
    return data
  },
}
