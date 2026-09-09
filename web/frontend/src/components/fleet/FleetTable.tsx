import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { SortableTh } from '@/components/table/SortableTh'
import { useTableControls, type ColumnSpec } from '@/lib/useTableControls'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { RotateCcw, Play, Square, Terminal } from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import { Sparkline } from '@/components/charts/Sparkline'
import { type FleetNode, getNodeStatus } from './NodeCard'

/** Серии метрик за период для мини-графиков: uuid → cpu/memory/disk точки */
export type FleetMetricsHistory = Record<string, { cpu: number[]; memory: number[]; disk: number[] }>

function sparkColor(v: number | null | undefined): string {
  if (v != null && v >= 95) return '#f87171'   // red-400
  if (v != null && v >= 80) return '#facc15'   // yellow-400
  return '#38bdf8'                              // sky-400
}

function statusPriority(n: FleetNode): number {
  if (!n.is_disabled && !n.is_connected) return 0 // offline
  if (n.is_connected && !n.is_disabled) return 1 // online
  return 2 // disabled
}

function usageColor(v: number | null | undefined): string {
  if (v == null) return 'text-dark-400'
  if (v >= 95) return 'text-red-400'
  if (v >= 80) return 'text-yellow-400'
  return 'text-white'
}

function fmtUptime(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  if (d > 0) return `${d}д ${h}ч`
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}ч ${m}м`
  return `${m}м`
}

const STATUS_STYLE: Record<string, string> = {
  online: 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]',
  offline: 'bg-red-400',
  disabled: 'bg-gray-500',
}

export interface FleetTableProps {
  nodes: FleetNode[]
  canEdit: boolean
  canTerminal: boolean
  onRestart: (uuid: string) => void
  onEnable: (uuid: string) => void
  onDisable: (uuid: string) => void
  onTerminal: (node: FleetNode) => void
  isPending: boolean
  /** История метрик за 24ч (спарклайны CPU/RAM/диск); нет данных — только цифры */
  history?: FleetMetricsHistory
}

export function FleetTable({
  nodes,
  canEdit,
  canTerminal,
  onRestart,
  onEnable,
  onDisable,
  onTerminal,
  isPending,
  history,
}: FleetTableProps) {
  const { t } = useTranslation()
  const { formatSpeed, formatTimeAgo } = useFormatters()

  const columns: ColumnSpec<FleetNode>[] = useMemo(
    () => [
      { key: 'name', sortAccessor: (n) => n.name },
      {
        key: 'status',
        sortAccessor: (n) => statusPriority(n),
        filterAccessor: (n) => getNodeStatus(n),
        filterType: 'select',
      },
      { key: 'cpu', sortAccessor: (n) => n.cpu_usage ?? -1, filterAccessor: (n) => n.cpu_usage ?? null, filterType: 'range' },
      { key: 'ram', sortAccessor: (n) => n.memory_usage ?? -1, filterAccessor: (n) => n.memory_usage ?? null, filterType: 'range' },
      { key: 'disk', sortAccessor: (n) => n.disk_usage ?? -1, filterAccessor: (n) => n.disk_usage ?? null, filterType: 'range' },
      { key: 'speed', sortAccessor: (n) => n.download_speed_bps + n.upload_speed_bps },
      { key: 'users', sortAccessor: (n) => n.users_online, filterAccessor: (n) => n.users_online, filterType: 'range' },
      { key: 'uptime', sortAccessor: (n) => n.uptime_seconds ?? -1 },
    ],
    [],
  )

  const { rows, sort, toggleSort, filters, setFilter } = useTableControls(nodes, columns, {
    initialSort: { key: 'status', dir: 'asc' },
    storageKey: 'fleet', // сортировка переживает уход со страницы
  })

  const statusOptions = [
    { value: 'online', label: t('fleet.filter.online') },
    { value: 'offline', label: t('fleet.filter.offline') },
    { value: 'disabled', label: t('fleet.filter.disabled') },
  ]

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableTh label={t('fleet.table.node')} sortKey="name" currentSort={sort} onSort={toggleSort} />
          <SortableTh
            label={t('fleet.table.status')}
            sortKey="status"
            currentSort={sort}
            onSort={toggleSort}
            filter={{ type: 'select', options: statusOptions, value: filters.status, onChange: (v) => setFilter('status', v) }}
          />
          <SortableTh label={t('fleet.table.cpu')} sortKey="cpu" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.cpu, onChange: (v) => setFilter('cpu', v), rangeUnit: { label: '%', factor: 1 } }} />
          <SortableTh label={t('fleet.table.ram')} sortKey="ram" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.ram, onChange: (v) => setFilter('ram', v), rangeUnit: { label: '%', factor: 1 } }} />
          <SortableTh label={t('fleet.table.disk')} sortKey="disk" currentSort={sort} onSort={toggleSort} align="right" className="hidden md:table-cell"
            filter={{ type: 'range', value: filters.disk, onChange: (v) => setFilter('disk', v), rangeUnit: { label: '%', factor: 1 } }} />
          <SortableTh label={t('fleet.table.speed')} sortKey="speed" currentSort={sort} onSort={toggleSort} align="right" className="hidden lg:table-cell" />
          <SortableTh label={t('fleet.table.users')} sortKey="users" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.users, onChange: (v) => setFilter('users', v) }} />
          <SortableTh label={t('fleet.table.uptime')} sortKey="uptime" currentSort={sort} onSort={toggleSort} align="right" className="hidden lg:table-cell" />
          <SortableTh label="" className="w-px" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((node) => {
          const status = getNodeStatus(node)
          return (
            <TableRow key={node.uuid}>
              <TableCell>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <div className="font-medium text-white truncate max-w-[200px]">{node.name}</div>
                    {node.is_external && (
                      <span className="shrink-0 rounded border border-sky-500/40 bg-sky-500/10 px-1 text-[10px] leading-4 text-sky-300">
                        {t('fleet.server.badge')}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-dark-300 font-mono truncate max-w-[200px]">{node.address}:{node.port}</div>
                </div>
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-1.5 text-xs text-dark-100">
                  <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} />
                  {t(`fleet.filter.${status}`)}
                </span>
                {status === 'offline' && node.last_seen_at && (
                  <div className="text-[10px] text-red-300/80 mt-0.5" title={node.last_seen_at}>
                    {formatTimeAgo(node.last_seen_at)}
                  </div>
                )}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-2">
                  <Sparkline data={history?.[node.uuid]?.cpu ?? []} color={sparkColor(node.cpu_usage)} className="hidden sm:block shrink-0" />
                  <span className={cn('font-mono text-sm', usageColor(node.cpu_usage))}>
                    {node.cpu_usage != null ? `${node.cpu_usage.toFixed(0)}%` : '—'}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-2">
                  <Sparkline data={history?.[node.uuid]?.memory ?? []} color={sparkColor(node.memory_usage)} className="hidden sm:block shrink-0" />
                  <span className={cn('font-mono text-sm', usageColor(node.memory_usage))}>
                    {node.memory_usage != null ? `${node.memory_usage.toFixed(0)}%` : '—'}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right hidden md:table-cell">
                <div className="flex items-center justify-end gap-2">
                  <Sparkline data={history?.[node.uuid]?.disk ?? []} color={sparkColor(node.disk_usage)} className="hidden lg:block shrink-0" />
                  <span className={cn('font-mono text-sm', usageColor(node.disk_usage))}>
                    {node.disk_usage != null ? `${node.disk_usage.toFixed(0)}%` : '—'}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-right font-mono text-xs hidden lg:table-cell whitespace-nowrap">
                <span className="text-blue-400">{formatSpeed(node.download_speed_bps)}</span>
                <span className="text-dark-500 mx-0.5">/</span>
                <span className="text-emerald-400">{formatSpeed(node.upload_speed_bps)}</span>
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-white">{node.users_online}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-200 hidden lg:table-cell">{fmtUptime(node.uptime_seconds)}</TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-0.5">
                  {canTerminal && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button size="icon" variant="ghost" aria-label={t('fleet.terminal.connect', { defaultValue: 'Терминал' })} className="h-7 w-7 text-dark-200 hover:text-white" onClick={() => onTerminal(node)}>
                          <Terminal className="w-3.5 h-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{t('fleet.terminal.connect', { defaultValue: 'Терминал' })}</TooltipContent>
                    </Tooltip>
                  )}
                  {canEdit && !node.is_external && status === 'online' && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button size="icon" variant="ghost" aria-label={t('fleet.actions.restart')} className="h-7 w-7 text-dark-200 hover:text-white" disabled={isPending} onClick={() => onRestart(node.uuid)}>
                          <RotateCcw className="w-3.5 h-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{t('fleet.actions.restart')}</TooltipContent>
                    </Tooltip>
                  )}
                  {canEdit && !node.is_external && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button size="icon" variant="ghost" aria-label={node.is_disabled ? t('fleet.actions.enable') : t('fleet.actions.disable')} className={cn('h-7 w-7', node.is_disabled ? 'text-green-400 hover:text-green-300' : 'text-red-400 hover:text-red-300')} disabled={isPending} onClick={() => (node.is_disabled ? onEnable(node.uuid) : onDisable(node.uuid))}>
                          {node.is_disabled ? <Play className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{node.is_disabled ? t('fleet.actions.enable') : t('fleet.actions.disable')}</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
