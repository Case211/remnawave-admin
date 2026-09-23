import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  AlertTriangle,
  Archive,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Clock,
  Loader2,
  Mail,
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
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'
import client from '@/api/client'
import { getDisplayTimeZone, toZonedDate } from '@/lib/timezone'

const QUEUES = ['wait_us', 'mine', 'late', 'wait_client', 'snoozed', 'all'] as const

/** Отложить можно на срок, а не только «на три часа». */
const SNOOZE_OPTIONS = [
  { id: 'h1', minutes: 60 },
  { id: 'h3', minutes: 180 },
  { id: 'tomorrow', minutes: 60 * 18 },
  { id: 'week', minutes: 60 * 24 * 7 },
] as const

/** Чьего хода ждёт обращение — этим живёт очередь, поэтому полоска слева
 *  показывает состояние, а не приоритет: приоритет и так висит бейджем. */
type TicketState = 'late' | 'waiting' | 'answered' | 'snoozed' | 'closed'

const STATE_BAR: Record<TicketState, string> = {
  late: 'bg-red-400',
  waiting: 'bg-amber-400',
  answered: 'bg-emerald-400',
  snoozed: 'bg-sky-400/60',
  closed: 'bg-white/10',
}

const STATE_BADGE: Record<TicketState, string> = {
  late: 'bg-red-400/15 text-red-300',
  waiting: 'bg-amber-400/15 text-amber-300',
  answered: 'bg-emerald-400/15 text-emerald-300',
  snoozed: 'bg-sky-400/12 text-sky-300',
  closed: 'bg-[var(--glass-bg)] text-dark-300',
}

/** Подписи берём от очередей — в списке и в фильтрах обращение должно
 *  называться одинаково. */
const STATE_LABEL: Record<TicketState, string> = {
  late: 'support.queues.late',
  waiting: 'support.queues.wait_us',
  answered: 'support.queues.wait_client',
  snoozed: 'support.queues.snoozed',
  closed: 'support.status.closed',
}
type QueueId = (typeof QUEUES)[number]

/** Время ожидания словами: оператору важны минуты, а не дата создания. */
function waitedFor(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const minutes = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч ${minutes % 60} мин`
  const days = Math.floor(hours / 24)
  return `${days} дн · ${new Date(iso).toLocaleDateString(undefined, { timeZone: getDisplayTimeZone(), day: '2-digit', month: '2-digit' })}`
}

function waitTone(iso: string | null, slaMinutes: number, slaOn = true, now = Date.now()): string {
  if (!iso) return 'text-dark-300'
  if (!slaOn) return 'text-dark-300'
  const minutes = (now - new Date(iso).getTime()) / 60000
  if (minutes >= slaMinutes) return 'text-red-400 font-bold'
  if (minutes >= slaMinutes / 2) return 'text-amber-400'
  return 'text-dark-300'
}

/** Канал обращения: у клиента из Telegram есть его id, остальные пишут из кабинета. */
function channelOf(telegramId: number | null): 'telegram' | 'cabinet' {
  return telegramId ? 'telegram' : 'cabinet'
}

/** Просрочен ли ответ — отдельно от цвета: значок и подпись говорят то же самое. */
function isBreached(iso: string | null, slaMinutes: number, slaOn: boolean, now: number): boolean {
  if (!iso || !slaOn) return false
  return (now - new Date(iso).getTime()) / 60000 >= slaMinutes
}

/** «Ответили через 8 мин» — сухая цифра, по которой видно качество работы. */
function minutesBetween(fromIso: string, toIso: string): string {
  const minutes = Math.max(0, Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours} ч ${minutes % 60} мин` : `${Math.floor(hours / 24)} дн`
}

/** Вид кликабельного элемента: без фона и отклика действие читается как текст. */
const ACTION_CLASS =
  'rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] text-dark-100 ' +
  'transition-colors hover:border-cyan-400/40 hover:bg-cyan-400/10 hover:text-white ' +
  'active:bg-cyan-400/15 disabled:opacity-50'

/** Действия над подпиской клиента красим по смыслу: продление даёт человеку
 *  дни, сброс отвязывает все его устройства. В сером ряду они выглядели
 *  одинаково безобидно, а нажимаются с телефона одним пальцем. */
const GRANT_CLASS =
  'rounded-lg border border-emerald-400/30 bg-emerald-400/10 text-emerald-200 ' +
  'transition-colors hover:border-emerald-400/50 hover:bg-emerald-400/20 hover:text-emerald-100 ' +
  'active:bg-emerald-400/25 disabled:opacity-50'

const RESET_CLASS =
  'rounded-lg border border-amber-400/30 bg-amber-400/10 text-amber-200 ' +
  'transition-colors hover:border-amber-400/50 hover:bg-amber-400/20 hover:text-amber-100 ' +
  'active:bg-amber-400/25 disabled:opacity-50'

/** Трафик по-человечески.
 *
 * Поле называется `*_gb`, но бот отдаёт в нём сырые байты — на экране это
 * выглядело как «Трафик: 5368709120». Значения меньше 1024 трактуем как
 * гигабайты (так ведут себя старые ответы), остальное — как байты.
 */
function formatTraffic(value: number | null | undefined): string {
  if (value == null) return '—'
  const bytes = value < 1024 ? value * 1024 ** 3 : value
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} КБ`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} МБ`
  if (bytes < 1024 ** 4) return `${(bytes / 1024 ** 3).toFixed(1)} ГБ`
  return `${(bytes / 1024 ** 4).toFixed(2)} ТБ`
}

function stateOf(
  item: { status: string; waiting_since: string | null; snooze_to: string | null },
  slaMinutes: number,
  slaOn: boolean,
  now: number,
): TicketState {
  if (item.status === 'closed') return 'closed'
  if (item.snooze_to && new Date(item.snooze_to).getTime() > now) return 'snoozed'
  if (!item.waiting_since) return 'answered'
  return isBreached(item.waiting_since, slaMinutes, slaOn, now) ? 'late' : 'waiting'
}

