import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Table, TableHeader, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { SortableTh } from '@/components/table/SortableTh'
import { useTableControls, type ColumnSpec } from '@/lib/useTableControls'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, Pencil, Play, Square, Trash2 } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

export interface HostRow {
  uuid: string
  remark: string
  address: string
  port: number
  is_disabled: boolean
  is_hidden: boolean
  tag?: string | null
  tags: string[] | null
  inbound: { uuid: string; tag: string; type: string } | null
  security_layer: string | null
  security: string | null
  nodes: { uuid: string; name: string }[] | null
  allowed_actions?: string[] | null
}

function sec(h: HostRow): string {
  return h.security_layer || h.security || 'none'
}
function hostStatus(h: HostRow): 'active' | 'disabled' | 'hidden' {
  if (h.is_disabled) return 'disabled'
  if (h.is_hidden) return 'hidden'
  return 'active'
}
function secColor(s: string): string {
  if (s === 'none') return 'text-red-400'
  if (s === 'reality') return 'text-green-400'
  if (s === 'tls' || s === 'xtls') return 'text-blue-400'
  return 'text-dark-200'
}

const STATUS_STYLE: Record<string, string> = {
  active: 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]',
  disabled: 'bg-gray-500',
  hidden: 'bg-yellow-400',
}

export interface HostsTableProps {
  hosts: HostRow[]
  canEdit: boolean
  canDelete: boolean
  onEdit: (h: HostRow) => void
  onEnable: (h: HostRow) => void
  onDisable: (h: HostRow) => void
  onDelete: (h: HostRow) => void
}

