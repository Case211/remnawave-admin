import { useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Search,
  RefreshCw,
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Users,
  ExternalLink,
  X,
  MoreVertical,
  Eye,
  Wallet,
  CreditCard,
  Activity,
  ArrowUpDown,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ExportDropdown } from '@/components/ExportDropdown'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

// ── Types ──

interface BedolagaUser {
  id: number
  telegram_id?: number
  username?: string
  first_name?: string
  last_name?: string
  status?: string
  balance_kopeks?: number
  balance_rubles?: number
  created_at?: string
  last_activity?: string
  subscription?: {
    id?: number
    status?: string
    end_date?: string
    is_trial?: boolean
    traffic_used_gb?: number
    traffic_limit_gb?: number
    device_limit?: number
  }
  promo_group?: { id?: number; name?: string }
}

interface OverviewData {
  users?: { total?: number; active?: number; blocked?: number; balance_rubles?: number }
  subscriptions?: { active?: number; expired?: number }
}

// ── Constants ──

const statusColors: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  blocked: 'bg-red-500/20 text-red-400 border-red-500/30',
  inactive: 'bg-dark-500/20 text-dark-300 border-dark-500/30',
}

const subStatusColors: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  expired: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  trial: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
}

type SortField = 'created_at' | 'last_activity' | 'balance' | 'username'
type SortOrder = 'asc' | 'desc'

const PER_PAGE_OPTIONS = [10, 20, 50, 100]

// ── Helpers ──

function getInitials(user: BedolagaUser): string {
  if (user.username) return user.username.charAt(0).toUpperCase()
  if (user.first_name) return user.first_name.charAt(0).toUpperCase()
  return '#'
}

function getInitialColor(id: number): string {
  const colors = [
    'bg-blue-500/20 text-blue-400',
    'bg-emerald-500/20 text-emerald-400',
    'bg-amber-500/20 text-amber-400',
    'bg-violet-500/20 text-violet-400',
    'bg-pink-500/20 text-pink-400',
    'bg-cyan-500/20 text-cyan-400',
  ]
  return colors[id % colors.length]
}

