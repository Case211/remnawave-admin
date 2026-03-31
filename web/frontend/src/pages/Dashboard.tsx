import { useState, useMemo, useEffect, useRef, memo, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  Server,
  ShieldAlert,
  RefreshCw,
  ExternalLink,
  Settings,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Wifi,
  Database,
  Globe,
  CreditCard,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  Tag,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  LineChart,
  Line,
  AreaChart,
  Area,
} from 'recharts'
import client from '../api/client'
import { billingApi } from '../api/billing'
import { auditApi, type AuditLogEntry } from '../api/audit'
import { usePermissionStore } from '../store/permissionStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { InfoTooltip } from '@/components/InfoTooltip'
import { cn } from '@/lib/utils'
import { useChartTheme } from '@/lib/useChartTheme'
import { useFormatters } from '@/lib/useFormatters'

// ── Types ────────────────────────────────────────────────────────

interface OverviewStats {
  total_users: number
  active_users: number
  disabled_users: number
  expired_users: number
  total_nodes: number
  online_nodes: number
  offline_nodes: number
  disabled_nodes: number
  total_hosts: number
  violations_today: number
  violations_week: number
  total_traffic_bytes: number
  users_online: number
}

// ViolationStats imported from shared types
import type { ViolationStats } from '@/types/violations'

interface TrafficStats {
  total_bytes: number
  today_bytes: number
  week_bytes: number
  month_bytes: number
}

interface TimeseriesPoint {
  timestamp: string
  value: number
}

interface NodeTimeseriesPoint {
  timestamp: string
  total: number
  nodes: Record<string, number>
}

interface TimeseriesResponse {
  period: string
  metric: string
  points: TimeseriesPoint[]
  node_points: NodeTimeseriesPoint[]
  node_names: Record<string, string>
}

interface SystemComponent {
  name: string
  status: string
  details: Record<string, any>
}

interface SystemComponentsResponse {
  components: SystemComponent[]
  uptime_seconds: number | null
  version: string
}

interface PanelRecap {
  thisMonth: { users: number; traffic: number }
  total: { users: number; nodes: number; traffic: number; nodesRam: number; nodesCpuCores: number; distinctCountries: number }
  version: string
  initDate: string | null
}

// ── API functions ────────────────────────────────────────────────

const fetchOverview = async (): Promise<OverviewStats> => {
  const { data } = await client.get('/analytics/overview')
  return data
}

const fetchViolationStats = async (): Promise<ViolationStats> => {
  const { data } = await client.get('/violations/stats')
  return data
}

const fetchTrafficStats = async (): Promise<TrafficStats> => {
  const { data } = await client.get('/analytics/traffic')
  return data
}

const fetchTimeseries = async (period: string, metric: string): Promise<TimeseriesResponse> => {
  const { data } = await client.get('/analytics/timeseries', {
    params: { period, metric },
  })
  return data
}

const fetchSystemComponents = async (): Promise<SystemComponentsResponse> => {
  const { data } = await client.get('/analytics/system/components')
  return data
}

const fetchPanelRecap = async (): Promise<PanelRecap> => {
  const { data } = await client.get('/analytics/panel/recap')
  return data
}

interface CollectorStats {
  queue: { pending_users: number; peak_queue_size: number; health: string }
  processing: {
    total_enqueued: number; total_processed: number; total_violations_found: number
    total_skipped_cooldown: number; last_drain_duration_ms: number; backlog: number
  }
  input: { total_batches_received: number; total_batches_rejected: number }
  background_tasks: { active: number; dropped: number }
  cooldown_cache_size: number
}

const fetchCollectorStats = async (): Promise<CollectorStats> => {
  const { data } = await client.get('/collector/stats')
  return data
}

interface TopUserItem {
  uuid: string
  username: string
  status: string
  used_traffic_bytes: number
  lifetime_used_traffic_bytes: number
  traffic_limit_bytes: number | null
  usage_percent: number | null
  online_at: string | null
}

interface TrendPoint {
  date: string
  value: number
}

interface TrendsResponse {
  series: TrendPoint[]
  metric: string
  period: string
  total_growth: number
}

interface TopViolatorItem {
  user_uuid: string
  username: string | null
  violations_count: number
  max_score: number
  avg_score: number
  last_violation_at: string
  actions: string[]
  top_reasons: string[]
}

const fetchTopUsers = async (limit = 5): Promise<{ items: TopUserItem[] }> => {
  const { data } = await client.get('/analytics/advanced/top-users', { params: { limit } })
  return data
}

const fetchTrends = async (metric: string, period: string): Promise<TrendsResponse> => {
  const { data } = await client.get('/analytics/advanced/trends', { params: { metric, period } })
  return data
}

const fetchTopViolators = async (days = 7, limit = 5): Promise<TopViolatorItem[]> => {
  const { data } = await client.get('/violations/top-violators', { params: { days, limit, min_score: 40 } })
  return Array.isArray(data) ? data : []
}

interface NodeFleetItem {
  uuid: string
  name: string
  is_connected: boolean
  is_disabled: boolean
  cpu_usage: number | null
  memory_usage: number | null
  users_online: number
  traffic_today_bytes: number
}

interface NodeFleetResponse {
  nodes: NodeFleetItem[]
  total: number
  online: number
}

interface TrafficAnomaly {
  nodeName: string
  nodeUuid: string
  todayBytes: number
  avgBytes: number
  deviationPercent: number
  direction: 'up' | 'down'
}

const fetchNodeFleet = async (): Promise<NodeFleetResponse> => {
  const { data } = await client.get('/analytics/node-fleet')
  return data
}

const fetchExpiringCounts = async (): Promise<{ in7d: number; in30d: number }> => {
  const [r7, r30] = await Promise.all([
    client.get('/users', { params: { expire_filter: 'expiring_7d', per_page: 1 } }),
    client.get('/users', { params: { expire_filter: 'expiring_30d', per_page: 1 } }),
  ])
  return { in7d: r7.data?.total ?? 0, in30d: r30.data?.total ?? 0 }
}

// ── Utilities ────────────────────────────────────────────────────

function createFormatBytes(t: (key: string) => string) {
  return function formatBytes(bytes: number | null | undefined): string {
    if (!bytes || bytes <= 0) return `0 ${t('common.bytes.b')}`
    const k = 1024
    const sizes = [t('common.bytes.b'), t('common.bytes.kb'), t('common.bytes.mb'), t('common.bytes.gb'), t('common.bytes.tb')]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    if (i < 0 || i >= sizes.length) return `0 ${t('common.bytes.b')}`
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }
}

function createFormatBytesShort(t: (key: string) => string) {
  return function formatBytesShort(bytes: number): string {
    if (bytes <= 0) return '0'
    const k = 1024
    const sizes = [t('common.bytes.b'), t('common.bytes.kb_short'), t('common.bytes.mb_short'), t('common.bytes.gb_short'), t('common.bytes.tb_short')]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    if (i < 0 || i >= sizes.length) return '0'
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + sizes[i]
  }
}

function createFormatUptime(t: (key: string, opts?: Record<string, unknown>) => string) {
  return function formatUptime(seconds: number | null | undefined): string {
    if (!seconds || seconds <= 0) return '-'
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d > 0) return t('dashboard.uptimeDH', { days: d, hours: h })
    if (h > 0) return t('dashboard.uptimeHM', { hours: h, minutes: m })
    return t('dashboard.uptimeM', { minutes: m })
  }
}

function formatTimestamp(ts: string): string {
  if (!ts) return ''
  // For dates like "2026-02-09", show "09.02"
  // For datetime like "2026-02-09T14:00", show "14:00"
  if (ts.includes('T')) {
    const parts = ts.split('T')
    const time = parts[1]?.substring(0, 5)
    if (time) return time
  }
  // Date format
  const parts = ts.split('-')
  if (parts.length === 3) {
    return `${parts[2]}.${parts[1]}`
  }
  return ts
}

// NODE_COLORS removed — now using chart.nodeColors from useChartTheme (theme-aware)

// ── StatCard ─────────────────────────────────────────────────────

