import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/lib/useTabParam'
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
import { QueryError } from '@/components/QueryError'
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

const LEVEL_BADGE_COLORS: Record<string, string> = {
  DEBUG: 'bg-gray-500/20 text-gray-400',
  INFO: 'bg-blue-500/20 text-blue-400',
  WARNING: 'bg-yellow-500/20 text-yellow-400',
  ERROR: 'bg-red-500/20 text-red-400',
}

// ── Message highlighting ─────────────────────────────────────────

// Message category detection for left border color
function getMessageCategory(message: string): string {
  if (/^Batch received:/i.test(message)) return 'batch-in'
  if (/^Batch upserted:/i.test(message)) return 'batch-out'
  if (/^User\s+[0-9a-f-]+:/i.test(message)) return 'user-check'
  if (/^(GET|POST|PUT|DELETE|PATCH)\s/i.test(message)) return 'http'
  if (/violation|alert|block/i.test(message)) return 'violation'
  return ''
}

const CATEGORY_BORDER: Record<string, string> = {
  'batch-in': 'border-l-2 border-l-emerald-500/40',
  'batch-out': 'border-l-2 border-l-sky-500/30',
  'user-check': 'border-l-2 border-l-amber-500/40',
  'http': 'border-l-2 border-l-violet-500/40',
  'violation': 'border-l-2 border-l-red-500/50',
}

function highlightMessage(message: string): React.ReactNode {
  if (!message) return message

  // First pass: find all key=value pairs and special patterns
  const tokens: { start: number; end: number; type: string; match: string; groups?: string[] }[] = []

  // key=value (numbers)
  const kvNumRe = /\b(\w+)=([\d.]+)\b/g
  let m: RegExpExecArray | null
  while ((m = kvNumRe.exec(message)) !== null) {
    tokens.push({ start: m.index, end: m.index + m[0].length, type: 'kv_num', match: m[0], groups: [m[1], m[2]] })
  }

  // UUIDs
  const uuidRe = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi
  while ((m = uuidRe.exec(message)) !== null) {
    tokens.push({ start: m.index, end: m.index + m[0].length, type: 'uuid', match: m[0] })
  }

  // HTTP status arrows
  const statusRe = /→\s*(\d{3})/g
  while ((m = statusRe.exec(message)) !== null) {
    tokens.push({ start: m.index, end: m.index + m[0].length, type: 'status', match: m[0], groups: [m[1]] })
  }

  // Parenthesized notes
  const noteRe = /\([^)]+\)/g
  while ((m = noteRe.exec(message)) !== null) {
    tokens.push({ start: m.index, end: m.index + m[0].length, type: 'note', match: m[0] })
  }

  // node= keyword (special — highlight node name)
  const nodeRe = /\bnode=(\S+)/g
  while ((m = nodeRe.exec(message)) !== null) {
    tokens.push({ start: m.index, end: m.index + m[0].length, type: 'node', match: m[0], groups: [m[1]] })
  }

  // Sort by start position, remove overlaps
  tokens.sort((a, b) => a.start - b.start)
  const filtered: typeof tokens = []
  let lastEnd = 0
  for (const t of tokens) {
    if (t.start >= lastEnd) {
      filtered.push(t)
      lastEnd = t.end
    }
  }

  // Build React nodes
  const result: React.ReactNode[] = []
  let pos = 0
  for (const token of filtered) {
    // Text before this token
    if (token.start > pos) {
      result.push(<span key={`t${pos}`}>{message.slice(pos, token.start)}</span>)
    }

    switch (token.type) {
      case 'node':
        result.push(
          <span key={`n${token.start}`}>
            <span className="text-dark-300">node=</span>
            <span className="text-emerald-400 font-medium">{token.groups![0]}</span>
          </span>
        )
        break
      case 'kv_num':
        result.push(
          <span key={`kv${token.start}`}>
            <span className="text-dark-300">{token.groups![0]}=</span>
            <span className="text-amber-300">{token.groups![1]}</span>
          </span>
        )
        break
      case 'uuid':
        result.push(
          <span key={`u${token.start}`} className="text-dark-400" title={token.match}>
            {token.match.slice(0, 8)}…
          </span>
        )
        break
      case 'status': {
        const code = token.groups?.[0] || ''
        const codeNum = parseInt(code)
        const statusColor = codeNum >= 500 ? 'text-red-400' : codeNum >= 400 ? 'text-yellow-400' : 'text-green-400'
        result.push(
          <span key={`s${token.start}`}>
            <span className="text-dark-300">→ </span>
            <span className={cn('font-medium', statusColor)}>{code}</span>
          </span>
        )
        break
      }
      case 'note':
        result.push(
          <span key={`p${token.start}`} className="text-dark-400 italic">{token.match}</span>
        )
        break
      default:
        result.push(<span key={`d${token.start}`}>{token.match}</span>)
    }
    pos = token.end
  }

  // Remaining text
  if (pos < message.length) {
    result.push(<span key={`e${pos}`}>{message.slice(pos)}</span>)
  }

  return <>{result}</>
}