export function HostsTable({ hosts, canEdit, canDelete, onEdit, onEnable, onDisable, onDelete }: HostsTableProps) {
  const { t } = useTranslation()

  const secLabel = (s: string): string =>
    ({ tls: t('hosts.security.tls'), reality: t('hosts.security.reality'), none: t('hosts.security.none'), xtls: t('hosts.security.xtls'), default: t('hosts.security.default') }[s] || s)

  const columns: ColumnSpec<HostRow>[] = useMemo(
    () => [
      { key: 'remark', sortAccessor: (h) => h.remark || '' },
      { key: 'address', sortAccessor: (h) => h.address },
      { key: 'security', sortAccessor: (h) => sec(h), filterAccessor: (h) => sec(h), filterType: 'select' },
      { key: 'inbound', filterAccessor: (h) => h.inbound?.tag ?? '', filterType: 'select' },
      { key: 'tag', sortAccessor: (h) => (h.tags || []).join(', ') || h.tag || '', filterAccessor: (h) => (h.tags || []).join(', ') || h.tag || '', filterType: 'select' },
      { key: 'status', sortAccessor: (h) => ({ active: 0, hidden: 1, disabled: 2 })[hostStatus(h)], filterAccessor: (h) => hostStatus(h), filterType: 'select' },
    ],
    [],
  )

  const { rows, sort, toggleSort, filters, setFilter } = useTableControls(hosts, columns, {
    initialSort: { key: 'remark', dir: 'asc' },
  })

  const uniq = (vals: (string | null | undefined)[]) => Array.from(new Set(vals.filter((v): v is string => !!v)))
  const securityOptions = useMemo(() => uniq(hosts.map((h) => sec(h))).map((s) => ({ value: s, label: secLabel(s) })), [hosts])
  const inboundOptions = useMemo(() => uniq(hosts.map((h) => h.inbound?.tag)).map((v) => ({ value: v, label: v })), [hosts])
  const tagOptions = useMemo(() => uniq(hosts.flatMap((h) => h.tags || (h.tag ? [h.tag] : []))).map((v) => ({ value: v, label: v })), [hosts])
  const statusOptions = [
    { value: 'active', label: t('hosts.statusActive') },
    { value: 'disabled', label: t('hosts.statusDisabled') },
    { value: 'hidden', label: t('hosts.statusHidden') },
  ]

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableTh label={t('hosts.table.remark', { defaultValue: 'Хост' })} sortKey="remark" currentSort={sort} onSort={toggleSort} />
          <SortableTh label={t('hosts.table.address', { defaultValue: 'Адрес' })} sortKey="address" currentSort={sort} onSort={toggleSort} className="hidden md:table-cell" />
          <SortableTh label={t('hosts.table.security', { defaultValue: 'Security' })} sortKey="security" currentSort={sort} onSort={toggleSort}
            filter={{ type: 'select', options: securityOptions, value: filters.security, onChange: (v) => setFilter('security', v) }} />
          <SortableTh label={t('hosts.table.inbound', { defaultValue: 'Inbound' })} className="hidden lg:table-cell"
            filter={{ type: 'select', options: inboundOptions, value: filters.inbound, onChange: (v) => setFilter('inbound', v) }} />
          <SortableTh label={t('hosts.table.nodes', { defaultValue: 'Ноды' })} align="right" className="hidden lg:table-cell" />
          <SortableTh label={t('hosts.table.tag', { defaultValue: 'Тег' })} sortKey="tag" currentSort={sort} onSort={toggleSort} className="hidden md:table-cell"
            filter={{ type: 'select', options: tagOptions, value: filters.tag, onChange: (v) => setFilter('tag', v) }} />
          <SortableTh label={t('hosts.table.status', { defaultValue: 'Статус' })} sortKey="status" currentSort={sort} onSort={toggleSort}
            filter={{ type: 'select', options: statusOptions, value: filters.status, onChange: (v) => setFilter('status', v) }} />
          <SortableTh label="" className="w-px" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((host) => {
          const status = hostStatus(host)
          const s = sec(host)
          const scopeEdit = canEdit && (host.allowed_actions == null || host.allowed_actions.includes('edit'))
          const scopeDelete = canDelete && (host.allowed_actions == null || host.allowed_actions.includes('delete'))
          return (
            <TableRow key={host.uuid}>
              <TableCell>
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="font-medium text-white truncate max-w-[180px]">{host.remark || '—'}</span>
                  {host.is_hidden && <Badge variant="secondary" className="text-[9px] px-1 py-0 bg-yellow-500/10 text-yellow-400">{t('hosts.statusHidden')}</Badge>}
                </div>
                <div className="text-xs text-dark-300 font-mono truncate max-w-[180px] md:hidden">{host.address}:{host.port}</div>
              </TableCell>
              <TableCell className="font-mono text-xs text-dark-200 hidden md:table-cell whitespace-nowrap">{host.address}:{host.port}</TableCell>
              <TableCell className={cn('text-sm', secColor(s))}>{secLabel(s)}</TableCell>
              <TableCell className="hidden lg:table-cell">
                {host.inbound ? (
                  <span className="text-xs text-dark-100">{host.inbound.tag} <span className="text-dark-400">{host.inbound.type}</span></span>
                ) : <span className="text-dark-400">—</span>}
              </TableCell>
              <TableCell className="text-right hidden lg:table-cell">
                {host.nodes && host.nodes.length > 0 ? (
                  <span className="text-xs text-dark-100" title={host.nodes.map((n) => n.name).join(', ')}>{host.nodes.length}</span>
                ) : <span className="text-dark-400">—</span>}
              </TableCell>
              <TableCell className="hidden md:table-cell">
                {host.tags && host.tags.length > 0 ? <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20">{host.tags.join(', ')}</span> : <span className="text-dark-400">—</span>}
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-1.5 text-xs text-dark-100">
                  <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} />
                  {status === 'active' ? t('hosts.statusActive') : status === 'disabled' ? t('hosts.statusDisabled') : t('hosts.statusHidden')}
                </span>
              </TableCell>
              <TableCell className="text-right">
                {(scopeEdit || scopeDelete) && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-dark-200 hover:text-white">
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {scopeEdit && <DropdownMenuItem onClick={() => onEdit(host)}><Pencil className="w-3.5 h-3.5 mr-2" />{t('hosts.actions.edit', { defaultValue: 'Изменить' })}</DropdownMenuItem>}
                      {scopeEdit && (host.is_disabled
                        ? <DropdownMenuItem onClick={() => onEnable(host)}><Play className="w-3.5 h-3.5 mr-2 text-green-400" />{t('hosts.actions.enable', { defaultValue: 'Включить' })}</DropdownMenuItem>
                        : <DropdownMenuItem onClick={() => onDisable(host)}><Square className="w-3.5 h-3.5 mr-2 text-red-400" />{t('hosts.actions.disable', { defaultValue: 'Выключить' })}</DropdownMenuItem>)}
                      {scopeDelete && <><DropdownMenuSeparator /><DropdownMenuItem onClick={() => onDelete(host)} className="text-red-400 focus:text-red-300"><Trash2 className="w-3.5 h-3.5 mr-2" />{t('hosts.actions.delete', { defaultValue: 'Удалить' })}</DropdownMenuItem></>}
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
