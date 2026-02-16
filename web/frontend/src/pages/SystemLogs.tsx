import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Search,
  Pause,
  Play,
  ArrowDown,
  Trash2,
  Terminal,
  Database,
  Bot,
  ShieldAlert,
  Globe,
  ChevronDown,
  ChevronRight,
  Settings2,
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { logsApi, type LogEntry, type LogFile } from '@/api/logs'
import { useAuthStore } from '@/store/authStore'

// ── Tab configuration ───────────────────────────────────────────

type LogTab = 'backend' | 'bot' | 'frontend' | 'violations' | 'postgres'

const TAB_CONFIG: Record<LogTab, { icon: typeof Terminal; labelKey: string }> = {
  backend: { icon: Terminal, labelKey: 'logs.tabs.backend' },
  bot: { icon: Bot, labelKey: 'logs.tabs.bot' },
  frontend: { icon: Globe, labelKey: 'logs.tabs.frontend' },
  violations: { icon: ShieldAlert, labelKey: 'logs.tabs.violations' },
  postgres: { icon: Database, labelKey: 'logs.tabs.postgres' },
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-500 font-bold',
}

const LEVEL_BADGE_COLORS: Record<string, string> = {
  DEBUG: 'bg-gray-500/20 text-gray-400',
  INFO: 'bg-blue-500/20 text-blue-400',
  WARNING: 'bg-yellow-500/20 text-yellow-400',
  ERROR: 'bg-red-500/20 text-red-400',
}

// ── Component ───────────────────────────────────────────────────

