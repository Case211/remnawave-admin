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
import { supportApi, type SupportTicket } from '../api/support'
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
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const draftRef = useRef<HTMLTextAreaElement>(null)

  const { data: queues } = useQuery({
    queryKey: ['support-queues'],
    queryFn: supportApi.getQueues,
    refetchInterval: 30_000,
  })
  const slaMinutes = queues?.sla_minutes ?? 30

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

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['support-queues'] })
    queryClient.invalidateQueries({ queryKey: ['support-tickets'] })
    queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] })
  }

  const replyMutation = useMutation({
    mutationFn: ({ text, close }: { text: string; close: boolean }) =>
      supportApi.reply(activeId as number, text, close),
    onSuccess: (_, variables) => {
      setDraft('')
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

  const statusMutation = useMutation({
    mutationFn: (status: string) => supportApi.setStatus(activeId as number, status),
    onSuccess: () => {
      invalidateAll()
      toast.success(t('common.saved'))
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

  const onDraftKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      send(e.shiftKey)
    }
  }

  const ticket = detail?.ticket
  const messages = detail?.messages ?? []

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
                value={search}
                onChange={(e) => setSearch(e.target.value)}
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
                </button>
              ))
            )}
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
                {canEdit && (
                  <Button variant="outline" size="sm" className="gap-1.5" onClick={() => assignMutation.mutate()}>
                    <Check className="w-3.5 h-3.5" />
                    {t('support.takeIt')}
                  </Button>
                )}
                {canEdit && ticket?.status !== 'closed' && (
                  <Button variant="ghost" size="sm" onClick={() => statusMutation.mutate('closed')}>
                    {t('support.close')}
                  </Button>
                )}
              </header>

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
