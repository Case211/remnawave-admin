import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface QueryErrorProps {
  onRetry?: () => void
  message?: string
}

export function QueryError({ onRetry, message }: QueryErrorProps) {
  const { t } = useTranslation()

  return (
    <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-3">
      <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-red-400 text-sm">
          {message || t('common.loadError')}
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm text-red-400 hover:text-red-300 flex items-center gap-1.5 shrink-0"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          {t('common.retry')}
        </button>
      )}
    </div>
  )
}
