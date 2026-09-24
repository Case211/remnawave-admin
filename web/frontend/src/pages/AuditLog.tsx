import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { subDays } from 'date-fns'
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Clock,
  User,
  Shield,
  Server,
  Globe,
  Settings,
  ShieldAlert,
  Users,
  UserCog,
  Activity,
  FileText,
  Zap,
} from '@/components/brand/icons'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import { QueryError } from '@/components/QueryError'
import { ExportDropdown } from '@/components/ExportDropdown'
import { auditApi, type AuditLogEntry, type AuditLogParams } from '@/api/audit'
import { useFormatters } from '@/lib/useFormatters'
import {
  resourceKey,
  resourceStyleKey,
  getResourceLabel,
  getActionLabelT,
  getDetailLabel,
  parseAction,
  getActionColor,
  tryParseJSON,
  formatDetailValue,
  getDescription,
  getVisibleDetails,
} from '@/lib/auditFormat'

// ── Constants ───────────────────────────────────────────────────

const PER_PAGE = 30

const RESOURCE_ICONS: Record<string, typeof Users> = {
  users: Users,
  nodes: Server,
  hosts: Globe,
  violations: ShieldAlert,
  settings: Settings,
  admins: UserCog,
  roles: Shield,
  auth: User,
  fleet: Activity,
  automation: Zap,
}

// Mono-accent: all resource badges use the theme accent color
const ACCENT_RESOURCE = 'bg-primary/20 text-primary-400 border-primary/30'
const RESOURCE_COLORS: Record<string, string> = {
  users: ACCENT_RESOURCE,
  nodes: ACCENT_RESOURCE,
  hosts: ACCENT_RESOURCE,
  violations: 'bg-red-500/20 text-red-400 border-red-500/30', // semantic: violations = danger
  settings: ACCENT_RESOURCE,
  admins: ACCENT_RESOURCE,
  roles: ACCENT_RESOURCE,
  auth: 'bg-muted text-muted-foreground border-border',
  automation: ACCENT_RESOURCE,
}

// ── Component ───────────────────────────────────────────────────

