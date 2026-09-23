import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, RefreshCw, Pencil, Play, Square, Key, Scan, Trash2, Gauge, Activity } from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import { useHasPermission } from '@/components/PermissionGate'

/** Нода в списке — общее для карточки, компактного вида и таблицы. */
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
  traffic_limit_bytes?: number | null
  traffic_reset_day?: number | null
  is_traffic_tracking_active?: boolean
  /** Когда нода последний раз сменила статус в панели */
  last_status_change?: string | null
  node_version?: string | null
  /** Порядок в панели (он же порядок локаций в подписке) */
  view_position?: number | null
  config_profile_uuid?: string | null
  active_inbound_uuids?: string[]
  country_code?: string | null
  note?: string | null
  node_consumption_multiplier?: number | null
  cpu_usage?: number | null
  memory_usage?: number | null
  uptime_seconds?: number | null
  download_speed_bps?: number
  upload_speed_bps?: number
  has_agent_token?: boolean
  agent_v2_connected?: boolean
  allowed_actions?: string[] | null
  shaper_state?: string | null
}

export type NodeStatus = 'online' | 'offline' | 'disabled'
export type AgentStatus = 'connected' | 'offline' | 'missing'

export function nodeStatus(n: NodeRow): NodeStatus {
  if (n.is_disabled) return 'disabled'
  if (n.is_connected) return 'online'
  return 'offline'
}

export function agentStatus(n: NodeRow): AgentStatus {
  if (n.agent_v2_connected) return 'connected'
  if (n.has_agent_token) return 'offline'
  return 'missing'
}

export const STATUS_STYLE: Record<NodeStatus, string> = {
  online: 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.6)]',
  offline: 'bg-red-400',
  disabled: 'bg-gray-500',
}

export const AGENT_STYLE: Record<AgentStatus, string> = {
  connected: 'text-emerald-300',
  offline: 'text-amber-300',
  missing: 'text-dark-300',
}

/** Флаг страны из двухбуквенного кода; неизвестный код — пусто. */
export function countryFlag(code?: string | null): string {
  if (!code || !/^[A-Za-z]{2}$/.test(code)) return ''
  return String.fromCodePoint(...code.toUpperCase().split('').map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}

export interface NodeActions {
  onRestart: (n: NodeRow) => void
  onEdit: (n: NodeRow) => void
  onEnable: (n: NodeRow) => void
  onDisable: (n: NodeRow) => void
  onDelete: (n: NodeRow) => void
  onTokenManage: (n: NodeRow) => void
  onShaper: (n: NodeRow) => void
  onFetchIps: (n: NodeRow) => void
}

/**
 * Меню действий ноды — одно на все три вида. Раньше в каждом виде было своё,
 * и они разошлись: разный порядок пунктов, разные иконки, в компактном виде
 * «Перезапуск» был только у онлайн-нод.
 */
export function NodeActionsMenu({
  node,
  canEdit,
  canDelete,
  actions,
  className,
}: {
  node: NodeRow
  canEdit: boolean
  canDelete: boolean
  actions: NodeActions
  className?: string
}) {
  const { t } = useTranslation()
  // Роль разрешает, но политика доступа к конкретной ноде может сузить
  const edit = canEdit && (node.allowed_actions == null || node.allowed_actions.includes('edit'))
  const remove = canDelete && (node.allowed_actions == null || node.allowed_actions.includes('delete'))
  // IP юзеров — это данные о юзерах: бэкенд пускает с правом users:view
  const ips = useHasPermission('users', 'view')
  // Та же машина во «Флоте»: нагрузка, терминал, скрипты
  const fleet = useHasPermission('fleet', 'view')
  const navigate = useNavigate()
  if (!edit && !remove && !ips && !fleet) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('common.openMenu')}
          className={cn('h-8 w-8 text-dark-300 hover:text-white shrink-0', className)}
        >
          <MoreVertical className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {edit && (
          <DropdownMenuItem onClick={() => actions.onRestart(node)}>
            <RefreshCw className="w-4 h-4 mr-2" />
            {t('nodes.actions.restart')}
          </DropdownMenuItem>
        )}
        {edit && (
          <DropdownMenuItem onClick={() => actions.onEdit(node)}>
            <Pencil className="w-4 h-4 mr-2" />
            {t('nodes.actions.edit')}
          </DropdownMenuItem>
        )}
        {edit && (
          <DropdownMenuItem onClick={() => actions.onTokenManage(node)}>
            <Key className="w-4 h-4 mr-2" />
            {t('nodes.actions.agentToken')}
          </DropdownMenuItem>
        )}
        {edit && (
          <DropdownMenuItem onClick={() => actions.onShaper(node)}>
            <Gauge className="w-4 h-4 mr-2" />
            {t('nodes.actions.shaper')}
          </DropdownMenuItem>
        )}
        {ips && (
          <DropdownMenuItem onClick={() => actions.onFetchIps(node)}>
            <Scan className="w-4 h-4 mr-2" />
            {t('nodes.actions.fetchUsersIps')}
          </DropdownMenuItem>
        )}
        {fleet && (
          <DropdownMenuItem onClick={() => navigate(`/servers?node=${node.uuid}`)}>
            <Activity className="w-4 h-4 mr-2" />
            {t('servers.openInFleet')}
          </DropdownMenuItem>
        )}
        {(edit || remove) && <DropdownMenuSeparator />}
        {edit && (node.is_disabled ? (
          <DropdownMenuItem onClick={() => actions.onEnable(node)} className="text-green-400 focus:text-green-400">
            <Play className="w-4 h-4 mr-2" />
            {t('nodes.actions.enable')}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onClick={() => actions.onDisable(node)} className="text-yellow-400 focus:text-yellow-400">
            <Square className="w-4 h-4 mr-2" />
            {t('nodes.actions.disable')}
          </DropdownMenuItem>
        ))}
        {remove && (
          <DropdownMenuItem onClick={() => actions.onDelete(node)} className="text-red-400 focus:text-red-400">
            <Trash2 className="w-4 h-4 mr-2" />
            {t('nodes.actions.delete')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
