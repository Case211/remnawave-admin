import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Users,
  CreditCard,
  Activity,
  HeartPulse,
  TrendingUp,
  Ticket,
  RefreshCw,
  AlertCircle,
  Bot,
  UserPlus,
  Wallet,
  Share2,
  ArrowRight,
  Megaphone,
  Ticket as TicketIcon,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { InfoTooltip } from '@/components/InfoTooltip'
import { cn } from '@/lib/utils'

// ── Types ──

interface OverviewData {
  users?: { total?: number; active?: number; blocked?: number; balance_kopeks?: number; balance_rubles?: number }
  subscriptions?: { active?: number; expired?: number }
  support?: { open_tickets?: number }
  payments?: { today_rubles?: number; today_kopeks?: number }
}

interface FullStatsData {
  users?: { total_users?: number; active_users?: number; blocked_users?: number; new_today?: number; new_week?: number; new_month?: number }
  subscriptions?: {
    active_subscriptions?: number; trial_subscriptions?: number; paid_subscriptions?: number
    trial_to_paid_conversion?: number
    trial_statistics?: { used_trials?: number; active_trials?: number; resettable_trials?: number }
  }
  transactions?: {
    totals?: { income_rubles?: number; expenses_rubles?: number; profit_rubles?: number; subscription_income_rubles?: number }
    today?: { transactions_count?: number; income_rubles?: number }
    by_type?: Record<string, { count?: number; amount?: number }>
    by_payment_method?: Record<string, { count?: number; amount?: number }>
  }
  referrals?: {
    users_with_referrals?: number; active_referrers?: number; total_paid_rubles?: number
    today_earnings_rubles?: number; week_earnings_rubles?: number; month_earnings_rubles?: number
    top_referrers?: Array<{ user_id?: number; display_name?: string; username?: string; total_earned_kopeks?: number; referrals_count?: number }>
  }
}

interface HealthData {
  status?: string; api_version?: string; bot_version?: string
  features?: { monitoring?: boolean; maintenance?: boolean; reporting?: boolean; webhooks?: boolean }
}

// ── Page ──

