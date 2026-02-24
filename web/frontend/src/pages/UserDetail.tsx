import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
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
  Network,
  Clock,
  AlertTriangle,
  Users,
  Activity,
  TrendingUp,
  Eye,
  QrCode,
  Download,
  ShieldOff,
  Settings,
  KeyRound,
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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { cn } from '@/lib/utils'
import { QRCodeSVG } from 'qrcode.react'

const ANALYZER_KEYS = ['temporal', 'geo', 'asn', 'profile', 'device', 'hwid'] as const

interface UserDetailData {
  uuid: string
  short_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  description: string | null
  tag: string | null
  status: string
  expire_at: string | null
  traffic_limit_bytes: number | null
  traffic_limit_strategy: string | null
  used_traffic_bytes: number
  lifetime_used_traffic_bytes: number
  hwid_device_limit: number
  external_squad_uuid: string | null
  active_internal_squads: { uuid: string; name: string }[] | null
  created_at: string
  updated_at: string | null
  online_at: string | null
  subscription_uuid: string | null
  subscription_url: string | null
  sub_last_user_agent: string | null
  sub_last_opened_at: string | null
  sub_revoked_at: string | null
  last_traffic_reset_at: string | null
  trojan_password: string | null
  vless_uuid: string | null
  ss_password: string | null
  first_connected_at: string | null
  last_connected_node_uuid: string | null
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
  traffic_limit_strategy: string
  is_unlimited: boolean
  expire_at: string
  hwid_device_limit: string
  description: string
  tag: string
  email: string
  telegram_id: string
}