// ── Component ───────────────────────────────────────────────────

export default function SystemLogs() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useTabParam<LogTab>('backend', ['backend', 'bot', 'frontend', 'violations', 'postgres'])
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
  const { data: initialData, isError, refetch } = useQuery({
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
    if (!isStreaming) return

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

    const wsUrl = `${base}/logs/stream?file=${activeTab}`
    // JWT через subprotocol (если есть в памяти) — не попадает в access-логи;
    // иначе аутентификация по HttpOnly cookie
    const ws = accessToken
      ? new WebSocket(wsUrl, ['access-token', accessToken])
      : new WebSocket(wsUrl)
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
    <div className="p-3 sm:p-4 md:p-6 space-y-3 sm:space-y-4 animate-fade-in overflow-x-hidden max-w-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-2xl font-bold text-white flex items-center gap-2">
            <Terminal className="w-5 h-5 sm:w-6 sm:h-6 text-primary-400 shrink-0" />
            {t('logs.title')}
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 sm:mt-1 hidden sm:block">
            {t('logs.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={isStreaming ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  setIsStreaming(!isStreaming)
                  if (!isStreaming) refetch()
                }}
                className={cn(
                  'h-8 px-2 sm:px-3',
                  isStreaming ? 'bg-emerald-600 hover:bg-emerald-700' : 'border-[var(--glass-border)]',
                )}
              >
                {isStreaming ? (
                  <>
                    <Pause className="w-4 h-4 sm:mr-1" />
                    <span className="hidden sm:inline">Live</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 sm:mr-1" />
                    <span className="hidden sm:inline">Paused</span>
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
                className={cn('border-[var(--glass-border)] h-8 w-8 p-0', autoScroll && 'bg-[var(--glass-bg)]')}
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
            className="border-[var(--glass-border)] h-8 px-2 sm:px-3"
          >
            <Trash2 className="w-4 h-4 sm:mr-1" />
            <span className="hidden sm:inline">{t('logs.clear')}</span>
          </Button>
        </div>
      </div>

      {isError && <QueryError onRetry={refetch} />}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <div className="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0 no-scrollbar">
          <TabsList className="bg-[var(--glass-bg)] border border-[var(--glass-border)] w-max sm:w-auto">
            {(Object.entries(TAB_CONFIG) as [LogTab, typeof TAB_CONFIG[LogTab]][]).map(([key, cfg]) => {
              const Icon = cfg.icon
              const fileInfo = logFiles?.find((f: LogFile) => f.key === key)
              return (
                <TabsTrigger
                  key={key}
                  value={key}
                  className="gap-1 sm:gap-1.5 px-2 sm:px-3 data-[state=active]:bg-[var(--glass-bg)]"
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-xs sm:text-sm whitespace-nowrap">{t(cfg.labelKey)}</span>
                  {fileInfo && fileInfo.exists && (
                    <span className="text-[10px] text-muted-foreground ml-0.5 sm:ml-1 hidden sm:inline">
                      {formatFileSize(fileInfo.size_bytes)}
                    </span>
                  )}
                </TabsTrigger>
              )
            })}
          </TabsList>
        </div>

        {/* Shared content for all tabs */}
        {(Object.keys(TAB_CONFIG) as LogTab[]).map((tab) => (
          <TabsContent key={tab} value={tab} className="mt-4 space-y-3">
            {/* Filters toolbar */}
            <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
              <CardContent className="p-2 sm:p-3">
                <div className="flex flex-col gap-2 sm:gap-3">
                  {/* Row 1: Search input + level filter */}
                  <div className="flex gap-2">
                    <div className="relative flex-1 min-w-0">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input
                        placeholder={t('logs.searchPlaceholder')}
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        className="pl-9 bg-[var(--glass-bg)] border-[var(--glass-border)] font-mono text-xs sm:text-sm h-9"
                      />
                    </div>
                    <Select value={levelFilter} onValueChange={(v) => { setLevelFilter(v); setStreamLines([]) }}>
                      <SelectTrigger className="w-[110px] sm:w-[140px] bg-[var(--glass-bg)] border-[var(--glass-border)] shrink-0 h-9">
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
                  </div>

                  {/* Row 2: Search button + log level control */}
                  <div className="flex items-center gap-2 sm:gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSearch}
                      className="border-[var(--glass-border)] h-8"
                    >
                      <Search className="w-4 h-4 mr-1.5" />
                      {t('common.search')}
                    </Button>

                    {/* Dynamic log level control */}
                    {canChangeLevel && currentLevel && (
                      <div className="flex items-center gap-1.5 sm:gap-2 border-l border-[var(--glass-border)] pl-2 sm:pl-3 ml-auto">
                        <Settings2 className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-muted-foreground shrink-0" />
                        <span className="text-[10px] sm:text-xs text-muted-foreground whitespace-nowrap">
                          {t('logs.logLevel')}:
                        </span>
                        <Select
                          value={currentLevel}
                          onValueChange={(v) => handleLevelChange(activeTab, v)}
                        >
                          <SelectTrigger className="w-[90px] sm:w-[110px] h-7 sm:h-8 bg-[var(--glass-bg)] border-[var(--glass-border)] text-xs">
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
                </div>
              </CardContent>
            </Card>

            {/* Log viewer */}
            <Card className="bg-[var(--glass-bg)] border-[var(--glass-border)]">
              <CardContent className="p-0">
                <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--glass-border)] bg-[var(--glass-bg)]">
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
                  className="h-[calc(100vh-480px)] min-h-[250px] md:h-[calc(100vh-420px)] md:min-h-[400px] overflow-y-auto overflow-x-hidden font-mono text-xs leading-5 p-1.5 sm:p-2"
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
                      const badgeColor = entry.level ? (LEVEL_BADGE_COLORS[entry.level] || 'bg-gray-500/20 text-gray-400') : ''
                      const isError = entry.level === 'ERROR' || entry.level === 'CRITICAL'
                      const isWarning = entry.level === 'WARNING'
                      const hasExtra = entry.extra && Object.keys(entry.extra).length > 0
                      const isExpanded = expandedRows.has(idx)
                      const category = getMessageCategory(entry.message || '')
                      const categoryBorder = CATEGORY_BORDER[category] || 'border-l-2 border-l-transparent'
                      const isEven = idx % 2 === 0

                      // Time-based separator: show thin line when second changes
                      const prevEntry = idx > 0 ? allLines[idx - 1] : null
                      const showSeparator = prevEntry?.timestamp && entry.timestamp
                        && entry.timestamp.slice(0, 19) !== prevEntry.timestamp.slice(0, 19)
                        && (idx % 5 === 0) // don't show too many separators

                      // On mobile, show only time (HH:MM:SS) from timestamp
                      const displayTimestamp = entry.timestamp
                        ? entry.timestamp.replace(/^\d{4}-\d{2}-\d{2}\s+/, '')
                        : null
                      const fullTimestamp = entry.timestamp

                      return (
                        <div key={idx}>
                          {/* Time separator */}
                          {showSeparator && (
                            <div className="border-t border-[var(--glass-border)]/30 my-0.5" />
                          )}

                          {/* Desktop layout: single row */}
                          <div
                            className={cn(
                              'hidden sm:flex items-start gap-2 px-2 py-[3px] rounded transition-colors',
                              categoryBorder,
                              isError ? 'bg-red-500/5' : isWarning ? 'bg-yellow-500/5' : isEven ? 'bg-transparent' : 'bg-white/[0.015]',
                              'hover:bg-[var(--glass-bg)]',
                              hasExtra && 'cursor-pointer',
                            )}
                            onClick={hasExtra ? () => toggleExpandRow(idx) : undefined}
                          >
                            {/* Expand indicator */}
                            {hasExtra ? (
                              <span className={cn('shrink-0 w-3 mt-0.5', isExpanded ? 'text-primary-400' : 'text-dark-500')}>
                                {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                              </span>
                            ) : (
                              <span className="w-3 shrink-0" />
                            )}
                            {entry.timestamp && (
                              <span className="text-dark-500 whitespace-nowrap shrink-0 select-none text-[11px]">
                                {fullTimestamp}
                              </span>
                            )}
                            {entry.level && (
                              <span className={cn(
                                'shrink-0 rounded px-1.5 py-0 text-[11px] font-medium leading-5 text-center w-[60px]',
                                badgeColor,
                              )}>
                                {entry.level}
                              </span>
                            )}
                            {entry.source && (
                              <span className="text-primary-400/60 w-[80px] shrink-0 truncate text-[11px]">
                                {entry.source}
                              </span>
                            )}
                            <span className={cn(
                              'whitespace-pre-wrap break-words min-w-0',
                              isError ? 'text-red-300' : isWarning ? 'text-yellow-200' : 'text-dark-100',
                            )}>
                              {isError || isWarning ? entry.message : highlightMessage(entry.message || '')}
                            </span>
                          </div>

                          {/* Mobile layout: stacked — meta row + message row */}
                          <div
                            className={cn(
                              'sm:hidden px-1.5 py-1 rounded transition-colors',
                              categoryBorder,
                              isError ? 'bg-red-500/5' : isWarning ? 'bg-yellow-500/5' : isEven ? 'bg-transparent' : 'bg-white/[0.015]',
                              'hover:bg-[var(--glass-bg)]',
                              hasExtra && 'cursor-pointer',
                            )}
                            onClick={hasExtra ? () => toggleExpandRow(idx) : undefined}
                          >
                            {/* Meta line: chevron + time + level + source */}
                            <div className="flex items-center gap-1.5 mb-0.5">
                              {hasExtra ? (
                                <span className={cn('shrink-0 w-3', isExpanded ? 'text-primary-400' : 'text-dark-500')}>
                                  {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                </span>
                              ) : (
                                <span className="w-3 shrink-0" />
                              )}
                              {displayTimestamp && (
                                <span className="text-dark-500 text-[10px] select-none shrink-0">
                                  {displayTimestamp}
                                </span>
                              )}
                              {entry.level && (
                                <span className={cn(
                                  'shrink-0 rounded px-1 py-0 text-[10px] font-medium leading-4 text-center',
                                  badgeColor,
                                )}>
                                  {entry.level}
                                </span>
                              )}
                              {entry.source && (
                                <span className="text-primary-400/60 text-[10px] truncate">
                                  {entry.source}
                                </span>
                              )}
                            </div>
                            {/* Message: full width */}
                            <div className={cn(
                              'text-[11px] leading-4 whitespace-pre-wrap break-words pl-[18px]',
                              isError ? 'text-red-300' : isWarning ? 'text-yellow-200' : 'text-dark-100',
                            )}>
                              {isError || isWarning ? entry.message : highlightMessage(entry.message || '')}
                            </div>
                          </div>

                          {/* Expanded extra fields */}
                          {hasExtra && isExpanded && (
                            <div className="ml-5 sm:ml-8 pl-2 sm:pl-4 py-1 border-l-2 border-[var(--glass-border)] mb-1 space-y-0.5">
                              {Object.entries(entry.extra!).map(([key, value]) => (
                                <div key={key} className="flex gap-1.5 sm:gap-2 text-[10px] sm:text-[11px]">
                                  <span className="text-purple-400 shrink-0 font-medium">{key}:</span>
                                  <span className="text-dark-300 break-words min-w-0">
                                    {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
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
