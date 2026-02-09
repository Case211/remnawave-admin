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
} from 'recharts'
import client from '../api/client'
import { usePermissionStore } from '../store/permissionStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

// Types matching backend responses
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

// API functions
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

// Utility functions
function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 Б'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// Stat card component
interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  color: 'cyan' | 'green' | 'yellow' | 'red' | 'violet'
  subtitle?: string
  onClick?: () => void
  loading?: boolean
  index?: number
}

function StatCard({ title, value, icon: Icon, color, subtitle, onClick, loading, index = 0 }: StatCardProps) {
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
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            {loading ? (
              <Skeleton className="h-8 w-20 mt-1" />
            ) : (
              <p className="text-xl md:text-2xl font-bold text-white mt-1">{value}</p>
            )}
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
            )}
          </div>
          <div
            className="p-3 rounded-lg transition-all duration-200"
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

// Loading skeleton
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

const SEVERITY_COLORS: Record<string, string> = {
  low: '#40c057',
  medium: '#fab005',
  high: '#ff922b',
  critical: '#fa5252',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)

  const canViewUsers = hasPermission('users', 'view')
  const canViewNodes = hasPermission('nodes', 'view')
  const canViewViolations = hasPermission('violations', 'view')
  const canViewAnalytics = hasPermission('analytics', 'view')
  const canViewSettings = hasPermission('settings', 'view')

  // Fetch data (only if permitted)
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

  // Refresh ALL dashboard queries
  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['overview'] })
    queryClient.invalidateQueries({ queryKey: ['violationStats'] })
    queryClient.invalidateQueries({ queryKey: ['trafficStats'] })
  }

  // Build violations chart from real stats
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

  // Build violations by action list
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
      {/* Page header */}
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

      {/* Error banner */}
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

      {/* Stats grid */}
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
                    <p className="text-xl md:text-2xl font-bold text-white mt-1">
                      {overview ? formatBytes(overview.total_traffic_bytes) : trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
                    </p>
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

      {/* Charts row — only if violations visible */}
      {canViewViolations && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Violations by severity */}
          <Card className="lg:col-span-2 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
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
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: 'rgba(22, 27, 34, 0.95)',
                        border: '1px solid rgba(72, 79, 88, 0.3)',
                        borderRadius: '8px',
                        backdropFilter: 'blur(12px)',
                      }}
                    />
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

          {/* Violations by action */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
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
        </div>
      )}

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Statistics summary */}
        {canViewAnalytics && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base md:text-lg">Сводка</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { label: 'Активные пользователи', value: overview?.active_users ?? '-' },
                  { label: 'Отключённые пользователи', value: overview?.disabled_users ?? '-' },
                  { label: 'Истёкшие подписки', value: overview?.expired_users ?? '-' },
                  { label: 'Пользователи онлайн', value: overview?.users_online ?? '-', color: 'text-green-400' },
                  { label: 'Хосты', value: overview?.total_hosts ?? '-' },
                  { label: 'Общий трафик', value: overview ? formatBytes(overview.total_traffic_bytes) : '-', color: 'text-violet-400' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-dark-400/10">
                    <span className="text-sm text-muted-foreground">{item.label}</span>
                    <span className={cn("text-sm font-semibold", item.color || "text-white")}>{item.value}</span>
                  </div>
                ))}
                {trafficStats && (
                  <>
                    <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
                      <span className="text-sm text-muted-foreground">Трафик сегодня</span>
                      <span className="text-sm text-cyan-400 font-semibold">{formatBytes(trafficStats.today_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
                      <span className="text-sm text-muted-foreground">Трафик за неделю</span>
                      <span className="text-sm text-cyan-400 font-semibold">{formatBytes(trafficStats.week_bytes)}</span>
                    </div>
                    <div className="flex items-center justify-between py-2">
                      <span className="text-sm text-muted-foreground">Трафик за месяц</span>
                      <span className="text-sm text-cyan-400 font-semibold">{formatBytes(trafficStats.month_bytes)}</span>
                    </div>
                  </>
                )}
              </div>
              {violationStats && violationStats.by_country && Object.keys(violationStats.by_country).length > 0 && (
                <>
                  <Separator className="mt-4" />
                  <div className="mt-4">
                    <h3 className="text-sm font-medium text-muted-foreground mb-2">Нарушения по странам</h3>
                    <div className="space-y-1">
                      {Object.entries(violationStats.by_country).slice(0, 5).map(([country, count]) => (
                        <div key={country} className="flex items-center justify-between">
                          <span className="text-xs text-dark-100">{country}</span>
                          <span className="text-xs text-white font-mono">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* Quick actions + System status */}
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base md:text-lg">Быстрые действия</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: Users, label: 'Пользователи', href: '/users', delay: '0.32s', perm: 'users' },
                { icon: Server, label: 'Ноды', href: '/nodes', delay: '0.36s', perm: 'nodes' },
                { icon: ShieldAlert, label: 'Нарушения', href: '/violations', delay: '0.4s', perm: 'violations' },
                { icon: Settings, label: 'Настройки', href: '/settings', delay: '0.44s', perm: 'settings' },
              ]
                .filter((item) => hasPermission(item.perm, 'view'))
                .map((item) => (
                  <Button
                    key={item.href}
                    variant="secondary"
                    onClick={() => navigate(item.href)}
                    className="py-8 flex flex-col items-center gap-2 hover:shadow-glow-teal animate-fade-in-up h-auto"
                    style={{ animationDelay: item.delay }}
                  >
                    <item.icon className="w-6 h-6" />
                    <span>{item.label}</span>
                  </Button>
                ))}
            </div>

            {/* System status */}
            <Separator className="mt-6" />
            <div className="mt-4">
              <h3 className="text-sm font-medium text-muted-foreground mb-3">Состояние системы</h3>
              <div className="space-y-2">
                {[
                  {
                    label: 'API',
                    ok: !!(overview && !overviewError),
                    loading: overviewLoading && canViewAnalytics,
                    text: !canViewAnalytics ? 'N/A' : overviewLoading ? 'Проверка...' : overview && !overviewError ? 'Работает' : 'Недоступен',
                  },
                  {
                    label: 'Ноды',
                    ok: !!(overview && overview.online_nodes > 0),
                    loading: false,
                    text: overview ? `${overview.online_nodes} онлайн` : '-',
                    warn: true,
                  },
                  {
                    label: 'База данных',
                    ok: violationStats !== undefined && !violationsError,
                    loading: violationsLoading && canViewViolations,
                    text: !canViewViolations ? 'N/A' : violationsLoading ? 'Проверка...' : violationStats !== undefined && !violationsError ? 'Доступна' : 'Недоступна',
                    warn: true,
                  },
                ].map((item) => (
                  <div key={item.label} className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{item.label}</span>
                    <span className="flex items-center gap-2 text-sm">
                      <Badge variant={item.ok ? "success" : item.warn ? "warning" : "destructive"} className="gap-1.5 px-2">
                        <span
                          className={cn("w-2 h-2 rounded-full", item.ok && "animate-pulse")}
                          style={{
                            background: item.ok ? '#0d9488' : item.warn ? '#fab005' : '#fa5252',
                            boxShadow: item.ok ? '0 0 6px rgba(13, 148, 136, 0.5)' : item.warn ? '0 0 6px rgba(250, 176, 5, 0.5)' : '0 0 6px rgba(250, 82, 82, 0.5)',
                          }}
                        />
                        {item.text}
                      </Badge>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
