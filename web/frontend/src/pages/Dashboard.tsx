import { useState, memo } from 'react'
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
  Minus,
  Activity,
  Wifi,
  Database,
  Globe,
  CreditCard,
  CalendarClock,
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

interface DeltaStats {
  users_delta: number | null
  users_online_delta: number | null
  traffic_delta: number | null
  violations_delta: number | null
  nodes_delta: number | null
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

const fetchDeltas = async (): Promise<DeltaStats> => {
  const { data } = await client.get('/analytics/deltas')
  return data
}

const fetchSystemComponents = async (): Promise<SystemComponentsResponse> => {
  const { data } = await client.get('/analytics/system/components')
  return data
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

// Node chart colors — mono-teal palette (varying brightness for distinction)
const NODE_COLORS = [
  '#06b6d4', '#0891b2', '#22d3ee', '#0e7490', '#67e8f9',
  '#155e75', '#0d9488', '#14b8a6', '#a5f3fc', '#164e63',
]

// ── StatCard ─────────────────────────────────────────────────────

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  color: 'cyan' | 'green' | 'yellow' | 'red' | 'violet'
  subtitle?: string
  onClick?: () => void
  loading?: boolean
  index?: number
  delta?: number | null
  deltaType?: 'percent' | 'absolute'
  tooltip?: string
}

const StatCard = memo(function StatCard({
  title, value, icon: Icon, color, subtitle, onClick, loading, index = 0,
  delta, deltaType = 'percent', tooltip,
}: StatCardProps) {
  const { t } = useTranslation()
  // Mono-accent: all stat card icons use the theme accent color via CSS variables
  const accentStyle = {
    bg: 'rgba(var(--glow-rgb), 0.15)',
    text: 'text-primary-400',
    border: 'rgba(var(--glow-rgb), 0.3)',
  }
  const colorConfig = {
    cyan: accentStyle,
    green: accentStyle,
    yellow: accentStyle,
    red: accentStyle,
    violet: accentStyle,
  }

  const cfg = colorConfig[color]

  return (
    <Card
      className={cn(
        "animate-fade-in-up group",
        onClick && "cursor-pointer hover:shadow-glow-teal transition-shadow"
      )}
      onClick={onClick}
      style={{ animationDelay: `${index * 0.07}s` }}
    >
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1">
              <p className="text-sm text-muted-foreground">{title}</p>
              {tooltip && <InfoTooltip text={tooltip} side="right" iconClassName="w-3.5 h-3.5" />}
            </div>
            {loading ? (
              <Skeleton className="h-8 w-20 mt-1" />
            ) : (
              <div className="flex items-center gap-2 mt-1">
                <p className="text-xl md:text-2xl font-bold text-white">{value}</p>
                {delta != null && delta !== 0 && (
                  <DeltaIndicator value={delta} type={deltaType} />
                )}
              </div>
            )}
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
            )}
          </div>
          <div
            className="p-3 rounded-lg transition-all duration-200 shrink-0"
            style={{
              background: cfg.bg,
              border: `1px solid ${cfg.border}`,
            }}
          >
            <Icon className={cn("w-6 h-6", cfg.text)} />
          </div>
        </div>
        {onClick && (
          <>
            <Separator className="mt-3" />
            <span className="text-xs text-muted-foreground group-hover:text-primary-400 flex items-center gap-1 transition-colors duration-200 mt-3">
              {t('dashboard.details')} <ExternalLink className="w-3 h-3" />
            </span>
          </>
        )}
      </CardContent>
    </Card>
  )
})

// ── DeltaIndicator ───────────────────────────────────────────────

const DeltaIndicator = memo(function DeltaIndicator({ value, type = 'percent' }: { value: number; type?: 'percent' | 'absolute' }) {
  const isPositive = value > 0
  const isNeutral = value === 0

  const text = type === 'percent'
    ? `${isPositive ? '+' : ''}${value}%`
    : `${isPositive ? '+' : ''}${value}`

  if (isNeutral) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
        <Minus className="w-3 h-3" />
        {text}
      </span>
    )
  }

  return (
    <span className={cn(
      "inline-flex items-center gap-0.5 text-xs font-medium",
      isPositive ? "text-green-400" : "text-red-400",
    )}>
      {isPositive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
      {text}
    </span>
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
          style={{ borderColor: '#0d9488', borderTopColor: 'transparent' }}
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
    <div className="flex items-center gap-1 bg-dark-600/50 rounded-lg p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-2.5 py-1 text-xs rounded-md transition-all duration-200",
            value === opt.value
              ? "bg-primary/20 text-primary-400 font-medium"
              : "text-muted-foreground hover:text-white"
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
  return (
    <div style={chart.tooltipStyle} className="px-3 py-2">
      <p className={cn("text-xs mb-1", chart.tooltipMutedClass)}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {formatBytesLocal(entry.value)}
        </p>
      ))}
    </div>
  )
}

