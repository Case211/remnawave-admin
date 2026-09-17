/**
 * Дополнительные виджеты дашборда — данные из других модулей админки
 * (финансы, Bedolaga, нарушения, бэкапы, себестоимость нод). Компактные,
 * переиспользуют существующие API. Видимость/порядок — на стороне Dashboard.
 */
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { financeApi } from '@/api/finance'
import { backupApi } from '@/api/backup'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Wallet, TrendingUp, ShieldAlert, HardDrive, Server, Maximize2, CalendarClock, AlertTriangle,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import type { FinanceItem } from '@/api/finance'

function money(v: number, cur = 'RUB'): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Math.round(v)) +
    (cur ? ` ${cur}` : '')
}

// размер/ресайз прокидываются с дашборда в каждый виджет
export interface WidgetSizeProps { onResize?: () => void }

/** Окраска плитки: тонирует акцентную линию, подложку и свечение через переменную glass-card. */
type ShellTone = 'default' | 'warning' | 'danger'
const SHELL_TONE: Record<ShellTone, string> = {
  default: '',
  warning: 'border-amber-400/35 hover:border-amber-400/50 [--card-accent-rgb:245,158,11]',
  danger: 'border-red-500/45 hover:border-red-500/60 [--card-accent-rgb:239,68,68]',
}

