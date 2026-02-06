import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  HiUsers,
  HiServer,
  HiShieldExclamation,
  HiStatusOnline,
  HiRefresh,
  HiExternalLink,
  HiCog,
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
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// Stat card component
interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  color: 'blue' | 'green' | 'yellow' | 'red' | 'purple'
  subtitle?: string
  onClick?: () => void
  loading?: boolean
}

function StatCard({ title, value, icon: Icon, color, subtitle, onClick, loading }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400 group-hover:bg-blue-500/20',
    green: 'bg-green-500/10 text-green-400 group-hover:bg-green-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-400 group-hover:bg-yellow-500/20',
    red: 'bg-red-500/10 text-red-400 group-hover:bg-red-500/20',
    purple: 'bg-purple-500/10 text-purple-400 group-hover:bg-purple-500/20',
  }

  return (
    <div
      className={`card group ${onClick ? 'cursor-pointer hover:border-dark-500 transition-colors' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          {loading ? (
            <div className="h-8 w-20 bg-dark-700 animate-pulse rounded mt-1"></div>
          ) : (
            <p className="text-xl md:text-2xl font-bold text-white mt-1">{value}</p>
          )}
          {subtitle && (
            <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
          )}
        </div>
        <div className={`p-3 rounded-lg transition-colors ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
      {onClick && (
        <div className="mt-3 pt-3 border-t border-dark-700">
          <span className="text-xs text-gray-500 group-hover:text-primary-400 flex items-center gap-1">
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
        <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
        <span className="text-sm text-gray-500">Загрузка...</span>
      </div>
    </div>
  )
}

const SEVERITY_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#f97316',
  critical: '#ef4444',
}

export default function Dashboard() {
  const navigate = useNavigate()

  // Fetch data
  const { data: overview, isLoading: overviewLoading, refetch: refetchOverview } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: 30000,
  })

  const { data: violationStats, isLoading: violationsLoading } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
    refetchInterval: 30000,
  })

  const { data: trafficStats, isLoading: trafficLoading } = useQuery({
    queryKey: ['trafficStats'],
    queryFn: fetchTrafficStats,
    refetchInterval: 60000,
  })

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
          <p className="text-gray-400 mt-1 text-sm md:text-base">Обзор системы Remnawave</p>
        </div>
        <button
          onClick={() => refetchOverview()}
          className="btn-secondary flex items-center gap-2 self-start sm:self-auto"
          disabled={isLoading}
        >
          <HiRefresh className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Обновить</span>
        </button>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Всего пользователей"
          value={overview?.total_users.toLocaleString() ?? '-'}
          icon={HiUsers}
          color="blue"
          subtitle={overview ? `${overview.active_users} активных, ${overview.expired_users} истекших` : undefined}
          onClick={() => navigate('/users')}
          loading={overviewLoading}
        />
        <StatCard
          title="Активные ноды"
          value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
          icon={HiServer}
          color="green"
          subtitle={overview ? `${overview.offline_nodes} офлайн, ${overview.disabled_nodes} отключ.${overview.users_online ? `, ${overview.users_online} онлайн` : ''}` : undefined}
          onClick={() => navigate('/nodes')}
          loading={overviewLoading}
        />
        <StatCard
          title="Нарушения"
          value={overview?.violations_today ?? 0}
          icon={HiShieldExclamation}
          color={overview && overview.violations_today > 0 ? 'red' : 'yellow'}
          subtitle={overview ? `Сегодня: ${overview.violations_today}, за неделю: ${overview.violations_week}` : undefined}
          onClick={() => navigate('/violations')}
          loading={overviewLoading}
        />
        <StatCard
          title="Общий трафик"
          value={overview ? formatBytes(overview.total_traffic_bytes) : trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
          icon={HiStatusOnline}
          color="purple"
          loading={overviewLoading && trafficLoading}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Violations by severity */}
        <div className="card lg:col-span-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <h2 className="text-base md:text-lg font-semibold text-white">Нарушения по уровню (за 7 дней)</h2>
            {violationStats && (
              <span className="text-xs text-gray-500">
                Всего: {violationStats.total} | Уникальных: {violationStats.unique_users}
              </span>
            )}
          </div>
          {violationsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={violationsChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis type="number" stroke="#9ca3af" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#9ca3af" fontSize={12} width={100} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {violationsChartData.map((entry) => (
                    <Cell key={entry.key} fill={SEVERITY_COLORS[entry.key] || '#f59e0b'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Violations by action */}
        <div className="card">
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">По рекомендации</h2>
          {violationsLoading ? (
            <ChartSkeleton />
          ) : actionChartData.length > 0 ? (
            <div className="space-y-3">
              {actionChartData.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">{item.name}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-dark-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary-500 rounded-full"
                        style={{
                          width: `${violationStats && violationStats.total > 0 ? (item.value / violationStats.total) * 100 : 0}%`
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
              <span className="text-gray-500 text-sm">Нет данных</span>
            </div>
          )}
          {violationStats && violationStats.max_score > 0 && (
            <div className="mt-4 pt-4 border-t border-dark-700 space-y-1">
              <div className="flex justify-between text-xs text-gray-400">
                <span>Средний скор</span>
                <span className="text-white">{violationStats.avg_score.toFixed(1)}</span>
              </div>
              <div className="flex justify-between text-xs text-gray-400">
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
        <div className="card">
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">Сводка</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-dark-700">
              <span className="text-sm text-gray-400">Активные пользователи</span>
              <span className="text-sm text-white font-semibold">{overview?.active_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-700">
              <span className="text-sm text-gray-400">Отключённые пользователи</span>
              <span className="text-sm text-white font-semibold">{overview?.disabled_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-700">
              <span className="text-sm text-gray-400">Истёкшие подписки</span>
              <span className="text-sm text-white font-semibold">{overview?.expired_users ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-700">
              <span className="text-sm text-gray-400">Пользователи онлайн</span>
              <span className="text-sm text-green-400 font-semibold">{overview?.users_online ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-dark-700">
              <span className="text-sm text-gray-400">Хосты</span>
              <span className="text-sm text-white font-semibold">{overview?.total_hosts ?? '-'}</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-sm text-gray-400">Общий трафик</span>
              <span className="text-sm text-purple-400 font-semibold">
                {overview ? formatBytes(overview.total_traffic_bytes) : '-'}
              </span>
            </div>
          </div>
          {violationStats && violationStats.by_country && Object.keys(violationStats.by_country).length > 0 && (
            <div className="mt-4 pt-4 border-t border-dark-700">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Нарушения по странам</h3>
              <div className="space-y-1">
                {Object.entries(violationStats.by_country).slice(0, 5).map(([country, count]) => (
                  <div key={country} className="flex items-center justify-between">
                    <span className="text-xs text-gray-300">{country}</span>
                    <span className="text-xs text-white font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="card">
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">Быстрые действия</h2>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => navigate('/users')}
              className="btn-secondary py-4 flex flex-col items-center gap-2"
            >
              <HiUsers className="w-6 h-6" />
              <span>Пользователи</span>
            </button>
            <button
              onClick={() => navigate('/nodes')}
              className="btn-secondary py-4 flex flex-col items-center gap-2"
            >
              <HiServer className="w-6 h-6" />
              <span>Ноды</span>
            </button>
            <button
              onClick={() => navigate('/violations')}
              className="btn-secondary py-4 flex flex-col items-center gap-2"
            >
              <HiShieldExclamation className="w-6 h-6" />
              <span>Нарушения</span>
            </button>
            <button
              onClick={() => navigate('/settings')}
              className="btn-secondary py-4 flex flex-col items-center gap-2"
            >
              <HiCog className="w-6 h-6" />
              <span>Настройки</span>
            </button>
          </div>

          {/* System status */}
          <div className="mt-6 pt-4 border-t border-dark-700">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Состояние системы</h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">API</span>
                <span className="flex items-center gap-2 text-sm">
                  <span className={`w-2 h-2 rounded-full ${overview ? 'bg-green-500' : 'bg-red-500'}`}></span>
                  <span className={overview ? 'text-green-400' : 'text-red-400'}>
                    {overview ? 'Работает' : 'Недоступен'}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Ноды</span>
                <span className="flex items-center gap-2 text-sm">
                  <span className={`w-2 h-2 rounded-full ${overview && overview.online_nodes > 0 ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
                  <span className={overview && overview.online_nodes > 0 ? 'text-green-400' : 'text-yellow-400'}>
                    {overview ? `${overview.online_nodes} онлайн` : '-'}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">База данных</span>
                <span className="flex items-center gap-2 text-sm">
                  <span className={`w-2 h-2 rounded-full ${violationStats !== undefined ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
                  <span className={violationStats !== undefined ? 'text-green-400' : 'text-yellow-400'}>
                    {violationStats !== undefined ? 'Доступна' : 'Проверка...'}
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
