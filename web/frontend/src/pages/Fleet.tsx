import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useHasPermission } from '@/components/PermissionGate'
import {
  Activity,
  RefreshCw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronDown,
  ChevronRight,
  Users,
  Cpu,
  MemoryStick,
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
} from 'lucide-react'
import client from '../api/client'
import { usePermissionStore } from '../store/permissionStore'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

// ── Types ────────────────────────────────────────────────────────

interface FleetNode {
  uuid: string
  name: string
  address: string
  port: number
  is_connected: boolean
  is_disabled: boolean
  is_xray_running: boolean
  xray_version: string | null
  users_online: number
  traffic_today_bytes: number
  traffic_total_bytes: number
  uptime_seconds: number | null
  cpu_usage: number | null
  memory_usage: number | null
  memory_total_bytes: number | null
  memory_used_bytes: number | null
  disk_usage: number | null
  disk_total_bytes: number | null
  disk_used_bytes: number | null
  last_seen_at: string | null
  download_speed_bps: number
  upload_speed_bps: number
  metrics_updated_at: string | null
}

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

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 Б'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatSpeed(bps: number): string {
  if (!bps || bps <= 0) return '-'
  const k = 1024
  const sizes = ['б/с', 'Кб/с', 'Мб/с', 'Гб/с']
  const i = Math.floor(Math.log(bps) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 б/с'
  return parseFloat((bps / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
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

function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Никогда'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)
  if (diffSec < 60) return 'Только что'
  if (diffMin < 60) return `${diffMin} мин назад`
  if (diffHour < 24) return `${diffHour} ч назад`
  return `${diffDay} дн назад`
}

function getNodeStatus(node: FleetNode): 'online' | 'offline' | 'disabled' {
  if (node.is_disabled) return 'disabled'
  if (node.is_connected) return 'online'
  return 'offline'
}

function getStatusBadge(status: 'online' | 'offline' | 'disabled') {
  switch (status) {
    case 'online':
      return <Badge variant="success" className="text-[10px] gap-1"><Wifi className="w-3 h-3" />Онлайн</Badge>
    case 'offline':
      return <Badge variant="destructive" className="text-[10px] gap-1"><WifiOff className="w-3 h-3" />Офлайн</Badge>
    case 'disabled':
      return <Badge variant="secondary" className="text-[10px] gap-1">Отключена</Badge>
  }
}

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

// ── Sort Header ──────────────────────────────────────────────────

function SortableHead({
  label,
  field,
  currentField,
  currentDir,
  onSort,
  className,
}: {
  label: string
  field: SortField
  currentField: SortField
  currentDir: SortDir
  onSort: (field: SortField) => void
  className?: string
}) {
  const isActive = currentField === field
  return (
    <TableHead className={cn('cursor-pointer select-none hover:text-white transition-colors', className)} onClick={() => onSort(field)}>
      <div className="flex items-center gap-1">
        {label}
        {isActive ? (
          currentDir === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
        ) : (
          <ArrowUpDown className="w-3 h-3 opacity-30" />
        )}
      </div>
    </TableHead>
  )
}

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
  const status = getNodeStatus(node)

  return (
    <div className="px-4 pb-4 pt-1 animate-fade-in">
      <div className="bg-dark-800/40 rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Column 1: Connection info */}
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">Информация</h4>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <Globe className="w-3.5 h-3.5 text-dark-300" />
                <span className="text-dark-200">Адрес</span>
                <span className="text-white ml-auto font-mono text-xs">{node.address}:{node.port}</span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-3.5 h-3.5 text-yellow-400" />
                <span className="text-dark-200">Xray</span>
                <span className="text-white ml-auto font-mono text-xs">{node.xray_version || '-'}</span>
              </div>
              <div className="flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-dark-300" />
                <span className="text-dark-200">Xray запущен</span>
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
                <span className="text-dark-200">Последняя связь</span>
                <span className="text-white ml-auto text-xs">{formatTimeAgo(node.last_seen_at)}</span>
              </div>
            </div>
          </div>

          {/* Column 2: Detailed metrics */}
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">Метрики</h4>
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
                <span className="text-dark-200">Диск</span>
                <span className={cn('ml-auto font-mono', node.disk_usage != null && node.disk_usage >= 95 ? 'text-red-400' : node.disk_usage != null && node.disk_usage >= 80 ? 'text-yellow-400' : 'text-white')}>
                  {node.disk_usage != null ? `${node.disk_usage.toFixed(1)}%` : '-'}
                  {node.disk_total_bytes != null && <span className="text-dark-400 text-[10px] ml-1">({formatBytes(node.disk_used_bytes ?? 0)} / {formatBytes(node.disk_total_bytes)})</span>}
                </span>
              </div>
              {node.disk_usage != null && (
                <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-500',
                      node.disk_usage >= 95 ? 'bg-red-500' : node.disk_usage >= 80 ? 'bg-yellow-500' : 'bg-violet-500',
                    )}
                    style={{ width: `${Math.min(node.disk_usage, 100)}%` }}
                  />
                </div>
              )}
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
            <h4 className="text-xs font-medium text-dark-200 uppercase tracking-wider">Трафик и действия</h4>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-3.5 h-3.5 text-violet-400" />
                <span className="text-dark-200">Сегодня</span>
                <span className="text-white ml-auto font-mono text-xs">{formatBytes(node.traffic_today_bytes)}</span>
              </div>
              <div className="flex items-center gap-2">
                <BarChart3 className="w-3.5 h-3.5 text-dark-300" />
                <span className="text-dark-200">Всего</span>
                <span className="text-white ml-auto font-mono text-xs">{formatBytes(node.traffic_total_bytes)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-dark-200">Пользователей</span>
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
                          Рестарт
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Перезапустить ноду</TooltipContent>
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
                          Включить
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Включить ноду</TooltipContent>
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
                          Отключить
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Отключить ноду</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────

export default function Fleet() {
  const queryClient = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canEditNodes = hasPermission('nodes', 'edit')

  const [sortField, setSortField] = useState<SortField>('status')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // ── Data ──────────────────────────────────────────────────────

  const { data: fleet, isLoading, refetch } = useQuery({
    queryKey: ['fleet'],
    queryFn: fetchFleet,
    refetchInterval: 15000,
  })

  // ── Mutations ─────────────────────────────────────────────────

  const restartNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/restart`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success('Нода перезапущена') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success('Нода включена') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fleet'] }); toast.success('Нода отключена') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const mutationPending = restartNode.isPending || enableNode.isPending || disableNode.isPending

  // ── Sorting ───────────────────────────────────────────────────

  const handleSort = (field: SortField) => {
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
    const totalUsers = fleet.nodes.reduce((sum, n) => sum + n.users_online, 0)

    return { avgCpu, avgRam, totalDl, totalUl, totalUsers }
  }, [fleet?.nodes])

  // ── Render ────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Fleet</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Мониторинг серверного парка</p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', isLoading && 'animate-spin')} />
            <span className="hidden sm:inline">Обновить</span>
          </Button>
        </div>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Server className="w-3.5 h-3.5" />
              <span className="text-xs">Всего</span>
            </div>
            <p className="text-2xl font-bold text-white">{isLoading ? '-' : fleet?.total ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Wifi className="w-3.5 h-3.5 text-green-400" />
              <span className="text-xs">Онлайн</span>
            </div>
            <p className="text-2xl font-bold text-green-400">{isLoading ? '-' : fleet?.online ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <WifiOff className="w-3.5 h-3.5 text-red-400" />
              <span className="text-xs">Офлайн</span>
            </div>
            <p className="text-2xl font-bold text-red-400">{isLoading ? '-' : fleet?.offline ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1.5 text-dark-200 mb-1">
              <Cpu className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-xs">Сред. CPU</span>
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
              <span className="text-xs">Сред. RAM</span>
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
              <span className="text-xs">Throughput</span>
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

      {/* Search + filter toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
          <Input
            placeholder="Поиск по имени или адресу..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {([
            { value: 'all', label: 'Все', count: fleet?.total },
            { value: 'online', label: 'Онлайн', count: fleet?.online },
            { value: 'offline', label: 'Офлайн', count: fleet?.offline },
            { value: 'disabled', label: 'Откл.', count: fleet?.disabled },
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
      </div>

      {/* Desktop: Node table */}
      <Card className="hidden md:block animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <SortableHead label="Статус" field="status" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-28" />
                <SortableHead label="Нода" field="name" currentField={sortField} currentDir={sortDir} onSort={handleSort} />
                <SortableHead label="CPU" field="cpu" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-24" />
                <SortableHead label="RAM" field="ram" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-24" />
                <SortableHead label="Диск" field="disk" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-24" />
                <SortableHead label="Скорость" field="speed" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-44" />
                <SortableHead label="Юзеры" field="users" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-20" />
                <SortableHead label="Трафик" field="traffic" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-28" />
                <SortableHead label="Uptime" field="uptime" currentField={sortField} currentDir={sortDir} onSort={handleSort} className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={10}>
                      <div className="h-10 bg-dark-700/30 rounded animate-pulse" />
                    </TableCell>
                  </TableRow>
                ))
              ) : sortedNodes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={10} className="text-center py-12">
                    <Server className="w-10 h-10 text-dark-300 mx-auto mb-2 opacity-40" />
                    <p className="text-dark-200">
                      {searchQuery || statusFilter !== 'all' ? 'Ничего не найдено' : 'Нет нод'}
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                sortedNodes.flatMap((node) => {
                  const status = getNodeStatus(node)
                  const isExpanded = expandedUuid === node.uuid
                  const totalSpeed = node.download_speed_bps + node.upload_speed_bps

                  const rows = [
                    <TableRow
                      key={node.uuid}
                      className={cn(
                        'cursor-pointer',
                        isExpanded && 'bg-dark-600/30 border-b-0',
                        status === 'offline' && 'bg-red-500/5',
                        node.is_disabled && 'opacity-50',
                      )}
                      onClick={() => setExpandedUuid(isExpanded ? null : node.uuid)}
                    >
                      <TableCell className="w-10 pr-0">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-dark-200" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-dark-300" />
                        )}
                      </TableCell>
                      <TableCell>{getStatusBadge(status)}</TableCell>
                      <TableCell>
                        <div>
                          <span className="text-white font-medium">{node.name}</span>
                          <span className="text-dark-300 text-xs ml-2 hidden lg:inline">{node.address}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {node.cpu_usage != null ? (
                          <div className="flex items-center gap-2">
                            <div className="w-12 h-1.5 bg-dark-700 rounded-full overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  node.cpu_usage >= 95 ? 'bg-red-500' : node.cpu_usage >= 80 ? 'bg-yellow-500' : 'bg-green-500',
                                )}
                                style={{ width: `${Math.min(node.cpu_usage, 100)}%` }}
                              />
                            </div>
                            <span className={cn('text-xs font-mono', getCpuColor(node.cpu_usage))}>
                              {node.cpu_usage.toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-dark-400 text-xs">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {node.memory_usage != null ? (
                          <div className="flex items-center gap-2">
                            <div className="w-12 h-1.5 bg-dark-700 rounded-full overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  node.memory_usage >= 95 ? 'bg-red-500' : node.memory_usage >= 80 ? 'bg-yellow-500' : 'bg-cyan-500',
                                )}
                                style={{ width: `${Math.min(node.memory_usage, 100)}%` }}
                              />
                            </div>
                            <span className={cn('text-xs font-mono', getRamColor(node.memory_usage))}>
                              {node.memory_usage.toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-dark-400 text-xs">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {node.disk_usage != null ? (
                          <div className="flex items-center gap-2">
                            <div className="w-12 h-1.5 bg-dark-700 rounded-full overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  node.disk_usage >= 95 ? 'bg-red-500' : node.disk_usage >= 80 ? 'bg-yellow-500' : 'bg-violet-500',
                                )}
                                style={{ width: `${Math.min(node.disk_usage, 100)}%` }}
                              />
                            </div>
                            <span className={cn('text-xs font-mono', node.disk_usage >= 95 ? 'text-red-400' : node.disk_usage >= 80 ? 'text-yellow-400' : 'text-white')}>
                              {node.disk_usage.toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-dark-400 text-xs">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {totalSpeed > 0 ? (
                          <div className="flex items-center gap-2 text-xs font-mono">
                            <ArrowDownRight className="w-3 h-3 text-blue-400 shrink-0" />
                            <span className="text-white">{formatSpeed(node.download_speed_bps)}</span>
                            <ArrowUpRight className="w-3 h-3 text-emerald-400 shrink-0" />
                            <span className="text-white">{formatSpeed(node.upload_speed_bps)}</span>
                          </div>
                        ) : (
                          <span className="text-dark-400 text-xs">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="text-white font-mono">{node.users_online}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-white font-mono text-xs">{formatBytes(node.traffic_today_bytes)}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-white font-mono text-xs">{formatUptime(node.uptime_seconds)}</span>
                      </TableCell>
                    </TableRow>,
                  ]

                  // Inline detail panel right after the row
                  if (isExpanded) {
                    rows.push(
                      <tr key={`${node.uuid}-detail`} className="bg-dark-600/20">
                        <td colSpan={10} className="p-0">
                          <NodeDetailPanel
                            node={node}
                            canEdit={canEditNodes}
                            onRestart={() => restartNode.mutate(node.uuid)}
                            onEnable={() => enableNode.mutate(node.uuid)}
                            onDisable={() => disableNode.mutate(node.uuid)}
                            isPending={mutationPending}
                          />
                        </td>
                      </tr>,
                    )
                  }

                  return rows
                })
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Mobile: Node cards */}
      <div className="md:hidden space-y-3 animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-16 bg-dark-700/30 rounded animate-pulse" />
              </CardContent>
            </Card>
          ))
        ) : sortedNodes.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              <Server className="w-10 h-10 text-dark-300 mx-auto mb-2 opacity-40" />
              <p className="text-dark-200">
                {searchQuery || statusFilter !== 'all' ? 'Ничего не найдено' : 'Нет нод'}
              </p>
            </CardContent>
          </Card>
        ) : (
          sortedNodes.map((node) => {
            const status = getNodeStatus(node)
            const isExpanded = expandedUuid === node.uuid
            const totalSpeed = node.download_speed_bps + node.upload_speed_bps

            return (
              <Card
                key={node.uuid}
                className={cn(
                  'cursor-pointer transition-colors',
                  status === 'offline' && 'border-red-500/30',
                  node.is_disabled && 'opacity-50',
                )}
                onClick={() => setExpandedUuid(isExpanded ? null : node.uuid)}
              >
                <CardContent className="p-4">
                  {/* Card header */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-dark-200 shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-dark-300 shrink-0" />
                      )}
                      <span className="text-white font-medium truncate">{node.name}</span>
                    </div>
                    {getStatusBadge(status)}
                  </div>

                  {/* Card metrics grid */}
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div className="p-2 bg-dark-800/50 rounded-lg">
                      <p className="text-[10px] text-dark-300 mb-0.5">CPU</p>
                      <p className={cn('text-sm font-mono font-semibold', getCpuColor(node.cpu_usage))}>
                        {node.cpu_usage != null ? `${node.cpu_usage.toFixed(0)}%` : '-'}
                      </p>
                    </div>
                    <div className="p-2 bg-dark-800/50 rounded-lg">
                      <p className="text-[10px] text-dark-300 mb-0.5">RAM</p>
                      <p className={cn('text-sm font-mono font-semibold', getRamColor(node.memory_usage))}>
                        {node.memory_usage != null ? `${node.memory_usage.toFixed(0)}%` : '-'}
                      </p>
                    </div>
                    <div className="p-2 bg-dark-800/50 rounded-lg">
                      <p className="text-[10px] text-dark-300 mb-0.5">Диск</p>
                      <p className={cn('text-sm font-mono font-semibold', node.disk_usage != null && node.disk_usage >= 95 ? 'text-red-400' : node.disk_usage != null && node.disk_usage >= 80 ? 'text-yellow-400' : 'text-white')}>
                        {node.disk_usage != null ? `${node.disk_usage.toFixed(0)}%` : '-'}
                      </p>
                    </div>
                    <div className="p-2 bg-dark-800/50 rounded-lg">
                      <p className="text-[10px] text-dark-300 mb-0.5">Юзеры</p>
                      <p className="text-sm font-mono font-semibold text-white">{node.users_online}</p>
                    </div>
                  </div>

                  {/* Speed + traffic row */}
                  <div className="flex items-center justify-between mt-2 text-xs text-dark-200">
                    <span>{totalSpeed > 0 ? `DL ${formatSpeed(node.download_speed_bps)} / UL ${formatSpeed(node.upload_speed_bps)}` : '-'}</span>
                    <span>{formatBytes(node.traffic_today_bytes)}</span>
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div onClick={(e) => e.stopPropagation()}>
                      <Separator className="my-3" />
                      <NodeDetailPanel
                        node={node}
                        canEdit={canEditNodes}
                        onRestart={() => restartNode.mutate(node.uuid)}
                        onEnable={() => enableNode.mutate(node.uuid)}
                        onDisable={() => disableNode.mutate(node.uuid)}
                        isPending={mutationPending}
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })
        )}
      </div>
    </div>
  )
}
