import { useTranslation } from 'react-i18next'

import {
  Cpu,
  MemoryStick,
  HardDrive,
  Clock,
  ArrowUp,
  ArrowDown,
  Terminal,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import CircularGauge from './CircularGauge'

// ── Types ────────────────────────────────────────────────────────

export interface FleetNode {
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
  cpu_cores: number | null
  memory_usage: number | null
  memory_total_bytes: number | null
  memory_used_bytes: number | null
  disk_usage: number | null
  disk_total_bytes: number | null
  disk_used_bytes: number | null
  disk_read_speed_bps: number
  disk_write_speed_bps: number
  last_seen_at: string | null
  download_speed_bps: number
  upload_speed_bps: number
  metrics_updated_at: string | null
}

export type NodeStatus = 'online' | 'offline' | 'disabled'

export function getNodeStatus(node: FleetNode): NodeStatus {
  if (node.is_disabled) return 'disabled'
  if (node.is_connected) return 'online'
  return 'offline'
}

// ── Helpers ──────────────────────────────────────────────────────

function formatSpeedCompact(bps: number): string {
  if (bps === 0) return '0 B/s'
  const units = ['B/s', 'K/s', 'M/s', 'G/s']
  let value = bps
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[unitIndex]}`
}

// ── Status Badge ────────────────────────────────────────────────

function StatusBadge({ status }: { status: NodeStatus }) {
  const { t } = useTranslation()

  switch (status) {
    case 'online':
      return (
        <Badge variant="success" className="text-[10px] gap-1 px-2 py-0.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          {t('fleet.statusOnline')}
        </Badge>
      )
    case 'offline':
      return (
        <Badge variant="destructive" className="text-[10px] gap-1 px-2 py-0.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
          {t('fleet.statusOffline')}
        </Badge>
      )
    case 'disabled':
      return (
        <Badge variant="secondary" className="text-[10px] gap-1 px-2 py-0.5">
          <span className="w-1.5 h-1.5 rounded-full bg-dark-400" />
          {t('fleet.statusDisabled')}
        </Badge>
      )
  }
}

// ── Uptime formatter ────────────────────────────────────────────

function formatUptimeShort(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '-'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

// ── NodeCard Component ──────────────────────────────────────────

interface NodeCardProps {
  node: FleetNode
  isExpanded: boolean
  onToggle: () => void
  onTerminalConnect?: () => void
  children?: React.ReactNode
}

export default function NodeCard({ node, isExpanded, onToggle, onTerminalConnect, children }: NodeCardProps) {
  const { t } = useTranslation()
  const status = getNodeStatus(node)

  const memoryGb = node.memory_total_bytes != null
    ? (node.memory_total_bytes / (1024 * 1024 * 1024)).toFixed(2)
    : null
  const diskGb = node.disk_total_bytes != null
    ? (node.disk_total_bytes / (1024 * 1024 * 1024)).toFixed(1)
    : null

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all duration-200 hover:border-dark-200/40',
        status === 'offline' && 'border-red-500/30',
        node.is_disabled && 'opacity-50',
        isExpanded && 'border-accent-500/40',
      )}
      onClick={onToggle}
    >
      <CardContent className="p-4">
        {/* Row 1: Name + Status + Terminal */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-white font-semibold truncate text-sm">{node.name}</span>
            <span className="text-dark-400 text-xs font-mono hidden sm:inline">{node.address}</span>
          </div>
          <div className="flex items-center gap-2">
            {onTerminalConnect && status === 'online' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-dark-200 hover:text-green-400"
                    onClick={(e) => { e.stopPropagation(); onTerminalConnect() }}
                  >
                    <Terminal className="w-3.5 h-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t('fleet.terminal.connect')}</TooltipContent>
              </Tooltip>
            )}
            <StatusBadge status={status} />
          </div>
        </div>

        {/* Row 2: System specs */}
        <div className="flex items-center gap-3 text-xs text-dark-200 mb-3">
          <div className="flex items-center gap-1">
            <Cpu className="w-3 h-3 text-dark-300" />
            <span>{node.cpu_cores ? `${node.cpu_cores} ${node.cpu_cores === 1 ? t('fleet.card.core') : t('fleet.card.cores')}` : '-'}</span>
          </div>
          <div className="flex items-center gap-1">
            <MemoryStick className="w-3 h-3 text-dark-300" />
            <span>{memoryGb ? `${memoryGb} G` : '-'}</span>
          </div>
          <div className="flex items-center gap-1">
            <HardDrive className="w-3 h-3 text-dark-300" />
            <span>{diskGb ? `${diskGb} G` : '-'}</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-dark-300" />
            <span>{formatUptimeShort(node.uptime_seconds)}</span>
          </div>
        </div>

        <Separator className="mb-3" />

        {/* Row 3: Metrics section */}
        <div className="grid grid-cols-4 gap-2">
          {/* CPU gauge */}
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-dark-300 uppercase tracking-wider mb-1.5">CPU</span>
            <CircularGauge value={node.cpu_usage} size={52} strokeWidth={4} />
          </div>

          {/* RAM gauge */}
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-dark-300 uppercase tracking-wider mb-1.5">RAM</span>
            <CircularGauge value={node.memory_usage} size={52} strokeWidth={4} />
          </div>

          {/* Network speeds */}
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-dark-300 uppercase tracking-wider mb-1.5">{t('fleet.card.network')}</span>
            <div className="flex flex-col items-center gap-1 mt-1">
              <div className="flex items-center gap-1">
                <ArrowUp className="w-3 h-3 text-emerald-400" />
                <span className="text-[11px] font-mono text-white">{formatSpeedCompact(node.upload_speed_bps)}</span>
              </div>
              <div className="flex items-center gap-1">
                <ArrowDown className="w-3 h-3 text-blue-400" />
                <span className="text-[11px] font-mono text-white">{formatSpeedCompact(node.download_speed_bps)}</span>
              </div>
            </div>
          </div>

          {/* Disk I/O */}
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-dark-300 uppercase tracking-wider mb-1.5">{t('fleet.card.disk')}</span>
            <div className="flex flex-col items-center gap-1 mt-1">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-dark-400 font-mono w-2">R</span>
                <span className="text-[11px] font-mono text-white">{formatSpeedCompact(node.disk_read_speed_bps)}</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-dark-400 font-mono w-2">W</span>
                <span className="text-[11px] font-mono text-white">{formatSpeedCompact(node.disk_write_speed_bps)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Expanded detail */}
        {isExpanded && children && (
          <div onClick={(e) => e.stopPropagation()}>
            <Separator className="my-3" />
            {children}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