function timeOfDay(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString([], { timeZone: getDisplayTimeZone(), hour: '2-digit', minute: '2-digit' })
}

/** Момент в будущем: «14:30» для сегодняшнего срока и «22.09, 14:30» для
 *  дальнего — отложка на неделю без даты выглядит как отложка на час. */
function moment(iso: string | null, now: number): string {
  if (!iso) return ''
  const at = new Date(iso)
  const sameDay = toZonedDate(at) === toZonedDate(new Date(now))
  return sameDay
    ? timeOfDay(iso)
    : at.toLocaleString([], { timeZone: getDisplayTimeZone(), day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Support() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canReply = useHasPermission('bedolaga_support', 'create')
  const canEdit = useHasPermission('bedolaga_support', 'edit')

  // Очередь берём из адреса: так на неё можно сослаться из палитры и из
  // уведомления об SLA.
  const [searchParams, setSearchParams] = useSearchParams()
  const queueFromUrl = searchParams.get('queue') as QueueId | null
  const ticketFromUrl = Number(searchParams.get('ticket')) || null
  const [queue, setQueueState] = useState<QueueId>(
    queueFromUrl && QUEUES.includes(queueFromUrl) ? queueFromUrl : 'wait_us',
  )
  // Правку адреса делаем от актуальных параметров, а не от снимка в замыкании:
  // хоткеи живут внутри эффекта и легко утащили бы устаревшую очередь.
  const patchParams = (
    change: (params: URLSearchParams) => void,
    options?: { replace?: boolean },
  ) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      change(next)
      return next
    }, options)
  }
  const setQueue = (next: QueueId) => {
    setQueueState(next)
    setSelectedId(null)
    // Раньше смена очереди заменяла весь адрес целиком — заодно теряя всё,
    // что в нём есть помимо очереди.
    patchParams((params) => {
      if (next === 'wait_us') params.delete('queue')
      else params.set('queue', next)
      params.delete('ticket')
    }, { replace: true })
  }
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [tagFilter, setTagFilter] = useState<number | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  // Массовые действия: разбор завала начинается с того, что половину очереди
  // нужно закрыть или забрать себе одним движением.
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const toggleSelected = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const [selectedId, setSelectedId] = useState<number | null>(ticketFromUrl)
  // На узком экране колонки не помещаются рядом: показываем либо очередь,
  // либо переписку. Флаг переключает панели, на десктопе он ни на что не влияет.
  const [mobileChatOpen, setMobileChatOpen] = useState(Boolean(ticketFromUrl))

  // Адрес — источник правды для открытого обращения: по ссылке из алерта или
  // от коллеги откроется именно оно, F5 не сбросит выбор, а системная «назад»
  // на телефоне вернёт к очереди вместо выхода из раздела.
  useEffect(() => {
    if (ticketFromUrl) {
      setSelectedId(ticketFromUrl)
      setMobileChatOpen(true)
    } else {
      setMobileChatOpen(false)
    }
  }, [ticketFromUrl])

  // Клик и переход по связанному обращению попадают в историю, хоткеи j/k —
  // нет: перебор очереди с клавиатуры не должен заваливать кнопку «назад».
  const selectTicket = (id: number, options?: { replace?: boolean }) => {
    setSelectedId(id)
    setMobileChatOpen(true)
    patchParams((params) => params.set('ticket', String(id)), options)
  }
  const backToQueue = () => {
    setMobileChatOpen(false)
    patchParams((params) => params.delete('ticket'), { replace: true })
  }
  // Шаблон, вставленный в черновик: его побочные действия уйдут вместе с ответом.
  const [pendingMacro, setPendingMacro] = useState<SupportMacro | null>(null)
  const clearDraft = () =>
    setDrafts((prev) => {
      if (activeId == null) return prev
      const next = { ...prev }
      delete next[activeId]
      return next
    })
  const draftRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const feedEndRef = useRef<HTMLDivElement>(null)
  // Ссылки на скачанные вложения: один blob на сообщение, чтобы не тянуть
  // файл заново при каждом ререндере.
  const [mediaUrls, setMediaUrls] = useState<Record<string, string>>({})
  const [viewer, setViewer] = useState<{ key: string; list: string[]; at: number } | null>(null)
  // Пока ответ идёт к боту, он уже виден в ленте — иначе секунду кажется, что
  // нажатие не сработало.
  const [sending, setSending] = useState<{ ticketId: number; text: string } | null>(null)
  // Время ожидания должно идти само, а не замирать до следующей загрузки списка.
  const [now, setNow] = useState(() => Date.now())
  // Закрытие уходит клиенту уведомлением и не отменяется, перехват тикета
  // забирает работу у коллеги — оба действия спрашивают подтверждение.
  const [confirming, setConfirming] = useState<
    null | 'close' | 'replyClose' | 'steal' | 'bulkSteal' | 'bulkClose' | 'extend' | 'resetDevices'
  >(null)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])

  const { data: queues } = useQuery({
    queryKey: ['support-queues'],
    queryFn: supportApi.getQueues,
    refetchInterval: 30_000,
    // Уведомление всплывает только при скрытой вкладке, а в фоне запросы по
    // умолчанию стоят — счётчик не менялся и уведомлять было не о чем.
    refetchIntervalInBackground: true,
  })
  const slaMinutes = queues?.sla_minutes ?? 30

  // Уведомления браузера: разрешение просим только по кнопке — без действия
  // оператора браузер всё равно откажет, а всплывающий запрос раздражает.
  const [notifyAllowed, setNotifyAllowed] = useState(
    typeof Notification !== 'undefined' && Notification.permission === 'granted',
  )
  const prevWaiting = useRef<number | null>(null)
  useEffect(() => {
    const waiting = queues?.wait_us ?? 0
    const previous = prevWaiting.current
    prevWaiting.current = waiting
    if (!notifyAllowed || previous === null || waiting <= previous) return
    if (document.visibilityState === 'visible') return
    try {
      new Notification(t('support.notify.title'), {
        body: t('support.notify.body', { count: waiting }),
        tag: 'support-queue',
      })
    } catch {
      // уведомления могут быть заблокированы политикой — это не повод падать
    }
  }, [queues?.wait_us, notifyAllowed, t])
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

  const {
    data: list,
    isLoading: listLoading,
    isError: listFailed,
    refetch: refetchList,
  } = useQuery({
    queryKey: ['support-tickets', queue, search, tagFilter],
    queryFn: () =>
      supportApi.listTickets({
        queue,
        search: search || undefined,
        tag_id: tagFilter ?? undefined,
        limit: 100,
      }),
    refetchInterval: 30_000,
  })

  const tickets = useMemo(() => list?.items ?? [], [list])

  // Очередь может вырасти до сотен обращений: рисуем только видимые строки.
  const listRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: tickets.length,
    getScrollElement: () => listRef.current,
    // На телефоне строка выше: там кегль крупнее, чем в плотном десктопном списке.
    estimateSize: () =>
      typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches ? 118 : 132,
    overscan: 8,
  })
  const activeId = selectedId ?? tickets[0]?.id ?? null

  // Черновик живёт на каждый тикет: переключился на срочное и вернулся —
  // набранный текст на месте.
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const draft = activeId != null ? drafts[activeId] ?? '' : ''
  const setDraft = (value: string) =>
    setDrafts((prev) => (activeId == null ? prev : { ...prev, [activeId]: value }))

  const {
    data: detail,
    isFetching: detailLoading,
    isError: detailFailed,
    error: detailError,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: ['support-ticket', activeId],
    queryFn: () => supportApi.getTicket(activeId as number),
    enabled: activeId != null,
    refetchInterval: 20_000,
    // «Такого обращения нет» — окончательный ответ, повторять его незачем.
    retry: (count, error) => (error as any)?.response?.status !== 404 && count < 2,
  })

  const { data: history } = useQuery({
    queryKey: ['support-history', activeId],
    queryFn: () => supportApi.history(activeId as number),
    enabled: activeId != null && historyOpen,
    staleTime: 30_000,
    retry: false,
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

  const { data: noteData } = useQuery({
    queryKey: ['support-note', detailUserId],
    queryFn: () => supportApi.getNote(detailUserId as number),
    enabled: detailUserId != null,
    staleTime: 60_000,
    retry: false,
  })
  const [noteDraft, setNoteDraft] = useState<string | null>(null)
  const noteText = noteDraft ?? noteData?.note ?? ''

  const noteMutation = useMutation({
    mutationFn: (note: string) => supportApi.saveNote(detailUserId as number, note),
    onSuccess: () => {
      setNoteDraft(null)
      queryClient.invalidateQueries({ queryKey: ['support-note', detailUserId] })
      toast.success(t('support.customer.noteSaved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  // Продлить и сбросить устройства — две самые частые просьбы в поддержке;
  // обе ручки уже есть в модуле клиентов.
  const quickActionMutation = useMutation({
    mutationFn: async (action: 'extend' | 'reset-devices') => {
      const subId = customer?.subscription?.id
      if (!subId) throw new Error('no subscription')
      if (action === 'extend') {
        await client.post(`/bedolaga/customers/subscriptions/${subId}/extend`, { days: 3 })
      } else {
        await client.post(`/bedolaga/customers/subscriptions/${subId}/reset-devices`)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['support-customer', detailUserId] })
      toast.success(t('support.customer.actionDone'))
    },
    onError: () => toast.error(t('common.error')),
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
    // Пингуем только пока вкладка открыта: иначе ушедший на обед оператор
    // продолжал «смотреть» тикет, и коллега его не брал.
    const ping = () => {
      if (document.hidden) return
      supportApi
        .presence(activeId)
        .then((r) => alive && setWatchers(r.watchers))
        .catch(() => undefined)
    }
    ping()
    const timer = setInterval(ping, 20_000)
    document.addEventListener('visibilitychange', ping)
    return () => {
      alive = false
      clearInterval(timer)
      document.removeEventListener('visibilitychange', ping)
    }
  }, [activeId])

  // Бот ответил «нет такого обращения»: оно уже вычищено из проекции, поэтому
  // очередь нужно перечитать, иначе строка провисит до следующего круга синка.
  const detailGone = (detailError as any)?.response?.status === 404
  useEffect(() => {
    if (detailGone) queryClient.invalidateQueries({ queryKey: ['support-tickets'] })
  }, [detailGone, queryClient])

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['support-queues'] })
    queryClient.invalidateQueries({ queryKey: ['support-tickets'] })
    queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] })
  }

  const replyMutation = useMutation({
    onMutate: ({ text }: { text: string; close: boolean }) => {
      if (activeId != null) setSending({ ticketId: activeId, text })
    },
    onSettled: () => setSending(null),
    mutationFn: ({ text, close }: { text: string; close: boolean }) =>
      supportApi.reply(activeId as number, text, close, {
        set_status: pendingMacro?.set_status ?? null,
        add_tag_id: pendingMacro?.add_tag_id ?? null,
      }),
    onSuccess: (_, variables) => {
      clearDraft()
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
      clearDraft()
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

  const untagMutation = useMutation({
    mutationFn: (tagId: number) => supportExtraApi.detachTag(activeId as number, tagId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] }),
    onError: () => toast.error(t('common.error')),
  })

  const [newTag, setNewTag] = useState('')
  const createTagMutation = useMutation({
    mutationFn: async (name: string) => {
      const tag = await supportExtraApi.createTag(name)
      if (activeId != null) await supportExtraApi.attachTag(activeId, tag.id)
      return tag
    },
    onSuccess: () => {
      setNewTag('')
      queryClient.invalidateQueries({ queryKey: ['support-tags'] })
      queryClient.invalidateQueries({ queryKey: ['support-ticket', activeId] })
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

  const bulkMutation = useMutation({
    mutationFn: async (action: 'close' | 'assign') => {
      const ids = Array.from(selected)
      // Последовательно: бот на пачку параллельных запросов отвечает 429.
      for (const id of ids) {
        if (action === 'close') await supportApi.setStatus(id, 'closed')
        else await supportApi.assign(id)
      }
    },
    onSuccess: () => {
      setSelected(new Set())
      invalidateAll()
      toast.success(t('support.bulk.done'))
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
        const nextId = tickets[Math.min(index + 1, tickets.length - 1)]?.id ?? activeId
        if (nextId != null) selectTicket(nextId, { replace: true })
      } else if (e.key === 'k' || e.key === 'л') {
        const prevId = tickets[Math.max(index - 1, 0)]?.id ?? activeId
        if (prevId != null) selectTicket(prevId, { replace: true })
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
        // Чужое обращение и с клавиатуры спрашивает подтверждение, как кнопка.
        const current = tickets.find((item) => item.id === activeId)
        if (current?.assignee_id != null && !current.assignee_is_me) setConfirming('steal')
        else if (!current?.assignee_is_me) assignMutation.mutate()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tickets, activeId, canEdit, assignMutation])

  const ticket = detail?.ticket
  const cardState = ticket
    ? stateOf(
        {
          status: ticket.status,
          waiting_since: ticket.waiting_since,
          snooze_to: (ticket as any).snooze_to ?? null,
        },
        slaMinutes,
        slaOn,
        now,
      )
    : 'answered' 
  const messages = detail?.messages ?? []
  const ticketTags = (detail as any)?.tags as SupportTag[] | undefined
  const siblings = ((detail as any)?.sibling_tickets ?? []) as Array<{
    id: number
    title: string
    status: string
    created_at: string
  }>

  return (
    <PermissionGate resource="bedolaga_support" action="view">
      <div className="flex h-[calc(100dvh-5.5rem)] flex-col gap-3 lg:h-[calc(100vh-5rem)] lg:flex-row">
        {/* Очереди */}
        {/* Телефон: очереди лентой, метрики и синк прячем — там триаж, а не отчёты */}
        <div className={cn('flex gap-2 overflow-x-auto pb-1 lg:hidden', mobileChatOpen && 'hidden')}>
          {visibleQueues.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setQueue(id)}
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

        <aside className="hidden w-52 flex-shrink-0 flex-col gap-4 lg:flex">
          <div className="space-y-1">
            {visibleQueues.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setQueue(id)}
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

          {typeof Notification !== 'undefined' && !notifyAllowed && (
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-[11px]"
              onClick={() =>
                Notification.requestPermission().then((result) => setNotifyAllowed(result === 'granted'))
              }
            >
              {t('support.notify.enable')}
            </Button>
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
            'flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--glass-border)] lg:w-80 lg:flex-none',
            mobileChatOpen && 'hidden lg:flex',
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
            {/* Список берёт первую сотню: без этой строки очередь из трёхсот
                обращений выглядит как очередь из ста. */}
            {!listLoading && !listFailed && tickets.length > 0 && (
              <p className="mt-1.5 px-0.5 text-[11px] text-dark-300">
                {t('support.shownOf', { shown: tickets.length, total: list?.total ?? tickets.length })}
                {(list?.total ?? 0) > tickets.length && (
                  <span className="text-amber-300"> · {t('support.truncated')}</span>
                )}
              </p>
            )}
          </div>

          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-b border-[var(--glass-border)] bg-cyan-400/8 px-3 py-2">
              <span className="text-[11px] font-semibold text-cyan-300">
                {t('support.bulk.selected', { count: selected.size })}
              </span>
              <span className="flex-1" />
              <Button
                size="sm"
                variant="outline"
                className="h-8"
                onClick={() =>
                  tickets.some((item) => selected.has(item.id) && item.assignee_id != null && !item.assignee_is_me)
                    ? setConfirming('bulkSteal')
                    : bulkMutation.mutate('assign')
                }
                disabled={bulkMutation.isPending}
              >
                {t('support.bulk.assign')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8"
                onClick={() => setConfirming('bulkClose')}
                disabled={bulkMutation.isPending}
              >
                {t('support.bulk.close')}
              </Button>
              <Button size="sm" variant="ghost" className="h-8" onClick={() => setSelected(new Set())}>
                {t('common.cancel')}
              </Button>
            </div>
          )}

          {allTags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-b border-[var(--glass-border)] px-3 py-2">
              {allTags.slice(0, 8).map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => setTagFilter(tagFilter === tag.id ? null : tag.id)}
                  className={cn(
                    'rounded-md px-2 py-0.5 text-[11px] font-medium border',
                    tagFilter === tag.id
                      ? 'border-cyan-400/30 bg-cyan-400/14 text-cyan-300'
                      : 'border-[var(--glass-border)] text-dark-300 hover:text-dark-100',
                  )}
                >
                  {tag.name}
                </button>
              ))}
            </div>
          )}

          <div ref={listRef} className="flex-1 overflow-y-auto" aria-busy={listLoading}>
            {listLoading ? (
              <div className="p-3 space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : listFailed ? (
              /* Упавший запрос рисовал «обращений нет» — оператор читал это как
                 разгребённую очередь и уходил. Сбой должен называться сбоем. */
              <EmptyState
                icon={AlertTriangle}
                title={t('support.loadFailed')}
                description={t('support.loadFailedHint')}
                action={
                  <Button variant="outline" size="sm" onClick={() => refetchList()}>
                    {t('common.retry')}
                  </Button>
                }
              />
            ) : tickets.length === 0 ? (
              search ? (
                <EmptyState
                  icon={Search}
                  title={t('support.emptySearch')}
                  description={t('support.emptySearchHint')}
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
                  const state = stateOf(item, slaMinutes, slaOn, now)
                  return (
                    <button
                      key={item.id}
                      type="button"
                      ref={rowVirtualizer.measureElement}
                      data-index={row.index}
                      onClick={() => {
                        selectTicket(item.id)
                      }}
                      className={cn(
                        'absolute left-0 top-0 flex w-full gap-2.5 border-b border-[var(--glass-border)] py-2.5 pr-3 text-left transition-colors',
                        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-cyan-400/60',
                        item.id === activeId ? 'bg-cyan-400/8' : 'hover:bg-[var(--glass-bg)]',
                      )}
                      style={{ transform: `translateY(${row.start}px)` }}
                    >
                      {/* Состояние — полоска слева: цвет читается боковым зрением,
                          не занимая места в и без того плотной карточке. */}
                      <span
                        className={cn('w-[3px] flex-shrink-0 rounded-r', STATE_BAR[state])}
                        aria-hidden="true"
                      />
                      {canEdit && (
                        <span
                          role="checkbox"
                          aria-checked={selected.has(item.id)}
                          aria-label={t('support.bulk.select')}
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleSelected(item.id)
                          }}
                          onKeyDown={(e) => {
                            if (e.key === ' ' || e.key === 'Enter') {
                              e.preventDefault()
                              e.stopPropagation()
                              toggleSelected(item.id)
                            }
                          }}
                          className="-m-2 flex h-8 w-8 flex-shrink-0 items-center justify-center"
                        >
                          <span
                            className={cn(
                              'flex h-4 w-4 items-center justify-center rounded border',
                              selected.has(item.id)
                                ? 'border-cyan-400 bg-cyan-400/20 text-cyan-300'
                                : 'border-[var(--glass-border)] text-transparent',
                            )}
                          >
                            <Check className="h-3 w-3" />
                          </span>
                        </span>
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="flex h-1.5 w-1.5 flex-shrink-0 items-center justify-center">
                            {(item.unread_count ?? 0) > 0 && (
                              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                            )}
                          </span>
                          <span className="truncate text-sm font-semibold text-white lg:text-xs">
                            {item.customer_name || `#${item.bot_user_id}`}
                          </span>
                          <span className="text-[11px] text-dark-300">#{item.id}</span>
                          {(item.priority === 'urgent' || item.priority === 'high') && (
                            <span
                              className={cn(
                                'flex-shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold',
                                item.priority === 'urgent'
                                  ? 'bg-red-400/15 text-red-300'
                                  : 'bg-orange-400/15 text-orange-300',
                              )}
                            >
                              {t(`support.priority.${item.priority}`)}
                            </span>
                          )}
                          {/* После ответа время тоже нужно: «ответ дан» без него не
                              говорит, вчера это было или пять минут назад. */}
                          <span
                            className={cn(
                              'ml-auto flex-shrink-0 text-[11px] tabular-nums',
                              item.waiting_since ? waitTone(item.waiting_since, slaMinutes, slaOn, now) : 'text-dark-300',
                            )}
                          >
                            {state === 'late' && <AlertTriangle className="mr-1 inline h-3 w-3" aria-hidden="true" />}
                            {waitedFor(item.waiting_since || item.last_message_at, now)}
                          </span>
                        </span>
                        <span className="mt-1 block truncate text-sm text-dark-100 lg:text-xs">{item.title}</span>
                        {item.last_message_text && (
                          <span className="mt-0.5 block truncate text-xs text-dark-300 lg:text-[11px]">
                            {/* Без автора превью читается как слова клиента, даже когда
                                это наш собственный ответ. */}
                            {item.last_message_from && (
                              <span className="font-semibold text-dark-200">
                                {item.last_message_from === 'admin' ? t('support.fromUs') : t('support.fromClient')}{' '}
                              </span>
                            )}
                            {item.last_message_text}
                          </span>
                        )}
                        <span className="mt-1 flex flex-wrap items-center gap-1.5">
                          <span
                            className={cn(
                              'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold',
                              STATE_BADGE[state],
                            )}
                          >
                            {t(STATE_LABEL[state])}
                          </span>
                          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-300">
                            {channelOf(item.telegram_id) === 'telegram' ? (
                              <Send className="h-2.5 w-2.5" />
                            ) : (
                              <Mail className="h-2.5 w-2.5" />
                            )}
                            {t(`support.channel.${channelOf(item.telegram_id)}`)}
                          </span>
                          {(item.attachments_count ?? 0) > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-300">
                              <Upload className="h-2.5 w-2.5" />
                              {item.attachments_count}
                            </span>
                          )}
                          {item.assignee_id != null && (
                            <span
                              className={cn(
                                'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]',
                                item.assignee_is_me
                                  ? 'bg-cyan-400/12 text-cyan-300'
                                  : 'bg-[var(--glass-bg)] text-dark-300',
                              )}
                            >
                              <Users className="h-2.5 w-2.5" aria-hidden="true" />
                              {item.assignee_is_me
                                ? t('support.assignedToMe')
                                : t('support.assignedToName', {
                                    name: item.assignee_name || `#${item.assignee_id}`,
                                  })}
                            </span>
                          )}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
          <div className="hidden border-t border-[var(--glass-border)] px-3 py-2 text-[11px] text-dark-300 lg:block">
            {t('support.hotkeys')}
          </div>
        </section>

        {/* Диалог */}
        <section
          className={cn(
            'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--glass-border)]',
            !mobileChatOpen && 'hidden lg:flex',
          )}
        >
          {activeId == null ? (
            <EmptyState icon={Users} title={t('support.pickTicket')} />
          ) : (
            <>
              <header className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-[var(--glass-border)] px-3 py-2.5 lg:flex-nowrap lg:gap-3 lg:px-4 lg:py-3">
                <button
                  type="button"
                  onClick={backToQueue}
                  aria-label={t('support.backToQueue')}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--glass-border)] text-dark-200 lg:hidden"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="min-w-0 flex-1 basis-full lg:basis-auto">
                  <div className="text-sm font-semibold text-white truncate">{ticket?.title}</div>
                  {/* Раньше номер, имя, канал и состояние шли одной серой строкой
                      через точки — глаз не отделял «кто написал» от «что делать».
                      Состояние названо действием оператора, а не именем очереди. */}
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-dark-300">
                    <span className="font-semibold text-dark-100">#{ticket?.id}</span>
                    <span className="truncate text-dark-100">
                      {ticket?.customer_name || `#${ticket?.bot_user_id}`}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--glass-bg)] px-2 py-0.5">
                      {channelOf(ticket?.telegram_id ?? null) === 'telegram' ? (
                        <Send className="h-2.5 w-2.5" aria-hidden="true" />
                      ) : (
                        <Mail className="h-2.5 w-2.5" aria-hidden="true" />
                      )}
                      {t(`support.channel.${channelOf(ticket?.telegram_id ?? null)}`)}
                    </span>
                    {ticket && (
                      <span
                        className={cn(
                          'inline-flex items-center rounded-full px-2 py-0.5 font-semibold',
                          STATE_BADGE[cardState],
                        )}
                      >
                        {cardState === 'snoozed' && (ticket as any)?.snooze_to
                          ? t('support.snoozedUntil', { time: moment((ticket as any).snooze_to, now) })
                          : t(`support.cardState.${cardState}`)}
                      </span>
                    )}
                    {ticket?.waiting_since ? ` · ${t('support.waiting')} ${waitedFor(ticket.waiting_since, now)}` : ''}
                    {ticket?.first_response_at && ticket?.created_at && (
                      <span className="hidden whitespace-nowrap rounded bg-[var(--glass-bg)] px-1.5 xl:inline">
                        {t('support.firstResponse')}:{' '}
                        <span className="text-dark-100">
                          {minutesBetween(ticket.created_at, ticket.first_response_at)}
                        </span>
                      </span>
                    )}
                    {ticket?.created_at && (
                      <span className="hidden whitespace-nowrap rounded bg-[var(--glass-bg)] px-1.5 xl:inline">
                        {t('support.age')}:{' '}
                        <span className="text-dark-100">{waitedFor(ticket.created_at, now)}</span>
                      </span>
                    )}
                  </div>
                </div>
                {watchers.length > 0 && (
                  <span className="flex items-center gap-1.5 rounded-full bg-amber-400/12 px-2.5 py-1 text-[11px] text-amber-300">
                    <Users className="w-3 h-3" />
                    {t('support.alsoViewing', { names: watchers.map((w) => w.username).join(', ') })}
                  </span>
                )}
                {/* Чужое обращение перехватывают, своё — отпускают: раньше кнопка
                    «снять» стояла на обоих и уводила тикет у коллеги молча. */}
                {canEdit && (
                  ticket?.assignee_is_me ? (
                    <Button variant="ghost" size="sm" className="h-9 gap-1.5" onClick={() => unassignMutation.mutate()}>
                      <Users className="w-3.5 h-3.5" aria-hidden="true" />
                      {t('support.unassign')}
                    </Button>
                  ) : ticket?.assignee_id != null ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 gap-1.5"
                      onClick={() => setConfirming('steal')}
                    >
                      <Users className="w-3.5 h-3.5" aria-hidden="true" />
                      {t('support.takeOver')}
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" className="h-9 gap-1.5" onClick={() => assignMutation.mutate()}>
                      <Check className="w-3.5 h-3.5" aria-hidden="true" />
                      {t('support.takeIt')}
                    </Button>
                  )
                )}
                {/* Раньше здесь были часы и голые «1 ч / 3 ч» — что случится при
                    нажатии, приходилось выяснять нажатием. */}
                {canEdit && (
                  <span className="flex items-center gap-1 rounded-lg border border-[var(--glass-border)] px-1.5 py-0.5">
                    <Clock className="h-3.5 w-3.5 text-dark-300" aria-hidden="true" />
                    <span className="text-[11px] text-dark-300">{t('support.snoozeLabel')}</span>
                    {SNOOZE_OPTIONS.map((option) => (
                      <button
                        key={option.minutes}
                        type="button"
                        onClick={() => snoozeMutation.mutate(option.minutes)}
                        disabled={snoozeMutation.isPending}
                        title={t('support.snoozeHint', { time: t(`support.snooze.${option.id}`) })}
                        aria-label={t('support.snoozeHint', { time: t(`support.snooze.${option.id}`) })}
                        className={cn(
                          'h-7 px-2 text-[11px] font-medium',
                          ACTION_CLASS,
                          (option.id === 'tomorrow' || option.id === 'week') && 'hidden xl:inline-block',
                        )}
                      >
                        {t(`support.snooze.${option.id}`)}
                      </button>
                    ))}
                  </span>
                )}
                {canEdit && ticket?.status !== 'closed' && (
                  <Button variant="ghost" size="sm" className="h-9" onClick={() => setConfirming('close')}>
                    {t('support.close')}
                  </Button>
                )}
              </header>

              {!customer && detailUserId != null && (
                <div className="flex flex-shrink-0 h-9 items-center border-b border-[var(--glass-border)] px-3 lg:px-4">
                  <Skeleton className="h-3 w-56" />
                </div>
              )}
              {customer && (
                <div className="flex min-h-9 flex-shrink-0 flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-[var(--glass-border)] px-3 py-2 text-[11px] text-dark-300 lg:px-4">
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
                          ? ` ${t('support.customer.until')} ${new Date(customer.subscription.end_date).toLocaleDateString(undefined, { timeZone: getDisplayTimeZone() })}`
                          : ''}
                      </span>
                    </span>
                  )}
                  {typeof customer.balance_rubles === 'number' && (
                    <span className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5">
                      {t('support.customer.balance')}: <span className="text-dark-100">{customer.balance_rubles} ₽</span>
                    </span>
                  )}
                  {customer.subscription?.device_limit != null && (
                    <span className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5">
                      {t('support.customer.devices')}:{' '}
                      <span className="text-dark-100">{customer.subscription.device_limit}</span>
                    </span>
                  )}
                  {customer.subscription?.traffic_used_gb != null && (
                    <span className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5">
                      {t('support.customer.traffic')}:{' '}
                      <span className="text-dark-100">
                        {formatTraffic(customer.subscription.traffic_used_gb)} /{' '}
                        {customer.subscription.traffic_limit_gb
                          ? formatTraffic(customer.subscription.traffic_limit_gb)
                          : t('support.customer.unlimited')}
                      </span>
                    </span>
                  )}
                  {customer.last_activity && (
                    <span className="rounded-md bg-[var(--glass-bg)] px-2 py-0.5">
                      {t('support.customer.lastSeen')}:{' '}
                      <span className="text-dark-100">
                        {new Date(customer.last_activity).toLocaleString(undefined, {
                          timeZone: getDisplayTimeZone(),
                          day: '2-digit',
                          month: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </span>
                  )}
                  {canEdit && customer.subscription?.id && (
                    <>
                      <button
                        type="button"
                        onClick={() => setConfirming('extend')}
                        disabled={quickActionMutation.isPending}
                        className={cn('h-8 px-2.5 text-[11px] font-medium', GRANT_CLASS)}
                      >
                        {t('support.customer.extend3d')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirming('resetDevices')}
                        disabled={quickActionMutation.isPending}
                        className={cn('h-8 px-2.5 text-[11px] font-medium', RESET_CLASS)}
                      >
                        {t('support.customer.resetDevices')}
                      </button>
                    </>
                  )}
                  <Link
                    to={`/bedolaga/customers/${customer.id}`}
                    className={cn('ml-auto flex h-8 items-center gap-1 px-2.5 text-[11px] font-medium text-cyan-300', ACTION_CLASS)}
                  >
                    <ExternalLink className="h-3 w-3" />
                    {t('support.customer.openProfile')}
                  </Link>
                </div>
              )}

              {detailUserId != null && canEdit && (
                <div className="flex flex-shrink-0 items-start gap-2 border-b border-[var(--glass-border)] px-3 py-2 lg:px-4">
                  <textarea
                    value={noteText}
                    onChange={(e) => setNoteDraft(e.target.value)}
                    rows={1}
                    placeholder={t('support.customer.notePlaceholder')}
                    aria-label={t('support.customer.note')}
                    className="h-8 flex-1 resize-none rounded-lg border border-amber-400/20 bg-amber-400/5 px-2.5 py-1.5 text-[11px] text-dark-100 outline-none focus:border-amber-400/40 focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  />
                  {noteDraft !== null && noteDraft !== (noteData?.note ?? '') && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8"
                      onClick={() => noteMutation.mutate(noteText)}
                      disabled={noteMutation.isPending}
                    >
                      {t('common.save')}
                    </Button>
                  )}
                </div>
              )}

              {(ticketTags?.length || allTags.length > 0) && canEdit && (
                <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--glass-border)] px-4 py-2">
                  {ticketTags?.map((tag) => (
                    <span
                      key={tag.id}
                      className="inline-flex items-center gap-1 rounded-md bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-200"
                    >
                      {tag.name}
                      <button
                        type="button"
                        onClick={() => untagMutation.mutate(tag.id)}
                        aria-label={t('support.tagRemove', { name: tag.name })}
                        className="-my-1 flex h-6 w-6 items-center justify-center text-dark-300 hover:text-red-300"
                      >
                        <X className="h-3 w-3" />
                      </button>
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
                        className={cn('border-dashed px-2 py-0.5 text-[11px]', ACTION_CLASS)}
                      >
                        + {tag.name}
                      </button>
                    ))}
                  <input
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newTag.trim()) {
                        e.preventDefault()
                        createTagMutation.mutate(newTag.trim())
                      }
                    }}
                    placeholder={t('support.tagNew')}
                    aria-label={t('support.tagNew')}
                    className="h-6 w-28 rounded-md border border-dashed border-[var(--glass-border)] bg-transparent px-2 text-[11px] text-dark-200 outline-none focus:border-cyan-400/40 focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  />
                </div>
              )}

              {siblings.length > 0 && (
                <div className="flex flex-shrink-0 flex-wrap items-center gap-1.5 border-b border-[var(--glass-border)] px-3 py-2 text-[11px] lg:px-4">
                  <span className="text-dark-300">{t('support.siblings', { count: siblings.length })}</span>
                  {siblings.map((sibling) => (
                    <button
                      key={sibling.id}
                      type="button"
                      onClick={() => selectTicket(sibling.id)}
                      className={cn('max-w-[220px] truncate px-2 py-1 text-[11px]', ACTION_CLASS)}
                      title={sibling.title}
                    >
                      #{sibling.id} · {sibling.title}
                    </button>
                  ))}
                </div>
              )}

              <div className="flex-shrink-0 border-b border-[var(--glass-border)] px-3 lg:px-4">
                <button
                  type="button"
                  onClick={() => setHistoryOpen((open) => !open)}
                  className={cn('my-1.5 flex h-7 items-center gap-1.5 px-2 text-[11px]', ACTION_CLASS)}
                >
                  <Clock className="h-3 w-3" />
                  {t('support.history.title')}
                </button>
                {historyOpen && (
                  <div className="max-h-28 space-y-1 overflow-y-auto pb-2">
                    {history?.items?.length ? (
                      history.items.map((entry, i) => (
                        <div key={`${entry.action}-${i}`} className="flex gap-2 text-[11px] text-dark-300">
                          <span className="tabular-nums">
                            {new Date(entry.created_at).toLocaleString(undefined, {
                              timeZone: getDisplayTimeZone(),
                              day: '2-digit',
                              month: '2-digit',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                          <span className="text-dark-100">
                            {t(`support.history.actions.${entry.action.replace('support.', '')}`, {
                              defaultValue: entry.action,
                            })}
                          </span>
                          <span>{entry.admin_username || t('support.history.system')}</span>
                        </div>
                      ))
                    ) : (
                      <div className="pb-1 text-[11px] text-dark-300">{t('support.history.empty')}</div>
                    )}
                  </div>
                )}
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 space-y-3" aria-busy={detailLoading}>
                {detailFailed && messages.length === 0 ? (
                  <EmptyState
                    icon={AlertTriangle}
                    title={detailGone ? t('support.ticketGone') : t('support.ticketLoadFailed')}
                    description={detailGone ? t('support.ticketGoneHint') : undefined}
                    action={
                      detailGone ? (
                        <Button variant="outline" size="sm" onClick={backToQueue}>
                          {t('support.backToQueue')}
                        </Button>
                      ) : (
                        <Button variant="outline" size="sm" onClick={() => refetchDetail()}>
                          {t('common.retry')}
                        </Button>
                      )
                    }
                  />
                ) : detailLoading && messages.length === 0 ? (
                  <Skeleton className="h-24 w-2/3" />
                ) : (
                  messages.map((m) => (
                    <div key={m.id} className={cn('flex', m.is_from_admin ? 'justify-end' : 'justify-start')}>
                      <div
                        className={cn(
                          'max-w-[88%] rounded-xl border px-3 py-2 lg:max-w-[70%]',
                          m.is_from_admin
                            ? 'border-emerald-400/20 bg-emerald-400/10'
                            : 'border-[var(--glass-border)] bg-[var(--glass-bg)]',
                        )}
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <span className={cn('text-[11px] font-bold', m.is_from_admin ? 'text-emerald-300' : 'text-cyan-300')}>
                            {m.is_auto
                              ? t('support.autoReply')
                              : m.author_name || (m.is_from_admin ? t('support.operator') : t('support.client'))}
                          </span>
                          {/* Робота видно сразу: иначе оператор ищет, кто из коллег
                              уже отвечал клиенту ночью. */}
                          {m.is_auto && (
                            <span className="rounded bg-[var(--glass-bg)] px-1.5 py-0.5 text-[11px] text-dark-300">
                              {t('support.autoReplyBadge')}
                            </span>
                          )}
                          <span className="text-[11px] text-dark-300">{timeOfDay(m.created_at)}</span>
                        </div>
                        <div className="whitespace-pre-line text-sm leading-relaxed text-dark-100 lg:text-xs">{m.text}</div>
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
                                        className={cn('w-full bg-white/5 object-cover', ready.length > 1 ? 'h-28' : 'h-60')}
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
                {sending && sending.ticketId === activeId && (
                  <div className="flex justify-end">
                    <div className="max-w-[88%] rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 opacity-60 lg:max-w-[70%]">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="text-[11px] font-bold text-emerald-300">{t('support.operator')}</span>
                        <span className="flex items-center gap-1 text-[11px] text-dark-300">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {t('support.sending')}
                        </span>
                      </div>
                      <div className="whitespace-pre-line text-sm leading-relaxed text-dark-100 lg:text-xs">{sending.text}</div>
                    </div>
                  </div>
                )}
                <div ref={feedEndRef} />
              </div>

              {canReply && (
                <footer className="flex-shrink-0 border-t border-[var(--glass-border)] p-3">
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
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-cyan-300">
                      <span>{t('support.macroApplied', { title: pendingMacro.title })}</span>
                      {pendingMacro.set_status && (
                        <span className="rounded bg-emerald-400/12 px-1.5 py-0.5 text-emerald-300">
                          {t('support.macroSetsStatus', {
                            status: t(`support.status.${pendingMacro.set_status}`),
                          })}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setPendingMacro(null)}
                        className="inline-flex items-center gap-1 text-dark-300 hover:text-dark-100"
                      >
                        <X className="h-3 w-3" />
                        {t('support.macroDrop')}
                      </button>
                    </div>
                  )}
                  <textarea
                    ref={draftRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={onDraftKeyDown}
                    rows={3}
                    style={{ maxHeight: '40vh' }}
                    aria-label={t('support.replyPlaceholder')}
                    placeholder={t('support.replyPlaceholder')}
                    className="w-full resize-none rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-2.5 text-sm text-dark-100 outline-none focus:border-cyan-400/40 lg:text-xs focus-visible:ring-2 focus-visible:ring-cyan-400/60"
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
                      className="h-11 w-11 p-0 lg:h-9 lg:w-9"
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
                    <span className="hidden text-[11px] text-dark-300 lg:inline">{t('support.sendHint')}</span>
                    <span className="hidden flex-1 lg:block" />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-11 flex-1 lg:h-9 lg:flex-none"
                      onClick={() => send(false)}
                      disabled={!draft.trim() || replyMutation.isPending}
                    >
                      {replyMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                      <span className="ml-1.5">{t('support.send')}</span>
                    </Button>
                    <Button
                      size="sm"
                      className="h-11 flex-1 lg:h-9 lg:flex-none"
                      onClick={() => setConfirming('replyClose')}
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

      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={confirming ? t(`support.confirm.${confirming}.title`) : ''}
        description={confirming ? t(`support.confirm.${confirming}.description`) : undefined}
        confirmLabel={confirming ? t(`support.confirm.${confirming}.action`) : undefined}
        variant={['steal', 'bulkSteal', 'extend'].includes(confirming ?? '') ? 'default' : 'destructive'}
        onConfirm={() => {
          if (confirming === 'close') statusMutation.mutate('closed')
          if (confirming === 'replyClose') send(true)
          if (confirming === 'steal') assignMutation.mutate()
          if (confirming === 'bulkSteal') bulkMutation.mutate('assign')
          if (confirming === 'extend') quickActionMutation.mutate('extend')
          if (confirming === 'resetDevices') quickActionMutation.mutate('reset-devices')
          if (confirming === 'bulkClose') bulkMutation.mutate('close')
          setConfirming(null)
        }}
      />

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
