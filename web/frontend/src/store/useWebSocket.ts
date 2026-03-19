/**
 * WebSocket hook for real-time updates from Remnawave backend.
 *
 * Connects to ws://host/api/v2/ws?token=JWT and listens for events:
 *   node_status, user_update, violation, connection, activity
 *
 * Automatically invalidates React Query caches when relevant events arrive.
 * Handles token expiry by refreshing before reconnect.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAuthStore } from './authStore'
import { authApi } from '../api/auth'

interface WsMessage {
  type: string
  data?: Record<string, unknown>
  timestamp?: string
}

function getWsUrl(token: string): string {
  const envUrl = window.__ENV?.API_URL || import.meta.env.VITE_API_URL || ''

  let base: string
  if (!envUrl) {
    // Relative — derive from current page location
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}/api/v2`
  } else {
    // Absolute URL supplied
    let url = envUrl
    if (window.location.protocol === 'https:' && url.startsWith('http://')) {
      url = url.replace('http://', 'https://')
    }
    const proto = url.startsWith('https') ? 'wss:' : 'ws:'
    const host = url.replace(/^https?:\/\//, '')
    base = `${proto}//${host}/api/v2`
  }

  return `${base}/ws?token=${encodeURIComponent(token)}`
}

function formatAuditAction(action: string, resource: string, t: (key: string) => string): string {
  // Try exact i18n description: audit.descriptions.{action}.{resource}
  const descKey = `audit.descriptions.${action}.${resource}`
  const desc = t(descKey)
  if (desc !== descKey) return desc

  // Try splitting compound action (e.g., create_user → create + user)
  const idx = action.indexOf('_')
  if (idx > 0) {
    const verb = action.slice(0, idx)
    const noun = action.slice(idx + 1)
    const compoundKey = `audit.descriptions.${verb}.${noun}`
    const compoundDesc = t(compoundKey)
    if (compoundDesc !== compoundKey) return compoundDesc
  }

  // Compose from action + resource labels
  const actionKey = `audit.actions.${action}`
  const actionLabel = t(actionKey)
  const resourceKey = `audit.resources.${resource}`
  const resourceLabel = t(resourceKey)
  const resolvedAction = actionLabel !== actionKey ? actionLabel : action
  const resolvedResource = resourceLabel !== resourceKey ? resourceLabel : resource
  return resolvedResource ? `${resolvedAction}: ${resolvedResource}` : resolvedAction
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000]
const TOPICS = ['node_status', 'user_update', 'violation', 'connection', 'hwid_update', 'notification', 'dashboard']

// Close code 4001 = auth failure from backend
const AUTH_FAILURE_CODE = 4001
// Stop reconnecting after this many consecutive auth failures
const MAX_AUTH_FAILURES = 3

export function useRealtimeUpdates() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const setTokens = useAuthStore((s) => s.setTokens)
  const logout = useAuthStore((s) => s.logout)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const authFailureCount = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const isMounted = useRef(true)
  const isRefreshing = useRef(false)

  // Debounced invalidation: batch multiple invalidations within 500ms window
  const pendingInvalidations = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const debouncedInvalidate = useCallback((queryKey: string[]) => {
    const key = JSON.stringify(queryKey)
    const existing = pendingInvalidations.current.get(key)
    if (existing) clearTimeout(existing)
    pendingInvalidations.current.set(key, setTimeout(() => {
      pendingInvalidations.current.delete(key)
      queryClient.invalidateQueries({ queryKey })
    }, 500))
  }, [queryClient])

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      if (event.data === 'pong' || event.data === 'ping') return

      try {
        const msg: WsMessage = JSON.parse(event.data)

        switch (msg.type) {
          case 'node_status':
            debouncedInvalidate(['nodes'])
            debouncedInvalidate(['fleet'])
            debouncedInvalidate(['systemComponents'])
            debouncedInvalidate(['node-fleet-analytics'])
            debouncedInvalidate(['node-metrics-history'])
            break
          case 'user_update':
            debouncedInvalidate(['users'])
            debouncedInvalidate(['overview'])
            debouncedInvalidate(['advanced-top-users'])
            debouncedInvalidate(['advanced-shared-hwids'])
            debouncedInvalidate(['advanced-retention'])
            if (msg.data?.uuid) {
              debouncedInvalidate(['user', msg.data.uuid as string])
              debouncedInvalidate(['user-hwid-devices', msg.data.uuid as string])
              debouncedInvalidate(['user-traffic-stats', msg.data.uuid as string])
            }
            break
          case 'hwid_update':
            debouncedInvalidate(['users'])
            if (msg.data?.uuid) {
              debouncedInvalidate(['user-hwid-devices', msg.data.uuid as string])
              debouncedInvalidate(['user', msg.data.uuid as string])
            }
            break
          case 'violation':
            debouncedInvalidate(['violations'])
            debouncedInvalidate(['violationStats'])
            debouncedInvalidate(['deltas'])
            debouncedInvalidate(['advanced-trends'])
            break
          case 'connection':
            debouncedInvalidate(['nodes'])
            debouncedInvalidate(['fleet'])
            break
          case 'agent_v2_status':
            debouncedInvalidate(['fleet'])
            debouncedInvalidate(['fleet-agents'])
            break
          case 'dashboard_stats':
            // Live dashboard update — write directly to cache, no refetch
            if (msg.data) {
              queryClient.setQueryData(['overview'], (old: Record<string, unknown> | undefined) =>
                old ? { ...old, ...msg.data } : msg.data,
              )
            }
            break
          case 'activity':
            debouncedInvalidate(['analytics'])
            debouncedInvalidate(['overview'])
            debouncedInvalidate(['timeseries'])
            debouncedInvalidate(['deltas'])
            debouncedInvalidate(['advanced-geo'])
            debouncedInvalidate(['advanced-trends'])
            debouncedInvalidate(['advanced-providers'])
            break
          case 'notification': {
            // Notifications: debounce queries, but show toast immediately
            debouncedInvalidate(['notifications'])
            debouncedInvalidate(['notifications-unread'])
            debouncedInvalidate(['notifications-recent'])

            const notifTitle = msg.data?.title as string | undefined
            const notifSeverity = msg.data?.severity as string | undefined
            if (notifTitle) {
              if (notifSeverity === 'critical') {
                toast.error(notifTitle, { duration: 6000 })
              } else if (notifSeverity === 'warning') {
                toast.warning(notifTitle, { duration: 5000 })
              } else {
                toast.info(notifTitle, { duration: 4000 })
              }
            }
            break
          }
          case 'audit': {
            // Audit: debounce queries, but show toast immediately
            debouncedInvalidate(['audit-logs'])
            debouncedInvalidate(['audit-stats'])
            debouncedInvalidate(['dashboard-audit-feed'])

            const currentUser = useAuthStore.getState().user
            const auditAdmin = msg.data?.admin_username as string | undefined
            if (auditAdmin && currentUser?.username && auditAdmin !== currentUser.username) {
              const action = (msg.data?.action as string) || ''
              const resource = (msg.data?.resource as string) || ''
              toast.info(
                `${auditAdmin}: ${formatAuditAction(action, resource, t)}`,
                { duration: 4000 },
              )
            }
            break
          }
        }
      } catch {
        // Non-JSON message, ignore
      }
    },
    [debouncedInvalidate, t],
  )

  /**
   * Try to refresh the access token using the refresh token.
   * Returns the new access token or null if refresh failed.
   */
  const tryRefreshToken = useCallback(async (): Promise<string | null> => {
    if (isRefreshing.current) return null
    const currentRefreshToken = useAuthStore.getState().refreshToken
    if (!currentRefreshToken) return null

    isRefreshing.current = true
    try {
      const response = await authApi.refreshToken(currentRefreshToken)
      setTokens(response.access_token, response.refresh_token)
      return response.access_token
    } catch {
      // Refresh failed — session is dead
      logout()
      return null
    } finally {
      isRefreshing.current = false
    }
  }, [setTokens, logout])

  const connect = useCallback(() => {
    const currentToken = useAuthStore.getState().accessToken
    const currentAuth = useAuthStore.getState().isAuthenticated
    if (!currentToken || !currentAuth || !isMounted.current) return

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }

    const url = getWsUrl(currentToken)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      reconnectAttempt.current = 0
      authFailureCount.current = 0
      // Subscribe to topics
      ws.send(JSON.stringify({ type: 'subscribe', topics: TOPICS }))
    }

    ws.onmessage = handleMessage

    ws.onclose = (event) => {
      if (!isMounted.current) return

      // Auth failure — try to refresh token before reconnecting
      if (event.code === AUTH_FAILURE_CODE) {
        authFailureCount.current++
        if (authFailureCount.current > MAX_AUTH_FAILURES) {
          // Too many consecutive auth failures — stop reconnecting and logout
          logout()
          return
        }
        tryRefreshToken().then((newToken) => {
          if (newToken && isMounted.current) {
            // Got a new token, reconnect immediately
            reconnectAttempt.current = 0
            reconnectTimer.current = setTimeout(() => {
              if (isMounted.current) connect()
            }, 500)
          }
          // If refresh failed, logout was already called — no reconnect
        })
        return
      }

      // Normal reconnect with exponential backoff
      const delay =
        RECONNECT_DELAYS[
          Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)
        ]
      reconnectAttempt.current++
      reconnectTimer.current = setTimeout(() => {
        if (isMounted.current) connect()
      }, delay)
    }

    ws.onerror = () => {
      // onclose will fire after this, handling reconnect
    }
  }, [handleMessage, tryRefreshToken])

  useEffect(() => {
    isMounted.current = true
    connect()

    return () => {
      isMounted.current = false
      clearTimeout(reconnectTimer.current)
      pendingInvalidations.current.forEach(timeout => clearTimeout(timeout))
      pendingInvalidations.current.clear()
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])
}