export default function SystemLogs() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<LogTab>('backend')
  const [levelFilter, setLevelFilter] = useState<string>('all')
  const [searchText, setSearchText] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(true)
  const [streamLines, setStreamLines] = useState<LogEntry[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())
  const logContainerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const accessToken = useAuthStore((s) => s.accessToken)

  // Log levels state
  const { data: logLevels, refetch: refetchLevels } = useQuery({
    queryKey: ['log-levels'],
    queryFn: () => logsApi.getLogLevel(),
    staleTime: 30000,
  })

  // Fetch initial log lines
  const { data: initialData, refetch } = useQuery({
    queryKey: ['logs-tail', activeTab, levelFilter, searchText],
    queryFn: () =>
      logsApi.tail({
        file: activeTab,
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
      window.__ENV?.API_URL ||
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

    const wsUrl = `${base}/logs/stream?token=${encodeURIComponent(accessToken)}&file=${activeTab}`
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
          if (searchText) {
            const q = searchText.toLowerCase()
            const inMessage = (entry.message || '').toLowerCase().includes(q)
            const inSource = (entry.source || '').toLowerCase().includes(q)
            const inLevel = (entry.level || '').toLowerCase().includes(q)
            if (!inMessage && !inSource && !inLevel) return
          }

          setStreamLines((prev) => {
            const next = [...prev, entry]
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
  }, [isStreaming, activeTab, accessToken, levelFilter, searchText])

  const handleTabChange = useCallback((tab: string) => {
    setActiveTab(tab as LogTab)
    setStreamLines([])
    setExpandedRows(new Set())
  }, [])

  const handleSearch = () => {
    setSearchText(searchInput)
    setStreamLines([])
  }

  const handleClear = () => {
    setStreamLines([])
    queryClient.setQueryData(['logs-tail', activeTab, levelFilter, searchText], (old: unknown) =>
      old ? { ...(old as Record<string, unknown>), items: [] } : old,
    )
  }

  const handleLevelChange = async (component: string, newLevel: string) => {
    try {
      await logsApi.setLogLevel(component, newLevel)
      refetchLevels()
    } catch {
      // Silent fail
    }
  }

  const toggleExpandRow = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) {
        next.delete(idx)
      } else {
        next.add(idx)
      }
      return next
    })
  }

  // Combine initial data with streamed lines
  const allLines = isStreaming
    ? [...(initialData?.items ?? []), ...streamLines]
    : (initialData?.items ?? [])

  // Get file info for active tab
  const activeFileInfo = logFiles?.find((f: LogFile) => f.key === activeTab)

  // Can change log level for backend and bot only
  const canChangeLevel = activeTab === 'backend' || activeTab === 'bot'
  const currentLevel = activeTab === 'backend' ? logLevels?.backend : activeTab === 'bot' ? logLevels?.bot : null

  return (
    <div className="p-4 md:p-6 space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Terminal className="w-6 h-6 text-primary-400" />
            {t('logs.title')}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t('logs.subtitle')}
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
              {isStreaming ? t('logs.pauseStreaming') : t('logs.resumeStreaming')}
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
              {autoScroll ? t('logs.autoScrollOn') : t('logs.autoScrollOff')}
            </TooltipContent>
          </Tooltip>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            className="border-dark-600"
          >
            <Trash2 className="w-4 h-4 mr-1" />
            {t('logs.clear')}
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="bg-dark-800 border border-dark-700">
          {(Object.entries(TAB_CONFIG) as [LogTab, typeof TAB_CONFIG[LogTab]][]).map(([key, cfg]) => {
            const Icon = cfg.icon
            const fileInfo = logFiles?.find((f: LogFile) => f.key === key)
            return (
              <TabsTrigger
                key={key}
                value={key}
                className="gap-1.5 data-[state=active]:bg-dark-700"
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t(cfg.labelKey)}</span>
                {fileInfo && fileInfo.exists && key !== 'frontend' && (
                  <span className="text-[10px] text-muted-foreground ml-1">
                    {formatFileSize(fileInfo.size_bytes)}
                  </span>
                )}
                {key === 'frontend' && fileInfo && (
                  <span className="text-[10px] text-muted-foreground ml-1">
                    {fileInfo.size_bytes}
                  </span>
                )}
              </TabsTrigger>
            )
          })}
        </TabsList>

        {/* Shared content for all tabs */}
        {(Object.keys(TAB_CONFIG) as LogTab[]).map((tab) => (
          <TabsContent key={tab} value={tab} className="mt-4 space-y-3">
            {/* Filters toolbar */}
            <Card className="bg-dark-800 border-dark-700">
              <CardContent className="p-3">
                <div className="flex flex-col sm:flex-row gap-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder={t('logs.searchPlaceholder')}
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      className="pl-9 bg-dark-900 border-dark-600 font-mono text-sm"
                    />
                  </div>
                  <Select value={levelFilter} onValueChange={(v) => { setLevelFilter(v); setStreamLines([]) }}>
                    <SelectTrigger className="w-[140px] bg-dark-900 border-dark-600">
                      <SelectValue placeholder={t('logs.level')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('logs.allLevels')}</SelectItem>
                      <SelectItem value="DEBUG">DEBUG</SelectItem>
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
                    {t('common.search')}
                  </Button>

                  {/* Dynamic log level control */}
                  {canChangeLevel && currentLevel && (
                    <div className="flex items-center gap-2 border-l border-dark-600 pl-3">
                      <Settings2 className="w-4 h-4 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {t('logs.logLevel')}:
                      </span>
                      <Select
                        value={currentLevel}
                        onValueChange={(v) => handleLevelChange(activeTab, v)}
                      >
                        <SelectTrigger className="w-[110px] h-8 bg-dark-900 border-dark-600 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="DEBUG">
                            <Badge className={cn('text-xs', LEVEL_BADGE_COLORS.DEBUG)}>DEBUG</Badge>
                          </SelectItem>
                          <SelectItem value="INFO">
                            <Badge className={cn('text-xs', LEVEL_BADGE_COLORS.INFO)}>INFO</Badge>
                          </SelectItem>
                          <SelectItem value="WARNING">
                            <Badge className={cn('text-xs', LEVEL_BADGE_COLORS.WARNING)}>WARNING</Badge>
                          </SelectItem>
                          <SelectItem value="ERROR">
                            <Badge className={cn('text-xs', LEVEL_BADGE_COLORS.ERROR)}>ERROR</Badge>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Log viewer */}
            <Card className="bg-dark-900 border-dark-700">
              <CardContent className="p-0">
                <div className="flex items-center justify-between px-4 py-2 border-b border-dark-700 bg-dark-800">
                  <span className="text-xs text-muted-foreground font-mono">
                    {t(TAB_CONFIG[activeTab].labelKey)}
                    {activeFileInfo?.filename && (
                      <span className="ml-2 opacity-50">({activeFileInfo.filename})</span>
                    )}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t('logs.linesCount', { count: allLines.length })}
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
                        <p>{isStreaming ? t('logs.waitingForEntries') : t('logs.noEntries')}</p>
                      </div>
                    </div>
                  ) : (
                    allLines.map((entry, idx) => {
                      const levelColor = entry.level ? LEVEL_COLORS[entry.level] : 'text-gray-500'
                      const isError = entry.level === 'ERROR' || entry.level === 'CRITICAL'
                      const hasExtra = entry.extra && Object.keys(entry.extra).length > 0
                      const isExpanded = expandedRows.has(idx)

                      return (
                        <div key={idx}>
                          <div
                            className={cn(
                              'flex items-start gap-2 px-2 py-0.5 rounded hover:bg-dark-800/50',
                              isError && 'bg-red-500/5',
                              hasExtra && 'cursor-pointer',
                            )}
                            onClick={hasExtra ? () => toggleExpandRow(idx) : undefined}
                          >
                            {/* Expand indicator for rows with extra data */}
                            {hasExtra ? (
                              <span className="text-dark-500 shrink-0 w-3 mt-0.5">
                                {isExpanded ? (
                                  <ChevronDown className="w-3 h-3" />
                                ) : (
                                  <ChevronRight className="w-3 h-3" />
                                )}
                              </span>
                            ) : (
                              <span className="w-3 shrink-0" />
                            )}

                            {entry.timestamp && (
                              <span className="text-dark-400 whitespace-nowrap shrink-0 select-none">
                                {entry.timestamp}
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
                          {/* Expanded extra fields */}
                          {hasExtra && isExpanded && (
                            <div className="ml-8 pl-4 py-1 border-l border-dark-700 mb-1">
                              {Object.entries(entry.extra!).map(([key, value]) => (
                                <div key={key} className="flex gap-2 text-[11px]">
                                  <span className="text-purple-400 shrink-0">{key}:</span>
                                  <span className="text-dark-300 break-all">
                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 B'
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}
