import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { WifiOff, ServerCrash, RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

type Status = 'online' | 'offline' | 'api-down'

export function OfflineIndicator() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<Status>('online')
  const failCountRef = useRef(0)

  useEffect(() => {
    const handleOnline = () => { setStatus('online'); failCountRef.current = 0 }
    const handleOffline = () => setStatus('offline')

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    if (!navigator.onLine) setStatus('offline')

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Track consecutive API failures via query cache
  useEffect(() => {
    const unsub = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === 'updated' && event.query.state.status === 'error') {
        failCountRef.current += 1
        if (failCountRef.current >= 3 && navigator.onLine) setStatus('api-down')
      }
      if (event.type === 'updated' && event.query.state.status === 'success') {
        failCountRef.current = 0
        if (navigator.onLine) setStatus('online')
      }
    })
    return () => unsub()
  }, [queryClient])

  const handleRetry = useCallback(() => {
    queryClient.invalidateQueries()
    failCountRef.current = 0
  }, [queryClient])

  if (status === 'online') return null

  const isOffline = status === 'offline'

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 animate-fade-in-up pb-safe">
      <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl backdrop-blur-xl shadow-lg border ${
        isOffline
          ? 'bg-yellow-500/15 border-yellow-500/30'
          : 'bg-red-500/15 border-red-500/30'
      }`}>
        {isOffline
          ? <WifiOff className="w-4 h-4 text-yellow-400" />
          : <ServerCrash className="w-4 h-4 text-red-400" />
        }
        <span className={`text-sm font-medium ${isOffline ? 'text-yellow-300' : 'text-red-300'}`}>
          {isOffline
            ? t('common.noConnection')
            : t('common.apiUnavailable', { defaultValue: 'Server unavailable' })
          }
        </span>
        {!isOffline && (
          <button
            onClick={handleRetry}
            className="ml-1 p-1 rounded-lg hover:bg-white/10 transition-colors"
            aria-label="Retry"
          >
            <RefreshCw className="w-3.5 h-3.5 text-red-300" />
          </button>
        )}
      </div>
    </div>
  )
}
