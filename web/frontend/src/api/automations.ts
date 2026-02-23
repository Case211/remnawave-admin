import client from './client'

// ── Types ────────────────────────────────────────────────────

export interface AutomationRule {
  id: number
  name: string
  description: string | null
  is_enabled: boolean
  category: 'users' | 'nodes' | 'violations' | 'system'
  trigger_type: 'event' | 'schedule' | 'threshold'
  trigger_config: Record<string, unknown>
  conditions: Record<string, unknown>[]
  action_type: string
  action_config: Record<string, unknown>
  last_triggered_at: string | null
  trigger_count: number
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AutomationRuleCreate {
  name: string
  description?: string | null
  is_enabled?: boolean
  category: string
  trigger_type: string
  trigger_config: Record<string, unknown>
  conditions?: Record<string, unknown>[]
  action_type: string
  action_config: Record<string, unknown>
}

export interface AutomationRuleUpdate {
  name?: string
  description?: string | null
  is_enabled?: boolean
  category?: string
  trigger_type?: string
  trigger_config?: Record<string, unknown>
  conditions?: Record<string, unknown>[]
  action_type?: string
  action_config?: Record<string, unknown>
}

export interface AutomationLogEntry {
  id: number
  rule_id: number
  rule_name: string | null
  triggered_at: string | null
  target_type: string | null
  target_id: string | null
  action_taken: string
  result: string
  details: Record<string, unknown> | null
}

export interface AutomationTemplate {
  id: string
  name: string
  description: string
  description_key?: string
  category: string
  trigger_type: string
  trigger_config: Record<string, unknown>
  conditions: Record<string, unknown>[]
  action_type: string
  action_config: Record<string, unknown>
}

export interface AutomationTestResult {
  rule_id: number
  would_trigger: boolean
  matching_targets: Record<string, unknown>[]
  estimated_actions: number
  details: string
}

export interface PaginatedRules {
  items: AutomationRule[]
  total: number
  page: number
  per_page: number
  pages: number
  total_active: number
  total_triggers: number
}

export interface PaginatedLogs {
  items: AutomationLogEntry[]
  total: number
  page: number
  per_page: number
  pages: number
}

// ── API ──────────────────────────────────────────────────────

export const automationsApi = {
  list: async (params?: {
    page?: number
    per_page?: number
    category?: string
    trigger_type?: string
    is_enabled?: boolean
  }): Promise<PaginatedRules> => {
    const { data } = await client.get('/automations', { params })
    return data
  },

  get: async (id: number): Promise<AutomationRule> => {
    const { data } = await client.get(`/automations/${id}`)
    return data
  },

  create: async (payload: AutomationRuleCreate): Promise<AutomationRule> => {
    const { data } = await client.post('/automations', payload)
    return data
  },

  update: async (id: number, payload: AutomationRuleUpdate): Promise<AutomationRule> => {
    const { data } = await client.put(`/automations/${id}`, payload)
    return data
  },

  toggle: async (id: number): Promise<AutomationRule> => {
    const { data } = await client.patch(`/automations/${id}/toggle`)
    return data
  },

  delete: async (id: number): Promise<void> => {
    await client.delete(`/automations/${id}`)
  },

  logs: async (params?: {
    page?: number
    per_page?: number
    rule_id?: number
    result?: string
    date_from?: string
    date_to?: string
  }): Promise<PaginatedLogs> => {
    const { data } = await client.get('/automations/log', { params })
    return data
  },

  templates: async (): Promise<AutomationTemplate[]> => {
    const { data } = await client.get('/automations/templates')
    return data
  },

  activateTemplate: async (templateId: string): Promise<AutomationRule> => {
    const { data } = await client.post(`/automations/templates/${templateId}/activate`)
    return data
  },

  test: async (id: number): Promise<AutomationTestResult> => {
    const { data } = await client.post(`/automations/${id}/test`)
    return data
  },
}
