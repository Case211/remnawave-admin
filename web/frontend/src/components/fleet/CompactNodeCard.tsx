import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Cpu,
  MemoryStick,
  HardDrive,
  Users,
  ArrowDownRight,
  ArrowUpRight,
  RotateCcw,
  Play,
  Square,
  Terminal,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import { type FleetNode, getNodeStatus } from './NodeCard'

const STATUS_STYLE: Record<string, string> = {
  online: 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]',
  offline: 'bg-red-400',
  disabled: 'bg-gray-500',
}

function usageColor(v: number | null | undefined): string {
  if (v == null) return 'text-dark-400'
  if (v >= 95) return 'text-red-400'
  if (v >= 80) return 'text-yellow-400'
  return 'text-white'
}

function barColor(v: number | null | undefined, base: string): string {
  if (v == null) return 'bg-dark-600'
  if (v >= 95) return 'bg-red-500'
  if (v >= 80) return 'bg-yellow-500'
  return base
}

function MiniMetric({
  Icon,
  value,
  base,
}: {
  Icon: typeof Cpu
  value: number | null | undefined
  base: string
}) {
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-1 mb-1">
        <Icon className="w-3 h-3 text-dark-300 shrink-0" />
        <span className={cn('font-mono text-[11px] ml-auto', usageColor(value))}>
          {value != null ? `${value.toFixed(0)}%` : '—'}
        </span>
      </div>
      <div className="h-1 bg-[var(--glass-bg)] rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-500', barColor(value, base))} style={{ width: `${Math.min(value ?? 0, 100)}%` }} />
      </div>
    </div>
  )
}

export interface CompactNodeCardProps {
  node: FleetNode
  canEdit: boolean
  canTerminal: boolean
  onRestart: (uuid: string) => void
  onEnable: (uuid: string) => void
  onDisable: (uuid: string) => void
  onTerminal: (node: FleetNode) => void
  isPending: boolean
}

export function CompactNodeCard({
  node,
  canEdit,
  canTerminal,
  onRestart,
  onEnable,
  onDisable,
  onTerminal,
  isPending,
}: CompactNodeCardProps) {
  const { t } = useTranslation()
  const { formatSpeed } = useFormatters()
  const status = getNodeStatus(node)

  return (
    <Card className="group">
      <CardContent className="p-3 space-y-2.5">
        {/* Header */}
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} role="img" title={t(`fleet.filter.${status}`)} aria-label={t(`fleet.filter.${status}`)} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <div className="font-medium text-white text-sm truncate leading-tight">{node.name}</div>
              {node.is_external && (
                <span className="shrink-0 rounded border border-sky-500/40 bg-sky-500/10 px-1 text-[10px] leading-4 text-sky-300">
                  {t('fleet.server.badge')}
                </span>
              )}
            </div>
            <div className="text-[11px] text-dark-300 font-mono truncate">{node.address}:{node.port}</div>
          </div>
          <span className="inline-flex items-center gap-1 text-xs text-dark-200 shrink-0">
            <Users className="w-3.5 h-3.5 text-cyan-400" />
            {node.users_online}
          </span>
        </div>

        {/* Metrics */}
        <div className="flex items-end gap-3">
          <MiniMetric Icon={Cpu} value={node.cpu_usage} base="bg-green-500" />
          <MiniMetric Icon={MemoryStick} value={node.memory_usage} base="bg-cyan-500" />
          <MiniMetric Icon={HardDrive} value={node.disk_usage} base="bg-violet-500" />
        </div>

        {/* Footer: speed + actions */}
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="inline-flex items-center gap-0.5 text-blue-400">
            <ArrowDownRight className="w-3 h-3" />{formatSpeed(node.download_speed_bps)}
          </span>
          <span className="inline-flex items-center gap-0.5 text-emerald-400">
            <ArrowUpRight className="w-3 h-3" />{formatSpeed(node.upload_speed_bps)}
          </span>
          <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            {canTerminal && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="icon" variant="ghost" aria-label={t('fleet.terminal.connect', { defaultValue: 'Терминал' })} className="h-6 w-6 text-dark-200 hover:text-white" onClick={() => onTerminal(node)}>
                    <Terminal className="w-3 h-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t('fleet.terminal.connect', { defaultValue: 'Терминал' })}</TooltipContent>
              </Tooltip>
            )}
            {canEdit && !node.is_external && status === 'online' && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="icon" variant="ghost" aria-label={t('fleet.actions.restart')} className="h-6 w-6 text-dark-200 hover:text-white" disabled={isPending} onClick={() => onRestart(node.uuid)}>
                    <RotateCcw className="w-3 h-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t('fleet.actions.restart')}</TooltipContent>
              </Tooltip>
            )}
            {canEdit && !node.is_external && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button size="icon" variant="ghost" aria-label={node.is_disabled ? t('fleet.actions.enable') : t('fleet.actions.disable')} className={cn('h-6 w-6', node.is_disabled ? 'text-green-400 hover:text-green-300' : 'text-red-400 hover:text-red-300')} disabled={isPending} onClick={() => (node.is_disabled ? onEnable(node.uuid) : onDisable(node.uuid))}>
                    {node.is_disabled ? <Play className="w-3 h-3" /> : <Square className="w-3 h-3" />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{node.is_disabled ? t('fleet.actions.enable') : t('fleet.actions.disable')}</TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
