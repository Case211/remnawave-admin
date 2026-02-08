import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import client from '../api/client'

interface UserDetailData {
  uuid: string
  short_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  status: string
  expire_at: string | null
  traffic_limit_bytes: number | null
  used_traffic_bytes: number
  lifetime_used_traffic_bytes: number
  hwid_device_limit: number
  created_at: string
  online_at: string | null
  subscription_uuid: string | null
  subscription_url: string | null
  sub_last_user_agent: string | null
  // Anti-abuse
  trust_score: number | null
  violation_count_30d: number
  active_connections: number
  unique_ips_24h: number
}

interface HwidDevice {
  hwid: string
  platform: string | null
  os_version: string | null
  device_model: string | null
  app_version: string | null
  user_agent: string | null
  created_at: string | null
  updated_at: string | null
}

interface Violation {
  id: number
  score: number
  recommended_action: string
  detected_at: string
  severity: string
}

interface EditFormData {
  status: string
  traffic_limit_bytes: number | null
  traffic_limit_gb: string
  is_unlimited: boolean
  expire_at: string
  hwid_device_limit: string
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

function getStatusBadge(status: string): { label: string; color: string } {
  const s = status.toLowerCase()
  switch (s) {
    case 'active': return { label: 'Активен', color: 'bg-green-500' }
    case 'disabled': return { label: 'Отключён', color: 'bg-red-500' }
    case 'expired': return { label: 'Истёк', color: 'bg-yellow-500' }
    case 'limited': return { label: 'Ограничен', color: 'bg-orange-500' }
    default: return { label: status, color: 'bg-gray-500' }
  }
}

function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'critical': return 'text-red-400 bg-red-500/10'
    case 'high': return 'text-orange-400 bg-orange-500/10'
    case 'medium': return 'text-yellow-400 bg-yellow-500/10'
    default: return 'text-dark-200 bg-gray-500/10'
  }
}

/** Parse User-Agent string into human-readable OS + app name */
function parseUserAgent(ua: string | null): { os: string; app: string; raw: string } {
  if (!ua) return { os: '—', app: '—', raw: '—' }

  let os = 'Неизвестно'
  let app = 'Неизвестно'

  // Detect OS
  if (/windows/i.test(ua)) {
    const ver = ua.match(/Windows NT (\d+\.\d+)/i)
    const winVer: Record<string, string> = { '10.0': '10/11', '6.3': '8.1', '6.2': '8', '6.1': '7' }
    os = ver ? `Windows ${winVer[ver[1]] || ver[1]}` : 'Windows'
  } else if (/android/i.test(ua)) {
    const ver = ua.match(/Android[\s/]?([\d.]+)/i)
    os = ver ? `Android ${ver[1]}` : 'Android'
  } else if (/iPhone|iPad|iOS/i.test(ua)) {
    const ver = ua.match(/OS[\s_]([\d_]+)/i)
    os = ver ? `iOS ${ver[1].replace(/_/g, '.')}` : 'iOS'
  } else if (/Mac\s?OS/i.test(ua)) {
    os = 'macOS'
  } else if (/Linux/i.test(ua)) {
    os = 'Linux'
  }

  // Detect app/client
  if (/v2rayN/i.test(ua)) app = 'v2rayN'
  else if (/v2rayNG/i.test(ua)) app = 'v2rayNG'
  else if (/Hiddify/i.test(ua)) app = 'Hiddify'
  else if (/Streisand/i.test(ua)) app = 'Streisand'
  else if (/FoXray/i.test(ua)) app = 'FoXray'
  else if (/ShadowRocket/i.test(ua)) app = 'Shadowrocket'
  else if (/Shadowrocket/i.test(ua)) app = 'Shadowrocket'
  else if (/Clash/i.test(ua)) app = ua.match(/Clash[\w.]*/i)?.[0] || 'Clash'
  else if (/Sing-?Box/i.test(ua)) app = 'sing-box'
  else if (/NekoBox/i.test(ua)) app = 'NekoBox'
  else if (/NekoRay/i.test(ua)) app = 'NekoRay'
  else if (/V2Box/i.test(ua)) app = 'V2Box'
  else if (/Loon/i.test(ua)) app = 'Loon'
  else if (/Surge/i.test(ua)) app = 'Surge'
  else if (/Quantumult/i.test(ua)) app = 'Quantumult X'
  else if (/stash/i.test(ua)) app = 'Stash'

  // Try extracting version from app name
  const verMatch = ua.match(new RegExp(`${app}[/\\s]?([\\d.]+)`, 'i'))
  if (verMatch && verMatch[1]) app = `${app} ${verMatch[1]}`

  return { os, app, raw: ua }
}

