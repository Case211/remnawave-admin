import { useState, useMemo, Fragment } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useOpenUser } from '@/lib/useOpenUser'
import {
  Fingerprint,
  Smartphone,
  Copy,
  ChevronDown,
  ChevronRight,
  Search,
  Clock,
  ShieldBan,
  Sparkles,
  Users,
} from '@/components/brand/icons'
import { toast } from 'sonner'
import { advancedAnalyticsApi } from '@/api/advancedAnalytics'
import type { SharedHwidGroup } from '@/api/advancedAnalytics'
import { ExportDropdown } from '@/components/ExportDropdown'
import { exportCSV, exportJSON } from '@/lib/export'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { InfoTooltip } from '@/components/InfoTooltip'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import { useFormatters } from '@/lib/useFormatters'

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-green-500/20 text-green-400',
  DISABLED: 'bg-red-500/20 text-red-400',
  EXPIRED: 'bg-yellow-500/20 text-yellow-400',
  LIMITED: 'bg-orange-500/20 text-orange-400',
}

type HwidFilter = 'all' | 'has_trial' | 'has_expired' | 'has_active'
type HwidSort = 'accounts' | 'recent' | 'active'

const NEW_ACCOUNT_WINDOW_MS = 7 * 24 * 3600 * 1000

function lastSeenTs(group: SharedHwidGroup): number {
  return Math.max(0, ...group.users.map((u) => (u.hwid_first_seen ? Date.parse(u.hwid_first_seen) : 0)))
}

function activeCount(group: SharedHwidGroup): number {
  return group.users.filter((u) => u.is_active).length
}

function activeTrialCount(group: SharedHwidGroup): number {
  return group.users.filter((u) => u.is_active && u.is_trial).length
}

function hasRecentAccount(group: SharedHwidGroup): boolean {
  return lastSeenTs(group) > Date.now() - NEW_ACCOUNT_WINDOW_MS
}