function relativeTime(d?: string): string {
  if (!d) return '—'
  const now = Date.now()
  const diff = now - new Date(d).getTime()
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

function trafficPercent(sub?: BedolagaUser['subscription']): number | null {
  if (!sub?.traffic_limit_gb || !sub.traffic_used_gb) return null
  return Math.min(100, (sub.traffic_used_gb / sub.traffic_limit_gb) * 100)
}

import { formatDateShortUtil as formatDate } from '@/lib/useFormatters'

// ── Component ──

export default function BedolagaCustomers() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initialSearch = searchParams.get('search') || ''

  // State
  const [search, setSearch] = useState(initialSearch)
  const [debouncedSearch, setDebouncedSearch] = useState(initialSearch)
  const [statusFilter, setStatusFilter] = useState('')
  const [subFilter, setSubFilter] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [showFilters, setShowFilters] = useState(false)
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')

  // Active filters count
  const activeFilterCount = [statusFilter, subFilter].filter(Boolean).length

  // Debounce search
  const handleSearch = useCallback((value: string) => {
    setSearch(value)
    const timeout = setTimeout(() => {
      setDebouncedSearch(value)
      setPage(1)
    }, 400)
    return () => clearTimeout(timeout)
  }, [])

  // ── Queries ──

  const { data: overview } = useQuery<OverviewData>({
    queryKey: ['bedolaga-overview'],
    queryFn: () => client.get('/bedolaga/overview').then((r) => r.data),
    staleTime: 60_000,
  })

  const { data, isLoading, refetch } = useQuery<{ items?: BedolagaUser[]; total?: number }>({
    queryKey: ['bedolaga-customers', page, perPage, debouncedSearch, statusFilter, subFilter, sortField, sortOrder],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('limit', String(perPage))
      params.set('offset', String((page - 1) * perPage))
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (statusFilter) params.set('status', statusFilter)
      if (subFilter) params.set('subscription_status', subFilter)
      if (sortField) params.set('sort', sortField)
      if (sortOrder) params.set('order', sortOrder)
      return client.get(`/bedolaga/customers?${params}`).then((r) => r.data)
    },
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  const users: BedolagaUser[] = Array.isArray(data?.items) ? data.items : []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  // ── Sort handler ──

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('desc')
    }
    setPage(1)
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 text-dark-400 opacity-0 group-hover:opacity-100 transition-opacity" />
    return sortOrder === 'asc' ? <ChevronUp className="w-3 h-3 text-primary-400" /> : <ChevronDown className="w-3 h-3 text-primary-400" />
  }

  // ── Filter chips ──

  const clearFilter = (key: string) => {
    if (key === 'status') setStatusFilter('')
    if (key === 'sub') setSubFilter('')
    setPage(1)
  }

  const clearAllFilters = () => {
    setStatusFilter('')
    setSubFilter('')
    setPage(1)
  }

  // ── Export ──

  const handleExportCSV = () => {
    const headers = ['ID', 'Username', 'Telegram ID', 'Status', 'Balance (₽)', 'Subscription', 'Last Activity']
    const rows = users.map((u) => [
      u.id,
      u.username || u.first_name || '',
      u.telegram_id || '',
      u.status || '',
      u.balance_rubles ?? 0,
      u.subscription?.status || 'none',
      u.last_activity || '',
    ])
    const csv = [headers.join(','), ...rows.map((r) => r.map((v) => `"${v}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bedolaga-customers-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(t('common.export.csvDone'))
  }

  const handleExportJSON = () => {
    const blob = new Blob([JSON.stringify(users, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bedolaga-customers-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(t('common.export.jsonDone'))
  }

  // ── Stat cards data ──

  const stats = useMemo(() => [
    { label: t('bedolaga.stats.totalUsers'), value: overview?.users?.total ?? '—', icon: Users, color: 'text-blue-400' },
    { label: t('bedolaga.stats.active'), value: overview?.users?.active ?? '—', icon: Activity, color: 'text-emerald-400' },
    { label: t('bedolaga.stats.activeSubs'), value: overview?.subscriptions?.active ?? '—', icon: CreditCard, color: 'text-violet-400' },
    { label: t('bedolaga.stats.totalBalance'), value: overview?.users?.balance_rubles != null ? `${overview.users.balance_rubles.toLocaleString()} ₽` : '—', icon: Wallet, color: 'text-amber-400' },
  ], [overview, t])

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('bedolaga.customers.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm">
            {t('bedolaga.customers.subtitle')}
            {total > 0 && <span className="text-dark-300 ml-1">({total})</span>}
          </p>
        </div>
        <div className="page-header-actions">
          <ExportDropdown onExportCSV={handleExportCSV} onExportJSON={handleExportJSON} disabled={!users.length} />
          <Button
            variant="secondary"
            onClick={() => setShowFilters(!showFilters)}
            className={cn('gap-2', showFilters && 'ring-2 ring-primary-500')}
          >
            <Filter className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.filters')}</span>
            {activeFilterCount > 0 && (
              <span className="flex items-center justify-center w-4.5 h-4.5 rounded-full bg-primary-500 text-[10px] text-white font-bold">
                {activeFilterCount}
              </span>
            )}
          </Button>
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading} aria-label={t('common.refresh')}>
            <RefreshCw className={cn('w-5 h-5', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {stats.map((stat) => (
          <Card key={stat.label} className="glass-card">
            <CardContent className="p-3 sm:p-4 flex items-center gap-3">
              <div className={cn('flex items-center justify-center w-9 h-9 rounded-lg bg-[var(--glass-bg-hover)]', stat.color)}>
                <stat.icon className="w-4.5 h-4.5" />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-dark-300 truncate">{stat.label}</p>
                <p className="text-lg font-bold truncate">{stat.value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
        <input
          type="text"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder={t('bedolaga.customers.searchPlaceholder')}
          className="w-full h-10 pl-10 pr-4 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
        />
        {search && (
          <button onClick={() => { setSearch(''); setDebouncedSearch(''); setPage(1) }} className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Filter chips */}
      {activeFilterCount > 0 && (
        <div className="flex items-center gap-2 flex-wrap animate-fade-in">
          {statusFilter && (
            <Badge className="gap-1 pr-1 bg-[var(--glass-bg-hover)] border-[var(--glass-border)] text-dark-100 cursor-pointer hover:border-red-500/50" onClick={() => clearFilter('status')}>
              {t('bedolaga.customers.status')}: {statusFilter}
              <X className="w-3 h-3 ml-0.5" />
            </Badge>
          )}
          {subFilter && (
            <Badge className="gap-1 pr-1 bg-[var(--glass-bg-hover)] border-[var(--glass-border)] text-dark-100 cursor-pointer hover:border-red-500/50" onClick={() => clearFilter('sub')}>
              {t('bedolaga.customers.subscription')}: {subFilter}
              <X className="w-3 h-3 ml-0.5" />
            </Badge>
          )}
          <button onClick={clearAllFilters} className="text-xs text-dark-400 hover:text-red-400 transition-colors">
            {t('common.resetAll')}
          </button>
        </div>
      )}

      {/* Filters panel */}
      {showFilters && (
        <Card className="glass-card animate-fade-in-down">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.customers.status')}</label>
                <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('common.all')}</option>
                  <option value="active">{t('bedolaga.customers.statusActive')}</option>
                  <option value="blocked">{t('bedolaga.customers.statusBlocked')}</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.customers.subscription')}</label>
                <select value={subFilter} onChange={(e) => { setSubFilter(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('common.all')}</option>
                  <option value="active">{t('bedolaga.customers.subActive')}</option>
                  <option value="expired">{t('bedolaga.customers.subExpired')}</option>
                  <option value="trial">{t('bedolaga.customers.subTrial')}</option>
                  <option value="none">{t('bedolaga.customers.subNone')}</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Desktop table */}
      <Card className="glass-card overflow-hidden hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                <th className="text-left p-3 font-medium">
                  <button onClick={() => handleSort('username')} className="group flex items-center gap-1 hover:text-white transition-colors">
                    {t('bedolaga.customers.user')} <SortIcon field="username" />
                  </button>
                </th>
                <th className="text-left p-3 font-medium">{t('bedolaga.customers.status')}</th>
                <th className="text-right p-3 font-medium">
                  <button onClick={() => handleSort('balance')} className="group flex items-center gap-1 ml-auto hover:text-white transition-colors">
                    {t('bedolaga.customers.balance')} <SortIcon field="balance" />
                  </button>
                </th>
                <th className="text-left p-3 font-medium">{t('bedolaga.customers.subscription')}</th>
                <th className="text-left p-3 font-medium">
                  <button onClick={() => handleSort('last_activity')} className="group flex items-center gap-1 hover:text-white transition-colors">
                    {t('bedolaga.customers.lastActivity')} <SortIcon field="last_activity" />
                  </button>
                </th>
                <th className="text-right p-3 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !users.length ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--glass-border)]">
                    <td className="p-3"><div className="flex items-center gap-2.5"><Skeleton className="h-8 w-8 rounded-full" /><Skeleton className="h-5 w-32" /></div></td>
                    <td className="p-3"><Skeleton className="h-5 w-16" /></td>
                    <td className="p-3"><Skeleton className="h-5 w-20" /></td>
                    <td className="p-3"><Skeleton className="h-5 w-32" /></td>
                    <td className="p-3"><Skeleton className="h-5 w-16" /></td>
                    <td className="p-3"><Skeleton className="h-5 w-8" /></td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-dark-300">
                    <Users className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    {t('bedolaga.customers.noResults')}
                  </td>
                </tr>
              ) : (
                users.map((user) => {
                  const tp = trafficPercent(user.subscription)
                  const online = isOnline(user.last_activity)
                  return (
                    <tr
                      key={user.id}
                      className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] cursor-pointer transition-colors"
                      onClick={() => navigate(`/bedolaga/customers/${user.id}`)}
                    >
                      {/* User with avatar */}
                      <td className="p-3">
                        <div className="flex items-center gap-2.5">
                          <div className={cn('flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold flex-shrink-0', getInitialColor(user.id))}>
                            {getInitials(user)}
                          </div>
                          <div className="min-w-0">
                            <span className="font-medium truncate block">{user.username || user.first_name || `#${user.id}`}</span>
                            {user.telegram_id && (
                              <span className="text-dark-400 text-xs">TG:{user.telegram_id}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      {/* Status */}
                      <td className="p-3">
                        <Badge className={cn('text-[10px]', statusColors[user.status || ''] || statusColors.inactive)}>
                          {user.status || '—'}
                        </Badge>
                      </td>
                      {/* Balance */}
                      <td className="p-3 text-right">
                        <span className={cn('font-medium tabular-nums', (user.balance_rubles ?? 0) < 0 && 'text-red-400 animate-pulse')}>
                          {(user.balance_rubles ?? 0).toLocaleString()} ₽
                        </span>
                      </td>
                      {/* Subscription with traffic bar */}
                      <td className="p-3">
                        {user.subscription ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5">
                              <Badge className={cn('text-[10px]', user.subscription.is_trial ? subStatusColors.trial : subStatusColors[user.subscription.status || ''] || statusColors.inactive)}>
                                {user.subscription.is_trial ? 'Trial' : user.subscription.status}
                              </Badge>
                              <span className="text-dark-400 text-xs">
                                {user.subscription.end_date ? `→ ${formatDate(user.subscription.end_date)}` : ''}
                              </span>
                            </div>
                            {tp !== null && (
                              <div className="flex items-center gap-1.5">
                                <div className="h-1.5 w-20 rounded-full bg-dark-600 overflow-hidden">
                                  <div
                                    className={cn(
                                      'h-full rounded-full transition-all',
                                      tp > 90 ? 'bg-red-500 animate-pulse' : tp > 70 ? 'bg-amber-500' : 'bg-emerald-500'
                                    )}
                                    style={{ width: `${tp}%` }}
                                  />
                                </div>
                                <span className={cn('text-[10px]', tp > 90 ? 'text-red-400' : 'text-dark-400')}>
                                  {user.subscription.traffic_used_gb?.toFixed(1)}/{user.subscription.traffic_limit_gb}GB
                                </span>
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-dark-400 text-xs">—</span>
                        )}
                      </td>
                      {/* Last activity with online indicator */}
                      <td className="p-3">
                        <div className="flex items-center gap-1.5">
                          <span className={cn(
                            'w-2 h-2 rounded-full flex-shrink-0',
                            online ? 'bg-emerald-400 animate-pulse' : 'bg-dark-500'
                          )} />
                          <span className={cn('text-xs', online ? 'text-emerald-400' : 'text-dark-300')}>
                            {relativeTime(user.last_activity)}
                          </span>
                        </div>
                      </td>
                      {/* Actions */}
                      <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t('common.openMenu')}>
                              <MoreVertical className="w-4 h-4 text-dark-400" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => navigate(`/bedolaga/customers/${user.id}`)}>
                              <Eye className="w-4 h-4 mr-2" />{t('users.actions.view')}
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => navigate(`/bedolaga/customers/${user.id}?action=balance`)}>
                              <Wallet className="w-4 h-4 mr-2" />{t('bedolaga.customerDetail.changeBalance')}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
          <div className="flex items-center gap-2">
            <span>{total > 0 ? `${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)}` : '0'} {t('common.of')} {total}</span>
            <Select value={String(perPage)} onValueChange={(v) => { setPerPage(Number(v)); setPage(1) }}>
              <SelectTrigger className="h-7 w-[70px] text-xs border-[var(--glass-border)] bg-transparent">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PER_PAGE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label={t('common.previousPage')}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="px-2">{page} / {totalPages}</span>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page >= totalPages} onClick={() => setPage(page + 1)} aria-label={t('common.nextPage')}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </Card>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {isLoading && !users.length ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="glass-card">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-3"><Skeleton className="h-10 w-10 rounded-full" /><Skeleton className="h-5 w-32" /></div>
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
              </CardContent>
            </Card>
          ))
        ) : users.length === 0 ? (
          <Card className="glass-card">
            <CardContent className="p-8 text-center text-dark-300">
              <Users className="w-8 h-8 mx-auto mb-2 opacity-40" />
              {t('bedolaga.customers.noResults')}
            </CardContent>
          </Card>
        ) : (
          users.map((user, idx) => {
            const tp = trafficPercent(user.subscription)
            const online = isOnline(user.last_activity)
            return (
              <Card
                key={user.id}
                className="glass-card cursor-pointer hover:border-[var(--glass-border-hover)] transition-all animate-fade-in-up"
                style={{ animationDelay: `${idx * 50}ms` }}
                onClick={() => navigate(`/bedolaga/customers/${user.id}`)}
              >
                <CardContent className="p-4">
                  {/* Top row: avatar + name + status */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn('flex items-center justify-center w-10 h-10 rounded-full text-sm font-bold flex-shrink-0', getInitialColor(user.id))}>
                        {getInitials(user)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium truncate">{user.username || user.first_name || `#${user.id}`}</span>
                          <Badge className={cn('text-[10px]', statusColors[user.status || ''] || statusColors.inactive)}>
                            {user.status || '—'}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-dark-400">
                          {user.telegram_id && <span>TG:{user.telegram_id}</span>}
                          <span className="flex items-center gap-1">
                            <span className={cn('w-1.5 h-1.5 rounded-full', online ? 'bg-emerald-400 animate-pulse' : 'bg-dark-500')} />
                            {relativeTime(user.last_activity)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <ExternalLink className="w-4 h-4 text-dark-400 flex-shrink-0" />
                  </div>

                  {/* Bottom row: balance + subscription */}
                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--glass-border)]">
                    <span className={cn('font-medium text-sm', (user.balance_rubles ?? 0) < 0 && 'text-red-400')}>
                      {(user.balance_rubles ?? 0).toLocaleString()} ₽
                    </span>
                    <div className="flex items-center gap-2">
                      {user.subscription ? (
                        <>
                          <Badge className={cn('text-[10px]', user.subscription.is_trial ? subStatusColors.trial : subStatusColors[user.subscription.status || ''] || statusColors.inactive)}>
                            {user.subscription.is_trial ? 'Trial' : user.subscription.status}
                          </Badge>
                          {tp !== null && (
                            <div className="flex items-center gap-1">
                              <div className="h-1.5 w-12 rounded-full bg-dark-600 overflow-hidden">
                                <div
                                  className={cn('h-full rounded-full', tp > 90 ? 'bg-red-500' : tp > 70 ? 'bg-amber-500' : 'bg-emerald-500')}
                                  style={{ width: `${tp}%` }}
                                />
                              </div>
                              <span className="text-[10px] text-dark-400">{Math.round(tp)}%</span>
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-dark-400 text-xs">{t('bedolaga.customers.subNone')}</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })
        )}

        {/* Mobile pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between text-xs text-dark-300">
            <span>{total > 0 ? `${(page - 1) * perPage + 1}–${Math.min(page * perPage, total)}` : '0'} {t('common.of')} {total}</span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label={t('common.previousPage')}>
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="px-2">{page} / {totalPages}</span>
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page >= totalPages} onClick={() => setPage(page + 1)} aria-label={t('common.nextPage')}>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
