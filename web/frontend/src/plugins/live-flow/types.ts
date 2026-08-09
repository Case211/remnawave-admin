/** Types for the live-flow plugin API (``/api/v2/plugins/live_flow``). */

export interface FlowNode {
  uuid: string
  name: string
  users: number
  tx_mbps: number
  rx_mbps: number
  connected: boolean
  profile: string | null
  inbounds: string[]
  sinks: string[]
}

/** Аутбаунд из конфиг-профиля: kind определяет род блока на схеме. */
export interface FlowSink {
  tag: string
  title: string
  kind: 'internet' | 'block' | 'warp' | 'chain'
}

export interface FlowData {
  total_users: number
  nodes: FlowNode[]
  sinks: FlowSink[]
}
