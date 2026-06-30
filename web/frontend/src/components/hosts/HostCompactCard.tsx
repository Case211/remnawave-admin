import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, Pencil, Play, Square, Trash2, Wifi, WifiOff, Server } from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import type { HostRow } from './HostsTable'

function sec(h: HostRow): string {
  return h.security_layer || h.security || 'none'
}
function secColor(s: string): string {
  if (s === 'none') return 'text-red-400'
  if (s === 'reality') return 'text-green-400'
  if (s === 'tls' || s === 'xtls') return 'text-blue-400'
  return 'text-dark-200'
}

export interface HostCompactCardProps {
  host: HostRow
  canEdit: boolean
  canDelete: boolean
  onEdit: (h: HostRow) => void
  onEnable: (h: HostRow) => void
  onDisable: (h: HostRow) => void
  onDelete: (h: HostRow) => void
}

export function HostCompactCard({ host, canEdit, canDelete, onEdit, onEnable, onDisable, onDelete }: HostCompactCardProps) {
  const { t } = useTranslation()
  const s = sec(host)
  const secLabel = ({ tls: t('hosts.security.tls'), reality: t('hosts.security.reality'), none: t('hosts.security.none'), xtls: t('hosts.security.xtls'), default: t('hosts.security.default') } as Record<string, string>)[s] || s
  const scopeEdit = canEdit && (host.allowed_actions == null || host.allowed_actions.includes('edit'))
  const scopeDelete = canDelete && (host.allowed_actions == null || host.allowed_actions.includes('delete'))

  return (
    <Card className={cn('group', host.is_disabled && 'opacity-60')}>
      <CardContent className="p-3 space-y-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={cn('p-1.5 rounded-md shrink-0', host.is_disabled ? 'bg-gray-500/10' : 'bg-green-500/10')}>
            {host.is_disabled ? <WifiOff className="w-4 h-4 text-dark-200" /> : <Wifi className="w-4 h-4 text-green-400" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="font-medium text-white text-sm truncate">{host.remark || t('hosts.statusNoName')}</span>
              {host.tags && host.tags.length > 0 && <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20 shrink-0">{host.tags.join(', ')}</span>}
              {host.is_hidden && <Badge variant="secondary" className="text-[9px] px-1 py-0 bg-yellow-500/10 text-yellow-400 shrink-0">{t('hosts.statusHidden')}</Badge>}
            </div>
            <div className="text-[11px] text-dark-300 font-mono truncate">{host.address}:{host.port}</div>
          </div>
          {(scopeEdit || scopeDelete) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost" className="h-6 w-6 text-dark-300 hover:text-white shrink-0">
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
        </div>

        <div className="flex items-center gap-2 text-[11px]">
          <span className={cn('font-medium', secColor(s))}>{secLabel}</span>
          {host.inbound && <span className="text-dark-300 truncate">· {host.inbound.tag}</span>}
          {host.nodes && host.nodes.length > 0 && (
            <span className="inline-flex items-center gap-1 text-dark-200 ml-auto shrink-0" title={host.nodes.map((n) => n.name).join(', ')}>
              <Server className="w-3 h-3" />{host.nodes.length}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
