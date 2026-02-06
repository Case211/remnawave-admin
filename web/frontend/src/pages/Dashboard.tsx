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
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import client from '../api/client'

// Types
interface OverviewStats {
  total_users: number
  active_users: number
  disabled_users: number
  expired_users: number
  total_nodes: number
  online_nodes: number
  offline_nodes: number
  total_hosts: number
  violations_today: number
  violations_week: number
}

interface ViolationStats {
  total: number
  pending: number
  resolved: number
  by_severity: Record<string, number>
  by_action: Record<string, number>
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

export default function Dashboard() {
  const navigate = useNavigate()

  // Fetch data
  const { data: overview, isLoading: overviewLoading, refetch: refetchOverview } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
    refetchInterval: 30000, // Обновлять каждые 30 сек
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

  // Mock data for charts (will be replaced with real time-series data)
  const trafficChartData = [
    { name: 'Пн', upload: 4000, download: 2400 },
    { name: 'Вт', upload: 3000, download: 1398 },
    { name: 'Ср', upload: 2000, download: 9800 },
    { name: 'Чт', upload: 2780, download: 3908 },
    { name: 'Пт', upload: 1890, download: 4800 },
    { name: 'Сб', upload: 2390, download: 3800 },
    { name: 'Вс', upload: 3490, download: 4300 },
  ]

  const violationsChartData = violationStats?.by_severity
    ? Object.entries(violationStats.by_severity).map(([name, value]) => ({
        name: name === 'low' ? 'Низкий' : name === 'medium' ? 'Средний' : name === 'high' ? 'Высокий' : 'Критический',
        value,
      }))
    : [
        { name: 'Низкий', value: 0 },
        { name: 'Средний', value: 0 },
        { name: 'Высокий', value: 0 },
        { name: 'Критический', value: 0 },
      ]

  // Recent activity (mock for now, will come from WebSocket)
  const recentActivity = [
    { type: 'connection', message: 'Новое подключение из Москвы', time: '2 мин назад' },
    { type: 'violation', message: 'Обнаружено нарушение (score: 78)', time: '5 мин назад' },
    { type: 'block', message: 'Пользователь заблокирован (авто, 24ч)', time: '12 мин назад' },
    { type: 'node', message: 'Нода DE-1 перезапущена', time: '1 час назад' },
  ]

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
          subtitle={overview ? `${overview.active_users} активных` : undefined}
          onClick={() => navigate('/users')}
          loading={overviewLoading}
        />
        <StatCard
          title="Активные ноды"
          value={overview ? `${overview.online_nodes}/${overview.total_nodes}` : '-'}
          icon={HiServer}
          color="green"
          subtitle={overview?.offline_nodes ? `${overview.offline_nodes} офлайн` : 'Все онлайн'}
          onClick={() => navigate('/nodes')}
          loading={overviewLoading}
        />
        <StatCard
          title="Нарушения сегодня"
          value={overview?.violations_today ?? violationStats?.total ?? 0}
          icon={HiShieldExclamation}
          color={violationStats && violationStats.pending > 0 ? 'red' : 'yellow'}
          subtitle={violationStats?.pending ? `${violationStats.pending} ожидают` : undefined}
          onClick={() => navigate('/violations')}
          loading={violationsLoading}
        />
        <StatCard
          title="Общий трафик"
          value={trafficStats ? formatBytes(trafficStats.total_bytes) : '-'}
          icon={HiStatusOnline}
          color="purple"
          subtitle={trafficStats?.today_bytes ? `Сегодня: ${formatBytes(trafficStats.today_bytes)}` : undefined}
          loading={trafficLoading}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Traffic chart - takes 2 columns */}
        <div className="card lg:col-span-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <h2 className="text-base md:text-lg font-semibold text-white">Трафик за неделю</h2>
            <div className="flex items-center gap-4 text-xs">
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-primary-500"></span>
                Загрузка
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-green-500"></span>
                Скачивание
              </span>
            </div>
          </div>
          {trafficLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={trafficChartData}>
                <defs>
                  <linearGradient id="colorUpload" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorDownload" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="upload"
                  stroke="#6366f1"
                  fillOpacity={1}
                  fill="url(#colorUpload)"
                />
                <Area
                  type="monotone"
                  dataKey="download"
                  stroke="#22c55e"
                  fillOpacity={1}
                  fill="url(#colorDownload)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Violations by severity */}
        <div className="card">
          <h2 className="text-base md:text-lg font-semibold text-white mb-4">Нарушения по уровню</h2>
          {violationsLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={violationsChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis type="number" stroke="#9ca3af" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#9ca3af" fontSize={12} width={80} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="value" fill="#f59e0b" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent activity */}
        <div className="card">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-4">
            <h2 className="text-base md:text-lg font-semibold text-white">Последняя активность</h2>
            <span className="text-xs text-gray-500">Обновляется в реальном времени</span>
          </div>
          <div className="space-y-3">
            {recentActivity.map((item, index) => (
              <div
                key={index}
                className="flex items-center gap-3 py-2 border-b border-dark-700 last:border-0"
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    item.type === 'connection'
                      ? 'bg-green-500'
                      : item.type === 'violation'
                        ? 'bg-yellow-500'
                        : item.type === 'block'
                          ? 'bg-red-500'
                          : 'bg-blue-500'
                  }`}
                ></span>
                <span className="flex-1 text-sm text-gray-300">{item.message}</span>
                <span className="text-xs text-gray-500">{item.time}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 pt-4 border-t border-dark-700">
            <button
              onClick={() => navigate('/violations')}
              className="text-sm text-primary-400 hover:text-primary-300 flex items-center gap-1"
            >
              Показать все нарушения <HiExternalLink className="w-4 h-4" />
            </button>
          </div>
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
                  <span className="w-2 h-2 rounded-full bg-green-500"></span>
                  <span className="text-green-400">Работает</span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">WebSocket</span>
                <span className="flex items-center gap-2 text-sm">
                  <span className="w-2 h-2 rounded-full bg-green-500"></span>
                  <span className="text-green-400">Подключен</span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">База данных</span>
                <span className="flex items-center gap-2 text-sm">
                  <span className="w-2 h-2 rounded-full bg-green-500"></span>
                  <span className="text-green-400">Доступна</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
