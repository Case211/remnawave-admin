import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Archive,
  Check,
  Clock,
  Loader2,
  RefreshCw,
  Search,
  Send,
  Users,
} from '@/components/brand/icons'
import {
  supportApi,
  supportExtraApi,
  type SupportMacro,
  type SupportTag,
  type SupportTicket,
  type SupportWatcher,
} from '../api/support'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/EmptyState'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'

const QUEUES = ['wait_us', 'mine', 'late', 'wait_client', 'snoozed', 'all'] as const
type QueueId = (typeof QUEUES)[number]

/** Время ожидания словами: оператору важны минуты, а не дата создания. */
function waitedFor(iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч ${minutes % 60} мин`
  return `${Math.floor(hours / 24)} дн`
}

function waitTone(iso: string | null, slaMinutes: number): string {
  if (!iso) return 'text-dark-400'
  const minutes = (Date.now() - new Date(iso).getTime()) / 60000
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
  const [draft, setDraft] = useState('')
  // Шаблон, вставленный в черновик: его побочные действия уйдут вместе с ответом.
  const [pendingMacro, setPendingMacro] = useState<SupportMacro | null>(null)
  const draftRef = useRef<HTMLTextAreaElement>(null)

  const { data: queues } = useQuery({
    queryKey: ['support-queues'],
    queryFn: supportApi.getQueues,
    refetchInterval: 30_000,
  })
  const slaMinutes = queues?.sla_minutes ?? 30

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
      <div className="flex h-[calc(100vh-5rem)] gap-3">
        {/* Очереди */}
        <aside className="w-52 flex-shrink-0 flex flex-col gap-4">
          <div className="space-y-1">
            {QUEUES.map((id) => (
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
                <span className={cn('text-xs tabular-nums', queue === id ? 'text-cyan-300' : 'text-dark-400')}>
                  {queues ? (queues as any)[id] : '—'}
                </span>
              </button>
            ))}
          </div>

          {metrics && (
            <div className="rounded-lg border border-[var(--glass-border)] p-2.5 text-[11px] text-dark-300 space-y-1">
              <div className="text-[10px] uppercase tracking-wider text-dark-400">
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
              <div className="flex justify-between">
                <span>{t('support.metrics.breached')}</span>
                <span className={cn('tabular-nums', metrics.breached ? 'text-red-400' : 'text-dark-100')}>
                  {metrics.breached} ({metrics.breached_percent}%)
                </span>
              </div>
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
        <section className="w-80 flex-shrink-0 flex flex-col rounded-xl border border-[var(--glass-border)] overflow-hidden">
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

          <div className="flex-1 overflow-y-auto">
            {listLoading ? (
              <div className="p-3 space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : tickets.length === 0 ? (
              <EmptyState icon={Archive} title={t('support.emptyQueue')} />
            ) : (
              tickets.map((item: SupportTicket) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={cn(
                    'w-full border-b border-[var(--glass-border)] px-3 py-2.5 text-left transition-colors',
                    item.id === activeId ? 'bg-cyan-400/8' : 'hover:bg-[var(--glass-bg)]',
                  )}
                >
                  <div className="flex items-center gap-2">
                    {(item.unread_count ?? 0) > 0 && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />}
                    <span className="text-xs font-semibold text-white truncate">
                      {item.customer_name || `#${item.bot_user_id}`}
                    </span>
                    <span className="text-[10px] text-dark-400">#{item.id}</span>
                    <span className={cn('ml-auto text-[11px] tabular-nums', waitTone(item.waiting_since, slaMinutes))}>
                      {item.waiting_since ? waitedFor(item.waiting_since) : t('support.answeredShort')}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-dark-100 truncate">{item.title}</div>
                  {item.last_message_text && (
                    <div className="mt-0.5 text-[11px] text-dark-400 truncate">{item.last_message_text}</div>
                  )}
                  {item.assignee_id != null && (
                    <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[10px] text-dark-300">
                      <Users className="w-2.5 h-2.5" />
                      {t('support.assignedTo', { id: item.assignee_id })}
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
          <div className="border-t border-[var(--glass-border)] px-3 py-2 text-[10px] text-dark-400">
            {t('support.hotkeys')}
          </div>
        </section>

        {/* Диалог */}
        <section className="flex-1 min-w-0 flex flex-col rounded-xl border border-[var(--glass-border)] overflow-hidden">
          {activeId == null ? (
            <EmptyState icon={Users} title={t('support.pickTicket')} />
          ) : (
            <>
              <header className="flex items-center gap-3 border-b border-[var(--glass-border)] px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-white truncate">{ticket?.title}</div>
                  <div className="text-[11px] text-dark-400">
                    #{ticket?.id} · {ticket?.customer_name || `#${ticket?.bot_user_id}`} · {t(`support.status.${ticket?.status}`)}
                    {ticket?.waiting_since ? ` · ${t('support.waiting')} ${waitedFor(ticket.waiting_since)}` : ''}
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
                    <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => unassignMutation.mutate()}>
                      <Users className="w-3.5 h-3.5" />
                      {t('support.unassign')}
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" className="gap-1.5" onClick={() => assignMutation.mutate()}>
                      <Check className="w-3.5 h-3.5" />
                      {t('support.takeIt')}
                    </Button>
                  )
                )}
                {canEdit && (
                  <Button variant="ghost" size="sm" onClick={() => snoozeMutation.mutate(180)}>
                    <Clock className="w-3.5 h-3.5 mr-1.5" />
                    {t('support.snooze3h')}
                  </Button>
                )}
                {canEdit && ticket?.status !== 'closed' && (
                  <Button variant="ghost" size="sm" onClick={() => statusMutation.mutate('closed')}>
                    {t('support.close')}
                  </Button>
                )}
              </header>

              {(ticketTags?.length || allTags.length > 0) && canEdit && (
                <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--glass-border)] px-4 py-2">
                  {ticketTags?.map((tag) => (
                    <span key={tag.id} className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5 text-[10px] text-dark-200">
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
                        className="rounded-md border border-dashed border-[var(--glass-border)] px-2 py-0.5 text-[10px] text-dark-400 hover:text-dark-200"
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
                          'max-w-[70%] rounded-xl border px-3 py-2',
                          m.is_from_admin
                            ? 'border-emerald-400/20 bg-emerald-400/10'
                            : 'border-[var(--glass-border)] bg-[var(--glass-bg)]',
                        )}
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <span className={cn('text-[11px] font-bold', m.is_from_admin ? 'text-emerald-300' : 'text-cyan-300')}>
                            {m.author_name || (m.is_from_admin ? t('support.operator') : t('support.client'))}
                          </span>
                          <span className="text-[10px] text-dark-400">{timeOfDay(m.created_at)}</span>
                        </div>
                        <div className="whitespace-pre-line text-xs leading-relaxed text-dark-100">{m.text}</div>
                        {m.has_media && (
                          <div className="mt-1.5 text-[11px] text-dark-400">
                            <Clock className="mr-1 inline w-3 h-3" />
                            {t('support.hasMedia', { type: m.media_type || 'file' })}
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
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
                          <span className="block truncate text-[11px] text-dark-400">{macro.body}</span>
                          {macro.set_status && (
                            <span className="mt-1 inline-block rounded bg-emerald-400/12 px-1.5 py-0.5 text-[10px] text-emerald-300">
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
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[10px] text-dark-400">{t('support.sendHint')}</span>
                    <span className="flex-1" />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => send(false)}
                      disabled={!draft.trim() || replyMutation.isPending}
                    >
                      {replyMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                      <span className="ml-1.5">{t('support.send')}</span>
                    </Button>
                    <Button size="sm" onClick={() => send(true)} disabled={!draft.trim() || replyMutation.isPending}>
                      {t('support.sendAndClose')}
                    </Button>
                  </div>
                </footer>
              )}
            </>
          )}
        </section>
      </div>
    </PermissionGate>
  )
}
