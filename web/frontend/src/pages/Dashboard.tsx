import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { usePermissionStore } from '../store/permissionStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

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

interface ViolationStats {
  total: number
  critical: number
  high: number
  medium: number
  low: number
  unique_users: number
  avg_score: number
  max_score: number
  by_action: Record<string, number>
  by_country: Record<string, number>
}

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

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 Б'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatBytesShort(bytes: number): string {
  if (bytes <= 0) return '0'
  const k = 1024
  const sizes = ['Б', 'К', 'М', 'Г', 'Т']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + sizes[i]
}

function formatUptime(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '-'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}д ${h}ч`
  if (h > 0) return `${h}ч ${m}м`
  return `${m}м`
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

// Node chart colors
const NODE_COLORS = [
  '#06b6d4', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444',
  '#ec4899', '#14b8a6', '#6366f1', '#84cc16', '#f97316',
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
}

function StatCard({
  title, value, icon: Icon, color, subtitle, onClick, loading, index = 0,
  delta, deltaType = 'percent',
}: StatCardProps) {
  const colorConfig = {
    cyan: {
      bg: 'rgba(34, 211, 238, 0.15)',
      text: 'text-cyan-400',
      border: 'rgba(34, 211, 238, 0.3)',
    },
    green: {
      bg: 'rgba(64, 192, 87, 0.15)',
      text: 'text-green-400',
      border: 'rgba(64, 192, 87, 0.3)',
    },
    yellow: {
      bg: 'rgba(250, 176, 5, 0.15)',
      text: 'text-yellow-400',
      border: 'rgba(250, 176, 5, 0.3)',
    },
    red: {
      bg: 'rgba(250, 82, 82, 0.15)',
      text: 'text-red-400',
      border: 'rgba(250, 82, 82, 0.3)',
    },
    violet: {
      bg: 'rgba(151, 117, 250, 0.15)',
      text: 'text-violet-400',
      border: 'rgba(151, 117, 250, 0.3)',
    },
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
            <p className="text-sm text-muted-foreground">{title}</p>
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
              Подробнее <ExternalLink className="w-3 h-3" />
            </span>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ── DeltaIndicator ───────────────────────────────────────────────

function DeltaIndicator({ value, type = 'percent' }: { value: number; type?: 'percent' | 'absolute' }) {
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
}

// ── ChartSkeleton ────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div className="h-64 flex items-center justify-center">
      <div className="flex flex-col items-center gap-2">
        <div
          className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
          style={{ borderColor: '#0d9488', borderTopColor: 'transparent' }}
        />
        <span className="text-sm text-muted-foreground">Загрузка...</span>
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

const tooltipStyle = {
  backgroundColor: 'rgba(22, 27, 34, 0.95)',
  border: '1px solid rgba(72, 79, 88, 0.3)',
  borderRadius: '8px',
  backdropFilter: 'blur(12px)',
}

function TrafficChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={tooltipStyle} className="px-3 py-2">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {formatBytes(entry.value)}
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
          <CardTitle className="text-base md:text-lg">Состояние системы</CardTitle>
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
                online: 'Работает',
                offline: 'Недоступен',
                degraded: 'Проблемы',
                unknown: 'Неизвестно',
              }[comp.status] || comp.status

              // Build detail string
              let detail = ''
              if (comp.name === 'Remnawave API' && comp.details.response_time_ms) {
                detail = `${comp.details.response_time_ms}мс`
              } else if (comp.name === 'Nodes') {
                detail = `${comp.details.online || 0}/${comp.details.total || 0}`
              } else if (comp.name === 'WebSocket') {
                detail = `${comp.details.active_connections || 0} сессий`
              } else if (comp.name === 'PostgreSQL' && comp.details.size != null) {
                detail = `pool: ${comp.details.free_size || 0}/${comp.details.size || 0}`
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
              <span className="text-xs text-muted-foreground">Время работы</span>
              <span className="text-xs text-white font-mono">{formatUptime(uptime)}</span>
            </div>
          </>
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

const TRAFFIC_PERIOD_OPTIONS = [
  { value: '24h', label: '24ч' },
  { value: '7d', label: '7д' },
  { value: '30d', label: '30д' },
]

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
          Версии и обновления
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Current version + update */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-dark-200">Текущая версия</p>
            <p className="text-lg font-bold text-white">v{updateInfo.current_version}</p>
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
                v{updateInfo.latest_version} доступна
              </Badge>
            </a>
          ) : (
            <Badge className="bg-dark-600 text-dark-200 border-dark-500 border">
              Актуально
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)

  const canViewUsers = hasPermission('users', 'view')
  const canViewNodes = hasPermission('nodes', 'view')
  const canViewViolations = hasPermission('violations', 'view')
  const canViewAnalytics = hasPermission('analytics', 'view')
  // Chart state
  const [trafficPeriod, setTrafficPeriod] = useState('7d')

  // ── Queries ──────────────────────────────────────────────────

  const { data: overview, isLoading: overviewLoading, isError: overviewError } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: 30000,
    enabled: canViewAnalytics,
  })

  const { data: violationStats, isLoading: violationsLoading, isError: violationsError } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
    refetchInterval: 30000,
    enabled: canViewViolations,
  })

  const { data: trafficStats, isLoading: trafficLoading } = useQuery({
    queryKey: ['trafficStats'],
    queryFn: fetchTrafficStats,
    refetchInterval: 60000,
    enabled: canViewAnalytics,
  })

  const { data: timeseries, isLoading: timeseriesLoading } = useQuery({
    queryKey: ['timeseries', trafficPeriod, 'traffic'],
    queryFn: () => fetchTimeseries(trafficPeriod, 'traffic'),
    refetchInterval: 60000,
    enabled: canViewAnalytics,
  })

  const { data: connectionsSeries } = useQuery({
    queryKey: ['timeseries', '24h', 'connections'],
    queryFn: () => fetchTimeseries('24h', 'connections'),
    refetchInterval: 30000,
    enabled: canViewAnalytics,
  })

  const { data: deltas } = useQuery({
    queryKey: ['deltas'],
    queryFn: fetchDeltas,
    refetchInterval: 120000,
    enabled: canViewAnalytics,
  })

  const { data: systemComponents, isLoading: componentsLoading } = useQuery({
    queryKey: ['systemComponents'],
    queryFn: fetchSystemComponents,
    refetchInterval: 60000,
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
        { name: 'Низкий', value: violationStats.low, key: 'low' },
        { name: 'Средний', value: violationStats.medium, key: 'medium' },
        { name: 'Высокий', value: violationStats.high, key: 'high' },
        { name: 'Критический', value: violationStats.critical, key: 'critical' },
      ]
    : [
        { name: 'Низкий', value: 0, key: 'low' },
        { name: 'Средний', value: 0, key: 'medium' },
        { name: 'Высокий', value: 0, key: 'high' },
        { name: 'Критический', value: 0, key: 'critical' },
      ]

  const actionLabels: Record<string, string> = {
    'no_action': 'Нет действий',
    'monitor': 'Мониторинг',
    'warn': 'Предупреждение',
    'soft_block': 'Мягкая блок.',
    'temp_block': 'Врем. блок.',
    'hard_block': 'Жёсткая блок.',
  }
  const actionChartData = violationStats?.by_action
    ? Object.entries(violationStats.by_action).map(([name, value]) => ({
        name: actionLabels[name] || name,
        value,
      }))
    : []

  const isLoading = overviewLoading || violationsLoading || trafficLoading

  return (
    <div className="space-y-6">
      {/* ── Page header ─────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Панель управления</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">Обзор системы Remnawave</p>
        </div>
        <Button
          variant="secondary"
          onClick={handleRefreshAll}
          disabled={isLoading}
          className="self-start sm:self-auto"
        >
          <RefreshCw className={cn("w-4 h-4 mr-2", isLoading && "animate-spin")} />
          <span className="hidden sm:inline">Обновить</span>
        </Button>
      </div>

      {/* ── Error banner ────────────────────────────────────────── */}
      {(overviewError || violationsError) && (
        <Card className="border-red-500/30 bg-red-500/10 animate-fade-in-down">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-red-400 text-sm">
                Ошибка загрузки данных. Некоторые показатели могут быть недоступны.
              </p>
              <Button variant="secondary" size="sm" onClick={handleRefreshAll}>
                Повторить
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Stats grid with deltas ──────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {canViewUsers && (
          <StatCard
            title="Всего пользователей"
            value={overview?.total_users != null ? overview.total_users.toLocaleString() : '-'}
            icon={Users}
            color="cyan"
            subtitle={overview ? `${overview.active_users} активных, ${overview.expired_users} истекших` : undefined}
            onClick={() => navigate('/users')}
            loading={overviewLoading && canViewAnalytics}
            index={0}
            delta={deltas?.users_delta}
            deltaType="percent"
          />
        )}
        {canViewNodes && (
          <StatCard
            title="Активные ноды"
            value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
            icon={Server}
            color="green"
            subtitle={overview ? `${overview.offline_nodes} офлайн, ${overview.disabled_nodes} отключ.${overview.users_online ? `, ${overview.users_online} онлайн` : ''}` : undefined}
            onClick={() => navigate('/nodes')}
            loading={overviewLoading && canViewAnalytics}
            index={1}
            delta={deltas?.nodes_delta}
            deltaType="absolute"
          />
        )}
        {canViewViolations && (
          <StatCard
            title="Нарушения"
            value={overview ? `${overview.violations_today}` : '-'}
            icon={ShieldAlert}
            color={overview && overview.violations_today > 0 ? 'red' : 'yellow'}
            subtitle={overview ? `Сегодня: ${overview.violations_today}, за неделю: ${overview.violations_week}` : undefined}
            onClick={() => navigate('/violations')}
            loading={overviewLoading && canViewAnalytics}
            index={2}
            delta={deltas?.violations_delta}
            deltaType="absolute"
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
                  <p className="text-sm text-muted-foreground">Трафик</p>
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
                    background: 'rgba(151, 117, 250, 0.15)',
                    border: '1px solid rgba(151, 117, 250, 0.3)',
                  }}
                >
                  <TrendingUp className="w-6 h-6 text-violet-400" />
                </div>
              </div>
              {trafficStats && (
                <>
                  <Separator className="mt-3" />
                  <div className="space-y-1.5 mt-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Сегодня</span>
                      <span className="text-xs text-cyan-400 font-semibold font-mono">{formatBytes(trafficStats.today_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">За неделю</span>
                      <span className="text-xs text-cyan-400 font-semibold font-mono">{formatBytes(trafficStats.week_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">За месяц</span>
                      <span className="text-xs text-cyan-400 font-semibold font-mono">{formatBytes(trafficStats.month_bytes)}</span>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* ── Traffic Chart ───────────────────────────────────────── */}
      {canViewAnalytics && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardHeader className="pb-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <CardTitle className="text-base md:text-lg">Трафик</CardTitle>
              <PeriodSwitcher
                value={trafficPeriod}
                onChange={setTrafficPeriod}
                options={TRAFFIC_PERIOD_OPTIONS}
              />
            </div>
          </CardHeader>
          <CardContent>
            {timeseriesLoading ? (
              <ChartSkeleton />
            ) : trafficChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
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
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(72, 79, 88, 0.3)" />
                    <XAxis dataKey="name" stroke="#8b949e" fontSize={11} />
                    <YAxis
                      stroke="#8b949e"
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
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(72, 79, 88, 0.3)" />
                    <XAxis dataKey="name" stroke="#8b949e" fontSize={11} />
                    <YAxis
                      stroke="#8b949e"
                      fontSize={11}
                      tickFormatter={(v) => formatBytesShort(v)}
                    />
                    <RechartsTooltip content={<TrafficChartTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="value"
                      name="Трафик"
                      stroke="#06b6d4"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, fill: '#06b6d4' }}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex items-center justify-center">
                <span className="text-muted-foreground text-sm">Нет данных за выбранный период</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Connections Chart + Violations ───────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Connections by node — horizontal bar chart */}
        {canViewAnalytics && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base md:text-lg">Подключения по нодам</CardTitle>
                <span className="text-xs text-muted-foreground">
                  Всего: {overview?.users_online || 0}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {connectionsBarData.length > 0 ? (
                <ResponsiveContainer width="100%" height={Math.max(connectionsBarData.length * 40 + 20, 120)}>
                  <BarChart data={connectionsBarData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(72, 79, 88, 0.3)" />
                    <XAxis type="number" stroke="#8b949e" fontSize={11} />
                    <YAxis
                      dataKey="name"
                      type="category"
                      stroke="#8b949e"
                      fontSize={11}
                      width={120}
                      tick={{ fill: '#c9d1d9' }}
                    />
                    <RechartsTooltip contentStyle={tooltipStyle} />
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
                        ? `${overview.users_online} пользователей онлайн`
                        : 'Нет данных о подключениях'}
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
                <CardTitle className="text-base md:text-lg">Нарушения по уровню (за 7 дней)</CardTitle>
                {violationStats && (
                  <span className="text-xs text-muted-foreground">
                    Всего: {violationStats.total} | Уникальных: {violationStats.unique_users}
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
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(72, 79, 88, 0.3)" />
                    <XAxis type="number" stroke="#8b949e" fontSize={12} />
                    <YAxis dataKey="name" type="category" stroke="#8b949e" fontSize={12} width={100} />
                    <RechartsTooltip contentStyle={tooltipStyle} />
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

      {/* ── Bottom row: Violations by action + System status ──── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Violations by action */}
        {canViewViolations && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base md:text-lg">По рекомендации</CardTitle>
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
                  <span className="text-muted-foreground text-sm">Нет данных</span>
                </div>
              )}
              {violationStats && violationStats.max_score > 0 && (
                <>
                  <Separator className="mt-4" />
                  <div className="space-y-1 mt-4">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Средний скор</span>
                      <span className="text-white">{violationStats.avg_score.toFixed(1)}</span>
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Максимальный скор</span>
                      <span className="text-white">{violationStats.max_score.toFixed(1)}</span>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* System status */}
        {canViewAnalytics ? (
          <SystemStatusCard
            components={systemComponents?.components || []}
            uptime={systemComponents?.uptime_seconds ?? null}
            version={systemComponents?.version || '2.0.0'}
            loading={componentsLoading}
          />
        ) : (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base md:text-lg">Быстрые действия</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { icon: Users, label: 'Пользователи', href: '/users', perm: 'users' },
                  { icon: Server, label: 'Ноды', href: '/nodes', perm: 'nodes' },
                  { icon: ShieldAlert, label: 'Нарушения', href: '/violations', perm: 'violations' },
                  { icon: Settings, label: 'Настройки', href: '/settings', perm: 'settings' },
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

        {/* Update checker */}
        {canViewAnalytics && <UpdateCheckerCard />}
      </div>
    </div>
  )
}
