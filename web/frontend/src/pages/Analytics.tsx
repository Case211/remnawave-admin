import { useState, useMemo, useCallback, memo, lazy, Suspense, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
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
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from 'recharts'
import { toast } from 'sonner'
import { advancedAnalyticsApi } from '@/api/advancedAnalytics'
import type { GeoCity, GeoCityUser, TopUser, SharedHwidGroup } from '@/api/advancedAnalytics'

// Lazy-load the map component (leaflet + react-leaflet + clustering)
const LazyGeoMap = lazy(() => import('@/components/LazyGeoMap'))
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
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
    <div className="flex items-center gap-1 bg-dark-600/50 rounded-lg p-0.5">
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

// ── Geo Map Card ────────────────────────────────────────────────

function GeoMapCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [geoPeriod, setGeoPeriod] = useState('7d')
  const chart = useChartTheme()

  const { data: geoData, isLoading } = useQuery({
    queryKey: ['advanced-geo', geoPeriod],
    queryFn: () => advancedAnalyticsApi.geo(geoPeriod),
    staleTime: 60_000,
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
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.geo.title')}</CardTitle>
            <InfoTooltip
              text={t('analytics.geo.tooltip')}
              side="right"
            />
          </div>
          <PeriodSwitcher
            value={geoPeriod}
            onChange={setGeoPeriod}
            options={[
              { value: '24h', label: t('analytics.periods.24h') },
              { value: '7d', label: t('analytics.periods.7d') },
              { value: '30d', label: t('analytics.periods.30d') },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[400px] w-full rounded-lg" />
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
            <div className="h-[400px] rounded-lg overflow-hidden border border-dark-500/50">
              <Suspense fallback={
                <div className="h-full flex items-center justify-center bg-dark-700/50">
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
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
                {countries.slice(0, 10).map((c) => {
                  const totalConns = countries.reduce((s, x) => s + x.count, 0)
                  const pct = totalConns > 0 ? ((c.count / totalConns) * 100).toFixed(1) : '0'
                  return (
                    <div
                      key={c.country_code}
                      className="flex items-center gap-2 p-2 rounded-lg bg-dark-600/30 border border-dark-500/30"
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
              className="rounded-lg border border-dark-500/30 overflow-hidden"
            >
              {/* City header row */}
              <button
                onClick={() => hasUsers && toggle(key)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors',
                  hasUsers
                    ? 'hover:bg-dark-600/30 cursor-pointer'
                    : 'cursor-default',
                  isOpen && 'bg-dark-600/20',
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
                <div className="border-t border-dark-500/30">
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
                          className="cursor-pointer hover:bg-dark-600/30"
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

  const { data, isLoading } = useQuery({
    queryKey: ['advanced-top-users', limit],
    queryFn: () => advancedAnalyticsApi.topUsers(limit),
    staleTime: 30_000,
  })

  const items = data?.items || []

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('analytics.topUsers.title')}</CardTitle>
            <InfoTooltip
              text={t('analytics.topUsers.tooltip')}
              side="right"
            />
          </div>
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
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
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
                    className="cursor-pointer hover:bg-dark-600/30"
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
      <div className="w-16 h-1.5 bg-dark-600 rounded-full overflow-hidden">
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
  const chart = useChartTheme()

  const { data, isLoading } = useQuery({
    queryKey: ['advanced-trends', metric, period],
    queryFn: () => advancedAnalyticsApi.trends(metric, period),
    staleTime: 60_000,
  })

  const series = data?.series || []
  const growth = data?.total_growth || 0

  const chartData = series.map((p) => ({
    date: formatDate(p.date),
    value: p.value,
  }))

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
            <PeriodSwitcher
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'users', label: t('analytics.trends.users') },
                { value: 'violations', label: t('analytics.trends.violations') },
                { value: 'traffic', label: t('analytics.trends.traffic') },
              ]}
            />
            <PeriodSwitcher
              value={period}
              onChange={setPeriod}
              options={[
                { value: '7d', label: t('analytics.periods.7d') },
                { value: '30d', label: t('analytics.periods.30d') },
                { value: '90d', label: t('analytics.periods.90d') },
              ]}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Growth summary */}
        <div className="flex items-center gap-3 mb-4 p-3 rounded-lg bg-dark-600/30 border border-dark-500/30">
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
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
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
                  cursor={{ stroke: 'rgba(6,182,212,0.3)' }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  fill="url(#trendGradient)"
                  dot={false}
                  activeDot={{ r: 4, fill: '#22d3ee' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Shared HWIDs Card ───────────────────────────────────────────

function SharedHwidsCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [expandedHwid, setExpandedHwid] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['advanced-shared-hwids'],
    queryFn: () => advancedAnalyticsApi.sharedHwids(),
    staleTime: 60_000,
  })

  const items: SharedHwidGroup[] = data?.items || []

  const filtered = useMemo(() => {
    if (!search.trim()) return items
    const q = search.toLowerCase()
    return items.filter(
      (g) =>
        g.hwid.toLowerCase().includes(q) ||
        g.users.some((u) => u.username?.toLowerCase().includes(q))
    )
  }, [items, search])

  const truncHwid = (hwid: string) =>
    hwid.length > 16 ? hwid.slice(0, 8) + '...' + hwid.slice(-4) : hwid

  const copyHwid = (hwid: string) => {
    navigator.clipboard.writeText(hwid)
    toast.success(t('common.copied', { defaultValue: 'Copied' }))
  }

  const formatDate = (d: string | null) => {
    if (!d) return '-'
    try {
      return new Date(d).toLocaleDateString()
    } catch {
      return d
    }
  }

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
                        : 'hover:bg-dark-600/40 border border-transparent'
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
                      <Badge className="bg-red-500/20 text-red-300 text-xs">
                        {group.user_count} {t('analytics.sharedHwids.accounts')}
                      </Badge>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="ml-8 mb-2 border border-dark-600 rounded-lg overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">{t('analytics.topUsers.user')}</TableHead>
                            <TableHead className="text-xs hidden sm:table-cell">{t('analytics.topUsers.status')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('analytics.sharedHwids.createdAt')}</TableHead>
                            <TableHead className="text-xs hidden md:table-cell">{t('analytics.sharedHwids.firstSeen')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {group.users.map((user) => (
                            <TableRow
                              key={user.uuid}
                              className="cursor-pointer hover:bg-dark-600/30"
                              onClick={() => navigate(`/users/${user.uuid}`)}
                            >
                              <TableCell>
                                <span className="font-medium text-white text-sm hover:text-primary-400 transition-colors">
                                  {user.username || user.uuid.slice(0, 8)}
                                </span>
                              </TableCell>
                              <TableCell className="hidden sm:table-cell">
                                <Badge
                                  variant="secondary"
                                  className={cn('text-xs', STATUS_COLORS[user.status] || '')}
                                >
                                  {t(`analytics.status.${user.status}`, { defaultValue: user.status })}
                                </Badge>
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

// ── Main Page ───────────────────────────────────────────────────

export default function Analytics() {
  const { t } = useTranslation()

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t('analytics.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('analytics.subtitle')}
        </p>
      </div>

      <Tabs defaultValue="geography" className="w-full">
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
      </Tabs>
    </div>
  )
}
