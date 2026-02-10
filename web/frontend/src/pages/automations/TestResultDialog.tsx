import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, AlertTriangle } from 'lucide-react'
import type { AutomationTestResult } from '../../api/automations'

interface TestResultDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: AutomationTestResult | null
}

export function TestResultDialog({ open, onOpenChange, result }: TestResultDialogProps) {
  if (!result) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Результат тестирования</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* Trigger status */}
          <div className="flex items-center gap-3 p-4 rounded-lg bg-dark-800/50 border border-dark-700">
            {result.would_trigger ? (
              <AlertTriangle className="w-6 h-6 text-yellow-400 flex-shrink-0" />
            ) : (
              <CheckCircle className="w-6 h-6 text-emerald-400 flex-shrink-0" />
            )}
            <div>
              <p className="text-sm font-medium text-white">
                {result.would_trigger ? 'Правило сработало бы' : 'Правило не сработало бы'}
              </p>
              <p className="text-xs text-dark-300 mt-1">{result.details}</p>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-dark-800/50 border border-dark-700">
              <p className="text-xs text-dark-400">Подходящих целей</p>
              <p className="text-lg font-semibold text-white mt-1">
                {result.matching_targets.length}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-dark-800/50 border border-dark-700">
              <p className="text-xs text-dark-400">Ожидаемых действий</p>
              <p className="text-lg font-semibold text-white mt-1">
                {result.estimated_actions}
              </p>
            </div>
          </div>

          {/* Matching targets */}
          {result.matching_targets.length > 0 && (
            <div>
              <p className="text-sm font-medium text-dark-200 mb-2">
                Подходящие цели (макс. 50):
              </p>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {result.matching_targets.map((target, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 px-3 py-2 rounded bg-dark-800/30 text-xs"
                  >
                    <Badge variant="outline" className="text-[10px]">
                      {(target as Record<string, unknown>).type as string || 'unknown'}
                    </Badge>
                    <span className="text-dark-200 truncate">
                      {(target as Record<string, unknown>).name as string
                        || (target as Record<string, unknown>).id as string
                        || JSON.stringify(target)}
                    </span>
                    {(target as Record<string, unknown>).value !== undefined && (
                      <span className="text-dark-400 ml-auto">
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
