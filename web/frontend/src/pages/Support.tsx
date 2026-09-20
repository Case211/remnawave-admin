import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Archive,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Clock,
  Loader2,
  RefreshCw,
  Search,
  Send,
  Upload,
  Users,
  X,
} from '@/components/brand/icons'
import {
  supportApi,
  supportExtraApi,
  type SupportMacro,
  type SupportTag,
  type SupportWatcher,
} from '../api/support'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/EmptyState'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'
import client from '@/api/client'

const QUEUES = ['wait_us', 'mine', 'late', 'wait_client', 'snoozed', 'all'] as const

/** Приоритет виден полоской: срочное должно выделяться до чтения текста. */
const PRIORITY_BAR: Record<string, string> = {
  urgent: 'bg-red-400',
  high: 'bg-orange-400',
  normal: 'bg-white/10',
  low: 'bg-white/5',
}
type QueueId = (typeof QUEUES)[number]

/** Время ожидания словами: оператору важны минуты, а не дата создания. */
function waitedFor(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const minutes = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч ${minutes % 60} мин`
  return `${Math.floor(hours / 24)} дн`
}

function waitTone(iso: string | null, slaMinutes: number, slaOn = true, now = Date.now()): string {
  if (!iso) return 'text-dark-300'
  if (!slaOn) return 'text-dark-300'
  const minutes = (now - new Date(iso).getTime()) / 60000
  if (minutes >= slaMinutes) return 'text-red-400 font-bold'
  if (minutes >= slaMinutes / 2) return 'text-amber-400'
  return 'text-dark-300'
}

function timeOfDay(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Support() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canReply = useHasPermission('bedolaga_support', 'create')
  const canEdit = useHasPermission('bedolaga_support', 'edit')

  const [queue, setQueue] = useState<QueueId>('wait_us')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // На узком экране колонки не помещаются рядом: показываем либо очередь,
  // либо переписку. Флаг переключает панели, на десктопе он ни на что не влияет.
  const [mobileChatOpen, setMobileChatOpen] = useState(false)
  const [draft, setDraft] = useState('')
  // Шаблон, вставленный в черновик: его побочные действия уйдут вместе с ответом.
  const [pendingMacro, setPendingMacro] = useState<SupportMacro | null>(null)
  const draftRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const feedEndRef = useRef<HTMLDivElement>(null)
  // Ссылки на скачанные вложения: один blob на сообщение, чтобы не тянуть
  // файл заново при каждом ререндере.
  const [mediaUrls, setMediaUrls] = useState<Record<string, string>>({})
  const [viewer, setViewer] = useState<{ key: string; list: string[]; at: number } | null>(null)
  // Время ожидания должно идти само, а не замирать до следующей загрузки списка.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])

  const { data: queues } = useQuery({
    queryKey: ['support-queues'],
    queryFn: supportApi.getQueues,
    refetchInterval: 30_000,
  })
  const slaMinutes = queues?.sla_minutes ?? 30
  // Контроль срока выключен — ни очереди «просрочены», ни цветного таймера:
  // подсвечивать нечего, а красное время без SLA только пугает.
  const slaOn = queues?.sla_enabled !== false
  const visibleQueues = slaOn ? QUEUES : QUEUES.filter((id) => id !== 'late')

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data: macrosData } = useQuery({
    queryKey: ['support-macros'],
    queryFn: supportExtraApi.listMacros,
    staleTime: 300_000,
  })
  const macros = macrosData?.items ?? []

  const { data: tagsData } = useQuery({
    queryKey: ['support-tags'],
    queryFn: supportExtraApi.listTags,
    staleTime: 300_000,
  })
  const allTags = tagsData?.items ?? []

  const { data: metrics } = useQuery({
    queryKey: ['support-metrics'],
    queryFn: () => supportExtraApi.metrics(7),
    staleTime: 120_000,
  })

  const { data: list, isLoading: listLoading } = useQuery({
    queryKey: ['support-tickets', queue, search],
    queryFn: () => supportApi.listTickets({ queue, search: search || undefined, limit: 100 }),
    refetchInterval: 30_000,
  })

  const tickets = useMemo(() => list?.items ?? [], [list])

  // Очередь может вырасти до сотен обращений: рисуем только видимые строки.
  const listRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: tickets.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 92,
    overscan: 8,
  })
  const activeId = selectedId ?? tickets[0]?.id ?? null

  const { data: detail, isFetching: detailLoading } = useQuery({
    queryKey: ['support-ticket', activeId],
    queryFn: () => supportApi.getTicket(activeId as number),
    enabled: activeId != null,
    refetchInterval: 20_000,
  })

  // Открыли тикет — он прочитан; иначе счётчик непрочитанных живёт вечно.
  useEffect(() => {
    if (activeId == null || !detail?.messages?.length) return
    const lastId = detail.messages[detail.messages.length - 1].id
    supportApi.markRead(activeId, lastId).then(() => {
      queryClient.invalidateQueries({ queryKey: ['support-tickets'] })
    })
  }, [activeId, detail?.messages, queryClient])

  const detailUserId = detail?.ticket?.bot_user_id ?? null

  // Кто пишет: подписка, баланс, ссылка в профиль. Оператору незачем уходить
  // в другой раздел, чтобы понять, с кем он разговаривает.
  const { data: customer } = useQuery({
    queryKey: ['support-customer', detailUserId],
    queryFn: () => client.get(`/bedolaga/customers/${detailUserId}`).then((r) => r.data),
    enabled: detailUserId != null,
    staleTime: 60_000,
    retry: false,
  })

  // Пока тикет открыт, отмечаемся каждые 20 секунд: коллега увидит, что им
  // уже занимаются, и не ответит вторым.
  const [watchers, setWatchers] = useState<SupportWatcher[]>([])
  useEffect(() => {
    if (activeId == null) {
      setWatchers([])
      return
    }
    let alive = true
    const ping = () => {
      supportApi
        .presence(activeId)
        .then((r) => alive && setWatchers(r.watchers))
        .catch(() => undefined)
    }
    ping()
    const timer = setInterval(ping, 20_000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [activeId])

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['support-queues'] })
    queryClient.invalidateQueries({ queryKey: ['support-tickets'] })
    queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] })
  }

  const replyMutation = useMutation({
    mutationFn: ({ text, close }: { text: string; close: boolean }) =>
      supportApi.reply(activeId as number, text, close, {
        set_status: pendingMacro?.set_status ?? null,
        add_tag_id: pendingMacro?.add_tag_id ?? null,
      }),
    onSuccess: (_, variables) => {
      setDraft('')
      setPendingMacro(null)
      invalidateAll()
      toast.success(variables.close ? t('support.repliedAndClosed') : t('support.replied'))
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail?.message || t('support.replyFailed')),
  })

  const assignMutation = useMutation({
    mutationFn: () => supportApi.assign(activeId as number),
    onSuccess: () => {
      invalidateAll()
      toast.success(t('support.assigned'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const unassignMutation = useMutation({
    mutationFn: () => supportApi.unassign(activeId as number),
    onSuccess: () => {
      invalidateAll()
      toast.success(t('support.unassigned'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const statusMutation = useMutation({
    mutationFn: (status: string) => supportApi.setStatus(activeId as number, status),
    onSuccess: () => {
      invalidateAll()
      toast.success(t('common.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const attachMutation = useMutation({
    mutationFn: (file: File) => supportApi.attach(activeId as number, file, draft.trim()),
    onSuccess: () => {
      setDraft('')
      invalidateAll()
      toast.success(t('support.attached'))
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail?.message || t('support.attachFailed')),
  })

  const snoozeMutation = useMutation({
    mutationFn: (minutes: number) => supportExtraApi.snooze(activeId as number, minutes),
    onSuccess: () => {
      invalidateAll()
      toast.success(t('support.snoozed'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const tagMutation = useMutation({
    mutationFn: (tagId: number) => supportExtraApi.attachTag(activeId as number, tagId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] })
    },
    onError: () => toast.error(t('common.error')),
  })

  const syncMutation = useMutation({
    mutationFn: () => supportApi.sync(false),
    onSuccess: (r) => {
      invalidateAll()
      toast.success(t('support.synced', { updated: r.updated }))
    },
    onError: () => toast.error(t('support.syncFailed')),
  })

  const send = (close: boolean) => {
    const text = draft.trim()
    if (!text || activeId == null) return
    replyMutation.mutate({ text, close })
  }

  /** Подстановки шаблона берём из карточки — руками их набирать бессмысленно. */
  const applyMacro = (macro: SupportMacro) => {
    const filled = macro.body
      .replace(/\{\{\s*name\s*\}\}/g, ticket?.customer_name || t('support.client'))
      .replace(/\{\{\s*ticket\s*\}\}/g, String(ticket?.id ?? ''))
    setDraft(filled)
    setPendingMacro(macro)
    draftRef.current?.focus()
  }

  const macroSuggestions = draft.startsWith('/')
    ? macros.filter((m) => {
        const query = draft.slice(1).toLowerCase().trim()
        if (!query) return true
        return m.title.toLowerCase().includes(query) || (m.shortcut || '').toLowerCase().includes(query)
      })
    : []

  const onDraftKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      send(e.shiftKey)
    }
  }

  // Вложения открытого тикета тянем один раз и держим как object-url.
  useEffect(() => {
    const withMedia = (detail?.messages ?? []).filter((m) => m.has_media)
    if (activeId == null || withMedia.length === 0) return

    // Одиночное вложение — один ключ, пачка — по ключу на файл.
    const wanted: Array<{ key: string; id: number; index?: number }> = []
    withMedia.forEach((m) => {
      if (m.media_items?.length) {
        m.media_items.forEach((item) => wanted.push({ key: `${m.id}:${item.index}`, id: m.id, index: item.index }))
      } else {
        wanted.push({ key: String(m.id), id: m.id })
      }
    })

    let alive = true
    const created: string[] = []
    Promise.all(
      wanted
        .filter((item) => !mediaUrls[item.key])
        .map(async (item) => {
          try {
            const url = await supportApi.mediaBlobUrl(activeId, item.id, item.index)
            created.push(url)
            return [item.key, url] as const
          } catch {
            return null
          }
        }),
    ).then((pairs) => {
      const fresh = pairs.filter(Boolean) as Array<readonly [string, string]>
      if (!alive) {
        created.forEach((url) => URL.revokeObjectURL(url))
        return
      }
      if (fresh.length) setMediaUrls((prev) => ({ ...prev, ...Object.fromEntries(fresh) }))
    })

    return () => {
      alive = false
    }
  }, [activeId, detail?.messages, mediaUrls])

  // Сменили тикет — старые ссылки больше не нужны.
  useEffect(() => {
    return () => {
      Object.values(mediaUrls).forEach((url) => URL.revokeObjectURL(url))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  useEffect(() => {
    if (!viewer) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setViewer(null)
      if (e.key === 'ArrowRight') setViewer((v) => (v ? { ...v, at: (v.at + 1) % v.list.length } : v))
      if (e.key === 'ArrowLeft') setViewer((v) => (v ? { ...v, at: (v.at - 1 + v.list.length) % v.list.length } : v))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [viewer])

  // Длинный тред открывается на последнем сообщении: листать вручную вверх
  // от начала переписки — не то, чего ждёт оператор.
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ block: 'end' })
  }, [activeId, detail?.messages?.length])

  // Хоткеи: пока курсор не в поле ввода, клавиатура ведёт по очереди.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')
      if (typing) {
        if (e.key === 'Escape') (target as HTMLElement).blur()
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const index = tickets.findIndex((item) => item.id === activeId)
      if (e.key === 'j' || e.key === 'о') {
        setSelectedId(tickets[Math.min(index + 1, tickets.length - 1)]?.id ?? activeId)
      } else if (e.key === 'k' || e.key === 'л') {
        setSelectedId(tickets[Math.max(index - 1, 0)]?.id ?? activeId)
      } else if (e.key === 'r' || e.key === 'к') {
        e.preventDefault()
        draftRef.current?.focus()
      } else if (e.key === '/' || e.key === '.') {
        e.preventDefault()
        setDraft('/')
        draftRef.current?.focus()
      } else if ((e.key === 'a' || e.key === 'ф') && activeId != null && canEdit) {
        // Закрытие хоткеем не делаем: оно уходит клиенту уведомлением и не
        // отменяется — случайная «c» на странице стоила бы дороже экономии клика.
        assignMutation.mutate()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tickets, activeId, canEdit, assignMutation])

  const ticket = detail?.ticket
  const messages = detail?.messages ?? []
  const ticketTags = (detail as any)?.tags as SupportTag[] | undefined

  return (
    <PermissionGate resource="bedolaga_support" action="view">
      <div className="flex h-[calc(100dvh-5.5rem)] flex-col gap-3 md:h-[calc(100vh-5rem)] md:flex-row">
        {/* Очереди */}
        {/* Телефон: очереди лентой, метрики и синк прячем — там триаж, а не отчёты */}
        <div className={cn('flex gap-2 overflow-x-auto pb-1 md:hidden', mobileChatOpen && 'hidden')}>
          {visibleQueues.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setQueue(id)
                setSelectedId(null)
              }}
              className={cn(
                'flex h-11 flex-shrink-0 items-center gap-1.5 rounded-full border px-4 text-xs font-semibold',
                queue === id
                  ? 'border-cyan-400/30 bg-cyan-400/14 text-cyan-300'
                  : 'border-[var(--glass-border)] text-dark-300',
              )}
            >
              {t(`support.queues.${id}`)}
              <span className="tabular-nums opacity-70">{queues ? (queues as any)[id] : '—'}</span>
            </button>
          ))}
        </div>

        <aside className="hidden w-52 flex-shrink-0 flex-col gap-4 md:flex">
          <div className="space-y-1">
            {visibleQueues.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setQueue(id)
                  setSelectedId(null)
                }}
                className={cn(
                  'flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors',
                  queue === id
                    ? 'bg-cyan-400/12 text-white font-semibold'
                    : 'text-dark-200 hover:bg-[var(--glass-bg)]',
                )}
              >
                <span>{t(`support.queues.${id}`)}</span>
                <span className={cn('text-xs tabular-nums', queue === id ? 'text-cyan-300' : 'text-dark-300')}>
                  {queues ? (queues as any)[id] : '—'}
                </span>
              </button>
            ))}
          </div>

          {metrics && (
            <div className="rounded-lg border border-[var(--glass-border)] p-2.5 text-[11px] text-dark-300 space-y-1">
              <div className="text-[11px] uppercase tracking-wider text-dark-300">
                {t('support.metrics.title', { days: metrics.days })}
              </div>
              <div className="flex justify-between">
                <span>{t('support.metrics.created')}</span>
                <span className="tabular-nums text-dark-100">{metrics.created}</span>
              </div>
              <div className="flex justify-between">
                <span>{t('support.metrics.avgFirstResponse')}</span>
                <span className="tabular-nums text-emerald-400">{metrics.avg_first_response_minutes} {t('support.metrics.min')}</span>
              </div>
              {metrics.sla_enabled && (
                <div className="flex justify-between">
                  <span>{t('support.metrics.breached')}</span>
                  <span className={cn('tabular-nums', metrics.breached ? 'text-red-400' : 'text-dark-100')}>
                    {metrics.breached} ({metrics.breached_percent}%)
                  </span>
                </div>
              )}
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending || !canEdit}
          >
            {syncMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {t('support.sync')}
          </Button>
        </aside>

        {/* Список */}
        <section
          className={cn(
            'flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--glass-border)] md:w-80 md:flex-none',
            mobileChatOpen && 'hidden md:flex',
          )}
        >
          <div className="p-3 border-b border-[var(--glass-border)]">
            <div className="flex items-center gap-2 rounded-lg bg-[var(--glass-bg)] px-2.5 py-1.5">
              <Search className="w-3.5 h-3.5 text-dark-400" />
              <Input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t('support.searchPlaceholder')}
                aria-label={t('support.searchPlaceholder')}
                className="h-6 border-0 bg-transparent p-0 text-xs focus-visible:ring-0"
              />
            </div>
          </div>

          <div ref={listRef} className="flex-1 overflow-y-auto">
            {listLoading ? (
              <div className="p-3 space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : tickets.length === 0 ? (
              search ? (
                <EmptyState
                  icon={Search}
                  title={t('support.emptySearch')}
                  action={
                    <Button variant="outline" size="sm" onClick={() => setSearchInput('')}>
                      {t('support.resetSearch')}
                    </Button>
                  }
                />
              ) : (
                <EmptyState icon={Archive} title={t('support.emptyQueue')} />
              )
            ) : (
              <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
                {rowVirtualizer.getVirtualItems().map((row) => {
                  const item = tickets[row.index]
                  return (
                    <button
                      key={item.id}
                      type="button"
                      ref={rowVirtualizer.measureElement}
                      data-index={row.index}
                      onClick={() => {
                        setSelectedId(item.id)
                        setMobileChatOpen(true)
                      }}
                      className={cn(
                        'absolute left-0 top-0 flex w-full gap-2.5 border-b border-[var(--glass-border)] py-2.5 pr-3 text-left transition-colors',
                        item.id === activeId ? 'bg-cyan-400/8' : 'hover:bg-[var(--glass-bg)]',
                      )}
                      style={{ transform: `translateY(${row.start}px)` }}
                    >
                      {/* Приоритет — полоска слева: цвет читается боковым зрением,
                          не занимая места в и без того плотной карточке. */}
                      <span
                        className={cn(
                          'w-[3px] flex-shrink-0 rounded-r',
                          PRIORITY_BAR[item.priority] || PRIORITY_BAR.normal,
                        )}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          {(item.unread_count ?? 0) > 0 && (
                            <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-cyan-400" />
                          )}
                          <span className="truncate text-xs font-semibold text-white">
                            {item.customer_name || `#${item.bot_user_id}`}
                          </span>
                          <span className="text-[11px] text-dark-300">#{item.id}</span>
                          <span
                            className={cn(
                              'ml-auto flex-shrink-0 text-[11px] tabular-nums',
                              waitTone(item.waiting_since, slaMinutes, slaOn, now),
                            )}
                          >
                            {item.waiting_since ? waitedFor(item.waiting_since, now) : t('support.answeredShort')}
                          </span>
                        </span>
                        <span className="mt-1 block truncate text-xs text-dark-100">{item.title}</span>
                        {item.last_message_text && (
                          <span className="mt-0.5 block truncate text-[11px] text-dark-300">
                            {item.last_message_text}
                          </span>
                        )}
                        {item.assignee_id != null && (
                          <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-300">
                            <Users className="h-2.5 w-2.5" />
                            {t('support.assignedTo', { id: item.assignee_id })}
                          </span>
                        )}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
          <div className="hidden border-t border-[var(--glass-border)] px-3 py-2 text-[11px] text-dark-300 md:block">
            {t('support.hotkeys')}
          </div>
        </section>

        {/* Диалог */}
        <section
          className={cn(
            'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--glass-border)]',
            !mobileChatOpen && 'hidden md:flex',
          )}
        >
          {activeId == null ? (
            <EmptyState icon={Users} title={t('support.pickTicket')} />
          ) : (
            <>
              <header className="flex flex-wrap items-center gap-2 border-b border-[var(--glass-border)] px-3 py-2.5 md:flex-nowrap md:gap-3 md:px-4 md:py-3">
                <button
                  type="button"
                  onClick={() => setMobileChatOpen(false)}
                  aria-label={t('support.backToQueue')}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--glass-border)] text-dark-200 md:hidden"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="min-w-0 flex-1 basis-full md:basis-auto">
                  <div className="text-sm font-semibold text-white truncate">{ticket?.title}</div>
                  <div className="text-[11px] text-dark-300">
                    #{ticket?.id} · {ticket?.customer_name || `#${ticket?.bot_user_id}`} · {t(`support.status.${ticket?.status}`)}
                    {ticket?.waiting_since ? ` · ${t('support.waiting')} ${waitedFor(ticket.waiting_since, now)}` : ''}
                  </div>
                </div>
                {watchers.length > 0 && (
                  <span className="flex items-center gap-1.5 rounded-full bg-amber-400/12 px-2.5 py-1 text-[11px] text-amber-300">
                    <Users className="w-3 h-3" />
                    {t('support.alsoViewing', { names: watchers.map((w) => w.username).join(', ') })}
                  </span>
                )}
                {canEdit && (
                  ticket?.assignee_id != null ? (
                    <Button variant="ghost" size="sm" className="h-9 gap-1.5" onClick={() => unassignMutation.mutate()}>
                      <Users className="w-3.5 h-3.5" />
                      {t('support.unassign')}
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" className="h-9 gap-1.5" onClick={() => assignMutation.mutate()}>
                      <Check className="w-3.5 h-3.5" />
                      {t('support.takeIt')}
                    </Button>
                  )
                )}
                {canEdit && (
                  <Button variant="ghost" size="sm" className="h-9" onClick={() => snoozeMutation.mutate(180)}>
                    <Clock className="w-3.5 h-3.5 mr-1.5" />
                    {t('support.snooze3h')}
                  </Button>
                )}
                {canEdit && ticket?.status !== 'closed' && (
                  <Button variant="ghost" size="sm" className="h-9" onClick={() => statusMutation.mutate('closed')}>
                    {t('support.close')}
                  </Button>
                )}
              </header>

              {customer && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--glass-border)] px-3 py-2 text-[11px] text-dark-300 md:px-4">
                  <span className="font-semibold text-dark-100">
                    {customer.full_name || customer.username || `#${customer.id}`}
                  </span>
                  {customer.subscription && (
                    <span>
                      {t('support.customer.subscription')}:{' '}
                      <span className="text-dark-100">
                        {customer.subscription.status === 'active'
                          ? t('support.customer.active')
                          : customer.subscription.status}
                        {customer.subscription.end_date
                          ? ` ${t('support.customer.until')} ${new Date(customer.subscription.end_date).toLocaleDateString()}`
                          : ''}
                      </span>
                    </span>
                  )}
                  {typeof customer.balance_rubles === 'number' && (
                    <span>
                      {t('support.customer.balance')}: <span className="text-dark-100">{customer.balance_rubles} ₽</span>
                    </span>
                  )}
                  <Link
                    to={`/bedolaga/customers/${customer.id}`}
                    className="ml-auto flex h-8 items-center gap-1 rounded-lg border border-[var(--glass-border)] px-2.5 text-cyan-300"
                  >
                    <ExternalLink className="h-3 w-3" />
                    {t('support.customer.openProfile')}
                  </Link>
                </div>
              )}

              {(ticketTags?.length || allTags.length > 0) && canEdit && (
                <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--glass-border)] px-4 py-2">
                  {ticketTags?.map((tag) => (
                    <span key={tag.id} className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-200">
                      {tag.name}
                    </span>
                  ))}
                  {allTags
                    .filter((tag) => !ticketTags?.some((x) => x.id === tag.id))
                    .slice(0, 6)
                    .map((tag) => (
                      <button
                        key={tag.id}
                        type="button"
                        onClick={() => tagMutation.mutate(tag.id)}
                        className="rounded-md border border-dashed border-[var(--glass-border)] px-2 py-0.5 text-[11px] text-dark-300 hover:text-dark-200"
                      >
                        + {tag.name}
                      </button>
                    ))}
                </div>
              )}

              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                {detailLoading && messages.length === 0 ? (
                  <Skeleton className="h-24 w-2/3" />
                ) : (
                  messages.map((m) => (
                    <div key={m.id} className={cn('flex', m.is_from_admin ? 'justify-end' : 'justify-start')}>
                      <div
                        className={cn(
                          'max-w-[88%] rounded-xl border px-3 py-2 md:max-w-[70%]',
                          m.is_from_admin
                            ? 'border-emerald-400/20 bg-emerald-400/10'
                            : 'border-[var(--glass-border)] bg-[var(--glass-bg)]',
                        )}
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <span className={cn('text-[11px] font-bold', m.is_from_admin ? 'text-emerald-300' : 'text-cyan-300')}>
                            {m.author_name || (m.is_from_admin ? t('support.operator') : t('support.client'))}
                          </span>
                          <span className="text-[11px] text-dark-300">{timeOfDay(m.created_at)}</span>
                        </div>
                        <div className="whitespace-pre-line text-xs leading-relaxed text-dark-100">{m.text}</div>
                        {m.has_media && (() => {
                          const keys = m.media_items?.length
                            ? m.media_items.map((item) => `${m.id}:${item.index}`)
                            : [String(m.id)]
                          const ready = keys.filter((key) => mediaUrls[key])
                          const types = m.media_items?.length
                            ? m.media_items.map((item) => item.type)
                            : [m.media_type || 'document']

                          if (ready.length === 0) {
                            return (
                              <div className="mt-1.5 text-[11px] text-dark-300">
                                <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />
                                {t('support.hasMedia', { type: m.media_type || 'file' })}
                              </div>
                            )
                          }

                          const photos = keys.filter((key, i) => mediaUrls[key] && types[i] === 'photo')
                          return (
                            <div
                              className={cn(
                                'mt-1.5 gap-1.5',
                                ready.length > 1 ? 'grid grid-cols-2' : 'flex flex-col',
                              )}
                            >
                              {keys.map((key, i) => {
                                const url = mediaUrls[key]
                                if (!url) return null
                                if (types[i] === 'photo') {
                                  return (
                                    <button
                                      key={key}
                                      type="button"
                                      onClick={() =>
                                        setViewer({ key, list: photos, at: Math.max(0, photos.indexOf(key)) })
                                      }
                                      className="block overflow-hidden rounded-lg border border-[var(--glass-border)]"
                                    >
                                      <img
                                        src={url}
                                        alt={t('support.hasMedia', { type: 'photo' })}
                                        className={cn('w-full object-cover', ready.length > 1 ? 'h-28' : 'max-h-60')}
                                      />
                                    </button>
                                  )
                                }
                                if (types[i] === 'video') {
                                  return <video key={key} src={url} controls className="max-h-60 w-full rounded-lg" />
                                }
                                return (
                                  <a
                                    key={key}
                                    href={url}
                                    download={`ticket-${m.ticket_id}-${m.id}-${i}`}
                                    className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--glass-border)] px-2.5 text-[11px] text-cyan-300"
                                  >
                                    <Download className="h-3.5 w-3.5" />
                                    {t('support.downloadFile')}
                                  </a>
                                )
                              })}
                            </div>
                          )
                        })()}
                      </div>
                    </div>
                  ))
                )}
                <div ref={feedEndRef} />
              </div>

              {canReply && (
                <footer className="border-t border-[var(--glass-border)] p-3">
                  {macroSuggestions.length > 0 && (
                    <div className="mb-2 max-h-40 overflow-y-auto rounded-lg border border-cyan-400/25 bg-[var(--glass-bg)]">
                      {macroSuggestions.map((macro) => (
                        <button
                          key={macro.id}
                          type="button"
                          onClick={() => applyMacro(macro)}
                          className="block w-full border-b border-[var(--glass-border)] px-3 py-2 text-left last:border-0 hover:bg-cyan-400/8"
                        >
                          <span className="block text-xs font-semibold text-white">{macro.title}</span>
                          <span className="block truncate text-[11px] text-dark-300">{macro.body}</span>
                          {macro.set_status && (
                            <span className="mt-1 inline-block rounded bg-emerald-400/12 px-1.5 py-0.5 text-[11px] text-emerald-300">
                              {t('support.macroSetsStatus', { status: t(`support.status.${macro.set_status}`) })}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                  {pendingMacro && (
                    <div className="mb-2 text-[11px] text-cyan-300">
                      {t('support.macroApplied', { title: pendingMacro.title })}
                    </div>
                  )}
                  <textarea
                    ref={draftRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={onDraftKeyDown}
                    rows={3}
                    aria-label={t('support.replyPlaceholder')}
                    placeholder={t('support.replyPlaceholder')}
                    className="w-full resize-none rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2.5 text-xs text-dark-100 outline-none focus:border-cyan-400/40"
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      ref={fileRef}
                      type="file"
                      className="hidden"
                      onChange={(e) => {
                        const picked = e.target.files?.[0]
                        if (picked) attachMutation.mutate(picked)
                        e.target.value = ''
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-11 w-11 p-0 md:h-9 md:w-9"
                      aria-label={t('support.attach')}
                      onClick={() => fileRef.current?.click()}
                      disabled={attachMutation.isPending}
                    >
                      {attachMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Upload className="h-4 w-4" />
                      )}
                    </Button>
                    <span className="hidden text-[11px] text-dark-300 md:inline">{t('support.sendHint')}</span>
                    <span className="hidden flex-1 md:block" />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-11 flex-1 md:h-9 md:flex-none"
                      onClick={() => send(false)}
                      disabled={!draft.trim() || replyMutation.isPending}
                    >
                      {replyMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                      <span className="ml-1.5">{t('support.send')}</span>
                    </Button>
                    <Button
                      size="sm"
                      className="h-11 flex-1 md:h-9 md:flex-none"
                      onClick={() => send(true)}
                      disabled={!draft.trim() || replyMutation.isPending}
                    >
                      {t('support.sendAndClose')}
                    </Button>
                  </div>
                </footer>
              )}
            </>
          )}
        </section>
      </div>

      {viewer && mediaUrls[viewer.list[viewer.at]] && (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-black/90"
          role="dialog"
          aria-modal="true"
          onClick={() => setViewer(null)}
        >
          <div className="flex items-center gap-2 p-3" onClick={(e) => e.stopPropagation()}>
            {viewer.list.length > 1 && (
              <span className="text-xs text-white/70 tabular-nums">
                {viewer.at + 1} / {viewer.list.length}
              </span>
            )}
            <span className="flex-1" />
            <a
              href={mediaUrls[viewer.list[viewer.at]]}
              download={`ticket-${activeId}-${viewer.list[viewer.at]}`}
              className="flex h-11 items-center gap-1.5 rounded-lg border border-white/20 px-3 text-xs text-white"
            >
              <Download className="h-4 w-4" />
              {t('support.downloadFile')}
            </a>
            <button
              type="button"
              onClick={() => setViewer(null)}
              aria-label={t('common.close')}
              className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/20 text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex flex-1 items-center gap-2 overflow-auto p-3">
            {viewer.list.length > 1 && (
              <button
                type="button"
                aria-label={t('support.prevMedia')}
                onClick={(e) => {
                  e.stopPropagation()
                  setViewer((v) => (v ? { ...v, at: (v.at - 1 + v.list.length) % v.list.length } : v))
                }}
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full border border-white/20 text-white"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}
            <img
              src={mediaUrls[viewer.list[viewer.at]]}
              alt={t('support.hasMedia', { type: 'photo' })}
              className="mx-auto max-h-full max-w-full object-contain"
              onClick={(e) => e.stopPropagation()}
            />
            {viewer.list.length > 1 && (
              <button
                type="button"
                aria-label={t('support.nextMedia')}
                onClick={(e) => {
                  e.stopPropagation()
                  setViewer((v) => (v ? { ...v, at: (v.at + 1) % v.list.length } : v))
                }}
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full border border-white/20 text-white"
              >
                <ChevronRight className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>
      )}
    </PermissionGate>
  )
}