function getPlatformInfo(platform: string | null): { icon: string; label: string } {
  const p = (platform || '').toLowerCase()
  if (p.includes('windows') || p === 'win') return { icon: '🖥️', label: 'Windows' }
  if (p.includes('android')) return { icon: '📱', label: 'Android' }
  if (p.includes('ios') || p.includes('iphone') || p.includes('ipad')) return { icon: '📱', label: 'iOS' }
  if (p.includes('macos') || p.includes('mac') || p.includes('darwin')) return { icon: '💻', label: 'macOS' }
  if (p.includes('linux')) return { icon: '🐧', label: 'Linux' }
  return { icon: '📟', label: platform || 'Неизвестно' }
}

function bytesToGb(bytes: number | null): string {
  if (!bytes) return ''
  return (bytes / (1024 * 1024 * 1024)).toFixed(2)
}

function gbToBytes(gb: string): number | null {
  const val = parseFloat(gb)
  if (isNaN(val) || val <= 0) return null
  return Math.round(val * 1024 * 1024 * 1024)
}

function formatDateForInput(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  // Format as YYYY-MM-DDTHH:mm for datetime-local input
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

interface TrafficStats {
  used_bytes: number
  lifetime_bytes: number
  traffic_limit_bytes: number | null
  period: string
  period_bytes: number
  nodes_traffic: {
    node_name: string
    node_uuid: string
    total_bytes: number
  }[]
}

type TrafficPeriod = 'current' | 'lifetime' | 'today' | 'week' | 'month' | '3month' | '6month' | 'year' | 'nodes'

const TRAFFIC_PERIODS: { key: TrafficPeriod; label: string }[] = [
  { key: 'current', label: 'Текущий' },
  { key: 'lifetime', label: 'Всё время' },
  { key: 'today', label: 'Сутки' },
  { key: 'week', label: 'Неделя' },
  { key: 'month', label: 'Месяц' },
  { key: '3month', label: '3 месяца' },
  { key: '6month', label: '6 месяцев' },
  { key: 'year', label: 'Год' },
  { key: 'nodes', label: 'По нодам' },
]

// API period keys (sent to backend)
const API_PERIODS: TrafficPeriod[] = ['today', 'week', 'month', '3month', '6month', 'year']

function TrafficBlock({ user, trafficPercent }: { user: UserDetailData; trafficPercent: number }) {
  const [period, setPeriod] = useState<TrafficPeriod>('current')
  const [nodePeriod, setNodePeriod] = useState<string>('today')

  // Fetch per-user traffic stats from Remnawave API for period-based views
  const apiPeriod = period === 'nodes' ? nodePeriod : (API_PERIODS.includes(period) ? period : null)

  const { data: trafficStats, isFetching } = useQuery<TrafficStats>({
    queryKey: ['user-traffic-stats', user.uuid, apiPeriod],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (apiPeriod) params.period = apiPeriod
      const response = await client.get(`/users/${user.uuid}/traffic-stats`, { params })
      return response.data
    },
    enabled: !!user.uuid && (period !== 'current' && period !== 'lifetime'),
    staleTime: 30_000,
  })

  const isUnlimited = !user.traffic_limit_bytes

  // Get display value and label based on current period
  const getDisplay = (): { value: number; label: string } => {
    switch (period) {
      case 'current':
        return { value: user.used_traffic_bytes, label: 'Текущий период' }
      case 'lifetime':
        return { value: user.lifetime_used_traffic_bytes || user.used_traffic_bytes, label: 'За всё время' }
      default:
        if (trafficStats && API_PERIODS.includes(period)) {
          return {
            value: trafficStats.period_bytes,
            label: TRAFFIC_PERIODS.find(p => p.key === period)?.label || '',
          }
        }
        return { value: user.used_traffic_bytes, label: 'Использовано' }
    }
  }

  const displayed = getDisplay()
  const showLoadingOverlay = isFetching && period !== 'current'

  const NODE_PERIOD_OPTIONS = [
    { key: 'today', label: 'Сутки' },
    { key: 'week', label: 'Неделя' },
    { key: 'month', label: 'Месяц' },
    { key: '3month', label: '3 мес.' },
    { key: '6month', label: '6 мес.' },
    { key: 'year', label: 'Год' },
  ]

  return (
    <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <h2 className="text-base md:text-lg font-semibold text-white mb-4">Трафик</h2>

      {/* Period selector */}
      <div className="flex flex-wrap gap-1 mb-4">
        {TRAFFIC_PERIODS.map((p) => (
          <button
            key={p.key}
            onClick={() => setPeriod(p.key)}
            className={`px-2.5 py-1 text-xs rounded-md font-medium transition-all ${
              period === p.key
                ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30'
                : 'text-dark-200 hover:text-white hover:bg-dark-700/50 border border-transparent'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {period === 'nodes' ? (
        /* Per-node breakdown */
        <div className="space-y-3">
          {/* Node period sub-filter */}
          <div className="flex flex-wrap gap-1">
            {NODE_PERIOD_OPTIONS.map((p) => (
              <button
                key={p.key}
                onClick={() => setNodePeriod(p.key)}
                className={`px-2 py-0.5 text-[11px] rounded font-medium transition-all ${
                  nodePeriod === p.key
                    ? 'bg-dark-600 text-white'
                    : 'text-dark-300 hover:text-dark-100 hover:bg-dark-700/50'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Node list */}
          <div className="space-y-2 relative">
            {showLoadingOverlay && (
              <div className="absolute inset-0 bg-dark-800/50 rounded-lg flex items-center justify-center z-10">
                <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
              </div>
            )}
            {trafficStats?.nodes_traffic && trafficStats.nodes_traffic.length > 0 ? (
              <>
                {trafficStats.nodes_traffic.map((node) => (
                  <div
                    key={node.node_uuid}
                    className="flex items-center justify-between p-2.5 bg-dark-700/40 rounded-lg border border-dark-600/20"
                  >
                    <span className="text-sm text-dark-100 truncate flex-1 mr-3">{node.node_name}</span>
                    <span className="text-white font-medium text-sm">{formatBytes(node.total_bytes)}</span>
                  </div>
                ))}
                {/* Total */}
                <div className="flex items-center justify-between p-2.5 bg-dark-600/30 rounded-lg border border-primary-500/20">
                  <span className="text-sm text-primary-400 font-medium">Итого</span>
                  <span className="text-sm text-white font-bold">
                    {formatBytes(trafficStats.nodes_traffic.reduce((sum, n) => sum + n.total_bytes, 0))}
                  </span>
                </div>
              </>
            ) : (
              <div className="text-center py-6 text-dark-300 text-sm">
                {isFetching ? 'Загрузка...' : 'Нет данных о трафике по нодам за этот период'}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Traffic bar and stats */
        <div className="space-y-4 relative">
          {showLoadingOverlay && (
            <div className="absolute inset-0 bg-dark-800/50 rounded-lg flex items-center justify-center z-10">
              <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          <div>
            {isUnlimited ? (
              <>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-dark-200">{displayed.label}</span>
                  <span className="text-primary-400 text-xs sm:text-sm font-medium">Безлимит</span>
                </div>
                <div className="relative w-full h-7 rounded-full overflow-hidden bg-gradient-to-r from-primary-600/30 to-cyan-600/30 border border-primary-500/20">
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-sm font-medium text-primary-200">
                      {formatBytes(displayed.value)}{period === 'current' ? ' / ∞' : ''}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-dark-200">{displayed.label}</span>
                  <span className="text-white text-xs sm:text-sm">
                    {formatBytes(displayed.value)}{period === 'current' ? ` / ${formatBytes(user.traffic_limit_bytes!)}` : ''}
                  </span>
                </div>
                {period === 'current' ? (
                  <>
                    <div className="w-full bg-dark-600 rounded-full h-2.5">
                      <div
                        className={`h-2.5 rounded-full transition-all ${
                          trafficPercent > 90 ? 'bg-red-500' : trafficPercent > 70 ? 'bg-yellow-500' : 'bg-primary-500'
                        }`}
                        style={{ width: `${trafficPercent}%` }}
                      />
                    </div>
                    <p className="text-xs text-dark-300 mt-1">
                      {trafficPercent.toFixed(1)}% использовано
                    </p>
                  </>
                ) : (
                  <div className="relative w-full h-7 rounded-full overflow-hidden bg-gradient-to-r from-primary-600/30 to-cyan-600/30 border border-primary-500/20">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-sm font-medium text-primary-200">
                        {formatBytes(displayed.value)}
                      </span>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3 pt-3 border-t border-dark-400/10">
            <div className="bg-dark-700/50 rounded-lg p-3 text-center">
              <p className="text-base font-bold text-white">{formatBytes(user.used_traffic_bytes)}</p>
              <p className="text-[11px] text-dark-200">Текущий период</p>
            </div>
            <div className="bg-dark-700/50 rounded-lg p-3 text-center">
              <p className="text-base font-bold text-white">
                {user.traffic_limit_bytes ? formatBytes(user.traffic_limit_bytes) : '∞'}
              </p>
              <p className="text-[11px] text-dark-200">Лимит</p>
            </div>
            <div className="bg-dark-700/50 rounded-lg p-3 text-center">
              <p className="text-base font-bold text-white">
                {formatBytes(user.lifetime_used_traffic_bytes || user.used_traffic_bytes)}
              </p>
              <p className="text-[11px] text-dark-200">Всё время</p>
            </div>
          </div>

          {/* Per-node breakdown for period views */}
          {API_PERIODS.includes(period) && trafficStats?.nodes_traffic && trafficStats.nodes_traffic.length > 0 && (
            <div className="pt-3 border-t border-dark-400/10">
              <p className="text-xs text-dark-300 mb-2">Разбивка по нодам</p>
              <div className="space-y-1.5">
                {trafficStats.nodes_traffic.map((node) => (
                  <div
                    key={node.node_uuid}
                    className="flex items-center justify-between px-2.5 py-1.5 bg-dark-700/30 rounded text-xs"
                  >
                    <span className="text-dark-100 truncate flex-1 mr-2">{node.node_name}</span>
                    <span className="text-white font-medium">{formatBytes(node.total_bytes)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const DEVICES_PER_PAGE = 3

function PaginatedDeviceList({ devices }: { devices: HwidDevice[] }) {
  const [devicePage, setDevicePage] = useState(1)
  const totalDevicePages = Math.ceil(devices.length / DEVICES_PER_PAGE)
  const startIdx = (devicePage - 1) * DEVICES_PER_PAGE
  const visibleDevices = devices.slice(startIdx, startIdx + DEVICES_PER_PAGE)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {visibleDevices.map((device, localIdx) => {
          const globalIdx = startIdx + localIdx
          const pi = getPlatformInfo(device.platform)
          return (
            <div
              key={device.hwid || globalIdx}
              className="bg-dark-700/40 rounded-lg p-3 border border-dark-600/20 hover:border-dark-500/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{pi.icon}</span>
                  <span className="text-sm font-medium text-white">{pi.label}</span>
                </div>
                <span className="text-[10px] text-dark-400 bg-dark-800/50 px-1.5 py-0.5 rounded font-mono">
                  #{globalIdx + 1}
                </span>
              </div>
              <div className="space-y-1.5 text-xs">
                {device.os_version && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">Версия ОС</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.os_version}</span>
                  </div>
                )}
                {device.device_model && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">Модель</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.device_model}</span>
                  </div>
                )}
                {device.app_version && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">Приложение</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.app_version}</span>
                  </div>
                )}
                {device.user_agent && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">User-Agent</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]" title={device.user_agent}>{device.user_agent}</span>
                  </div>
                )}
                {device.created_at && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">Добавлено</span>
                    <span className="text-dark-100">
                      {format(new Date(device.created_at), 'dd.MM.yyyy HH:mm')}
                    </span>
                  </div>
                )}
              </div>
              {device.hwid && (
                <p className="text-[10px] text-dark-400 font-mono mt-2 truncate" title={device.hwid}>
                  HWID: {device.hwid}
                </p>
              )}
            </div>
          )
        })}
      </div>

      {/* Pagination controls */}
      {totalDevicePages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setDevicePage(Math.max(1, devicePage - 1))}
            disabled={devicePage <= 1}
            className="px-2 py-1 text-xs bg-dark-700 hover:bg-dark-600 disabled:opacity-40 disabled:cursor-not-allowed text-dark-100 rounded transition-colors"
          >
            ←
          </button>
          <span className="text-xs text-dark-200">
            {devicePage} / {totalDevicePages}
          </span>
          <button
            onClick={() => setDevicePage(Math.min(totalDevicePages, devicePage + 1))}
            disabled={devicePage >= totalDevicePages}
            className="px-2 py-1 text-xs bg-dark-700 hover:bg-dark-600 disabled:opacity-40 disabled:cursor-not-allowed text-dark-100 rounded transition-colors"
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}

export default function UserDetail() {
  const { uuid } = useParams<{ uuid: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(searchParams.get('edit') === '1')
  const [editForm, setEditForm] = useState<EditFormData>({
    status: '',
    traffic_limit_bytes: null,
    traffic_limit_gb: '',
    is_unlimited: false,
    expire_at: '',
    hwid_device_limit: '',
  })
  const [editError, setEditError] = useState('')
  const [editSuccess, setEditSuccess] = useState(false)

  // Fetch user data
  const { data: user, isLoading, error } = useQuery<UserDetailData>({
    queryKey: ['user', uuid],
    queryFn: async () => {
      const response = await client.get(`/users/${uuid}`)
      return response.data
    },
    enabled: !!uuid,
  })

  // Fetch user violations
  const { data: violations } = useQuery<Violation[]>({
    queryKey: ['user-violations', uuid],
    queryFn: async () => {
      const response = await client.get(`/violations/user/${uuid}`)
      return response.data
    },
    enabled: !!uuid,
  })

  // Fetch HWID devices
  const { data: hwidDevices, isFetching: hwidFetching } = useQuery<HwidDevice[]>({
    queryKey: ['user-hwid-devices', uuid],
    queryFn: async () => {
      const response = await client.get(`/users/${uuid}/hwid-devices`)
      return response.data
    },
    enabled: !!uuid,
  })

  // Sync HWID devices from API
  const syncHwidMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/sync-hwid-devices`) },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-hwid-devices', uuid] })
    },
  })

  // Initialize edit form when user data loads
  useEffect(() => {
    if (user) {
      setEditForm({
        status: user.status,
        traffic_limit_bytes: user.traffic_limit_bytes,
        traffic_limit_gb: bytesToGb(user.traffic_limit_bytes),
        is_unlimited: !user.traffic_limit_bytes,
        expire_at: formatDateForInput(user.expire_at),
        hwid_device_limit: String(user.hwid_device_limit),
      })
    }
  }, [user])

  // Mutations
  const enableMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/enable`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }) },
  })
  const disableMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/disable`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }) },
  })
  const resetTrafficMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/reset-traffic`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }) },
  })
  const deleteMutation = useMutation({
    mutationFn: async () => { await client.delete(`/users/${uuid}`) },
    onSuccess: () => { navigate('/users') },
  })

  const updateUserMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const response = await client.patch(`/users/${uuid}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', uuid] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setEditSuccess(true)
      setEditError('')
      setTimeout(() => setEditSuccess(false), 3000)
      setIsEditing(false)
      setSearchParams({})
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || 'Ошибка сохранения')
    },
  })

  const handleSave = () => {
    setEditError('')
    const updateData: Record<string, unknown> = {}

    // Status
    if (user && editForm.status !== user.status) {
      updateData.status = editForm.status
    }

    // Traffic limit
    const newTrafficLimit = editForm.is_unlimited ? null : gbToBytes(editForm.traffic_limit_gb)
    if (user && newTrafficLimit !== user.traffic_limit_bytes) {
      updateData.traffic_limit_bytes = newTrafficLimit
    }

    // Expire at
    if (editForm.expire_at) {
      const newExpire = new Date(editForm.expire_at).toISOString()
      if (user && newExpire !== user.expire_at) {
        updateData.expire_at = newExpire
      }
    } else if (user?.expire_at) {
      updateData.expire_at = null
    }

    // HWID device limit
    const newHwid = parseInt(editForm.hwid_device_limit, 10)
    if (!isNaN(newHwid) && user && newHwid !== user.hwid_device_limit) {
      updateData.hwid_device_limit = newHwid
    }

    if (Object.keys(updateData).length === 0) {
      setIsEditing(false)
      setSearchParams({})
      return
    }

    updateUserMutation.mutate(updateData)
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    setSearchParams({})
    setEditError('')
    if (user) {
      setEditForm({
        status: user.status,
        traffic_limit_bytes: user.traffic_limit_bytes,
        traffic_limit_gb: bytesToGb(user.traffic_limit_bytes),
        is_unlimited: !user.traffic_limit_bytes,
        expire_at: formatDateForInput(user.expire_at),
        hwid_device_limit: String(user.hwid_device_limit),
      })
    }
  }

  const handleStartEdit = () => {
    setIsEditing(true)
    setSearchParams({ edit: '1' })
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
        <p className="text-red-400">Пользователь не найден</p>
        <button onClick={() => navigate('/users')} className="mt-2 text-sm text-primary-400 hover:underline">
          Вернуться к списку
        </button>
      </div>
    )
  }

  const trafficPercent = user.traffic_limit_bytes
    ? Math.min((user.used_traffic_bytes / user.traffic_limit_bytes) * 100, 100)
    : 0

  const statusBadge = getStatusBadge(user.status)
  const uaInfo = parseUserAgent(user.sub_last_user_agent)

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between animate-fade-in-up">
        <div className="flex items-center gap-3 md:gap-4 min-w-0">
          <button
            onClick={() => navigate('/users')}
            className="p-2 text-dark-200 hover:text-white rounded-lg hover:bg-dark-600 flex-shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg md:text-2xl font-bold text-white truncate">
                {user.username || user.email || user.short_uuid}
              </h1>
              <span className={`px-2 py-1 rounded text-xs font-medium ${statusBadge.color} text-white flex-shrink-0`}>
                {statusBadge.label}
              </span>
            </div>
            <p className="text-xs md:text-sm text-dark-200 truncate">{user.uuid}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {isEditing ? (
            <>
              <button
                onClick={handleSave}
                disabled={updateUserMutation.isPending}
                className="px-3 md:px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-green-800 text-white rounded-lg text-sm"
              >
                {updateUserMutation.isPending ? 'Сохранение...' : 'Сохранить'}
              </button>
              <button
                onClick={handleCancelEdit}
                disabled={updateUserMutation.isPending}
                className="px-3 md:px-4 py-2 bg-dark-700 hover:bg-dark-600 text-dark-100 rounded-lg text-sm"
              >
                Отмена
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleStartEdit}
                className="px-3 md:px-4 py-2 bg-primary-600 hover:bg-primary-500 text-white rounded-lg text-sm"
              >
                Редактировать
              </button>
              {user.status === 'active' ? (
                <button onClick={() => disableMutation.mutate()} disabled={disableMutation.isPending}
                  className="px-3 md:px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-red-800 text-white rounded-lg text-sm">
                  Отключить
                </button>
              ) : (
                <button onClick={() => enableMutation.mutate()} disabled={enableMutation.isPending}
                  className="px-3 md:px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-green-800 text-white rounded-lg text-sm">
                  Включить
                </button>
              )}
              <button onClick={() => resetTrafficMutation.mutate()} disabled={resetTrafficMutation.isPending}
                className="px-3 md:px-4 py-2 bg-dark-700 hover:bg-dark-600 text-primary-400 rounded-lg text-sm">
                Сбросить трафик
              </button>
              <button onClick={() => { if (confirm('Удалить пользователя?')) deleteMutation.mutate() }}
                disabled={deleteMutation.isPending}
                className="px-3 md:px-4 py-2 bg-dark-700 hover:bg-dark-600 text-red-400 rounded-lg text-sm">
                Удалить
              </button>
            </>
          )}
        </div>
      </div>

      {/* Edit success/error messages */}
      {editSuccess && (
        <div className="card border border-green-500/30 bg-green-500/10 py-3">
          <p className="text-green-400 text-sm">Изменения сохранены</p>
        </div>
      )}
      {editError && (
        <div className="card border border-red-500/30 bg-red-500/10 py-3">
          <p className="text-red-400 text-sm">{editError}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-4 md:space-y-6">

          {/* Block: General info / Edit form */}
          <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            <h2 className="text-base md:text-lg font-semibold text-white mb-4">
              {isEditing ? 'Редактирование' : 'Общая информация'}
            </h2>

            {isEditing ? (
              /* Edit form */
              <div className="space-y-5">
                {/* Status */}
                <div>
                  <label className="block text-sm text-dark-200 mb-1.5">Статус</label>
                  <select
                    value={editForm.status}
                    onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                    className="input"
                  >
                    <option value="active">Активен</option>
                    <option value="disabled">Отключён</option>
                    <option value="limited">Ограничен</option>
                    <option value="expired">Истёк</option>
                  </select>
                </div>

                {/* Traffic limit */}
                <div>
                  <label className="block text-sm text-dark-200 mb-1.5">Лимит трафика</label>
                  <div className="flex items-center gap-3 mb-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editForm.is_unlimited}
                        onChange={(e) => setEditForm({
                          ...editForm,
                          is_unlimited: e.target.checked,
                          traffic_limit_gb: e.target.checked ? '' : editForm.traffic_limit_gb,
                        })}
                        className="w-4 h-4 rounded border-dark-400/30 bg-dark-800 text-primary-500 focus:ring-primary-500/50"
                      />
                      <span className="text-sm text-dark-100">Безлимитный</span>
                    </label>
                  </div>
                  {!editForm.is_unlimited && (
                    <div className="relative">
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        value={editForm.traffic_limit_gb}
                        onChange={(e) => setEditForm({ ...editForm, traffic_limit_gb: e.target.value })}
                        placeholder="Введите лимит"
                        className="input pr-12"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-dark-200">ГБ</span>
                    </div>
                  )}
                </div>

                {/* Expire date */}
                <div>
                  <label className="block text-sm text-dark-200 mb-1.5">Дата истечения</label>
                  <input
                    type="datetime-local"
                    value={editForm.expire_at}
                    onChange={(e) => setEditForm({ ...editForm, expire_at: e.target.value })}
                    className="input"
                  />
                  {editForm.expire_at && (
                    <button
                      onClick={() => setEditForm({ ...editForm, expire_at: '' })}
                      className="text-xs text-dark-200 hover:text-primary-400 mt-1"
                    >
                      Убрать дату (бессрочно)
                    </button>
                  )}
                </div>

                {/* HWID limit */}
                <div>
                  <label className="block text-sm text-dark-200 mb-1.5">Лимит устройств (HWID)</label>
                  <input
                    type="number"
                    min="0"
                    value={editForm.hwid_device_limit}
                    onChange={(e) => setEditForm({ ...editForm, hwid_device_limit: e.target.value })}
                    className="input"
                  />
                </div>

                {/* Read-only fields */}
                <div className="pt-3 border-t border-dark-400/10">
                  <p className="text-xs text-dark-300 mb-3">Информация (только чтение)</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-dark-200">Username</p>
                      <p className="text-white text-sm">{user.username || '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-200">Email</p>
                      <p className="text-white text-sm truncate">{user.email || '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-200">Telegram ID</p>
                      <p className="text-white text-sm">{user.telegram_id || '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-dark-200">Short UUID</p>
                      <p className="text-white text-sm font-mono">{user.short_uuid || '—'}</p>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* View mode */
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-dark-200">Username</p>
                  <p className="text-white">{user.username || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Email</p>
                  <p className="text-white truncate">{user.email || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Telegram ID</p>
                  <p className="text-white">{user.telegram_id || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Short UUID</p>
                  <p className="text-white font-mono">{user.short_uuid || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Создан</p>
                  <p className="text-white">
                    {user.created_at
                      ? format(new Date(user.created_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                      : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Истекает</p>
                  <p className="text-white">
                    {user.expire_at
                      ? format(new Date(user.expire_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                      : 'Бессрочно'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-dark-200">Последняя активность</p>
                  <p className="text-white">
                    {user.online_at
                      ? format(new Date(user.online_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                      : '—'}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Block: Traffic */}
          <TrafficBlock user={user} trafficPercent={trafficPercent} />

          {/* Block: Devices (HWID) */}
          <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base md:text-lg font-semibold text-white">
                Устройства
                {hwidDevices && hwidDevices.length > 0 && (
                  <span className="ml-2 text-sm font-normal text-dark-200">
                    {hwidDevices.length} / {user.hwid_device_limit || '∞'}
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => syncHwidMutation.mutate()}
                  disabled={syncHwidMutation.isPending || hwidFetching}
                  className="p-1.5 text-dark-300 hover:text-primary-400 hover:bg-dark-700/50 rounded-lg transition-colors disabled:opacity-40"
                  title="Синхронизировать устройства"
                >
                  <svg className={`w-4 h-4 ${syncHwidMutation.isPending ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
                <span className="text-xs text-dark-300 bg-dark-700/50 px-2 py-1 rounded">
                  Лимит: {user.hwid_device_limit || '∞'}
                </span>
              </div>
            </div>

            {/* HWID device cards with pagination */}
            {hwidDevices && hwidDevices.length > 0 ? (
              <PaginatedDeviceList devices={hwidDevices} />
            ) : (
              <div className="text-center py-6 text-dark-300 text-sm">
                Нет зарегистрированных устройств
              </div>
            )}
          </div>

          {/* Block: Violations */}
          {violations && violations.length > 0 && (
            <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
              <h2 className="text-base md:text-lg font-semibold text-white mb-4">
                Нарушения ({violations.length})
              </h2>
              <div className="space-y-3">
                {violations.slice(0, 5).map((v) => (
                  <div
                    key={v.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-dark-700 rounded-lg"
                  >
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${getSeverityColor(v.severity)}`}>
                        {v.severity}
                      </span>
                      <span className="text-white text-sm">Score: {v.score.toFixed(1)}</span>
                      <span className="text-dark-200 text-sm">{v.recommended_action}</span>
                    </div>
                    <span className="text-dark-200 text-xs sm:text-sm flex-shrink-0">
                      {format(new Date(v.detected_at), 'dd.MM.yyyy HH:mm')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4 md:space-y-6">

          {/* Block: Subscription */}
          <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <h2 className="text-base md:text-lg font-semibold text-white mb-4">Подписка</h2>
            <div className="space-y-3">
              {user.subscription_url ? (
                <div>
                  <p className="text-xs text-dark-200 mb-1">Ссылка подписки</p>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={user.subscription_url}
                      className="input text-xs font-mono flex-1 truncate"
                    />
                    <button
                      onClick={() => copyToClipboard(user.subscription_url!)}
                      className={`px-3 py-2 rounded-lg text-xs font-medium flex-shrink-0 transition-colors ${
                        copied
                          ? 'bg-green-600 text-white'
                          : 'bg-dark-600 hover:bg-dark-500 text-dark-100'
                      }`}
                    >
                      {copied ? 'OK' : 'Копировать'}
                    </button>
                  </div>
                </div>
              ) : user.subscription_uuid ? (
                <div>
                  <p className="text-xs text-dark-200 mb-1">UUID подписки</p>
                  <p className="text-white text-sm font-mono break-all">{user.subscription_uuid}</p>
                </div>
              ) : (
                <p className="text-dark-200 text-sm">Нет активной подписки</p>
              )}
              {user.subscription_url && user.subscription_uuid && (
                <div>
                  <p className="text-xs text-dark-200 mb-1">UUID подписки</p>
                  <p className="text-dark-100 text-xs font-mono break-all">{user.subscription_uuid}</p>
                </div>
              )}
            </div>
          </div>

          {/* Block: Anti-Abuse */}
          <div className="card rounded-xl border border-dark-400/10 p-4 md:p-6 animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <h2 className="text-base md:text-lg font-semibold text-white mb-4">Anti-Abuse</h2>
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm text-dark-200">Trust Score</p>
                  <span className="text-white font-medium">{user.trust_score ?? 100}</span>
                </div>
                <div className="w-full bg-dark-600 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      (user.trust_score ?? 100) >= 70 ? 'bg-green-500'
                        : (user.trust_score ?? 100) >= 40 ? 'bg-yellow-500'
                        : 'bg-red-500'
                    }`}
                    style={{ width: `${user.trust_score ?? 100}%` }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-dark-600 rounded-lg p-3 text-center">
                  <p className="text-xl md:text-2xl font-bold text-white">{user.violation_count_30d}</p>
                  <p className="text-xs text-dark-200">Нарушений (30д)</p>
                </div>
                <div className="bg-dark-600 rounded-lg p-3 text-center">
                  <p className="text-xl md:text-2xl font-bold text-white">{user.active_connections}</p>
                  <p className="text-xs text-dark-200">Подключений</p>
                </div>
              </div>
              <div className="bg-dark-600 rounded-lg p-3 text-center">
                <p className="text-xl md:text-2xl font-bold text-white">{user.unique_ips_24h}</p>
                <p className="text-xs text-dark-200">Уникальных IP (24ч)</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
