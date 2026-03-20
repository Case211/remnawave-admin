import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Search,
  RefreshCw,
  Filter,
  ChevronLeft,
  ChevronRight,
  Users,
  ExternalLink,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

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

const statusColors: Record<string, string> = {
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  blocked: 'bg-red-500/20 text-red-400 border-red-500/30',
  inactive: 'bg-dark-500/20 text-dark-300 border-dark-500/30',
}

export default function BedolagaCustomers() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [showFilters, setShowFilters] = useState(false)
  const perPage = 20

  // Debounce search
  const handleSearch = useCallback((value: string) => {
    setSearch(value)
    const timeout = setTimeout(() => {
      setDebouncedSearch(value)
      setPage(1)
    }, 400)
    return () => clearTimeout(timeout)
  }, [])

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['bedolaga-customers', page, perPage, debouncedSearch, status],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('limit', String(perPage))
      params.set('offset', String((page - 1) * perPage))
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (status) params.set('status', status)
      return client.get(`/bedolaga/customers?${params}`).then((r) => r.data)
    },
    staleTime: 30_000,
    keepPreviousData: true,
  })

  const users: BedolagaUser[] = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const formatDate = (d?: string) => {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  }

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
          <Button variant="secondary" onClick={() => setShowFilters(!showFilters)} className={cn('gap-2', showFilters && 'ring-2 ring-primary-500')}>
            <Filter className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.filters')}</span>
          </Button>
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('w-5 h-5', isLoading && 'animate-spin')} />
          </Button>
        </div>
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
      </div>

      {/* Filters */}
      {showFilters && (
        <Card className="glass-card animate-fade-in-down">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.customers.status')}</label>
                <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('common.all')}</option>
                  <option value="active">{t('bedolaga.customers.statusActive')}</option>
                  <option value="blocked">{t('bedolaga.customers.statusBlocked')}</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                <th className="text-left p-3 font-medium">{t('bedolaga.customers.user')}</th>
                <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.customers.status')}</th>
                <th className="text-right p-3 font-medium hidden md:table-cell">{t('bedolaga.customers.balance')}</th>
                <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.customers.subscription')}</th>
                <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.customers.lastActivity')}</th>
                <th className="text-right p-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !users.length ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--glass-border)]">
                    <td className="p-3"><Skeleton className="h-5 w-32" /></td>
                    <td className="p-3 hidden sm:table-cell"><Skeleton className="h-5 w-16" /></td>
                    <td className="p-3 hidden md:table-cell"><Skeleton className="h-5 w-20" /></td>
                    <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-24" /></td>
                    <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-20" /></td>
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
                users.map((user) => (
                  <tr
                    key={user.id}
                    className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] cursor-pointer transition-colors"
                    onClick={() => navigate(`/bedolaga/customers/${user.id}`)}
                  >
                    <td className="p-3">
                      <div>
                        <span className="font-medium">{user.username || user.first_name || `#${user.id}`}</span>
                        {user.telegram_id && (
                          <span className="text-dark-400 text-xs ml-1.5">TG:{user.telegram_id}</span>
                        )}
                      </div>
                      {user.promo_group?.name && (
                        <span className="text-xs text-dark-300">{user.promo_group.name}</span>
                      )}
                    </td>
                    <td className="p-3 hidden sm:table-cell">
                      <Badge className={cn('text-[10px]', statusColors[user.status || ''] || statusColors.inactive)}>
                        {user.status || '—'}
                      </Badge>
                    </td>
                    <td className="p-3 text-right hidden md:table-cell">
                      <span className="font-medium">{user.balance_rubles?.toLocaleString() ?? 0} ₽</span>
                    </td>
                    <td className="p-3 hidden lg:table-cell">
                      {user.subscription ? (
                        <div className="text-xs">
                          <Badge className={cn('text-[10px] mr-1', user.subscription.status === 'active' ? statusColors.active : statusColors.inactive)}>
                            {user.subscription.is_trial ? 'Trial' : user.subscription.status}
                          </Badge>
                          <span className="text-dark-300">
                            {user.subscription.end_date ? `→ ${formatDate(user.subscription.end_date)}` : ''}
                          </span>
                        </div>
                      ) : (
                        <span className="text-dark-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="p-3 hidden lg:table-cell text-dark-300 text-xs">
                      {formatDate(user.last_activity)}
                    </td>
                    <td className="p-3 text-right">
                      <ExternalLink className="w-4 h-4 text-dark-400" />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
            <span>
              {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} {t('common.of')} {total}
            </span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="px-2">{page} / {totalPages}</span>
              <Button variant="ghost" size="icon" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