const STAT_COLORS = {
  cyan:   { rgb: '6, 182, 212',   text: 'text-cyan-400',   hoverText: 'group-hover:text-cyan-400',   bar: '#06b6d4' },
  green:  { rgb: '34, 197, 94',   text: 'text-emerald-400', hoverText: 'group-hover:text-emerald-400', bar: '#22c55e' },
  yellow: { rgb: '234, 179, 8',   text: 'text-amber-400',  hoverText: 'group-hover:text-amber-400',  bar: '#eab308' },
  red:    { rgb: '239, 68, 68',   text: 'text-red-400',    hoverText: 'group-hover:text-red-400',    bar: '#ef4444' },
  violet: { rgb: '139, 92, 246',  text: 'text-violet-400', hoverText: 'group-hover:text-violet-400', bar: '#8b5cf6' },
  pink:   { rgb: '236, 72, 153',  text: 'text-pink-400',   hoverText: 'group-hover:text-pink-400',   bar: '#ec4899' },
} as const

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  color: keyof typeof STAT_COLORS
  subtitle?: string
  onClick?: () => void
  loading?: boolean
  index?: number
}

/** Animate a numeric value from 0 → target over ~800ms */
function useCountUp(target: string | number, loading?: boolean): string {
  const [display, setDisplay] = useState('0')
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (loading) return

    const str = String(target)
    // Extract leading numeric part (e.g. "1,234" → 1234, "3/5" → 3)
    const cleaned = str.replace(/,/g, '')
    const num = parseFloat(cleaned)
    if (!isFinite(num) || num === 0 || str === '-') {
      setDisplay(str)
      return
    }

    const isInt = Number.isInteger(num) && !cleaned.includes('.')
    const suffix = cleaned.length < str.length ? str.slice(cleaned.indexOf(String(num)) + String(num).length) : ''
    // For values like "3/5" just show immediately
    if (/[/]/.test(str)) {
      setDisplay(str)
      return
    }

    const duration = 800
    const start = performance.now()

    const tick = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = eased * num

      if (isInt) {
        setDisplay(Math.round(current).toLocaleString() + suffix)
      } else {
        setDisplay(current.toFixed(1) + suffix)
      }

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        setDisplay(str)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, loading])

  return display
}

const StatCard = memo(function StatCard({
  title, value, icon: Icon, color, subtitle, onClick, loading, index = 0,
}: StatCardProps) {
  const { t } = useTranslation()
  const cfg = STAT_COLORS[color]
  const animatedValue = useCountUp(value, loading)

  return (
    <Card
      className={cn(
        "animate-fade-in-up group relative overflow-hidden transition-all duration-300",
        onClick && "cursor-pointer hover:-translate-y-0.5"
      )}
      onClick={onClick}
      style={{
        animationDelay: `${index * 0.05}s`,
        '--stat-rgb': cfg.rgb,
      } as React.CSSProperties}
    >
      {/* Left color bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg transition-all duration-300 group-hover:w-[4px]"
        style={{
          background: `linear-gradient(180deg, ${cfg.bar} 0%, rgba(${cfg.rgb}, 0.3) 100%)`,
          boxShadow: `0 0 8px rgba(${cfg.rgb}, 0.15)`,
        }}
      />
      {/* Top glow line on hover */}
      <div
        className="absolute inset-x-0 top-0 h-px opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ background: `linear-gradient(90deg, transparent, rgba(${cfg.rgb}, 0.5), transparent)` }}
      />
      {/* Hover glow shadow */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none rounded-lg"
        style={{ boxShadow: `inset 0 0 30px -12px rgba(${cfg.rgb}, 0.1), 0 0 20px -8px rgba(${cfg.rgb}, 0.15)` }}
      />
      <CardContent className="px-4 py-3 relative">
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-muted-foreground">{title}</p>
            {loading ? (
              <Skeleton className="h-7 w-16 mt-1" />
            ) : (
              <p className="text-lg md:text-xl font-bold text-white mt-0.5">{animatedValue}</p>
            )}
            {subtitle && (
              <p className="text-[11px] text-muted-foreground mt-0.5">{subtitle}</p>
            )}
          </div>
          <div
            className="p-2 rounded-lg shrink-0 backdrop-blur-sm transition-all duration-300 group-hover:scale-110"
            style={{
              background: `rgba(${cfg.rgb}, 0.12)`,
              border: `1px solid rgba(${cfg.rgb}, 0.25)`,
            }}
          >
            <Icon className={cn("w-5 h-5 transition-colors duration-300", cfg.text)} />
          </div>
        </div>
        {onClick && (
          <span className={cn(
            "text-[11px] text-muted-foreground flex items-center gap-1 transition-colors duration-200 mt-2",
            cfg.hoverText,
          )}>
            {t('dashboard.details')} <ExternalLink className="w-3 h-3" />
          </span>
        )}
      </CardContent>
    </Card>
  )
})

// ── ChartSkeleton ────────────────────────────────────────────────

function ChartSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="h-64 flex items-center justify-center">
      <div className="flex flex-col items-center gap-2">
        <div
          className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
          style={{ borderColor: 'rgba(var(--glow-rgb), 0.8)', borderTopColor: 'transparent' }}
        />
        <span className="text-sm text-muted-foreground">{t('dashboard.loading')}</span>
      </div>
    </div>
  )
}

// ── PeriodSwitcher ───────────────────────────────────────────────

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
    <div className="flex items-center gap-1 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-lg p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-2.5 py-1 text-xs rounded-md transition-all duration-200",
            value === opt.value
              ? "bg-[var(--glass-bg-hover)] text-primary-400 font-medium border border-[var(--glass-border-hover)] shadow-[0_0_8px_-3px_rgba(var(--glow-rgb),0.2)]"
              : "text-muted-foreground hover:text-white border border-transparent"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ── Custom Chart Tooltip ─────────────────────────────────────────

interface TooltipPayloadEntry {
  name: string
  value: number
  color: string
}

function TrafficChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayloadEntry[]; label?: string }) {
  const { t } = useTranslation()
  const chart = useChartTheme()
  const formatBytesLocal = createFormatBytes(t)
  if (!active || !payload?.length) return null
  // Sort by value descending for readability; keep original color from stroke
  const sorted = [...payload].sort((a, b) => (b.value || 0) - (a.value || 0))
  return (
    <div style={chart.tooltipStyle} className="px-3 py-2">
      <p className={cn("text-xs mb-1", chart.tooltipMutedClass)}>{label}</p>
      {sorted.map((entry, i) => (
        <p key={i} className="text-xs flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
          <span style={{ color: entry.color }}>{entry.name}: {formatBytesLocal(entry.value)}</span>
        </p>
      ))}
    </div>
  )
}

// ── GrowthTrendsCard ─────────────────────────────────────────────

