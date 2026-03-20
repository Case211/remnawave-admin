import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
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
  Calendar,
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
  users?: { total?: number; active?: number; blocked?: number; balance_rubles?: number }
  subscriptions?: { active?: number; expired?: number }
  support?: { open_tickets?: number }
  payments?: { today_rubles?: number; today_kopeks?: number }
}

interface FullStatsData {
  users?: {
    total?: number; active?: number; blocked?: number; balance_rubles?: number
    new_today?: number; new_week?: number; new_month?: number
  }
  subscriptions?: {
    active?: number; expired?: number
    trial?: { count?: number; conversions?: number }
    detailed_by_plan?: Record<string, { count?: number; revenue_rubles?: number }>
  }
  transactions?: {
    income?: { today?: number; week?: number; month?: number }
    expenses?: { today?: number; week?: number; month?: number }
    by_type?: Record<string, number>
    by_method?: Record<string, number>
  }
  referrals?: {
    total_referrers?: number
    earnings_by_period?: { today?: number; week?: number; month?: number }
    top_referrers?: Array<{ username?: string; invited_count?: number; earnings_rubles?: number }>
  }
}

interface HealthData {
  status?: string
  api_version?: string
  bot_version?: string
  features?: {
    monitoring?: boolean
    maintenance?: boolean
    reporting?: boolean
    webhooks?: boolean
  }
}

// ── Components ──

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = 'text-primary-400',
}: {
  icon: typeof Users
  label: string
  value: string | number
  sub?: string
  color?: string
}) {
  return (
    <Card className="glass-card">
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs text-dark-300 uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-bold">{value}</p>
            {sub && <p className="text-xs text-dark-300">{sub}</p>}
          </div>
          <div className={cn('p-2 rounded-lg bg-[var(--glass-bg)]', color)}>
            <Icon className="w-5 h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function PeriodRow({ label, today, week, month }: { label: string; today?: number; week?: number; month?: number }) {
  const fmt = (v?: number) => v != null ? `${v.toLocaleString()} ₽` : '—'
  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--glass-border)] last:border-0">
      <span className="text-sm text-dark-200">{label}</span>
      <div className="flex gap-4 text-sm">
        <span className="text-dark-300 w-24 text-right">{fmt(today)}</span>
        <span className="text-dark-300 w-24 text-right">{fmt(week)}</span>
        <span className="font-medium w-24 text-right">{fmt(month)}</span>
      </div>
    </div>
  )
}

// ── Page ──

