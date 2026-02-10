import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import {
  ArrowLeft,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Pencil,
  Trash2,
  X,
  Save,
  ShieldCheck,
  Smartphone,
  Monitor,
  Laptop,
  Server,
  Globe,
  Clock,
  AlertTriangle,
  Users,
  Activity,
  TrendingUp,
  Eye,
} from 'lucide-react'
import { toast } from 'sonner'
import client from '../api/client'
import { useHasPermission } from '../components/PermissionGate'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

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

function getStatusBadge(status: string): { label: string; variant: 'default' | 'success' | 'warning' | 'destructive' | 'secondary'; dotColor: string } {
  const s = status.toLowerCase()
  switch (s) {
    case 'active': return { label: 'Активен', variant: 'success', dotColor: 'bg-green-400' }
    case 'disabled': return { label: 'Отключён', variant: 'destructive', dotColor: 'bg-red-400' }
    case 'expired': return { label: 'Истёк', variant: 'warning', dotColor: 'bg-yellow-400' }
    case 'limited': return { label: 'Ограничен', variant: 'warning', dotColor: 'bg-orange-400' }
    default: return { label: status, variant: 'secondary', dotColor: 'bg-gray-400' }
  }
}

function getSeverityBadge(severity: string): { variant: 'destructive' | 'warning' | 'secondary'; icon: typeof AlertTriangle } {
  switch (severity) {
    case 'critical': return { variant: 'destructive', icon: AlertTriangle }
    case 'high': return { variant: 'destructive', icon: AlertTriangle }
    case 'medium': return { variant: 'warning', icon: AlertTriangle }
    default: return { variant: 'secondary', icon: AlertTriangle }
  }
}

