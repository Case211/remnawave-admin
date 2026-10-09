import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  CreditCard,
  Gift,
  History,
  Megaphone,
  RefreshCw,
  Share2,
  Star,
  Ticket,
  Wallet,
} from '@/components/brand/icons'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { InfoTooltip } from '@/components/InfoTooltip'
import { formatDateUtil, getLocale, useFormatters } from '@/lib/useFormatters'
import { cn } from '@/lib/utils'

/** Событие подписки из Bedolaga — GET /notifications/subscriptions бота. */
export interface SubscriptionEvent {
  id: number
  event_type: string
  user_id: number
  user_full_name?: string | null
  user_username?: string | null
  user_telegram_id?: number | null
  amount_kopeks?: number | null
  occurred_at: string
  extra?: Record<string, unknown> | null
}

const PAGE = 20
const MAX_LIMIT = 200 // больше webapi бота за раз не отдаёт

// Группы — по смыслу для оператора: деньги, триалы, промо, кампании
const FILTERS = [
  { id: 'all', types: [] },
  { id: 'payments', types: ['purchase', 'renewal', 'balance_topup'] },
  { id: 'trials', types: ['activation'] },
  { id: 'promo', types: ['promocode_activation', 'promo_group_change'] },
  { id: 'campaigns', types: ['referral_link_visit', 'campaign_registration'] },
] as const

type FilterId = (typeof FILTERS)[number]['id']

const TYPE_STYLES: Record<string, { icon: typeof Gift; color: string }> = {
  activation: { icon: Gift, color: 'text-blue-400 bg-blue-500/10' },
  purchase: { icon: CreditCard, color: 'text-emerald-400 bg-emerald-500/10' },
  renewal: { icon: RefreshCw, color: 'text-emerald-400 bg-emerald-500/10' },
  balance_topup: { icon: Wallet, color: 'text-amber-400 bg-amber-500/10' },
  promocode_activation: { icon: Ticket, color: 'text-violet-400 bg-violet-500/10' },
  promo_group_change: { icon: Star, color: 'text-violet-400 bg-violet-500/10' },
  referral_link_visit: { icon: Share2, color: 'text-pink-400 bg-pink-500/10' },
  campaign_registration: { icon: Megaphone, color: 'text-pink-400 bg-pink-500/10' },
}
const OTHER_STYLE = { icon: History, color: 'text-dark-300 bg-[var(--glass-bg)]' }

// У этих типов сумма — деньги от клиента; у остальных — бонус ему на баланс
const PAID_TYPES = new Set(['activation', 'purchase', 'renewal', 'balance_topup'])

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const text = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null)

export const rubles = (kopeks: number): string => `${(kopeks / 100).toLocaleString(getLocale())} ₽`

/** Название типа события; незнакомый тип бота показываем как есть. */
export function eventTitle(type: string, t: TFunction): string {
  return t(`bedolaga.events.types.${type}`, { defaultValue: type })
}

/** Короткие подробности из extra — у каждого типа бот кладёт туда свои поля. */
export function eventDetails(type: string, extra: Record<string, unknown> | null | undefined, t: TFunction): string[] {
  const x = extra ?? {}
  const days = (v: unknown, sign = '') => {
    const n = num(v)
    return n ? `${sign}${t('bedolaga.events.details.days', { count: n })}` : null
  }
  let parts: (string | null)[] = []
  switch (type) {
    case 'activation': {
      const devices = num(x.device_limit)
      parts = [days(x.trial_duration_days), devices ? t('bedolaga.events.details.devices', { count: devices }) : null]
      break
    }
    case 'purchase':
      parts = [
        days(x.period_days),
        x.was_trial_conversion === true ? t('bedolaga.events.details.fromTrial') : null,
        text(x.payment_method),
      ]
      break
    case 'renewal':
      parts = [days(x.extended_days, '+'), text(x.payment_method)]
      break
    case 'balance_topup': {
      const after = num(x.balance_after)
      parts = [after != null ? t('bedolaga.events.details.balance', { amount: rubles(after) }) : null]
      break
    }
    case 'promocode_activation':
      parts = [text(x.code), days(x.subscription_days, '+')]
      break
    case 'referral_link_visit':
      parts = [text(x.campaign_name), x.was_registered === true ? t('bedolaga.events.details.returning') : null]
      break
    case 'campaign_registration':
      parts = [text(x.campaign_name)]
      break
    case 'promo_group_change': {
      const from = text(x.old_group_name)
      const to = text(x.new_group_name)
      parts = [
        from || to ? `${from ?? '—'} → ${to ?? '—'}` : null,
        x.automatic === true ? t('bedolaga.events.details.automatic') : null,
      ]
      break
    }
  }
  return parts.filter((p): p is string => Boolean(p))
}