export default function BedolagaDashboard() {
  const { t } = useTranslation()

  const { data: statusData } = useQuery({
    queryKey: ['bedolaga-status'],
    queryFn: () => client.get('/bedolaga/status').then((r) => r.data),
    staleTime: 60_000,
  })
  const isConfigured = statusData?.configured

  const { data: overview, isLoading: overviewLoading, refetch: refetchOverview } = useQuery<OverviewData>({
    queryKey: ['bedolaga-overview'],
    queryFn: () => client.get('/bedolaga/overview').then((r) => r.data),
    enabled: isConfigured === true, staleTime: 60_000, retry: 1,
  })
  const { data: full, isLoading: fullLoading, refetch: refetchFull } = useQuery<FullStatsData>({
    queryKey: ['bedolaga-full'],
    queryFn: () => client.get('/bedolaga/full').then((r) => r.data),
    enabled: isConfigured === true, staleTime: 120_000, retry: 1,
  })
  const { data: health, refetch: refetchHealth } = useQuery<HealthData>({
    queryKey: ['bedolaga-health'],
    queryFn: () => client.get('/bedolaga/health').then((r) => r.data),
    enabled: isConfigured === true, staleTime: 60_000, retry: 1,
  })

  const isLoading = overviewLoading
  const refetchAll = () => { refetchOverview(); refetchFull(); refetchHealth() }

  // Not configured
  if (isConfigured === false) {
    return (
      <div className="space-y-4 md:space-y-6">
        <div className="page-header"><div><h1 className="page-header-title">{t('bedolaga.title')}</h1></div></div>
        <Card className="glass-card">
          <CardContent className="p-8 text-center">
            <AlertCircle className="w-12 h-12 text-amber-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold mb-2">{t('bedolaga.notConfigured')}</h2>
            <p className="text-dark-300 text-sm max-w-md mx-auto whitespace-pre-line text-left">{t('bedolaga.notConfiguredDesc')}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  const users = overview?.users
  const subs = overview?.subscriptions
  const payments = overview?.payments
  const support = overview?.support
  const txns = full?.transactions
  const refs = full?.referrals
  const fullSubs = full?.subscriptions
  const healthOk = health?.status === 'ok'
  const inMaintenance = health?.features?.maintenance
  const profit = txns?.totals?.profit_rubles

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="page-header-title">{t('bedolaga.title')}</h1>
            <InfoTooltip text={t('bedolaga.tooltip')} side="right" />
            {health && (
              <Badge className={cn('text-[10px]', healthOk && !inMaintenance ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30')}>
                {inMaintenance ? t('bedolaga.maintenance') : healthOk ? t('bedolaga.online') : t('bedolaga.offline')}
              </Badge>
            )}
          </div>
          <p className="text-dark-200 mt-1 text-sm">
            {t('bedolaga.subtitle')}
            {health?.bot_version && <span className="text-dark-300 ml-1">v{health.bot_version}</span>}
          </p>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" size="icon" onClick={refetchAll} disabled={isLoading}>
            <RefreshCw className={cn('w-5 h-5', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* ── Top stat cards ── */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : (
        <>
          {/* Row 1: Main metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MiniStat icon={Users} label={t('bedolaga.stats.totalUsers')} value={users?.total?.toLocaleString() ?? '—'} sub={`${t('bedolaga.stats.active')}: ${users?.active ?? 0}`} color="text-blue-400" />
            <MiniStat icon={Activity} label={t('bedolaga.stats.activeSubs')} value={subs?.active?.toLocaleString() ?? '—'} sub={`${t('bedolaga.stats.expired')}: ${subs?.expired ?? 0}`} color="text-emerald-400" />
            <MiniStat icon={CreditCard} label={t('bedolaga.stats.depositsToday')} value={payments?.today_rubles != null ? `${payments.today_rubles.toLocaleString()} ₽` : '0 ₽'} color="text-amber-400" />
            <MiniStat icon={TrendingUp} label={t('bedolaga.stats.totalBalance')} value={users?.balance_rubles != null ? `${users.balance_rubles.toLocaleString()} ₽` : '—'} color="text-violet-400" />
          </div>

          {/* Row 2: Secondary metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MiniStat icon={Ticket} label={t('bedolaga.stats.openTickets')} value={support?.open_tickets ?? 0} color="text-rose-400" />
            <MiniStat icon={Users} label={t('bedolaga.stats.blockedUsers')} value={users?.blocked ?? 0} color="text-red-400" />
            <MiniStat icon={HeartPulse} label={t('bedolaga.stats.botStatus')} value={healthOk ? t('bedolaga.online') : t('bedolaga.offline')} sub={health?.api_version ? `API ${health.api_version}` : undefined} color={healthOk ? 'text-emerald-400' : 'text-red-400'} />
            <MiniStat icon={Bot} label={t('bedolaga.stats.services')} value={[health?.features?.monitoring && 'Mon', health?.features?.webhooks && 'WH', health?.features?.reporting && 'Rep'].filter(Boolean).join(' / ') || '—'} color="text-cyan-400" />
          </div>
        </>
      )}

      {/* ── Extended stats ── */}
      {full && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Finance card */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Wallet className="w-4 h-4 text-emerald-400" />
                {t('bedolaga.sections.income')}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xs text-dark-300 mb-1">{t('bedolaga.periods.today')}</p>
                  <p className="text-lg font-bold text-emerald-400">{txns?.today?.income_rubles?.toLocaleString() ?? 0} ₽</p>
                  {txns?.today?.transactions_count != null && <p className="text-[10px] text-dark-400">{txns.today.transactions_count} txn</p>}
                </div>
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xs text-dark-300 mb-1">{t('bedolaga.income.revenue')}</p>
                  <p className="text-lg font-bold">{txns?.totals?.income_rubles?.toLocaleString() ?? 0} ₽</p>
                  {txns?.totals?.subscription_income_rubles != null && <p className="text-[10px] text-dark-400">sub: {txns.totals.subscription_income_rubles.toLocaleString()} ₽</p>}
                </div>
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xs text-dark-300 mb-1">{profit != null && profit >= 0 ? 'Profit' : t('bedolaga.income.expenses')}</p>
                  <p className={cn('text-lg font-bold', profit != null && profit >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                    {profit != null ? `${profit.toLocaleString()} ₽` : `${txns?.totals?.expenses_rubles?.toLocaleString() ?? 0} ₽`}
                  </p>
                </div>
              </div>

              {/* Payment methods inline */}
              {txns?.by_payment_method && Object.keys(txns.by_payment_method).length > 0 && (
                <div className="border-t border-[var(--glass-border)] pt-2 space-y-1.5">
                  <p className="text-[10px] text-dark-400 uppercase tracking-wider">{t('bedolaga.sections.paymentMethods')}</p>
                  {Object.entries(txns.by_payment_method)
                    .sort(([, a], [, b]) => ((b as any).count ?? 0) - ((a as any).count ?? 0))
                    .slice(0, 4)
                    .map(([method, data]) => (
                      <div key={method} className="flex items-center justify-between text-xs">
                        <span className="text-dark-200">{method}</span>
                        <span className="font-medium">{(data as any).count ?? 0}x · {(((data as any).amount ?? 0) / 100).toLocaleString()} ₽</span>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* New users + Subscriptions */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-blue-400" />
                {t('bedolaga.sections.newUsers')} & {t('bedolaga.sections.plans')}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 space-y-3">
              {/* New users row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xl font-bold">{full.users?.new_today ?? '—'}</p>
                  <p className="text-[10px] text-dark-300">{t('bedolaga.periods.today')}</p>
                </div>
                <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xl font-bold">{full.users?.new_week ?? '—'}</p>
                  <p className="text-[10px] text-dark-300">{t('bedolaga.periods.week')}</p>
                </div>
                <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-xl font-bold">{full.users?.new_month ?? '—'}</p>
                  <p className="text-[10px] text-dark-300">{t('bedolaga.periods.month')}</p>
                </div>
              </div>

              {/* Subscription breakdown */}
              {fullSubs && (
                <div className="border-t border-[var(--glass-border)] pt-3">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="flex-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-dark-300">Paid: {fullSubs.paid_subscriptions ?? 0}</span>
                        <span className="text-dark-300">Trial: {fullSubs.trial_subscriptions ?? 0}</span>
                      </div>
                      <div className="h-2 rounded-full bg-dark-600 overflow-hidden flex">
                        {(fullSubs.paid_subscriptions ?? 0) > 0 && (
                          <div className="h-full bg-emerald-500" style={{ width: `${((fullSubs.paid_subscriptions ?? 0) / Math.max(1, (fullSubs.paid_subscriptions ?? 0) + (fullSubs.trial_subscriptions ?? 0))) * 100}%` }} />
                        )}
                        {(fullSubs.trial_subscriptions ?? 0) > 0 && (
                          <div className="h-full bg-blue-500" style={{ width: `${((fullSubs.trial_subscriptions ?? 0) / Math.max(1, (fullSubs.paid_subscriptions ?? 0) + (fullSubs.trial_subscriptions ?? 0))) * 100}%` }} />
                        )}
                      </div>
                    </div>
                  </div>
                  {fullSubs.trial_to_paid_conversion != null && (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-dark-300">{t('bedolaga.conversions')}</span>
                      <span className="font-medium text-emerald-400">{fullSubs.trial_to_paid_conversion.toFixed(1)}%</span>
                    </div>
                  )}
                  {fullSubs.trial_statistics && (
                    <div className="flex items-center justify-between text-xs mt-1">
                      <span className="text-dark-300">{t('bedolaga.trial')}</span>
                      <span className="text-dark-200">Active: {fullSubs.trial_statistics.active_trials ?? 0} · Used: {fullSubs.trial_statistics.used_trials ?? 0}</span>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Referrals */}
          {refs && (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
                  <div className="flex items-center gap-2"><Share2 className="w-4 h-4 text-violet-400" />{t('bedolaga.sections.referrals')}</div>
                  <Link to="/bedolaga/referrals"><Button variant="ghost" size="sm" className="text-xs gap-1 h-7">{t('bedolaga.referrals.title')} <ArrowRight className="w-3 h-3" /></Button></Link>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                  <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                    <p className="text-lg font-bold">{refs.active_referrers ?? refs.users_with_referrals ?? 0}</p>
                    <p className="text-[10px] text-dark-300">{t('bedolaga.referrals.totalReferrers')}</p>
                  </div>
                  <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                    <p className="text-lg font-bold text-emerald-400">{refs.today_earnings_rubles ?? 0} ₽</p>
                    <p className="text-[10px] text-dark-300">{t('bedolaga.periods.today')}</p>
                  </div>
                  <div className="text-center p-2.5 rounded-lg bg-[var(--glass-bg)]">
                    <p className="text-lg font-bold">{refs.month_earnings_rubles ?? 0} ₽</p>
                    <p className="text-[10px] text-dark-300">{t('bedolaga.periods.month')}</p>
                  </div>
                </div>
                {Array.isArray(refs.top_referrers) && refs.top_referrers.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] text-dark-400 uppercase tracking-wider mb-1">{t('bedolaga.referrals.top')}</p>
                    {refs.top_referrers.slice(0, 5).map((ref, i) => {
                      const maxEarnings = refs.top_referrers![0]?.total_earned_kopeks ?? 1
                      const pct = ref.total_earned_kopeks ? (ref.total_earned_kopeks / maxEarnings) * 100 : 0
                      return (
                        <div key={i} className="relative">
                          <div className="absolute inset-0 rounded bg-emerald-500/5" style={{ width: `${pct}%` }} />
                          <div className="relative flex items-center justify-between py-1.5 px-2 text-xs">
                            <div className="flex items-center gap-2">
                              <span className="text-dark-400 w-4">#{i + 1}</span>
                              <div className={cn('w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold', ['bg-blue-500/20 text-blue-400', 'bg-emerald-500/20 text-emerald-400', 'bg-violet-500/20 text-violet-400', 'bg-amber-500/20 text-amber-400', 'bg-pink-500/20 text-pink-400'][i % 5])}>
                                {(ref.display_name || ref.username || '?').charAt(0).toUpperCase()}
                              </div>
                              <span className="font-medium">{ref.display_name || ref.username || '—'}</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-dark-300">{ref.referrals_count ?? 0} inv</span>
                              <span className="font-medium text-emerald-400 w-16 text-right">{ref.total_earned_kopeks ? (ref.total_earned_kopeks / 100).toLocaleString() : 0} ₽</span>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Quick links */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">{t('bedolaga.title')}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-2 gap-2">
                {[
                  { to: '/bedolaga/customers', icon: Users, label: t('bedolaga.customers.title'), color: 'text-blue-400' },
                  { to: '/bedolaga/promo', icon: TicketIcon, label: t('bedolaga.promo.title'), color: 'text-amber-400' },
                  { to: '/bedolaga/marketing', icon: Megaphone, label: t('bedolaga.marketing.title'), color: 'text-pink-400' },
                  { to: '/bedolaga/referrals', icon: Share2, label: t('bedolaga.referrals.title'), color: 'text-violet-400' },
                ].map(({ to, icon: Icon, label, color }) => (
                  <Link key={to} to={to}>
                    <div className="flex items-center gap-2.5 p-3 rounded-lg bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] border border-transparent hover:border-[var(--glass-border-hover)] transition-all cursor-pointer group">
                      <Icon className={cn('w-4 h-4 group-hover:scale-110 transition-transform', color)} />
                      <span className="text-xs font-medium text-dark-200 group-hover:text-white transition-colors">{label}</span>
                      <ArrowRight className="w-3 h-3 text-dark-400 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {fullLoading && !full && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
        </div>
      )}
    </div>
  )
}

// ── Mini stat card ──

function MiniStat({ icon: Icon, label, value, sub, color }: { icon: typeof Users; label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <Card className="glass-card">
      <CardContent className="p-3 sm:p-4">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <p className="text-[10px] sm:text-xs text-dark-300 uppercase tracking-wider truncate">{label}</p>
            <p className="text-xl sm:text-2xl font-bold mt-0.5 truncate">{value}</p>
            {sub && <p className="text-[10px] text-dark-400 mt-0.5 truncate">{sub}</p>}
          </div>
          <div className={cn('p-2 rounded-lg bg-[var(--glass-bg)] flex-shrink-0', color)}>
            <Icon className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
