import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, RotateCcw, Pencil, Play, Square, Key, Globe, Trash2, Bot, BotOff, Gauge, Users, BarChart3 } from '@/components/brand/icons'
import { ShaperBadge } from './ShaperBadge'
import { cn } from '@/lib/utils'
import type { NodeRow } from './NodesTable'

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

export interface NodeCompactCardProps {
  node: NodeRow
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

export function NodeCompactCard({
  node,
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
}: NodeCompactCardProps) {
  const { t } = useTranslation()
  const { formatBytes, formatTimeAgo } = useFormatters()
  const status = nodeStatus(node)
  const agent = agentStatus(node)
  const scopeEdit = canEdit && (node.allowed_actions == null || node.allowed_actions.includes('edit'))
  const scopeDelete = canDelete && (node.allowed_actions == null || node.allowed_actions.includes('delete'))
  const isOnline = node.is_connected && !node.is_disabled

  return (
    <Card className={cn('group', node.is_disabled && 'opacity-60')}>
      <CardContent className="p-3 space-y-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} role="img" title={t(`nodes.status.${status}`)} aria-label={t(`nodes.status.${status}`)} />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-white text-sm truncate leading-tight">{node.name}</div>
            <div className="text-[11px] text-dark-300 font-mono truncate">{node.address}:{node.port}</div>
          </div>
          {(scopeEdit || scopeDelete) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost" aria-label={t('common.openMenu')} className="h-6 w-6 text-dark-300 hover:text-white shrink-0">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {scopeEdit && isOnline && <DropdownMenuItem onClick={() => onRestart(node)}><RotateCcw className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.restart')}</DropdownMenuItem>}
                {scopeEdit && <DropdownMenuItem onClick={() => onEdit(node)}><Pencil className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.edit', { defaultValue: 'Изменить' })}</DropdownMenuItem>}
                {scopeEdit && (node.is_disabled
                  ? <DropdownMenuItem onClick={() => onEnable(node)}><Play className="w-3.5 h-3.5 mr-2 text-green-400" />{t('nodes.actions.enable')}</DropdownMenuItem>
                  : <DropdownMenuItem onClick={() => onDisable(node)}><Square className="w-3.5 h-3.5 mr-2 text-red-400" />{t('nodes.actions.disable')}</DropdownMenuItem>)}
                {scopeEdit && <DropdownMenuItem onClick={() => onTokenManage(node)}><Key className="w-3.5 h-3.5 mr-2" />{t('nodes.agent.token', { defaultValue: 'Токен агента' })}</DropdownMenuItem>}
                {scopeEdit && <DropdownMenuItem onClick={() => onShaper(node)}><Gauge className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.shaper')}</DropdownMenuItem>}
                <DropdownMenuItem onClick={() => onFetchIps(node)}><Globe className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.fetchIps', { defaultValue: 'IP юзеров' })}</DropdownMenuItem>
                {scopeDelete && <><DropdownMenuSeparator /><DropdownMenuItem onClick={() => onDelete(node)} className="text-red-400 focus:text-red-300"><Trash2 className="w-3.5 h-3.5 mr-2" />{t('nodes.actions.delete', { defaultValue: 'Удалить' })}</DropdownMenuItem></>}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        <div className="flex items-center gap-3 text-[11px]">
          <span className={cn('inline-flex items-center gap-1', AGENT_STYLE[agent])}>
            {agent === 'missing' ? <BotOff className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            {t(`nodes.agent.${agent}`)}
          </span>
          <ShaperBadge state={node.shaper_state} />
          <span className="inline-flex items-center gap-1 text-dark-100 ml-auto">
            <Users className="w-3.5 h-3.5 text-cyan-400" />
            {node.users_online}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] text-dark-200 font-mono">
          <BarChart3 className="w-3.5 h-3.5 text-violet-400 shrink-0" />
          <span className="text-dark-100">{formatBytes(node.traffic_today_bytes)}</span>
          <span className="text-dark-500">/</span>
          <span>{formatBytes(node.traffic_total_bytes)}</span>
          {node.last_seen_at && !isOnline && (
            <span className="ml-auto text-dark-400">{formatTimeAgo(node.last_seen_at)}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