function WidgetShell({ title, subtitle, icon, to, onResize, tone = 'default', children }: {
  title: string; subtitle?: string; icon: React.ReactNode; to?: string; onResize?: () => void
  tone?: ShellTone; children: React.ReactNode
}) {
  const head = (
    <div className="flex items-center gap-2 min-w-0">
      {icon}
      <CardTitle className="text-base truncate">{title}</CardTitle>
      {subtitle && <span className="text-xs text-muted-foreground truncate">{subtitle}</span>}
    </div>
  )
  return (
    <Card className={cn('h-full', SHELL_TONE[tone])}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          {to ? <Link to={to} className="hover:opacity-80 transition-opacity min-w-0">{head}</Link> : head}
          {onResize && (
            <button type="button" onClick={onResize}
              className="shrink-0 p-1 rounded-md text-muted-foreground hover:text-white hover:bg-white/5 transition-colors"
              title="Изменить размер">
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

// Подпись в одну строку и число с валютой мелким шрифтом: три ячейки в ряд
// остаются одной высоты и не переносятся даже в узкой плитке.
function Kpi({ label, value, unit, tone }: {
  label: string; value: string; unit?: string; tone?: 'green' | 'red' | 'white'
}) {
  return (
    <div className="min-w-0 bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
      <p className="text-xs text-muted-foreground truncate" title={label}>{label}</p>
      <p className={cn('flex items-baseline gap-1 whitespace-nowrap font-bold tabular-nums leading-tight',
        tone === 'green' ? 'text-green-400' : tone === 'red' ? 'text-red-400' : 'text-white')}>
        <span className="min-w-0 text-lg truncate">{value}</span>
        {unit && <span className="shrink-0 text-[11px] font-medium text-muted-foreground">{unit}</span>}
      </p>
    </div>
  )
}

/** За сколько дней до оплаты плитка желтеет; меньше дня (сегодня или просрочено) — краснеет. */
export const PAYMENT_SOON_DAYS = 5
/** Горизонт, в котором ищем ближайший платёж. */
export const UPCOMING_DAYS = 30
export type PaymentUrgency = 'none' | 'soon' | 'now'

export function paymentUrgency(daysLeft: number | null | undefined): PaymentUrgency {
  if (daysLeft == null) return 'none'
  if (daysLeft < 1) return 'now'
  if (daysLeft <= PAYMENT_SOON_DAYS) return 'soon'
  return 'none'
}

/** Ближайший расход. Доходы ждут, а не платят — на цвет плитки не влияют. */
export function nextPayment(items: FinanceItem[] | undefined): FinanceItem | null {
  const expenses = (items ?? []).filter((i) => i.kind === 'expense' && i.days_left != null)
  if (!expenses.length) return null
  return expenses.reduce((a, b) => ((b.days_left ?? 0) < (a.days_left ?? 0) ? b : a))
}

const URGENCY_ROW: Record<PaymentUrgency, string> = {
  none: 'border-[var(--glass-border)] bg-[var(--glass-bg)]',
  soon: 'border-amber-400/30 bg-amber-400/[0.08]',
  now: 'border-red-500/35 bg-red-500/[0.1]',
}
const URGENCY_ICON: Record<PaymentUrgency, string> = {
  none: 'text-primary-400', soon: 'text-amber-400', now: 'text-red-400',
}
const URGENCY_DUE: Record<PaymentUrgency, string> = {
  none: 'text-muted-foreground', soon: 'text-amber-300', now: 'text-red-300',
}
const URGENCY_SHELL: Record<PaymentUrgency, ShellTone> = { none: 'default', soon: 'warning', now: 'danger' }

// ── Финансы: KPI месяца + ближайшие списания ─────────────────────
export function FinanceWidget({ onResize }: WidgetSizeProps) {
  const { t } = useTranslation()
  const { data: summary, isLoading } = useQuery({
    queryKey: ['finance-summary'], queryFn: () => financeApi.getSummary(6), staleTime: 60_000,
  })
  const { data: upcoming } = useQuery({
    queryKey: ['finance-upcoming', UPCOMING_DAYS], queryFn: () => financeApi.getUpcoming(UPCOMING_DAYS),
    staleTime: 60_000,
  })
  const tm = summary?.this_month
  const base = summary?.base_currency || 'RUB'
  const next = nextPayment(upcoming?.items)
  const urgency = paymentUrgency(next?.days_left)
  const NextIcon = urgency === 'now' ? AlertTriangle : CalendarClock
  const dueLabel = !next ? '' : next.is_overdue
    ? t('finance.overdueDays', { count: Math.abs(next.days_left ?? 0) })
    : (next.days_left ?? 0) === 0 ? t('finance.dueToday') : t('finance.inDays', { count: next.days_left ?? 0 })
  return (
    <WidgetShell title={t('finance.title')} subtitle={t('dashboard.widgetData.thisMonth')} to="/finance"
      onResize={onResize} tone={URGENCY_SHELL[urgency]} icon={<Wallet className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Kpi label={t('dashboard.widgetData.expense')} value={money(tm?.expense ?? 0, '')} unit={base} tone="red" />
            <Kpi label={t('dashboard.widgetData.income')} value={money(tm?.income ?? 0, '')} unit={base} tone="green" />
            <Kpi label={t('dashboard.widgetData.profit')} value={money(tm?.net ?? 0, '')} unit={base}
              tone={(tm?.net ?? 0) >= 0 ? 'green' : 'red'} />
          </div>
          {/* Ближайший платёж: нода · хостер и сумма со сроком; срок красит и строку, и плитку */}
          {next ? (
            <div className={cn('mt-2 flex items-center gap-2 rounded-lg border px-3 py-1.5', URGENCY_ROW[urgency])}
              title={t('dashboard.widgetData.nextPayment')}>
              <NextIcon className={cn('h-4 w-4 shrink-0', URGENCY_ICON[urgency])} />
              <div className="min-w-0 flex-1 truncate text-sm">
                <span className="text-white/90">{next.node_name || next.name}</span>
                {next.provider_name && <span className="text-muted-foreground"> · {next.provider_name}</span>}
              </div>
              <div className="shrink-0 whitespace-nowrap text-sm tabular-nums">
                <span className="font-semibold text-white">{money(next.amount, next.currency)}</span>
                <span className={cn('ml-1.5 text-xs', URGENCY_DUE[urgency])}>{dueLabel}</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-2">
              {t('dashboard.widgetData.noPayments', { count: UPCOMING_DAYS })}
            </p>
          )}
        </>
      )}
    </WidgetShell>
  )
}

// ── Bedolaga: доход ──────────────────────────────────────────────
export function BedolagaWidget({ onResize }: WidgetSizeProps) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['finance-bedolaga-income'], queryFn: financeApi.getBedolagaIncome,
    staleTime: 120_000, retry: false,
  })
  if (isError) return null // бот не настроен (503) — прячем
  return (
    <WidgetShell title={t('finance.bedolagaIncome')} to="/finance" onResize={onResize} icon={<TrendingUp className="w-5 h-5 text-green-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <div className="grid grid-cols-3 gap-2">
          <Kpi label={t('finance.bedolagaSubscription')} value={money(data?.total.subscription_income ?? 0, '')} unit="RUB" tone="green" />
          <Kpi label={t('finance.bedolagaDeposits')} value={money(data?.total.deposit_income ?? 0, '')} unit="RUB" />
          <Kpi label={t('finance.bedolagaProfit')} value={money(data?.total.profit ?? 0, '')} unit="RUB"
            tone={(data?.total.profit ?? 0) >= 0 ? 'green' : 'red'} />
        </div>
      )}
    </WidgetShell>
  )
}