export default function Bedolaga() {
  const { t } = useTranslation()

  const { data: statusData } = useQuery({
    queryKey: ['bedolaga-status'],
    queryFn: () => client.get('/bedolaga/status').then((r) => r.data),
    staleTime: 60_000,
  })

  const isConfigured = statusData?.configured

  const {
    data: overview,
    isLoading: overviewLoading,
    refetch: refetchOverview,
  } = useQuery<OverviewData>({
    queryKey: ['bedolaga-overview'],
    queryFn: () => client.get('/bedolaga/overview').then((r) => r.data),
    enabled: isConfigured === true,
    staleTime: 60_000,
    retry: 1,
  })

  const {
    data: full,
    isLoading: fullLoading,
    refetch: refetchFull,
  } = useQuery<FullStatsData>({
    queryKey: ['bedolaga-full'],
    queryFn: () => client.get('/bedolaga/full').then((r) => r.data),
    enabled: isConfigured === true,
    staleTime: 120_000,
    retry: 1,
  })

  const {
    data: health,
    isLoading: healthLoading,
    refetch: refetchHealth,
  } = useQuery<HealthData>({
    queryKey: ['bedolaga-health'],
    queryFn: () => client.get('/bedolaga/health').then((r) => r.data),
    enabled: isConfigured === true,
    staleTime: 60_000,
    retry: 1,
  })

  const isLoading = overviewLoading || healthLoading

  // Not configured state
  if (isConfigured === false) {
    return (
      <div className="space-y-4 md:space-y-6">
        <div className="page-header">
          <div><h1 className="page-header-title">{t('bedolaga.title')}</h1></div>
        </div>
        <Card className="glass-card">
          <CardContent className="p-8 text-center">
            <AlertCircle className="w-12 h-12 text-amber-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold mb-2">{t('bedolaga.notConfigured')}</h2>
            <p className="text-dark-300 text-sm max-w-md mx-auto">{t('bedolaga.notConfiguredDesc')}</p>
            <code className="block mt-4 text-xs text-dark-300 bg-[var(--glass-bg)] p-3 rounded-lg">
              BEDOLAGA_API_URL=http://...:8000<br />
              BEDOLAGA_API_TOKEN=your_token
            </code>
          </CardContent>
        </Card>
      </div>
    )
  }

  const users = overview?.users
  const subs = overview?.subscriptions
  const payments = overview?.payments
  const support = overview?.support
  const fullUsers = full?.users
  const txns = full?.transactions
  const refs = full?.referrals
  const trial = full?.subscriptions?.trial

  const healthOk = health?.status === 'ok'
  const inMaintenance = health?.features?.maintenance

  const refetchAll = () => {
    refetchOverview()
    refetchFull()
    refetchHealth()
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-header-title">{t('bedolaga.title')}</h1>
            <InfoTooltip text={t('bedolaga.tooltip')} side="right" />
            {health && (
              <Badge
                variant={healthOk && !inMaintenance ? 'default' : 'destructive'}
                className={cn(
                  'ml-2 text-[10px]',
                  healthOk && !inMaintenance
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                    : 'bg-red-500/20 text-red-400 border-red-500/30'
                )}
              >
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

      {/* Overview cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="glass-card"><CardContent className="p-4"><Skeleton className="h-4 w-20 mb-2" /><Skeleton className="h-8 w-16" /></CardContent></Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <StatCard icon={Users} label={t('bedolaga.stats.totalUsers')} value={users?.total?.toLocaleString() ?? '—'} sub={`${t('bedolaga.stats.active')}: ${users?.active?.toLocaleString() ?? '—'}`} color="text-blue-400" />
          <StatCard icon={Activity} label={t('bedolaga.stats.activeSubs')} value={subs?.active?.toLocaleString() ?? '—'} sub={`${t('bedolaga.stats.expired')}: ${subs?.expired?.toLocaleString() ?? '—'}`} color="text-emerald-400" />
          <StatCard icon={CreditCard} label={t('bedolaga.stats.depositsToday')} value={payments?.today_rubles != null ? `${payments.today_rubles.toLocaleString()} ₽` : '—'} color="text-amber-400" />
          <StatCard icon={TrendingUp} label={t('bedolaga.stats.totalBalance')} value={users?.balance_rubles != null ? `${users.balance_rubles.toLocaleString()} ₽` : '—'} color="text-violet-400" />
          <StatCard icon={Ticket} label={t('bedolaga.stats.openTickets')} value={support?.open_tickets ?? '—'} color="text-rose-400" />
          <StatCard icon={Users} label={t('bedolaga.stats.blockedUsers')} value={users?.blocked?.toLocaleString() ?? '—'} color="text-red-400" />
          <StatCard icon={HeartPulse} label={t('bedolaga.stats.botStatus')} value={healthOk ? t('bedolaga.online') : t('bedolaga.offline')} sub={health?.api_version ? `API ${health.api_version}` : undefined} color={healthOk ? 'text-emerald-400' : 'text-red-400'} />
          <StatCard icon={Bot} label={t('bedolaga.stats.services')} value={[health?.features?.monitoring && 'Mon', health?.features?.webhooks && 'WH', health?.features?.reporting && 'Rep'].filter(Boolean).join(' / ') || '—'} sub={inMaintenance ? t('bedolaga.maintenance') : undefined} color="text-cyan-400" />
        </div>
      )}

      {/* Extended stats from /full */}
      {full && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* New users */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-blue-400" />
                {t('bedolaga.sections.newUsers')}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-2xl font-bold">{fullUsers?.new_today ?? '—'}</p>
                  <p className="text-xs text-dark-300">{t('bedolaga.periods.today')}</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-2xl font-bold">{fullUsers?.new_week ?? '—'}</p>
                  <p className="text-xs text-dark-300">{t('bedolaga.periods.week')}</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)]">
                  <p className="text-2xl font-bold">{fullUsers?.new_month ?? '—'}</p>
                  <p className="text-xs text-dark-300">{t('bedolaga.periods.month')}</p>
                </div>
              </div>
              {trial && (
                <div className="mt-3 flex items-center justify-between text-xs text-dark-300 px-1">
                  <span>{t('bedolaga.trial')}: {trial.count ?? 0}</span>
                  <span>{t('bedolaga.conversions')}: {trial.conversions ?? 0}</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Income */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Wallet className="w-4 h-4 text-emerald-400" />
                {t('bedolaga.sections.income')}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="space-y-0">
                <div className="flex items-center justify-between text-xs text-dark-300 pb-2 border-b border-[var(--glass-border)]">
                  <span></span>
                  <div className="flex gap-4">
                    <span className="w-24 text-right">{t('bedolaga.periods.today')}</span>
                    <span className="w-24 text-right">{t('bedolaga.periods.week')}</span>
                    <span className="w-24 text-right">{t('bedolaga.periods.month')}</span>
                  </div>
                </div>
                <PeriodRow label={t('bedolaga.income.revenue')} today={txns?.income?.today} week={txns?.income?.week} month={txns?.income?.month} />
                <PeriodRow label={t('bedolaga.income.expenses')} today={txns?.expenses?.today} week={txns?.expenses?.week} month={txns?.expenses?.month} />
              </div>
            </CardContent>
          </Card>

          {/* Payment methods */}
          {txns?.by_method && Object.keys(txns.by_method).length > 0 && (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-amber-400" />
                  {t('bedolaga.sections.paymentMethods')}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-2">
                  {Object.entries(txns.by_method)
                    .sort(([, a], [, b]) => (b as number) - (a as number))
                    .map(([method, count]) => (
                      <div key={method} className="flex items-center justify-between py-1.5 border-b border-[var(--glass-border)] last:border-0">
                        <span className="text-sm">{method}</span>
                        <span className="text-sm font-medium">{(count as number).toLocaleString()}</span>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Referrals */}
          {refs && (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Share2 className="w-4 h-4 text-violet-400" />
                  {t('bedolaga.sections.referrals')}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex items-center gap-4 mb-3">
                  <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)] flex-1">
                    <p className="text-xl font-bold">{refs.total_referrers?.toLocaleString() ?? '—'}</p>
                    <p className="text-xs text-dark-300">{t('bedolaga.referrals.totalReferrers')}</p>
                  </div>
                  {refs.earnings_by_period && (
                    <>
                      <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)] flex-1">
                        <p className="text-xl font-bold">{refs.earnings_by_period.today?.toLocaleString() ?? 0} ₽</p>
                        <p className="text-xs text-dark-300">{t('bedolaga.periods.today')}</p>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-[var(--glass-bg)] flex-1">
                        <p className="text-xl font-bold">{refs.earnings_by_period.month?.toLocaleString() ?? 0} ₽</p>
                        <p className="text-xs text-dark-300">{t('bedolaga.periods.month')}</p>
                      </div>
                    </>
                  )}
                </div>
                {Array.isArray(refs.top_referrers) && refs.top_referrers.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs text-dark-300 uppercase tracking-wider">{t('bedolaga.referrals.top')}</p>
                    {refs.top_referrers.slice(0, 5).map((ref, i) => (
                      <div key={i} className="flex items-center justify-between py-1 text-sm">
                        <span className="text-dark-200">
                          <span className="text-dark-400 mr-1.5">#{i + 1}</span>
                          {ref.username || '—'}
                        </span>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-dark-300">{ref.invited_count ?? 0} inv</span>
                          <span className="font-medium">{ref.earnings_rubles?.toLocaleString() ?? 0} ₽</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Subscription plans */}
          {full?.subscriptions?.detailed_by_plan && Object.keys(full.subscriptions.detailed_by_plan).length > 0 && (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-cyan-400" />
                  {t('bedolaga.sections.plans')}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-2">
                  {Object.entries(full.subscriptions.detailed_by_plan)
                    .sort(([, a], [, b]) => ((b as any).count ?? 0) - ((a as any).count ?? 0))
                    .map(([plan, data]) => (
                      <div key={plan} className="flex items-center justify-between py-1.5 border-b border-[var(--glass-border)] last:border-0">
                        <span className="text-sm">{plan}</span>
                        <div className="flex items-center gap-3 text-sm">
                          <span className="text-dark-300">{(data as any).count ?? 0} sub</span>
                          {(data as any).revenue_rubles != null && (
                            <span className="font-medium">{(data as any).revenue_rubles.toLocaleString()} ₽</span>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Full stats loading */}
      {fullLoading && !full && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="glass-card"><CardContent className="p-6"><Skeleton className="h-4 w-32 mb-4" /><Skeleton className="h-20 w-full" /></CardContent></Card>
          ))}
        </div>
      )}
    </div>
  )
}
