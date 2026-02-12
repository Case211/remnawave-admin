import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { format, subDays } from 'date-fns'
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
} from 'lucide-react'
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
import { ExportDropdown } from '@/components/ExportDropdown'
import { exportCSV, exportJSON } from '@/lib/export'
import { auditApi, type AuditLogEntry, type AuditLogParams } from '@/api/audit'
import { useFormatters } from '@/lib/useFormatters'
import type { TFunction } from 'i18next'

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

const RESOURCE_COLORS: Record<string, string> = {
  users: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  nodes: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  hosts: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  violations: 'bg-red-500/20 text-red-400 border-red-500/30',
  settings: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  admins: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  roles: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  auth: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  automation: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
}

// ── Helpers ──────────────────────────────────────────────────────

function getResourceLabel(t: TFunction, resource: string): string {
  return t(`audit.resources.${resource}`, { defaultValue: resource })
}

function getActionLabelT(t: TFunction, action: string): string {
  return t(`audit.actions.${action}`, { defaultValue: action })
}

function getDetailLabel(t: TFunction, key: string): string {
  return t(`audit.details.${key}`, { defaultValue: key })
}

function parseAction(fullAction: string): { resource: string; action: string } {
  const dot = fullAction.indexOf('.')
  if (dot === -1) return { resource: '', action: fullAction }
  return { resource: fullAction.slice(0, dot), action: fullAction.slice(dot + 1) }
}

function getActionColor(action: string): string {
  if (action.includes('delete') || action === 'disable' || action.includes('revoke'))
    return 'bg-red-500/20 text-red-400 border-red-500/30'
  if (action === 'create' || action === 'enable')
    return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
  if (action.includes('login') || action === 'change_password')
    return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
  if (action === 'logout')
    return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
}

function tryParseJSON(str: string | null): Record<string, unknown> | null {
  if (!str) return null
  try {
    const parsed = JSON.parse(str)
    return typeof parsed === 'object' && parsed !== null ? parsed : null
  } catch {
    return null
  }
}

function formatBytesRaw(bytes: unknown): string {
  const num = Number(bytes)
  if (isNaN(num) || num === 0) return '0'
  if (num >= 1099511627776) return `${(num / 1099511627776).toFixed(1)} TB`
  if (num >= 1073741824) return `${(num / 1073741824).toFixed(1)} GB`
  if (num >= 1048576) return `${(num / 1048576).toFixed(1)} MB`
  return `${(num / 1024).toFixed(0)} KB`
}