function GrowthTrendsCard({
  trends,
  loading,
  metric,
  onMetricChange,
}: {
  trends: TrendsResponse | undefined
  loading: boolean
  metric: string
  onMetricChange: (m: string) => void
}) {
  const { t } = useTranslation()
  const chart = useChartTheme()
  const formatBytesLocal = createFormatBytes(t)

  const metricOptions = [
    { value: 'users', label: t('dashboard.trendUsers') },
    { value: 'traffic', label: t('dashboard.trendTraffic') },
    { value: 'violations', label: t('dashboard.trendViolations') },
  ]

  const formatValue = (v: number) => {
    if (metric === 'traffic') return formatBytesLocal(v)
    return v.toLocaleString()
  }

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader className="pb-2">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base md:text-lg">{t('dashboard.growthTrends')}</CardTitle>
            <InfoTooltip text={t('dashboard.growthTrendsTooltip')} side="right" />
          </div>
          <PeriodSwitcher value={metric} onChange={onMetricChange} options={metricOptions} />
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <ChartSkeleton />
        ) : trends && trends.series.length > 0 ? (
          <>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs text-muted-foreground">{t('dashboard.totalGrowth')}:</span>
              <span className="text-sm font-semibold text-primary-400">{formatValue(trends.total_growth)}</span>
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={trends.series}>
                <defs>
                  <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chart.accentColor} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chart.accentColor} stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                <XAxis dataKey="date" stroke={chart.axis} fontSize={10} tickFormatter={(d) => { const p = d.split('-'); return `${p[2]}.${p[1]}` }} />
                <YAxis stroke={chart.axis} fontSize={10} tickFormatter={(v) => metric === 'traffic' ? createFormatBytesShort(t)(v) : v} />
                <RechartsTooltip content={(props: any) => {
                  if (!props.active || !props.payload?.length) return null
                  return (
                    <div style={chart.tooltipStyle} className="px-3 py-2">
                      <p className={cn("text-xs mb-1", chart.tooltipMutedClass)}>{props.label}</p>
                      {props.payload.map((entry: any, i: number) => (
                        <p key={i} className="text-xs" style={{ color: entry.color }}>
                          {entry.name}: {formatValue(entry.value)}
                        </p>
                      ))}
                    </div>
                  )
                }} />
                <Area type="monotone" dataKey="value" name={metricOptions.find((o) => o.value === metric)?.label || metric} stroke={chart.accentColor} fill="url(#trendGrad)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </>
        ) : (
          <div className="h-[180px] flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noData')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── TopUsersCard ─────────────────────────────────────────────────

function TopUsersCard({
  topUsers,
  loading,
}: {
  topUsers: { items: TopUserItem[] } | undefined
  loading: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const formatBytesLocal = createFormatBytes(t)
  const items = topUsers?.items || []

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base md:text-lg">{t('dashboard.topUsersByTraffic')}</CardTitle>
            <InfoTooltip text={t('dashboard.topUsersByTrafficTooltip')} side="right" />
          </div>
          <span className="text-xs text-muted-foreground">{t('dashboard.top5')}</span>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-2">
            {items.map((user, i) => (
              <div
                key={user.uuid}
                className="flex items-center gap-3 bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)] cursor-pointer hover:bg-[var(--glass-bg-hover)] transition-colors"
                onClick={() => navigate(`/users/${user.uuid}`)}
              >
                <span className="text-xs text-muted-foreground w-4 text-center font-mono">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-white truncate hover:text-primary-400 transition-colors">{user.username}</span>
                    <span className="text-xs text-primary-400 font-mono font-semibold shrink-0 ml-2">{formatBytesLocal(user.used_traffic_bytes)}</span>
                  </div>
                  {user.traffic_limit_bytes && user.usage_percent != null ? (
                    <div className="w-full h-1.5 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${Math.min(user.usage_percent, 100)}%`,
                          background: user.usage_percent >= 90 ? 'linear-gradient(90deg, #ef4444, #f87171)' : user.usage_percent >= 70 ? 'linear-gradient(90deg, #f59e0b, #fbbf24)' : 'linear-gradient(90deg, var(--accent-from), var(--accent-to))',
                        }}
                      />
                    </div>
                  ) : (
                    <div className="w-full h-1.5 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
                      <div className="h-full rounded-full w-full" style={{ background: 'linear-gradient(90deg, var(--accent-from), var(--accent-to))', opacity: 0.3 }} />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noData')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── TopViolatorsCard ────────────────────────────────────────────

function TopViolatorsCard({
  topViolators,
  loading,
}: {
  topViolators: TopViolatorItem[] | undefined
  loading: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const items = topViolators || []

  const scoreColor = (score: number) => {
    if (score >= 80) return 'text-red-400'
    if (score >= 60) return 'text-orange-400'
    if (score >= 40) return 'text-yellow-400'
    return 'text-green-400'
  }

  return (
    <Card className="animate-fade-in-up cursor-pointer hover:shadow-[0_0_24px_-6px_rgba(var(--glow-rgb),0.2)] transition-all" style={{ animationDelay: '0.2s' }} onClick={() => navigate('/violations')}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base md:text-lg">{t('dashboard.topViolators')}</CardTitle>
            <InfoTooltip text={t('dashboard.topViolatorsTooltip')} side="right" />
          </div>
          <span className="text-xs text-muted-foreground">{t('dashboard.last7days')}</span>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-2">
            {items.map((v, i) => (
              <div key={v.user_uuid} className="flex items-center gap-3 bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)]">
                <span className="text-xs text-muted-foreground w-4 text-center font-mono">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-white truncate">{v.username || v.user_uuid.substring(0, 8)}</span>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{v.violations_count}</Badge>
                      <span className={cn("text-xs font-mono font-semibold", scoreColor(v.max_score))}>{v.max_score.toFixed(0)}</span>
                    </div>
                  </div>
                  {v.top_reasons.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {v.top_reasons.slice(0, 2).map((r) => (
                        <span key={r} className="text-[9px] text-muted-foreground bg-[var(--glass-bg-hover)] rounded px-1 py-0.5">{r}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noViolators')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── CollectorQueueCard ───────────────────────────────────────────

function CollectorQueueCard({ stats, loading }: { stats?: CollectorStats; loading: boolean }) {
  const { t } = useTranslation()

  const healthColor: Record<string, string> = {
    idle: '#6b7280',
    ok: '#10b981',
    busy: '#f59e0b',
    overloaded: '#ef4444',
  }

  const healthLabel: Record<string, string> = {
    idle: 'Idle',
    ok: 'OK',
    busy: t('dashboard.collectorBusy'),
    overloaded: t('dashboard.collectorOverloaded'),
  }

  const health = stats?.queue?.health || 'idle'
  const color = healthColor[health] || '#6b7280'

  const metrics = [
    {
      label: t('dashboard.collectorPending'),
      value: stats?.queue?.pending_users ?? 0,
      highlight: (stats?.queue?.pending_users ?? 0) > 500,
    },
    {
      label: t('dashboard.collectorProcessed'),
      value: stats?.processing?.total_processed ?? 0,
    },
    {
      label: t('dashboard.collectorViolations'),
      value: stats?.processing?.total_violations_found ?? 0,
    },
    {
      label: t('dashboard.collectorSkipped'),
      value: stats?.processing?.total_skipped_cooldown ?? 0,
    },
    {
      label: t('dashboard.collectorDrainMs'),
      value: `${stats?.processing?.last_drain_duration_ms ?? 0}ms`,
    },
    {
      label: t('dashboard.collectorBatches'),
      value: stats?.input?.total_batches_received ?? 0,
    },
  ]

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.collectorQueue')}</CardTitle>
          </div>
          <Badge
            variant="secondary"
            className="text-[10px] font-mono"
            style={{ color, borderColor: color }}
          >
            {healthLabel[health] || health}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-1.5">
            {metrics.map((m) => (
              <div
                key={m.label}
                className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-2.5 py-1.5 border border-[var(--glass-border)]"
              >
                <span className="text-xs text-muted-foreground">{m.label}</span>
                <span
                  className={`text-xs font-mono ${m.highlight ? 'text-amber-400 font-bold' : 'text-white'}`}
                >
                  {typeof m.value === 'number' ? m.value.toLocaleString() : m.value}
                </span>
              </div>
            ))}
            {(stats?.input?.total_batches_rejected ?? 0) > 0 && (
              <div className="flex items-center justify-between bg-red-500/10 rounded-lg px-2.5 py-1.5 border border-red-500/30">
                <span className="text-xs text-red-400">{t('dashboard.collectorRejected')}</span>
                <span className="text-xs font-mono text-red-400 font-bold">
                  {stats!.input.total_batches_rejected.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── SystemStatusCard ─────────────────────────────────────────────

function SystemStatusCard({
  components,
  uptime,
  version,
  loading,
  panelRecap,
}: {
  components: SystemComponent[]
  uptime: number | null
  version: string
  loading: boolean
  panelRecap?: PanelRecap
}) {
  const { t } = useTranslation()
  const formatUptime = createFormatUptime(t)

  const iconMap: Record<string, React.ElementType> = {
    'Remnawave API': Globe,
    'PostgreSQL': Database,
    'Nodes': Server,
    'WebSocket': Activity,
  }

  const statusColorMap: Record<string, string> = {
    online: '#10b981',
    offline: '#ef4444',
    degraded: '#f59e0b',
    unknown: '#6b7280',
  }

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.systemStatus')}</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {uptime != null && (
              <span className="text-[10px] text-muted-foreground font-mono">{formatUptime(uptime)}</span>
            )}
            {panelRecap?.version && (
              <Badge variant="outline" className="text-[10px] font-mono">
                Panel {panelRecap.version}
              </Badge>
            )}
            {version && (
              <Badge variant="secondary" className="text-[10px] font-mono">
                v{version}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-1.5">
            {components.map((comp) => {
              const IconComp = iconMap[comp.name] || Activity
              const statusColor = statusColorMap[comp.status] || '#6b7280'

              let detail = ''
              const d = comp.details || {}
              if (comp.name === 'Remnawave API' && d.response_time_ms) {
                detail = `${d.response_time_ms}${t('dashboard.ms')}`
              } else if (comp.name === 'Nodes') {
                detail = `${d.online || 0}/${d.total || 0}`
              } else if (comp.name === 'WebSocket') {
                detail = `${d.active_connections || 0} ${t('dashboard.sessions')}`
              } else if (comp.name === 'PostgreSQL' && d.size != null) {
                detail = `pool: ${d.free_size || 0}/${d.size || 0}`
              }

              return (
                <div key={comp.name} className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-2.5 py-1.5 border border-[var(--glass-border)]">
                  <div className="flex items-center gap-2">
                    <IconComp className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-xs text-white">{comp.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {detail && (
                      <span className="text-[10px] text-muted-foreground font-mono">{detail}</span>
                    )}
                    <span
                      className={cn("w-1.5 h-1.5 rounded-full", comp.status === 'online' && "animate-pulse")}
                      style={{
                        background: statusColor,
                        boxShadow: comp.status === 'online' ? `0 0 8px ${statusColor}` : `0 0 6px ${statusColor}80`,
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {panelRecap && (panelRecap.total.distinctCountries > 0 || panelRecap.initDate) && (
          <div className="mt-2 pt-2 border-t border-[var(--glass-border)] flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
            {panelRecap.total.distinctCountries > 0 && (
              <span>{t('dashboard.countries')}: {panelRecap.total.distinctCountries}</span>
            )}
            {panelRecap.total.nodesCpuCores > 0 && (
              <span>CPU: {panelRecap.total.nodesCpuCores} {t('dashboard.cores')}</span>
            )}
            {panelRecap.initDate && (
              <span>{t('dashboard.panelSince')}: {new Date(panelRecap.initDate).toLocaleDateString()}</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── BillingSummaryCard ───────────────────────────────────────────

function BillingSummaryCard({ loading }: { loading: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { formatCurrency, formatDate } = useFormatters()

  const { data: billing, isLoading } = useQuery({
    queryKey: ['billingSummary'],
    queryFn: billingApi.getSummary,
    refetchInterval: 120000,
    staleTime: 60_000,
    retry: false,
  })

  const isCardLoading = loading || isLoading

  return (
    <Card
      className="animate-fade-in-up cursor-pointer hover:shadow-glow-teal transition-shadow"
      style={{ animationDelay: '0.35s' }}
      onClick={() => navigate('/billing')}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base md:text-lg">{t('dashboard.billing')}</CardTitle>
            <InfoTooltip text={t('dashboard.billingTooltip')} side="right" />
          </div>
          <div
            className="p-2 rounded-lg"
            style={{
              background: 'rgba(var(--glow-rgb), 0.15)',
              border: '1px solid rgba(var(--glow-rgb), 0.3)',
            }}
          >
            <CreditCard className="w-5 h-5 text-primary-400" />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isCardLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : billing ? (
          <div className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">{t('dashboard.billingMonthly')}</p>
              <p className="text-xl font-bold text-white">
                {formatCurrency(Number(billing.current_month_payments) || 0)}
              </p>
            </div>
            <Separator />
            <div className="space-y-1.5">
              <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-1.5 border border-[var(--glass-border)]">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingProviders')}</span>
                <span className="text-xs text-white font-mono">{billing.total_providers}</span>
              </div>
              <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-1.5 border border-[var(--glass-border)]">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingNodes')}</span>
                <span className="text-xs text-white font-mono">{billing.total_billing_nodes}</span>
              </div>
              <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-1.5 border border-[var(--glass-border)]">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingTotalSpent')}</span>
                <span className="text-xs text-primary-400 font-semibold font-mono">
                  {formatCurrency(Number(billing.total_spent) || 0)}
                </span>
              </div>
              {billing.next_payment_date && (
                <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-1.5 border border-[var(--glass-border)]">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <CalendarClock className="w-3 h-3" />
                    {t('dashboard.billingNextPayment')}
                  </span>
                  <span className="text-xs text-primary-400 font-mono">
                    {formatDate(billing.next_payment_date)}
                  </span>
                </div>
              )}
            </div>
            <Separator />
            <span className="text-xs text-muted-foreground group-hover:text-primary-400 flex items-center gap-1 transition-colors duration-200">
              {t('dashboard.details')} <ExternalLink className="w-3 h-3" />
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('common.noData')}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Constants ────────────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  low: '#40c057',
  medium: '#fab005',
  high: '#ff922b',
  critical: '#fa5252',
}


// ── Update Checker Card ──────────────────────────────────────────

interface UpdateInfo {
  current_version: string
  latest_version: string | null
  update_available: boolean
  release_url: string | null
  changelog: string | null
  published_at: string | null
}

interface DependencyVersions {
  python: string | null
  postgresql: string | null
  fastapi: string | null
  xray_nodes: Record<string, string>
}

interface ReleaseInfo {
  tag: string
  name: string
  changelog: string
  url: string
  published_at: string | null
}

function UpdateCheckerCard() {
  const { t } = useTranslation()
  const [expandedRelease, setExpandedRelease] = useState<string | null>(null)

  const { data: updateInfo, isLoading } = useQuery<UpdateInfo>({
    queryKey: ['updates'],
    queryFn: async () => {
      const { data } = await client.get('/analytics/updates')
      return data
    },
    staleTime: 300000, // 5 min
    retry: false,
  })

  const { data: deps } = useQuery<DependencyVersions>({
    queryKey: ['dependencies'],
    queryFn: async () => {
      const { data } = await client.get('/analytics/dependencies')
      return data
    },
    staleTime: 300000,
    retry: false,
  })

  const { data: releaseHistory } = useQuery<ReleaseInfo[]>({
    queryKey: ['release-history'],
    queryFn: async () => {
      const { data } = await client.get('/analytics/release-history')
      return Array.isArray(data) ? data : []
    },
    staleTime: 300000,
    retry: false,
    enabled: !!updateInfo?.update_available,
  })

  if (isLoading) {
    return (
      <Card className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
        <CardContent className="p-4">
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!updateInfo) return null

  const xrayNodes = deps?.xray_nodes || {}
  const xrayVersions = Object.values(xrayNodes)
  const uniqueXray = [...new Set(xrayVersions)]
  const releases = releaseHistory || []

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base md:text-lg flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary-400" />
          {t('dashboard.versionsAndUpdates')}
          <InfoTooltip
            text={t('dashboard.versionsTooltip')}
            side="right"
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Current version + update */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-dark-200">{t('dashboard.currentVersion')}</p>
            <p className="text-lg font-bold text-white">{updateInfo.current_version && updateInfo.current_version !== 'unknown' ? `v${updateInfo.current_version}` : updateInfo.current_version}</p>
          </div>
          {updateInfo.update_available && updateInfo.latest_version ? (
            <a
              href={updateInfo.release_url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex"
            >
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border gap-1 cursor-pointer hover:bg-emerald-500/30 transition-colors">
                <ArrowUpRight className="w-3 h-3" />
                {t('dashboard.versionAvailable', { version: updateInfo.latest_version })}
              </Badge>
            </a>
          ) : (
            <Badge className="bg-[var(--glass-bg-hover)] text-dark-200 border-[var(--glass-border)] border">
              {t('dashboard.upToDate')}
            </Badge>
          )}
        </div>

        {/* Release history */}
        {releases.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-dark-300">
              {t('dashboard.missedUpdates', { count: releases.length })}
            </p>
            <div className="space-y-1 max-h-64 overflow-auto">
              {releases.map((rel) => {
                const isExpanded = expandedRelease === rel.tag
                return (
                  <Fragment key={rel.tag}>
                    <button
                      type="button"
                      onClick={() => setExpandedRelease(isExpanded ? null : rel.tag)}
                      className="w-full flex items-center gap-2 bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] rounded-lg px-3 py-2 text-left transition-colors"
                    >
                      <Tag className="w-3 h-3 text-primary-400 flex-shrink-0" />
                      <span className="text-sm font-medium text-white">v{rel.tag}</span>
                      {rel.published_at && (
                        <span className="text-[11px] text-dark-400 ml-auto mr-2">
                          {new Date(rel.published_at).toLocaleDateString()}
                        </span>
                      )}
                      {isExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
                      )}
                    </button>
                    {isExpanded && (
                      <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2 ml-5 space-y-2">
                        {rel.changelog && (
                          <p className="text-xs text-dark-300 whitespace-pre-wrap break-words">
                            {rel.changelog}
                          </p>
                        )}
                        {rel.url && (
                          <a
                            href={rel.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] text-primary-400 hover:text-primary-300 transition-colors"
                          >
                            <ExternalLink className="w-3 h-3" />
                            GitHub
                          </a>
                        )}
                      </div>
                    )}
                  </Fragment>
                )
              })}
            </div>
          </div>
        )}

        {/* Single changelog fallback (when no release history loaded yet) */}
        {updateInfo.update_available && updateInfo.changelog && releases.length === 0 && (
          <div className="bg-[var(--glass-bg)] rounded-lg p-3 max-h-24 overflow-auto">
            <p className="text-xs text-dark-300 whitespace-pre-wrap line-clamp-4">
              {updateInfo.changelog.slice(0, 300)}
            </p>
          </div>
        )}

        <Separator className="bg-[var(--glass-bg-hover)]" />

        {/* Dependencies */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
          {deps?.python && (
            <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5">
              <span className="text-dark-300">Python</span>
              <span className="text-white font-mono text-xs">{deps.python}</span>
            </div>
          )}
          {deps?.postgresql && (
            <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5">
              <span className="text-dark-300">PostgreSQL</span>
              <span className="text-white font-mono text-xs">{deps.postgresql}</span>
            </div>
          )}
          {deps?.fastapi && (
            <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5">
              <span className="text-dark-300">FastAPI</span>
              <span className="text-white font-mono text-xs">{deps.fastapi}</span>
            </div>
          )}
          {uniqueXray.length > 0 && (
            <div className="flex items-center justify-between bg-[var(--glass-bg)] rounded px-3 py-1.5">
              <span className="text-dark-300">Xray</span>
              <span className="text-white font-mono text-xs">{uniqueXray.join(', ')}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}


// ── ActivityFeedCard ─────────────────────────────────────────────

/** Plurals→singular map for audit entity normalization */
const ENTITY_SINGULAR: Record<string, string> = {
  users: 'user', nodes: 'node', hosts: 'host',
  admins: 'admin', roles: 'role', violations: 'violation',
}

/** Verb aliases for descriptions lookup */
const VERB_ALIASES: Record<string, string> = {
  generate_agent_token: 'generate_token',
  revoke_agent_token: 'revoke_token',
}

/**
 * Translate dotted audit action (e.g. "users.sync_hwid") into a human-readable string.
 * Lookup chain: audit.feed.{action} → audit.descriptions.{verb}.{singular} → audit.actions.{verb} + audit.resources.{singular} → humanized raw
 */
function translateAuditAction(action: string, t: (key: string) => string): string {
  // Try direct feed translation (handles any format)
  const feedKey = `audit.feed.${action}`
  const feedResult = t(feedKey)
  if (feedResult !== feedKey) return feedResult

  const dotIdx = action.indexOf('.')
  if (dotIdx <= 0) {
    const ak = `audit.actions.${action}`
    const al = t(ak)
    return al !== ak ? al : action.replace(/_/g, ' ')
  }

  const entity = action.slice(0, dotIdx)
  const verb = action.slice(dotIdx + 1)
  const singular = ENTITY_SINGULAR[entity] || entity

  // Try audit.descriptions.{verb}.{singular}
  const descKey = `audit.descriptions.${verb}.${singular}`
  const desc = t(descKey)
  if (desc !== descKey) return desc

  // Try verb alias (generate_agent_token → generate_token)
  const aliasVerb = VERB_ALIASES[verb]
  if (aliasVerb) {
    const aliasKey = `audit.descriptions.${aliasVerb}.${singular}`
    const aliasResult = t(aliasKey)
    if (aliasResult !== aliasKey) return aliasResult
  }

  // Compose from actions + resources
  const actionLabel = t(`audit.actions.${verb}`)
  const resourceLabel = t(`audit.resources.${singular}`)
  if (actionLabel !== `audit.actions.${verb}` && resourceLabel !== `audit.resources.${singular}`) {
    return `${actionLabel}: ${resourceLabel}`
  }
  if (actionLabel !== `audit.actions.${verb}`) return actionLabel

  return verb.replace(/_/g, ' ')
}

/** Extract a short label from audit entry details JSON (username, name, setting key, etc.) */
/** Extract a concise context string from audit entry details JSON. */
function extractDetailLabel(details: string | null): string | null {
  if (!details) return null
  try {
    const d = JSON.parse(details)
    const parts: string[] = []

    // Primary identifier: username / name / remark / title
    const id = d.username || d.name || d.remark || d.title || null
    if (id) parts.push(String(id))

    // Setting key
    if (d.setting) parts.push(String(d.setting))

    // Address (nodes/hosts — if no name available)
    if (!id && d.address) parts.push(String(d.address))

    // Bulk operation count
    if (d.count != null) {
      let bulk = `×${d.count}`
      if (d.failed > 0) bulk += ` (✗${d.failed})`
      parts.push(bulk)
    }

    // Changed fields (for update actions)
    if (Array.isArray(d.fields) && d.fields.length > 0) {
      parts.push(d.fields.slice(0, 3).join(', ') + (d.fields.length > 3 ? '…' : ''))
    }

    // Status / value (if nothing else matched)
    if (parts.length === 0 && d.status) parts.push(String(d.status))
    if (parts.length === 0 && d.value != null) parts.push(String(d.value).slice(0, 30))

    return parts.length > 0 ? parts.join(' · ') : null
  } catch {
    return null
  }
}

const ActivityFeedCard = memo(function ActivityFeedCard({
  items, loading,
}: {
  items: AuditLogEntry[]
  loading: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { formatTimeAgo } = useFormatters()

  const actionIcon = (action: string) => {
    if (action.includes('create') || action.includes('template_activate')) return '+'
    if (action.includes('delete') || action.includes('remove') || action.includes('revoke')) return '×'
    if (action.includes('update') || action.includes('edit') || action.includes('toggle')) return '✎'
    if (action.includes('login')) return '→'
    if (action.includes('logout')) return '←'
    if (action.includes('enable')) return '▶'
    if (action.includes('disable')) return '■'
    if (action.includes('sync') || action.includes('restart') || action.includes('trigger')) return '↻'
    if (action.includes('resolve') || action.includes('annul')) return '✓'
    if (action.includes('generate') || action.includes('reset')) return '⟳'
    return '•'
  }

  return (
    <Card
      className="animate-fade-in-up cursor-pointer hover:shadow-[0_0_24px_-6px_rgba(var(--glow-rgb),0.2)] transition-all"
      style={{ animationDelay: '0.25s' }}
      onClick={() => navigate('/audit')}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.activityFeed')}</CardTitle>
            <InfoTooltip text={t('dashboard.activityFeedTooltip')} side="right" />
          </div>
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{t('dashboard.live')}</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-5 w-full" />)}
          </div>
        ) : items.length > 0 ? (
          <div className="space-y-0.5 max-h-[200px] overflow-auto">
            {items.map((entry) => {
              const label = translateAuditAction(entry.action, t)
              const detail = extractDetailLabel(entry.details)
              return (
                <div key={entry.id} className="flex items-center gap-2 py-1 text-xs">
                  <span className="text-muted-foreground shrink-0 w-14 text-[10px] font-mono">
                    {entry.created_at ? formatTimeAgo(entry.created_at) : ''}
                  </span>
                  <span className="text-primary-400 w-3 text-center shrink-0 font-mono">
                    {actionIcon(entry.action)}
                  </span>
                  <span className="text-muted-foreground truncate">
                    <span className="text-white">{entry.admin_username}</span>{' '}
                    {label}{detail ? <span className="opacity-60"> · {detail}</span> : null}
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="h-20 flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noActivity')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

// ── NodeLoadCard ────────────────────────────────────────────────

const NodeLoadCard = memo(function NodeLoadCard({
  nodes, loading,
}: {
  nodes: NodeFleetItem[]
  loading: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const sortedNodes = useMemo(() => {
    if (!nodes?.length) return []
    return nodes
      .filter((n) => n.is_connected && !n.is_disabled)
      .map((n) => ({
        ...n,
        load: ((n.cpu_usage ?? 0) + (n.memory_usage ?? 0)) / 2,
      }))
      .sort((a, b) => b.load - a.load)
      .slice(0, 5)
  }, [nodes])

  const loadColor = (load: number) => {
    if (load >= 90) return '#ef4444'
    if (load >= 70) return '#f59e0b'
    return 'var(--accent-from)'
  }

  return (
    <Card
      className="animate-fade-in-up cursor-pointer hover:shadow-[0_0_24px_-6px_rgba(var(--glow-rgb),0.2)] transition-all"
      style={{ animationDelay: '0.2s' }}
      onClick={() => navigate('/fleet')}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.nodeLoad')}</CardTitle>
            <InfoTooltip text={t('dashboard.nodeLoadTooltip')} side="right" />
          </div>
          <span className="text-xs text-muted-foreground">{t('dashboard.top5')}</span>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-5 w-full" />)}
          </div>
        ) : sortedNodes.length > 0 ? (
          <div className="space-y-1.5">
            {sortedNodes.map((node) => (
              <div key={node.uuid} className="flex items-center gap-2">
                <span className="text-xs text-white truncate w-24 shrink-0">{node.name}</span>
                <div className="flex-1 h-1.5 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(node.load, 100)}%`, background: loadColor(node.load) }}
                  />
                </div>
                <span className="text-xs text-muted-foreground font-mono w-10 text-right">
                  {node.load.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-20 flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noData')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

// ── ExpiryCountsCard ────────────────────────────────────────────

const ExpiryCountsCard = memo(function ExpiryCountsCard({
  counts, loading,
}: {
  counts: { in7d: number; in30d: number } | undefined
  loading: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <Card
      className="animate-fade-in-up"
      style={{ animationDelay: '0.25s' }}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.expiryTimeline')}</CardTitle>
            <InfoTooltip text={t('dashboard.expiryTimelineTooltip')} side="right" />
          </div>
          <CalendarClock className="w-4 h-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : counts ? (
          <div className="space-y-2">
            <div
              className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)] cursor-pointer hover:bg-[var(--glass-bg-hover)] transition-colors"
              onClick={() => navigate('/users?expire_filter=expiring_7d')}
            >
              <span className="text-xs text-muted-foreground">{t('dashboard.expiringIn7d')}</span>
              <Badge
                variant="secondary"
                className={cn(
                  'font-mono text-xs',
                  counts.in7d > 10 && 'bg-red-500/20 text-red-400 border-red-500/30',
                  counts.in7d > 0 && counts.in7d <= 10 && 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
                )}
              >
                {counts.in7d}
              </Badge>
            </div>
            <div
              className="flex items-center justify-between bg-[var(--glass-bg)] rounded-lg px-3 py-2 border border-[var(--glass-border)] cursor-pointer hover:bg-[var(--glass-bg-hover)] transition-colors"
              onClick={() => navigate('/users?expire_filter=expiring_30d')}
            >
              <span className="text-xs text-muted-foreground">{t('dashboard.expiringIn30d')}</span>
              <Badge variant="secondary" className="font-mono text-xs">{counts.in30d}</Badge>
            </div>
          </div>
        ) : (
          <div className="h-16 flex items-center justify-center">
            <span className="text-muted-foreground text-sm">{t('dashboard.noData')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

// ── TrafficAnomalyCard ──────────────────────────────────────────

const TrafficAnomalyCard = memo(function TrafficAnomalyCard({
  anomalies, loading,
}: {
  anomalies: TrafficAnomaly[]
  loading: boolean
}) {
  const { t } = useTranslation()
  const formatBytesLocal = createFormatBytes(t)

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm md:text-base">{t('dashboard.trafficAnomalies')}</CardTitle>
            <InfoTooltip text={t('dashboard.trafficAnomaliesTooltip')} side="right" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-5 w-full" />)}
          </div>
        ) : anomalies.length > 0 ? (
          <div className="space-y-1.5">
            {anomalies.map((a) => (
              <div key={a.nodeUuid} className="flex items-center gap-2 text-xs">
                <span className="text-white truncate w-24 shrink-0">{a.nodeName}</span>
                {a.direction === 'up' ? (
                  <ArrowUpRight className="w-3.5 h-3.5 text-red-400 shrink-0" />
                ) : (
                  <ArrowDownRight className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                )}
                <span className={cn(
                  'font-mono font-semibold shrink-0',
                  a.direction === 'up' ? 'text-red-400' : 'text-blue-400',
                )}>
                  {a.direction === 'up' ? '+' : ''}{a.deviationPercent}%
                </span>
                <span className="text-muted-foreground truncate">
                  {formatBytesLocal(a.todayBytes)} vs {formatBytesLocal(a.avgBytes)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-16 flex items-center justify-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-muted-foreground text-sm">{t('dashboard.noAnomalies')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
})


// ── Main Dashboard Component ─────────────────────────────────────

export default function Dashboard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const { formatBytes: formatBytesUtil } = useFormatters()
  const formatBytes = (bytes: number | null | undefined) => (!bytes || bytes <= 0) ? `0 ${t('common.bytes.b')}` : formatBytesUtil(bytes)
  const formatBytesShort = createFormatBytesShort(t)

  const canViewUsers = hasPermission('users', 'view')
  const canViewNodes = hasPermission('nodes', 'view')
  const canViewViolations = hasPermission('violations', 'view')
  const canViewAnalytics = hasPermission('analytics', 'view')
  const canViewBilling = hasPermission('billing', 'view')
  const canViewAudit = hasPermission('audit', 'view')
  const canViewFleet = hasPermission('fleet', 'view')
  // Chart state
  const [trafficPeriod, setTrafficPeriod] = useState('7d')
  const [trendMetric, setTrendMetric] = useState('users')
  const chart = useChartTheme()

  const trafficPeriodOptions = [
    { value: '24h', label: t('dashboard.period24h') },
    { value: '7d', label: t('dashboard.period7d') },
    { value: '30d', label: t('dashboard.period30d') },
  ]

  // ── Queries ──────────────────────────────────────────────────

  const { data: overview, isLoading: overviewLoading, isError: overviewError } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: canViewAnalytics,
  })

  const { data: violationStats, isLoading: violationsLoading, isError: violationsError } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: canViewViolations,
  })

  const { data: trafficStats, isLoading: trafficLoading } = useQuery({
    queryKey: ['trafficStats'],
    queryFn: fetchTrafficStats,
    refetchInterval: 120_000,
    staleTime: 60_000,
    enabled: canViewAnalytics,
  })

  const { data: timeseries, isLoading: timeseriesLoading } = useQuery({
    queryKey: ['timeseries', trafficPeriod, 'traffic'],
    queryFn: () => fetchTimeseries(trafficPeriod, 'traffic'),
    refetchInterval: 120_000,
    staleTime: 60_000,
    enabled: canViewAnalytics,
  })

  const { data: connectionsSeries, isLoading: connectionsLoading } = useQuery({
    queryKey: ['timeseries', '24h', 'connections'],
    queryFn: () => fetchTimeseries('24h', 'connections'),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: canViewAnalytics,
  })

  const { data: collectorStats, isLoading: collectorLoading } = useQuery({
    queryKey: ['collectorStats'],
    queryFn: fetchCollectorStats,
    refetchInterval: 30_000,
    staleTime: 15_000,
    enabled: canViewAnalytics,
  })

  const { data: systemComponents, isLoading: componentsLoading } = useQuery({
    queryKey: ['systemComponents'],
    queryFn: fetchSystemComponents,
    refetchInterval: 120_000,
    staleTime: 60_000,
    enabled: canViewAnalytics,
  })

  const { data: panelRecap } = useQuery({
    queryKey: ['panelRecap'],
    queryFn: fetchPanelRecap,
    staleTime: 120_000,
    refetchInterval: 300_000,
    enabled: canViewAnalytics,
  })

  const { data: topUsers, isLoading: topUsersLoading } = useQuery({
    queryKey: ['topUsers'],
    queryFn: () => fetchTopUsers(5),
    staleTime: 120_000,
    refetchInterval: 300_000,
    enabled: canViewAnalytics,
  })

  const { data: trends, isLoading: trendsLoading } = useQuery({
    queryKey: ['trends', trendMetric],
    queryFn: () => fetchTrends(trendMetric, '30d'),
    staleTime: 120_000,
    refetchInterval: 300_000,
    enabled: canViewAnalytics,
  })

  const { data: topViolators, isLoading: topViolatorsLoading } = useQuery({
    queryKey: ['topViolators'],
    queryFn: () => fetchTopViolators(7, 5),
    staleTime: 60_000,
    refetchInterval: 120_000,
    enabled: canViewViolations,
  })

  const { data: auditFeed, isLoading: auditLoading } = useQuery({
    queryKey: ['dashboard-audit-feed'],
    queryFn: () => auditApi.list({ limit: 10 }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: canViewAudit,
  })

  const { data: nodeFleet, isLoading: nodeFleetLoading } = useQuery({
    queryKey: ['dashboard-node-fleet'],
    queryFn: fetchNodeFleet,
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: canViewFleet,
  })

  const { data: expiringCounts, isLoading: expiringLoading } = useQuery({
    queryKey: ['dashboard-expiring'],
    queryFn: fetchExpiringCounts,
    refetchInterval: 600_000,
    staleTime: 300_000,
    enabled: canViewUsers,
  })

  // ── Refresh ──────────────────────────────────────────────────

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['overview'] })
    queryClient.invalidateQueries({ queryKey: ['violationStats'] })
    queryClient.invalidateQueries({ queryKey: ['trafficStats'] })
    queryClient.invalidateQueries({ queryKey: ['timeseries'] })
    queryClient.invalidateQueries({ queryKey: ['systemComponents'] })
    queryClient.invalidateQueries({ queryKey: ['billingSummary'] })
    queryClient.invalidateQueries({ queryKey: ['topUsers'] })
    queryClient.invalidateQueries({ queryKey: ['trends'] })
    queryClient.invalidateQueries({ queryKey: ['topViolators'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-audit-feed'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-node-fleet'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-expiring'] })
  }

  // ── Chart data ───────────────────────────────────────────────

  // Traffic chart data
  const trafficChartData = (Array.isArray(timeseries?.points) ? timeseries.points : []).map((p) => ({
    name: formatTimestamp(p.timestamp),
    value: p.value,
  })) || []

  // Per-node traffic chart data (for stacked area)
  const nodeTrafficChartData = (Array.isArray(timeseries?.node_points) ? timeseries.node_points : []).map((p) => ({
    name: formatTimestamp(p.timestamp),
    ...p.nodes,
  })) || []

  const nodeNames = timeseries?.node_names || {}
  const nodeUuids = Object.keys(nodeNames)

  // Connections data — per-node bar chart from current snapshot
  const connectionNodeNames = connectionsSeries?.node_names || {}
  const connectionsBarData = connectionsSeries?.node_points?.[0]
    ? Object.entries(connectionsSeries.node_points[0].nodes)
        .map(([uid, value]) => ({
          name: connectionNodeNames[uid] || uid.substring(0, 8),
          value,
        }))
        .filter((d) => d.value > 0)
        .sort((a, b) => b.value - a.value)
    : []

  // Violations chart
  const violationsChartData = violationStats
    ? [
        { name: t('dashboard.severityLow'), value: violationStats.low, key: 'low' },
        { name: t('dashboard.severityMedium'), value: violationStats.medium, key: 'medium' },
        { name: t('dashboard.severityHigh'), value: violationStats.high, key: 'high' },
        { name: t('dashboard.severityCritical'), value: violationStats.critical, key: 'critical' },
      ]
    : [
        { name: t('dashboard.severityLow'), value: 0, key: 'low' },
        { name: t('dashboard.severityMedium'), value: 0, key: 'medium' },
        { name: t('dashboard.severityHigh'), value: 0, key: 'high' },
        { name: t('dashboard.severityCritical'), value: 0, key: 'critical' },
      ]

  // ── Traffic anomaly computation ──────────────────────────────
  const trafficAnomalies = useMemo<TrafficAnomaly[]>(() => {
    if (!nodeFleet?.nodes?.length || !timeseries?.node_points?.length) return []
    const nNames = timeseries.node_names || {}
    const nodeAvgs: Record<string, number> = {}
    for (const uid of Object.keys(nNames)) {
      const vals = timeseries.node_points.map(p => p.nodes[uid] ?? 0).filter(v => v > 0)
      if (vals.length > 0) nodeAvgs[uid] = vals.reduce((a, b) => a + b, 0) / vals.length
    }
    const anomalies: TrafficAnomaly[] = []
    for (const node of nodeFleet.nodes) {
      if (!node.is_connected || node.is_disabled) continue
      const avg = nodeAvgs[node.uuid]
      if (avg == null || avg < 1024 * 1024) continue
      const today = node.traffic_today_bytes
      const deviation = avg > 0 ? ((today - avg) / avg) * 100 : 0
      if (Math.abs(deviation) > 50) {
        anomalies.push({
          nodeName: node.name, nodeUuid: node.uuid,
          todayBytes: today, avgBytes: avg,
          deviationPercent: Math.round(deviation),
          direction: deviation > 0 ? 'up' : 'down',
        })
      }
    }
    return anomalies.sort((a, b) => Math.abs(b.deviationPercent) - Math.abs(a.deviationPercent)).slice(0, 5)
  }, [nodeFleet, timeseries])

  const isLoading = overviewLoading || violationsLoading || trafficLoading || timeseriesLoading || connectionsLoading || componentsLoading

  return (
    <div className="space-y-6">
      {/* ── Page header ─────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('dashboard.title')}</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">{t('dashboard.subtitle')}</p>
        </div>
        <Button
          variant="secondary"
          onClick={handleRefreshAll}
          disabled={isLoading}
          className="self-start sm:self-auto"
        >
          <RefreshCw className={cn("w-4 h-4 mr-2", isLoading && "animate-spin")} />
          <span className="hidden sm:inline">{t('dashboard.refresh')}</span>
        </Button>
      </div>

      {/* ── Error banner ────────────────────────────────────────── */}
      {(overviewError || violationsError) && (
        <Card className="border-red-500/30 bg-red-500/10 animate-fade-in-down">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-red-400 text-sm">
                {t('dashboard.loadError')}
              </p>
              <Button variant="secondary" size="sm" onClick={handleRefreshAll}>
                {t('dashboard.retry')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Stats grid (5 compact cards) ────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {canViewUsers && (
          <StatCard
            title={t('dashboard.totalUsers')}
            value={overview?.total_users != null ? overview.total_users.toLocaleString() : '-'}
            icon={Users}
            color="cyan"
            subtitle={overview ? t('dashboard.usersSubtitle', { active: overview.active_users, expired: overview.expired_users }) : undefined}
            onClick={() => navigate('/users')}
            loading={overviewLoading && canViewAnalytics}
            index={0}
          />
        )}
        {canViewAnalytics && (
          <StatCard
            title={t('dashboard.currentOnline')}
            value={overview?.users_online != null ? overview.users_online.toLocaleString() : '-'}
            icon={Wifi}
            color="green"
            subtitle={overview ? t('dashboard.onlineSubtitle', { nodes: overview.online_nodes }) : undefined}
            loading={overviewLoading}
            index={1}
          />
        )}
        {canViewNodes && (
          <StatCard
            title={t('dashboard.activeNodes')}
            value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
            icon={Server}
            color="violet"
            subtitle={overview ? t('dashboard.nodesSubtitle', { offline: overview.offline_nodes, disabled: overview.disabled_nodes, online: overview.users_online || 0 }) : undefined}
            onClick={() => navigate('/nodes')}
            loading={overviewLoading && canViewAnalytics}
            index={2}
          />
        )}
        {canViewViolations && (
          <StatCard
            title={t('dashboard.violations')}
            value={overview ? `${overview.violations_today}` : '-'}
            icon={ShieldAlert}
            color={overview && overview.violations_today > 0 ? 'red' : 'yellow'}
            subtitle={overview ? t('dashboard.violationsSubtitle', { today: overview.violations_today, week: overview.violations_week }) : undefined}
            onClick={() => navigate('/violations')}
            loading={overviewLoading && canViewAnalytics}
            index={3}
          />
        )}
        {canViewAnalytics && (
          <StatCard
            title={t('dashboard.traffic')}
            value={overview ? formatBytes(overview.total_traffic_bytes) : trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
            icon={TrendingUp}
            color="pink"
            subtitle={trafficStats ? `${t('dashboard.trafficDay')}: ${formatBytes(trafficStats.today_bytes)} | ${t('dashboard.trafficWeek')}: ${formatBytes(trafficStats.week_bytes)} | ${t('dashboard.trafficMonth')}: ${formatBytes(trafficStats.month_bytes)}` : undefined}
            loading={overviewLoading && trafficLoading}
            index={4}
          />
        )}
      </div>

      {/* ── Row 2: Traffic Chart + Growth Trends ────────────────── */}
      {canViewAnalytics && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <CardHeader className="pb-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base md:text-lg">{t('dashboard.traffic')}</CardTitle>
                  <InfoTooltip text={t('dashboard.trafficChartTooltip')} side="right" />
                </div>
                <PeriodSwitcher value={trafficPeriod} onChange={setTrafficPeriod} options={trafficPeriodOptions} />
              </div>
            </CardHeader>
            <CardContent>
              {timeseriesLoading ? (
                <ChartSkeleton />
              ) : trafficChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={240}>
                  {nodeUuids.length > 0 && nodeTrafficChartData.length > 0 ? (
                    <AreaChart data={nodeTrafficChartData}>
                      <defs>
                        {nodeUuids.map((uid, i) => (
                          <linearGradient key={uid} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={chart.nodeColors[i % chart.nodeColors.length]} stopOpacity={0.3} />
                            <stop offset="95%" stopColor={chart.nodeColors[i % chart.nodeColors.length]} stopOpacity={0.05} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="name" stroke={chart.axis} fontSize={11} />
                      <YAxis stroke={chart.axis} fontSize={11} tickFormatter={(v) => formatBytesShort(v)} />
                      <RechartsTooltip content={<TrafficChartTooltip />} />
                      {nodeUuids.map((uid, i) => (
                        <Area key={uid} type="monotone" dataKey={uid} name={nodeNames[uid] || uid.substring(0, 8)} stackId="traffic" stroke={chart.nodeColors[i % chart.nodeColors.length]} fill={`url(#grad-${i})`} strokeWidth={2} />
                      ))}
                    </AreaChart>
                  ) : (
                    <LineChart data={trafficChartData}>
                      <defs>
                        <linearGradient id="trafficGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={chart.accentColor} stopOpacity={0.3} />
                          <stop offset="95%" stopColor={chart.accentColor} stopOpacity={0.05} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="name" stroke={chart.axis} fontSize={11} />
                      <YAxis stroke={chart.axis} fontSize={11} tickFormatter={(v) => formatBytesShort(v)} />
                      <RechartsTooltip content={<TrafficChartTooltip />} />
                      <Line type="monotone" dataKey="value" name={t('dashboard.traffic')} stroke={chart.accentColor} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: chart.accentColor }} />
                    </LineChart>
                  )}
                </ResponsiveContainer>
              ) : (
                <div className="h-60 flex items-center justify-center">
                  <span className="text-muted-foreground text-sm">{t('dashboard.noDataForPeriod')}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <GrowthTrendsCard trends={trends} loading={trendsLoading} metric={trendMetric} onMetricChange={setTrendMetric} />
      </div>
      )}

      {/* ── Row 3: Connections by Node + Top Users by Traffic ─────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {canViewAnalytics && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base md:text-lg">{t('dashboard.connectionsByNode')}</CardTitle>
                  <InfoTooltip text={t('dashboard.connectionsByNodeTooltip')} side="right" />
                </div>
                <span className="text-xs text-muted-foreground">
                  {t('dashboard.total')}: {overview?.users_online || 0}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {connectionsBarData.length > 0 ? (
                <ResponsiveContainer width="100%" height={Math.max(connectionsBarData.length * 40 + 20, 120)}>
                  <BarChart data={connectionsBarData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                    <XAxis type="number" stroke={chart.axis} fontSize={11} />
                    <YAxis dataKey="name" type="category" stroke={chart.axis} fontSize={11} width={120} tick={{ fill: chart.tick }} />
                    <RechartsTooltip contentStyle={chart.tooltipStyle} />
                    <Bar dataKey="value" name={t('dashboard.quantity', 'Количество')} radius={[0, 6, 6, 0]} maxBarSize={24}>
                      {connectionsBarData.map((_entry, i) => (
                        <Cell key={i} fill={chart.nodeColors[i % chart.nodeColors.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[120px] flex items-center justify-center">
                  <div className="text-center">
                    <Wifi className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
                    <span className="text-muted-foreground text-sm">
                      {overview?.users_online
                        ? t('dashboard.usersOnline', { count: overview.users_online })
                        : t('dashboard.noConnectionData')}
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {canViewAnalytics && (
          <TopUsersCard topUsers={topUsers} loading={topUsersLoading} />
        )}
      </div>

      {/* ── Row 4: Node Load + Expiry + Traffic Anomaly ───────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {canViewFleet && (
          <NodeLoadCard nodes={nodeFleet?.nodes || []} loading={nodeFleetLoading} />
        )}
        {canViewUsers && (
          <ExpiryCountsCard counts={expiringCounts} loading={expiringLoading} />
        )}
        {(canViewFleet && canViewAnalytics) && (
          <TrafficAnomalyCard anomalies={trafficAnomalies} loading={nodeFleetLoading || timeseriesLoading} />
        )}
      </div>

      {/* ── Row 5: Activity Feed + Violations + Top Violators ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {canViewAudit && (
          <ActivityFeedCard items={auditFeed?.items || []} loading={auditLoading} />
        )}

        {canViewViolations && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm md:text-base">{t('dashboard.violationsBySeverity')}</CardTitle>
                  <InfoTooltip text={t('dashboard.violationsBySeverityTooltip')} side="right" />
                </div>
                {violationStats && (
                  <span className="text-xs text-muted-foreground">
                    {t('dashboard.total')}: {violationStats.total}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {violationsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-6 w-full" />)}
                </div>
              ) : (
                <div className="space-y-2">
                  {violationsChartData.map((entry) => {
                    const maxVal = Math.max(...violationsChartData.map((e) => e.value), 1)
                    return (
                      <div key={entry.key} className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground w-20 shrink-0">{entry.name}</span>
                        <div className="flex-1 h-2 bg-[var(--glass-bg-hover)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${(entry.value / maxVal) * 100}%`,
                              background: SEVERITY_COLORS[entry.key] || '#fab005',
                            }}
                          />
                        </div>
                        <span className="text-xs text-white font-mono w-8 text-right">{entry.value}</span>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {canViewViolations && (
          <TopViolatorsCard topViolators={topViolators} loading={topViolatorsLoading} />
        )}
      </div>

      {/* ── Row 6: Billing + Collector + System Status + Updates ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {canViewBilling && <BillingSummaryCard loading={false} />}

        {canViewAnalytics && (
          <CollectorQueueCard stats={collectorStats} loading={collectorLoading} />
        )}

        {canViewAnalytics && (
          <SystemStatusCard
            components={systemComponents?.components || []}
            uptime={systemComponents?.uptime_seconds ?? null}
            version={systemComponents?.version || ''}
            loading={componentsLoading}
            panelRecap={panelRecap}
          />
        )}

        {canViewAnalytics ? (
          <UpdateCheckerCard />
        ) : !canViewBilling ? (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm md:text-base">{t('dashboard.quickActions')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { icon: Users, label: t('dashboard.users'), href: '/users', perm: 'users' },
                  { icon: Server, label: t('dashboard.nodes'), href: '/nodes', perm: 'nodes' },
                  { icon: ShieldAlert, label: t('dashboard.violationsLabel'), href: '/violations', perm: 'violations' },
                  { icon: Settings, label: t('dashboard.settings'), href: '/settings', perm: 'settings' },
                ]
                  .filter((item) => hasPermission(item.perm, 'view'))
                  .map((item) => (
                    <Button
                      key={item.href}
                      variant="secondary"
                      onClick={() => navigate(item.href)}
                      className="py-8 flex flex-col items-center gap-2 hover:shadow-glow-teal h-auto"
                    >
                      <item.icon className="w-6 h-6" />
                      <span>{item.label}</span>
                    </Button>
                  ))}
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  )
}
