import client from './client'

/** Единица проверки: оператор x округ x белый список. Ключ op_key приходит
 *  готовым ("mts|цфо|on") — собирать его из частей нельзя. Поля id/alive/
 *  region_label бэкенд дублирует ради записей, снятых до контракта 1.1. */
export interface BsOperator {
  op_key: string
  operator: string
  name: string
  region?: string | null
  region_code?: string | null
  dpi?: 'on' | 'off' | null
  channel_state: string
  probeable: boolean
  id: string
  alive: boolean
  region_label?: string | null
}

export interface BsAccount {
  balance_credits?: number
  balance_total?: number
  bonus_credits?: number
  tier?: string
}

export interface BsStatus {
  configured: boolean
  account: BsAccount | null
  /** Токен есть, но сервис отказал: истёк тариф, ключ отозван, обслуживание. */
  error?: string | null
}

export interface BsOpResult {
  op: string
  ok: boolean
  channel_state: string | null
  latency_ms: number | null
  tcp_is_tls: boolean | null
  error: string | null
}

export interface BsSummary {
  passed: number
  total: number
  operators: BsOpResult[]
  cost_credits: number | null
  skipped_dpi_off: string[]
}

export interface BsTargetSummary extends BsSummary {
  target: string
}

export interface BsNode {
  uuid: string
  name: string
  ip: string | null
  address: string | null
  agent_ip: string | null
}

export interface NodeBsSummary {
  passed: number
  total: number
  checked_at: string | null
}

export interface BsCheckRecord {
  id: number
  node_uuid: string
  checked_at: string
  passed: number
  total: number
  cost_credits: number | null
  result: { summary?: BsSummary; raw?: unknown }
  created_by: string | null
}

export interface BsHistoryRow {
  id: number
  node_uuid: string | null
  kind: string
  target: string | null
  passed: number
  total: number
  cost_credits: number | null
  result: any
  created_by: string | null
  checked_at: string
}

export interface HistorySave {
  kind: string
  target?: string
  passed: number
  total: number
  cost_credits?: number | null
  result: any
}

export interface BsJob {
  id: number
  name: string
  kind: string
  enabled: boolean
  interval_minutes: number
  config: any
  budget_daily: number
  alert: boolean
  last_run_at: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface BsJobInput {
  name: string
  kind: string
  enabled: boolean
  interval_minutes: number
  config: any
  budget_daily: number
  alert: boolean
}

export interface ProbeBody {
  target?: string
  targets?: string[]
  operators: string[]
  probes: Record<string, boolean>
  sni_hosts: string[]
  dpi: string
}

export interface ScanBody {
  cidr: string
  operators: string[]
  probes: Record<string, boolean>
  sni_hosts: string[]
  dpi: string
}

export interface VlessBody {
  raw_input: string
  selected_modems: string[]
  dpi: string
  core: string
}

export const bscheckApi = {
  async status(): Promise<BsStatus> {
    const { data } = await client.get('/bscheck/status'); return data
  },
  async setToken(token: string): Promise<{ configured: boolean }> {
    const { data } = await client.put('/bscheck/token', { token }); return data
  },
  async deleteToken(): Promise<{ configured: boolean }> {
    const { data } = await client.delete('/bscheck/token'); return data
  },
  async operators(): Promise<BsOperator[]> {
    const { data } = await client.get('/bscheck/operators'); return data.items
  },
  async nodes(): Promise<BsNode[]> {
    const { data } = await client.get('/bscheck/nodes'); return data.items
  },
  async summary(): Promise<Record<string, NodeBsSummary>> {
    const { data } = await client.get('/bscheck/summary'); return data.items
  },
  async nodeHistory(uuid: string): Promise<{ last: BsCheckRecord | null; history: BsCheckRecord[] }> {
    const { data } = await client.get(`/bscheck/nodes/${uuid}`); return data
  },
  async preview(body: ProbeBody): Promise<{ cost_credits: number }> {
    const { data } = await client.post('/bscheck/probe/preview', body); return data
  },
  async checkNode(uuid: string, body: ProbeBody): Promise<{ summary: BsSummary; checked_at: string | null }> {
    const { data } = await client.post(`/bscheck/nodes/${uuid}/check`, body); return data
  },
  async probeMulti(body: ProbeBody): Promise<{ targets: BsTargetSummary[]; cost_credits: number | null }> {
    const { data } = await client.post('/bscheck/probe', body); return data
  },
  async scanPreview(body: ScanBody): Promise<{ cost_credits: number; total_ips?: number }> {
    const { data } = await client.post('/bscheck/scans/preview', body); return data
  },
  async scanSubmit(body: ScanBody): Promise<{ scan_id: number; state: string }> {
    const { data } = await client.post('/bscheck/scans', body); return data
  },
  async scanStatus(id: number | string): Promise<any> {
    const { data } = await client.get(`/bscheck/scans/${id}`); return data
  },
  async vlessSubmit(body: VlessBody): Promise<{ test_id: number; cost_credits: number; n_servers?: number }> {
    const { data } = await client.post('/bscheck/vless', body); return data
  },
  async vlessStatus(id: number | string): Promise<any> {
    const { data } = await client.get(`/bscheck/vless/${id}`); return data
  },
  async scanCancel(id: number | string): Promise<{ state: string; done_ips?: number; total_ips?: number }> {
    const { data } = await client.post(`/bscheck/scans/${id}/cancel`); return data
  },
  async vlessCancel(id: number | string): Promise<{ cancelled: boolean; refunded_credits?: number }> {
    const { data } = await client.post(`/bscheck/vless/${id}/cancel`); return data
  },
  async saveHistory(payload: HistorySave): Promise<BsHistoryRow> {
    const { data } = await client.post('/bscheck/history', payload); return data
  },
  async history(kind?: string, limit = 50, jobId?: number): Promise<BsHistoryRow[]> {
    const { data } = await client.get('/bscheck/history', { params: { kind, limit, job_id: jobId } }); return data.items
  },
  async jobs(): Promise<BsJob[]> {
    const { data } = await client.get('/bscheck/jobs'); return data.items
  },
  async createJob(payload: BsJobInput): Promise<BsJob> {
    const { data } = await client.post('/bscheck/jobs', payload); return data
  },
  async updateJob(id: number, payload: BsJobInput): Promise<BsJob> {
    const { data } = await client.put(`/bscheck/jobs/${id}`, payload); return data
  },
  async deleteJob(id: number): Promise<void> {
    await client.delete(`/bscheck/jobs/${id}`)
  },
}
