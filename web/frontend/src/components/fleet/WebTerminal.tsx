/**
 * WebTerminal — xterm.js terminal connected to a node via WebSocket.
 *
 * Uses @xterm/xterm + @xterm/addon-fit for responsive terminal.
 * Connects to WS /api/v2/fleet/{nodeUuid}/terminal?token=JWT.
 * All data is base64-encoded over WebSocket.
 */
import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useAuthStore } from '@/store/authStore'

interface WebTerminalProps {
  nodeUuid: string
  nodeName: string
  onDisconnect?: () => void
  onReady?: () => void
}

type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

function getWsUrl(nodeUuid: string, token: string): string {
  const envUrl = window.__ENV?.API_URL || import.meta.env.VITE_API_URL || ''

  let base: string
  if (!envUrl) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}/api/v2`
  } else {
    let url = envUrl
    if (window.location.protocol === 'https:' && url.startsWith('http://')) {
      url = url.replace('http://', 'https://')
    }
    const proto = url.startsWith('https') ? 'wss:' : 'ws:'
    const host = url.replace(/^https?:\/\//, '')
    base = `${proto}//${host}/api/v2`
  }

  return `${base}/fleet/${nodeUuid}/terminal?token=${encodeURIComponent(token)}`
}

export default function WebTerminal({ nodeUuid, nodeName, onDisconnect, onReady }: WebTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<ConnectionState>('connecting')

  // Store callbacks in refs so the effect doesn't re-run when they change
  const onDisconnectRef = useRef(onDisconnect)
  const onReadyRef = useRef(onReady)
  onDisconnectRef.current = onDisconnect
  onReadyRef.current = onReady

  useEffect(() => {
    const token = useAuthStore.getState().accessToken
    if (!token || !containerRef.current) return

    // Cancelled flag — set by cleanup to prevent the deferred connect
    // from running after React.StrictMode's synchronous unmount.
    let cancelled = false
    let ws: WebSocket | null = null
    let term: Terminal | null = null
    let resizeObserver: ResizeObserver | null = null

    // Defer the actual WebSocket connection by a tick.  In React 18
    // StrictMode (dev), effects run mount → cleanup → mount.  The first
    // mount's cleanup fires synchronously, setting cancelled = true
    // before the timeout fires, so only the *second* mount actually
    // opens the WebSocket — preventing the phantom first session.
    const connectTimer = setTimeout(() => {
      if (cancelled || !containerRef.current) return

      // Create terminal
      term = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        theme: {
          background: '#0a0a0f',
          foreground: '#e4e4e7',
          cursor: '#a78bfa',
          selectionBackground: '#a78bfa40',
          black: '#18181b',
          red: '#ef4444',
          green: '#22c55e',
          yellow: '#eab308',
          blue: '#3b82f6',
          magenta: '#a855f7',
          cyan: '#06b6d4',
          white: '#e4e4e7',
          brightBlack: '#52525b',
          brightRed: '#f87171',
          brightGreen: '#4ade80',
          brightYellow: '#facc15',
          brightBlue: '#60a5fa',
          brightMagenta: '#c084fc',
          brightCyan: '#22d3ee',
          brightWhite: '#fafafa',
        },
        allowProposedApi: true,
      })

      const fitAddon = new FitAddon()
      const webLinksAddon = new WebLinksAddon()

      term.loadAddon(fitAddon)
      term.loadAddon(webLinksAddon)

      term.open(containerRef.current!)
      fitAddon.fit()

      termRef.current = term
      fitRef.current = fitAddon

      term.writeln(`\x1b[1;35mConnecting to ${nodeName}...\x1b[0m\r\n`)

      // Connect WebSocket
      const url = getWsUrl(nodeUuid, token)
      ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setState('connecting')
      }

      ws.onmessage = (event) => {
        const data = event.data

        // Try JSON messages
        if (data.startsWith('{')) {
          try {
            const msg = JSON.parse(data)
            if (msg.type === 'ready') {
              setState('connected')
              term!.writeln('\x1b[1;32mConnected.\x1b[0m\r\n')
              onReadyRef.current?.()
              return
            }
            if (msg.type === 'error') {
              term!.writeln(`\x1b[1;31mError: ${msg.message}\x1b[0m\r\n`)
              setState('error')
              return
            }
            if (msg.type === 'ping') {
              ws!.send(JSON.stringify({ type: 'pong' }))
              return
            }
            return
          } catch {
            // Not JSON, treat as terminal data
          }
        }

        // Base64-encoded terminal output
        try {
          const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0))
          term!.write(bytes)
        } catch {
          // Plain text fallback
          term!.write(data)
        }
      }

      ws.onclose = () => {
        if (cancelled) return
        setState('disconnected')
        term?.writeln('\r\n\x1b[1;33mDisconnected.\x1b[0m')
        onDisconnectRef.current?.()
      }

      ws.onerror = () => {
        if (cancelled) return
        setState('error')
      }

      // Forward keyboard input
      term.onData((data) => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(btoa(data))
        }
      })

      // Handle resize
      resizeObserver = new ResizeObserver(() => {
        try {
          fitAddon.fit()
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'resize',
              cols: term!.cols,
              rows: term!.rows,
            }))
          }
        } catch {
          // Ignore resize errors during cleanup
        }
      })

      if (containerRef.current) {
        resizeObserver.observe(containerRef.current)
      }
    }, 0)

    return () => {
      cancelled = true
      clearTimeout(connectTimer)
      resizeObserver?.disconnect()
      if (ws) {
        ws.onclose = null  // prevent onDisconnect callback during cleanup
        ws.close()
      }
      term?.dispose()
      termRef.current = null
      fitRef.current = null
      wsRef.current = null
    }
  // Only reconnect when the target node changes, not on callback changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeUuid, nodeName])

  return (
    <div className="relative w-full h-full min-h-[300px]">
      {state === 'connecting' && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded bg-yellow-500/20 text-yellow-400">
          Connecting...
        </div>
      )}
      {state === 'connected' && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded bg-green-500/20 text-green-400">
          Connected
        </div>
      )}
      {state === 'disconnected' && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded bg-red-500/20 text-red-400">
          Disconnected
        </div>
      )}
      {state === 'error' && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded bg-red-500/20 text-red-400">
          Error
        </div>
      )}
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ background: '#0a0a0f' }}
      />
    </div>
  )
}
