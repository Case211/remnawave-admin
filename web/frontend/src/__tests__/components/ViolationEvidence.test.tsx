/**
 * #306: какие подключения дали нарушение и где был клиент вокруг него.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import {
  evidenceGroups,
  ViolationAddressesCard,
  ViolationEvidenceCard,
} from '@/components/violations/ViolationEvidence'
import client from '@/api/client'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

const RAW = {
  breakdown: {
    geo: {
      score: 90,
      evidence: [
        { ip: '1.1.1.1', country: 'RU', city: 'Moscow', node_name: 'Germany W', kind: 'simultaneous',
          connected_at: '2026-09-30T11:01:00+00:00' },
        { ip: '2.2.2.2', country: 'KZ', city: 'Almaty', node_uuid: 'abcdef1234', kind: 'simultaneous',
          connected_at: '2026-09-30T11:07:00+00:00' },
      ],
    },
    temporal: { score: 0, evidence: [] },
    asn: { score: 25, evidence: [{ ip: '5.5.5.5', connection_type: 'datacenter', asn_org: 'Hetzner' }] },
  },
}

describe('evidenceGroups', () => {
  it('is empty for old violations without a breakdown', () => {
    expect(evidenceGroups(null)).toEqual([])
    expect(evidenceGroups({})).toEqual([])
  })

  it('groups evidence by what caught it and drops empty groups', () => {
    expect(evidenceGroups(RAW).map((g) => [g.key, g.entries.length])).toEqual([['geoSimultaneous', 2], ['asn', 1]])
  })
})

describe('ViolationEvidenceCard', () => {
  it('names the addresses, countries and nodes behind the violation', () => {
    render(<ViolationEvidenceCard rawData={RAW} />)
    expect(screen.getByText('Подключения, давшие нарушение')).toBeInTheDocument()
    expect(screen.getByText('Одновременно из разных стран')).toBeInTheDocument()
    expect(screen.getByText('1.1.1.1')).toBeInTheDocument()
    expect(screen.getByText('KZ · Almaty')).toBeInTheDocument()
    expect(screen.getByText('→ Germany W')).toBeInTheDocument()
    // Без имени ноды — начало uuid, а не пустота
    expect(screen.getByText('→ abcdef12')).toBeInTheDocument()
    expect(screen.getByText('Hetzner')).toBeInTheDocument()
  })

  it('renders nothing without evidence', () => {
    const { container } = render(<ViolationEvidenceCard rawData={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ViolationAddressesCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows one line per address around the violation', async () => {
    vi.mocked(client.get).mockResolvedValue({
      data: {
        window_minutes: 60,
        items: [{
          ip: '2.2.2.2', first_seen: '2026-09-30T11:01:00+00:00', last_seen: '2026-09-30T11:20:00+00:00',
          connections: 3, nodes: ['Germany W', 'NL'], country_code: 'KZ', city: null,
          connection_type: 'mobile', asn_org: 'Beeline KZ',
        }],
      },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    render(
      <QueryClientProvider client={queryClient}>
        <ViolationAddressesCard violationId={5} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Адреса вокруг нарушения (±60 мин)')).toBeInTheDocument()
    expect(client.get).toHaveBeenCalledWith('/violations/5/addresses')
    expect(screen.getByText('подключений: 3')).toBeInTheDocument()
    expect(screen.getByText('узлы: Germany W, NL')).toBeInTheDocument()
    expect(screen.getByText('Beeline KZ')).toBeInTheDocument()
  })
})
