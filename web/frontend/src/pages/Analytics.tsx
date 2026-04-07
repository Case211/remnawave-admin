import { useState, useMemo, useCallback, memo, lazy, Suspense, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useTabParam } from '@/lib/useTabParam'
import { usePermissionStore } from '@/store/permissionStore'
import {
  Globe,
  Users,
  TrendingUp,
  ArrowUpRight,
  MapPin,
  BarChart3,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronRight,
  Search,
  ArrowUpDown,
  Fingerprint,
  Smartphone,
  Copy,
  Server,
  Cpu,
  Activity,
  Shield,
  Network,
  GitCompare,
  CalendarDays,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { toast } from 'sonner'
import { advancedAnalyticsApi } from '@/api/advancedAnalytics'
import type { GeoCity, GeoCityUser, TopUser, SharedHwidGroup, NodeFleetItem, RetentionCohort, NodeMetricsHistoryItem, NodeMetricsTimeseriesPoint, GeoBalanceNode, GeoBalanceRecommendation } from '@/api/advancedAnalytics'
import { ExportDropdown } from '@/components/ExportDropdown'
import { exportCSV, exportJSON, formatBytesForExport } from '@/lib/export'

// Lazy-load the map component (leaflet + react-leaflet + clustering)
const LazyGeoMap = lazy(() => import('@/components/LazyGeoMap'))
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
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
import { useChartTheme } from '@/lib/useChartTheme'
import { useFormatters } from '@/lib/useFormatters'

// ── Period Switcher ─────────────────────────────────────────────

function PeriodSwitcher({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="flex items-center gap-1 bg-[var(--glass-bg)] rounded-lg p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'px-2.5 py-1 text-xs rounded-md transition-all duration-200',
            value === opt.value
              ? 'bg-primary/20 text-primary-400 font-medium'
              : 'text-muted-foreground hover:text-white',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Utilities ───────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const parts = dateStr.split('-')
  if (parts.length === 3) return `${parts[2]}.${parts[1]}`
  return dateStr
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-green-500/20 text-green-400',
  DISABLED: 'bg-red-500/20 text-red-400',
  EXPIRED: 'bg-yellow-500/20 text-yellow-400',
  LIMITED: 'bg-orange-500/20 text-orange-400',
}

// ── Chart Tooltip ───────────────────────────────────────────────

interface TrendTooltipProps {
  active?: boolean
  payload?: { value: number }[]
  label?: string
  metric?: string
}

function TrendTooltip({ active, payload, label, metric }: TrendTooltipProps) {
  const chart = useChartTheme()
  const { formatBytes } = useFormatters()
  if (!active || !payload?.length) return null
  const val = payload[0].value
  return (
    <div style={chart.tooltipStyle} className="px-3 py-2">
      <p className={cn("text-xs mb-1", chart.tooltipMutedClass)}>{label}</p>
      <p className={cn("text-sm font-medium", chart.tooltipTextClass)}>
        {metric === 'traffic' ? formatBytes(val) : val.toLocaleString()}
      </p>
    </div>
  )
}

// ── Date Range Picker (F4) ──────────────────────────────────────

function DateRangePicker({
  dateFrom,
  dateTo,
  onChange,
  onClear,
}: {
  dateFrom: string
  dateTo: string
  onChange: (from: string, to: string) => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="date"
        value={dateFrom}
        onChange={(e) => onChange(e.target.value, dateTo)}
        className="h-7 px-1.5 text-xs rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-white focus:outline-none focus:ring-1 focus:ring-primary/50"
      />
      <span className="text-xs text-muted-foreground">–</span>
      <input
        type="date"
        value={dateTo}
        onChange={(e) => onChange(dateFrom, e.target.value)}
        className="h-7 px-1.5 text-xs rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-white focus:outline-none focus:ring-1 focus:ring-primary/50"
      />
      {(dateFrom || dateTo) && (
        <button
          onClick={onClear}
          className="text-xs text-muted-foreground hover:text-white px-1.5 py-0.5 rounded hover:bg-[var(--glass-bg-hover)]"
          title={t('common.clear', { defaultValue: 'Clear' })}
        >
          ✕
        </button>
      )}
    </div>
  )
}

// ── Geo Map Card ────────────────────────────────────────────────

function GeoMapCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [geoPeriod, setGeoPeriod] = useState('7d')
  const [geoDateFrom, setGeoDateFrom] = useState('')
  const [geoDateTo, setGeoDateTo] = useState('')
  const chart = useChartTheme()

  const hasCustomDates = Boolean(geoDateFrom)
  const apiDateFrom = hasCustomDates ? new Date(geoDateFrom).toISOString() : undefined
  const apiDateTo = hasCustomDates && geoDateTo ? new Date(geoDateTo + 'T23:59:59').toISOString() : undefined

  const { data: geoData, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-geo', geoPeriod, geoDateFrom, geoDateTo],
    queryFn: () => advancedAnalyticsApi.geo(geoPeriod, apiDateFrom, apiDateTo),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const cities = geoData?.cities || []
  const countries = geoData?.countries || []

  // Compute max count for radius scaling
  const maxCount = useMemo(
    () => Math.max(1, ...cities.map((c: GeoCity) => c.count)),
    [cities],
  )

  // Map center: if we have cities, use weighted center; otherwise default
  const center = useMemo(() => {
    if (cities.length === 0) return [50, 40] as [number, number]
    const totalWeight = cities.reduce((s: number, c: GeoCity) => s + c.count, 0)
    if (totalWeight === 0) return [50, 40] as [number, number]
    const lat = cities.reduce((s: number, c: GeoCity) => s + c.lat * c.count, 0) / totalWeight
    const lon = cities.reduce((s: number, c: GeoCity) => s + c.lon * c.count, 0) / totalWeight
    return [lat, lon] as [number, number]
  }, [cities])

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.geo.title')}</CardTitle>
            <InfoTooltip
              text={t('analytics.geo.tooltip')}
              side="right"
            />
          </div>
          <div className="flex items-center gap-2">
            {!hasCustomDates && (
              <PeriodSwitcher
                value={geoPeriod}
                onChange={setGeoPeriod}
                options={[
                  { value: '24h', label: t('analytics.periods.24h') },
                  { value: '7d', label: t('analytics.periods.7d') },
                  { value: '30d', label: t('analytics.periods.30d') },
                  { value: 'all', label: t('analytics.periods.all') },
                ]}
              />
            )}
            <DateRangePicker
              dateFrom={geoDateFrom}
              dateTo={geoDateTo}
              onChange={(from, to) => { setGeoDateFrom(from); setGeoDateTo(to) }}
              onClear={() => { setGeoDateFrom(''); setGeoDateTo('') }}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[400px] w-full rounded-lg" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : cities.length === 0 && countries.length === 0 ? (
          <div className="h-[400px] flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <MapPin className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('analytics.geo.noData')}</p>
              <p className="text-xs mt-1">{t('analytics.geo.noDataHint')}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Map — lazy-loaded with clustering */}
            <div className="h-[400px] rounded-lg overflow-hidden border border-[var(--glass-border)]/50">
              <Suspense fallback={
                <div className="h-full flex items-center justify-center bg-[var(--glass-bg)]">
                  <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
                </div>
              }>
                <LazyGeoMap
                  cities={cities}
                  maxCount={maxCount}
                  center={center}
                  mapBackground={chart.mapBackground}
                  mapTileUrl={chart.mapTileUrl}
                />
              </Suspense>
            </div>

            {/* Top countries */}
            {countries.length > 0 && (
              <CountryGrid countries={countries} />
            )}

            {/* Users by city — collapsible list */}
            {cities.length > 0 && (
              <CityUsersList cities={cities} navigate={navigate} />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── City Users List (collapsible) ────────────────────────────────

function CityUsersList({
  cities,
  navigate,
}: {
  cities: GeoCity[]
  navigate: (path: string) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('count_desc')
  const [countryFilter, setCountryFilter] = useState('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [expandedFull, setExpandedFull] = useState<Set<string>>(new Set())

  const toggle = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const showAllUsers = useCallback((key: string) => {
    setExpandedFull((prev) => {
      const next = new Set(prev)
      next.add(key)
      return next
    })
  }, [])

  const availableCountries = useMemo(() => {
    const countrySet = new Set(cities.map((c) => c.country))
    return Array.from(countrySet).sort()
  }, [cities])

  const filtered = useMemo(() => {
    let result = cities

    // Country filter
    if (countryFilter !== 'all') {
      result = result.filter((c) => c.country === countryFilter)
    }

    // Text search
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter((c) => {
        if (c.city.toLowerCase().includes(q)) return true
        if (c.country.toLowerCase().includes(q)) return true
        return (c.users || []).some(
          (u) => (u.username || '').toLowerCase().includes(q),
        )
      })
    }

    // Sorting
    result = [...result].sort((a, b) => {
      switch (sortBy) {
        case 'count_desc': return b.count - a.count
        case 'count_asc': return a.count - b.count
        case 'users_desc': return b.unique_users - a.unique_users
        case 'users_asc': return a.unique_users - b.unique_users
        case 'city_asc': return a.city.localeCompare(b.city)
        case 'city_desc': return b.city.localeCompare(a.city)
        default: return b.count - a.count
      }
    })

    return result
  }, [cities, search, sortBy, countryFilter])

  return (
    <div>
      {/* Header + filters */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="flex items-center gap-2 mr-auto">
          <MapPin className="w-4 h-4 text-primary-400" />
          <h3 className="text-sm font-medium text-white">
            {t('analytics.geo.usersByCity')}
          </h3>
          <span className="text-xs text-muted-foreground">
            {t('analytics.geo.citiesCount', { count: filtered.length })}
          </span>
        </div>

        {/* Country filter */}
        <Select value={countryFilter} onValueChange={setCountryFilter}>
          <SelectTrigger className="h-8 w-[150px] text-xs">
            <SelectValue placeholder={t('analytics.geo.allCountries')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('analytics.geo.allCountries')}</SelectItem>
            {availableCountries.map((country) => (
              <SelectItem key={country} value={country}>{country}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="h-8 w-[170px] text-xs">
            <ArrowUpDown className="w-3.5 h-3.5 mr-1.5 shrink-0" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="count_desc">{t('analytics.geo.sort.countDesc')}</SelectItem>
            <SelectItem value="count_asc">{t('analytics.geo.sort.countAsc')}</SelectItem>
            <SelectItem value="users_desc">{t('analytics.geo.sort.usersDesc')}</SelectItem>
            <SelectItem value="users_asc">{t('analytics.geo.sort.usersAsc')}</SelectItem>
            <SelectItem value="city_asc">{t('analytics.geo.sort.cityAsc')}</SelectItem>
            <SelectItem value="city_desc">{t('analytics.geo.sort.cityDesc')}</SelectItem>
          </SelectContent>
        </Select>

        {/* Search */}
        <div className="relative w-full max-w-[240px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('analytics.geo.searchPlaceholder')}
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>

      {/* City list */}
      <div className="space-y-1">
        {filtered.map((city) => {
          const key = `${city.city}-${city.country}`
          const isOpen = expanded.has(key)
          const allUsers = city.users || []
          const hasUsers = allUsers.length > 0
          const showFull = expandedFull.has(key)
          const users = showFull ? allUsers : allUsers.slice(0, 15)
          const hasMore = allUsers.length > 15 && !showFull

          return (
            <div
              key={key}
              className="rounded-lg border border-[var(--glass-border)] overflow-hidden"
            >
              {/* City header row */}
              <button
                onClick={() => hasUsers && toggle(key)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors',
                  hasUsers
                    ? 'hover:bg-[var(--glass-bg-hover)]/30 cursor-pointer'
                    : 'cursor-default',
                  isOpen && 'bg-[var(--glass-bg-hover)]/20',
                )}
              >
                <MapPin className="w-3.5 h-3.5 text-primary-400 shrink-0" />
                <span className="text-sm font-medium text-white flex-1 truncate">
                  {city.city}, {city.country}
                </span>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-muted-foreground">
                    {t('analytics.geo.totalConnections', { count: city.count, formattedCount: city.count.toLocaleString() })}
                  </span>
                  {city.unique_users > 0 && (
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {city.unique_users} {t('analytics.geo.users').toLowerCase()}
                    </Badge>
                  )}
                  {hasUsers && (
                    <ChevronDown
                      className={cn(
                        'w-4 h-4 text-muted-foreground transition-transform duration-200',
                        isOpen && 'rotate-180',
                      )}
                    />
                  )}
                </div>
              </button>

              {/* Expanded user rows */}
              {isOpen && hasUsers && (
                <div className="border-t border-[var(--glass-border)]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">{t('analytics.geo.userColumn')}</TableHead>
                        <TableHead className="text-xs hidden sm:table-cell">{t('analytics.topUsers.status')}</TableHead>
                        <TableHead className="text-xs text-right">{t('analytics.geo.connectionsColumn')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((user: GeoCityUser) => (
                        <TableRow
                          key={user.uuid}
                          className="cursor-pointer hover:bg-[var(--glass-bg-hover)]/30"
                          onClick={() => navigate(`/users/${user.uuid}`)}
                        >
                          <TableCell>
                            <div className="flex flex-col gap-0.5">
                              <div className="flex items-center gap-1.5">
                                <Users className="w-3 h-3 shrink-0 text-muted-foreground" />
                                <span className="font-medium text-sm text-white truncate max-w-[200px]">
                                  {user.username || user.uuid.slice(0, 8)}
                                </span>
                                <ArrowUpRight className="w-3 h-3 text-muted-foreground shrink-0" />
                              </div>
                              {user.ips && user.ips.length > 0 && (
                                <span className="text-[10px] font-mono text-muted-foreground pl-[18px] truncate max-w-[280px]" title={user.ips.join(', ')}>
                                  {user.ips.join(', ')}
                                </span>
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
                          <TableCell className="text-right font-mono text-sm">
                            {user.connections.toLocaleString()}
                          </TableCell>
                        </TableRow>
                      ))}
                      {hasMore && (
                        <TableRow>
                          <TableCell colSpan={3} className="text-center">
                            <button
                              onClick={(e) => { e.stopPropagation(); showAllUsers(key) }}
                              className="text-[11px] text-primary-400 hover:text-primary-300 transition-colors"
                            >
                              {t('analytics.geo.showAll', { count: allUsers.length })}
                            </button>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Country Grid (B3 fix — totalConns via useMemo) ──────────────

function CountryGrid({ countries }: { countries: { country: string; country_code: string; count: number }[] }) {
  const totalConns = useMemo(() => countries.reduce((s, x) => s + x.count, 0), [countries])
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
      {countries.slice(0, 10).map((c) => {
        const pct = totalConns > 0 ? ((c.count / totalConns) * 100).toFixed(1) : '0'
        return (
          <div
            key={c.country_code}
            className="flex items-center gap-2 p-2 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]"
          >
            <span className="text-lg leading-none">
              {countryFlag(c.country_code)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-white truncate">{c.country}</p>
              <p className="text-xs text-muted-foreground">
                {c.count.toLocaleString()} ({pct}%)
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Convert 2-letter country code to flag emoji */
function countryFlag(code: string): string {
  if (!code || code.length !== 2) return '\u{1F310}'
  const offset = 0x1f1e6
  const a = code.charCodeAt(0) - 65
  const b = code.charCodeAt(1) - 65
  if (a < 0 || a > 25 || b < 0 || b > 25) return '\u{1F310}'
  return String.fromCodePoint(offset + a, offset + b)
}

// ── Top Users Card ──────────────────────────────────────────────

function TopUsersCard() {
  const { t } = useTranslation()
  const { formatBytes } = useFormatters()
  const navigate = useNavigate()
  const [limit, setLimit] = useState(20)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const hasCustomDates = Boolean(dateFrom && dateTo)
  const apiDateFrom = hasCustomDates ? new Date(dateFrom).toISOString() : undefined
  const apiDateTo = hasCustomDates ? new Date(dateTo + 'T23:59:59').toISOString() : undefined

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-top-users', limit, dateFrom, dateTo],
    queryFn: () => advancedAnalyticsApi.topUsers(limit, apiDateFrom, apiDateTo),
    staleTime: 30_000,
    refetchInterval: hasCustomDates ? undefined : 60_000,
  })

  const items = data?.items || []

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('analytics.topUsers.title')}</CardTitle>
              <InfoTooltip
                text={t('analytics.topUsers.tooltip')}
                side="right"
              />
            </div>
            <div className="flex items-center gap-2">
              <ExportDropdown
                disabled={items.length === 0}
                onExportCSV={() => exportCSV(items.map((u) => ({
                  username: u.username, status: u.status,
                  traffic: formatBytesForExport(u.used_traffic_bytes),
                  limit: formatBytesForExport(u.traffic_limit_bytes),
                  usage_percent: u.usage_percent ?? '',
                })), 'top-users')}
                onExportJSON={() => exportJSON(items, 'top-users')}
              />
              <PeriodSwitcher
                value={String(limit)}
                onChange={(v) => setLimit(Number(v))}
                options={[
                  { value: '10', label: t('analytics.topUsers.top10') },
                  { value: '20', label: t('analytics.topUsers.top20') },
                  { value: '50', label: t('analytics.topUsers.top50') },
                ]}
              />
            </div>
          </div>
          <DateRangePicker
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={(f, t2) => { setDateFrom(f); setDateTo(t2) }}
            onClear={() => { setDateFrom(''); setDateTo('') }}
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : items.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Users className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('analytics.topUsers.noData')}</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>{t('analytics.topUsers.user')}</TableHead>
                  <TableHead className="hidden sm:table-cell">{t('analytics.topUsers.status')}</TableHead>
                  <TableHead className="text-right">{t('analytics.topUsers.traffic')}</TableHead>
                  <TableHead className="text-right hidden md:table-cell">{t('analytics.topUsers.limit')}</TableHead>
                  <TableHead className="text-right hidden lg:table-cell">{t('analytics.topUsers.usage')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((user: TopUser, idx: number) => (
                  <TableRow
                    key={user.uuid}
                    className="cursor-pointer hover:bg-[var(--glass-bg-hover)]/30"
                    onClick={() => navigate(`/users/${user.uuid}`)}
                  >
                    <TableCell className="font-mono text-muted-foreground text-xs">
                      {idx + 1}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <OnlineIndicator onlineAt={user.online_at} />
                        <span className="font-medium text-white text-sm truncate max-w-[200px]">
                          {user.username || user.uuid.slice(0, 8)}
                        </span>
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
                    <TableCell className="text-right font-mono text-sm">
                      {formatBytes(user.used_traffic_bytes)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm hidden md:table-cell text-muted-foreground">
                      {user.traffic_limit_bytes
                        ? formatBytes(user.traffic_limit_bytes)
                        : '\u221E'}
                    </TableCell>
                    <TableCell className="text-right hidden lg:table-cell">
                      {user.usage_percent != null ? (
                        <UsageBar percent={user.usage_percent} />
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function OnlineIndicator({ onlineAt }: { onlineAt: string | null }) {
  if (!onlineAt) return <WifiOff className="w-3.5 h-3.5 text-dark-300 shrink-0" />

  const lastSeen = new Date(onlineAt).getTime()
  const now = Date.now()
  const diffMin = (now - lastSeen) / 60000

  if (diffMin < 5) {
    return <Wifi className="w-3.5 h-3.5 text-green-400 shrink-0" />
  }
  return <WifiOff className="w-3.5 h-3.5 text-dark-300 shrink-0" />
}

const UsageBar = memo(function UsageBar({ percent }: { percent: number }) {
  const color =
    percent >= 90 ? 'bg-red-500' : percent >= 70 ? 'bg-yellow-500' : 'bg-primary'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${Math.min(100, percent)}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-10 text-right">
        {percent.toFixed(0)}%
      </span>
    </div>
  )
})

// ── Trends Card ─────────────────────────────────────────────────

function TrendsCard() {
  const { t } = useTranslation()
  const { formatBytes } = useFormatters()
  const [metric, setMetric] = useState('users')
  const [period, setPeriod] = useState('30d')
  const [compare, setCompare] = useState(false)
  const [trendDateFrom, setTrendDateFrom] = useState('')
  const [trendDateTo, setTrendDateTo] = useState('')
  const chart = useChartTheme()

  const hasCustomDates = Boolean(trendDateFrom)
  const apiDateFrom = hasCustomDates ? new Date(trendDateFrom).toISOString() : undefined
  const apiDateTo = hasCustomDates && trendDateTo ? new Date(trendDateTo + 'T23:59:59').toISOString() : undefined

  // B1 fix: for traffic, use the real timeseries API (daily consumption)
  const isTraffic = metric === 'traffic'
  const tsPeriod = period === '90d' ? '30d' : period

  // Previous period for comparison
  const prevPeriodMap: Record<string, string> = { '7d': '7d', '30d': '30d', '90d': '90d' }
  const prevPeriod = prevPeriodMap[period] || '30d'

  const { data: trendsData, isLoading: trendsLoading, isError: trendsError, refetch: trendsRefetch } = useQuery({
    queryKey: ['advanced-trends', metric, period, trendDateFrom, trendDateTo],
    queryFn: () => advancedAnalyticsApi.trends(metric, period, apiDateFrom, apiDateTo),
    staleTime: 60_000,
    refetchInterval: 60_000,
    enabled: !isTraffic,
  })

  const { data: tsData, isLoading: tsLoading, isError: tsError, refetch: tsRefetch } = useQuery({
    queryKey: ['timeseries', tsPeriod, 'traffic'],
    queryFn: () => advancedAnalyticsApi.timeseries(tsPeriod, 'traffic'),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: isTraffic,
  })

  // F5: comparison — fetch previous period
  const { data: prevTrendsData } = useQuery({
    queryKey: ['advanced-trends', metric, prevPeriod, 'prev'],
    queryFn: () => advancedAnalyticsApi.trends(metric, prevPeriod),
    staleTime: 60_000,
    enabled: compare && !isTraffic,
  })

  const isLoading = isTraffic ? tsLoading : trendsLoading
  const isError = isTraffic ? tsError : trendsError
  const refetch = isTraffic ? tsRefetch : trendsRefetch

  // Normalize data from both APIs into same chartData format
  const { chartData, growth } = useMemo(() => {
    if (isTraffic) {
      const points = tsData?.points || []
      const mapped = points.map((p) => ({
        date: formatDate(p.timestamp.split('T')[0]),
        value: p.value,
      }))
      const totalGrowth = points.reduce((s, p) => s + p.value, 0)
      return { chartData: mapped, growth: totalGrowth }
    }
    const series = trendsData?.series || []
    const prevSeries = compare ? (prevTrendsData?.series || []) : []

    const mapped = series.map((p, i) => ({
      date: formatDate(p.date),
      value: p.value,
      prevValue: prevSeries[i]?.value ?? undefined,
    }))
    return { chartData: mapped, growth: trendsData?.total_growth || 0 }
  }, [isTraffic, tsData, trendsData, compare, prevTrendsData])

  const formatBytesShort = (bytes: number): string => {
    if (bytes <= 0) return '0'
    const k = 1024
    const sizes = ['B', 'K', 'M', 'G', 'T']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    if (i < 0 || i >= sizes.length) return '0'
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + sizes[i]
  }

  const periodLabel = period === '7d'
    ? t('analytics.trends.last7d')
    : period === '30d'
      ? t('analytics.trends.last30d')
      : t('analytics.trends.last90d')

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.trends.title')}</CardTitle>
            <InfoTooltip
              text={t('analytics.trends.tooltip')}
              side="right"
            />
          </div>
          <div className="flex items-center gap-2">
            {!isTraffic && !hasCustomDates && (
              <Button
                variant={compare ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={() => setCompare((v) => !v)}
              >
                <GitCompare className="w-3 h-3" />
                {t('analytics.trends.compare', { defaultValue: 'Compare' })}
              </Button>
            )}
            <PeriodSwitcher
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'users', label: t('analytics.trends.users') },
                { value: 'violations', label: t('analytics.trends.violations') },
                { value: 'traffic', label: t('analytics.trends.traffic') },
              ]}
            />
            {!hasCustomDates && (
              <PeriodSwitcher
                value={period}
                onChange={setPeriod}
                options={[
                  { value: '7d', label: t('analytics.periods.7d') },
                  { value: '30d', label: t('analytics.periods.30d') },
                  { value: '90d', label: t('analytics.periods.90d') },
                  { value: 'all', label: t('analytics.periods.all') },
                ]}
              />
            )}
            <DateRangePicker
              dateFrom={trendDateFrom}
              dateTo={trendDateTo}
              onChange={(from, to) => { setTrendDateFrom(from); setTrendDateTo(to) }}
              onClear={() => { setTrendDateFrom(''); setTrendDateTo('') }}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Growth summary */}
        <div className="flex items-center gap-3 mb-4 p-3 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
          <ArrowUpRight className={cn('w-5 h-5 shrink-0', growth >= 0 ? 'text-green-400' : 'text-red-400 rotate-90')} />
          <div>
            <p className="text-sm font-medium text-white">
              {t(`analytics.trends.metric.${metric}`)}: {growth >= 0 ? '+' : ''}
              {metric === 'traffic' ? formatBytes(Math.abs(growth)) : growth.toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground">
              {periodLabel}
            </p>
          </div>
        </div>

        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : chartData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-muted-foreground">
            {t('analytics.trends.noData')}
          </div>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chart.accentColor} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chart.accentColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={chart.grid}
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: chart.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: chart.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={50}
                  tickFormatter={(v: number) =>
                    metric === 'traffic' ? formatBytesShort(v) : v.toLocaleString()
                  }
                />
                <RechartsTooltip
                  content={<TrendTooltip metric={metric} />}
                  cursor={{ stroke: `${chart.accentColor}4D` }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={chart.accentColor}
                  strokeWidth={2}
                  fill="url(#trendGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: chart.accentColor }}
                />
                {compare && !isTraffic && (
                  <Area
                    type="monotone"
                    dataKey="prevValue"
                    stroke={chart.accentColor}
                    strokeWidth={1.5}
                    strokeDasharray="5 5"
                    strokeOpacity={0.5}
                    fill="none"
                    dot={false}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Shared HWIDs Card ───────────────────────────────────────────

type HwidFilter = 'all' | 'has_trial' | 'has_expired' | 'has_active'

function SharedHwidsCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [expandedHwid, setExpandedHwid] = useState<string | null>(null)
  const [filter, setFilter] = useState<HwidFilter>('all')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-shared-hwids'],
    queryFn: () => advancedAnalyticsApi.sharedHwids(),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const items: SharedHwidGroup[] = data?.items || []

  const filtered = useMemo(() => {
    let result = items
    // Apply filter
    if (filter === 'has_trial') {
      result = result.filter((g) => g.users.some((u) => u.is_trial))
    } else if (filter === 'has_expired') {
      result = result.filter((g) => g.users.some((u) => !u.is_active && u.expire_date))
    } else if (filter === 'has_active') {
      result = result.filter((g) => g.users.some((u) => u.is_active))
    }
    // Apply search
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (g) =>
          g.hwid.toLowerCase().includes(q) ||
          g.users.some((u) => u.username?.toLowerCase().includes(q))
      )
    }
    return result
  }, [items, search, filter])

  const truncHwid = (hwid: string) =>
    hwid.length > 16 ? hwid.slice(0, 8) + '...' + hwid.slice(-4) : hwid

  const copyHwid = (hwid: string) => {
    navigator.clipboard.writeText(hwid)
    toast.success(t('common.copied', { defaultValue: 'Copied' }))
  }

  const { formatDateShort: formatDate } = useFormatters()

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Fingerprint className="w-5 h-5 text-red-400" />
            <CardTitle className="text-base">{t('analytics.sharedHwids.title')}</CardTitle>
            <InfoTooltip text={t('analytics.sharedHwids.tooltip')} side="right" />
            {items.length > 0 && (
              <Badge variant="secondary" className="text-xs bg-red-500/20 text-red-300">
                {items.length}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1 flex-wrap">
            <ExportDropdown
              disabled={filtered.length === 0}
              onExportCSV={() => exportCSV(filtered.flatMap((g) =>
                g.users.map((u) => ({
                  hwid: g.hwid, platform: g.platform ?? '', device: g.device_model ?? '',
                  username: u.username, status: u.status, is_trial: u.is_trial, is_active: u.is_active,
                }))
              ), 'shared-hwids')}
              onExportJSON={() => exportJSON(filtered, 'shared-hwids')}
            />
            {(['all', 'has_trial', 'has_active', 'has_expired'] as HwidFilter[]).map((f) => (
              <Button
                key={f}
                variant={filter === f ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => setFilter(f)}
              >
                {t(`analytics.sharedHwids.filter.${f}`, {
                  defaultValue: f === 'all' ? 'All' : f === 'has_trial' ? 'Trial' : f === 'has_active' ? 'Active' : 'Expired',
                })}
              </Button>
            ))}
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('analytics.sharedHwids.searchPlaceholder')}
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
              <p>{t('analytics.sharedHwids.noData')}</p>
              <p className="text-xs mt-1">{t('analytics.sharedHwids.noDataHint')}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((group) => {
              const isOpen = expandedHwid === group.hwid
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

                    <div className="ml-auto flex items-center gap-1.5">
                      {group.users.some((u) => u.is_trial) && (
                        <Badge className="bg-yellow-500/20 text-yellow-300 text-[10px]">trial</Badge>
                      )}
                      <Badge className="bg-red-500/20 text-red-300 text-xs">
                        {group.user_count} {t('analytics.sharedHwids.accounts')}
                      </Badge>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="ml-8 mb-2 border border-[var(--glass-border)] rounded-lg overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t('analytics.topUsers.user')}</TableHead>
                            <TableHead className="text-xs hidden sm:table-cell">{t('analytics.topUsers.status')}</TableHead>
                            <TableHead className="text-xs hidden sm:table-cell">{t('analytics.sharedHwids.subscription', 'Подписка')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('analytics.sharedHwids.createdAt')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('analytics.sharedHwids.firstSeen')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {group.users.map((user) => (
                            <TableRow
                              key={user.uuid}
                              className="cursor-pointer hover:bg-[var(--glass-bg-hover)]/30"
                              onClick={() => navigate(`/users/${user.uuid}`)}
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
                                      ? t('analytics.sharedHwids.active', 'Активна')
                                      : t('analytics.sharedHwids.expired', 'Истекла')}
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

// ── Providers Card (F2) ──────────────────────────────────────────

const PIE_COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

function ProvidersCard() {
  const { t } = useTranslation()
  const chart = useChartTheme()
  const [period, setPeriod] = useState('7d')
  const [activeFlag, setActiveFlag] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-providers', period],
    queryFn: () => advancedAnalyticsApi.providers(period),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const { data: flagAsnData, isLoading: flagAsnLoading } = useQuery({
    queryKey: ['advanced-providers-flag-asn', activeFlag, period],
    queryFn: () => advancedAnalyticsApi.providersFlagAsn(activeFlag!, period),
    enabled: !!activeFlag,
    staleTime: 60_000,
  })

  const connectionTypes = data?.connection_types || []
  const topAsn = data?.top_asn || []
  const flags = data?.flags

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Network className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.providers.title', { defaultValue: 'Providers & ASN' })}</CardTitle>
            <InfoTooltip text={t('analytics.providers.tooltip', { defaultValue: 'Connection types, ASN distribution, and security flags' })} side="right" />
          </div>
          <div className="flex items-center gap-2">
            <ExportDropdown
              disabled={!data}
              onExportCSV={async () => {
                const full = await advancedAnalyticsApi.providersAsnAll(period)
                exportCSV([
                  ...connectionTypes.map((ct) => ({ type: 'connection_type', name: ct.type, count: ct.count, percent: ct.percent })),
                  ...full.asn_list.map((a) => ({ type: 'asn', name: `AS${a.asn} ${a.org}`, count: a.count, percent: a.percent })),
                ], 'providers')
              }}
              onExportJSON={async () => {
                const full = await advancedAnalyticsApi.providersAsnAll(period)
                exportJSON({ ...data, all_asn: full.asn_list }, 'providers')
              }}
            />
            <PeriodSwitcher
              value={period}
              onChange={setPeriod}
              options={[
                { value: '24h', label: t('analytics.periods.24h') },
                { value: '7d', label: t('analytics.periods.7d') },
                { value: '30d', label: t('analytics.periods.30d') },
                { value: 'all', label: t('analytics.periods.all') },
              ]}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : (
          <div className="space-y-6">
            {/* Flags: VPN / Proxy / Tor / Hosting pills */}
            {flags && (
              <div className="flex flex-wrap gap-2">
                {([
                  { key: 'vpn', label: 'VPN', icon: Shield, color: 'text-blue-400 bg-blue-500/20', activeColor: 'text-blue-300 bg-blue-500/40 ring-1 ring-blue-400/50' },
                  { key: 'proxy', label: 'Proxy', icon: Shield, color: 'text-yellow-400 bg-yellow-500/20', activeColor: 'text-yellow-300 bg-yellow-500/40 ring-1 ring-yellow-400/50' },
                  { key: 'tor', label: 'Tor', icon: Shield, color: 'text-purple-400 bg-purple-500/20', activeColor: 'text-purple-300 bg-purple-500/40 ring-1 ring-purple-400/50' },
                  { key: 'hosting', label: 'Hosting', icon: Server, color: 'text-orange-400 bg-orange-500/20', activeColor: 'text-orange-300 bg-orange-500/40 ring-1 ring-orange-400/50' },
                ] as const).map((f) => {
                  const d = flags[f.key]
                  const isActive = activeFlag === f.key
                  return (
                    <button
                      key={f.key}
                      onClick={() => setActiveFlag(isActive ? null : f.key)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--glass-border)] transition-all cursor-pointer',
                        isActive ? f.activeColor : f.color,
                        d.count === 0 && 'opacity-50',
                      )}
                      disabled={d.count === 0}
                    >
                      <f.icon className="w-3.5 h-3.5" />
                      <span className="text-xs font-medium">{f.label}</span>
                      <span className="text-sm font-bold">{d.percent}%</span>
                      <span className="text-xs opacity-60">({d.count})</span>
                    </button>
                  )
                })}
              </div>

            )}

            {/* Flag ASN breakdown */}
            {activeFlag && (
              <div className="bg-[var(--glass-bg)]/50 rounded-lg p-4 border border-[var(--glass-border)]/30">
                <h3 className="text-sm font-medium text-white mb-3">
                  ASN — {activeFlag.toUpperCase()} ({flagAsnData?.total ?? '...'})
                </h3>
                {flagAsnLoading ? (
                  <Skeleton className="h-32 w-full" />
                ) : flagAsnData?.asn_list?.length ? (
                  <div className="space-y-1.5 max-h-64 overflow-y-auto">
                    {flagAsnData.asn_list.map((asn) => (
                      <div key={asn.asn} className="flex items-center gap-2 text-xs">
                        <span className="text-muted-foreground w-16 shrink-0">AS{asn.asn}</span>
                        <span className="text-white flex-1 truncate">{asn.org}</span>
                        <span className="text-muted-foreground">{asn.count.toLocaleString()}</span>
                        <span className="text-muted-foreground w-12 text-right">{asn.percent}%</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">{t('common.noData', { defaultValue: 'No data' })}</p>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Connection Type Donut */}
              {connectionTypes.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-white mb-3">{t('analytics.providers.connectionTypes', { defaultValue: 'Connection Types' })}</h3>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={connectionTypes}
                          dataKey="count"
                          nameKey="type"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
                          paddingAngle={2}
                        >
                          {connectionTypes.map((_entry, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip
                          contentStyle={chart.tooltipStyle}
                          formatter={(value, name) => [`${Number(value).toLocaleString()} (${connectionTypes.find((c) => c.type === name)?.percent ?? 0}%)`, t(`analytics.providers.connectionType.${String(name)}`, { defaultValue: String(name) })]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2 justify-center">
                    {connectionTypes.map((ct, i) => (
                      <div key={ct.type} className="flex items-center gap-1.5 text-xs">
                        <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-muted-foreground">{t(`analytics.providers.connectionType.${ct.type}`, { defaultValue: ct.type })}</span>
                        <span className="text-white font-medium">{ct.percent}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top ASN Bar Chart */}
              {topAsn.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-white mb-3">{t('analytics.providers.topAsn', { defaultValue: 'Top ASN' })}</h3>
                  <div className="space-y-2">
                    {topAsn.map((asn, i) => {
                      const maxCount = topAsn[0]?.count || 1
                      return (
                        <div key={asn.asn} className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground w-16 truncate shrink-0" title={`AS${asn.asn}`}>
                            AS{asn.asn}
                          </span>
                          <div className="flex-1 h-5 bg-[var(--glass-bg-hover)] rounded overflow-hidden">
                            <div
                              className="h-full rounded transition-all"
                              style={{
                                width: `${(asn.count / maxCount) * 100}%`,
                                backgroundColor: PIE_COLORS[i % PIE_COLORS.length],
                              }}
                            />
                          </div>
                          <span className="text-xs text-white w-24 truncate text-right" title={asn.org}>
                            {asn.org}
                          </span>
                          <span className="text-xs text-muted-foreground w-10 text-right">{asn.percent}%</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Nodes Card (F1) ──────────────────────────────────────────────

type NodeSortField = 'name' | 'cpu' | 'ram' | 'disk' | 'users' | 'traffic' | 'speed'

function NodesTrafficCard() {
  const { t } = useTranslation()
  const { formatBytes } = useFormatters()

  // Default to last 7 days
  const today = new Date()
  const weekAgo = new Date(today)
  weekAgo.setDate(weekAgo.getDate() - 7)
  const [dateFrom, setDateFrom] = useState(weekAgo.toISOString().slice(0, 10))
  const [dateTo, setDateTo] = useState(today.toISOString().slice(0, 10))

  const apiDateFrom = new Date(dateFrom).toISOString()
  const apiDateTo = new Date(dateTo + 'T23:59:59').toISOString()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['nodes-traffic', dateFrom, dateTo],
    queryFn: () => advancedAnalyticsApi.nodesTraffic(apiDateFrom, apiDateTo),
    staleTime: 60_000,
    enabled: Boolean(dateFrom && dateTo),
  })

  const items = data?.items || []
  const totalBytes = data?.total_bytes || 0

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('analytics.nodesTraffic.title', { defaultValue: 'Traffic by Nodes' })}</CardTitle>
            </div>
            {totalBytes > 0 && (
              <Badge variant="secondary" className="text-xs font-mono">
                {formatBytes(totalBytes)}
              </Badge>
            )}
          </div>
          <DateRangePicker
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={(f, t2) => { setDateFrom(f); setDateTo(t2) }}
            onClear={() => {
              const now = new Date()
              const wa = new Date(now); wa.setDate(wa.getDate() - 7)
              setDateFrom(wa.toISOString().slice(0, 10))
              setDateTo(now.toISOString().slice(0, 10))
            }}
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : items.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Server className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('analytics.nodesTraffic.noData', { defaultValue: 'No traffic data for this period' })}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((node) => (
              <div
                key={node.uuid}
                className="bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)] space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white font-medium truncate">{node.name}</span>
                  <div className="flex items-center gap-3 ml-3 shrink-0">
                    <span className="text-xs text-muted-foreground font-mono">{node.percent}%</span>
                    <span className="text-sm text-white font-mono w-24 text-right">{formatBytes(node.traffic_bytes)}</span>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-dark-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500/70 rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(node.percent, 1)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}


function NodesCard() {
  const { t } = useTranslation()
  const { formatBytes, formatSpeed } = useFormatters()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canViewFleet = hasPermission('fleet', 'view')
  const [sortField, setSortField] = useState<NodeSortField>('traffic')
  const [sortAsc, setSortAsc] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['node-fleet-analytics'],
    queryFn: () => advancedAnalyticsApi.nodeFleet(),
    staleTime: 30_000,
    refetchInterval: 30_000,
    enabled: canViewFleet,
  })

  const nodes: NodeFleetItem[] = data?.nodes || []
  const totalNodes = data?.total || 0
  const onlineNodes = data?.online || 0
  const offlineNodes = totalNodes - onlineNodes

  const avgCpu = useMemo(() => {
    const vals = nodes.filter((n) => n.cpu_usage != null && n.is_connected).map((n) => n.cpu_usage!)
    return vals.length > 0 ? Math.round(vals.reduce((s, v) => s + v, 0) / vals.length) : 0
  }, [nodes])

  const avgRam = useMemo(() => {
    const vals = nodes.filter((n) => n.memory_usage != null && n.is_connected).map((n) => n.memory_usage!)
    return vals.length > 0 ? Math.round(vals.reduce((s, v) => s + v, 0) / vals.length) : 0
  }, [nodes])

  const sorted = useMemo(() => {
    const arr = [...nodes]
    arr.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name': cmp = a.name.localeCompare(b.name); break
        case 'cpu': cmp = (a.cpu_usage ?? 0) - (b.cpu_usage ?? 0); break
        case 'ram': cmp = (a.memory_usage ?? 0) - (b.memory_usage ?? 0); break
        case 'disk': cmp = (a.disk_usage ?? 0) - (b.disk_usage ?? 0); break
        case 'users': cmp = a.users_online - b.users_online; break
        case 'traffic': cmp = a.traffic_today_bytes - b.traffic_today_bytes; break
        case 'speed': cmp = (a.download_speed_bps + a.upload_speed_bps) - (b.download_speed_bps + b.upload_speed_bps); break
      }
      return sortAsc ? cmp : -cmp
    })
    return arr
  }, [nodes, sortField, sortAsc])

  const toggleSort = (field: NodeSortField) => {
    if (sortField === field) setSortAsc((prev) => !prev)
    else { setSortField(field); setSortAsc(false) }
  }

  const SortHeader = ({ field, children }: { field: NodeSortField; children: React.ReactNode }) => (
    <TableHead
      className="text-xs cursor-pointer select-none hover:text-white transition-colors"
      onClick={() => toggleSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        {sortField === field && (
          <ChevronDown className={cn('w-3 h-3', sortAsc && 'rotate-180')} />
        )}
      </div>
    </TableHead>
  )

  const formatUptime = (seconds: number | null): string => {
    if (!seconds) return '-'
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    if (d > 0) return `${d}d ${h}h`
    const m = Math.floor((seconds % 3600) / 60)
    return `${h}h ${m}m`
  }

  if (!canViewFleet) return null

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.nodes.title', { defaultValue: 'Nodes' })}</CardTitle>
            <InfoTooltip text={t('analytics.nodes.tooltip', { defaultValue: 'Node fleet health and performance' })} side="right" />
          </div>
          <ExportDropdown
            disabled={nodes.length === 0}
            onExportCSV={() => exportCSV(nodes.map((n) => ({
              name: n.name, status: n.is_connected ? 'online' : n.is_disabled ? 'disabled' : 'offline',
              cpu: n.cpu_usage != null ? `${n.cpu_usage}%` : '', ram: n.memory_usage != null ? `${n.memory_usage}%` : '',
              users_online: n.users_online, traffic_today: formatBytesForExport(n.traffic_today_bytes),
              uptime: formatUptime(n.uptime_seconds),
            })), 'nodes-analytics')}
            onExportJSON={() => exportJSON(nodes, 'nodes-analytics')}
          />
        </div>
      </CardHeader>
      <CardContent>
        {/* Stat pills */}
        <div className="flex flex-wrap gap-2 mb-4">
          {[
            { label: t('analytics.nodes.total', { defaultValue: 'Total' }), value: totalNodes, icon: Server },
            { label: t('analytics.nodes.online', { defaultValue: 'Online' }), value: onlineNodes, icon: Wifi, color: 'text-green-400' },
            { label: t('analytics.nodes.offline', { defaultValue: 'Offline' }), value: offlineNodes, icon: WifiOff, color: 'text-red-400' },
            { label: t('analytics.nodes.avgCpu', { defaultValue: 'Avg CPU' }), value: `${avgCpu}%`, icon: Cpu, color: avgCpu > 80 ? 'text-red-400' : 'text-primary-400' },
            { label: t('analytics.nodes.avgRam', { defaultValue: 'Avg RAM' }), value: `${avgRam}%`, icon: Activity, color: avgRam > 80 ? 'text-red-400' : 'text-primary-400' },
          ].map((stat) => (
            <div
              key={stat.label}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]"
            >
              <stat.icon className={cn('w-3.5 h-3.5', stat.color || 'text-muted-foreground')} />
              <span className="text-xs text-muted-foreground">{stat.label}:</span>
              <span className="text-sm font-medium text-white">{stat.value}</span>
            </div>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : nodes.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Server className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('analytics.nodes.noData', { defaultValue: 'No nodes found' })}</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader field="name">{t('analytics.nodes.name', { defaultValue: 'Node' })}</SortHeader>
                  <TableHead className="text-xs">{t('analytics.topUsers.status')}</TableHead>
                  <SortHeader field="cpu">CPU</SortHeader>
                  <SortHeader field="ram">RAM</SortHeader>
                  <SortHeader field="disk">{t('analytics.nodes.disk', { defaultValue: 'Disk' })}</SortHeader>
                  <SortHeader field="users">{t('analytics.nodes.users', { defaultValue: 'Users' })}</SortHeader>
                  <SortHeader field="traffic">{t('analytics.nodes.traffic', { defaultValue: 'Traffic' })}</SortHeader>
                  <SortHeader field="speed">{t('analytics.nodes.speed', { defaultValue: 'Speed' })}</SortHeader>
                  <TableHead className="text-xs hidden lg:table-cell">Uptime</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((node) => (
                  <TableRow
                    key={node.uuid}
                    className="hover:bg-[var(--glass-bg-hover)]/30"
                  >
                    <TableCell className="font-medium text-white text-sm max-w-[160px] truncate">
                      {node.name}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn('text-xs',
                          node.is_disabled ? 'bg-gray-500/20 text-gray-400' :
                          node.is_connected ? 'bg-green-500/20 text-green-400' :
                          'bg-red-500/20 text-red-400'
                        )}
                      >
                        {node.is_disabled ? t('analytics.nodes.disabled', { defaultValue: 'Disabled' }) :
                         node.is_connected ? t('analytics.nodes.online', { defaultValue: 'Online' }) :
                         t('analytics.nodes.offline', { defaultValue: 'Offline' })}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {node.cpu_usage != null ? (
                        <ResourceBar value={node.cpu_usage} />
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell>
                      {node.memory_usage != null ? (
                        <ResourceBar value={node.memory_usage} />
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell>
                      {node.disk_usage != null ? (
                        <ResourceBar value={node.disk_usage} />
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell className="font-mono text-sm text-center">
                      {node.users_online}
                    </TableCell>
                    <TableCell className="font-mono text-sm text-right">
                      {formatBytes(node.traffic_today_bytes)}
                    </TableCell>
                    <TableCell className="text-xs text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <span className="text-green-400">{formatSpeed(node.download_speed_bps)}</span>
                        <span className="text-blue-400">{formatSpeed(node.upload_speed_bps)}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground hidden lg:table-cell">
                      {formatUptime(node.uptime_seconds)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const ResourceBar = memo(function ResourceBar({ value }: { value: number }) {
  const color = value >= 90 ? 'bg-red-500' : value >= 70 ? 'bg-yellow-500' : 'bg-primary'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-12 h-1.5 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${Math.min(100, value)}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-8 text-right">{value}%</span>
    </div>
  )
})

// ── Node Metrics History Card ───────────────────────────────────

const METRIC_COLORS = { cpu: '#ef4444', memory: '#f59e0b', disk: '#3b82f6' }

function NodeMetricsHistoryCard() {
  const { t } = useTranslation()
  const chart = useChartTheme()
  const [period, setPeriod] = useState('24h')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['node-metrics-history', period],
    queryFn: () => advancedAnalyticsApi.nodeMetricsHistory(period),
    staleTime: 60_000,
    refetchInterval: 60_000,
  })

  const nodes: NodeMetricsHistoryItem[] = Array.isArray(data?.nodes) ? data!.nodes : []
  const timeseries: NodeMetricsTimeseriesPoint[] = Array.isArray(data?.timeseries) ? data!.timeseries : []
  // Build chart data: each point has timestamp + per-node cpu/memory/disk
  const chartData = useMemo(() => {
    if (!timeseries.length) return []
    // Aggregate across all nodes for overview chart (avg of all nodes per bucket)
    return timeseries.map((point) => {
      const vals = Object.values(point.nodes)
      const cpuVals = vals.map((v) => v.cpu).filter((v): v is number => v !== null)
      const memVals = vals.map((v) => v.memory).filter((v): v is number => v !== null)
      const diskVals = vals.map((v) => v.disk).filter((v): v is number => v !== null)
      const ts = point.timestamp
      const label = period === '30d'
        ? ts.slice(5, 10)
        : period === '7d'
          ? `${ts.slice(5, 10)} ${ts.slice(11, 13)}h`
          : ts.slice(11, 16)
      return {
        time: label,
        cpu: cpuVals.length ? Math.round(cpuVals.reduce((a, b) => a + b, 0) / cpuVals.length * 10) / 10 : null,
        memory: memVals.length ? Math.round(memVals.reduce((a, b) => a + b, 0) / memVals.length * 10) / 10 : null,
        disk: diskVals.length ? Math.round(diskVals.reduce((a, b) => a + b, 0) / diskVals.length * 10) / 10 : null,
      }
    })
  }, [timeseries, period])

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.nodes.history.title', { defaultValue: 'Metrics History' })}</CardTitle>
            <InfoTooltip text={t('analytics.nodes.history.tooltip', { defaultValue: 'Average node metrics over the selected period' })} side="right" />
          </div>
          <div className="flex items-center gap-2">
            <ExportDropdown
              disabled={!nodes.length}
              onExportCSV={() => exportCSV(nodes.map((n) => ({
                node: n.node_name, avg_cpu: n.avg_cpu, avg_memory: n.avg_memory, avg_disk: n.avg_disk,
                max_cpu: n.max_cpu, max_memory: n.max_memory, max_disk: n.max_disk, samples: n.samples_count,
              })), 'node-metrics-history')}
              onExportJSON={() => exportJSON(data, 'node-metrics-history')}
            />
            <PeriodSwitcher
              value={period}
              onChange={setPeriod}
              options={[
                { value: '24h', label: t('analytics.periods.24h') },
                { value: '7d', label: t('analytics.periods.7d') },
                { value: '30d', label: t('analytics.periods.30d') },
                { value: 'all', label: t('analytics.periods.all') },
              ]}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : !nodes.length ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            <p>{t('analytics.nodes.history.noData', { defaultValue: 'No historical data yet' })}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Overview chart */}
            {chartData.length > 1 && (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                    <XAxis dataKey="time" stroke={chart.axis} fontSize={10} tickLine={false} />
                    <YAxis
                      stroke={chart.axis}
                      fontSize={10}
                      tickLine={false}
                      axisLine={false}
                      domain={[0, 100]}
                      tickFormatter={(v: number) => `${v}%`}
                    />
                    <RechartsTooltip
                      contentStyle={chart.tooltipStyle}
                      formatter={(value) => [`${value}%`]}
                    />
                    <Line type="monotone" dataKey="cpu" name="CPU" stroke={METRIC_COLORS.cpu} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="memory" name="RAM" stroke={METRIC_COLORS.memory} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="disk" name="Disk" stroke={METRIC_COLORS.disk} strokeWidth={2} dot={false} />
                    <Legend
                      verticalAlign="top"
                      height={28}
                      formatter={(value: string) => <span className="text-xs text-muted-foreground">{value}</span>}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Per-node table */}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">{t('analytics.nodes.name', { defaultValue: 'Node' })}</TableHead>
                    <TableHead className="text-xs text-center">{t('analytics.nodes.history.avgCpu', { defaultValue: 'Avg CPU' })}</TableHead>
                    <TableHead className="text-xs text-center">{t('analytics.nodes.history.avgRam', { defaultValue: 'Avg RAM' })}</TableHead>
                    <TableHead className="text-xs text-center">{t('analytics.nodes.history.avgDisk', { defaultValue: 'Avg Disk' })}</TableHead>
                    <TableHead className="text-xs text-center hidden md:table-cell">{t('analytics.nodes.history.maxCpu', { defaultValue: 'Max CPU' })}</TableHead>
                    <TableHead className="text-xs text-center hidden md:table-cell">{t('analytics.nodes.history.maxRam', { defaultValue: 'Max RAM' })}</TableHead>
                    <TableHead className="text-xs text-center hidden md:table-cell">{t('analytics.nodes.history.maxDisk', { defaultValue: 'Max Disk' })}</TableHead>
                    <TableHead className="text-xs text-right hidden lg:table-cell">{t('analytics.nodes.history.samples', { defaultValue: 'Samples' })}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {nodes.map((node) => (
                    <TableRow key={node.node_uuid}>
                      <TableCell className="text-xs font-medium">{node.node_name || node.node_uuid.slice(0, 8)}</TableCell>
                      <TableCell className="text-center">{node.avg_cpu != null ? <ResourceBar value={node.avg_cpu} /> : '-'}</TableCell>
                      <TableCell className="text-center">{node.avg_memory != null ? <ResourceBar value={node.avg_memory} /> : '-'}</TableCell>
                      <TableCell className="text-center">{node.avg_disk != null ? <ResourceBar value={node.avg_disk} /> : '-'}</TableCell>
                      <TableCell className="text-xs text-center hidden md:table-cell text-muted-foreground">{node.max_cpu != null ? `${node.max_cpu}%` : '-'}</TableCell>
                      <TableCell className="text-xs text-center hidden md:table-cell text-muted-foreground">{node.max_memory != null ? `${node.max_memory}%` : '-'}</TableCell>
                      <TableCell className="text-xs text-center hidden md:table-cell text-muted-foreground">{node.max_disk != null ? `${node.max_disk}%` : '-'}</TableCell>
                      <TableCell className="text-xs text-right hidden lg:table-cell text-muted-foreground">{node.samples_count.toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Retention Card (F6) ─────────────────────────────────────────

function retentionColor(pct: number): string {
  if (pct >= 80) return 'bg-green-500/30 text-green-300'
  if (pct >= 60) return 'bg-green-500/20 text-green-400'
  if (pct >= 40) return 'bg-yellow-500/20 text-yellow-400'
  if (pct >= 20) return 'bg-orange-500/20 text-orange-400'
  return 'bg-red-500/20 text-red-400'
}

function RetentionCard() {
  const { t } = useTranslation()
  const [weeks, setWeeks] = useState('12')
  const weeksNum = parseInt(weeks, 10) || 12

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-retention', weeksNum],
    queryFn: () => advancedAnalyticsApi.retention(weeksNum),
    refetchInterval: 60_000,
  })

  const cohorts: RetentionCohort[] = Array.isArray(data?.cohorts) ? data!.cohorts : []
  const overallRetention = data?.overall_retention ?? 0
  const totalRegistered = data?.total_registered ?? 0
  const totalRetained = data?.total_retained ?? 0

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <CalendarDays className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">
              {t('analytics.retention.title', { defaultValue: 'Retention Analysis' })}
            </CardTitle>
            <InfoTooltip
              text={t('analytics.retention.tooltip')}
              side="right"
            />
          </div>
          <div className="flex items-center gap-2">
            <ExportDropdown
              disabled={cohorts.length === 0}
              onExportCSV={() => exportCSV(cohorts.map((c) => ({
                week: c.week,
                total_users: c.total_users,
                active_users: c.active_users,
                retention_pct: `${c.retention_percent}%`,
                with_traffic_pct: `${c.with_traffic_percent}%`,
                with_active_sub_pct: `${c.with_active_sub_percent}%`,
              })), 'retention-cohorts')}
              onExportJSON={() => exportJSON(data, 'retention-cohorts')}
            />
            <Select value={weeks} onValueChange={setWeeks}>
              <SelectTrigger className="w-[100px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="12">12 {t('analytics.retention.weeks', { defaultValue: 'weeks' })}</SelectItem>
                <SelectItem value="24">24 {t('analytics.retention.weeks', { defaultValue: 'weeks' })}</SelectItem>
                <SelectItem value="52">52 {t('analytics.retention.weeks', { defaultValue: 'weeks' })}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Summary stats */}
        <div className="flex flex-wrap gap-3 mb-4">
          {[
            {
              label: t('analytics.retention.overallRetention', { defaultValue: 'Overall Retention' }),
              value: `${overallRetention}%`,
              color: overallRetention >= 50 ? 'text-green-400' : overallRetention >= 30 ? 'text-yellow-400' : 'text-red-400',
            },
            {
              label: t('analytics.retention.totalRegistered', { defaultValue: 'Registered' }),
              value: totalRegistered.toLocaleString(),
              color: 'text-white',
            },
            {
              label: t('analytics.retention.totalRetained', { defaultValue: 'Retained' }),
              value: totalRetained.toLocaleString(),
              color: 'text-primary-400',
            },
          ].map((stat) => (
            <div
              key={stat.label}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]"
            >
              <span className="text-xs text-muted-foreground">{stat.label}:</span>
              <span className={cn('text-sm font-medium', stat.color)}>{stat.value}</span>
            </div>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : cohorts.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <CalendarDays className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p>{t('analytics.retention.noData', { defaultValue: 'No cohort data available' })}</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">
                    {t('analytics.retention.week', { defaultValue: 'Week' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.weekSub')}</span>
                  </TableHead>
                  <TableHead className="text-xs text-right">
                    {t('analytics.retention.total', { defaultValue: 'Total' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.totalSub')}</span>
                  </TableHead>
                  <TableHead className="text-xs text-right">
                    {t('analytics.retention.active', { defaultValue: 'Active' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.activeSub')}</span>
                  </TableHead>
                  <TableHead className="text-xs text-center">
                    {t('analytics.retention.retentionPct', { defaultValue: 'Retention' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.retentionPctSub')}</span>
                  </TableHead>
                  <TableHead className="text-xs text-center">
                    {t('analytics.retention.trafficPct', { defaultValue: 'With Traffic' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.trafficPctSub')}</span>
                  </TableHead>
                  <TableHead className="text-xs text-center">
                    {t('analytics.retention.subPct', { defaultValue: 'Active Sub' })}
                    <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.retention.subPctSub')}</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cohorts.map((cohort) => (
                  <TableRow key={cohort.week}>
                    <TableCell className="text-sm font-mono text-white">{cohort.week}</TableCell>
                    <TableCell className="text-sm text-right">{cohort.total_users}</TableCell>
                    <TableCell className="text-sm text-right">{cohort.active_users}</TableCell>
                    <TableCell className="text-center">
                      <span className={cn('inline-block px-2 py-0.5 rounded text-xs font-medium', retentionColor(cohort.retention_percent))}>
                        {cohort.retention_percent}%
                      </span>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className={cn('inline-block px-2 py-0.5 rounded text-xs font-medium', retentionColor(cohort.with_traffic_percent))}>
                        {cohort.with_traffic_percent}%
                      </span>
                    </TableCell>
                    <TableCell className="text-center">
                      <span className={cn('inline-block px-2 py-0.5 rounded text-xs font-medium', retentionColor(cohort.with_active_sub_percent))}>
                        {cohort.with_active_sub_percent}%
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Churn Rate ──────────────────────────────────────────────────

function ChurnCard() {
  const { t } = useTranslation()
  const chartTheme = useChartTheme()
  const [period, setPeriod] = useState('month')
  const [months, setMonths] = useState('6')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-churn', period, months],
    queryFn: () => advancedAnalyticsApi.churn(period, parseInt(months, 10)),
    refetchInterval: 120_000,
  })

  const series = Array.isArray(data?.series) ? data!.series : []
  const avgChurn = data?.avg_churn ?? 0

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-red-400" />
            <CardTitle className="text-base">
              {t('analytics.churn.title', { defaultValue: 'Churn Rate' })}
            </CardTitle>
            <InfoTooltip
              text={t('analytics.churn.tooltip')}
              side="right"
            />
          </div>
          <div className="flex items-center gap-2">
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="w-[100px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="week">{t('analytics.churn.weekly', { defaultValue: 'Weekly' })}</SelectItem>
                <SelectItem value="month">{t('analytics.churn.monthly', { defaultValue: 'Monthly' })}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={months} onValueChange={setMonths}>
              <SelectTrigger className="w-[90px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="3">3 {t('analytics.churn.months', { defaultValue: 'mo' })}</SelectItem>
                <SelectItem value="6">6 {t('analytics.churn.months', { defaultValue: 'mo' })}</SelectItem>
                <SelectItem value="12">12 {t('analytics.churn.months', { defaultValue: 'mo' })}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Average churn badge */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.churn.avgChurn', { defaultValue: 'Avg Churn' })}:</span>
            <span className={cn('text-sm font-medium', avgChurn <= 10 ? 'text-green-400' : avgChurn <= 25 ? 'text-yellow-400' : 'text-red-400')}>
              {avgChurn}%
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.churn.periods', { defaultValue: 'Periods' })}:</span>
            <span className="text-sm font-medium text-white">{series.length}</span>
          </div>
        </div>

        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : series.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground">
            <p>{t('analytics.churn.noData', { defaultValue: 'No churn data' })}</p>
          </div>
        ) : (
          <>
            {/* Chart */}
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} />
                <XAxis dataKey="period" tick={{ fill: chartTheme.tick, fontSize: 11 }} />
                <YAxis tick={{ fill: chartTheme.tick, fontSize: 11 }} />
                <RechartsTooltip contentStyle={chartTheme.tooltipStyle} />
                <Area type="monotone" dataKey="active_users" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.15} name="Active" />
                <Area type="monotone" dataKey="churned_users" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} name="Churned" />
                <Area type="monotone" dataKey="new_users" stroke="#10b981" fill="#10b981" fillOpacity={0.1} name="New" />
                <Legend />
              </AreaChart>
            </ResponsiveContainer>

            {/* Table */}
            <div className="overflow-x-auto mt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">
                      {t('analytics.churn.period', { defaultValue: 'Period' })}
                    </TableHead>
                    <TableHead className="text-xs text-right">
                      Active
                      <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.churn.activeSub')}</span>
                    </TableHead>
                    <TableHead className="text-xs text-right">
                      New
                      <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.churn.newSub')}</span>
                    </TableHead>
                    <TableHead className="text-xs text-right">
                      Churned
                      <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.churn.churnedSub')}</span>
                    </TableHead>
                    <TableHead className="text-xs text-center">
                      Churn %
                      <span className="block text-[10px] text-muted-foreground font-normal">{t('analytics.churn.churnPctSub')}</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {series.map((row) => (
                    <TableRow key={row.period}>
                      <TableCell className="text-sm font-mono text-white">{row.period}</TableCell>
                      <TableCell className="text-sm text-right">{row.active_users.toLocaleString()}</TableCell>
                      <TableCell className="text-sm text-right text-green-400">+{row.new_users.toLocaleString()}</TableCell>
                      <TableCell className="text-sm text-right text-red-400">{row.churned_users > 0 ? `-${row.churned_users.toLocaleString()}` : '0'}</TableCell>
                      <TableCell className="text-center">
                        <span className={cn('inline-block px-2 py-0.5 rounded text-xs font-medium',
                          row.churn_rate <= 10 ? 'bg-green-500/20 text-green-400' :
                          row.churn_rate <= 25 ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-red-500/20 text-red-400'
                        )}>
                          {row.churn_rate}%
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ── LTV Estimate ────────────────────────────────────────────────

function LtvCard() {
  const { t } = useTranslation()

  const { data, isLoading } = useQuery({
    queryKey: ['advanced-ltv'],
    queryFn: () => advancedAnalyticsApi.ltv(),
    refetchInterval: 300_000,
  })

  const avgDays = data?.avg_lifetime_days ?? 0
  const ltv = data?.estimated_ltv ?? 0
  const sampleSize = data?.sample_size ?? 0

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-primary-400" />
          <CardTitle className="text-base">
            {t('analytics.ltv.title', { defaultValue: 'User Lifetime Value' })}
          </CardTitle>
          <InfoTooltip
            text={t('analytics.ltv.tooltip')}
            side="right"
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex flex-col items-center gap-1 p-4 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
              <span className="text-2xl font-bold text-white">{avgDays.toFixed(0)}</span>
              <span className="text-xs text-muted-foreground text-center">
                {t('analytics.ltv.avgLifetime', { defaultValue: 'Avg Lifetime (days)' })}
              </span>
              <span className="text-[10px] text-muted-foreground">{t('analytics.ltv.avgLifetimeSub')}</span>
            </div>
            <div className="flex flex-col items-center gap-1 p-4 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
              <span className="text-2xl font-bold text-primary-400">${ltv.toFixed(2)}</span>
              <span className="text-xs text-muted-foreground text-center">
                {t('analytics.ltv.estimatedLtv', { defaultValue: 'Estimated LTV' })}
              </span>
              <span className="text-[10px] text-muted-foreground">{t('analytics.ltv.estimatedLtvSub')}</span>
            </div>
            <div className="flex flex-col items-center gap-1 p-4 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
              <span className="text-2xl font-bold text-white">{sampleSize.toLocaleString()}</span>
              <span className="text-xs text-muted-foreground text-center">
                {t('analytics.ltv.sampleSize', { defaultValue: 'Sample Size' })}
              </span>
              <span className="text-[10px] text-muted-foreground">{t('analytics.ltv.sampleSizeSub')}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}


// ── Geo-Balance ─────────────────────────────────────────────────

function GeoBalanceCard() {
  const { t } = useTranslation()
  const [days, setDays] = useState('7')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['advanced-geo-balance', days],
    queryFn: () => advancedAnalyticsApi.geoBalance(Number(days)),
    staleTime: 60_000,
  })

  const nodes: GeoBalanceNode[] = Array.isArray(data?.nodes) ? data!.nodes : []
  const recommendations: GeoBalanceRecommendation[] = Array.isArray(data?.recommendations) ? data!.recommendations : []
  const regions = Array.isArray(data?.regions) ? data!.regions : []
  const overloadedCount = data?.overloaded_count ?? 0
  const medianOnline = data?.median_users_online ?? 0

  return (
    <Card className="animate-fade-in-up">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">
              {t('analytics.geoBalance.title', { defaultValue: 'Geo-Balancing' })}
            </CardTitle>
            <InfoTooltip
              text={t('analytics.geoBalance.tooltip', { defaultValue: 'Node load distribution analysis: detects overloaded nodes (CPU>80%, RAM>85%, Disk>90%) and shows user distribution by country per node. Recommendations help optimize infrastructure.' })}
              side="right"
            />
          </div>
          <div className="flex items-center gap-2">
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-[90px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">24h</SelectItem>
                <SelectItem value="7">7d</SelectItem>
                <SelectItem value="30">30d</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Summary */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.geoBalance.totalNodes', { defaultValue: 'Nodes' })}:</span>
            <span className="text-sm font-medium text-white">{nodes.length}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.geoBalance.overloaded', { defaultValue: 'Overloaded' })}:</span>
            <span className={cn('text-sm font-medium', overloadedCount > 0 ? 'text-red-400' : 'text-green-400')}>{overloadedCount}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.geoBalance.medianOnline', { defaultValue: 'Median Online' })}:</span>
            <span className="text-sm font-medium text-white">{medianOnline}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
            <span className="text-xs text-muted-foreground">{t('analytics.geoBalance.regions', { defaultValue: 'Countries' })}:</span>
            <span className="text-sm font-medium text-white">{regions.length}</span>
          </div>
        </div>

        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : (
          <>
            {/* Recommendations */}
            {recommendations.length > 0 && (
              <div className="space-y-2 mb-4">
                <h4 className="text-sm font-medium text-white">{t('analytics.geoBalance.recommendations', { defaultValue: 'Recommendations' })}</h4>
                {recommendations.map((rec, i) => (
                  <div key={i} className={cn(
                    'px-3 py-2 rounded-lg border text-sm',
                    rec.severity === 'critical' ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
                  )}>
                    {rec.message}
                  </div>
                ))}
              </div>
            )}

            {/* Nodes table */}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">{t('analytics.geoBalance.node', { defaultValue: 'Node' })}</TableHead>
                    <TableHead className="text-xs text-center">CPU</TableHead>
                    <TableHead className="text-xs text-center">RAM</TableHead>
                    <TableHead className="text-xs text-center">Disk</TableHead>
                    <TableHead className="text-xs text-right">{t('analytics.geoBalance.online', { defaultValue: 'Online' })}</TableHead>
                    <TableHead className="text-xs hidden sm:table-cell">{t('analytics.geoBalance.topCountries', { defaultValue: 'Top Countries' })}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {nodes.filter(n => n.is_connected && !n.is_disabled).map((node) => (
                    <TableRow key={node.uuid} className={node.is_overloaded ? 'bg-red-500/5' : ''}>
                      <TableCell className="text-sm font-medium text-white">
                        {node.name}
                        {node.is_overloaded && <span className="ml-1 text-red-400 text-xs">!</span>}
                      </TableCell>
                      <TableCell className="text-center">
                        <span className={cn('text-xs font-mono',
                          node.cpu_usage > 90 ? 'text-red-400' : node.cpu_usage > 70 ? 'text-yellow-400' : 'text-green-400'
                        )}>{node.cpu_usage}%</span>
                      </TableCell>
                      <TableCell className="text-center">
                        <span className={cn('text-xs font-mono',
                          node.memory_usage > 90 ? 'text-red-400' : node.memory_usage > 70 ? 'text-yellow-400' : 'text-green-400'
                        )}>{node.memory_usage}%</span>
                      </TableCell>
                      <TableCell className="text-center">
                        <span className={cn('text-xs font-mono',
                          node.disk_usage > 90 ? 'text-red-400' : node.disk_usage > 70 ? 'text-yellow-400' : 'text-green-400'
                        )}>{node.disk_usage}%</span>
                      </TableCell>
                      <TableCell className="text-sm text-right">{node.users_online}</TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <div className="flex flex-wrap gap-1">
                          {node.top_countries.slice(0, 3).map((c) => (
                            <span key={c.country_code} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--glass-bg-hover)]/50 text-muted-foreground">
                              {c.country_code} ({c.user_count})
                            </span>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Top regions */}
            {regions.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-white mb-2">{t('analytics.geoBalance.topRegions', { defaultValue: 'Top Regions by Users' })}</h4>
                <div className="flex flex-wrap gap-2">
                  {regions.slice(0, 15).map((r) => (
                    <span key={r.country_code} className="text-xs px-2 py-1 rounded-lg bg-[var(--glass-bg-hover)]/30 border border-[var(--glass-border)]">
                      {r.country_name} <span className="font-medium text-white">{r.user_count.toLocaleString()}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ── Torrent / P2P Analytics ──────────────────────────────────────

function TorrentAnalyticsCard() {
  const { t } = useTranslation()
  const chart = useChartTheme()
  const [days, setDays] = useState('7')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['torrent-stats', days],
    queryFn: () => advancedAnalyticsApi.torrentStats(Number(days)),
    staleTime: 60_000,
  })

  const summary = data?.summary ?? { total_events: 0, unique_users: 0, unique_destinations: 0, affected_nodes: 0 }
  const timeseries = Array.isArray(data?.timeseries) ? data!.timeseries : []
  const topUsers = Array.isArray(data?.top_users) ? data!.top_users : []
  const topDest = Array.isArray(data?.top_destinations) ? data!.top_destinations : []
  const topNodes = Array.isArray(data?.top_nodes) ? data!.top_nodes : []

  const chartData = useMemo(
    () => timeseries.map((p) => ({ date: p.date?.slice(5, 10) ?? '', events: p.events, users: p.users })),
    [timeseries],
  )

  return (
    <Card className="animate-fade-in-up">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-400" />
            <CardTitle className="text-base">{t('analytics.torrent.title', { defaultValue: 'P2P / Torrent Activity' })}</CardTitle>
          </div>
          <PeriodSwitcher
            value={days}
            onChange={setDays}
            options={[
              { value: '7', label: '7d' },
              { value: '30', label: '30d' },
              { value: '90', label: '90d' },
              { value: '3650', label: t('analytics.periods.all') },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : !summary.total_events ? (
          <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
            <p>{t('analytics.torrent.noData', { defaultValue: 'No torrent events detected' })}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary badges */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: t('analytics.torrent.totalEvents', { defaultValue: 'Events' }), value: summary.total_events, color: 'text-red-400' },
                ...(summary.reports_last_24h != null ? [{ label: t('analytics.torrent.last24h', { defaultValue: 'Last 24h' }), value: summary.reports_last_24h, color: 'text-red-300' }] : []),
                { label: t('analytics.torrent.uniqueUsers', { defaultValue: 'Users' }), value: summary.unique_users, color: 'text-orange-400' },
                { label: t('analytics.torrent.affectedNodes', { defaultValue: 'Nodes' }), value: summary.affected_nodes, color: 'text-blue-400' },
              ].map((s) => (
                <div key={s.label} className="bg-[var(--glass-bg)] rounded-lg p-3 text-center">
                  <p className={cn('text-xl font-bold', s.color)}>{s.value.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>

            {/* Timeline chart */}
            {chartData.length > 1 && (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
                    <XAxis dataKey="date" stroke={chart.axis} fontSize={10} tickLine={false} />
                    <YAxis stroke={chart.axis} fontSize={10} tickLine={false} axisLine={false} />
                    <RechartsTooltip contentStyle={chart.tooltipStyle} />
                    <Area type="monotone" dataKey="events" name={t('analytics.torrent.events', { defaultValue: 'Events' })} stroke="#ef4444" fill="#ef444420" strokeWidth={2} />
                    <Area type="monotone" dataKey="users" name={t('analytics.torrent.users', { defaultValue: 'Users' })} stroke="#f97316" fill="#f9731620" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Top destinations + Top users side by side */}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Top destinations */}
              {topDest.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">
                    {t('analytics.torrent.topDestinations', { defaultValue: 'Top Trackers' })}
                  </h4>
                  <div className="space-y-1.5 max-h-60 overflow-y-auto">
                    {topDest.map((d, i) => (
                      <div key={i} className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5 text-xs">
                        <span className="text-white/80 truncate max-w-[200px]" title={d.destination}>{d.destination}</span>
                        <div className="flex gap-3 text-muted-foreground shrink-0">
                          <span>{d.events} evt</span>
                          <span>{d.users} usr</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top users */}
              {topUsers.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">
                    {t('analytics.torrent.topUsers', { defaultValue: 'Top Violators' })}
                  </h4>
                  <div className="space-y-1.5 max-h-60 overflow-y-auto">
                    {topUsers.map((u, i) => (
                      <div key={i} className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5 text-xs">
                        <span className="text-white/80 font-mono truncate max-w-[200px]">{u.username || (u.user_uuid ? `${u.user_uuid.slice(0, 8)}...` : '?')}</span>
                        <Badge variant="destructive" className="text-[10px]">{u.event_count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Top nodes */}
              {topNodes.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">
                    {t('analytics.torrent.topNodes', { defaultValue: 'Top Nodes' })}
                  </h4>
                  <div className="space-y-1.5 max-h-60 overflow-y-auto">
                    {topNodes.map((n, i) => (
                      <div key={i} className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5 text-xs">
                        <span className="text-white/80 truncate max-w-[200px]">{n.country_code && <span className="mr-1">{n.country_code}</span>}{n.name}</span>
                        <Badge variant="secondary" className="text-[10px]">{n.total}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Main Page ───────────────────────────────────────────────────

const VALID_TABS = ['geography', 'users', 'trends', 'shared-hwids', 'providers', 'nodes-traffic', 'nodes', 'geo-balance', 'torrent', 'retention'] as const

export default function Analytics() {
  const { t } = useTranslation()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canViewAnalytics = hasPermission('analytics', 'view')
  const [tab, setTab] = useTabParam('geography', [...VALID_TABS])

  if (!canViewAnalytics) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">{t('common.noPermission', { defaultValue: 'No permission' })}</p>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t('analytics.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('analytics.subtitle')}
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList>
          <TabsTrigger value="geography" className="gap-1.5">
            <Globe className="w-4 h-4" />
            {t('analytics.tabs.geography')}
          </TabsTrigger>
          <TabsTrigger value="users" className="gap-1.5">
            <BarChart3 className="w-4 h-4" />
            {t('analytics.tabs.topUsers')}
          </TabsTrigger>
          <TabsTrigger value="trends" className="gap-1.5">
            <TrendingUp className="w-4 h-4" />
            {t('analytics.tabs.trends')}
          </TabsTrigger>
          <TabsTrigger value="shared-hwids" className="gap-1.5">
            <Fingerprint className="w-4 h-4" />
            {t('analytics.tabs.sharedHwids')}
          </TabsTrigger>
          <TabsTrigger value="providers" className="gap-1.5">
            <Network className="w-4 h-4" />
            {t('analytics.tabs.providers', { defaultValue: 'Providers' })}
          </TabsTrigger>
          <TabsTrigger value="nodes-traffic" className="gap-1.5">
            <BarChart3 className="w-4 h-4" />
            {t('analytics.tabs.nodesTraffic', { defaultValue: 'Node Traffic' })}
          </TabsTrigger>
          <TabsTrigger value="nodes" className="gap-1.5">
            <Server className="w-4 h-4" />
            {t('analytics.tabs.nodes', { defaultValue: 'Nodes' })}
          </TabsTrigger>
          <TabsTrigger value="geo-balance" className="gap-1.5">
            <Activity className="w-4 h-4" />
            {t('analytics.tabs.geoBalance', { defaultValue: 'Geo-Balance' })}
          </TabsTrigger>
          <TabsTrigger value="torrent" className="gap-1.5">
            <Shield className="w-4 h-4" />
            {t('analytics.tabs.torrent', { defaultValue: 'P2P / Torrent' })}
          </TabsTrigger>
          <TabsTrigger value="retention" className="gap-1.5">
            <CalendarDays className="w-4 h-4" />
            {t('analytics.tabs.retention', { defaultValue: 'Retention' })}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="geography" className="space-y-6">
          <GeoMapCard />
        </TabsContent>

        <TabsContent value="users">
          <TopUsersCard />
        </TabsContent>

        <TabsContent value="trends">
          <TrendsCard />
        </TabsContent>

        <TabsContent value="shared-hwids">
          <SharedHwidsCard />
        </TabsContent>

        <TabsContent value="providers">
          <ProvidersCard />
        </TabsContent>

        <TabsContent value="nodes-traffic">
          <NodesTrafficCard />
        </TabsContent>

        <TabsContent value="nodes">
          <div className="space-y-4">
            <NodesCard />
            <NodeMetricsHistoryCard />
          </div>
        </TabsContent>

        <TabsContent value="geo-balance">
          <GeoBalanceCard />
        </TabsContent>

        <TabsContent value="torrent">
          <TorrentAnalyticsCard />
        </TabsContent>

        <TabsContent value="retention" className="space-y-4">
          <RetentionCard />
          <ChurnCard />
          <LtvCard />
        </TabsContent>
      </Tabs>
    </div>
  )
}
