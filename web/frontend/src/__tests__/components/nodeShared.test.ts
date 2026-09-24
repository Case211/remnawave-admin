import { describe, expect, it } from 'vitest'
import { agentStatus, countryFlag, nodeStatus, type NodeRow } from '@/components/nodes/nodeShared'

const base: NodeRow = {
  uuid: 'n', name: 'n', address: 'a', port: 2222, is_connected: true, is_disabled: false,
  users_online: 0, xray_version: null, traffic_total_bytes: 0, traffic_today_bytes: 0,
}

describe('общее для видов нод', () => {
  it('флаг страны', () => {
    expect(countryFlag('FI')).toBe('🇫🇮')
    expect(countryFlag('de')).toBe('🇩🇪')
    expect(countryFlag(null)).toBe('')
    expect(countryFlag('XYZ')).toBe('')
  })

  it('отключённая нода — «отключена», даже если панель считает её подключённой', () => {
    expect(nodeStatus({ ...base, is_disabled: true })).toBe('disabled')
    expect(nodeStatus(base)).toBe('online')
    expect(nodeStatus({ ...base, is_connected: false })).toBe('offline')
  })

  it('агент', () => {
    expect(agentStatus({ ...base, agent_v2_connected: true })).toBe('connected')
    expect(agentStatus({ ...base, has_agent_token: true })).toBe('offline')
    expect(agentStatus(base)).toBe('missing')
  })
})
