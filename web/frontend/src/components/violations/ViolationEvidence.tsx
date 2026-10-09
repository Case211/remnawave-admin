/**
 * Какие подключения дали нарушение и где был клиент вокруг него.
 *
 * Причина «одновременные подключения из разных стран» — строка текста; какие
 * два адреса, с каких узлов и с какого времени, админ видит здесь. Улики пишут
 * анализаторы в разбор скоринга (raw_data.breakdown.<анализатор>.evidence),
 * сводка адресов — отдельная ручка по окну вокруг нарушения.
 */
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Crosshair, Network } from '@/components/brand/icons'
import { useFormatters } from '@/lib/useFormatters'

export interface EvidenceEntry {
  ip: string | null
  node_uuid?: string | null
  node_name?: string | null
  connected_at?: string | null
  last_seen_at?: string | null
  country?: string | null
  city?: string | null
  asn_org?: string | null
  connection_type?: string | null
  kind?: string
  source?: string | null
}

export interface EvidenceGroup {
  key: 'geoSimultaneous' | 'geoTravel' | 'temporal' | 'asn'
  entries: EvidenceEntry[]
}

interface AddressSummaryItem {
  ip: string
  first_seen: string | null
  last_seen: string | null
  connections: number
  nodes: string[]
  country_code: string | null
  city: string | null
  connection_type: string | null
  asn_org: string | null
}

type Breakdown = Record<string, { evidence?: EvidenceEntry[] } | undefined>

/** Улики из разбора скоринга, по группам; пусто — разбора нет (старое нарушение). */
export function evidenceGroups(rawData: Record<string, unknown> | null | undefined): EvidenceGroup[] {
  const breakdown = rawData?.breakdown as Breakdown | undefined
  if (!breakdown || typeof breakdown !== 'object') return []
  const list = (part: string) => {
    const evidence = breakdown[part]?.evidence
    return Array.isArray(evidence) ? evidence : []
  }
  const groups: EvidenceGroup[] = [
    { key: 'geoSimultaneous', entries: list('geo').filter((e) => e.kind === 'simultaneous') },
    { key: 'geoTravel', entries: list('geo').filter((e) => e.kind === 'travel') },
    { key: 'temporal', entries: list('temporal') },
    { key: 'asn', entries: list('asn') },
  ]
  return groups.filter((g) => g.entries.length > 0)
}

function NetworkBadge({ type }: { type: string | null | undefined }) {
  const { t } = useTranslation()
  if (!type || type === 'unknown') return null
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--glass-border)] text-dark-200">
      {t(`violations.connectionTypes.${type}`, { defaultValue: type })}
    </span>
  )
}

function EvidenceRow({ entry }: { entry: EvidenceEntry }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const place = [entry.country, entry.city].filter(Boolean).join(' · ')
  const node = entry.node_name || entry.node_uuid?.slice(0, 8)
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs">
      <code className="font-mono text-dark-100">{entry.ip}</code>
      {place && <span className="text-dark-200">{place}</span>}
      <NetworkBadge type={entry.connection_type} />
      {entry.asn_org && (
        <span className="text-primary-400 truncate max-w-[160px]" title={entry.asn_org}>{entry.asn_org}</span>
      )}
      {entry.source && (
        <span className="text-dark-300" title={entry.source}>{t('violations.evidence.pool')}</span>
      )}
      {node && <span className="text-dark-300">→ {node}</span>}
      {entry.connected_at && (
        <span className="text-dark-400 sm:ml-auto">
          {t('violations.evidence.since', { time: formatDate(entry.connected_at) })}
        </span>
      )}
    </div>
  )
}

/** «Подключения, давшие нарушение» — по уликам анализаторов. */
export function ViolationEvidenceCard({ rawData }: { rawData: Record<string, unknown> | null | undefined }) {
  const { t } = useTranslation()
  const groups = evidenceGroups(rawData)
  if (groups.length === 0) return null
  return (
    <Card className="animate-fade-in-up border-red-500/30" style={{ animationDelay: '0.18s' }}>
      <CardContent className="p-4 space-y-3">
        <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider">
          <Crosshair className="w-4 h-4 inline mr-1" />
          {t('violations.evidence.title')}
        </h3>
        {groups.map((group) => (
          <div key={group.key} className="space-y-1.5">
            <p className="text-xs text-dark-300">{t(`violations.evidence.groups.${group.key}`)}</p>
            {group.entries.map((entry, i) => (
              <EvidenceRow key={`${entry.ip}-${entry.connected_at}-${i}`} entry={entry} />
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/** Сводка адресов вокруг нарушения: строка на адрес вместо сотен событий ленты. */
export function ViolationAddressesCard({ violationId }: { violationId: number }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const { data } = useQuery({
    queryKey: ['violation-addresses', violationId],
    queryFn: async () => {
      const response = await client.get(`/violations/${violationId}/addresses`)
      return response.data as { window_minutes: number; items: AddressSummaryItem[] }
    },
  })
  if (!data || data.items.length === 0) return null
  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.31s' }}>
      <CardContent className="p-4">
        <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
          <Network className="w-4 h-4 inline mr-1" />
          {t('violations.addresses.title', { minutes: data.window_minutes })}
        </h3>
        <div className="space-y-1.5">
          {data.items.map((item) => (
            <div key={item.ip} className="rounded bg-[var(--glass-bg)]/80 px-3 py-2 text-xs space-y-1">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <code className="font-mono text-dark-100">{item.ip}</code>
                {(item.country_code || item.city) && (
                  <span className="text-dark-200">{[item.country_code, item.city].filter(Boolean).join(' · ')}</span>
                )}
                <NetworkBadge type={item.connection_type} />
                {item.asn_org && (
                  <span className="text-primary-400 truncate max-w-[160px]" title={item.asn_org}>{item.asn_org}</span>
                )}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-dark-300">
                <span>{t('violations.addresses.online', { from: formatDate(item.first_seen), to: formatDate(item.last_seen) })}</span>
                <span>{t('violations.addresses.connections', { count: item.connections })}</span>
                {item.nodes.length > 0 && (
                  <span>{t('violations.addresses.nodes', { nodes: item.nodes.join(', ') })}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
