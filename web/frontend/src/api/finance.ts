import client from './client'

export interface FinanceCategory {
  id: number
  name: string
  kind: 'expense' | 'income'
  color: string | null
  icon: string | null
  is_system: boolean
  sort_order: number
}

export interface FinanceProvider {
  id: number
  name: string
  url: string | null
  favicon_url: string | null
  notes: string | null
  archived?: boolean
  items_count?: number
}

export interface FinanceItem {
  id: number
  kind: 'expense' | 'income'
  name: string
  category_id: number | null
  category_name: string | null
  category_color: string | null
  category_icon: string | null
  provider_id: number | null
  provider_name: string | null
  node_uuid: string | null
  node_name: string | null
  currency: string
  amount: number
  billing_cycle: 'monthly' | 'yearly' | 'once' | 'days'
  cycle_days: number | null
  next_due_at: string | null
  url: string | null
  notes: string | null
  status: 'active' | 'archived'
  monthly_equivalent: number
  days_left?: number
  is_overdue?: boolean
}

export interface FinancePayment {
  id: number
  item_id: number | null
  item_name: string
  kind: 'expense' | 'income'
  paid_at: string
  amount: number
  currency: string
  rate_rub: number | null
  amount_rub: number
  comment: string | null
  source: string
}

export interface FinanceRate {
  currency: string
  rate_rub: number
  is_manual: boolean
  updated_at: string
}

export interface FinanceSummary {
  base_currency: string
  monthly: { month: string; expense: number; income: number; net: number }[]
  by_category: { category: string; color: string; monthly: number }[]
  by_currency: { currency: string; expense_monthly: number; income_monthly: number }[]
  recurring: { expense: number; income: number; net: number }
  this_month?: {
    month: string | null
    expense: number
    income: number
    net: number
    expense_actual: number
    income_actual: number
    expense_upcoming: number
    income_upcoming: number
  }
}

export interface ItemPayload {
  name: string
  kind: string
  category_id?: number | null
  provider_id?: number | null
  node_uuid?: string | null
  currency: string
  amount: number
  billing_cycle: string
  cycle_days?: number | null
  next_due_at?: string | null
  url?: string | null
  notes?: string | null
  status?: string
}

export interface AdapterField {
  name: string
  label: string
  type: 'text' | 'password' | 'url'
  required: boolean
  placeholder: string | null
  help: string | null
}

export interface HosterAdapter {
  slug: string
  title: string
  description: string
  needs_base_url: boolean
  fields: AdapterField[]
}

export interface FinanceService {
  name: string
  status: string | null
  price: number | null
  currency: string | null
  period: string | null
  next_due_at: string | null
  external_id: string | null
  specs: string | null
  ips?: string[] | null
  // автосопоставление с нодой панели (по IP/имени, считается на бэке)
  node_uuid?: string | null
  node_name?: string | null
}

export interface FinanceAccount {
  id: number
  provider_id: number
  provider_name: string
  provider_url: string | null
  adapter: string
  base_url: string | null
  auto_sync: boolean
  low_balance_threshold: number | null
  balance: number | null
  balance_currency: string | null
  services: FinanceService[] | null
  last_sync_at: string | null
  last_sync_status: 'ok' | 'error' | null
  last_sync_error: string | null
}

export interface BalanceSnapshot {
  account_id: number
  snapshot_date: string
  balance: number
  currency: string
  provider_name: string
}

export interface NodeCost {
  node_uuid: string
  node_name: string
  monthly_cost: number
  traffic_gb: number
  cost_per_gb: number | null
  users: number
  cost_per_user: number | null
}

export interface NodeCosts {
  base_currency: string
  days: number
  unassigned_monthly: number
  items: NodeCost[]
}

export interface AccountTestResult {
  status: 'ok' | 'error'
  error?: string
  balance?: number | null
  currency?: string | null
  services?: FinanceService[]
}