// ── Нарушения: за сегодня + топ ──────────────────────────────────
interface ViolationStatsResp { total?: number; today?: number; by_type?: Record<string, number> }
interface TopViolator { username?: string; user_uuid?: string; count?: number; violations?: number }
export function ViolationsWidget({ onResize }: WidgetSizeProps) {
  const { t } = useTranslation()
  const { data: stats, isLoading } = useQuery({
    queryKey: ['violations-stats', 1], staleTime: 60_000,
    queryFn: async () => (await client.get('/violations/stats', { params: { days: 1 } })).data as ViolationStatsResp,
  })
  const { data: top } = useQuery({
    queryKey: ['violations-top', 7], staleTime: 60_000,
    queryFn: async () => (await client.get('/violations/top-violators', { params: { days: 7, limit: 5 } })).data as { items?: TopViolator[] } | TopViolator[],
  })
  const topList = Array.isArray(top) ? top : (top?.items || [])
  return (
    <WidgetShell title={t('nav.violations', { defaultValue: 'Нарушения' })} to="/violations" onResize={onResize} icon={<ShieldAlert className="w-5 h-5 text-red-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-red-400">{stats?.today ?? 0}</span>
            <span className="text-xs text-muted-foreground">{t('dashboard.widgetData.violationsToday')}</span>
          </div>
          {topList.length > 0 && (
            <div className="mt-2 space-y-1">
              {topList.slice(0, 5).map((v, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-white/80 truncate">{v.username || v.user_uuid?.slice(0, 8) || '—'}</span>
                  <span className="text-muted-foreground font-mono">{v.count ?? v.violations ?? 0}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </WidgetShell>
  )
}

// ── Бэкапы: последний + место ────────────────────────────────────
export function BackupWidget({ onResize }: WidgetSizeProps) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['backup-status'], queryFn: backupApi.getStatus, staleTime: 120_000, retry: false,
  })
  const last = data?.last_backup
  const okDate = last?.created_at ? last.created_at.slice(0, 16).replace('T', ' ') : '—'
  const stale = last?.created_at ? (Date.now() - new Date(last.created_at).getTime()) > 36 * 3600_000 : true
  return (
    <WidgetShell title={t('nav.backups', { defaultValue: 'Бэкапы' })} to="/backups" onResize={onResize} icon={<HardDrive className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-1.5 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">{t('dashboard.widgetData.lastBackup')}</span>
            <span className={cn('font-mono text-xs', stale ? 'text-amber-400' : 'text-green-400')}>{okDate}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">{t('dashboard.widgetData.backupFiles')}</span>
            <span className="font-mono text-xs text-white">{data?.file_count ?? 0}</span>
          </div>
        </div>
      )}
    </WidgetShell>
  )
}

// ── Себестоимость: топ дорогих нод ₽/GB ──────────────────────────
export function NodeCostsWidget({ onResize }: WidgetSizeProps) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['finance-node-costs'], queryFn: () => financeApi.getNodeCosts(30), staleTime: 300_000,
  })
  const base = data?.base_currency || 'RUB'
  const top = (data?.items || []).filter((n) => n.cost_per_gb != null)
    .sort((a, b) => (b.cost_per_gb || 0) - (a.cost_per_gb || 0)).slice(0, 5)
  return (
    <WidgetShell title={t('finance.nodeCosts.title')} to="/finance" onResize={onResize} icon={<Server className="w-5 h-5 text-primary-400" />}>
      {isLoading ? <Skeleton className="h-20 w-full" /> : !top.length ? (
        <p className="text-xs text-muted-foreground">{t('dashboard.widgetData.noNodeCosts')}</p>
      ) : (
        <div className="space-y-1">
          {top.map((n) => (
            <div key={n.node_uuid} className="flex items-center justify-between text-xs">
              <span className="text-white/80 truncate">{n.node_name}</span>
              <span className="font-mono text-muted-foreground">{money(n.cost_per_gb || 0, base)}/GB</span>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  )
}