export default function AuditLog() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [resourceFilter, setResourceFilter] = useState<string>('all')
  const [actionFilter, setActionFilter] = useState<string>('all')
  const [periodFilter, setPeriodFilter] = useState<string>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [adminFilter, setAdminFilter] = useState<string>('all')
  const [ipFilter, setIpFilter] = useState('')
  // «Весь журнал» из истории в карточке юзера или ноды — ?resource_id=
  const [searchParams, setSearchParams] = useSearchParams()
  const resourceIdFilter = searchParams.get('resource_id') || ''
  const [searchInput, setSearchInput] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const PERIOD_OPTIONS = useMemo(() => [
    { value: 'all', label: t('audit.period.all') },
    { value: '24h', label: t('audit.period.24h') },
    { value: '7d', label: t('audit.period.7d') },
    { value: '30d', label: t('audit.period.30d') },
    { value: 'custom', label: t('audit.period.custom') },
  ], [t])

  // Build query params
  const params = useMemo<AuditLogParams>(() => {
    const p: AuditLogParams = {
      limit: PER_PAGE,
      offset: (page - 1) * PER_PAGE,
    }
    if (search) p.search = search
    if (resourceFilter !== 'all') p.resource = resourceFilter
    if (adminFilter !== 'all') p.admin_username = adminFilter
    if (ipFilter) p.ip_address = ipFilter
    if (resourceIdFilter) p.resource_id = resourceIdFilter
    // Точное действие: «create» без точки ловил и «create_external_server»
    if (actionFilter !== 'all') p.action = `.${actionFilter}`
    if (periodFilter !== 'all') {
      const now = new Date()
      if (periodFilter === '24h') p.date_from = subDays(now, 1).toISOString()
      else if (periodFilter === '7d') p.date_from = subDays(now, 7).toISOString()
      else if (periodFilter === '30d') p.date_from = subDays(now, 30).toISOString()
      // Голая дата — сутки по часам панели, «по» включает весь день
      else if (periodFilter === 'custom') {
        if (dateFrom) p.date_from = dateFrom
        if (dateTo) p.date_to = dateTo
      }
    }
    return p
  }, [page, search, resourceFilter, actionFilter, periodFilter, dateFrom, dateTo, adminFilter, ipFilter, resourceIdFilter])

  const { data, isLoading, isError: isDataError, refetch } = useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => auditApi.list(params),
    refetchInterval: 60_000,
  })

  const { data: stats, isError: isStatsError, refetch: refetchStats } = useQuery({
    queryKey: ['audit-stats'],
    queryFn: () => auditApi.stats(),
    staleTime: 30000,
  })

  const { data: auditAdmins } = useQuery({
    queryKey: ['audit-admins'],
    queryFn: () => auditApi.admins(),
    staleTime: 60000,
  })

  const { data: actions, isError: isActionsError, refetch: refetchActions } = useQuery({
    queryKey: ['audit-actions'],
    queryFn: () => auditApi.actions(),
    staleTime: 60000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  // Unique resources from actions
  const resources = useMemo(() => {
    if (!actions) return []
    const set = new Set<string>()
    actions.forEach((a) => {
      const dot = a.indexOf('.')
      if (dot > 0) set.add(resourceKey(a.slice(0, dot)))
    })
    return Array.from(set).sort()
  }, [actions])

  // Unique action types for filter
  const actionTypes = useMemo(() => {
    if (!actions) return []
    const set = new Set<string>()
    actions.forEach((a) => {
      const dot = a.indexOf('.')
      if (dot > 0) set.add(a.slice(dot + 1))
    })
    return Array.from(set).sort()
  }, [actions])

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(1)
  }

  const toggleRow = (id: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const hasError = isDataError || isStatsError || isActionsError
  const handleRetry = () => { refetch(); refetchStats(); refetchActions() }

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('audit.title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t('audit.subtitle')}
          </p>
        </div>
        <ExportDropdown
          onExportCSV={() => auditApi.export(params, 'csv').catch(() => toast.error(t('common.error')))}
          onExportJSON={() => auditApi.export(params, 'json').catch(() => toast.error(t('common.error')))}
          disabled={total === 0}
        />
      </div>

      {hasError && <QueryError onRetry={handleRetry} />}

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/20">
                <FileText className="w-4 h-4 text-primary-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.totalRecords')}</p>
                <p className="text-lg font-bold text-white">{stats?.total?.toLocaleString() ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/20">
                <Clock className="w-4 h-4 text-primary-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.today')}</p>
                <p className="text-lg font-bold text-white">{stats?.today ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/20">
                <Users className="w-4 h-4 text-primary-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.activeAdmins')}</p>
                <p className="text-lg font-bold text-white">{stats?.by_admin?.length ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/20">
                <Activity className="w-4 h-4 text-primary-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">
                  {t('audit.stats.resourceTypesPeriod', { days: stats?.period_days ?? 30 })}
                </p>
                <p className="text-lg font-bold text-white">
                  {stats?.by_resource ? Object.keys(stats.by_resource).length : '\u2014'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder={t('audit.searchPlaceholder')}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="pl-9 bg-[var(--glass-bg)] border-[var(--glass-border)]"
              />
            </div>
            <Select value={resourceFilter} onValueChange={(v) => { setResourceFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-[var(--glass-bg)] border-[var(--glass-border)]">
                <Filter className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue placeholder={t('audit.resource')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('audit.allResources')}</SelectItem>
                {resources.map((r) => (
                  <SelectItem key={r} value={r}>
                    {getResourceLabel(t, r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[180px] bg-[var(--glass-bg)] border-[var(--glass-border)]">
                <Activity className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue placeholder={t('audit.action')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('audit.allActions')}</SelectItem>
                {actionTypes.map((a) => (
                  <SelectItem key={a} value={a}>
                    {getActionLabelT(t, a)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={adminFilter} onValueChange={(v) => { setAdminFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[170px] bg-[var(--glass-bg)] border-[var(--glass-border)]">
                <User className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue placeholder={t('audit.admin')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('audit.allAdmins')}</SelectItem>
                {(auditAdmins ?? []).map((a) => (
                  <SelectItem key={a.username} value={a.username}>
                    {a.username}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={periodFilter} onValueChange={(v) => { setPeriodFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-[var(--glass-bg)] border-[var(--glass-border)]">
                <Clock className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIOD_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {periodFilter === 'custom' && (
              <div className="flex items-center gap-2">
                <Input
                  type="date"
                  value={dateFrom}
                  max={dateTo || undefined}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
                  aria-label={t('audit.dateFrom')}
                  className="w-[150px] bg-[var(--glass-bg)] border-[var(--glass-border)]"
                />
                <span className="text-muted-foreground">{'\u2014'}</span>
                <Input
                  type="date"
                  value={dateTo}
                  min={dateFrom || undefined}
                  onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
                  aria-label={t('audit.dateTo')}
                  className="w-[150px] bg-[var(--glass-bg)] border-[var(--glass-border)]"
                />
              </div>
            )}
            <Button
              variant="outline"
              onClick={handleSearch}
              className="border-[var(--glass-border)]"
            >
              <Search className="w-4 h-4 mr-2" />
              {t('common.search')}
            </Button>
          </div>
          {(ipFilter || resourceIdFilter) && (
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              {resourceIdFilter && (
                <FilterChip
                  label={`ID: ${resourceIdFilter}`}
                  clearLabel={t('audit.clearFilter')}
                  onClear={() => { setSearchParams({}); setPage(1) }}
                />
              )}
              {ipFilter && (
                <FilterChip
                  label={`IP: ${ipFilter}`}
                  clearLabel={t('audit.clearIpFilter')}
                  onClear={() => { setIpFilter(''); setPage(1) }}
                />
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>{t('audit.noRecords')}</p>
            </div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden md:block overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-[var(--glass-border)] hover:bg-transparent">
                      <TableHead className="text-dark-200 w-[160px]">{t('audit.table.date')}</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">{t('audit.table.admin')}</TableHead>
                      <TableHead className="text-dark-200">{t('audit.table.action')}</TableHead>
                      <TableHead className="text-dark-200">{t('audit.table.details')}</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">IP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <AuditRow
                        key={item.id}
                        item={item}
                        expanded={expandedRows.has(item.id)}
                        onToggle={() => toggleRow(item.id)}
                        onFilterIp={(ip) => { setIpFilter(ip); setPage(1) }}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden p-4 space-y-3">
                {items.map((item) => (
                  <MobileAuditCard key={item.id} item={item} />
                ))}
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between p-4 border-t border-[var(--glass-border)]">
                <p className="text-sm text-muted-foreground">
                  {t('audit.totalEntries', { count: total })}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="border-[var(--glass-border)]"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-dark-200">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                    className="border-[var(--glass-border)]"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function FilterChip({ label, clearLabel, onClear }: { label: string; clearLabel: string; onClear: () => void }) {
  return (
    <Badge variant="outline" className="gap-1.5 font-mono text-xs">
      {label}
      <button type="button" onClick={onClear} aria-label={clearLabel} className="text-muted-foreground hover:text-white">
        {'\u2715'}
      </button>
    </Badge>
  )
}

// ── Desktop Row Component ────────────────────────────────────────

function AuditRow({
  item,
  expanded,
  onToggle,
  onFilterIp,
}: {
  item: AuditLogEntry
  expanded: boolean
  onToggle: () => void
  onFilterIp: (ip: string) => void
}) {
  const { t } = useTranslation()
  const { formatTimeAgo, formatDate } = useFormatters()
  const parsed = parseAction(item.action)
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || RESOURCE_ICONS[resourceStyleKey(parsed.resource)] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || RESOURCE_COLORS[resourceStyleKey(parsed.resource)] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(t, parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const hasDetails = visibleDetails.length > 0

  return (
    <>
      <TableRow
        className={`border-[var(--glass-border)] ${hasDetails ? 'cursor-pointer hover:bg-[var(--glass-bg)]' : ''}`}
        onClick={hasDetails ? onToggle : undefined}
      >
        {/* Date */}
        <TableCell className="text-dark-200 whitespace-nowrap align-top">
          <Tooltip>
            <TooltipTrigger>
              <span className="text-sm">
                {item.created_at
                  ? formatTimeAgo(item.created_at)
                  : '\u2014'}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {item.created_at
                ? formatDate(item.created_at)
                : ''}
            </TooltipContent>
          </Tooltip>
        </TableCell>

        {/* Admin */}
        <TableCell className="align-top">
          <span className="font-medium text-white text-sm">
            {item.admin_username}
          </span>
        </TableCell>

        {/* Action (resource badge + action badge + description) */}
        <TableCell className="align-top">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              {parsed.resource && (
                <Badge
                  variant="outline"
                  className={`${resourceColor} border text-xs gap-1`}
                >
                  <ResourceIcon className="w-3 h-3" />
                  {getResourceLabel(t, parsed.resource)}
                </Badge>
              )}
              <Badge
                variant="outline"
                className={`${actionColor} border text-xs`}
              >
                {getActionLabelT(t, parsed.action)}
              </Badge>
            </div>
            <p className="text-sm text-dark-100">{description}</p>
          </div>
        </TableCell>

        {/* Details preview */}
        <TableCell className="align-top">
          {hasDetails ? (
            <div className="flex items-center gap-2">
              <div className="space-y-0.5 flex-1 min-w-0">
                {visibleDetails.slice(0, 2).map(([key, value]) => (
                  <div key={key} className="text-xs text-dark-300 truncate">
                    <span className="text-dark-400">{getDetailLabel(t, key)}:</span>{' '}
                    <span className="text-dark-200">{formatDetailValue(t, key, value)}</span>
                  </div>
                ))}
                {visibleDetails.length > 2 && (
                  <span className="text-xs text-dark-500">
                    {t('audit.moreDetails', { count: visibleDetails.length - 2 })}
                  </span>
                )}
              </div>
              <ChevronDown
                className={`w-4 h-4 text-dark-400 shrink-0 transition-transform ${
                  expanded ? 'rotate-180' : ''
                }`}
              />
            </div>
          ) : (
            <span className="text-xs text-dark-500">{'\u2014'}</span>
          )}
        </TableCell>

        {/* IP — клик ставит фильтр */}
        <TableCell className="text-dark-300 font-mono text-xs align-top">
          {item.ip_address ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onFilterIp(item.ip_address as string) }}
              className="hover:text-primary-400 hover:underline"
              title={t('audit.filterByIp')}
            >
              {item.ip_address}
            </button>
          ) : '\u2014'}
        </TableCell>
      </TableRow>

      {/* Expanded details row */}
      {expanded && hasDetails && (
        <TableRow className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
          <TableCell colSpan={5} className="py-3 px-6">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-2">
              {visibleDetails.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <p className="text-xs text-dark-400 mb-0.5">{getDetailLabel(t, key)}</p>
                  <p className="text-sm text-dark-100 break-words">{formatDetailValue(t, key, value)}</p>
                </div>
              ))}
            </div>
            {item.resource_id && (
              <div className="mt-3 pt-2 border-t border-[var(--glass-border)]">
                <span className="text-xs text-dark-400">{t('audit.resourceId')}: </span>
                <span className="text-xs text-dark-200 font-mono">{item.resource_id}</span>
              </div>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── Mobile Card Component ────────────────────────────────────────

function MobileAuditCard({ item }: { item: AuditLogEntry }) {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
  const parsed = parseAction(item.action)
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || RESOURCE_ICONS[resourceStyleKey(parsed.resource)] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || RESOURCE_COLORS[resourceStyleKey(parsed.resource)] || 'bg-gray-500/20 text-gray-400'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(t, parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] space-y-2"
      onClick={visibleDetails.length > 0 ? () => setExpanded(!expanded) : undefined}
    >
      {/* Header: admin + time */}
      <div className="flex items-center justify-between">
        <span className="font-medium text-white text-sm">
          {item.admin_username}
        </span>
        <span className="text-xs text-muted-foreground">
          {item.created_at
            ? formatTimeAgo(item.created_at)
            : ''}
        </span>
      </div>

      {/* Badges */}
      <div className="flex items-center gap-2 flex-wrap">
        {parsed.resource && (
          <Badge
            variant="outline"
            className={`${resourceColor} border text-xs gap-1`}
          >
            <ResourceIcon className="w-3 h-3" />
            {getResourceLabel(t, parsed.resource)}
          </Badge>
        )}
        <Badge
          variant="outline"
          className={`${actionColor} border text-xs`}
        >
          {getActionLabelT(t, parsed.action)}
        </Badge>
      </div>

      {/* Description */}
      <p className="text-sm text-dark-100">{description}</p>

      {/* Details preview */}
      {visibleDetails.length > 0 && (
        <div className="space-y-1">
          {(expanded ? visibleDetails : visibleDetails.slice(0, 2)).map(([key, value]) => (
            <div key={key} className="text-xs text-dark-300">
              <span className="text-dark-400">{getDetailLabel(t, key)}:</span>{' '}
              <span className="text-dark-200">{formatDetailValue(t, key, value)}</span>
            </div>
          ))}
          {!expanded && visibleDetails.length > 2 && (
            <span className="text-xs text-dark-500">
              {t('audit.moreDetails', { count: visibleDetails.length - 2 })}...
            </span>
          )}
        </div>
      )}

      {/* Footer: IP + resource ID */}
      <div className="flex items-center justify-between pt-1 border-t border-[var(--glass-border)]/50">
        {item.ip_address && (
          <span className="text-xs text-muted-foreground font-mono">
            {item.ip_address}
          </span>
        )}
        {item.resource_id && (
          <span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
            ID: {item.resource_id}
          </span>
        )}
      </div>
    </div>
  )
}