export const financeApi = {
  getSummary: async (months = 6): Promise<FinanceSummary> =>
    (await client.get('/finance/summary', { params: { months } })).data,

  getUpcoming: async (days = 30): Promise<{ items: FinanceItem[] }> =>
    (await client.get('/finance/upcoming', { params: { days } })).data,

  listItems: async (params: Record<string, string | number | undefined> = {}): Promise<{ items: FinanceItem[] }> =>
    (await client.get('/finance/items', { params })).data,

  createItem: async (data: ItemPayload): Promise<FinanceItem> =>
    (await client.post('/finance/items', data)).data,

  updateItem: async (id: number, data: Partial<ItemPayload>): Promise<FinanceItem> =>
    (await client.patch(`/finance/items/${id}`, data)).data,

  deleteItem: async (id: number): Promise<void> => {
    await client.delete(`/finance/items/${id}`)
  },

  markPaid: async (id: number, data: { amount?: number; paid_at?: string; comment?: string } = {}): Promise<FinanceItem> =>
    (await client.post(`/finance/items/${id}/paid`, data)).data,

  skipCycle: async (id: number): Promise<FinanceItem> =>
    (await client.post(`/finance/items/${id}/skip`)).data,

  listPayments: async (params: Record<string, string | number | undefined> = {}): Promise<{ items: FinancePayment[] }> =>
    (await client.get('/finance/payments', { params })).data,

  createPayment: async (data: {
    item_id?: number | null; item_name?: string; kind: string
    paid_at: string; amount: number; currency: string; comment?: string
  }): Promise<{ id: number }> =>
    (await client.post('/finance/payments', data)).data,

  deletePayment: async (id: number): Promise<void> => {
    await client.delete(`/finance/payments/${id}`)
  },

  /** Правка операции на месте; comment: null очищает комментарий. */
  updatePayment: async (id: number, data: {
    item_name?: string; kind?: string; paid_at?: string
    amount?: number; currency?: string; comment?: string | null
  }): Promise<FinancePayment> =>
    (await client.patch(`/finance/payments/${id}`, data)).data,

  listCategories: async (): Promise<{ items: FinanceCategory[] }> =>
    (await client.get('/finance/categories')).data,

  createCategory: async (data: { name: string; kind: string; color?: string; icon?: string }): Promise<FinanceCategory> =>
    (await client.post('/finance/categories', data)).data,

  updateCategory: async (id: number, data: { name?: string; color?: string; icon?: string; sort_order?: number }): Promise<void> => {
    await client.patch(`/finance/categories/${id}`, data)
  },

  deleteCategory: async (id: number): Promise<void> => {
    await client.delete(`/finance/categories/${id}`)
  },

  listProviders: async (): Promise<{ items: FinanceProvider[] }> =>
    (await client.get('/finance/providers')).data,

  createProvider: async (data: { name: string; url?: string; notes?: string }): Promise<FinanceProvider> =>
    (await client.post('/finance/providers', data)).data,

  updateProvider: async (id: number, data: { name?: string; url?: string; notes?: string; archived?: boolean }): Promise<{ status: string; archived_items?: number }> =>
    (await client.patch(`/finance/providers/${id}`, data)).data,

  deleteProvider: async (id: number): Promise<void> => {
    await client.delete(`/finance/providers/${id}`)
  },

  getNodeCosts: async (days = 30): Promise<NodeCosts> =>
    (await client.get('/finance/node-costs', { params: { days } })).data,

  listRates: async (): Promise<{ items: FinanceRate[]; base_currency: string }> =>
    (await client.get('/finance/rates')).data,

  setRate: async (currency: string, rate_rub: number): Promise<void> => {
    await client.put(`/finance/rates/${currency}`, { rate_rub, is_manual: true })
  },

  refreshRates: async (): Promise<{ updated: number; items: FinanceRate[] }> =>
    (await client.post('/finance/rates/refresh')).data,
  /** Снять ручной флаг с курса и сразу подтянуть его из внешнего источника. */
  resetRateToAuto: async (currency: string): Promise<{ updated: number; items: FinanceRate[] }> =>
    (await client.post(`/finance/rates/${currency}/auto`)).data,

  importFromPanel: async (currency = 'USD'): Promise<{ providers: number; items: number; payments: number; retagged: number; skipped: number; errors: string[] }> =>
    (await client.post('/finance/import-panel', null, { params: { currency } })).data,

  listAdapters: async (): Promise<{ items: HosterAdapter[] }> =>
    (await client.get('/finance/adapters')).data,

  listAccounts: async (): Promise<{ items: FinanceAccount[] }> =>
    (await client.get('/finance/accounts')).data,

  createAccount: async (data: {
    provider_id: number; adapter: string; base_url?: string | null
    credentials: Record<string, string>; auto_sync?: boolean; low_balance_threshold?: number | null
  }): Promise<FinanceAccount> =>
    (await client.post('/finance/accounts', data)).data,

  updateAccount: async (id: number, data: {
    base_url?: string | null; credentials?: Record<string, string>
    auto_sync?: boolean; low_balance_threshold?: number | null
  }): Promise<FinanceAccount> =>
    (await client.patch(`/finance/accounts/${id}`, data)).data,

  deleteAccount: async (id: number): Promise<void> => {
    await client.delete(`/finance/accounts/${id}`)
  },

  testAccount: async (data: {
    account_id?: number; adapter?: string; base_url?: string | null
    credentials?: Record<string, string>
  }): Promise<AccountTestResult> =>
    (await client.post('/finance/accounts/test', data)).data,

  syncAccount: async (id: number): Promise<{ status: string; error?: string; balance?: number; currency?: string; services?: number; due_dates_updated?: number }> =>
    (await client.post(`/finance/accounts/${id}/sync`)).data,

  listSnapshots: async (days = 90): Promise<{ items: BalanceSnapshot[] }> =>
    (await client.get('/finance/snapshots', { params: { days } })).data,

  getBedolagaIncome: async (): Promise<BedolagaIncome> =>
    (await client.get('/finance/bedolaga-income')).data,
}

export interface BedolagaIncome {
  currency: string
  total: { deposit_income: number; subscription_income: number; profit: number }
  today: { deposit_income: number; transactions_count: number }
  by_payment_method: Record<string, number>
}
