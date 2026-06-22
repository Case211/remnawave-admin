import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ChevronDown,
  ChevronRight,
  Crown,
  ExternalLink,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  TrendingUp,
  Users,
  Wallet,
} from '@/components/brand/icons'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { formatDateShortUtil as formatDate } from '@/lib/useFormatters'

// ── Types ──

interface Referrer {
  id: number
  telegram_id?: number
  username?: string
  first_name?: string
  referral_code?: string
  effective_referral_commission_percent?: number
  invited_count?: number
  active_referrals?: number
  total_earned_kopeks?: number
  total_earned_rubles?: number
  month_earned_kopeks?: number
  month_earned_rubles?: number
  created_at?: string
  last_activity?: string
}

interface ReferralRow {
  id: number
  telegram_id?: number
  username?: string
  first_name?: string
  display_name?: string
  status?: string
  balance_rubles?: number
  subscription_status?: string
  is_trial?: boolean
  subscription_end?: string
  created_at?: string
  last_activity?: string
}

interface ReferrersResponse {
  items?: Referrer[]
  total?: number
  total_unfiltered?: number
  limit?: number
  offset?: number
}

interface RefsResponse {
  items?: ReferralRow[]
  total?: number
  cached_at?: number
}

interface PartnerStats {
  total_referrers?: number
  active_referrers?: number
  total_referrals?: number
  active_referrals?: number
  total_paid_kopeks?: number
  total_paid_rubles?: number
  month_paid_kopeks?: number
  month_paid_rubles?: number
}

type SortKey = 'invited_desc' | 'invited_asc' | 'earned_desc' | 'earned_asc' | 'activity_desc' | 'created_desc'

// ── Helpers ──

function relativeTime(d?: string): string {
  if (!d) return '—'
  const diff = Date.now() - new Date(d).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'online'
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d`
  return `${Math.floor(days / 30)}mo`
}

function isOnline(d?: string): boolean {
  if (!d) return false
  return Date.now() - new Date(d).getTime() < 5 * 60_000
}

function displayName(u: { username?: string; first_name?: string; id: number }): string {
  return u.username || u.first_name || `#${u.id}`
}

function avatarColor(id: number): string {
  const palette = [
    'bg-blue-500/20 text-blue-400',
    'bg-emerald-500/20 text-emerald-400',
    'bg-violet-500/20 text-violet-400',
    'bg-amber-500/20 text-amber-400',
    'bg-pink-500/20 text-pink-400',
    'bg-cyan-500/20 text-cyan-400',
  ]
  return palette[Math.abs(id) % palette.length]
}

function rubles(value?: number): string {
  if (value == null) return '—'
  return `${Math.round(value).toLocaleString()} ₽`
}

const PAGE = 50

// ── Component ──

