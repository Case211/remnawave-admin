import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { SortableTh } from '@/components/table/SortableTh'
import { useTableControls, type ColumnSpec } from '@/lib/useTableControls'
import { Bot, BotOff } from '@/components/brand/icons'
import { ShaperBadge } from './ShaperBadge'
import { cn } from '@/lib/utils'
import {
  AGENT_STYLE,
  STATUS_STYLE,
  NodeActionsMenu,
  agentStatus,
  countryFlag,
  nodeStatus,
  type NodeActions,
  type NodeRow,
} from './nodeShared'

export type { NodeRow } from './nodeShared'

export interface NodesTableProps extends NodeActions {
  nodes: NodeRow[]
  canEdit: boolean
  canDelete: boolean
}

export function NodesTable({ nodes, canEdit, canDelete, ...actions }: NodesTableProps) {
  const { t } = useTranslation()
  const { formatBytes, formatSpeed, formatTimeAgo } = useFormatters()

  const columns: ColumnSpec<NodeRow>[] = useMemo(
    () => [
      { key: 'name', sortAccessor: (n) => n.name },
      {
        key: 'status',
        sortAccessor: (n) => ({ offline: 0, online: 1, disabled: 2 })[nodeStatus(n)],
        filterAccessor: (n) => nodeStatus(n),
        filterType: 'select',
      },
      {
        key: 'agent',
        sortAccessor: (n) => ({ missing: 0, offline: 1, connected: 2 })[agentStatus(n)],
        filterAccessor: (n) => agentStatus(n),
        filterType: 'select',
      },
      { key: 'users', sortAccessor: (n) => n.users_online, filterAccessor: (n) => n.users_online, filterType: 'range' },
      { key: 'today', sortAccessor: (n) => n.traffic_today_bytes, filterAccessor: (n) => n.traffic_today_bytes, filterType: 'range' },
      { key: 'total', sortAccessor: (n) => n.traffic_total_bytes },
      { key: 'xray', sortAccessor: (n) => n.xray_version ?? '' },
      { key: 'speed', sortAccessor: (n) => (n.download_speed_bps || 0) + (n.upload_speed_bps || 0) },
      { key: 'since', sortAccessor: (n) => (n.last_status_change ? new Date(n.last_status_change).getTime() : 0) },
    ],
    [],
  )

  const { rows, sort, toggleSort, filters, setFilter } = useTableControls(nodes, columns, {
    initialSort: { key: 'status', dir: 'asc' },
    storageKey: 'nodes', // сортировка переживает уход со страницы
  })

  const statusOptions = [
    { value: 'online', label: t('nodes.status.online') },
    { value: 'offline', label: t('nodes.status.offline') },
    { value: 'disabled', label: t('nodes.status.disabled') },
  ]
  const agentOptions = [
    { value: 'connected', label: t('nodes.agent.connected') },
    { value: 'offline', label: t('nodes.agent.offline') },
    { value: 'missing', label: t('nodes.agent.missing') },
  ]
  const gb = { label: t('common.bytes.gb'), factor: 1e9 }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableTh label={t('nodes.table.node')} sortKey="name" currentSort={sort} onSort={toggleSort} />
          <SortableTh label={t('nodes.table.status')} sortKey="status" currentSort={sort} onSort={toggleSort}
            filter={{ type: 'select', options: statusOptions, value: filters.status, onChange: (v) => setFilter('status', v) }} />
          <SortableTh label={t('nodes.table.agent')} sortKey="agent" currentSort={sort} onSort={toggleSort} className="hidden md:table-cell"
            filter={{ type: 'select', options: agentOptions, value: filters.agent, onChange: (v) => setFilter('agent', v) }} />
          <SortableTh label={t('nodes.table.users')} sortKey="users" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.users, onChange: (v) => setFilter('users', v) }} />
          <SortableTh label={t('nodes.table.today')} sortKey="today" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.today, onChange: (v) => setFilter('today', v), rangeUnit: gb }} />
          <SortableTh label={t('nodes.table.period')} sortKey="total" currentSort={sort} onSort={toggleSort} align="right" className="hidden lg:table-cell" />
          <SortableTh label={t('nodes.table.speed')} sortKey="speed" currentSort={sort} onSort={toggleSort} align="right" className="hidden xl:table-cell" />
          <SortableTh label={t('nodes.table.xray')} sortKey="xray" currentSort={sort} onSort={toggleSort} className="hidden lg:table-cell" />
          <SortableTh label={t('nodes.table.since')} sortKey="since" currentSort={sort} onSort={toggleSort} align="right" className="hidden md:table-cell" />
          <SortableTh label="" className="w-px" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((node) => {
          const status = nodeStatus(node)
          const agent = agentStatus(node)
          return (
            <TableRow key={node.uuid}>
              <TableCell>
                <div className="font-medium text-white truncate max-w-[200px]">
                  {countryFlag(node.country_code)} {node.name}
                </div>
                <div className="text-xs text-dark-300 font-mono truncate max-w-[200px]">{node.address}:{node.port}</div>
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-1.5 text-xs text-dark-100">
                  <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} />
                  {t(`nodes.status.${status}`)}
                </span>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                <span className={cn('inline-flex items-center gap-1 text-xs', AGENT_STYLE[agent])}>
                  {agent === 'missing' ? <BotOff className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
                  {t(`nodes.agent.${agent}`)}
                </span>
                <ShaperBadge state={node.shaper_state} className="ml-2" />
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-white">{node.users_online}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-100 whitespace-nowrap">{formatBytes(node.traffic_today_bytes)}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-200 hidden lg:table-cell whitespace-nowrap">{formatBytes(node.traffic_total_bytes)}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-200 hidden xl:table-cell whitespace-nowrap">
                {status === 'online' ? `↓${formatSpeed(node.download_speed_bps || 0)} ↑${formatSpeed(node.upload_speed_bps || 0)}` : '—'}
              </TableCell>
              <TableCell className="font-mono text-xs text-dark-200 hidden lg:table-cell">{node.xray_version || '—'}</TableCell>
              <TableCell className="text-right text-xs text-dark-200 hidden md:table-cell whitespace-nowrap">
                {node.last_status_change ? formatTimeAgo(node.last_status_change) : '—'}
              </TableCell>
              <TableCell className="text-right">
                <NodeActionsMenu node={node} canEdit={canEdit} canDelete={canDelete} actions={actions} className="h-7 w-7" />
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
