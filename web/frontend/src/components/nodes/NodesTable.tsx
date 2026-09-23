import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { SortableTh } from '@/components/table/SortableTh'
import { useTableControls, type ColumnSpec } from '@/lib/useTableControls'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, RotateCcw, Pencil, Play, Square, Key, Globe, Trash2, Bot, BotOff, Gauge } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

export interface NodeRow {
  uuid: string
  name: string
  address: string
  port: number
  is_connected: boolean
  is_disabled: boolean
  users_online: number
  xray_version: string | null
  traffic_total_bytes: number
  traffic_today_bytes: number
  last_seen_at: string | null
  has_agent_token?: boolean
  agent_v2_connected?: boolean
  allowed_actions?: string[] | null
}

function nodeStatus(n: NodeRow): 'online' | 'offline' | 'disabled' {
  if (n.is_disabled) return 'disabled'
  if (n.is_connected) return 'online'
  return 'offline'
}

function agentStatus(n: NodeRow): 'connected' | 'offline' | 'missing' {
  if (n.agent_v2_connected) return 'connected'
  if (n.has_agent_token) return 'offline'
  return 'missing'
}

const STATUS_STYLE: Record<string, string> = {
  online: 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]',
  offline: 'bg-red-400',
  disabled: 'bg-gray-500',
}

const AGENT_STYLE: Record<string, string> = {
  connected: 'text-emerald-300',
  offline: 'text-amber-300',
  missing: 'text-dark-300',
}

export interface NodesTableProps {
  nodes: NodeRow[]
  canEdit: boolean
  canDelete: boolean
  onRestart: (n: NodeRow) => void
  onEdit: (n: NodeRow) => void
  onEnable: (n: NodeRow) => void
  onDisable: (n: NodeRow) => void
  onDelete: (n: NodeRow) => void
  onTokenManage: (n: NodeRow) => void
  onShaper: (n: NodeRow) => void
  onFetchIps: (n: NodeRow) => void
}

export function NodesTable({
  nodes,
  canEdit,
  canDelete,
  onRestart,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
  onTokenManage,
  onShaper,
  onFetchIps,
}: NodesTableProps) {
  const { t } = useTranslation()
  const { formatBytes, formatTimeAgo } = useFormatters()

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
      { key: 'seen', sortAccessor: (n) => (n.last_seen_at ? new Date(n.last_seen_at).getTime() : 0) },
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
  const gb = { label: 'ГБ', factor: 1e9 }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableTh label={t('nodes.table.node', { defaultValue: 'Нода' })} sortKey="name" currentSort={sort} onSort={toggleSort} />
          <SortableTh label={t('nodes.table.status', { defaultValue: 'Статус' })} sortKey="status" currentSort={sort} onSort={toggleSort}
            filter={{ type: 'select', options: statusOptions, value: filters.status, onChange: (v) => setFilter('status', v) }} />
          <SortableTh label={t('nodes.table.agent', { defaultValue: 'Агент' })} sortKey="agent" currentSort={sort} onSort={toggleSort} className="hidden md:table-cell"
            filter={{ type: 'select', options: agentOptions, value: filters.agent, onChange: (v) => setFilter('agent', v) }} />
          <SortableTh label={t('nodes.table.users', { defaultValue: 'Юзеры' })} sortKey="users" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.users, onChange: (v) => setFilter('users', v) }} />
          <SortableTh label={t('nodes.table.today', { defaultValue: 'Трафик/день' })} sortKey="today" currentSort={sort} onSort={toggleSort} align="right"
            filter={{ type: 'range', value: filters.today, onChange: (v) => setFilter('today', v), rangeUnit: gb }} />
          <SortableTh label={t('nodes.table.total', { defaultValue: 'Всего' })} sortKey="total" currentSort={sort} onSort={toggleSort} align="right" className="hidden lg:table-cell" />
          <SortableTh label={t('nodes.table.xray', { defaultValue: 'Xray' })} sortKey="xray" currentSort={sort} onSort={toggleSort} className="hidden lg:table-cell" />
          <SortableTh label={t('nodes.table.seen', { defaultValue: 'Был(а)' })} sortKey="seen" currentSort={sort} onSort={toggleSort} align="right" className="hidden md:table-cell" />
          <SortableTh label="" className="w-px" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((node) => {
          const status = nodeStatus(node)
          const agent = agentStatus(node)
          const scopeEdit = canEdit && (node.allowed_actions == null || node.allowed_actions.includes('edit'))
          const scopeDelete = canDelete && (node.allowed_actions == null || node.allowed_actions.includes('delete'))
          const isOnline = node.is_connected && !node.is_disabled
          return (
            <TableRow key={node.uuid}>
              <TableCell>
                <div className="font-medium text-white truncate max-w-[200px]">{node.name}</div>
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
              </TableCell>
              <TableCell className="text-right font-mono text-sm text-white">{node.users_online}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-100 whitespace-nowrap">{formatBytes(node.traffic_today_bytes)}</TableCell>
              <TableCell className="text-right font-mono text-xs text-dark-200 hidden lg:table-cell whitespace-nowrap">{formatBytes(node.traffic_total_bytes)}</TableCell>
              <TableCell className="font-mono text-xs text-dark-200 hidden lg:table-cell">{node.xray_version || '—'}</TableCell>
              <TableCell className="text-right text-xs text-dark-200 hidden md:table-cell whitespace-nowrap">
                {node.last_seen_at ? formatTimeAgo(node.last_seen_at) : '—'}
              </TableCell>
              <TableCell className="text-right">
                {(scopeEdit || scopeDelete) && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="icon" variant="ghost" aria-label={t('common.openMenu')} className="h-7 w-7 text-dark-200 hover:text-white">
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {scopeEdit && isOnline && (
                        <DropdownMenuItem onClick={() => onRestart(node)}><RotateCcw className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.restart')}</DropdownMenuItem>
                      )}
                      {scopeEdit && (
                        <DropdownMenuItem onClick={() => onEdit(node)}><Pencil className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.edit', { defaultValue: 'Изменить' })}</DropdownMenuItem>
                      )}
                      {scopeEdit && (
                        node.is_disabled ? (
                          <DropdownMenuItem onClick={() => onEnable(node)}><Play className="w-3.5 h-3.5 mr-2 text-green-400" />{t('nodes.actions.enable')}</DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => onDisable(node)}><Square className="w-3.5 h-3.5 mr-2 text-red-400" />{t('nodes.actions.disable')}</DropdownMenuItem>
                        )
                      )}
                      {scopeEdit && (
                        <DropdownMenuItem onClick={() => onTokenManage(node)}><Key className="w-3.5 h-3.5 mr-2" />{t('nodes.agent.token', { defaultValue: 'Токен агента' })}</DropdownMenuItem>
                      )}
                      {scopeEdit && (
                        <DropdownMenuItem onClick={() => onShaper(node)}><Gauge className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.shaper')}</DropdownMenuItem>
                      )}
                      <DropdownMenuItem onClick={() => onFetchIps(node)}><Globe className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.fetchIps', { defaultValue: 'IP юзеров' })}</DropdownMenuItem>
                      {scopeDelete && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => onDelete(node)} className="text-red-400 focus:text-red-300"><Trash2 className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.delete', { defaultValue: 'Удалить' })}</DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
