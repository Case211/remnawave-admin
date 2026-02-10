import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  Pause,
  Play,
  ArrowDown,
  Trash2,
  FileText,
  Terminal,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { logsApi, type LogEntry, type LogFile } from '@/api/logs'
import { useAuthStore } from '@/store/authStore'

// ── Constants ───────────────────────────────────────────────────

const LOG_FILE_LABELS: Record<string, string> = {
  web_info: 'Web Backend (INFO)',
  web_warning: 'Web Backend (WARNING+)',
  bot_info: 'Telegram Bot (INFO)',
  bot_warning: 'Telegram Bot (WARNING+)',
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-500 font-bold',
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

// ── Component ───────────────────────────────────────────────────

export default function SystemLogs() {
  const [selectedFile, setSelectedFile] = useState('web_info')
  const [levelFilter, setLevelFilter] = useState<string>('all')
  const [searchText, setSearchText] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(true)
  const [streamLines, setStreamLines] = useState<LogEntry[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const accessToken = useAuthStore((s) => s.accessToken)

  // Fetch initial log lines
  const { data: initialData, refetch } = useQuery({
    queryKey: ['logs-tail', selectedFile, levelFilter, searchText],
    queryFn: () =>
      logsApi.tail({
        file: selectedFile,
        lines: 500,
        level: levelFilter !== 'all' ? levelFilter : undefined,
        search: searchText || undefined,
      }),
    staleTime: 10000,
  })

  // Fetch available log files
  const { data: logFiles } = useQuery({
    queryKey: ['log-files'],
    queryFn: () => logsApi.files(),
    staleTime: 30000,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [streamLines, initialData, autoScroll])

  // WebSocket streaming
  useEffect(() => {
    if (!isStreaming || !accessToken) return

    const envUrl =
      (window as any).__ENV?.API_URL ||
      import.meta.env.VITE_API_URL ||
      ''
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

    const wsUrl = `${base}/logs/stream?token=${encodeURIComponent(accessToken)}&file=${selectedFile}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setStreamLines([])
    }

    ws.onmessage = (event) => {
      if (event.data === 'pong') return
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'log_line' && msg.data) {
          const entry: LogEntry = msg.data
          // Apply client-side filters
          if (levelFilter !== 'all' && entry.level && entry.level !== levelFilter.toUpperCase()) return
          if (searchText && !(entry.message || '').toLowerCase().includes(searchText.toLowerCase())) return

          setStreamLines((prev) => {
            const next = [...prev, entry]
            // Keep last 2000 lines in memory
            return next.length > 2000 ? next.slice(-1500) : next
          })
        }
      } catch {
        // Non-JSON
      }
    }

    ws.onclose = () => {
      wsRef.current = null
    }

    // Ping to keep alive
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 30000)

    return () => {
      clearInterval(pingInterval)
      ws.onclose = null
      ws.close()
      wsRef.current = null
    }
  }, [isStreaming, selectedFile, accessToken, levelFilter, searchText])

  // Switch file via WebSocket
  const handleFileSwitch = useCallback((file: string) => {
    setSelectedFile(file)
    setStreamLines([])
  }, [])

  const handleSearch = () => {
    setSearchText(searchInput)
    setStreamLines([])
  }

  const handleClear = () => {
    setStreamLines([])
  }

  // Combine initial data with streamed lines
  const allLines = isStreaming
    ? [...(initialData?.items ?? []), ...streamLines]
    : (initialData?.items ?? [])

  return (
    <div className="p-4 md:p-6 space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Terminal className="w-6 h-6 text-primary-400" />
            Системные логи
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Просмотр логов бэкенда и бота в реальном времени
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={isStreaming ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  setIsStreaming(!isStreaming)
                  if (!isStreaming) refetch()
                }}
                className={isStreaming ? 'bg-emerald-600 hover:bg-emerald-700' : 'border-dark-600'}
              >
                {isStreaming ? (
                  <>
                    <Pause className="w-4 h-4 mr-1" />
                    Live
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-1" />
                    Paused
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {isStreaming ? 'Приостановить стриминг' : 'Возобновить стриминг'}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoScroll(!autoScroll)}
                className={cn('border-dark-600', autoScroll && 'bg-dark-700')}
              >
                <ArrowDown className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {autoScroll ? 'Автопрокрутка включена' : 'Автопрокрутка выключена'}
            </TooltipContent>
          </Tooltip>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            className="border-dark-600"
          >
            <Trash2 className="w-4 h-4 mr-1" />
            Очистить
          </Button>
        </div>
      </div>

      {/* File cards */}
      {logFiles && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {logFiles.map((f: LogFile) => (
            <Card
              key={f.key}
              className={cn(
                'bg-dark-800 border cursor-pointer transition-all hover:border-primary-400/50',
                selectedFile === f.key ? 'border-primary-400' : 'border-dark-700',
              )}
              onClick={() => handleFileSwitch(f.key)}
            >
              <CardContent className="p-3">
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium text-white truncate">
                    {LOG_FILE_LABELS[f.key] || f.filename}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    {f.exists ? formatFileSize(f.size_bytes) : 'Не найден'}
                  </span>
                  {selectedFile === f.key && (
                    <Badge className="bg-primary-400/20 text-primary-400 text-xs">
                      Active
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Filters */}
      <Card className="bg-dark-800 border-dark-700">
        <CardContent className="p-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по содержимому лога..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="pl-9 bg-dark-900 border-dark-600 font-mono text-sm"
              />
            </div>
            <Select value={levelFilter} onValueChange={(v) => { setLevelFilter(v); setStreamLines([]) }}>
              <SelectTrigger className="w-[140px] bg-dark-900 border-dark-600">
                <SelectValue placeholder="Уровень" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все уровни</SelectItem>
                <SelectItem value="INFO">INFO</SelectItem>
                <SelectItem value="WARNING">WARNING</SelectItem>
                <SelectItem value="ERROR">ERROR</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={handleSearch}
              className="border-dark-600"
            >
              <Search className="w-4 h-4 mr-2" />
              Найти
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Log viewer */}
      <Card className="bg-dark-900 border-dark-700">
        <CardContent className="p-0">
          <div className="flex items-center justify-between px-4 py-2 border-b border-dark-700 bg-dark-800">
            <span className="text-xs text-muted-foreground font-mono">
              {LOG_FILE_LABELS[selectedFile] || selectedFile}
            </span>
            <span className="text-xs text-muted-foreground">
              {allLines.length} строк
              {isStreaming && (
                <span className="ml-2 inline-flex items-center">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-1" />
                  Live
                </span>
              )}
            </span>
          </div>
          <div
            ref={logContainerRef}
            className="h-[calc(100vh-420px)] min-h-[400px] overflow-auto font-mono text-xs leading-5 p-2"
          >
            {allLines.length === 0 ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <div className="text-center">
                  <Terminal className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>{isStreaming ? 'Ожидание новых записей...' : 'Нет записей'}</p>
                </div>
              </div>
            ) : (
              allLines.map((entry, idx) => {
                const levelColor = entry.level ? LEVEL_COLORS[entry.level] : 'text-gray-500'
                const isError = entry.level === 'ERROR' || entry.level === 'CRITICAL'

                return (
                  <div
                    key={idx}
                    className={cn(
                      'flex items-start gap-2 px-2 py-0.5 rounded hover:bg-dark-800/50',
                      isError && 'bg-red-500/5',
                    )}
                  >
                    {entry.timestamp && (
                      <span className="text-dark-400 whitespace-nowrap shrink-0 select-none">
                        {entry.timestamp.split(' ')[1] || entry.timestamp}
                      </span>
                    )}
                    {entry.level && (
                      <span className={cn('w-[60px] shrink-0 text-right', levelColor)}>
                        {entry.level}
                      </span>
                    )}
                    {entry.source && (
                      <span className="text-cyan-400/70 w-[80px] shrink-0 truncate">
                        {entry.source}
                      </span>
                    )}
                    <span className={cn('text-dark-100 break-all', isError && 'text-red-300')}>
                      {entry.message}
                    </span>
                  </div>
                )
              })
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