function getPlatformIcon(platform: string | null): { icon: typeof Smartphone; label: string } {
  const p = (platform || '').toLowerCase()
  if (p.includes('windows') || p === 'win') return { icon: Monitor, label: 'Windows' }
  if (p.includes('android')) return { icon: Smartphone, label: 'Android' }
  if (p.includes('ios') || p.includes('iphone') || p.includes('ipad')) return { icon: Smartphone, label: 'iOS' }
  if (p.includes('macos') || p.includes('mac') || p.includes('darwin')) return { icon: Laptop, label: 'macOS' }
  if (p.includes('linux')) return { icon: Monitor, label: 'Linux' }
  return { icon: Smartphone, label: platform || 'Неизвестно' }
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
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary-400" />
          Трафик
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Period selector */}
        <div className="flex flex-wrap gap-1">
          {TRAFFIC_PERIODS.map((p) => (
            <Button
              key={p.key}
              variant={period === p.key ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setPeriod(p.key)}
              className={cn(
                'h-7 px-2.5 text-xs',
                period === p.key
                  ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30 hover:bg-primary-600/30 shadow-none'
                  : 'text-dark-200 hover:text-white'
              )}
            >
              {p.label}
            </Button>
          ))}
        </div>

        {period === 'nodes' ? (
          /* Per-node breakdown */
          <div className="space-y-3">
            {/* Node period sub-filter */}
            <div className="flex flex-wrap gap-1">
              {NODE_PERIOD_OPTIONS.map((p) => (
                <Button
                  key={p.key}
                  variant={nodePeriod === p.key ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setNodePeriod(p.key)}
                  className={cn(
                    'h-6 px-2 text-[11px]',
                    nodePeriod === p.key
                      ? 'bg-dark-600 text-white'
                      : 'text-dark-300 hover:text-dark-100'
                  )}
                >
                  {p.label}
                </Button>
              ))}
            </div>

            {/* Node list */}
            <div className="space-y-2 relative">
              {showLoadingOverlay && (
                <div className="absolute inset-0 bg-dark-800/50 rounded-lg flex items-center justify-center z-10">
                  <RefreshCw className="h-5 w-5 text-primary-500 animate-spin" />
                </div>
              )}
              {trafficStats?.nodes_traffic && trafficStats.nodes_traffic.length > 0 ? (
                <>
                  {trafficStats.nodes_traffic.map((node) => (
                    <div
                      key={node.node_uuid}
                      className="flex items-center justify-between p-2.5 bg-dark-700/40 rounded-lg border border-dark-600/20"
                    >
                      <div className="flex items-center gap-2 flex-1 min-w-0 mr-3">
                        <Server className="h-3.5 w-3.5 text-dark-300 flex-shrink-0" />
                        <span className="text-sm text-dark-100 truncate">{node.node_name}</span>
                      </div>
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
                <RefreshCw className="h-5 w-5 text-primary-500 animate-spin" />
              </div>
            )}
            <div>
              {isUnlimited ? (
                <>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-dark-200">{displayed.label}</span>
                    <Badge variant="default" className="text-xs">Безлимит</Badge>
                  </div>
                  <div className="relative w-full h-7 rounded-full overflow-hidden bg-gradient-to-r from-primary-600/30 to-cyan-600/30 border border-primary-500/20">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-sm font-medium text-primary-200">
                        {formatBytes(displayed.value)}{period === 'current' ? ' / \u221E' : ''}
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
                          className={cn(
                            'h-2.5 rounded-full transition-all',
                            trafficPercent > 90 ? 'bg-red-500' : trafficPercent > 70 ? 'bg-yellow-500' : 'bg-primary-500'
                          )}
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
            <Separator />
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-dark-700/50 rounded-lg p-3 text-center">
                <p className="text-base font-bold text-white">{formatBytes(user.used_traffic_bytes)}</p>
                <p className="text-[11px] text-dark-200">Текущий период</p>
              </div>
              <div className="bg-dark-700/50 rounded-lg p-3 text-center">
                <p className="text-base font-bold text-white">
                  {user.traffic_limit_bytes ? formatBytes(user.traffic_limit_bytes) : '\u221E'}
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
              <>
                <Separator />
                <div>
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
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
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
          const pi = getPlatformIcon(device.platform)
          const PlatformIcon = pi.icon
          return (
            <div
              key={device.hwid || globalIdx}
              className="bg-dark-700/40 rounded-lg p-3 border border-dark-600/20 hover:border-dark-500/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <PlatformIcon className="h-4 w-4 text-primary-400" />
                  <span className="text-sm font-medium text-white">{pi.label}</span>
                </div>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 font-mono">
                  #{globalIdx + 1}
                </Badge>
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDevicePage(Math.max(1, devicePage - 1))}
            disabled={devicePage <= 1}
            className="h-7 w-7 p-0"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-xs text-dark-200">
            {devicePage} / {totalDevicePages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDevicePage(Math.min(totalDevicePages, devicePage + 1))}
            disabled={devicePage >= totalDevicePages}
            className="h-7 w-7 p-0"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
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
  const canEdit = useHasPermission('users', 'edit')
  const canDelete = useHasPermission('users', 'delete')
  const [isEditing, setIsEditing] = useState(searchParams.get('edit') === '1' && canEdit)
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
      toast.success('HWID устройства синхронизированы')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка синхронизации')
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
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success('Пользователь включён') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const disableMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/disable`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success('Пользователь отключён') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const resetTrafficMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/reset-traffic`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success('Трафик сброшен') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const deleteMutation = useMutation({
    mutationFn: async () => { await client.delete(`/users/${uuid}`) },
    onSuccess: () => { toast.success('Пользователь удалён'); navigate('/users') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка удаления') },
  })

  const updateUserMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const response = await client.patch(`/users/${uuid}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', uuid] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Пользователь обновлён')
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
      <div className="space-y-4 md:space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="space-y-2 flex-1">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-72" />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-40 w-full rounded-xl" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </div>
        </div>
      </div>
    )
  }

  if (error || !user) {
    return (
      <Card className="border-red-500/20 bg-red-500/10">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-5 w-5 text-red-400" />
            <p className="text-red-400 font-medium">Пользователь не найден</p>
          </div>
          <Button variant="link" onClick={() => navigate('/users')} className="px-0">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Вернуться к списку
          </Button>
        </CardContent>
      </Card>
    )
  }

  const trafficPercent = user.traffic_limit_bytes
    ? Math.min((user.used_traffic_bytes / user.traffic_limit_bytes) * 100, 100)
    : 0

  const statusBadge = getStatusBadge(user.status)
  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between animate-fade-in-up">
        <div className="flex items-center gap-3 md:gap-4 min-w-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/users')}
            className="flex-shrink-0"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg md:text-2xl font-bold text-white truncate">
                {user.username || user.email || user.short_uuid}
              </h1>
              <Badge variant={statusBadge.variant} className="flex-shrink-0">
                <span className={cn('h-1.5 w-1.5 rounded-full mr-1.5', statusBadge.dotColor)} />
                {statusBadge.label}
              </Badge>
            </div>
            <p className="text-xs md:text-sm text-dark-200 truncate font-mono">{user.uuid}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {isEditing && canEdit ? (
            <>
              <Button
                onClick={handleSave}
                disabled={updateUserMutation.isPending}
                size="sm"
                className="bg-green-600 hover:bg-green-500 text-white"
              >
                <Save className="h-4 w-4 mr-1.5" />
                {updateUserMutation.isPending ? 'Сохранение...' : 'Сохранить'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelEdit}
                disabled={updateUserMutation.isPending}
              >
                <X className="h-4 w-4 mr-1.5" />
                Отмена
              </Button>
            </>
          ) : (
            <>
              {canEdit && (
                <Button size="sm" onClick={handleStartEdit}>
                  <Pencil className="h-4 w-4 mr-1.5" />
                  Редактировать
                </Button>
              )}
              {canEdit && (
                user.status === 'active' ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => disableMutation.mutate()}
                    disabled={disableMutation.isPending}
                  >
                    <X className="h-4 w-4 mr-1.5" />
                    Отключить
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => enableMutation.mutate()}
                    disabled={enableMutation.isPending}
                    className="bg-green-600 hover:bg-green-500 text-white"
                  >
                    <Check className="h-4 w-4 mr-1.5" />
                    Включить
                  </Button>
                )
              )}
              {canEdit && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => resetTrafficMutation.mutate()}
                  disabled={resetTrafficMutation.isPending}
                  className="text-primary-400"
                >
                  <RefreshCw className={cn('h-4 w-4 mr-1.5', resetTrafficMutation.isPending && 'animate-spin')} />
                  Сбросить трафик
                </Button>
              )}
              {canDelete && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { if (confirm('Удалить пользователя?')) deleteMutation.mutate() }}
                  disabled={deleteMutation.isPending}
                  className="text-red-400 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />
                  Удалить
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Edit success/error messages */}
      {editSuccess && (
        <Card className="border-green-500/30 bg-green-500/10">
          <CardContent className="py-3 px-4 flex items-center gap-2">
            <Check className="h-4 w-4 text-green-400" />
            <p className="text-green-400 text-sm">Изменения сохранены</p>
          </CardContent>
        </Card>
      )}
      {editError && (
        <Card className="border-red-500/30 bg-red-500/10">
          <CardContent className="py-3 px-4 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            <p className="text-red-400 text-sm">{editError}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-4 md:space-y-6">

          {/* Block: General info / Edit form */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {isEditing ? (
                  <>
                    <Pencil className="h-5 w-5 text-primary-400" />
                    Редактирование
                  </>
                ) : (
                  <>
                    <Eye className="h-5 w-5 text-primary-400" />
                    Общая информация
                  </>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isEditing ? (
                /* Edit form */
                <div className="space-y-5">
                  {/* Status */}
                  <div className="space-y-2">
                    <Label>Статус</Label>
                    <Select
                      value={editForm.status}
                      onValueChange={(value) => setEditForm({ ...editForm, status: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Выберите статус" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">Активен</SelectItem>
                        <SelectItem value="disabled">Отключён</SelectItem>
                        <SelectItem value="limited">Ограничен</SelectItem>
                        <SelectItem value="expired">Истёк</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Traffic limit */}
                  <div className="space-y-2">
                    <Label>Лимит трафика</Label>
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
                        <Input
                          type="number"
                          step="0.1"
                          min="0"
                          value={editForm.traffic_limit_gb}
                          onChange={(e) => setEditForm({ ...editForm, traffic_limit_gb: e.target.value })}
                          placeholder="Введите лимит"
                          className="pr-12"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-dark-200">ГБ</span>
                      </div>
                    )}
                  </div>

                  {/* Expire date */}
                  <div className="space-y-2">
                    <Label>Дата истечения</Label>
                    <Input
                      type="datetime-local"
                      value={editForm.expire_at}
                      onChange={(e) => setEditForm({ ...editForm, expire_at: e.target.value })}
                    />
                    {editForm.expire_at && (
                      <Button
                        variant="link"
                        size="sm"
                        onClick={() => setEditForm({ ...editForm, expire_at: '' })}
                        className="px-0 h-auto text-xs text-dark-200 hover:text-primary-400"
                      >
                        Убрать дату (бессрочно)
                      </Button>
                    )}
                  </div>

                  {/* HWID limit */}
                  <div className="space-y-2">
                    <Label>Лимит устройств (HWID)</Label>
                    <Input
                      type="number"
                      min="0"
                      value={editForm.hwid_device_limit}
                      onChange={(e) => setEditForm({ ...editForm, hwid_device_limit: e.target.value })}
                    />
                  </div>

                  {/* Read-only fields */}
                  <Separator />
                  <div>
                    <p className="text-xs text-dark-300 mb-3">Информация (только чтение)</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <p className="text-xs text-dark-200">Username</p>
                        <p className="text-white text-sm">{user.username || '\u2014'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-dark-200">Email</p>
                        <p className="text-white text-sm truncate">{user.email || '\u2014'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-dark-200">Telegram ID</p>
                        <p className="text-white text-sm">{user.telegram_id || '\u2014'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-dark-200">Short UUID</p>
                        <p className="text-white text-sm font-mono">{user.short_uuid || '\u2014'}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* View mode */
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-dark-200">Username</p>
                    <p className="text-white">{user.username || '\u2014'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-dark-200">Email</p>
                    <p className="text-white truncate">{user.email || '\u2014'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-dark-200">Telegram ID</p>
                    <p className="text-white">{user.telegram_id || '\u2014'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-dark-200">Short UUID</p>
                    <p className="text-white font-mono">{user.short_uuid || '\u2014'}</p>
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Clock className="h-3.5 w-3.5 text-dark-300" />
                      <p className="text-sm text-dark-200">Создан</p>
                    </div>
                    <p className="text-white">
                      {user.created_at
                        ? format(new Date(user.created_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                        : '\u2014'}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Clock className="h-3.5 w-3.5 text-dark-300" />
                      <p className="text-sm text-dark-200">Истекает</p>
                    </div>
                    <p className="text-white">
                      {user.expire_at
                        ? format(new Date(user.expire_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                        : 'Бессрочно'}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Activity className="h-3.5 w-3.5 text-dark-300" />
                      <p className="text-sm text-dark-200">Последняя активность</p>
                    </div>
                    <p className="text-white">
                      {user.online_at
                        ? format(new Date(user.online_at), 'dd MMM yyyy, HH:mm', { locale: ru })
                        : '\u2014'}
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Block: Traffic */}
          <TrafficBlock user={user} trafficPercent={trafficPercent} />

          {/* Block: Devices (HWID) */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Smartphone className="h-5 w-5 text-primary-400" />
                  Устройства
                  {hwidDevices && hwidDevices.length > 0 && (
                    <span className="ml-1 text-sm font-normal text-dark-200">
                      {hwidDevices.length} / {user.hwid_device_limit || '\u221E'}
                    </span>
                  )}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => syncHwidMutation.mutate()}
                    disabled={syncHwidMutation.isPending || hwidFetching}
                    className="h-8 w-8 p-0"
                    title="Синхронизировать устройства"
                  >
                    <RefreshCw className={cn('h-4 w-4', syncHwidMutation.isPending && 'animate-spin')} />
                  </Button>
                  <Badge variant="outline" className="text-xs">
                    Лимит: {user.hwid_device_limit || '\u221E'}
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* HWID device cards with pagination */}
              {hwidDevices && hwidDevices.length > 0 ? (
                <PaginatedDeviceList devices={hwidDevices} />
              ) : (
                <div className="text-center py-6 text-dark-300 text-sm">
                  Нет зарегистрированных устройств
                </div>
              )}
            </CardContent>
          </Card>

          {/* Block: Violations */}
          {violations && violations.length > 0 && (
            <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-400" />
                  Нарушения
                  <Badge variant="warning" className="ml-1">{violations.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {violations.slice(0, 5).map((v) => {
                    const sevBadge = getSeverityBadge(v.severity)
                    return (
                      <div
                        key={v.id}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-dark-700 rounded-lg"
                      >
                        <div className="flex items-center gap-3 flex-wrap">
                          <Badge variant={sevBadge.variant}>
                            {v.severity}
                          </Badge>
                          <span className="text-white text-sm">Score: {v.score.toFixed(1)}</span>
                          <span className="text-dark-200 text-sm">{v.recommended_action}</span>
                        </div>
                        <span className="text-dark-200 text-xs sm:text-sm flex-shrink-0">
                          {format(new Date(v.detected_at), 'dd.MM.yyyy HH:mm')}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4 md:space-y-6">

          {/* Block: Subscription */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-primary-400" />
                Подписка
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {user.subscription_url ? (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">Ссылка подписки</p>
                    <div className="flex items-center gap-2">
                      <Input
                        readOnly
                        value={user.subscription_url}
                        className="text-xs font-mono flex-1 truncate"
                      />
                      <Button
                        variant={copied ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => copyToClipboard(user.subscription_url!)}
                        className={cn(
                          'flex-shrink-0',
                          copied && 'bg-green-600 hover:bg-green-500 text-white'
                        )}
                      >
                        {copied ? (
                          <>
                            <Check className="h-3.5 w-3.5 mr-1" />
                            OK
                          </>
                        ) : (
                          <>
                            <Copy className="h-3.5 w-3.5 mr-1" />
                            Копировать
                          </>
                        )}
                      </Button>
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
            </CardContent>
          </Card>

          {/* Block: Anti-Abuse */}
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-primary-400" />
                Anti-Abuse
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm text-dark-200">Trust Score</p>
                    <Badge
                      variant={
                        (user.trust_score ?? 100) >= 70 ? 'success'
                          : (user.trust_score ?? 100) >= 40 ? 'warning'
                          : 'destructive'
                      }
                    >
                      {user.trust_score ?? 100}
                    </Badge>
                  </div>
                  <div className="w-full bg-dark-600 rounded-full h-2">
                    <div
                      className={cn(
                        'h-2 rounded-full transition-all',
                        (user.trust_score ?? 100) >= 70 ? 'bg-green-500'
                          : (user.trust_score ?? 100) >= 40 ? 'bg-yellow-500'
                          : 'bg-red-500'
                      )}
                      style={{ width: `${user.trust_score ?? 100}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-dark-600 rounded-lg p-3 text-center">
                    <div className="flex justify-center mb-1">
                      <AlertTriangle className="h-4 w-4 text-dark-300" />
                    </div>
                    <p className="text-xl md:text-2xl font-bold text-white">{user.violation_count_30d}</p>
                    <p className="text-xs text-dark-200">Нарушений (30д)</p>
                  </div>
                  <div className="bg-dark-600 rounded-lg p-3 text-center">
                    <div className="flex justify-center mb-1">
                      <Users className="h-4 w-4 text-dark-300" />
                    </div>
                    <p className="text-xl md:text-2xl font-bold text-white">{user.active_connections}</p>
                    <p className="text-xs text-dark-200">Подключений</p>
                  </div>
                </div>
                <div className="bg-dark-600 rounded-lg p-3 text-center">
                  <div className="flex justify-center mb-1">
                    <Globe className="h-4 w-4 text-dark-300" />
                  </div>
                  <p className="text-xl md:text-2xl font-bold text-white">{user.unique_ips_24h}</p>
                  <p className="text-xs text-dark-200">Уникальных IP (24ч)</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