/** Кто: имя, иначе @username, иначе Telegram ID, иначе id в Bedolaga. */
export function customerLabel(event: SubscriptionEvent): string {
  const username = text(event.user_username)
  return (
    text(event.user_full_name) ??
    (username ? `@${username}` : null) ??
    (event.user_telegram_id ? String(event.user_telegram_id) : `#${event.user_id}`)
  )
}

/** Лента событий подписок по всем клиентам Bedolaga — свежие сверху. */
export function EventsFeed() {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
  const [filter, setFilter] = useState<FilterId>('all')
  const [limit, setLimit] = useState(PAGE)

  const { data, isLoading, isError, isPlaceholderData } = useQuery<{ items?: SubscriptionEvent[]; total?: number }>({
    queryKey: ['bedolaga-events', filter, limit],
    queryFn: () => {
      const query = new URLSearchParams({ limit: String(limit) })
      FILTERS.find((f) => f.id === filter)?.types.forEach((type) => query.append('event_type', type))
      return client.get(`/bedolaga/customers/events?${query}`).then((r) => r.data)
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: 1,
  })
  const items = Array.isArray(data?.items) ? data.items : []
  const total = data?.total ?? items.length

  const pick = (id: FilterId) => {
    setFilter(id)
    setLimit(PAGE)
  }

  return (
    <Card className="glass-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <History className="w-4 h-4 text-cyan-400" />
          {t('bedolaga.events.title')}
          <InfoTooltip text={t('bedolaga.events.tooltip')} />
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-1.5 mb-3">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => pick(f.id)}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-colors',
                filter === f.id
                  ? 'border-cyan-400/30 bg-cyan-400/15 text-cyan-300'
                  : 'border-[var(--glass-border)] text-dark-400 hover:text-dark-200',
              )}
            >
              {t(`bedolaga.events.filters.${f.id}`)}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 rounded-lg" />)}
          </div>
        ) : items.length === 0 ? (
          <p className={cn('text-sm py-6 text-center', isError ? 'text-red-400' : 'text-dark-400')}>
            {t(isError ? 'bedolaga.events.error' : 'bedolaga.events.empty')}
          </p>
        ) : (
          <div className={cn('transition-opacity', isPlaceholderData && 'opacity-60')}>
            {items.map((event) => {
              const { icon: Icon, color } = TYPE_STYLES[event.event_type] ?? OTHER_STYLE
              const details = eventDetails(event.event_type, event.extra, t)
              const amount = num(event.amount_kopeks)
              const paid = PAID_TYPES.has(event.event_type)
              return (
                <div key={event.id} className="flex items-center gap-3 py-2 border-b border-[var(--glass-border)] last:border-0">
                  <div className={cn('p-1.5 rounded-lg flex-shrink-0', color)}>
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs truncate">
                      <span className="font-medium text-dark-100">{eventTitle(event.event_type, t)}</span>
                      <span className="text-dark-400"> · </span>
                      <Link to={`/bedolaga/customers/${event.user_id}`} className="text-dark-200 hover:text-white transition-colors">
                        {customerLabel(event)}
                      </Link>
                    </div>
                    {details.length > 0 && <div className="text-[10px] text-dark-400 truncate">{details.join(' · ')}</div>}
                  </div>
                  {/* Сумма и время — одной колонкой: на телефоне место нужнее имени клиента */}
                  <div className="flex flex-col items-end flex-shrink-0">
                    {amount ? (
                      <span className={cn('text-xs font-bold tabular-nums', paid ? 'text-emerald-400' : 'text-violet-300')}>
                        {paid ? '' : '+'}{rubles(amount)}
                      </span>
                    ) : null}
                    <span className="text-[10px] text-dark-400 whitespace-nowrap" title={formatDateUtil(event.occurred_at)}>
                      {formatTimeAgo(event.occurred_at)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {items.length < total && limit < MAX_LIMIT && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs"
            disabled={isPlaceholderData}
            onClick={() => setLimit((l) => Math.min(MAX_LIMIT, l + PAGE))}
          >
            {t('bedolaga.events.more')}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
