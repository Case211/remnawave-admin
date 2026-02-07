import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  HiUsers,
  HiServer,
  HiShieldExclamation,
  HiStatusOnline,
  HiRefresh,
  HiExternalLink,
  HiCog,
  HiTrendingUp,
} from 'react-icons/hi'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import client from '../api/client'

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
    <div
      className={`card group animate-fade-in-up ${onClick ? 'cursor-pointer glow-teal-hover' : ''}`}
      onClick={onClick}
      style={{ transition: 'all 0.2s ease', animationDelay: `${index * 0.07}s` }}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-dark-200">{title}</p>
          {loading ? (
            <div className="h-8 w-20 skeleton rounded mt-1"></div>
          ) : (
            <p className="text-xl md:text-2xl font-bold text-white mt-1">{value}</p>
          )}
          {subtitle && (
            <p className="text-xs text-dark-200 mt-1">{subtitle}</p>
          )}
        </div>
        <div
          className="p-3 rounded-lg transition-all duration-200"
          style={{
            background: cfg.bg,
            border: `1px solid ${cfg.border}`,
          }}
        >
          <Icon className={`w-6 h-6 ${cfg.text}`} />
        </div>
      </div>
      {onClick && (
        <div className="mt-3 pt-3 border-t border-dark-400/10">
          <span className="text-xs text-dark-200 group-hover:text-primary-400 flex items-center gap-1 transition-colors duration-200">
            Подробнее <HiExternalLink className="w-3 h-3" />
          </span>
        </div>
      )}
    </div>
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
        ></div>
        <span className="text-sm text-dark-200">Загрузка...</span>
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

  // Fetch data
  const { data: overview, isLoading: overviewLoading, isError: overviewError } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: 30000,
  })

  const { data: violationStats, isLoading: violationsLoading, isError: violationsError } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
    refetchInterval: 30000,
  })

  const { data: trafficStats, isLoading: trafficLoading } = useQuery({
    queryKey: ['trafficStats'],
    queryFn: fetchTrafficStats,
    refetchInterval: 60000,
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

  // Build traffic subtitle from trafficStats
  const trafficSubtitle = trafficStats
    ? `Сегодня: ${formatBytes(trafficStats.today_bytes)}, за неделю: ${formatBytes(trafficStats.week_bytes)}`
    : undefined

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Панель управления</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Обзор системы Remnawave</p>
        </div>
        <button
          onClick={handleRefreshAll}
          className="btn-secondary flex items-center gap-2 self-start sm:self-auto"
          disabled={isLoading}
        >
          <HiRefresh className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Обновить</span>
        </button>
      </div>

      {/* Error banner */}
      {(overviewError || violationsError) && (
        <div className="card border border-red-500/30 bg-red-500/10 animate-fade-in-down">
          <div className="flex items-center justify-between">
            <p className="text-red-400 text-sm">
              Ошибка загрузки данных. Некоторые показатели могут быть недоступны.
            </p>
            <button onClick={handleRefreshAll} className="btn-secondary text-sm">
              Повторить
            </button>
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Всего пользователей"
          value={overview?.total_users != null ? overview.total_users.toLocaleString() : '-'}
          icon={HiUsers}
          color="cyan"
          subtitle={overview ? `${overview.active_users} активных, ${overview.expired_users} истекших` : undefined}
          onClick={() => navigate('/users')}
          loading={overviewLoading}
          index={0}
        />
        <StatCard
          title="Активные ноды"
          value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
          icon={HiServer}
          color="green"
          subtitle={overview ? `${overview.offline_nodes} офлайн, ${overview.disabled_nodes} отключ.${overview.users_online ? `, ${overview.users_online} онлайн` : ''}` : undefined}
          onClick={() => navigate('/nodes')}
          loading={overviewLoading}
          index={1}
        />
        <StatCard
          title="Нарушения"
          value={overview ? `${overview.violations_today}` : '-'}
          icon={HiShieldExclamation}
          color={overview && overview.violations_today > 0 ? 'red' : 'yellow'}
          subtitle={overview ? `Сегодня: ${overview.violations_today}, за неделю: ${overview.violations_week}` : undefined}
          onClick={() => navigate('/violations')}
          loading={overviewLoading}
          index={2}
        />
        <StatCard
          title="Общий трафик"
          value={overview ? formatBytes(overview.total_traffic_bytes) : trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
          icon={HiTrendingUp}
          color="violet"
          subtitle={trafficSubtitle}
          loading={overviewLoading && trafficLoading}
          index={3}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Violations by severity */}
        <div className="card lg:col-span-2 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <h2 className="text-base md:text-lg font-semibold text-white">Нарушения по уровню (за 7 дней)</h2>
            {violationStats && (
              <span className="text-xs text-dark-200">
                Всего: {violationStats.total} | Уникальных: {violationStats.unique_users}
              </span>
            )}
          </div>
          {violationsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={violationsChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(72, 79, 88, 0.3)" />
                <XAxis type="number" stroke="#8b949e" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#8b949e" fontSize={12} width={100} />
                <Tooltip
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
        </div>

        {/* Violations by action */}
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">По рекомендации</h2>
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
              <span className="text-dark-200 text-sm">Нет данных</span>
            </div>
          )}
          {violationStats && violationStats.max_score > 0 && (
            <div className="mt-4 pt-4 border-t border-dark-400/10 space-y-1">
              <div className="flex justify-between text-xs text-dark-200">
                <span>Средний скор</span>
                <span className="text-white">{violationStats.avg_score.toFixed(1)}</span>
              </div>
              <div className="flex justify-between text-xs text-dark-200">
                <span>Максимальный скор</span>
                <span className="text-white">{violationStats.max_score.toFixed(1)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Statistics summary */}
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">Сводка</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Активные пользователи</span>
              <span className="text-sm text-white font-semibold">{overview?.active_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Отключённые пользователи</span>
              <span className="text-sm text-white font-semibold">{overview?.disabled_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Истёкшие подписки</span>
              <span className="text-sm text-white font-semibold">{overview?.expired_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Пользователи онлайн</span>
              <span className="text-sm text-green-400 font-semibold">{overview?.users_online ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Хосты</span>
              <span className="text-sm text-white font-semibold">{overview?.total_hosts ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
              <span className="text-sm text-dark-200">Общий трафик</span>
              <span className="text-sm text-violet-400 font-semibold">
                {overview ? formatBytes(overview.total_traffic_bytes) : '-'}
              </span>
            </div>
            {trafficStats && (
              <>
                <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
                  <span className="text-sm text-dark-200">Трафик сегодня</span>
                  <span className="text-sm text-cyan-400 font-semibold">
                    {formatBytes(trafficStats.today_bytes)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-dark-400/10">
                  <span className="text-sm text-dark-200">Трафик за неделю</span>
                  <span className="text-sm text-cyan-400 font-semibold">
                    {formatBytes(trafficStats.week_bytes)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm text-dark-200">Трафик за месяц</span>
                  <span className="text-sm text-cyan-400 font-semibold">
                    {formatBytes(trafficStats.month_bytes)}
                  </span>
                </div>
              </>
            )}
          </div>
          {violationStats && violationStats.by_country && Object.keys(violationStats.by_country).length > 0 && (
            <div className="mt-4 pt-4 border-t border-dark-400/10">
              <h3 className="text-sm font-medium text-dark-200 mb-2">Нарушения по странам</h3>
              <div className="space-y-1">
                {Object.entries(violationStats.by_country).slice(0, 5).map(([country, count]) => (
                  <div key={country} className="flex items-center justify-between">
                    <span className="text-xs text-dark-100">{country}</span>
                    <span className="text-xs text-white font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">Быстрые действия</h2>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => navigate('/users')}
              className="btn-secondary py-4 flex flex-col items-center gap-2 glow-teal-hover animate-fade-in-up"
              style={{ animationDelay: '0.32s' }}
            >
              <HiUsers className="w-6 h-6" />
              <span>Пользователи</span>
            </button>
            <button
              onClick={() => navigate('/nodes')}
              className="btn-secondary py-4 flex flex-col items-center gap-2 glow-teal-hover animate-fade-in-up"
              style={{ animationDelay: '0.36s' }}
            >
              <HiServer className="w-6 h-6" />
              <span>Ноды</span>
            </button>
            <button
              onClick={() => navigate('/violations')}
              className="btn-secondary py-4 flex flex-col items-center gap-2 glow-teal-hover animate-fade-in-up"
              style={{ animationDelay: '0.4s' }}
            >
              <HiShieldExclamation className="w-6 h-6" />
              <span>Нарушения</span>
            </button>
            <button
              onClick={() => navigate('/settings')}
              className="btn-secondary py-4 flex flex-col items-center gap-2 glow-teal-hover animate-fade-in-up"
              style={{ animationDelay: '0.44s' }}
            >
              <HiCog className="w-6 h-6" />
              <span>Настройки</span>
            </button>
          </div>

          {/* System status */}
          <div className="mt-6 pt-4 border-t border-dark-400/10">
            <h3 className="text-sm font-medium text-dark-200 mb-3">Состояние системы</h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-200">API</span>
                <span className="flex items-center gap-2 text-sm">
                  <span
                    className={`w-2 h-2 rounded-full ${overview && !overviewError ? 'animate-pulse' : ''}`}
                    style={{
                      background: overview && !overviewError ? '#0d9488' : '#fa5252',
                      boxShadow: overview && !overviewError ? '0 0 6px rgba(13, 148, 136, 0.5)' : '0 0 6px rgba(250, 82, 82, 0.5)',
                    }}
                  ></span>
                  <span className={overview && !overviewError ? 'text-green-400' : 'text-red-400'}>
                    {overviewLoading ? 'Проверка...' : overview && !overviewError ? 'Работает' : 'Недоступен'}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-200">Ноды</span>
                <span className="flex items-center gap-2 text-sm">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: overview && overview.online_nodes > 0 ? '#0d9488' : '#fab005',
                      boxShadow: overview && overview.online_nodes > 0 ? '0 0 6px rgba(13, 148, 136, 0.5)' : '0 0 6px rgba(250, 176, 5, 0.5)',
                    }}
                  ></span>
                  <span className={overview && overview.online_nodes > 0 ? 'text-green-400' : 'text-yellow-400'}>
                    {overview ? `${overview.online_nodes} онлайн` : '-'}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-200">База данных</span>
                <span className="flex items-center gap-2 text-sm">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: violationStats !== undefined && !violationsError ? '#0d9488' : '#fab005',
                      boxShadow: violationStats !== undefined && !violationsError ? '0 0 6px rgba(13, 148, 136, 0.5)' : '0 0 6px rgba(250, 176, 5, 0.5)',
                    }}
                  ></span>
                  <span className={violationStats !== undefined && !violationsError ? 'text-green-400' : 'text-yellow-400'}>
                    {violationsLoading ? 'Проверка...' : violationStats !== undefined && !violationsError ? 'Доступна' : 'Недоступна'}
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