// ── SystemStatusCard ─────────────────────────────────────────────

function SystemStatusCard({
  components,
  uptime,
  version,
  loading,
}: {
  components: SystemComponent[]
  uptime: number | null
  version: string
  loading: boolean
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
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base md:text-lg">{t('dashboard.systemStatus')}</CardTitle>
            <InfoTooltip
              text={t('dashboard.systemStatusTooltip')}
              side="right"
            />
          </div>
          {version && (
            <Badge variant="secondary" className="text-[10px] font-mono">
              v{version}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-2.5">
            {components.map((comp) => {
              const IconComp = iconMap[comp.name] || Activity
              const statusColor = statusColorMap[comp.status] || '#6b7280'
              const statusLabel = {
                online: t('dashboard.statusOnline'),
                offline: t('dashboard.statusOffline'),
                degraded: t('dashboard.statusDegraded'),
                unknown: t('dashboard.statusUnknown'),
              }[comp.status] || comp.status

              // Build detail string
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
                <div key={comp.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <IconComp className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm text-white">{comp.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {detail && (
                      <span className="text-[10px] text-muted-foreground font-mono">{detail}</span>
                    )}
                    <Badge
                      variant={comp.status === 'online' ? 'success' : comp.status === 'degraded' ? 'warning' : 'destructive'}
                      className="gap-1.5 px-2 text-[10px]"
                    >
                      <span
                        className={cn("w-1.5 h-1.5 rounded-full", comp.status === 'online' && "animate-pulse")}
                        style={{
                          background: statusColor,
                          boxShadow: `0 0 6px ${statusColor}80`,
                        }}
                      />
                      {statusLabel}
                    </Badge>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {uptime != null && (
          <>
            <Separator className="mt-3" />
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-muted-foreground">{t('dashboard.uptime')}</span>
              <span className="text-xs text-white font-mono">{formatUptime(uptime)}</span>
            </div>
          </>
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
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingProviders')}</span>
                <span className="text-xs text-white font-mono">{billing.total_providers}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingNodes')}</span>
                <span className="text-xs text-white font-mono">{billing.total_billing_nodes}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{t('dashboard.billingTotalSpent')}</span>
                <span className="text-xs text-primary-400 font-semibold font-mono">
                  {formatCurrency(Number(billing.total_spent) || 0)}
                </span>
              </div>
              {billing.next_payment_date && (
                <div className="flex items-center justify-between">
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

function UpdateCheckerCard() {
  const { t } = useTranslation()
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
            <Badge className="bg-dark-600 text-dark-200 border-dark-500 border">
              {t('dashboard.upToDate')}
            </Badge>
          )}
        </div>

        {/* Changelog preview */}
        {updateInfo.update_available && updateInfo.changelog && (
          <div className="bg-dark-700 rounded-lg p-3 max-h-24 overflow-auto">
            <p className="text-xs text-dark-300 whitespace-pre-wrap line-clamp-4">
              {updateInfo.changelog.slice(0, 300)}
            </p>
          </div>
        )}

        <Separator className="bg-dark-600" />

        {/* Dependencies */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          {deps?.python && (
            <div className="flex items-center justify-between bg-dark-700 rounded px-3 py-1.5">
              <span className="text-dark-300">Python</span>
              <span className="text-white font-mono text-xs">{deps.python}</span>
            </div>
          )}
          {deps?.postgresql && (
            <div className="flex items-center justify-between bg-dark-700 rounded px-3 py-1.5">
              <span className="text-dark-300">PostgreSQL</span>
              <span className="text-white font-mono text-xs">{deps.postgresql}</span>
            </div>
          )}
          {deps?.fastapi && (
            <div className="flex items-center justify-between bg-dark-700 rounded px-3 py-1.5">
              <span className="text-dark-300">FastAPI</span>
              <span className="text-white font-mono text-xs">{deps.fastapi}</span>
            </div>
          )}
          {uniqueXray.length > 0 && (
            <div className="flex items-center justify-between bg-dark-700 rounded px-3 py-1.5">
              <span className="text-dark-300">Xray</span>
              <span className="text-white font-mono text-xs">{uniqueXray.join(', ')}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}


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
  // Chart state
  const [trafficPeriod, setTrafficPeriod] = useState('7d')
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
    refetchInterval: 30000,
    staleTime: 15_000,
    enabled: canViewAnalytics,
  })

  const { data: violationStats, isLoading: violationsLoading, isError: violationsError } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
    refetchInterval: 30000,
    staleTime: 15_000,
    enabled: canViewViolations,
  })

  const { data: trafficStats, isLoading: trafficLoading } = useQuery({
    queryKey: ['trafficStats'],
    queryFn: fetchTrafficStats,
    refetchInterval: 60000,
    staleTime: 30_000,
    enabled: canViewAnalytics,
  })

  const { data: timeseries, isLoading: timeseriesLoading } = useQuery({
    queryKey: ['timeseries', trafficPeriod, 'traffic'],
    queryFn: () => fetchTimeseries(trafficPeriod, 'traffic'),
    refetchInterval: 60000,
    staleTime: 30_000,
    enabled: canViewAnalytics,
  })

  const { data: connectionsSeries, isLoading: connectionsLoading } = useQuery({
    queryKey: ['timeseries', '24h', 'connections'],
    queryFn: () => fetchTimeseries('24h', 'connections'),
    refetchInterval: 30000,
    staleTime: 15_000,
    enabled: canViewAnalytics,
  })

  const { data: deltas, isLoading: deltasLoading } = useQuery({
    queryKey: ['deltas'],
    queryFn: fetchDeltas,
    refetchInterval: 120000,
    staleTime: 60_000,
    enabled: canViewAnalytics,
  })

  const { data: systemComponents, isLoading: componentsLoading } = useQuery({
    queryKey: ['systemComponents'],
    queryFn: fetchSystemComponents,
    refetchInterval: 60000,
    staleTime: 30_000,
    enabled: canViewAnalytics,
  })

  // ── Refresh ──────────────────────────────────────────────────

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['overview'] })
    queryClient.invalidateQueries({ queryKey: ['violationStats'] })
    queryClient.invalidateQueries({ queryKey: ['trafficStats'] })
    queryClient.invalidateQueries({ queryKey: ['timeseries'] })
    queryClient.invalidateQueries({ queryKey: ['deltas'] })
    queryClient.invalidateQueries({ queryKey: ['systemComponents'] })
    queryClient.invalidateQueries({ queryKey: ['billingSummary'] })
  }

  // ── Chart data ───────────────────────────────────────────────

  // Traffic chart data
  const trafficChartData = timeseries?.points?.map((p) => ({
    name: formatTimestamp(p.timestamp),
    value: p.value,
  })) || []

  // Per-node traffic chart data (for stacked area)
  const nodeTrafficChartData = timeseries?.node_points?.map((p) => ({
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

  const actionLabels: Record<string, string> = {
    'no_action': t('dashboard.actionNoAction'),
    'monitor': t('dashboard.actionMonitor'),
    'warn': t('dashboard.actionWarn'),
    'soft_block': t('dashboard.actionSoftBlock'),
    'temp_block': t('dashboard.actionTempBlock'),
    'hard_block': t('dashboard.actionHardBlock'),
  }
  const actionChartData = violationStats?.by_action
    ? Object.entries(violationStats.by_action).map(([name, value]) => ({
        name: actionLabels[name] || name,
        value,
      }))
    : []

  const isLoading = overviewLoading || violationsLoading || trafficLoading || timeseriesLoading || connectionsLoading || deltasLoading || componentsLoading

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

      {/* ── Stats grid with deltas ──────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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
            delta={deltas?.users_delta}
            deltaType="percent"
            tooltip={t('dashboard.totalUsersTooltip')}
          />
        )}
        {canViewNodes && (
          <StatCard
            title={t('dashboard.activeNodes')}
            value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
            icon={Server}
            color="green"
            subtitle={overview ? t('dashboard.nodesSubtitle', { offline: overview.offline_nodes, disabled: overview.disabled_nodes, online: overview.users_online || 0 }) : undefined}
            onClick={() => navigate('/nodes')}
            loading={overviewLoading && canViewAnalytics}
            index={1}
            delta={deltas?.nodes_delta}
            deltaType="absolute"
            tooltip={t('dashboard.activeNodesTooltip')}
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
            index={2}
            delta={deltas?.violations_delta}
            deltaType="absolute"
            tooltip={t('dashboard.violationsTooltip')}
          />
        )}
        {canViewAnalytics && (
          <Card
            className="animate-fade-in-up"
            style={{ animationDelay: '0.21s' }}
          >
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1">
                    <p className="text-sm text-muted-foreground">{t('dashboard.traffic')}</p>
                    <InfoTooltip
                      text={t('dashboard.trafficTooltip')}
                      side="right"
                      iconClassName="w-3.5 h-3.5"
                    />
                  </div>
                  {(overviewLoading && trafficLoading) ? (
                    <Skeleton className="h-8 w-20 mt-1" />
                  ) : (
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-xl md:text-2xl font-bold text-white">
                        {overview ? formatBytes(overview.total_traffic_bytes) : trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
                      </p>
                      {deltas?.traffic_delta != null && deltas.traffic_delta !== 0 && (
                        <DeltaIndicator value={deltas.traffic_delta} type="percent" />
                      )}
                    </div>
                  )}
                </div>
                <div
                  className="p-3 rounded-lg"
                  style={{
                    background: 'rgba(var(--glow-rgb), 0.15)',
                    border: '1px solid rgba(var(--glow-rgb), 0.3)',
                  }}
                >
                  <TrendingUp className="w-6 h-6 text-primary-400" />
                </div>
              </div>
              {trafficStats && (
                <>
                  <Separator className="mt-3" />
                  <div className="space-y-1.5 mt-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{t('dashboard.today')}</span>
                      <span className="text-xs text-primary-400 font-semibold font-mono">{formatBytes(trafficStats.today_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{t('dashboard.thisWeek')}</span>
                      <span className="text-xs text-primary-400 font-semibold font-mono">{formatBytes(trafficStats.week_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{t('dashboard.thisMonth')}</span>
                      <span className="text-xs text-primary-400 font-semibold font-mono">{formatBytes(trafficStats.month_bytes)}</span>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ── System Status + Traffic Chart (side by side) ────────── */}
      {canViewAnalytics && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Status (left) */}
          <SystemStatusCard
            components={systemComponents?.components || []}
            uptime={systemComponents?.uptime_seconds ?? null}
            version={systemComponents?.version || ''}
            loading={componentsLoading}
          />

        {/* Traffic Chart (right) */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <CardHeader className="pb-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base md:text-lg">{t('dashboard.traffic')}</CardTitle>
                  <InfoTooltip
                    text={t('dashboard.trafficChartTooltip')}
                    side="right"
                  />
                </div>
                <PeriodSwitcher
                  value={trafficPeriod}
                  onChange={setTrafficPeriod}
                  options={trafficPeriodOptions}
                />
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
                            <stop offset="5%" stopColor={NODE_COLORS[i % NODE_COLORS.length]} stopOpacity={0.3} />
                            <stop offset="95%" stopColor={NODE_COLORS[i % NODE_COLORS.length]} stopOpacity={0.05} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="name" stroke={chart.axis} fontSize={11} />
                      <YAxis
                        stroke={chart.axis}
                        fontSize={11}
                        tickFormatter={(v) => formatBytesShort(v)}
                      />
                      <RechartsTooltip content={<TrafficChartTooltip />} />
                      {nodeUuids.map((uid, i) => (
                        <Area
                          key={uid}
                          type="monotone"
                          dataKey={uid}
                          name={nodeNames[uid] || uid.substring(0, 8)}
                          stackId="traffic"
                          stroke={NODE_COLORS[i % NODE_COLORS.length]}
                          fill={`url(#grad-${i})`}
                          strokeWidth={2}
                        />
                      ))}
                    </AreaChart>
                  ) : (
                    <LineChart data={trafficChartData}>
                      <defs>
                        <linearGradient id="trafficGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.05} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                      <XAxis dataKey="name" stroke={chart.axis} fontSize={11} />
                      <YAxis
                        stroke={chart.axis}
                        fontSize={11}
                        tickFormatter={(v) => formatBytesShort(v)}
                      />
                      <RechartsTooltip content={<TrafficChartTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="value"
                        name={t('dashboard.traffic')}
                        stroke="#06b6d4"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: '#06b6d4' }}
                      />
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
      </div>
      )}

      {/* ── Connections Chart + Violations ───────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Connections by node — horizontal bar chart */}
        {canViewAnalytics && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base md:text-lg">{t('dashboard.connectionsByNode')}</CardTitle>
                  <InfoTooltip
                    text={t('dashboard.connectionsByNodeTooltip')}
                    side="right"
                  />
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
                    <YAxis
                      dataKey="name"
                      type="category"
                      stroke={chart.axis}
                      fontSize={11}
                      width={120}
                      tick={{ fill: chart.tick }}
                    />
                    <RechartsTooltip contentStyle={chart.tooltipStyle} />
                    <Bar dataKey="value" radius={[0, 6, 6, 0]} maxBarSize={24}>
                      {connectionsBarData.map((_entry, i) => (
                        <Cell key={i} fill={NODE_COLORS[i % NODE_COLORS.length]} />
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

        {/* Violations by severity */}
        {canViewViolations && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <CardHeader className="pb-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base md:text-lg">{t('dashboard.violationsBySeverity')}</CardTitle>
                  <InfoTooltip
                    text={t('dashboard.violationsBySeverityTooltip')}
                    side="right"
                  />
                </div>
                {violationStats && (
                  <span className="text-xs text-muted-foreground">
                    {t('dashboard.total')}: {violationStats.total} | {t('dashboard.unique')}: {violationStats.unique_users}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {violationsLoading ? (
                <ChartSkeleton />
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={violationsChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                    <XAxis type="number" stroke={chart.axis} fontSize={12} />
                    <YAxis dataKey="name" type="category" stroke={chart.axis} fontSize={12} width={100} />
                    <RechartsTooltip contentStyle={chart.tooltipStyle} />
                    <Bar dataKey="value" radius={[0, 8, 8, 0]}>
                      {violationsChartData.map((entry) => (
                        <Cell key={entry.key} fill={SEVERITY_COLORS[entry.key] || '#fab005'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ── Bottom row: Violations by action + Billing/Updates ──── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Violations by action */}
        {canViewViolations && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base md:text-lg">{t('dashboard.byRecommendation')}</CardTitle>
                <InfoTooltip
                  text={t('dashboard.byRecommendationTooltip')}
                  side="right"
                />
              </div>
            </CardHeader>
            <CardContent>
              {violationsLoading ? (
                <ChartSkeleton />
              ) : actionChartData.length > 0 ? (
                <div className="space-y-3">
                  {actionChartData.map((item, i) => (
                    <div key={item.name} className="flex items-center justify-between animate-fade-in" style={{ animationDelay: `${i * 0.05}s` }}>
                      <span className="text-sm text-dark-100">{item.name}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 bg-dark-600 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${violationStats && violationStats.total > 0 ? (item.value / violationStats.total) * 100 : 0}%`,
                              background: 'linear-gradient(90deg, #0d9488, #06b6d4)',
                            }}
                          />
                        </div>
                        <span className="text-sm text-white font-mono w-8 text-right">{item.value}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-48 flex items-center justify-center">
                  <span className="text-muted-foreground text-sm">{t('dashboard.noData')}</span>
                </div>
              )}
              {violationStats && violationStats.max_score > 0 && (
                <>
                  <Separator className="mt-4" />
                  <div className="space-y-1 mt-4">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>{t('dashboard.avgScore')}</span>
                      <span className="text-white">{violationStats.avg_score.toFixed(1)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>{t('dashboard.maxScore')}</span>
                      <span className="text-white">{violationStats.max_score.toFixed(1)}</span>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Right column: Billing/Updates or QuickActions */}
        {canViewAnalytics || canViewBilling ? (
          <div className="space-y-6">
            {canViewBilling && <BillingSummaryCard loading={false} />}
            {canViewAnalytics && <UpdateCheckerCard />}
          </div>
        ) : (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base md:text-lg">{t('dashboard.quickActions')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
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
        )}
      </div>
    </div>
  )
}
