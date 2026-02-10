import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Globe,
  Users,
  TrendingUp,
  ArrowUpRight,
  MapPin,
  BarChart3,
  Wifi,
  WifiOff,
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
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { advancedAnalyticsApi } from '@/api/advancedAnalytics'
import type { GeoCity, TopUser } from '@/api/advancedAnalytics'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { cn } from '@/lib/utils'

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

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 Б'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const parts = dateStr.split('-')
  if (parts.length === 3) return `${parts[2]}.${parts[1]}`
  return dateStr
}

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Активен',
  DISABLED: 'Отключен',
  EXPIRED: 'Истёк',
  LIMITED: 'Лимит',
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-green-500/20 text-green-400',
  DISABLED: 'bg-red-500/20 text-red-400',
  EXPIRED: 'bg-yellow-500/20 text-yellow-400',
  LIMITED: 'bg-orange-500/20 text-orange-400',
}

// ── Chart Tooltip ───────────────────────────────────────────────

const tooltipStyle = {
  backgroundColor: 'rgba(22, 27, 34, 0.95)',
  border: '1px solid rgba(72, 79, 88, 0.3)',
  borderRadius: '8px',
  backdropFilter: 'blur(12px)',
}

function TrendTooltip({ active, payload, label, metric }: any) {
  if (!active || !payload?.length) return null
  const val = payload[0].value
  return (
    <div style={tooltipStyle} className="px-3 py-2">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-sm font-medium text-white">
        {metric === 'traffic' ? formatBytes(val) : val.toLocaleString()}
      </p>
    </div>
  )
}

// ── Geo Map Card ────────────────────────────────────────────────

function GeoMapCard() {
  const [geoPeriod, setGeoPeriod] = useState('7d')

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
    const lat = cities.reduce((s: number, c: GeoCity) => s + c.lat * c.count, 0) / totalWeight
    const lon = cities.reduce((s: number, c: GeoCity) => s + c.lon * c.count, 0) / totalWeight
    return [lat, lon] as [number, number]
  }, [cities])

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-cyan-400" />
            <CardTitle className="text-base">География подключений</CardTitle>
          </div>
          <PeriodSwitcher
            value={geoPeriod}
            onChange={setGeoPeriod}
            options={[
              { value: '24h', label: '24ч' },
              { value: '7d', label: '7д' },
              { value: '30d', label: '30д' },
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
              <p>Нет данных о географии</p>
              <p className="text-xs mt-1">Данные появятся после обработки IP-адресов</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Map */}
            <div className="h-[400px] rounded-lg overflow-hidden border border-dark-500/50">
              <MapContainer
                center={center}
                zoom={3}
                className="h-full w-full"
                style={{ background: '#0d1117' }}
                attributionControl={false}
              >
                <TileLayer
                  url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                />
                {cities.map((city: GeoCity, idx: number) => {
                  const radius = Math.max(5, Math.min(25, (city.count / maxCount) * 25))
                  return (
                    <CircleMarker
                      key={`${city.city}-${city.country}-${idx}`}
                      center={[city.lat, city.lon]}
                      radius={radius}
                      pathOptions={{
                        color: '#06b6d4',
                        fillColor: '#22d3ee',
                        fillOpacity: 0.4,
                        weight: 1,
                      }}
                    >
                      <Popup>
                        <div className="text-xs">
                          <p className="font-medium">{city.city}, {city.country}</p>
                          <p>{city.count} подключений</p>
                        </div>
                      </Popup>
                    </CircleMarker>
                  )
                })}
              </MapContainer>
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
          </div>
        )}
      </CardContent>
    </Card>
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
            <BarChart3 className="w-5 h-5 text-violet-400" />
            <CardTitle className="text-base">Топ по трафику</CardTitle>
          </div>
          <PeriodSwitcher
            value={String(limit)}
            onChange={(v) => setLimit(Number(v))}
            options={[
              { value: '10', label: 'Топ 10' },
              { value: '20', label: 'Топ 20' },
              { value: '50', label: 'Топ 50' },
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
              <p>Нет данных о трафике</p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Пользователь</TableHead>
                  <TableHead className="hidden sm:table-cell">Статус</TableHead>
                  <TableHead className="text-right">Трафик</TableHead>
                  <TableHead className="text-right hidden md:table-cell">Лимит</TableHead>
                  <TableHead className="text-right hidden lg:table-cell">Использовано</TableHead>
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
                        {STATUS_LABELS[user.status] || user.status}
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

function UsageBar({ percent }: { percent: number }) {
  const color =
    percent >= 90 ? 'bg-red-500' : percent >= 70 ? 'bg-yellow-500' : 'bg-cyan-500'
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
}

// ── Trends Card ─────────────────────────────────────────────────

function TrendsCard() {
  const [metric, setMetric] = useState('users')
  const [period, setPeriod] = useState('30d')

  const { data, isLoading } = useQuery({
    queryKey: ['advanced-trends', metric, period],
    queryFn: () => advancedAnalyticsApi.trends(metric, period),
    staleTime: 60_000,
  })

  const series = data?.series || []
  const growth = data?.total_growth || 0

  const metricLabel: Record<string, string> = {
    users: 'Новые пользователи',
    violations: 'Нарушения',
    traffic: 'Трафик',
  }

  const chartData = series.map((p) => ({
    date: formatDate(p.date),
    value: p.value,
  }))

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            <CardTitle className="text-base">Тенденции</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <PeriodSwitcher
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'users', label: 'Пользователи' },
                { value: 'violations', label: 'Нарушения' },
                { value: 'traffic', label: 'Трафик' },
              ]}
            />
            <PeriodSwitcher
              value={period}
              onChange={setPeriod}
              options={[
                { value: '7d', label: '7д' },
                { value: '30d', label: '30д' },
                { value: '90d', label: '90д' },
              ]}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Growth summary */}
        <div className="flex items-center gap-3 mb-4 p-3 rounded-lg bg-dark-600/30 border border-dark-500/30">
          <ArrowUpRight className="w-5 h-5 text-green-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-white">
              {metricLabel[metric] || metric}: +
              {metric === 'traffic' ? formatBytes(growth) : growth.toLocaleString()}
            </p>
            <p className="text-xs text-muted-foreground">
              за {period === '7d' ? '7 дней' : period === '30d' ? '30 дней' : '90 дней'}
            </p>
          </div>
        </div>

        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : chartData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-muted-foreground">
            Нет данных за выбранный период
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
                  stroke="rgba(72,79,88,0.2)"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#8b949e', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#8b949e', fontSize: 11 }}
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

function formatBytesShort(bytes: number): string {
  if (bytes <= 0) return '0'
  const k = 1024
  const sizes = ['Б', 'К', 'М', 'Г', 'Т']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + sizes[i]
}

// ── Main Page ───────────────────────────────────────────────────

export default function Analytics() {
  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Расширенная аналитика</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Географическое распределение, топ пользователей и тенденции роста
        </p>
      </div>

      {/* Geo Map */}
      <GeoMapCard />

      {/* Two-column layout for top users and trends */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <TopUsersCard />
        <TrendsCard />
      </div>
    </div>
  )
}
