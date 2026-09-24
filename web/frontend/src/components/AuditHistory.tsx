import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useHasPermission } from '@/components/PermissionGate'
import { auditApi } from '@/api/audit'
import { useFormatters } from '@/lib/useFormatters'
import {
  formatDetailValue,
  getActionColor,
  getActionLabelT,
  getDetailLabel,
  getVisibleDetails,
  parseAction,
  tryParseJSON,
} from '@/lib/auditFormat'

/**
 * История действий админов с объектом — из журнала аудита. Без права
 * audit:view ничего не рендерит: иначе блок всегда был бы пустым из-за 403.
 */
export function AuditHistory({
  resource,
  resourceId,
  limit = 20,
  enabled = true,
}: {
  resource: string
  resourceId: string
  limit?: number
  /** Грузить только когда блок раскрыт */
  enabled?: boolean
}) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const canView = useHasPermission('audit', 'view')

  const { data, isLoading } = useQuery({
    queryKey: ['audit-history', resource, resourceId, limit],
    queryFn: () => auditApi.resourceHistory(resource, resourceId, limit),
    enabled: canView && enabled && !!resourceId,
    staleTime: 30000,
  })

  if (!canView) return null
  const items = data?.items ?? []

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
      </div>
    )
  }
  if (items.length === 0) {
    return <p className="text-center py-4 text-dark-300 text-sm">{t('audit.historyEmpty')}</p>
  }

  return (
    <div className="space-y-3">
      <div className="relative pl-6 space-y-4">
        <div className="absolute left-[9px] top-2 bottom-2 w-px bg-[var(--glass-bg-hover)]" />
        {items.map((item) => {
          const { action } = parseAction(item.action ?? '')
          const details = getVisibleDetails(tryParseJSON(item.details))
          return (
            <div key={item.id} className="relative">
              <div className="absolute -left-6 top-1 w-[7px] h-[7px] rounded-full bg-primary-400 ring-2 ring-dark-800" />
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-sm font-medium text-white">{item.admin_username}</span>
                <Badge variant="outline" className={`text-xs border ${getActionColor(action)}`}>
                  {getActionLabelT(t, action)}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {item.created_at ? formatDate(item.created_at) : ''}
                </span>
              </div>
              {details.length > 0 && (
                <div className="mt-0.5 space-y-0.5">
                  {details.slice(0, 6).map(([key, value]) => (
                    <p key={key} className="text-xs text-dark-300 break-words">
                      <span className="text-dark-400">{getDetailLabel(t, key)}:</span>{' '}
                      <span className="text-dark-200">{formatDetailValue(t, key, value)}</span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <Link
        to={`/audit?resource_id=${encodeURIComponent(resourceId)}`}
        className="inline-block text-xs text-primary-400 hover:underline"
      >
        {t('audit.historyOpen')}
      </Link>
    </div>
  )
}
