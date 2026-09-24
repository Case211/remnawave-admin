import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { Card, CardContent } from '@/components/ui/card'
import { Bot, BotOff, Users, BarChart3 } from '@/components/brand/icons'
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

export interface NodeCompactCardProps extends NodeActions {
  node: NodeRow
  canEdit: boolean
  canDelete: boolean
}

export function NodeCompactCard({ node, canEdit, canDelete, ...actions }: NodeCompactCardProps) {
  const { t } = useTranslation()
  const { formatBytes, formatSpeed, formatTimeAgo } = useFormatters()
  const status = nodeStatus(node)
  const agent = agentStatus(node)
  const isOnline = status === 'online'
  return (
    <Card className={cn('group', node.is_disabled && 'opacity-60')}>
      <CardContent className="p-3 space-y-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn('w-2 h-2 rounded-full shrink-0', STATUS_STYLE[status])} role="img" title={t(`nodes.status.${status}`)} aria-label={t(`nodes.status.${status}`)} />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-white text-sm truncate leading-tight">
              {countryFlag(node.country_code)} {node.name}
            </div>
            <div className="text-[11px] text-dark-300 font-mono truncate">{node.address}:{node.port}</div>
          </div>
          <NodeActionsMenu node={node} canEdit={canEdit} canDelete={canDelete} actions={actions} className="h-6 w-6" />
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
          <span className="text-dark-100" title={t('nodes.stats.today')}>{formatBytes(node.traffic_today_bytes)}</span>
          <span className="text-dark-500">/</span>
          <span title={t('nodes.stats.periodHint', { day: node.traffic_reset_day ?? 1 })}>{formatBytes(node.traffic_total_bytes)}</span>
          {isOnline ? (
            <span className="ml-auto text-dark-300">
              ↓{formatSpeed(node.download_speed_bps || 0)} ↑{formatSpeed(node.upload_speed_bps || 0)}
            </span>
          ) : node.last_status_change && (
            <span className="ml-auto text-dark-400">
              {t(`nodes.since.${status}`, { ago: formatTimeAgo(node.last_status_change) })}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
