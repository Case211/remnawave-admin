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

const AUDIT_ACTION_LABELS: Record<string, string> = {
  create_user: 'создал пользователя',
  update_user: 'обновил пользователя',
  delete_user: 'удалил пользователя',
  enable_user: 'включил пользователя',
  disable_user: 'отключил пользователя',
  revoke_sub: 'отозвал подписку',
  create_host: 'создал хост',
  update_host: 'обновил хост',
  delete_host: 'удалил хост',
  update_settings: 'изменил настройки',
  create_admin: 'создал администратора',
  update_admin: 'обновил администратора',
  delete_admin: 'удалил администратора',
  create_role: 'создал роль',
  update_role: 'обновил роль',
  delete_role: 'удалил роль',
  login: 'вошёл в систему',
  resolve_violation: 'обработал нарушение',
}

const AUDIT_RESOURCE_LABELS: Record<string, string> = {
  users: 'пользователя',
  hosts: 'хост',
  nodes: 'ноду',
  settings: 'настройки',
  admins: 'администратора',
  roles: 'роль',
  violations: 'нарушение',
}

function formatAuditAction(action: string, resource: string): string {
  const label = AUDIT_ACTION_LABELS[action]
  if (label) return label

  // Fallback: try to build from action + resource
  const resLabel = AUDIT_RESOURCE_LABELS[resource]
  if (resLabel) return `${action} ${resLabel}`
  return `${action} ${resource || ''}`
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000]
const TOPICS = ['node_status', 'user_update', 'violation', 'connection', 'hwid_update']

// Close code 4001 = auth failure from backend
const AUTH_FAILURE_CODE = 4001

export function useRealtimeUpdates() {
  const queryClient = useQueryClient()
  const setTokens = useAuthStore((s) => s.setTokens)
  const logout = useAuthStore((s) => s.logout)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const isMounted = useRef(true)
  const isRefreshing = useRef(false)

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      if (event.data === 'pong' || event.data === 'ping') return

      try {
        const msg: WsMessage = JSON.parse(event.data)

        switch (msg.type) {
          case 'node_status':
            queryClient.invalidateQueries({ queryKey: ['nodes'] })
            queryClient.invalidateQueries({ queryKey: ['fleet'] })
            queryClient.invalidateQueries({ queryKey: ['systemComponents'] })
            break
          case 'user_update':
            queryClient.invalidateQueries({ queryKey: ['users'] })
            queryClient.invalidateQueries({ queryKey: ['overview'] })
            if (msg.data?.uuid) {
              queryClient.invalidateQueries({ queryKey: ['user', msg.data.uuid] })
              queryClient.invalidateQueries({ queryKey: ['user-hwid-devices', msg.data.uuid] })
              queryClient.invalidateQueries({ queryKey: ['user-traffic-stats', msg.data.uuid] })
            }
            break
          case 'hwid_update':
            queryClient.invalidateQueries({ queryKey: ['users'] })
            if (msg.data?.uuid) {
              queryClient.invalidateQueries({ queryKey: ['user-hwid-devices', msg.data.uuid] })
              queryClient.invalidateQueries({ queryKey: ['user', msg.data.uuid] })
            }
            break
          case 'violation':
            queryClient.invalidateQueries({ queryKey: ['violations'] })
            queryClient.invalidateQueries({ queryKey: ['violationStats'] })
            queryClient.invalidateQueries({ queryKey: ['deltas'] })
            break
          case 'connection':
            queryClient.invalidateQueries({ queryKey: ['nodes'] })
            queryClient.invalidateQueries({ queryKey: ['fleet'] })
            break
          case 'activity':
            // Refresh dashboard-related queries
            queryClient.invalidateQueries({ queryKey: ['analytics'] })
            queryClient.invalidateQueries({ queryKey: ['overview'] })
            queryClient.invalidateQueries({ queryKey: ['timeseries'] })
            queryClient.invalidateQueries({ queryKey: ['deltas'] })
            break
          case 'audit': {
            // Refresh audit log queries
            queryClient.invalidateQueries({ queryKey: ['audit-logs'] })
            queryClient.invalidateQueries({ queryKey: ['audit-stats'] })

            // Show toast for actions by OTHER admins
            const currentUser = useAuthStore.getState().user
            const auditAdmin = msg.data?.admin_username as string | undefined
            if (auditAdmin && currentUser?.username && auditAdmin !== currentUser.username) {
              const action = (msg.data?.action as string) || ''
              const resource = (msg.data?.resource as string) || ''
              toast.info(
                `${auditAdmin}: ${formatAuditAction(action, resource)}`,
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
    [queryClient],
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
      // Subscribe to topics
      ws.send(JSON.stringify({ type: 'subscribe', topics: TOPICS }))
    }

    ws.onmessage = handleMessage

    ws.onclose = (event) => {
      if (!isMounted.current) return

      // Auth failure — try to refresh token before reconnecting
      if (event.code === AUTH_FAILURE_CODE) {
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
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])
}
