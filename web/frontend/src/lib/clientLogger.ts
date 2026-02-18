import client from '@/api/client'

interface FrontendLogEntry {
  level: string
  message: string
  source?: string
  stack?: string
  url?: string
  userAgent?: string
  timestamp?: string
}

class ClientLogger {
  private buffer: FrontendLogEntry[] = []
  private flushInterval: ReturnType<typeof setInterval> | null = null
  private originalConsoleError: typeof console.error | null = null
  private initialized = false

  init() {
    if (this.initialized) return
    this.initialized = true

    // Capture unhandled errors
    window.addEventListener('error', (event) => {
      this.capture({
        level: 'ERROR',
        message: event.message || 'Unknown error',
        source: 'window.onerror',
        stack: event.error?.stack,
        url: event.filename ? `${event.filename}:${event.lineno}:${event.colno}` : undefined,
      })
    })

    // Capture unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      const reason = event.reason
      this.capture({
        level: 'ERROR',
        message: reason?.message || String(reason) || 'Unhandled rejection',
        source: 'unhandledrejection',
        stack: reason?.stack,
      })
    })

    // Intercept console.error
    this.originalConsoleError = console.error
    console.error = (...args: unknown[]) => {
      this.capture({
        level: 'ERROR',
        message: args.map((a) => (typeof a === 'object' ? JSON.stringify(a) : String(a))).join(' '),
        source: 'console.error',
      })
      this.originalConsoleError?.apply(console, args)
    }

    // Flush every 10 seconds
    this.flushInterval = setInterval(() => this.flush(), 10000)
  }

  capture(entry: Omit<FrontendLogEntry, 'timestamp' | 'userAgent'>) {
    this.buffer.push({
      ...entry,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      userAgent: navigator.userAgent,
    })

    // Auto-flush if buffer is large
    if (this.buffer.length >= 50) {
      this.flush()
    }
  }

  async flush() {
    if (this.buffer.length === 0) return

    const entries = [...this.buffer]
    this.buffer = []

    try {
      await client.post('/logs/frontend', entries)
    } catch {
      // Silent fail — don't recurse into error logging
    }
  }

  destroy() {
    if (this.flushInterval) {
      clearInterval(this.flushInterval)
      this.flushInterval = null
    }
    if (this.originalConsoleError) {
      console.error = this.originalConsoleError
      this.originalConsoleError = null
    }
    this.flush()
    this.initialized = false
  }
}

export const clientLogger = new ClientLogger()
