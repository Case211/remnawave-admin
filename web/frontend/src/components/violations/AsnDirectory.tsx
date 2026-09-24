import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Globe, Network, Search } from '@/components/brand/icons'
import { asnApi, type ASNRecord } from '@/api/asn'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { QueryError } from '@/components/QueryError'

const ROWS_LIMIT = 50

/** Тип провайдера из справочника ASN — на языке админа. */
export function useProviderTypeLabel() {
  const { t } = useTranslation()
  return (type: string | null | undefined) =>
    t(`asn.types.${type || 'unknown'}`, { defaultValue: type || t('asn.types.unknown') })
}

/**
 * Справочник ASN для разбора нарушений: по нему детектор решает, мобильная
 * это сеть, хостинг или VPN. Только поиск — синхронизация одна, в «Настройках».
 */
export function AsnDirectory() {
  const { t } = useTranslation()
  const typeLabel = useProviderTypeLabel()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const { data: stats, isLoading: statsLoading, isError: statsError, refetch } = useQuery({
    queryKey: ['asn-stats'],
    queryFn: asnApi.getStats,
  })
  const query = search.trim()
  const { data: found = [], isFetching: searching } = useQuery({
    queryKey: ['asn-search', query],
    queryFn: () => asnApi.search(query),
    enabled: query.length >= 2,
  })
  const { data: byType = [], isFetching: typeLoading } = useQuery({
    queryKey: ['asn-by-type', typeFilter],
    queryFn: () => asnApi.getByType(typeFilter),
    enabled: !!typeFilter,
  })

  if (statsError) return <QueryError onRetry={refetch} />

  const types = stats ? Object.entries(stats.by_type).sort(([, a], [, b]) => b - a) : []
  const active = query.length >= 2 || !!typeFilter

  return (
    <div className="space-y-4">
      <p className="text-sm text-dark-200">
        {t('asn.directory.description')}{' '}
        <Link to="/settings" className="text-primary-400 hover:underline">{t('asn.directory.syncLink')}</Link>
      </p>

      {statsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label={t('asn.directory.totalRecords')} value={stats.total} />
          {types.slice(0, 3).map(([type, count]) => (
            <StatCard key={type} label={typeLabel(type)} value={count} />
          ))}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
          <Input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setTypeFilter('') }}
            placeholder={t('asn.directory.searchPlaceholder')}
            aria-label={t('asn.directory.searchPlaceholder')}
            className="pl-9"
          />
        </div>
        <Select value={typeFilter || 'all'} onValueChange={(v) => { setTypeFilter(v === 'all' ? '' : v); setSearch('') }}>
          <SelectTrigger className="sm:w-56" aria-label={t('asn.directory.filterByType')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('asn.directory.allTypes')}</SelectItem>
            {types.map(([type, count]) => (
              <SelectItem key={type} value={type}>{typeLabel(type)} ({count})</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {searching || typeLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : active ? (
        <AsnTable records={typeFilter ? byType : found} />
      ) : (
        <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
          <CardContent className="p-8 text-center">
            <Globe className="w-12 h-12 mx-auto mb-3 text-dark-400" />
            <p className="text-dark-200">{t('asn.directory.searchHint')}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
      <CardContent className="p-3">
        <p className="text-xs text-dark-300">{label}</p>
        <p className="text-xl font-bold text-white mt-1 tabular-nums">{value.toLocaleString()}</p>
      </CardContent>
    </Card>
  )
}

function AsnTable({ records }: { records: ASNRecord[] }) {
  const { t } = useTranslation()
  const typeLabel = useProviderTypeLabel()

  if (records.length === 0) {
    return (
      <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
        <CardContent className="p-8 text-center">
          <Network className="w-12 h-12 mx-auto mb-3 text-dark-400" />
          <p className="text-dark-200">{t('asn.directory.noResults')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-[var(--glass-border)]">
              <tr>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ASN</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">{t('asn.directory.orgName')}</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">{t('asn.directory.type')}</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3 hidden sm:table-cell">{t('asn.directory.region')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--glass-border)]">
              {records.slice(0, ROWS_LIMIT).map((record) => (
                <tr key={record.asn} className="hover:bg-[var(--glass-bg)] transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-white">AS{record.asn}</td>
                  <td className="px-4 py-3 text-sm text-dark-100">
                    <div>{record.org_name}</div>
                    {record.org_name_en && record.org_name_en !== record.org_name && (
                      <div className="text-xs text-dark-300">{record.org_name_en}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <Badge variant="outline" className="text-xs">{typeLabel(record.provider_type)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-dark-200 hidden sm:table-cell">
                    {[record.region, record.city].filter(Boolean).join(', ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {records.length > ROWS_LIMIT && (
          <div className="text-center text-xs text-dark-400 py-2 border-t border-[var(--glass-border)]">
            {t('asn.directory.showingOf', { shown: ROWS_LIMIT, total: records.length })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