function formatDetailValue(t: TFunction, key: string, value: unknown): string {
  if (value === null || value === undefined) return '\u2014'
  if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no')
  if (key === 'data_limit' && typeof value === 'number') return formatBytesRaw(value)
  if (key === 'expire_date' && typeof value === 'string') {
    try {
      return format(new Date(value), 'dd.MM.yyyy HH:mm')
    } catch { return String(value) }
  }
  if (key === 'new_state') return value === 'enabled' ? t('common.enabled') : t('common.disabled')
  if (key === 'is_disabled') return value ? t('common.yes') : t('common.no')
  if (key === 'is_active') return value ? t('common.yes') : t('common.no')
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function getDescription(
  t: TFunction,
  resource: string,
  action: string,
  resourceId: string | null,
  details: Record<string, unknown> | null,
): string {
  const target = (details?.username as string)
    || (details?.name as string)
    || (details?.remark as string)
    || (details?.setting as string)
    || resourceId
    || ''

  // Special case for automation toggle
  if (resource === 'automation' && action === 'toggle') {
    const name = (details?.name as string) || target
    return details?.new_state === 'enabled'
      ? t('audit.descriptions.automation.toggle_on', { target: name })
      : t('audit.descriptions.automation.toggle_off', { target: name })
  }

  const key = `audit.descriptions.${resource}.${action}`
  const result = t(key, { target })
  if (result && result !== key) return result

  // Fallback: generate a generic description
  const actionLabel = getActionLabelT(t, action).toLowerCase()
  const resourceLabel = getResourceLabel(t, resource).toLowerCase()
  return `${actionLabel} ${resourceLabel}${target ? ` ${target}` : ''}`
}

/** Get top N detail entries, excluding keys already used in description */
function getVisibleDetails(details: Record<string, unknown> | null): [string, unknown][] {
  if (!details) return []
  const skipKeys = new Set(['setting'])
  return Object.entries(details).filter(([k]) => !skipKeys.has(k))
}

// ── Component ───────────────────────────────────────────────────

export default function AuditLog() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [resourceFilter, setResourceFilter] = useState<string>('all')
  const [actionFilter, setActionFilter] = useState<string>('all')
  const [periodFilter, setPeriodFilter] = useState<string>('all')
  const [searchInput, setSearchInput] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const PERIOD_OPTIONS = useMemo(() => [
    { value: 'all', label: t('audit.period.all') },
    { value: '24h', label: t('audit.period.24h') },
    { value: '7d', label: t('audit.period.7d') },
    { value: '30d', label: t('audit.period.30d') },
  ], [t])

  // Build query params
  const params = useMemo<AuditLogParams>(() => {
    const p: AuditLogParams = {
      limit: PER_PAGE,
      offset: (page - 1) * PER_PAGE,
    }
    if (search) p.search = search
    if (resourceFilter !== 'all') p.resource = resourceFilter
    if (actionFilter !== 'all') p.action = actionFilter
    if (periodFilter !== 'all') {
      const now = new Date()
      if (periodFilter === '24h') p.date_from = subDays(now, 1).toISOString()
      else if (periodFilter === '7d') p.date_from = subDays(now, 7).toISOString()
      else if (periodFilter === '30d') p.date_from = subDays(now, 30).toISOString()
    }
    return p
  }, [page, search, resourceFilter, actionFilter, periodFilter])

  const { data, isLoading } = useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => auditApi.list(params),
    refetchInterval: 15000,
  })

  const { data: stats } = useQuery({
    queryKey: ['audit-stats'],
    queryFn: () => auditApi.stats(),
    staleTime: 30000,
  })

  const { data: actions } = useQuery({
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
      if (dot > 0) set.add(a.slice(0, dot))
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

  // Export data
  const exportData = useMemo(
    () =>
      items.map((item) => {
        const { resource, action } = parseAction(item.action)
        const details = tryParseJSON(item.details)
        return {
          id: item.id,
          date: item.created_at ? format(new Date(item.created_at), 'yyyy-MM-dd HH:mm:ss') : '',
          admin: item.admin_username,
          resource,
          action: getActionLabelT(t, action),
          description: getDescription(t, resource, action, item.resource_id, details),
          resource_id: item.resource_id || '',
          details: item.details || '',
          ip: item.ip_address || '',
        }
      }),
    [items, t],
  )

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
          onExportCSV={() => exportCSV(exportData, 'audit-log')}
          onExportJSON={() => exportJSON(exportData, 'audit-log')}
          disabled={items.length === 0}
        />
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/20">
                <FileText className="w-4 h-4 text-cyan-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.totalRecords')}</p>
                <p className="text-lg font-bold text-white">{stats?.total?.toLocaleString() ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/20">
                <Clock className="w-4 h-4 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.today')}</p>
                <p className="text-lg font-bold text-white">{stats?.today ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-500/20">
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.activeAdmins')}</p>
                <p className="text-lg font-bold text-white">{stats?.by_admin?.length ?? '\u2014'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-500/20">
                <Activity className="w-4 h-4 text-purple-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.stats.resourceTypes')}</p>
                <p className="text-lg font-bold text-white">
                  {stats?.by_resource ? Object.keys(stats.by_resource).length : '\u2014'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="bg-dark-800 border-dark-700">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder={t('audit.searchPlaceholder')}
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="pl-9 bg-dark-900 border-dark-600"
              />
            </div>
            <Select value={resourceFilter} onValueChange={(v) => { setResourceFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-dark-900 border-dark-600">
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
              <SelectTrigger className="w-[180px] bg-dark-900 border-dark-600">
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
            <Select value={periodFilter} onValueChange={(v) => { setPeriodFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-dark-900 border-dark-600">
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
            <Button
              variant="outline"
              onClick={handleSearch}
              className="border-dark-600"
            >
              <Search className="w-4 h-4 mr-2" />
              {t('common.search')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-dark-800 border-dark-700">
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
                    <TableRow className="border-dark-700 hover:bg-transparent">
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
              <div className="flex items-center justify-between p-4 border-t border-dark-700">
                <p className="text-sm text-muted-foreground">
                  {t('audit.totalEntries', { count: total })}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="border-dark-600"
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
                    className="border-dark-600"
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

// ── Desktop Row Component ────────────────────────────────────────

function AuditRow({
  item,
  expanded,
  onToggle,
}: {
  item: AuditLogEntry
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const { formatTimeAgo, formatDate } = useFormatters()
  const parsed = parseAction(item.action)
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(t, parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const hasDetails = visibleDetails.length > 0

  return (
    <>
      <TableRow
        className={`border-dark-700 ${hasDetails ? 'cursor-pointer hover:bg-dark-700/50' : ''}`}
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
            <span className="text-xs text-dark-500">\u2014</span>
          )}
        </TableCell>

        {/* IP */}
        <TableCell className="text-dark-300 font-mono text-xs align-top">
          {item.ip_address || '\u2014'}
        </TableCell>
      </TableRow>

      {/* Expanded details row */}
      {expanded && hasDetails && (
        <TableRow className="border-dark-700 bg-dark-900/50">
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
              <div className="mt-3 pt-2 border-t border-dark-700">
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
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(t, parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="p-3 rounded-lg bg-dark-900 border border-dark-700 space-y-2"
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
      <div className="flex items-center justify-between pt-1 border-t border-dark-700/50">
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
