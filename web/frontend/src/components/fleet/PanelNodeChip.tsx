import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useHasPermission } from '@/components/PermissionGate'

/**
 * Метка «нода панели» у машины во «Флоте»: ведёт на вкладку нод к этой же
 * ноде — юзеры, трафик, шейпер. Серверам вне панели её не показываем.
 */
export function PanelNodeChip({ uuid }: { uuid: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const canNodes = useHasPermission('nodes', 'view')
  if (!canNodes) return null
  return (
    <button
      type="button"
      onClick={(e) => {
        // карточка раскрывается по клику — переход не должен её дёргать
        e.stopPropagation()
        navigate(`/servers?tab=nodes&node=${uuid}`)
      }}
      className="shrink-0 rounded border border-violet-500/40 bg-violet-500/10 px-1 text-[10px] leading-4 text-violet-300 hover:bg-violet-500/20"
      title={t('servers.openInNodes')}
    >
      {t('servers.panelNode')}
    </button>
  )
}
