/**
 * WebSocket hook for real-time updates from Remnawave backend.
 *
 * Connects to ws://host/api/v2/ws?token=JWT and listens for events:
 *   node_status, user_update, violation, connection, activity
 *
 * Automatically invalidates React Query caches when relevant events arrive.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from './authStore'

interface WsMessage {
  type: string
  data?: Record<string, unknown>
  timestamp?: string
}

function getWsUrl(token: string): string {
  const envUrl = (window as any).__ENV?.API_URL || (window as any).import?.meta?.env?.VITE_API_URL || ''

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

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000]
const TOPICS = ['node_status', 'user_update', 'violation', 'connection']

export function useRealtimeUpdates() {
  const queryClient = useQueryClient()
  const accessToken = useAuthStore((s) => s.accessToken)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const isMounted = useRef(true)

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      if (event.data === 'pong' || event.data === 'ping') return

      try {
        const msg: WsMessage = JSON.parse(event.data)

        switch (msg.type) {
          case 'node_status':
            queryClient.invalidateQueries({ queryKey: ['nodes'] })
            break
          case 'user_update':
            queryClient.invalidateQueries({ queryKey: ['users'] })
            if (msg.data?.uuid) {
              queryClient.invalidateQueries({ queryKey: ['user', msg.data.uuid] })
            }
            break
          case 'violation':
            queryClient.invalidateQueries({ queryKey: ['violations'] })
            break
          case 'connection':
            queryClient.invalidateQueries({ queryKey: ['nodes'] })
            break
          case 'activity':
            // Refresh dashboard-related queries
            queryClient.invalidateQueries({ queryKey: ['analytics'] })
            break
        }
      } catch {
        // Non-JSON message, ignore
      }
    },
    [queryClient],
  )

  const connect = useCallback(() => {
    if (!accessToken || !isAuthenticated || !isMounted.current) return
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }

    const url = getWsUrl(accessToken)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      reconnectAttempt.current = 0
      // Subscribe to topics
      ws.send(JSON.stringify({ type: 'subscribe', topics: TOPICS }))
    }

    ws.onmessage = handleMessage

    ws.onclose = () => {
      if (!isMounted.current) return
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
  }, [accessToken, isAuthenticated, handleMessage])

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