function getStatusBadge(status: string, t: (key: string) => string): { label: string; variant: 'default' | 'success' | 'warning' | 'destructive' | 'secondary'; dotColor: string } {
  const s = status.toLowerCase()
  switch (s) {
    case 'active': return { label: t('userDetail.statuses.active'), variant: 'success', dotColor: 'bg-green-400' }
    case 'disabled': return { label: t('userDetail.statuses.disabled'), variant: 'destructive', dotColor: 'bg-red-400' }
    case 'expired': return { label: t('userDetail.statuses.expired'), variant: 'warning', dotColor: 'bg-yellow-400' }
    case 'limited': return { label: t('userDetail.statuses.limited'), variant: 'warning', dotColor: 'bg-orange-400' }
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

function getPlatformIcon(platform: string | null, t: (key: string) => string): { icon: typeof Smartphone; label: string } {
  const p = (platform || '').toLowerCase()
  if (p.includes('windows') || p === 'win') return { icon: Monitor, label: 'Windows' }
  if (p.includes('android')) return { icon: Smartphone, label: 'Android' }
  if (p.includes('ios') || p.includes('iphone') || p.includes('ipad')) return { icon: Smartphone, label: 'iOS' }
  if (p.includes('macos') || p.includes('mac') || p.includes('darwin')) return { icon: Laptop, label: 'macOS' }
  if (p.includes('linux')) return { icon: Monitor, label: 'Linux' }
  return { icon: Smartphone, label: platform || t('userDetail.unknown') }
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

// API period keys (sent to backend)
const API_PERIODS: TrafficPeriod[] = ['today', 'week', 'month', '3month', '6month', 'year']

function TrafficBlock({ user, trafficPercent }: { user: UserDetailData; trafficPercent: number }) {
  const { t } = useTranslation()
  const { formatBytes } = useFormatters()
  const [period, setPeriod] = useState<TrafficPeriod>('current')
  const [nodePeriod, setNodePeriod] = useState<string>('today')

  const TRAFFIC_PERIODS: { key: TrafficPeriod; label: string }[] = [
    { key: 'current', label: t('userDetail.traffic.periods.current') },
    { key: 'lifetime', label: t('userDetail.traffic.periods.lifetime') },
    { key: 'today', label: t('userDetail.traffic.periods.today') },
    { key: 'week', label: t('userDetail.traffic.periods.week') },
    { key: 'month', label: t('userDetail.traffic.periods.month') },
    { key: '3month', label: t('userDetail.traffic.periods.3month') },
    { key: '6month', label: t('userDetail.traffic.periods.6month') },
    { key: 'year', label: t('userDetail.traffic.periods.year') },
    { key: 'nodes', label: t('userDetail.traffic.periods.byNodes') },
  ]

  const NODE_PERIOD_OPTIONS = [
    { key: 'today', label: t('userDetail.traffic.periods.today') },
    { key: 'week', label: t('userDetail.traffic.periods.week') },
    { key: 'month', label: t('userDetail.traffic.periods.month') },
    { key: '3month', label: t('userDetail.traffic.periods.3monthShort') },
    { key: '6month', label: t('userDetail.traffic.periods.6monthShort') },
    { key: 'year', label: t('userDetail.traffic.periods.year') },
  ]

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
        return { value: user.used_traffic_bytes, label: t('userDetail.traffic.currentPeriod') }
      case 'lifetime':
        return { value: user.lifetime_used_traffic_bytes || user.used_traffic_bytes, label: t('userDetail.traffic.allTime') }
      default:
        if (trafficStats && API_PERIODS.includes(period)) {
          return {
            value: trafficStats.period_bytes,
            label: TRAFFIC_PERIODS.find(p => p.key === period)?.label || '',
          }
        }
        return { value: user.used_traffic_bytes, label: t('userDetail.traffic.used') }
    }
  }

  const displayed = getDisplay()
  const showLoadingOverlay = isFetching && period !== 'current'

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary-400" />
          {t('userDetail.traffic.title')}
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
                    <span className="text-sm text-primary-400 font-medium">{t('userDetail.traffic.total')}</span>
                    <span className="text-sm text-white font-bold">
                      {formatBytes(trafficStats.nodes_traffic.reduce((sum, n) => sum + n.total_bytes, 0))}
                    </span>
                  </div>
                </>
              ) : (
                <div className="text-center py-6 text-dark-300 text-sm">
                  {isFetching ? t('userDetail.traffic.loading') : t('userDetail.traffic.noNodeData')}
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
                    <Badge variant="default" className="text-xs">{t('userDetail.trafficUnlimited')}</Badge>
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
                        {t('userDetail.traffic.percentUsed', { percent: trafficPercent.toFixed(1) })}
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
                <p className="text-[11px] text-dark-200">{t('userDetail.traffic.currentPeriod')}</p>
              </div>
              <div className="bg-dark-700/50 rounded-lg p-3 text-center">
                <p className="text-base font-bold text-white">
                  {user.traffic_limit_bytes ? formatBytes(user.traffic_limit_bytes) : '\u221E'}
                </p>
                <p className="text-[11px] text-dark-200">{t('userDetail.traffic.limit')}</p>
              </div>
              <div className="bg-dark-700/50 rounded-lg p-3 text-center">
                <p className="text-base font-bold text-white">
                  {formatBytes(user.lifetime_used_traffic_bytes || user.used_traffic_bytes)}
                </p>
                <p className="text-[11px] text-dark-200">{t('userDetail.traffic.allTime')}</p>
              </div>
            </div>

            {/* Per-node breakdown for period views */}
            {API_PERIODS.includes(period) && trafficStats?.nodes_traffic && trafficStats.nodes_traffic.length > 0 && (
              <>
                <Separator />
                <div>
                  <p className="text-xs text-dark-300 mb-2">{t('userDetail.traffic.nodeBreakdown')}</p>
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

function PaginatedDeviceList({
  devices,
  onDeleteDevice,
  onDeleteAll
}: {
  devices: HwidDevice[]
  onDeleteDevice?: (deviceId: string) => void
  onDeleteAll?: () => void
}) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const [devicePage, setDevicePage] = useState(1)
  const totalDevicePages = Math.ceil(devices.length / DEVICES_PER_PAGE)
  const startIdx = (devicePage - 1) * DEVICES_PER_PAGE
  const visibleDevices = devices.slice(startIdx, startIdx + DEVICES_PER_PAGE)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {visibleDevices.map((device, localIdx) => {
          const globalIdx = startIdx + localIdx
          const pi = getPlatformIcon(device.platform, t)
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
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 font-mono">
                    #{globalIdx + 1}
                  </Badge>
                  {onDeleteDevice && device.hwid && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteDevice(device.hwid!)}
                      className="h-6 w-6 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
              <div className="space-y-1.5 text-xs">
                {device.os_version && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">{t('userDetail.devices.osVersion')}</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.os_version}</span>
                  </div>
                )}
                {device.device_model && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">{t('userDetail.devices.model')}</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.device_model}</span>
                  </div>
                )}
                {device.app_version && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">{t('userDetail.devices.app')}</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]">{device.app_version}</span>
                  </div>
                )}
                {device.user_agent && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">{t('userDetail.devices.userAgent')}</span>
                    <span className="text-dark-100 text-right truncate ml-2 max-w-[60%]" title={device.user_agent}>{device.user_agent}</span>
                  </div>
                )}
                {device.created_at && (
                  <div className="flex justify-between">
                    <span className="text-dark-300">{t('userDetail.devices.added')}</span>
                    <span className="text-dark-100">
                      {formatDate(device.created_at)}
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

      {/* Delete all button */}
      {onDeleteAll && devices.length > 0 && (
        <div className="flex justify-center pt-2">
          <Button
            variant="destructive"
            size="sm"
            onClick={onDeleteAll}
            className="text-xs"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1.5" />
            {t('userDetail.devices.deleteAll', 'Удалить все устройства')}
          </Button>
        </div>
      )}

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

/**
 * User audit history — shows admin actions on this user.
 */
interface AuditItem {
  id: number
  action: string
  admin_username: string
  created_at: string | null
  details: string | null
}

function UserHistory({ uuid }: { uuid: string }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const { data, isLoading } = useQuery<{ items: AuditItem[] }>({
    queryKey: ['user-history', uuid],
    queryFn: async () => {
      const response = await client.get(`/audit/resource/users/${uuid}`, { params: { limit: 20 } })
      return response.data
    },
    enabled: !!uuid,
    staleTime: 30000,
  })

  const items = data?.items ?? []

  if (isLoading) {
    return (
      <Card className="bg-dark-800 border-dark-700">
        <CardHeader><CardTitle className="text-white text-base">{t('userDetail.history.title')}</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
        </CardContent>
      </Card>
    )
  }

  if (items.length === 0) return null

  return (
    <Card className="bg-dark-800 border-dark-700">
      <CardHeader>
        <CardTitle className="text-white text-base flex items-center gap-2">
          <Clock className="w-4 h-4 text-primary-400" />
          {t('userDetail.history.title')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative pl-6 space-y-4">
          {/* Timeline line */}
          <div className="absolute left-[9px] top-2 bottom-2 w-px bg-dark-600" />
          {items.map((item) => {
            const dot = item.action?.indexOf('.') ?? -1
            const action = dot > 0 ? item.action.slice(dot + 1) : item.action
            return (
              <div key={item.id} className="relative">
                {/* Timeline dot */}
                <div className="absolute -left-6 top-1 w-[7px] h-[7px] rounded-full bg-primary-400 ring-2 ring-dark-800" />
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-sm font-medium text-white">{item.admin_username}</span>
                  <Badge variant="outline" className="text-xs bg-dark-700 border-dark-600">
                    {action}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {item.created_at ? formatDate(item.created_at) : ''}
                  </span>
                </div>
                {item.details && (
                  <p className="text-xs text-dark-300 mt-0.5 truncate max-w-md">{item.details}</p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}


const IP_DEFAULT_LIMIT = 10

interface IpHistoryItem {
  ip: string
  country: string
  city: string
  asn_org: string
  connections: number
  last_seen: string | null
}

function IpHistoryCard({ userUuid }: { userUuid: string }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const [period, setPeriod] = useState('24h')
  const [showAll, setShowAll] = useState(false)
  const [copiedIp, setCopiedIp] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['user-ips', userUuid, period],
    queryFn: async () => {
      const { data } = await client.get(`/users/${userUuid}/ip-history`, { params: { period } })
      return data as { items: IpHistoryItem[]; total: number }
    },
  })

  const items = data?.items || []
  const visible = showAll ? items : items.slice(0, IP_DEFAULT_LIMIT)
  const hasMore = items.length > IP_DEFAULT_LIMIT && !showAll

  const copyIp = (ip: string) => {
    navigator.clipboard.writeText(ip)
    setCopiedIp(ip)
    setTimeout(() => setCopiedIp(null), 1500)
  }

  // Reset showAll when period changes
  useEffect(() => { setShowAll(false) }, [period])

  return (
    <Card className="animate-fade-in-up" style={{ animationDelay: '0.18s' }}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Network className="h-5 w-5 text-primary-400" />
            {t('userDetail.ips.title')}
            {items.length > 0 && (
              <Badge variant="secondary" className="ml-1">{items.length}</Badge>
            )}
          </CardTitle>
          <div className="flex gap-1">
            {(['24h', '7d', '30d'] as const).map((p) => (
              <Button
                key={p}
                variant={period === p ? 'default' : 'ghost'}
                size="sm"
                className="h-7 px-2.5 text-xs"
                onClick={() => setPeriod(p)}
              >
                {t(`userDetail.ips.periods.${p}`)}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-6 text-dark-300 text-sm">
            {t('userDetail.ips.noData')}
          </div>
        ) : (
          <div className="space-y-1">
            {/* Header */}
            <div className="grid grid-cols-[1fr_auto_auto] sm:grid-cols-[1fr_1fr_auto_auto] gap-2 px-2 pb-1 text-[10px] text-dark-300 uppercase tracking-wider">
              <span>{t('userDetail.ips.ip')}</span>
              <span className="hidden sm:block">{t('userDetail.ips.city')}</span>
              <span className="text-right">{t('userDetail.ips.connections')}</span>
              <span className="text-right w-[80px]">{t('userDetail.ips.lastSeen')}</span>
            </div>
            {/* Rows */}
            {visible.map((item) => (
              <div
                key={item.ip}
                className="grid grid-cols-[1fr_auto_auto] sm:grid-cols-[1fr_1fr_auto_auto] gap-2 items-center px-2 py-1.5 rounded-md hover:bg-dark-600/30 transition-colors group"
              >
                <div className="flex flex-col min-w-0">
                  <button
                    onClick={() => copyIp(item.ip)}
                    className="font-mono text-sm text-white truncate text-left hover:text-primary-400 transition-colors"
                    title={copiedIp === item.ip ? 'Copied!' : item.ip}
                  >
                    {copiedIp === item.ip ? (
                      <span className="flex items-center gap-1">
                        <Check className="h-3 w-3 text-green-400" />
                        {item.ip}
                      </span>
                    ) : (
                      item.ip
                    )}
                  </button>
                  {item.asn_org && (
                    <span className="text-[10px] text-dark-300 truncate">{item.asn_org}</span>
                  )}
                  {/* Mobile-only city */}
                  {(item.city || item.country) && (
                    <span className="text-[10px] text-dark-300 sm:hidden">
                      {[item.city, item.country].filter(Boolean).join(', ')}
                    </span>
                  )}
                </div>
                <span className="hidden sm:block text-xs text-dark-200 truncate">
                  {[item.city, item.country].filter(Boolean).join(', ') || '—'}
                </span>
                <span className="text-xs font-mono text-dark-100 text-right">
                  {item.connections}
                </span>
                <span className="text-[11px] text-dark-300 text-right w-[80px]">
                  {item.last_seen ? formatDate(item.last_seen) : '—'}
                </span>
              </div>
            ))}
            {/* Show all button */}
            {hasMore && (
              <button
                onClick={() => setShowAll(true)}
                className="w-full text-center py-2 text-xs text-primary-400 hover:text-primary-300 transition-colors"
              >
                {t('userDetail.ips.showAll', { count: items.length })}
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function UserDetail() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const { uuid } = useParams<{ uuid: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [qrDialogOpen, setQrDialogOpen] = useState(false)
  const qrRef = useRef<HTMLDivElement>(null)
  const canEdit = useHasPermission('users', 'edit')
  const canDelete = useHasPermission('users', 'delete')
  const [isEditing, setIsEditing] = useState(searchParams.get('edit') === '1' && canEdit)
  const [editForm, setEditForm] = useState<EditFormData>({
    status: '',
    traffic_limit_bytes: null,
    traffic_limit_gb: '',
    traffic_limit_strategy: 'NO_RESET',
    is_unlimited: false,
    expire_at: '',
    hwid_device_limit: '',
    description: '',
    tag: '',
    email: '',
    telegram_id: '',
  })
  const [editError, setEditError] = useState('')
  const [editSuccess, setEditSuccess] = useState(false)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  useEffect(() => {
    return () => { timersRef.current.forEach(clearTimeout) }
  }, [])
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showRevokeFullConfirm, setShowRevokeFullConfirm] = useState(false)
  const [showRevokePasswordsConfirm, setShowRevokePasswordsConfirm] = useState(false)
  const [exclusionDialogOpen, setExclusionDialogOpen] = useState(false)
  const [selectedExclusions, setSelectedExclusions] = useState<Set<string>>(new Set())
  const [exclusionMode, setExclusionMode] = useState<'full' | 'partial' | 'none'>('none')

  // Reset exclusion dialog state on open
  useEffect(() => {
    if (exclusionDialogOpen) {
      setExclusionMode('none')
      setSelectedExclusions(new Set())
    }
  }, [exclusionDialogOpen])

  const exclusionMutation = useMutation({
    mutationFn: (body: { user_uuid: string; excluded_analyzers?: string[]; reason?: string }) =>
      client.post('/violations/whitelist', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      toast.success(t('violations.toast.whitelistAdded'))
      setExclusionDialogOpen(false)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

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
      toast.success(t('userDetail.toasts.hwidSynced'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.syncError'))
    },
  })

  // Delete single HWID device
  const [deviceToDelete, setDeviceToDelete] = useState<string | null>(null)
  const deleteDeviceMutation = useMutation({
    mutationFn: async (deviceId: string) => {
      await client.delete(`/users/${uuid}/hwid-devices/${deviceId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-hwid-devices', uuid] })
      queryClient.invalidateQueries({ queryKey: ['user', uuid] })
      toast.success(t('userDetail.toasts.deviceDeleted', 'HWID устройство удалено'))
      setDeviceToDelete(null)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.deleteError'))
    },
  })

  // Delete all HWID devices
  const [showDeleteAllDevices, setShowDeleteAllDevices] = useState(false)
  const deleteAllDevicesMutation = useMutation({
    mutationFn: async () => {
      await client.delete(`/users/${uuid}/hwid-devices`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-hwid-devices', uuid] })
      queryClient.invalidateQueries({ queryKey: ['user', uuid] })
      toast.success(t('userDetail.toasts.allDevicesDeleted', 'Все HWID устройства удалены'))
      setShowDeleteAllDevices(false)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.deleteError'))
    },
  })

  // Initialize edit form when user data loads
  useEffect(() => {
    if (user) {
      setEditForm({
        status: user.status,
        traffic_limit_bytes: user.traffic_limit_bytes,
        traffic_limit_gb: bytesToGb(user.traffic_limit_bytes),
        traffic_limit_strategy: user.traffic_limit_strategy || 'NO_RESET',
        is_unlimited: !user.traffic_limit_bytes,
        expire_at: formatDateForInput(user.expire_at),
        hwid_device_limit: String(user.hwid_device_limit),
        description: user.description || '',
        tag: user.tag || '',
        email: user.email || '',
        telegram_id: user.telegram_id ? String(user.telegram_id) : '',
      })
    }
  }, [user])

  // Mutations
  const enableMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/enable`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success(t('userDetail.toasts.userEnabled')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.error')) },
  })
  const disableMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/disable`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success(t('userDetail.toasts.userDisabled')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.error')) },
  })
  const resetTrafficMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/reset-traffic`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success(t('userDetail.toasts.trafficReset')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.error')) },
  })
  const revokeFullMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/revoke`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success(t('userDetail.subscription.revokeFullSuccess')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.error')) },
  })
  const revokePasswordsMutation = useMutation({
    mutationFn: async () => { await client.post(`/users/${uuid}/revoke?passwords_only=true`) },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['user', uuid] }); toast.success(t('userDetail.subscription.revokePasswordsSuccess')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.error')) },
  })
  const deleteMutation = useMutation({
    mutationFn: async () => { await client.delete(`/users/${uuid}`) },
    onSuccess: () => { toast.success(t('userDetail.toasts.userDeleted')); navigate('/users') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('userDetail.toasts.deleteError')) },
  })

  const updateUserMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const response = await client.patch(`/users/${uuid}`, data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', uuid] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('userDetail.toasts.userUpdated'))
      setEditSuccess(true)
      setEditError('')
      timersRef.current.push(setTimeout(() => setEditSuccess(false), 3000))
      setIsEditing(false)
      setSearchParams({})
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || t('userDetail.toasts.saveError'))
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

    // Traffic limit strategy
    if (user && editForm.traffic_limit_strategy !== (user.traffic_limit_strategy || 'NO_RESET')) {
      updateData.traffic_limit_strategy = editForm.traffic_limit_strategy
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

    // Description
    const newDesc = editForm.description.trim()
    if (user && newDesc !== (user.description || '')) {
      updateData.description = newDesc || null
    }

    // Tag
    const newTag = editForm.tag.trim().toUpperCase()
    if (user && newTag !== (user.tag || '')) {
      updateData.tag = newTag || null
    }

    // Email
    const newEmail = editForm.email.trim()
    if (user && newEmail !== (user.email || '')) {
      updateData.email = newEmail || null
    }

    // Telegram ID
    const newTgId = editForm.telegram_id.trim() ? parseInt(editForm.telegram_id, 10) : null
    if (user && newTgId !== user.telegram_id) {
      updateData.telegram_id = newTgId
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
        traffic_limit_strategy: user.traffic_limit_strategy || 'NO_RESET',
        is_unlimited: !user.traffic_limit_bytes,
        expire_at: formatDateForInput(user.expire_at),
        hwid_device_limit: String(user.hwid_device_limit),
        description: user.description || '',
        tag: user.tag || '',
        email: user.email || '',
        telegram_id: user.telegram_id ? String(user.telegram_id) : '',
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
    timersRef.current.push(setTimeout(() => setCopied(false), 2000))
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
            <p className="text-red-400 font-medium">{t('userDetail.notFound')}</p>
          </div>
          <Button variant="link" onClick={() => navigate('/users')} className="px-0">
            <ArrowLeft className="h-4 w-4 mr-1" />
            {t('userDetail.backToList')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  const trafficPercent = user.traffic_limit_bytes
    ? Math.min((user.used_traffic_bytes / user.traffic_limit_bytes) * 100, 100)
    : 0

  const statusBadge = getStatusBadge(user.status, t)
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
              {user.tag && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20">{user.tag}</span>
              )}
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
                {updateUserMutation.isPending ? t('userDetail.actions.saving') : t('userDetail.actions.save')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelEdit}
                disabled={updateUserMutation.isPending}
              >
                <X className="h-4 w-4 mr-1.5" />
                {t('userDetail.actions.cancel')}
              </Button>
            </>
          ) : (
            <>
              {canEdit && (
                <Button size="sm" onClick={handleStartEdit}>
                  <Pencil className="h-4 w-4 mr-1.5" />
                  {t('userDetail.actions.edit')}
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
                    {t('userDetail.actions.disable')}
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => enableMutation.mutate()}
                    disabled={enableMutation.isPending}
                    className="bg-green-600 hover:bg-green-500 text-white"
                  >
                    <Check className="h-4 w-4 mr-1.5" />
                    {t('userDetail.actions.enable')}
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
                  {t('userDetail.actions.resetTraffic')}
                </Button>
              )}
              {canDelete && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={deleteMutation.isPending}
                  className="text-red-400 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />
                  {t('userDetail.actions.delete')}
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
            <p className="text-green-400 text-sm">{t('userDetail.changesSaved')}</p>
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
                    {t('userDetail.editing')}
                  </>
                ) : (
                  <>
                    <Eye className="h-5 w-5 text-primary-400" />
                    {t('userDetail.generalInfo')}
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
                    <Label>{t('userDetail.fields.status')}</Label>
                    <Select
                      value={editForm.status}
                      onValueChange={(value) => setEditForm({ ...editForm, status: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={t('userDetail.fields.selectStatus')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">{t('userDetail.statuses.active')}</SelectItem>
                        <SelectItem value="disabled">{t('userDetail.statuses.disabled')}</SelectItem>
                        <SelectItem value="limited">{t('userDetail.statuses.limited')}</SelectItem>
                        <SelectItem value="expired">{t('userDetail.statuses.expired')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Description */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.description')}</Label>
                    <Input
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      placeholder={t('userDetail.fields.descriptionPlaceholder')}
                    />
                  </div>

                  {/* Tag */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.tag')}</Label>
                    <Input
                      value={editForm.tag}
                      onChange={(e) => setEditForm({ ...editForm, tag: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })}
                      placeholder="MY_TAG"
                      maxLength={16}
                      className="font-mono"
                    />
                    <p className="text-xs text-dark-300">{t('userDetail.fields.tagHint')}</p>
                  </div>

                  {/* Email */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.email')}</Label>
                    <Input
                      type="email"
                      value={editForm.email}
                      onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                      placeholder="user@example.com"
                    />
                  </div>

                  {/* Telegram ID */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.telegramId')}</Label>
                    <Input
                      type="number"
                      value={editForm.telegram_id}
                      onChange={(e) => setEditForm({ ...editForm, telegram_id: e.target.value })}
                      placeholder="123456789"
                    />
                  </div>

                  {/* Traffic limit */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.trafficLimit')}</Label>
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
                        <span className="text-sm text-dark-100">{t('userDetail.trafficUnlimited')}</span>
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
                          placeholder={t('userDetail.fields.enterLimit')}
                          className="pr-12"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-dark-200">{t('userDetail.fields.gb')}</span>
                      </div>
                    )}
                  </div>

                  {/* Traffic reset strategy */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.trafficReset')}</Label>
                    <Select
                      value={editForm.traffic_limit_strategy}
                      onValueChange={(value) => setEditForm({ ...editForm, traffic_limit_strategy: value })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="NO_RESET">{t('userDetail.strategies.noReset')}</SelectItem>
                        <SelectItem value="DAY">{t('userDetail.strategies.daily')}</SelectItem>
                        <SelectItem value="WEEK">{t('userDetail.strategies.weekly')}</SelectItem>
                        <SelectItem value="MONTH">{t('userDetail.strategies.monthly')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Expire date */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.expireDate')}</Label>
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
                        {t('userDetail.fields.removeDate')}
                      </Button>
                    )}
                  </div>

                  {/* HWID limit */}
                  <div className="space-y-2">
                    <Label>{t('userDetail.fields.hwidLimit')}</Label>
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
                    <p className="text-xs text-dark-300 mb-3">{t('userDetail.fields.readOnly')}</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <p className="text-xs text-dark-200">Username</p>
                        <p className="text-white text-sm">{user.username || '\u2014'}</p>
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
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-dark-200">Username</p>
                      <p className="text-white">{user.username || '\u2014'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-dark-200">{t('userDetail.fields.email')}</p>
                      <p className="text-white truncate">{user.email || '\u2014'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-dark-200">{t('userDetail.fields.telegramId')}</p>
                      <p className="text-white">{user.telegram_id || '\u2014'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-dark-200">Short UUID</p>
                      <p className="text-white font-mono">{user.short_uuid || '\u2014'}</p>
                    </div>
                    {user.tag && (
                      <div>
                        <p className="text-sm text-dark-200">{t('userDetail.fields.tag')}</p>
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20">{user.tag}</span>
                      </div>
                    )}
                    {user.description && (
                      <div className="sm:col-span-2">
                        <p className="text-sm text-dark-200">{t('userDetail.fields.description')}</p>
                        <p className="text-white text-sm">{user.description}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-sm text-dark-200">{t('userDetail.fields.trafficReset')}</p>
                      <p className="text-white">
                        {{ NO_RESET: t('userDetail.strategies.noReset'), DAY: t('userDetail.strategies.daily'), WEEK: t('userDetail.strategies.weekly'), MONTH: t('userDetail.strategies.monthly') }[user.traffic_limit_strategy || 'NO_RESET'] || user.traffic_limit_strategy || '\u2014'}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <Clock className="h-3.5 w-3.5 text-dark-300" />
                        <p className="text-sm text-dark-200">{t('userDetail.fields.created')}</p>
                      </div>
                      <p className="text-white">
                        {user.created_at
                          ? formatDate(user.created_at)
                          : '\u2014'}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <Clock className="h-3.5 w-3.5 text-dark-300" />
                        <p className="text-sm text-dark-200">{t('userDetail.fields.expires')}</p>
                      </div>
                      <p className="text-white">
                        {user.expire_at
                          ? formatDate(user.expire_at)
                          : t('userDetail.indefinite')}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <Activity className="h-3.5 w-3.5 text-dark-300" />
                        <p className="text-sm text-dark-200">{t('userDetail.fields.lastActivity')}</p>
                      </div>
                      <p className="text-white">
                        {user.online_at
                          ? formatDate(user.online_at)
                          : '\u2014'}
                      </p>
                    </div>
                    {user.last_traffic_reset_at && (
                      <div>
                        <p className="text-sm text-dark-200">{t('userDetail.fields.lastTrafficReset')}</p>
                        <p className="text-white">
                          {formatDate(user.last_traffic_reset_at)}
                        </p>
                      </div>
                    )}
                    {user.first_connected_at && (
                      <div>
                        <p className="text-sm text-dark-200">{t('userDetail.fields.firstConnection')}</p>
                        <p className="text-white">
                          {formatDate(user.first_connected_at)}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Internal squads */}
                  {user.active_internal_squads && user.active_internal_squads.length > 0 && (
                    <>
                      <Separator />
                      <div>
                        <p className="text-sm text-dark-200 mb-2">{t('userDetail.internalSquads')}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {user.active_internal_squads.map((sq) => (
                            <Badge key={sq.uuid} variant="outline" className="text-xs">{sq.name}</Badge>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {/* Protocol credentials */}
                  {(user.trojan_password || user.vless_uuid || user.ss_password) && (
                    <>
                      <Separator />
                      <div>
                        <p className="text-sm text-dark-200 mb-2">{t('userDetail.protocols')}</p>
                        <div className="grid grid-cols-1 gap-2">
                          {user.vless_uuid && (
                            <div className="bg-dark-700/40 rounded-lg p-2.5">
                              <p className="text-xs text-dark-300 mb-0.5">VLESS UUID</p>
                              <p className="text-xs font-mono text-white break-all">{user.vless_uuid}</p>
                            </div>
                          )}
                          {user.trojan_password && (
                            <div className="bg-dark-700/40 rounded-lg p-2.5">
                              <p className="text-xs text-dark-300 mb-0.5">Trojan Password</p>
                              <p className="text-xs font-mono text-white break-all">{user.trojan_password}</p>
                            </div>
                          )}
                          {user.ss_password && (
                            <div className="bg-dark-700/40 rounded-lg p-2.5">
                              <p className="text-xs text-dark-300 mb-0.5">Shadowsocks Password</p>
                              <p className="text-xs font-mono text-white break-all">{user.ss_password}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
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
                  {t('userDetail.devices.title')}
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
                    title={t('userDetail.devices.sync')}
                  >
                    <RefreshCw className={cn('h-4 w-4', syncHwidMutation.isPending && 'animate-spin')} />
                  </Button>
                  <Badge variant="outline" className="text-xs">
                    {t('userDetail.devices.limitLabel')}: {user.hwid_device_limit || '\u221E'}
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* HWID device cards with pagination */}
              {hwidDevices && hwidDevices.length > 0 ? (
                <PaginatedDeviceList
                  devices={hwidDevices}
                  onDeleteDevice={setDeviceToDelete}
                  onDeleteAll={() => setShowDeleteAllDevices(true)}
                />
              ) : (
                <div className="text-center py-6 text-dark-300 text-sm">
                  {t('userDetail.devices.noDevices')}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Block: IP Addresses */}
          <IpHistoryCard userUuid={uuid!} />

          {/* Block: Violations */}
          {violations && violations.length > 0 && (
            <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-yellow-400" />
                  {t('userDetail.violations.title')}
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
                          {formatDate(v.detected_at)}
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
                {t('userDetail.subscription.title')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {user.subscription_url ? (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.link')}</p>
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
                            {t('userDetail.subscription.copy')}
                          </>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setQrDialogOpen(true)}
                        className="flex-shrink-0"
                      >
                        <QrCode className="h-3.5 w-3.5 mr-1" />
                        QR
                      </Button>
                    </div>
                  </div>
                ) : user.subscription_uuid ? (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.uuid')}</p>
                    <p className="text-white text-sm font-mono break-all">{user.subscription_uuid}</p>
                  </div>
                ) : (
                  <p className="text-dark-200 text-sm">{t('userDetail.subscription.noActive')}</p>
                )}
                {user.subscription_url && user.subscription_uuid && (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.uuid')}</p>
                    <p className="text-dark-100 text-xs font-mono break-all">{user.subscription_uuid}</p>
                  </div>
                )}
                {user.sub_last_opened_at && (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.lastOpened')}</p>
                    <p className="text-dark-100 text-xs">
                      {formatDate(user.sub_last_opened_at)}
                    </p>
                  </div>
                )}
                {user.sub_revoked_at && (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.revoked')}</p>
                    <p className="text-red-400 text-xs">
                      {formatDate(user.sub_revoked_at)}
                    </p>
                  </div>
                )}
                {user.sub_last_user_agent && (
                  <div>
                    <p className="text-xs text-dark-200 mb-1">{t('userDetail.subscription.userAgent')}</p>
                    <p className="text-dark-100 text-xs truncate" title={user.sub_last_user_agent}>{user.sub_last_user_agent}</p>
                  </div>
                )}
                {canEdit && (
                  <div className="pt-3 border-t border-dark-400/20 grid grid-cols-2 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-amber-400 hover:text-amber-300"
                      onClick={() => setShowRevokeFullConfirm(true)}
                      disabled={revokeFullMutation.isPending}
                    >
                      <RefreshCw className={cn('h-3.5 w-3.5', revokeFullMutation.isPending && 'animate-spin')} />
                      {t('userDetail.subscription.revokeFull')}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => setShowRevokePasswordsConfirm(true)}
                      disabled={revokePasswordsMutation.isPending}
                    >
                      <KeyRound className={cn('h-3.5 w-3.5', revokePasswordsMutation.isPending && 'animate-pulse')} />
                      {t('userDetail.subscription.revokePasswords')}
                    </Button>
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
                    <p className="text-sm text-dark-200">{t('userDetail.antiAbuse.trustScore')}</p>
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
                    <p className="text-xs text-dark-200">{t('userDetail.antiAbuse.violations30d')}</p>
                  </div>
                  <div className="bg-dark-600 rounded-lg p-3 text-center">
                    <div className="flex justify-center mb-1">
                      <Users className="h-4 w-4 text-dark-300" />
                    </div>
                    <p className="text-xl md:text-2xl font-bold text-white">{user.active_connections}</p>
                    <p className="text-xs text-dark-200">{t('userDetail.antiAbuse.connections')}</p>
                  </div>
                </div>
                <div className="bg-dark-600 rounded-lg p-3 text-center">
                  <div className="flex justify-center mb-1">
                    <Globe className="h-4 w-4 text-dark-300" />
                  </div>
                  <p className="text-xl md:text-2xl font-bold text-white">{user.unique_ips_24h}</p>
                  <p className="text-xs text-dark-200">{t('userDetail.antiAbuse.uniqueIps24h')}</p>
                </div>
                {/* Exclusion settings button */}
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full gap-2 mt-2"
                  onClick={() => setExclusionDialogOpen(true)}
                >
                  <Settings className="w-4 h-4" />
                  {t('violations.exclusions.configureButton')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* History */}
      <UserHistory uuid={uuid!} />

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title={t('userDetail.deleteConfirm.title')}
        description={t('userDetail.deleteConfirm.description')}
        confirmLabel={t('userDetail.deleteConfirm.confirm')}
        variant="destructive"
        onConfirm={() => { deleteMutation.mutate(); setShowDeleteConfirm(false) }}
      />

      {/* Revoke full subscription confirm */}
      <ConfirmDialog
        open={showRevokeFullConfirm}
        onOpenChange={setShowRevokeFullConfirm}
        title={t('userDetail.subscription.revokeFullConfirm')}
        description={t('userDetail.subscription.revokeFullConfirmDesc')}
        confirmLabel={t('userDetail.subscription.revokeFull')}
        variant="destructive"
        onConfirm={() => { revokeFullMutation.mutate(); setShowRevokeFullConfirm(false) }}
      />

      {/* Revoke passwords only confirm */}
      <ConfirmDialog
        open={showRevokePasswordsConfirm}
        onOpenChange={setShowRevokePasswordsConfirm}
        title={t('userDetail.subscription.revokePasswordsConfirm')}
        description={t('userDetail.subscription.revokePasswordsConfirmDesc')}
        confirmLabel={t('userDetail.subscription.revokePasswords')}
        variant="destructive"
        onConfirm={() => { revokePasswordsMutation.mutate(); setShowRevokePasswordsConfirm(false) }}
      />

      {/* Delete single HWID device confirm */}
      <ConfirmDialog
        open={!!deviceToDelete}
        onOpenChange={(open) => !open && setDeviceToDelete(null)}
        title={t('userDetail.devices.deleteConfirm.title', 'Удалить HWID устройство?')}
        description={t('userDetail.devices.deleteConfirm.description', 'Это действие нельзя отменить. Устройство будет удалено из системы.')}
        confirmLabel={t('userDetail.devices.deleteConfirm.confirm', 'Удалить')}
        variant="destructive"
        onConfirm={() => deviceToDelete && deleteDeviceMutation.mutate(deviceToDelete)}
      />

      {/* Delete all HWID devices confirm */}
      <ConfirmDialog
        open={showDeleteAllDevices}
        onOpenChange={setShowDeleteAllDevices}
        title={t('userDetail.devices.deleteAllConfirm.title', 'Удалить все HWID устройства?')}
        description={t('userDetail.devices.deleteAllConfirm.description', 'Это действие нельзя отменить. Все устройства пользователя будут удалены из системы.')}
        confirmLabel={t('userDetail.devices.deleteAllConfirm.confirm', 'Удалить все')}
        variant="destructive"
        onConfirm={() => deleteAllDevicesMutation.mutate()}
      />

      {/* QR Code Dialog */}
      <Dialog open={qrDialogOpen} onOpenChange={setQrDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5" />
              {t('userDetail.subscription.qrTitle')}
            </DialogTitle>
            <DialogDescription>
              {t('userDetail.subscription.qrDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center gap-4">
            <div ref={qrRef} className="bg-white p-4 rounded-lg">
              <QRCodeSVG
                value={user?.subscription_url || ''}
                size={256}
                level="M"
              />
            </div>
            <p className="text-xs text-dark-300 text-center font-mono break-all px-2">
              {user?.subscription_url}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const svg = qrRef.current?.querySelector('svg')
                if (!svg) return
                const svgData = new XMLSerializer().serializeToString(svg)
                const canvas = document.createElement('canvas')
                const ctx = canvas.getContext('2d')
                const img = new Image()
                img.onload = () => {
                  canvas.width = img.width
                  canvas.height = img.height
                  ctx?.drawImage(img, 0, 0)
                  const a = document.createElement('a')
                  a.download = `subscription-qr-${user?.short_uuid || 'code'}.png`
                  a.href = canvas.toDataURL('image/png')
                  a.click()
                }
                img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)))
              }}
            >
              <Download className="h-3.5 w-3.5 mr-1" />
              {t('userDetail.subscription.qrDownload')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Analyzer Exclusions Dialog */}
      <Dialog open={exclusionDialogOpen} onOpenChange={setExclusionDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldOff className="h-5 w-5" />
              {t('violations.exclusions.configureTitle')}
            </DialogTitle>
            <DialogDescription>
              {user?.username || uuid}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-3 gap-2">
              {(['none', 'partial', 'full'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => { setExclusionMode(mode); if (mode !== 'partial') setSelectedExclusions(new Set()) }}
                  className={cn(
                    'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                    exclusionMode === mode
                      ? mode === 'full' ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                        : mode === 'partial' ? 'bg-amber-600/20 text-amber-400 border-amber-500/30'
                        : 'bg-dark-600 text-white border-dark-400/30'
                      : 'bg-dark-700/50 text-dark-200 border-dark-400/20 hover:text-white hover:border-dark-400/40'
                  )}
                >
                  {t(`violations.exclusions.mode_${mode}`)}
                </button>
              ))}
            </div>
            {exclusionMode === 'partial' && (
              <div className="space-y-1.5">
                {ANALYZER_KEYS.map(key => (
                  <label
                    key={key}
                    className={cn(
                      'flex items-center gap-2.5 px-3 py-2 rounded-md cursor-pointer transition-all border',
                      selectedExclusions.has(key)
                        ? 'bg-amber-600/10 border-amber-500/30 text-amber-300'
                        : 'bg-dark-700/30 border-dark-400/15 text-dark-200 hover:border-dark-400/30'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedExclusions.has(key)}
                      onChange={() => {
                        setSelectedExclusions(prev => {
                          const next = new Set(prev)
                          if (next.has(key)) next.delete(key); else next.add(key)
                          return next
                        })
                      }}
                      className="rounded border-dark-400/30 bg-dark-800 text-primary-500 focus:ring-primary-500/40"
                    />
                    <span className="text-sm">{t(`violations.analyzers.${key}`)}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setExclusionDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            {exclusionMode === 'none' ? (
              <Button
                variant="outline"
                onClick={() => {
                  if (uuid) client.delete(`/violations/whitelist/${uuid}`).then(() => {
                    toast.success(t('violations.toast.whitelistRemoved'))
                    setExclusionDialogOpen(false)
                  }).catch(() => toast.error(t('common.error')))
                }}
              >
                {t('violations.exclusions.removeWhitelist')}
              </Button>
            ) : (
              <Button
                onClick={() => {
                  if (!uuid) return
                  exclusionMutation.mutate({
                    user_uuid: uuid,
                    excluded_analyzers: exclusionMode === 'partial' && selectedExclusions.size > 0
                      ? Array.from(selectedExclusions) : undefined,
                    reason: exclusionMode === 'full' ? 'Full whitelist via user detail' : 'Partial exclusion via user detail',
                  })
                }}
                className="gap-2"
              >
                <ShieldOff className="w-4 h-4" />
                {t('common.save')}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
