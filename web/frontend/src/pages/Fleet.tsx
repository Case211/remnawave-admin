import { useState, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import {
  Activity,
  RefreshCw,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  BarChart3,
  Wifi,
  WifiOff,
  Play,
  Square,
  RotateCcw,
  Server,
  Zap,
  Globe,
  ShieldCheck,
  ShieldAlert,
  Search,
  HardDrive,
  Cpu,
  MemoryStick,
  Users,
  ArrowUpDown,
  FileCode,
  History,
} from 'lucide-react'
import client from '../api/client'
import { usePermissionStore } from '../store/permissionStore'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import NodeCard, { type FleetNode, getNodeStatus } from '@/components/fleet/NodeCard'
import TerminalDialog from '@/components/fleet/TerminalDialog'
import type { Script } from '@/components/fleet/ScriptCatalog'

const ScriptCatalog = lazy(() => import('@/components/fleet/ScriptCatalog'))
const RunScriptDialog = lazy(() => import('@/components/fleet/RunScriptDialog'))
const CommandHistory = lazy(() => import('@/components/fleet/CommandHistory'))

// ── Types ────────────────────────────────────────────────────────

interface FleetResponse {
  nodes: FleetNode[]
  total: number
  online: number
  offline: number
  disabled: number
}

type SortField = 'name' | 'status' | 'cpu' | 'ram' | 'disk' | 'speed' | 'users' | 'traffic' | 'uptime'
type SortDir = 'asc' | 'desc'
type StatusFilter = 'all' | 'online' | 'offline' | 'disabled'

// ── API ──────────────────────────────────────────────────────────

const fetchFleet = async (): Promise<FleetResponse> => {
  const { data } = await client.get('/analytics/node-fleet')
  return data
}

// ── Utilities ────────────────────────────────────────────────────

function getCpuColor(cpu: number | null): string {
  if (cpu == null) return 'text-dark-300'
  if (cpu >= 95) return 'text-red-400'
  if (cpu >= 80) return 'text-yellow-400'
  return 'text-white'
}

function getRamColor(ram: number | null): string {
  if (ram == null) return 'text-dark-300'
  if (ram >= 95) return 'text-red-400'
  if (ram >= 80) return 'text-yellow-400'
  return 'text-white'
}

// ── Sort field labels ────────────────────────────────────────────

const SORT_FIELDS: { value: SortField; labelKey: string }[] = [
  { value: 'status', labelKey: 'fleet.table.status' },
  { value: 'name', labelKey: 'fleet.table.node' },
  { value: 'cpu', labelKey: 'fleet.table.cpu' },
  { value: 'ram', labelKey: 'fleet.table.ram' },
  { value: 'disk', labelKey: 'fleet.table.disk' },
  { value: 'speed', labelKey: 'fleet.table.speed' },
  { value: 'users', labelKey: 'fleet.table.users' },
  { value: 'traffic', labelKey: 'fleet.table.traffic' },
  { value: 'uptime', labelKey: 'fleet.table.uptime' },
]

// ── Node Detail Panel ────────────────────────────────────────────

function NodeDetailPanel({
  node,
  canEdit,
  onRestart,
  onEnable,
  onDisable,
  isPending,
}: {
  node: FleetNode
  canEdit: boolean
  onRestart: () => void
  onEnable: () => void
  onDisable: () => void
  isPending: boolean
}) {
  const { t } = useTranslation()
  const { formatBytes, formatSpeed, formatTimeAgo } = useFormatters()
  const status = getNodeStatus(node)

  const formatUptime = (seconds: number | null | undefined): string => {
    if (!seconds || seconds <= 0) return '-'
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d > 0) return t('fleet.detail.uptimeDaysHours', { days: d, hours: h })
    if (h > 0) return t('fleet.detail.uptimeHoursMinutes', { hours: h, minutes: m })
    return t('fleet.detail.uptimeMinutes', { minutes: m })
  }

  return (
    <div className="animate-fade-in">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Column 1: Connection info */}
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">{t('fleet.detail.info')}</h4>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Globe className="w-3.5 h-3.5 text-dark-300" />
              <span className="text-dark-200">{t('fleet.detail.address')}</span>
              <span className="text-white ml-auto font-mono text-xs">{node.address}:{node.port}</span>
            </div>
            <div className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-yellow-400" />
              <span className="text-dark-200">Xray</span>
              <span className="text-white ml-auto font-mono text-xs">{node.xray_version || '-'}</span>
            </div>
            <div className="flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-dark-300" />
              <span className="text-dark-200">{t('fleet.detail.xrayRunning')}</span>
              <span className="ml-auto">
                {node.is_xray_running ? (
                  <ShieldCheck className="w-4 h-4 text-green-400" />
                ) : (
                  <ShieldAlert className="w-4 h-4 text-red-400" />
                )}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-dark-300" />
              <span className="text-dark-200">{t('fleet.detail.lastSeen')}</span>
              <span className="text-white ml-auto text-xs">{node.last_seen_at ? formatTimeAgo(node.last_seen_at) : t('fleet.statusNever')}</span>
            </div>
          </div>
        </div>

        {/* Column 2: Detailed metrics */}
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">{t('fleet.detail.metrics')}</h4>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-dark-200">CPU</span>
              <span className={cn('ml-auto font-mono', getCpuColor(node.cpu_usage))}>
                {node.cpu_usage != null ? `${node.cpu_usage.toFixed(1)}%` : '-'}
              </span>
            </div>
            {node.cpu_usage != null && (
              <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-500',
                    node.cpu_usage >= 95 ? 'bg-red-500' : node.cpu_usage >= 80 ? 'bg-yellow-500' : 'bg-green-500',
                  )}
                  style={{ width: `${Math.min(node.cpu_usage, 100)}%` }}
                />
              </div>
            )}
            <div className="flex items-center gap-2">
              <MemoryStick className="w-3.5 h-3.5 text-pink-400" />
              <span className="text-dark-200">RAM</span>
              <span className={cn('ml-auto font-mono', getRamColor(node.memory_usage))}>
                {node.memory_usage != null ? `${node.memory_usage.toFixed(1)}%` : '-'}
              </span>
            </div>
            {node.memory_usage != null && (
              <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-500',
                    node.memory_usage >= 95 ? 'bg-red-500' : node.memory_usage >= 80 ? 'bg-yellow-500' : 'bg-cyan-500',
                  )}
                  style={{ width: `${Math.min(node.memory_usage, 100)}%` }}
                />
              </div>
            )}
            <div className="flex items-center gap-2">
              <HardDrive className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-dark-200">{t('fleet.detail.disk')}</span>
              <span className={cn('ml-auto font-mono', node.disk_usage != null && node.disk_usage >= 95 ? 'text-red-400' : node.disk_usage != null && node.disk_usage >= 80 ? 'text-yellow-400' : 'text-white')}>
                {node.disk_usage != null ? `${node.disk_usage.toFixed(1)}%` : '-'}
                {node.disk_total_bytes != null && <span className="text-dark-400 text-[10px] ml-1">({formatBytes(node.disk_used_bytes ?? 0)} / {formatBytes(node.disk_total_bytes)})</span>}
              </span>
            </div>
            {node.memory_total_bytes != null && (
              <div className="flex items-center gap-2">
                <MemoryStick className="w-3.5 h-3.5 text-dark-400" />
                <span className="text-dark-300 text-[10px]">
                  {formatBytes(node.memory_used_bytes ?? 0)} / {formatBytes(node.memory_total_bytes)}
                </span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <ArrowDownRight className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-dark-200">Download</span>
              <span className="text-white ml-auto font-mono text-xs">{formatSpeed(node.download_speed_bps)}</span>
            </div>
            <div className="flex items-center gap-2">
              <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-dark-200">Upload</span>
              <span className="text-white ml-auto font-mono text-xs">{formatSpeed(node.upload_speed_bps)}</span>
            </div>
          </div>
        </div>

        {/* Column 3: Actions + Traffic */}
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">{t('fleet.detail.trafficAndActions')}</h4>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-dark-200">{t('fleet.detail.today')}</span>
              <span className="text-white ml-auto font-mono text-xs">{formatBytes(node.traffic_today_bytes)}</span>
            </div>
            <div className="flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5 text-dark-300" />
              <span className="text-dark-200">{t('fleet.detail.total')}</span>
              <span className="text-white ml-auto font-mono text-xs">{formatBytes(node.traffic_total_bytes)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Users className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-dark-200">{t('fleet.detail.users')}</span>
              <span className="text-white ml-auto font-mono">{node.users_online}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-green-400" />
              <span className="text-dark-200">Uptime</span>
              <span className="text-white ml-auto font-mono text-xs">{formatUptime(node.uptime_seconds)}</span>
            </div>
          </div>

          {/* Quick actions */}
          {canEdit && (
            <>
              <Separator />
              <div className="flex items-center gap-2 pt-1">
                {status === 'online' && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-8 gap-1.5"
                        disabled={isPending}
                        onClick={onRestart}
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        {t('fleet.actions.restart')}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>{t('fleet.actions.restartTooltip')}</TooltipContent>
                  </Tooltip>
                )}
                {node.is_disabled ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-8 gap-1.5 text-green-400 hover:text-green-300"
                        disabled={isPending}
                        onClick={onEnable}
                      >
                        <Play className="w-3.5 h-3.5" />
                        {t('fleet.actions.enable')}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>{t('fleet.actions.enableTooltip')}</TooltipContent>
                  </Tooltip>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-8 gap-1.5 text-red-400 hover:text-red-300"
                        disabled={isPending}
                        onClick={onDisable}
                      >
                        <Square className="w-3.5 h-3.5" />
                        {t('fleet.actions.disable')}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>{t('fleet.actions.disableTooltip')}</TooltipContent>
                  </Tooltip>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────

export default function Fleet() {
  const { t } = useTranslation()
  const { formatSpeed } = useFormatters()
  const queryClient = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canEditNodes = hasPermission('fleet', 'edit')
  const canTerminal = hasPermission('fleet', 'terminal')
  const canScripts = hasPermission('fleet', 'scripts')

  const [activeTab, setActiveTab] = useState('monitoring')
  const [sortField, setSortField] = useState<SortField>('status')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Terminal state
  const [terminalNode, setTerminalNode] = useState<{ uuid: string; name: string } | null>(null)

  // Script state
  const [runScript, setRunScript] = useState<Script | null>(null)

  // ── Data ──────────────────────────────────────────────────────

  const { data: fleet, isLoading, refetch } = useQuery({
    queryKey: ['fleet'],
    queryFn: fetchFleet,
    refetchInterval: 15000,
  })

  // ── Mutations ─────────────────────────────────────────────────

  const restartNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/restart`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success(t('fleet.toast.restarted')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('fleet.toast.error')) },
  })

  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success(t('fleet.toast.enabled')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('fleet.toast.error')) },
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success(t('fleet.toast.disabled')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('fleet.toast.error')) },
  })

  const mutationPending = restartNode.isPending || enableNode.isPending || disableNode.isPending

  // ── Sorting ───────────────────────────────────────────────────

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const sortedNodes = useMemo(() => {
    if (!fleet?.nodes) return []
    let nodes = [...fleet.nodes]

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      nodes = nodes.filter(
        (n) => n.name.toLowerCase().includes(q) || n.address.toLowerCase().includes(q),
      )
    }

    // Filter by status
    if (statusFilter !== 'all') {
      nodes = nodes.filter((n) => getNodeStatus(n) === statusFilter)
    }

    const statusPriority = (n: FleetNode) => {
      if (!n.is_disabled && !n.is_connected) return 0 // offline first
      if (n.is_connected && !n.is_disabled) return 1  // online
      return 2                                          // disabled
    }

    nodes.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name':
          cmp = a.name.localeCompare(b.name)
          break
        case 'status':
          cmp = statusPriority(a) - statusPriority(b)
          break
        case 'cpu':
          cmp = (a.cpu_usage ?? -1) - (b.cpu_usage ?? -1)
          break
        case 'ram':
          cmp = (a.memory_usage ?? -1) - (b.memory_usage ?? -1)
          break
        case 'disk':
          cmp = (a.disk_usage ?? -1) - (b.disk_usage ?? -1)
          break
        case 'speed':
          cmp = (a.download_speed_bps + a.upload_speed_bps) - (b.download_speed_bps + b.upload_speed_bps)
          break
        case 'users':
          cmp = a.users_online - b.users_online
          break
        case 'traffic':
          cmp = a.traffic_today_bytes - b.traffic_today_bytes
          break
        case 'uptime':
          cmp = (a.uptime_seconds ?? -1) - (b.uptime_seconds ?? -1)
          break
      }
      if (cmp === 0) cmp = a.name.localeCompare(b.name)
      return sortDir === 'desc' ? -cmp : cmp
    })

    return nodes
  }, [fleet?.nodes, sortField, sortDir, searchQuery, statusFilter])

  // ── Aggregates ────────────────────────────────────────────────

  const aggregates = useMemo(() => {
    if (!fleet?.nodes?.length) return { avgCpu: null, avgRam: null, totalDl: 0, totalUl: 0, totalUsers: 0 }

    const onlineNodes = fleet.nodes.filter((n) => n.is_connected && !n.is_disabled)

    const cpuNodes = onlineNodes.filter((n) => n.cpu_usage != null)
    const ramNodes = onlineNodes.filter((n) => n.memory_usage != null)

    const avgCpu = cpuNodes.length > 0
      ? cpuNodes.reduce((sum, n) => sum + (n.cpu_usage ?? 0), 0) / cpuNodes.length
      : null
    const avgRam = ramNodes.length > 0
      ? ramNodes.reduce((sum, n) => sum + (n.memory_usage ?? 0), 0) / ramNodes.length
      : null
    const totalDl = onlineNodes.reduce((sum, n) => sum + n.download_speed_bps, 0)
    const totalUl = onlineNodes.reduce((sum, n) => sum + n.upload_speed_bps, 0)
    const totalUsers = Array.isArray(fleet.nodes) ? fleet.nodes.reduce((sum, n) => sum + n.users_online, 0) : 0

    return { avgCpu, avgRam, totalDl, totalUl, totalUsers }
  }, [fleet?.nodes])

  // ── Render ────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('fleet.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('fleet.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', isLoading && 'animate-spin')} />
            <span className="hidden sm:inline">{t('fleet.actions.refresh')}</span>
          </Button>
        </div>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Server className="w-3.5 h-3.5" />
              <span className="text-xs">{t('fleet.stats.total')}</span>
            </div>
            <p className="text-2xl font-bold text-white">{isLoading ? '-' : fleet?.total ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Wifi className="w-3.5 h-3.5 text-green-400" />
              <span className="text-xs">{t('fleet.stats.online')}</span>
            </div>
            <p className="text-2xl font-bold text-green-400">{isLoading ? '-' : fleet?.online ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <WifiOff className="w-3.5 h-3.5 text-red-400" />
              <span className="text-xs">{t('fleet.stats.offline')}</span>
            </div>
            <p className="text-2xl font-bold text-red-400">{isLoading ? '-' : fleet?.offline ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Cpu className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-xs">{t('fleet.stats.avgCpu')}</span>
            </div>
            <p className={cn('text-2xl font-bold', getCpuColor(aggregates.avgCpu))}>
              {isLoading ? '-' : aggregates.avgCpu != null ? `${aggregates.avgCpu.toFixed(0)}%` : '-'}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <MemoryStick className="w-3.5 h-3.5 text-pink-400" />
              <span className="text-xs">{t('fleet.stats.avgRam')}</span>
            </div>
            <p className={cn('text-2xl font-bold', getRamColor(aggregates.avgRam))}>
              {isLoading ? '-' : aggregates.avgRam != null ? `${aggregates.avgRam.toFixed(0)}%` : '-'}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs">{t('fleet.stats.throughput')}</span>
            </div>
            <p className="text-lg font-bold text-white leading-tight">
              {isLoading ? '-' : (
                <>
                  <span className="text-blue-400">{formatSpeed(aggregates.totalDl)}</span>
                  <span className="text-dark-400 text-sm mx-0.5">/</span>
                  <span className="text-emerald-400">{formatSpeed(aggregates.totalUl)}</span>
                </>
              )}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
        <TabsList className="h-9">
          <TabsTrigger value="monitoring" className="text-xs gap-1.5">
            <Activity className="w-3.5 h-3.5" />
            {t('fleet.tabs.monitoring')}
          </TabsTrigger>
          {canScripts && (
            <TabsTrigger value="scripts" className="text-xs gap-1.5">
              <FileCode className="w-3.5 h-3.5" />
              {t('fleet.tabs.scripts')}
            </TabsTrigger>
          )}
          <TabsTrigger value="history" className="text-xs gap-1.5">
            <History className="w-3.5 h-3.5" />
            {t('fleet.tabs.history')}
          </TabsTrigger>
        </TabsList>

        {/* ── Monitoring Tab ──────────────────────────────────────── */}
        <TabsContent value="monitoring" className="space-y-4 mt-4">
          {/* Search + filter + sort toolbar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
              <Input
                placeholder={t('fleet.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="flex items-center gap-1.5">
              {([
                { value: 'all', label: t('fleet.filter.all'), count: fleet?.total },
                { value: 'online', label: t('fleet.filter.online'), count: fleet?.online },
                { value: 'offline', label: t('fleet.filter.offline'), count: fleet?.offline },
                { value: 'disabled', label: t('fleet.filter.disabled'), count: fleet?.disabled },
              ] as const).map(({ value, label, count }) => (
                <Button
                  key={value}
                  variant={statusFilter === value ? 'default' : 'secondary'}
                  size="sm"
                  className="h-8 text-xs gap-1"
                  onClick={() => setStatusFilter(value)}
                >
                  {label}
                  {count != null && count > 0 && (
                    <span className={cn(
                      'text-[10px] font-mono',
                      statusFilter === value ? 'text-white/80' : 'text-dark-300',
                    )}>
                      {count}
                    </span>
                  )}
                </Button>
              ))}
            </div>
            {/* Sort dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="secondary" size="sm" className="h-8 gap-1.5 ml-auto">
                  <ArrowUpDown className="w-3.5 h-3.5" />
                  <span className="text-xs">{t('fleet.sort.label')}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuRadioGroup
                  value={`${sortField}-${sortDir}`}
                  onValueChange={(v) => {
                    const [field, dir] = v.split('-') as [SortField, SortDir]
                    setSortField(field)
                    setSortDir(dir)
                  }}
                >
                  {SORT_FIELDS.map(({ value, labelKey }) => (
                    <DropdownMenuRadioItem key={`${value}-asc`} value={`${value}-${sortField === value && sortDir === 'asc' ? 'desc' : 'asc'}`} onClick={() => toggleSort(value)}>
                      {t(labelKey)} {sortField === value ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Node card grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <div className="h-[180px] bg-dark-700/30 rounded animate-pulse" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : sortedNodes.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Server className="w-10 h-10 text-dark-300 mx-auto mb-2 opacity-40" />
                <p className="text-dark-200">
                  {searchQuery || statusFilter !== 'all' ? t('fleet.nothingFound') : t('fleet.noNodes')}
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {sortedNodes.map((node) => (
                <NodeCard
                  key={node.uuid}
                  node={node}
                  isExpanded={expandedUuid === node.uuid}
                  onToggle={() => setExpandedUuid(expandedUuid === node.uuid ? null : node.uuid)}
                  onTerminalConnect={canTerminal ? () => setTerminalNode({ uuid: node.uuid, name: node.name }) : undefined}
                >
                  <NodeDetailPanel
                    node={node}
                    canEdit={canEditNodes}
                    onRestart={() => restartNode.mutate(node.uuid)}
                    onEnable={() => enableNode.mutate(node.uuid)}
                    onDisable={() => disableNode.mutate(node.uuid)}
                    isPending={mutationPending}
                  />
                </NodeCard>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Scripts Tab ──────────────────────────────────────────── */}
        {canScripts && (
          <TabsContent value="scripts" className="mt-4">
            <Suspense fallback={<div className="h-40 bg-dark-700/30 rounded animate-pulse" />}>
              <ScriptCatalog onRunScript={(script) => setRunScript(script)} />
            </Suspense>
          </TabsContent>
        )}

        {/* ── History Tab ──────────────────────────────────────────── */}
        <TabsContent value="history" className="mt-4">
          <Suspense fallback={<div className="h-40 bg-dark-700/30 rounded animate-pulse" />}>
            <CommandHistory />
          </Suspense>
        </TabsContent>
      </Tabs>

      {/* Terminal Dialog */}
      {terminalNode && (
        <TerminalDialog
          open={!!terminalNode}
          onOpenChange={(open) => { if (!open) setTerminalNode(null) }}
          nodeUuid={terminalNode.uuid}
          nodeName={terminalNode.name}
        />
      )}

      {/* Run Script Dialog */}
      <Suspense fallback={null}>
        {runScript && (
          <RunScriptDialog
            open={!!runScript}
            onOpenChange={(open) => { if (!open) setRunScript(null) }}
            script={runScript}
          />
        )}
      </Suspense>
    </div>
  )
}