export default function BedolagaReferrals() {
  const { t } = useTranslation()

  const [search, setSearch] = useState('')
  const [topOnly, setTopOnly] = useState(false)
  const [minRefs, setMinRefs] = useState(0)
  const [sort, setSort] = useState<SortKey>('invited_desc')
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const params = useMemo(() => {
    const sp = new URLSearchParams({
      sort,
      limit: String(PAGE),
      offset: String(offset),
    })
    if (search.trim()) sp.set('search', search.trim())
    if (topOnly) sp.set('top_only', 'true')
    if (minRefs > 0 && !topOnly) sp.set('min_refs', String(minRefs))
    return sp.toString()
  }, [search, topOnly, minRefs, sort, offset])

  const { data: stats } = useQuery<PartnerStats>({
    queryKey: ['bedolaga-referral-stats'],
    queryFn: () => client.get('/bedolaga/referrals/stats').then((r) => r.data),
    staleTime: 60_000,
  })

  const { data, isLoading, isFetching, refetch } = useQuery<ReferrersResponse>({
    queryKey: ['bedolaga-referrers', params],
    queryFn: () => client.get(`/bedolaga/referrals/referrers?${params}`).then((r) => r.data),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  const referrers: Referrer[] = Array.isArray(data?.items) ? data.items : []
  const total = data?.total ?? 0
  const totalUnfiltered = data?.total_unfiltered ?? total
  const pages = Math.max(1, Math.ceil(total / PAGE))
  const currentPage = Math.floor(offset / PAGE) + 1

  function toggleRow(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function resetFilters() {
    setSearch('')
    setTopOnly(false)
    setMinRefs(0)
    setSort('invited_desc')
    setOffset(0)
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('bedolaga.referrals.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm">{t('bedolaga.referrals.subtitle')}</p>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn('w-5 h-5', isFetching && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={Users}
          label={t('bedolaga.referrals.totalReferrers')}
          value={stats?.total_referrers ?? totalUnfiltered}
          sub={stats?.active_referrers != null ? `${t('bedolaga.referrals.active')}: ${stats.active_referrers}` : undefined}
          tone="text-violet-400"
        />
        <StatCard
          icon={Share2}
          label={t('bedolaga.referrals.totalReferrals')}
          value={stats?.total_referrals ?? '—'}
          sub={stats?.active_referrals != null ? `${t('bedolaga.referrals.active')}: ${stats.active_referrals}` : undefined}
          tone="text-blue-400"
        />
        <StatCard
          icon={Wallet}
          label={t('bedolaga.referrals.totalEarnings')}
          value={rubles(stats?.total_paid_rubles)}
          tone="text-emerald-400"
        />
        <StatCard
          icon={TrendingUp}
          label={t('bedolaga.referrals.monthEarnings')}
          value={rubles(stats?.month_paid_rubles)}
          tone="text-amber-400"
        />
      </div>

      {/* Filters */}
      <Card className="glass-card">
        <CardContent className="p-3 sm:p-4">
          <div className="flex flex-col lg:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setOffset(0)
                }}
                placeholder={t('bedolaga.referrals.searchPlaceholder')}
                className="w-full pl-10 pr-3 py-2 text-sm rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] focus:border-violet-500/50 focus:outline-none transition-colors"
              />
            </div>

            <Select
              value={String(minRefs)}
              onValueChange={(v) => {
                setMinRefs(Number(v))
                setOffset(0)
              }}
              disabled={topOnly}
            >
              <SelectTrigger className="w-full lg:w-48 h-9 text-sm">
                <SelectValue placeholder={t('bedolaga.referrals.minRefs')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">{t('bedolaga.referrals.minRefsAny')}</SelectItem>
                <SelectItem value="1">≥ 1</SelectItem>
                <SelectItem value="3">≥ 3</SelectItem>
                <SelectItem value="5">≥ 5</SelectItem>
                <SelectItem value="10">≥ 10</SelectItem>
              </SelectContent>
            </Select>

            <Button
              variant={topOnly ? 'default' : 'secondary'}
              size="sm"
              onClick={() => {
                setTopOnly((v) => !v)
                setOffset(0)
              }}
              className="gap-1.5"
            >
              <Crown className="w-4 h-4" />
              {t('bedolaga.referrals.topOnly')}
            </Button>

            <Select value={sort} onValueChange={(v) => { setSort(v as SortKey); setOffset(0) }}>
              <SelectTrigger className="w-full lg:w-56 h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="invited_desc">{t('bedolaga.referrals.sort.invitedDesc')}</SelectItem>
                <SelectItem value="invited_asc">{t('bedolaga.referrals.sort.invitedAsc')}</SelectItem>
                <SelectItem value="earned_desc">{t('bedolaga.referrals.sort.earnedDesc')}</SelectItem>
                <SelectItem value="earned_asc">{t('bedolaga.referrals.sort.earnedAsc')}</SelectItem>
                <SelectItem value="activity_desc">{t('bedolaga.referrals.sort.activityDesc')}</SelectItem>
                <SelectItem value="created_desc">{t('bedolaga.referrals.sort.createdDesc')}</SelectItem>
              </SelectContent>
            </Select>

            {(search || topOnly || minRefs > 0 || sort !== 'invited_desc') && (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                {t('bedolaga.referrals.resetFilters')}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="glass-card overflow-hidden">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--glass-bg)] text-[10px] uppercase tracking-wider text-dark-300">
                <tr>
                  <th className="w-10" />
                  <th className="text-left p-3 font-medium">{t('bedolaga.referrals.referrer')}</th>
                  <th className="text-right p-3 font-medium hidden sm:table-cell">{t('bedolaga.referrals.invited')}</th>
                  <th className="text-right p-3 font-medium hidden md:table-cell">{t('bedolaga.referrals.activeRefs')}</th>
                  <th className="text-right p-3 font-medium">{t('bedolaga.referrals.earnedTotal')}</th>
                  <th className="text-right p-3 font-medium hidden lg:table-cell">{t('bedolaga.referrals.earnedMonth')}</th>
                  <th className="text-right p-3 font-medium hidden lg:table-cell">{t('bedolaga.referrals.lastActivity')}</th>
                  <th className="text-right p-3 font-medium hidden md:table-cell">{t('bedolaga.referrals.createdAt')}</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {isLoading && !data && (
                  <>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <tr key={i} className="border-t border-[var(--glass-border)]">
                        <td colSpan={9} className="p-3"><Skeleton className="h-8 w-full" /></td>
                      </tr>
                    ))}
                  </>
                )}

                {!isLoading && referrers.length === 0 && (
                  <tr>
                    <td colSpan={9} className="p-10 text-center text-dark-300">
                      <Sparkles className="w-8 h-8 text-dark-400 mx-auto mb-2" />
                      <p>{t('bedolaga.referrals.noData')}</p>
                    </td>
                  </tr>
                )}

                {referrers.map((r) => (
                  <ReferrerRow
                    key={r.id}
                    referrer={r}
                    isOpen={expanded.has(r.id)}
                    onToggle={() => toggleRow(r.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {total > PAGE && (
            <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
              <span>
                {t('bedolaga.referrals.showing', { from: offset + 1, to: Math.min(offset + referrers.length, total), total })}
              </span>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  ←
                </Button>
                <span>{currentPage} / {pages}</span>
                <Button variant="ghost" size="sm" disabled={currentPage >= pages} onClick={() => setOffset(offset + PAGE)}>
                  →
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── Stat card ──

function StatCard({ icon: Icon, label, value, sub, tone }: {
  icon: typeof Users
  label: string
  value: number | string
  sub?: string
  tone?: string
}) {
  return (
    <Card className="glass-card">
      <CardContent className="p-3 sm:p-4">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <p className="text-[10px] sm:text-xs text-dark-300 uppercase tracking-wider truncate">{label}</p>
            <p className="text-xl sm:text-2xl font-bold mt-0.5 truncate">{value}</p>
            {sub && <p className="text-[10px] text-dark-400 mt-0.5 truncate">{sub}</p>}
          </div>
          <div className={cn('p-2 rounded-lg bg-[var(--glass-bg)] flex-shrink-0', tone)}>
            <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Referrer row + lazy-loaded refs ──

function ReferrerRow({
  referrer,
  isOpen,
  onToggle,
}: {
  referrer: Referrer
  isOpen: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const earnedRub = referrer.total_earned_rubles ?? (referrer.total_earned_kopeks ? referrer.total_earned_kopeks / 100 : 0)
  const monthRub = referrer.month_earned_rubles ?? (referrer.month_earned_kopeks ? referrer.month_earned_kopeks / 100 : 0)
  const online = isOnline(referrer.last_activity)

  const { data: refsData, isFetching: refsLoading } = useQuery<RefsResponse>({
    queryKey: ['bedolaga-referrer-refs', referrer.id],
    queryFn: () => client.get(`/bedolaga/referrals/referrers/${referrer.id}/refs`).then((r) => r.data),
    enabled: isOpen,
    staleTime: 5 * 60_000,
  })
  const refs: ReferralRow[] = Array.isArray(refsData?.items) ? refsData.items : []

  return (
    <>
      <tr
        className="border-t border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="p-3 align-middle">
          {isOpen ? <ChevronDown className="w-4 h-4 text-dark-400" /> : <ChevronRight className="w-4 h-4 text-dark-400" />}
        </td>
        <td className="p-3 align-middle">
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn('w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0', avatarColor(referrer.id))}>
              {displayName(referrer).charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <Link
                to={`/bedolaga/customers/${referrer.id}`}
                onClick={(e) => e.stopPropagation()}
                className="font-medium text-white hover:text-violet-400 transition-colors truncate block"
              >
                {displayName(referrer)}
              </Link>
              <div className="text-[11px] text-dark-400 flex items-center gap-2 truncate">
                {referrer.telegram_id ? <span>TG {referrer.telegram_id}</span> : null}
                {referrer.referral_code ? (
                  <span className="font-mono">/{referrer.referral_code}</span>
                ) : null}
              </div>
            </div>
            {online && <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" title="online" />}
          </div>
        </td>
        <td className="p-3 align-middle text-right hidden sm:table-cell">
          <span className="font-medium tabular-nums">{referrer.invited_count ?? 0}</span>
        </td>
        <td className="p-3 align-middle text-right hidden md:table-cell">
          <span className="text-dark-200 tabular-nums">{referrer.active_referrals ?? 0}</span>
        </td>
        <td className="p-3 align-middle text-right">
          <span className="font-medium tabular-nums text-emerald-400">{earnedRub.toLocaleString()} ₽</span>
        </td>
        <td className="p-3 align-middle text-right hidden lg:table-cell">
          <span className="tabular-nums text-dark-200">{monthRub.toLocaleString()} ₽</span>
        </td>
        <td className="p-3 align-middle text-right hidden lg:table-cell text-dark-300 text-xs">
          {relativeTime(referrer.last_activity)}
        </td>
        <td className="p-3 align-middle text-right hidden md:table-cell text-dark-300 text-xs">
          {formatDate(referrer.created_at)}
        </td>
        <td className="p-3 align-middle text-right">
          <Link to={`/bedolaga/customers/${referrer.id}`} onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="icon" className="h-8 w-8" title={t('bedolaga.referrals.openProfile')}>
              <ExternalLink className="w-4 h-4" />
            </Button>
          </Link>
        </td>
      </tr>

      {isOpen && (
        <tr className="bg-[var(--glass-bg)]">
          <td colSpan={9} className="p-0">
            <div className="px-3 sm:px-12 py-3 border-t border-[var(--glass-border)]">
              {refsLoading && !refsData && (
                <div className="space-y-2 py-2">
                  {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
                </div>
              )}
              {!refsLoading && refs.length === 0 && (
                <p className="py-4 text-center text-dark-400 text-xs">{t('bedolaga.referrals.noRefsForUser')}</p>
              )}
              {refs.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-[10px] uppercase tracking-wider text-dark-400">
                      <tr>
                        <th className="text-left py-2 font-medium">{t('bedolaga.referrals.referral')}</th>
                        <th className="text-left py-2 font-medium hidden sm:table-cell">{t('bedolaga.referrals.subStatus')}</th>
                        <th className="text-right py-2 font-medium hidden md:table-cell">{t('bedolaga.referrals.balance')}</th>
                        <th className="text-right py-2 font-medium hidden md:table-cell">{t('bedolaga.referrals.registered')}</th>
                        <th className="text-right py-2 font-medium">{t('bedolaga.referrals.lastActivity')}</th>
                        <th className="w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {refs.map((ref) => (
                        <tr key={ref.id} className="border-t border-[var(--glass-border)]">
                          <td className="py-2">
                            <Link
                              to={`/bedolaga/customers/${ref.id}`}
                              className="text-white hover:text-violet-400 transition-colors"
                            >
                              {ref.display_name || displayName(ref)}
                            </Link>
                          </td>
                          <td className="py-2 hidden sm:table-cell">
                            <SubBadge status={ref.subscription_status} isTrial={ref.is_trial} />
                          </td>
                          <td className="py-2 text-right hidden md:table-cell tabular-nums">
                            {ref.balance_rubles != null ? `${ref.balance_rubles.toLocaleString()} ₽` : '—'}
                          </td>
                          <td className="py-2 text-right hidden md:table-cell text-dark-300">
                            {formatDate(ref.created_at)}
                          </td>
                          <td className="py-2 text-right text-dark-300">
                            {relativeTime(ref.last_activity)}
                          </td>
                          <td className="py-2 text-right">
                            <Link to={`/bedolaga/customers/${ref.id}`}>
                              <Button variant="ghost" size="icon" className="h-6 w-6">
                                <ExternalLink className="w-3 h-3" />
                              </Button>
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function SubBadge({ status, isTrial }: { status?: string; isTrial?: boolean }) {
  const { t } = useTranslation()
  if (!status || status === 'none') return <Badge variant="outline" className="text-[10px] text-dark-400">—</Badge>
  if (status === 'active' && isTrial) return <Badge className="text-[10px] bg-blue-500/20 text-blue-400 border-blue-500/30">{t('bedolaga.referrals.subLabels.trial')}</Badge>
  if (status === 'active') return <Badge className="text-[10px] bg-emerald-500/20 text-emerald-400 border-emerald-500/30">{t('bedolaga.referrals.subLabels.active')}</Badge>
  if (status === 'expired') return <Badge className="text-[10px] bg-amber-500/20 text-amber-400 border-amber-500/30">{t('bedolaga.referrals.subLabels.expired')}</Badge>
  return <Badge variant="outline" className="text-[10px]">{status}</Badge>
}
