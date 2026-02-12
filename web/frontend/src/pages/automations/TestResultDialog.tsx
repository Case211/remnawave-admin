import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, AlertTriangle, Info, Zap, Clock } from 'lucide-react'
import type { AutomationTestResult } from '../../api/automations'

interface TestResultDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: AutomationTestResult | null
}

/** Split backend "details" string into structured parts for display */
function parseDetails(details: string): { icon: 'trigger' | 'action' | 'info'; text: string }[] {
  if (!details) return []
  return details.split('; ').map((part) => {
    const lower = part.toLowerCase()
    if (
      lower.startsWith('cron:') ||
      lower.startsWith('интервал:') ||
      lower.startsWith('interval:') ||
      lower.startsWith('триггер') ||
      lower.startsWith('event trigger') ||
      lower.startsWith('порог:') ||
      lower.startsWith('threshold:')
    ) {
      return { icon: 'trigger' as const, text: part }
    }
    if (
      lower.startsWith('действие:') ||
      lower.startsWith('action:')
    ) {
      return { icon: 'action' as const, text: part }
    }
    return { icon: 'info' as const, text: part }
  })
}

const DETAIL_ICONS = {
  trigger: Clock,
  action: Zap,
  info: Info,
}

export function TestResultDialog({ open, onOpenChange, result }: TestResultDialogProps) {
  const { t } = useTranslation()
  if (!result) return null

  const detailParts = parseDetails(result.details)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('automations.testResult.title')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* Trigger status */}
          <div
            className={`flex items-center gap-3 p-4 rounded-lg border-2 ${
              result.would_trigger
                ? 'bg-yellow-500/5 border-yellow-500/30'
                : 'bg-emerald-500/5 border-emerald-500/30'
            }`}
          >
            {result.would_trigger ? (
              <AlertTriangle className="w-6 h-6 text-yellow-400 flex-shrink-0" />
            ) : (
              <CheckCircle className="w-6 h-6 text-emerald-400 flex-shrink-0" />
            )}
            <div>
              <p className="text-sm font-medium text-white">
                {result.would_trigger ? t('automations.testResult.wouldTrigger') : t('automations.testResult.wouldNotTrigger')}
              </p>
              <p className="text-xs text-dark-300 mt-1">
                {result.would_trigger
                  ? t('automations.testResult.wouldTriggerDesc')
                  : t('automations.testResult.wouldNotTriggerDesc')}
              </p>
            </div>
          </div>

          {/* Parsed detail parts */}
          {detailParts.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-dark-400 uppercase tracking-wider">{t('automations.testResult.details')}</p>
              <div className="space-y-1.5">
                {detailParts.map((part, i) => {
                  const Icon = DETAIL_ICONS[part.icon]
                  return (
                    <div
                      key={i}
                      className="flex items-start gap-2.5 px-3 py-2 rounded-lg bg-dark-800 border-2 border-dark-600"
                    >
                      <Icon className="w-4 h-4 text-dark-400 mt-0.5 flex-shrink-0" />
                      <span className="text-sm text-dark-200">{part.text}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Stats */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600">
              <p className="text-xs text-dark-400">{t('automations.testResult.matchingTargets')}</p>
              <p className="text-lg font-semibold text-white mt-1">
                {result.matching_targets.length}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600">
              <p className="text-xs text-dark-400">{t('automations.testResult.expectedActions')}</p>
              <p className="text-lg font-semibold text-white mt-1">
                {result.estimated_actions}
              </p>
            </div>
          </div>

          {/* Matching targets */}
          {result.matching_targets.length > 0 && (
            <div>
              <p className="text-xs font-medium text-dark-400 uppercase tracking-wider mb-2">
                {t('automations.testResult.matchingTargetsMax')}
              </p>
              <div className="max-h-48 overflow-y-auto space-y-1.5">
                {result.matching_targets.map((target, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-800 border-2 border-dark-600 text-xs"
                  >
                    <Badge variant="outline" className="text-[10px] border-dark-500">
                      {(target as Record<string, unknown>).type as string || 'unknown'}
                    </Badge>
                    <span className="text-dark-200 truncate">
                      {(target as Record<string, unknown>).name as string
                        || (target as Record<string, unknown>).id as string
                        || JSON.stringify(target)}
                    </span>
                    {(target as Record<string, unknown>).value !== undefined && (
                      <span className="text-dark-400 ml-auto font-mono">
                        = {String((target as Record<string, unknown>).value)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