export function SharedHwidsCard() {
  const { t } = useTranslation()
  const openUser = useOpenUser()
  const [search, setSearch] = useState('')
  const [expandedHwid, setExpandedHwid] = useState<string | null>(null)
  const [filter, setFilter] = useState<HwidFilter>('all')
  const [platformFilter, setPlatformFilter] = useState('')
  const [minAccounts, setMinAccounts] = useState(2)
  const [sortBy, setSortBy] = useState<HwidSort>('accounts')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-shared-hwids'],
    queryFn: () => advancedAnalyticsApi.sharedHwids(2, 200),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const items: SharedHwidGroup[] = data?.items || []
  const banThreshold = data?.hard_block_accounts_threshold || 0
  const trialThreshold = data?.active_trials_threshold || 0

  const platforms = useMemo(
    () => [...new Set(items.map((g) => g.platform).filter(Boolean))] as string[],
    [items]
  )

  const stats = useMemo(() => ({
    groups: items.length,
    accounts: items.reduce((s, g) => s + g.user_count, 0),
    withActive: items.filter((g) => activeCount(g) > 0).length,
    overThreshold: banThreshold > 0 ? items.filter((g) => g.user_count >= banThreshold).length : 0,
    trialAbuse: trialThreshold > 0
      ? items.filter((g) => activeTrialCount(g) > trialThreshold).length
      : 0,
  }), [items, banThreshold, trialThreshold])

  const filtered = useMemo(() => {
    let result = items
    if (filter === 'has_trial') {
      result = result.filter((g) => g.users.some((u) => u.is_trial))
    } else if (filter === 'has_expired') {
      result = result.filter((g) => g.users.some((u) => !u.is_active && u.expire_date))
    } else if (filter === 'has_active') {
      result = result.filter((g) => g.users.some((u) => u.is_active))
    }
    if (platformFilter) {
      result = result.filter((g) => g.platform === platformFilter)
    }
    if (minAccounts > 2) {
      result = result.filter((g) => g.user_count >= minAccounts)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (g) =>
          g.hwid.toLowerCase().includes(q) ||
          g.users.some((u) => u.username?.toLowerCase().includes(q))
      )
    }
    const sorted = [...result]
    if (sortBy === 'recent') {
      sorted.sort((a, b) => lastSeenTs(b) - lastSeenTs(a))
    } else if (sortBy === 'active') {
      sorted.sort((a, b) => activeCount(b) - activeCount(a) || b.user_count - a.user_count)
    } else {
      sorted.sort((a, b) => b.user_count - a.user_count)
    }
    return sorted
  }, [items, search, filter, platformFilter, minAccounts, sortBy])

  const truncHwid = (hwid: string) =>
    hwid.length > 16 ? hwid.slice(0, 8) + '...' + hwid.slice(-4) : hwid

  const copyHwid = (hwid: string) => {
    navigator.clipboard.writeText(hwid)
    toast.success(t('common.copied', { defaultValue: 'Copied' }))
  }

  const { formatDateShort: formatDate } = useFormatters()

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Fingerprint className="w-5 h-5 text-red-400" />
            <CardTitle className="text-base">{t('violations.sharedHwids.title')}</CardTitle>
            <InfoTooltip text={t('violations.sharedHwids.tooltip')} side="right" />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Select value={sortBy} onValueChange={(v) => setSortBy(v as HwidSort)}>
              <SelectTrigger className="h-8 w-[150px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="accounts">{t('violations.sharedHwids.sort.accounts')}</SelectItem>
                <SelectItem value="recent">{t('violations.sharedHwids.sort.recent')}</SelectItem>
                <SelectItem value="active">{t('violations.sharedHwids.sort.active')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={String(minAccounts)} onValueChange={(v) => setMinAccounts(Number(v))}>
              <SelectTrigger className="h-8 w-[80px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[2, 3, 5, 7].map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}+</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {platforms.length > 1 && (
              <Select value={platformFilter || 'all'} onValueChange={(v) => setPlatformFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="h-8 w-[120px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('violations.sharedHwids.filter.all')}</SelectItem>
                  {platforms.map((p) => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <ExportDropdown
              disabled={filtered.length === 0}
              onExportCSV={() => exportCSV(filtered.flatMap((g) =>
                g.users.map((u) => ({
                  hwid: g.hwid, platform: g.platform ?? '', device: g.device_model ?? '',
                  username: u.username, status: u.status, is_trial: u.is_trial, is_active: u.is_active,
                  app_version: u.app_version ?? '',
                }))
              ), 'shared-hwids')}
              onExportJSON={() => exportJSON(filtered, 'shared-hwids')}
            />
          </div>
        </div>

        {/* Summary strip */}
        {items.length > 0 && (
          <div className="flex items-center gap-4 flex-wrap text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Smartphone className="w-3.5 h-3.5" />
              {t('violations.sharedHwids.stats.groups')}: <b className="text-white">{stats.groups}</b>
            </span>
            <span className="flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" />
              {t('violations.sharedHwids.stats.accounts')}: <b className="text-white">{stats.accounts}</b>
            </span>
            <span className="flex items-center gap-1.5">
              {t('violations.sharedHwids.stats.withActive')}: <b className="text-green-400">{stats.withActive}</b>
            </span>
            {banThreshold > 0 && (
              <span className="flex items-center gap-1.5">
                <ShieldBan className="w-3.5 h-3.5 text-red-400" />
                {t('violations.sharedHwids.stats.overThreshold', { thr: banThreshold })}: <b className="text-red-400">{stats.overThreshold}</b>
              </span>
            )}
            {trialThreshold > 0 && (
              <span className="flex items-center gap-1.5">
                <ShieldBan className="w-3.5 h-3.5 text-orange-400" />
                {t('violations.sharedHwids.stats.trialAbuse', { thr: trialThreshold })}: <b className="text-orange-400">{stats.trialAbuse}</b>
              </span>
            )}
          </div>
        )}

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            {(['all', 'has_trial', 'has_active', 'has_expired'] as HwidFilter[]).map((f) => (
              <Button
                key={f}
                variant={filter === f ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => setFilter(f)}
              >
                {t(`violations.sharedHwids.filter.${f}`)}
              </Button>
            ))}
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('violations.sharedHwids.searchPlaceholder')}
              className="pl-9 h-8 text-sm"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : filtered.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Fingerprint className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('violations.sharedHwids.noData')}</p>
              <p className="text-xs mt-1">{t('violations.sharedHwids.noDataHint')}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((group) => {
              const isOpen = expandedHwid === group.hwid
              const active = activeCount(group)
              const lastSeen = lastSeenTs(group)
              const overThreshold = banThreshold > 0 && group.user_count >= banThreshold
              const trialAbuse = trialThreshold > 0 && activeTrialCount(group) > trialThreshold
              return (
                <Fragment key={group.hwid}>
                  <div
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors',
                      isOpen
                        ? 'bg-red-500/10 border border-red-500/20'
                        : 'hover:bg-[var(--glass-bg-hover)]/40 border border-transparent'
                    )}
                    onClick={() => setExpandedHwid(isOpen ? null : group.hwid)}
                  >
                    {isOpen ? (
                      <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                    )}

                    <Smartphone className="w-4 h-4 text-muted-foreground shrink-0" />

                    <button
                      className="font-mono text-xs text-white hover:text-primary-400 transition-colors"
                      title={group.hwid}
                      onClick={(e) => { e.stopPropagation(); copyHwid(group.hwid) }}
                    >
                      {truncHwid(group.hwid)}
                      <Copy className="w-3 h-3 inline ml-1 opacity-40" />
                    </button>

                    {group.platform && (
                      <Badge variant="outline" className="text-[10px] h-5">
                        {group.platform}
                      </Badge>
                    )}
                    {group.device_model && (
                      <span className="text-xs text-muted-foreground hidden sm:inline truncate max-w-[150px]">
                        {group.device_model}
                      </span>
                    )}
                    {lastSeen > 0 && (
                      <span
                        className="hidden md:flex items-center gap-1 text-xs text-muted-foreground"
                        title={t('violations.sharedHwids.lastActivityTooltip')}
                      >
                        <Clock className="w-3 h-3" />
                        {formatDate(new Date(lastSeen).toISOString())}
                      </span>
                    )}

                    <div className="ml-auto flex items-center gap-1.5">
                      {hasRecentAccount(group) && (
                        <Badge className="bg-cyan-500/20 text-cyan-300 text-[10px] gap-1">
                          <Sparkles className="w-3 h-3" />
                          {t('violations.sharedHwids.newAccount')}
                        </Badge>
                      )}
                      {group.users.some((u) => u.is_trial) && (
                        <Badge className="bg-yellow-500/20 text-yellow-300 text-[10px]">trial</Badge>
                      )}
                      {overThreshold && (
                        <Badge
                          className="bg-red-600/30 text-red-300 text-[10px] gap-1"
                          title={t('violations.sharedHwids.overThresholdTooltip', { thr: banThreshold })}
                        >
                          <ShieldBan className="w-3 h-3" />
                          {t('violations.sharedHwids.overThresholdBadge', { thr: banThreshold })}
                        </Badge>
                      )}
                      {trialAbuse && (
                        <Badge
                          className="bg-orange-600/30 text-orange-200 text-[10px] gap-1"
                          title={t('violations.sharedHwids.trialAbuseTooltip', { thr: trialThreshold })}
                        >
                          <ShieldBan className="w-3 h-3" />
                          {t('violations.sharedHwids.trialAbuseBadge', { count: activeTrialCount(group) })}
                        </Badge>
                      )}
                      {active > 0 && (
                        <Badge className="bg-green-500/20 text-green-300 text-xs">
                          {active} {t('violations.sharedHwids.activeShort')}
                        </Badge>
                      )}
                      <Badge className="bg-red-500/20 text-red-300 text-xs">
                        {group.user_count} {t('violations.sharedHwids.accounts')}
                      </Badge>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="ml-8 mb-2 border border-[var(--glass-border)] rounded-lg overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t('violations.sharedHwids.user')}</TableHead>
                            <TableHead className="text-xs hidden sm:table-cell">{t('violations.sharedHwids.status')}</TableHead>
                            <TableHead className="text-xs hidden sm:table-cell">{t('violations.sharedHwids.subscription')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('violations.sharedHwids.createdAt')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('violations.sharedHwids.firstSeen')}</TableHead>
                            <TableHead className="text-xs hidden lg:table-cell">{t('violations.sharedHwids.appVersion')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {group.users.map((user) => (
                            <TableRow
                              key={user.uuid}
                              className="cursor-pointer hover:bg-[var(--glass-bg-hover)]/30"
                              {...openUser(user.uuid)}
                            >
                              <TableCell>
                                <div className="flex items-center gap-1.5">
                                  <span className="font-medium text-white text-sm hover:text-primary-400 transition-colors">
                                    {user.username || user.uuid.slice(0, 8)}
                                  </span>
                                  {user.is_trial && (
                                    <Badge className="bg-yellow-500/20 text-yellow-300 text-[10px] px-1.5 py-0">trial</Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="hidden sm:table-cell">
                                <Badge
                                  variant="secondary"
                                  className={cn('text-xs', STATUS_COLORS[user.status] || '')}
                                >
                                  {t(`analytics.status.${user.status}`, { defaultValue: user.status })}
                                </Badge>
                              </TableCell>
                              <TableCell className="hidden sm:table-cell">
                                {user.expire_date ? (
                                  <Badge
                                    variant="secondary"
                                    className={cn('text-xs', user.is_active ? 'bg-green-500/20 text-green-300' : 'bg-[var(--glass-bg-hover)] text-dark-200')}
                                  >
                                    {user.is_active
                                      ? t('violations.sharedHwids.active')
                                      : t('violations.sharedHwids.expired')}
                                  </Badge>
                                ) : (
                                  <span className="text-xs text-dark-300">-</span>
                                )}
                              </TableCell>
                              <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                                {formatDate(user.created_at)}
                              </TableCell>
                              <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                                {formatDate(user.hwid_first_seen)}
                              </TableCell>
                              <TableCell className="hidden lg:table-cell text-xs text-muted-foreground font-mono">
                                {user.app_version || '-'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </Fragment>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
