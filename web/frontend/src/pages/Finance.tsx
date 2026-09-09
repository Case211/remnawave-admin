import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/lib/useTabParam'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  RefreshCw,
  Wallet,
  Check,
  Clock,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Download,
  CalendarClock,
  Server,
  Settings2,
  Zap,
  ChevronDown,
  Archive,
  MoreVertical,
  RotateCcw,
  Pencil,
  Tag,
} from '@/components/brand/icons'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'
import { InteractiveChart } from '@/components/charts/InteractiveChart'
import { financeApi, FinanceItem, FinancePayment, ItemPayload, FinanceProvider, FinanceAccount, FinanceService, AccountTestResult } from '../api/finance'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { QueryError } from '@/components/QueryError'
import { InfoTooltip } from '@/components/InfoTooltip'
import { useHasPermission } from '@/components/PermissionGate'
import { useChartTheme } from '@/lib/useChartTheme'
import { cn } from '@/lib/utils'

const CYCLES = ['monthly', 'yearly', 'days', 'once'] as const
const PIE_COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']
// фиат + ходовая крипта (курсы: фиат — ЦБ РФ, крипта — CoinGecko)
const COMMON_CURRENCIES = ['RUB', 'USD', 'EUR', 'USDT', 'TON', 'BTC']

function fmtMoney(amount: number, currency: string): string {
  const s = amount.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${s} ${currency}`
}

/** Валюта: селект из курсов + ходовых, «Другая…» раскрывает ручной ввод. */
function CurrencySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation()
  const { data: rates } = useQuery({ queryKey: ['finance-rates'], queryFn: financeApi.listRates, staleTime: 300_000 })
  const options = useMemo(() => {
    const set = new Set([...COMMON_CURRENCIES, ...(rates?.items || []).map((r) => r.currency)])
    if (value) set.add(value.toUpperCase())
    return Array.from(set).sort()
  }, [rates, value])
  const [custom, setCustom] = useState(false)

  if (custom) {
    return (
      <Input
        autoFocus value={value} maxLength={8}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        onBlur={() => value && setCustom(false)}
      />
    )
  }
  return (
    <Select value={value || 'RUB'} onValueChange={(v) => (v === '__custom' ? setCustom(true) : onChange(v))}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
        <SelectItem value="__custom">{t('finance.otherCurrency')}</SelectItem>
      </SelectContent>
    </Select>
  )
}

// ── Overview tab ─────────────────────────────────────────────────

function OverviewTab() {
  const { t } = useTranslation()
  const chart = useChartTheme()

  // 12 месяцев истории — хватает и графику, и селектору месяца KPI
  const { data: summary, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-summary'],
    queryFn: () => financeApi.getSummary(12),
    staleTime: 60_000,
  })
  const [kpiMonth, setKpiMonth] = useState('current')
  const { data: upcoming } = useQuery({
    queryKey: ['finance-upcoming'],
    queryFn: () => financeApi.getUpcoming(30),
    staleTime: 60_000,
  })
  const { data: bedolaga } = useQuery({
    queryKey: ['finance-bedolaga-income'],
    queryFn: financeApi.getBedolagaIncome,
    staleTime: 120_000,
    retry: false,  // не настроена (503) → просто прячем блок
  })
  const { data: accounts } = useQuery({
    queryKey: ['finance-accounts'], queryFn: financeApi.listAccounts, staleTime: 60_000,
  })
  const hasAccounts = (accounts?.items.length ?? 0) > 0
  const { data: snapshots } = useQuery({
    queryKey: ['finance-snapshots'],
    queryFn: () => financeApi.listSnapshots(90),
    staleTime: 300_000,
    enabled: hasAccounts,
  })
  const { data: nodeCosts } = useQuery({
    queryKey: ['finance-node-costs'],
    queryFn: () => financeApi.getNodeCosts(30),
    staleTime: 300_000,
  })

  const balanceTrend = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>()
    const providers = new Set<string>()
    for (const s of snapshots?.items || []) {
      providers.add(s.provider_name)
      const row = byDate.get(s.snapshot_date) || { date: s.snapshot_date.slice(5) }
      row[s.provider_name] = s.balance
      byDate.set(s.snapshot_date, row)
    }
    return { rows: Array.from(byDate.values()), providers: Array.from(providers) }
  }, [snapshots])

  const base = summary?.base_currency || 'RUB'

  const monthlyChart = useMemo(
    () => (summary?.monthly || []).map((m) => ({
      label: m.month.slice(2), expense: m.expense, income: m.income, net: m.net,
    })),
    [summary],
  )

  // KPI-месяц: «current» = факт + предстоящие списания до конца месяца
  // (с сервера); прошлый месяц — чистый факт из monthly[] (upcoming не бывает).
  const monthOptions = useMemo(() => {
    const nowKey = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}` })()
    return (summary?.monthly || []).map((m) => m.month).filter((m) => m !== nowKey).reverse()
  }, [summary])
  const thisMonth = useMemo(() => {
    if (kpiMonth !== 'current') {
      const b = (summary?.monthly || []).find((m) => m.month === kpiMonth)
      return {
        income: b?.income ?? 0, expense: b?.expense ?? 0, net: b?.net ?? 0,
        expense_actual: b?.expense ?? 0, income_actual: b?.income ?? 0,
        expense_upcoming: 0, income_upcoming: 0,
      }
    }
    const tm = summary?.this_month
    if (tm) return tm
    const now = new Date()
    const key = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const b = (summary?.monthly || []).find((m) => m.month === key)
    return {
      income: b?.income ?? 0, expense: b?.expense ?? 0, net: b?.net ?? 0,
      expense_actual: b?.expense ?? 0, income_actual: b?.income ?? 0,
      expense_upcoming: 0, income_upcoming: 0,
    }
  }, [summary, kpiMonth])
  const periodLabel = kpiMonth === 'current' ? t('finance.thisMonth') : kpiMonth
  const kpiHint = (actual: number, upcoming: number) =>
    upcoming > 0
      ? t('finance.factPlusUpcoming', { actual: fmtMoney(actual, base), upcoming: fmtMoney(upcoming, base) })
      : periodLabel
  // человекочитаемые названия способов оплаты; неизвестные бренды — капитализация слага
  const pmLabel = (m: string) =>
    t(`finance.pm.${m}`, { defaultValue: m.charAt(0).toUpperCase() + m.slice(1).replace(/_/g, ' ') })

  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-4">
      {/* Селектор месяца KPI: текущий (факт+предстоящие) или любой из истории */}
      <div className="flex items-center gap-2">
        <Select value={kpiMonth} onValueChange={setKpiMonth}>
          <SelectTrigger className="w-44 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="current">{t('finance.range.thisMonth')}</SelectItem>
            {monthOptions.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* KPI строка */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <KpiCard
              icon={<TrendingDown className="w-5 h-5 text-red-400" />}
              label={t('finance.monthExpense')}
              value={fmtMoney(thisMonth.expense, base)}
              hint={kpiHint(thisMonth.expense_actual, thisMonth.expense_upcoming)}
              tone="red"
            />
            <KpiCard
              icon={<TrendingUp className="w-5 h-5 text-green-400" />}
              label={t('finance.monthIncome')}
              value={fmtMoney(thisMonth.income, base)}
              hint={kpiHint(thisMonth.income_actual, thisMonth.income_upcoming)}
              tone="green"
            />
            <KpiCard
              icon={<Wallet className="w-5 h-5 text-primary-400" />}
              label={t('finance.monthProfit')}
              value={fmtMoney(thisMonth.net, base)}
              hint={periodLabel}
              tone={thisMonth.net >= 0 ? 'green' : 'red'}
            />
          </>
        )}
      </div>

      {/* Балансы хостеров + тренд */}
      {hasAccounts && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('finance.hosterBalances')}</CardTitle>
              <InfoTooltip text={t('finance.hosterBalancesTooltip')} side="right" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 mb-3">
              {(accounts?.items || []).filter((a) => a.balance != null).map((a) => {
                const low = a.low_balance_threshold != null && (a.balance ?? 0) < a.low_balance_threshold
                return (
                  <div key={a.id} className={cn(
                    'px-3 py-2 rounded-lg border min-w-[140px]',
                    low ? 'bg-red-500/10 border-red-500/20' : 'bg-[var(--glass-bg)] border-[var(--glass-border)]',
                  )}>
                    <p className="text-xs text-muted-foreground truncate">{a.provider_name}</p>
                    <p className={cn('text-base font-bold font-mono', low ? 'text-red-400' : 'text-white')}>
                      {fmtMoney(a.balance ?? 0, a.balance_currency || '')}
                    </p>
                    {a.last_sync_status === 'error' && (
                      <p className="text-[10px] text-red-400 truncate" title={a.last_sync_error || ''}>{t('finance.syncFailed')}</p>
                    )}
                  </div>
                )
              })}
            </div>
            {balanceTrend.rows.length > 1 && (
              <InteractiveChart
                data={balanceTrend.rows}
                xKey="date"
                height={180}
                defaultType="line"
                exportName="hoster-balances"
                tooltipFormatter={(v, n) => [fmtMoney(Number(v) || 0, base), n]}
                series={balanceTrend.providers.map((p, i) => ({
                  key: p, name: p, color: PIE_COLORS[i % PIE_COLORS.length],
                }))}
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* Доход Bedolaga (живой) */}
      {bedolaga && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-green-400" />
              <CardTitle className="text-base">{t('finance.bedolagaIncome')}</CardTitle>
              <InfoTooltip text={t('finance.bedolagaTooltip')} side="right" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaSubscription')}</p>
                <p className="text-lg font-bold text-green-400">{fmtMoney(bedolaga.total.subscription_income, 'RUB')}</p>
                <p className="text-[11px] text-muted-foreground">{t('finance.allTime')}</p>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaDeposits')}</p>
                <p className="text-lg font-bold text-white">{fmtMoney(bedolaga.total.deposit_income, 'RUB')}</p>
                <p className="text-[11px] text-muted-foreground">{t('finance.bedolagaToday')}: {fmtMoney(bedolaga.today.deposit_income, 'RUB')}</p>
              </div>
              <div className="bg-[var(--glass-bg)] rounded-lg px-3 py-2.5 border border-[var(--glass-border)]">
                <p className="text-xs text-muted-foreground">{t('finance.bedolagaProfit')}</p>
                <p className={cn('text-lg font-bold', bedolaga.total.profit >= 0 ? 'text-green-400' : 'text-red-400')}>
                  {fmtMoney(bedolaga.total.profit, 'RUB')}
                </p>
                <p className="text-[11px] text-muted-foreground">{t('finance.allTime')}</p>
              </div>
            </div>
            {Object.keys(bedolaga.by_payment_method).length > 0 && (
              <div className="flex items-center gap-2 flex-wrap mt-3">
                <span className="text-xs text-muted-foreground">{t('finance.bedolagaByMethod')}:</span>
                {Object.entries(bedolaga.by_payment_method).map(([m, amt]) => (
                  <Badge key={m} variant="outline" className="text-[10px]">
                    {pmLabel(m)}: {fmtMoney(amt, 'RUB')}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* P&L график + структура расходов */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('finance.plByMonth')}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[240px] w-full" />
            ) : monthlyChart.length === 0 ? (
              <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
                {t('finance.noPayments')}
              </div>
            ) : (
              <InteractiveChart
                data={monthlyChart}
                xKey="label"
                height={240}
                exportName="pl-by-month"
                tooltipFormatter={(v, n) => [fmtMoney(Number(v) || 0, base), t(`finance.${n}`)]}
                legendFormatter={(v) => t(`finance.${v}`)}
                series={[
                  { key: 'expense', name: 'expense', color: '#ef4444' },
                  { key: 'income', name: 'income', color: '#10b981' },
                ]}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('finance.expenseStructure')}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[240px] w-full" />
            ) : !summary?.by_category.length ? (
              <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
                {t('finance.noItems')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={summary.by_category} dataKey="monthly" nameKey="category"
                    cx="50%" cy="50%" outerRadius={80} innerRadius={45}
                  >
                    {summary.by_category.map((c, i) => (
                      <Cell key={c.category} fill={c.color || PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={chart.tooltipStyle}
                    formatter={(v, n) => [fmtMoney(Number(v) || 0, base), String(n)]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Себестоимость нод: ₽/GB и ₽/юзер за 30 дней */}
      {(nodeCosts?.items.length ?? 0) > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-primary-400" />
              <CardTitle className="text-base">{t('finance.nodeCosts.title')}</CardTitle>
              <InfoTooltip text={t('finance.nodeCosts.tooltip')} side="right" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground text-left">
                    <th scope="col" className="pb-2 pr-3 font-normal">{t('finance.nodeCosts.node')}</th>
                    <th scope="col" className="pb-2 pr-3 font-normal text-right">{t('finance.nodeCosts.monthlyCost')}</th>
                    <th scope="col" className="pb-2 pr-3 font-normal text-right">{t('finance.nodeCosts.traffic', { days: nodeCosts!.days })}</th>
                    <th scope="col" className="pb-2 pr-3 font-normal text-right">{t('finance.nodeCosts.perGb')}</th>
                    <th scope="col" className="pb-2 pr-3 font-normal text-right">{t('finance.nodeCosts.users')}</th>
                    <th scope="col" className="pb-2 font-normal text-right">{t('finance.nodeCosts.perUser')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {nodeCosts!.items.map((n) => (
                    <tr key={n.node_uuid}>
                      <td className="py-2 pr-3 text-white whitespace-nowrap">{n.node_name}</td>
                      <td className="py-2 pr-3 text-right font-mono whitespace-nowrap">
                        {n.monthly_cost > 0 ? fmtMoney(n.monthly_cost, base) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-2 pr-3 text-right font-mono whitespace-nowrap">{n.traffic_gb > 0 ? `${n.traffic_gb} GB` : '—'}</td>
                      <td className="py-2 pr-3 text-right font-mono whitespace-nowrap">
                        {n.cost_per_gb != null ? fmtMoney(n.cost_per_gb, base) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-2 pr-3 text-right font-mono">{n.users || '—'}</td>
                      <td className="py-2 text-right font-mono whitespace-nowrap">
                        {n.cost_per_user != null ? fmtMoney(n.cost_per_user, base) : <span className="text-muted-foreground">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {nodeCosts!.unassigned_monthly > 0 && (
              <p className="text-[11px] text-muted-foreground mt-2">
                {t('finance.nodeCosts.unassigned', { amount: fmtMoney(nodeCosts!.unassigned_monthly, base) })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Ближайшие списания */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-primary-400" />
            <CardTitle className="text-base">{t('finance.upcoming')}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {!upcoming?.items.length ? (
            <div className="py-6 text-center text-sm text-muted-foreground">{t('finance.noUpcoming')}</div>
          ) : (
            <div className="space-y-1.5">
              {upcoming.items.slice(0, 12).map((it) => (
                <div
                  key={it.id}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg border',
                    it.is_overdue
                      ? 'bg-red-500/10 border-red-500/20'
                      : (it.days_left ?? 99) <= 1
                        ? 'bg-yellow-500/10 border-yellow-500/20'
                        : 'bg-[var(--glass-bg)] border-[var(--glass-border)]',
                  )}
                >
                  {it.is_overdue ? (
                    <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                  ) : (
                    <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                  )}
                  <span className="text-sm text-white truncate">{it.name}</span>
                  {it.provider_name && (
                    <Badge variant="outline" className="text-[10px] h-5">{it.provider_name}</Badge>
                  )}
                  <span className="ml-auto text-xs font-mono text-white">{fmtMoney(it.amount, it.currency)}</span>
                  <span className={cn('text-xs w-24 text-right', it.is_overdue ? 'text-red-400' : 'text-muted-foreground')}>
                    {it.is_overdue
                      ? t('finance.overdueDays', { count: Math.abs(it.days_left ?? 0) })
                      : it.days_left === 0
                        ? t('finance.dueToday')
                        : t('finance.inDays', { count: it.days_left ?? 0 })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function KpiCard({ icon, label, value, hint, tone }: {
  icon: React.ReactNode; label: string; value: string; hint: string; tone: 'red' | 'green'
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">{label}</span>
          {icon}
        </div>
        <p className={cn('text-xl font-bold', tone === 'green' ? 'text-green-400' : 'text-red-400')}>{value}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>
      </CardContent>
    </Card>
  )
}

// ── Items tab ────────────────────────────────────────────────────

const EMPTY_FORM: ItemPayload = {
  name: '', kind: 'expense', category_id: null, provider_id: null, node_uuid: null,
  currency: 'RUB', amount: 0, billing_cycle: 'monthly', cycle_days: 30,
  next_due_at: null, url: null, notes: null,
}

function ItemsTab({ canCreate, canEdit, canDelete, prefillProvider, onPrefillConsumed }: {
  canCreate: boolean; canEdit: boolean; canDelete: boolean
  prefillProvider?: number | null; onPrefillConsumed?: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [kindFilter, setKindFilter] = useState<string>('all')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FinanceItem | null>(null)
  const [form, setForm] = useState<ItemPayload>(EMPTY_FORM)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [catsOpen, setCatsOpen] = useState(false)

  // «Добавить сервер» из карточки хостера: открыть диалог с выбранным провайдером
  useEffect(() => {
    if (prefillProvider != null) {
      setEditing(null)
      setForm({ ...EMPTY_FORM, provider_id: prefillProvider })
      setDialogOpen(true)
      onPrefillConsumed?.()
    }
  }, [prefillProvider, onPrefillConsumed])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-items', kindFilter],
    queryFn: () => financeApi.listItems(kindFilter === 'all' ? {} : { kind: kindFilter }),
    staleTime: 30_000,
  })
  const { data: cats } = useQuery({ queryKey: ['finance-cats'], queryFn: financeApi.listCategories, staleTime: 300_000 })
  const { data: provs } = useQuery({ queryKey: ['finance-provs'], queryFn: financeApi.listProviders, staleTime: 300_000 })
  const { data: nodesList } = useQuery({
    queryKey: ['nodes-brief'],
    queryFn: async () => {
      const { data } = await client.get('/nodes', { params: { per_page: 500 } })
      return (data.items || data) as { uuid: string; name: string }[]
    },
    staleTime: 300_000,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-summary'] })
    qc.invalidateQueries({ queryKey: ['finance-upcoming'] })
  }

  const saveMut = useMutation({
    mutationFn: (payload: ItemPayload) =>
      editing ? financeApi.updateItem(editing.id, payload) : financeApi.createItem(payload),
    onSuccess: () => { toast.success(t('common.saved')); setDialogOpen(false); invalidate() },
    onError: () => toast.error(t('common.saveError')),
  })
  const paidMut = useMutation({
    mutationFn: (id: number) => financeApi.markPaid(id),
    onSuccess: (it) => { toast.success(t('finance.markedPaid', { next: it.next_due_at || '—' })); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const skipMut = useMutation({
    mutationFn: (id: number) => financeApi.skipCycle(id),
    onSuccess: () => { toast.success(t('finance.cycleSkipped')); invalidate() },
  })
  const delMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteItem(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteId(null); invalidate() },
  })

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setDialogOpen(true) }
  const openEdit = (it: FinanceItem) => {
    setEditing(it)
    setForm({
      name: it.name, kind: it.kind, category_id: it.category_id, provider_id: it.provider_id,
      node_uuid: it.node_uuid, currency: it.currency, amount: it.amount,
      billing_cycle: it.billing_cycle, cycle_days: it.cycle_days ?? 30,
      next_due_at: it.next_due_at, url: it.url, notes: it.notes,
    })
    setDialogOpen(true)
  }

  const kindCats = (cats?.items || []).filter((c) => c.kind === form.kind)

  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-1">
          {['all', 'expense', 'income'].map((k) => (
            <Button
              key={k} size="sm" variant={kindFilter === k ? 'default' : 'outline'}
              className="h-8 text-xs" onClick={() => setKindFilter(k)}
            >
              {t(`finance.kind.${k}`)}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {(canCreate || canEdit || canDelete) && (
            <Button size="sm" variant="outline" onClick={() => setCatsOpen(true)} className="gap-1.5" title={t('finance.cat.title')}>
              <Tag className="w-4 h-4" /> <span className="hidden sm:inline">{t('finance.cat.manage')}</span>
            </Button>
          )}
          {canCreate && (
            <Button size="sm" onClick={openCreate} className="gap-1.5">
              <Plus className="w-4 h-4" /> {t('finance.addItem')}
            </Button>
          )}
        </div>
      </div>

      <CategoriesDialog open={catsOpen} onOpenChange={setCatsOpen} canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} />

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : !data?.items.length ? (
        <EmptyState icon={Wallet} title={t('finance.noItems')} description={t('finance.noItemsHint')} />
      ) : (
        <div className="space-y-1.5">
          {data.items.map((it) => (
            <Card key={it.id} className="hover:bg-[var(--glass-bg-hover)]/30 transition-colors">
              <CardContent className="py-3 flex items-center gap-3 flex-wrap">
                <span className="text-lg" title={it.category_name || ''}>{it.category_icon || (it.kind === 'income' ? '💰' : '📦')}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white truncate">{it.name}</span>
                    {it.kind === 'income' && <Badge className="bg-green-500/20 text-green-300 text-[10px]">{t('finance.kind.income')}</Badge>}
                    {it.status === 'archived' && <Badge variant="outline" className="text-[10px]">{t('finance.archived')}</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
                    {it.provider_name && <span>{it.provider_name}</span>}
                    {it.node_name && <span>· {it.node_name}</span>}
                    <span>· {t(`finance.cycle.${it.billing_cycle}`)}</span>
                    {it.next_due_at && it.billing_cycle !== 'once' && (
                      <span className={cn(it.is_overdue && 'text-red-400')}>· {t('finance.due')}: {it.next_due_at}</span>
                    )}
                  </div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-sm font-mono text-white">{fmtMoney(it.amount, it.currency)}</div>
                  {it.billing_cycle !== 'monthly' && it.billing_cycle !== 'once' && (
                    <div className="text-[11px] text-muted-foreground">≈ {fmtMoney(it.monthly_equivalent, it.currency)}/{t('finance.moShort')}</div>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {canEdit && it.status === 'active' && it.billing_cycle !== 'once' && (
                    <Button size="sm" variant="ghost" className="h-8 gap-1 text-green-400 hover:text-green-300"
                      onClick={() => paidMut.mutate(it.id)} disabled={paidMut.isPending}>
                      <Check className="w-4 h-4" /> <span className="hidden sm:inline">{t('finance.paid')}</span>
                    </Button>
                  )}
                  {canEdit && it.status === 'active' && it.billing_cycle !== 'once' && (
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-muted-foreground"
                      onClick={() => skipMut.mutate(it.id)} disabled={skipMut.isPending} title={t('finance.skip')}>
                      ⏭
                    </Button>
                  )}
                  {canEdit && (
                    <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => openEdit(it)}>
                      {t('common.edit')}
                    </Button>
                  )}
                  {canDelete && (
                    <Button size="sm" variant="ghost" className="h-8 px-2 text-red-400 hover:text-red-300"
                      onClick={() => setDeleteId(it.id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Item dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t('finance.editItem') : t('finance.addItem')}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>{t('finance.field.name')}</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>{t('finance.field.kind')}</Label>
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v, category_id: null })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="expense">{t('finance.kind.expense')}</SelectItem>
                  <SelectItem value="income">{t('finance.kind.income')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('finance.field.category')}</Label>
              <Select value={form.category_id ? String(form.category_id) : 'none'}
                onValueChange={(v) => setForm({ ...form, category_id: v === 'none' ? null : Number(v) })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {kindCats.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.icon} {c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('finance.field.amount')}</Label>
              <Input type="number" step="0.01" value={form.amount}
                onChange={(e) => setForm({ ...form, amount: Number(e.target.value) })} />
            </div>
            <div>
              <Label>{t('finance.field.currency')}</Label>
              <CurrencySelect value={form.currency} onChange={(v) => setForm({ ...form, currency: v })} />
            </div>
            <div>
              <Label>{t('finance.field.cycle')}</Label>
              <Select value={form.billing_cycle} onValueChange={(v) => setForm({ ...form, billing_cycle: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CYCLES.map((c) => <SelectItem key={c} value={c}>{t(`finance.cycle.${c}`)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {form.billing_cycle === 'days' && (
              <div>
                <Label>{t('finance.field.cycleDays')}</Label>
                <Input type="number" value={form.cycle_days ?? 30}
                  onChange={(e) => setForm({ ...form, cycle_days: Number(e.target.value) })} />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('finance.field.provider')}</Label>
                <Select value={form.provider_id ? String(form.provider_id) : 'none'}
                  onValueChange={(v) => setForm({ ...form, provider_id: v === 'none' ? null : Number(v) })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t('finance.field.noProvider')}</SelectItem>
                    {(provs?.items || []).map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{t('finance.field.node')}</Label>
                <Select value={form.node_uuid || 'none'}
                  onValueChange={(v) => setForm({ ...form, node_uuid: v === 'none' ? null : v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t('finance.field.noNode')}</SelectItem>
                    {(nodesList || []).map((n) => <SelectItem key={n.uuid} value={n.uuid}>{n.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>{form.billing_cycle === 'once' ? t('finance.field.paymentDate') : t('finance.field.nextDue')}</Label>
              <Input type="date" value={form.next_due_at || ''}
                onChange={(e) => setForm({ ...form, next_due_at: e.target.value || null })} />
            </div>
            <div className="col-span-2">
              <Label>{t('finance.field.url')}</Label>
              <Input value={form.url || ''} placeholder="https://" onChange={(e) => setForm({ ...form, url: e.target.value || null })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => saveMut.mutate(form)} disabled={!form.name.trim() || saveMut.isPending}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(o) => !o && setDeleteId(null)}
        title={t('finance.deleteItemTitle')}
        description={t('finance.deleteItemDesc')}
        variant="destructive"
        onConfirm={() => deleteId && delMut.mutate(deleteId)}
      />
    </div>
  )
}

// ── Categories dialog ────────────────────────────────────────────

// Добавить / переименовать / удалить категории расходов и доходов.
// Системные категории можно переименовать, но не удалить (защита на бэке).
function CategoriesDialog({ open, onOpenChange, canCreate, canEdit, canDelete }: {
  open: boolean; onOpenChange: (open: boolean) => void
  canCreate: boolean; canEdit: boolean; canDelete: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['finance-cats'], queryFn: financeApi.listCategories, staleTime: 300_000, enabled: open })
  const [newName, setNewName] = useState<Record<string, string>>({ expense: '', income: '' })
  const [newIcon, setNewIcon] = useState<Record<string, string>>({ expense: '', income: '' })
  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [deleteId, setDeleteId] = useState<number | null>(null)

  // категории видны в записях, сводке и структуре расходов
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-cats'] })
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-summary'] })
  }
  const onError = (e: any) =>
    toast.error(e?.response?.status === 409 ? t('finance.cat.exists') : (e?.response?.data?.detail || t('common.error')))

  const createMut = useMutation({
    mutationFn: (kind: string) => financeApi.createCategory({
      kind, name: newName[kind].trim(), icon: newIcon[kind].trim() || undefined,
    }),
    onSuccess: (_c, kind) => {
      toast.success(t('common.saved'))
      setNewName((prev) => ({ ...prev, [kind]: '' }))
      setNewIcon((prev) => ({ ...prev, [kind]: '' }))
      invalidate()
    },
    onError,
  })
  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => financeApi.updateCategory(id, { name }),
    onSuccess: () => { toast.success(t('common.saved')); setEditId(null); invalidate() },
    onError,
  })
  const delMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteCategory(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteId(null); invalidate() },
    onError,
  })

  const startRename = (id: number, name: string) => { setEditId(id); setEditName(name) }
  const submitRename = (id: number) => {
    const name = editName.trim()
    if (name) renameMut.mutate({ id, name })
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{t('finance.cat.title')}</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">{t('finance.cat.hint')}</p>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
            {(['expense', 'income'] as const).map((kind) => {
              const list = (data?.items || []).filter((c) => c.kind === kind)
              return (
                <div key={kind} className="space-y-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{t(`finance.kind.${kind}`)}</div>
                  {!list.length && <div className="text-xs text-muted-foreground">{t('finance.cat.empty')}</div>}
                  {list.map((c) => (
                    <div key={c.id} className="flex items-center gap-2 rounded-md border border-white/5 px-2 py-1.5">
                      <span className="text-base w-6 text-center shrink-0">{c.icon || (kind === 'income' ? '💰' : '📦')}</span>
                      {editId === c.id ? (
                        <Input
                          autoFocus value={editName} className="h-8 text-sm"
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') submitRename(c.id)
                            if (e.key === 'Escape') setEditId(null)
                          }}
                        />
                      ) : (
                        <span className="text-sm text-white truncate">{c.name}</span>
                      )}
                      {c.is_system && <Badge variant="outline" className="text-[10px] shrink-0">{t('finance.cat.system')}</Badge>}
                      <div className="ml-auto flex items-center gap-1 shrink-0">
                        {editId === c.id ? (
                          <>
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-green-400 hover:text-green-300"
                              disabled={!editName.trim() || renameMut.isPending} onClick={() => submitRename(c.id)} title={t('common.save')}>
                              <Check className="w-4 h-4" />
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setEditId(null)}>
                              {t('common.cancel')}
                            </Button>
                          </>
                        ) : (
                          <>
                            {canEdit && (
                              <Button size="sm" variant="ghost" className="h-7 px-2" title={t('finance.cat.rename')} onClick={() => startRename(c.id, c.name)}>
                                <Pencil className="w-4 h-4" />
                              </Button>
                            )}
                            {canDelete && (
                              <Button size="sm" variant="ghost" className="h-7 px-2 text-red-400 hover:text-red-300 disabled:opacity-40"
                                disabled={c.is_system} title={c.is_system ? t('finance.cat.systemHint') : t('common.delete')}
                                onClick={() => setDeleteId(c.id)}>
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                  {canCreate && (
                    <div className="flex items-center gap-2">
                      <Input
                        value={newIcon[kind]} placeholder={t('finance.cat.iconPh')} className="h-8 w-20 text-center text-sm" maxLength={4}
                        onChange={(e) => setNewIcon({ ...newIcon, [kind]: e.target.value })}
                      />
                      <Input
                        value={newName[kind]} placeholder={t('finance.cat.namePh')} className="h-8 text-sm"
                        onChange={(e) => setNewName({ ...newName, [kind]: e.target.value })}
                        onKeyDown={(e) => { if (e.key === 'Enter' && newName[kind].trim()) createMut.mutate(kind) }}
                      />
                      <Button size="sm" variant="outline" className="h-8 gap-1 shrink-0"
                        disabled={!newName[kind].trim() || createMut.isPending} onClick={() => createMut.mutate(kind)}>
                        <Plus className="w-4 h-4" />{t('common.add')}
                      </Button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>{t('common.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={deleteId != null}
        onOpenChange={(o) => !o && setDeleteId(null)}
        title={t('finance.cat.deleteTitle')}
        description={t('finance.cat.deleteDesc')}
        variant="destructive"
        confirmLabel={t('common.delete')}
        onConfirm={() => deleteId != null && delMut.mutate(deleteId)}
      />
    </>
  )
}

// ── Payments tab ─────────────────────────────────────────────────

// Пресеты периода операций: ключ → (since, until) в ISO-датах
function paymentsRange(preset: string, from: string, to: string): { since?: string; until?: string } {
  const today = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  const startOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1)
  switch (preset) {
    case 'thisMonth':
      return { since: iso(startOfMonth(today)) }
    case 'prevMonth': {
      const prev = new Date(today.getFullYear(), today.getMonth() - 1, 1)
      return { since: iso(prev), until: iso(new Date(today.getFullYear(), today.getMonth(), 0)) }
    }
    case '90d': {
      const d = new Date(today); d.setDate(d.getDate() - 90)
      return { since: iso(d) }
    }
    case 'custom':
      return { ...(from ? { since: from } : {}), ...(to ? { until: to } : {}) }
    default:
      return {}
  }
}

const EMPTY_PAYMENT = { kind: 'expense', item_name: '', amount: '', currency: 'RUB', paid_at: '', comment: '' }

function PaymentsTab({ canCreate, canEdit, canDelete }: { canCreate: boolean; canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [preset, setPreset] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FinancePayment | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [pf, setPf] = useState({ ...EMPTY_PAYMENT })

  const range = useMemo(() => paymentsRange(preset, from, to), [preset, from, to])
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-payments', range.since ?? '', range.until ?? ''],
    queryFn: () => financeApi.listPayments({ limit: 500, ...range }),
    staleTime: 30_000,
  })
  const delMut = useMutation({
    mutationFn: (id: number) => financeApi.deletePayment(id),
    onSuccess: () => {
      toast.success(t('common.deleted')); setDeleteId(null)
      qc.invalidateQueries({ queryKey: ['finance-payments'] }); qc.invalidateQueries({ queryKey: ['finance-summary'] })
    },
    onError: () => toast.error(t('common.error')),
  })
  // Один диалог на добавление и правку: editing — какую операцию правим
  const saveMut = useMutation({
    mutationFn: async () => {
      const base = {
        kind: pf.kind as 'expense' | 'income',
        amount: parseFloat(pf.amount),
        currency: pf.currency.trim().toUpperCase() || 'RUB',
        paid_at: pf.paid_at,
        item_name: pf.item_name.trim() || undefined,
      }
      if (editing) {
        // пустой комментарий при правке очищает его, пустое название оставляет прежнее
        await financeApi.updatePayment(editing.id, { ...base, comment: pf.comment.trim() || null })
        return
      }
      await financeApi.createPayment({ ...base, comment: pf.comment.trim() || undefined })
    },
    onSuccess: () => {
      toast.success(editing ? t('finance.paymentUpdated') : t('finance.paymentAdded'))
      setDialogOpen(false); setEditing(null); setPf({ ...EMPTY_PAYMENT })
      qc.invalidateQueries({ queryKey: ['finance-payments'] })
      qc.invalidateQueries({ queryKey: ['finance-summary'] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })
  const pfValid = pf.paid_at && parseFloat(pf.amount) > 0
  const openAdd = () => { setEditing(null); setPf({ ...EMPTY_PAYMENT }); setDialogOpen(true) }
  const openEdit = (p: FinancePayment) => {
    setEditing(p)
    setPf({ kind: p.kind, item_name: p.item_name, amount: String(p.amount), currency: p.currency, paid_at: p.paid_at, comment: p.comment || '' })
    setDialogOpen(true)
  }

  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-3">
      {/* Период + добавление операции (в т.ч. задним числом) */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-44 h-9"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('finance.range.all')}</SelectItem>
            <SelectItem value="thisMonth">{t('finance.range.thisMonth')}</SelectItem>
            <SelectItem value="prevMonth">{t('finance.range.prevMonth')}</SelectItem>
            <SelectItem value="90d">{t('finance.range.last90')}</SelectItem>
            <SelectItem value="custom">{t('finance.range.custom')}</SelectItem>
          </SelectContent>
        </Select>
        {preset === 'custom' && (
          <>
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40 h-9" aria-label={t('finance.range.from')} />
            <span className="text-muted-foreground text-sm">—</span>
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40 h-9" aria-label={t('finance.range.to')} />
          </>
        )}
        {canCreate && (
          <Button size="sm" className="ml-auto gap-1.5" onClick={openAdd}>
            <Plus className="w-4 h-4" />{t('finance.addPayment')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : !data?.items.length ? (
        <EmptyState icon={Wallet} title={t('finance.noPayments')} />
      ) : (
      <div className="space-y-1.5">
      {data.items.map((p) => (
        <Card key={p.id}>
          <CardContent className="py-2.5 flex items-center gap-3">
            <span className={cn('w-1.5 h-8 rounded-full', p.kind === 'income' ? 'bg-green-500' : 'bg-red-500')} />
            <div className="min-w-0">
              <div className="text-sm text-white truncate">{p.item_name}</div>
              <div className="text-xs text-muted-foreground">{p.paid_at}{p.comment ? ` · ${p.comment}` : ''}{p.source !== 'manual' ? ` · ${p.source}` : ''}</div>
            </div>
            <div className="ml-auto text-right">
              <div className={cn('text-sm font-mono', p.kind === 'income' ? 'text-green-400' : 'text-red-400')}>
                {p.kind === 'income' ? '+' : '−'}{fmtMoney(p.amount, p.currency)}
              </div>
              {p.currency !== 'RUB' && <div className="text-[11px] text-muted-foreground">≈ {fmtMoney(p.amount_rub, 'RUB')}</div>}
            </div>
            {canEdit && (
              <Button size="sm" variant="ghost" className="h-8 px-2" title={t('common.edit')} onClick={() => openEdit(p)}>
                <Pencil className="w-4 h-4" />
              </Button>
            )}
            {canDelete && (
              <Button size="sm" variant="ghost" className="h-8 px-2 text-red-400 hover:text-red-300" title={t('common.delete')} onClick={() => setDeleteId(p.id)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
      </div>
      )}

      {/* Диалог: ручная операция произвольной датой (в т.ч. старая) или правка существующей */}
      <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditing(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editing ? t('finance.editPayment') : t('finance.addPayment')}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>{t('finance.field.kind')}</Label>
                <Select value={pf.kind} onValueChange={(v) => setPf({ ...pf, kind: v })}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="expense">{t('finance.kind.expense')}</SelectItem>
                    <SelectItem value="income">{t('finance.kind.income')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{t('finance.field.paymentDate')}</Label>
                <Input type="date" value={pf.paid_at} onChange={(e) => setPf({ ...pf, paid_at: e.target.value })} className="h-9" />
              </div>
            </div>
            <div>
              <Label>{t('finance.field.name')}</Label>
              <Input value={pf.item_name} placeholder={t('finance.paymentNamePh')}
                onChange={(e) => setPf({ ...pf, item_name: e.target.value })} className="h-9" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>{t('finance.field.amount')}</Label>
                <Input type="number" min="0" step="0.01" value={pf.amount}
                  onChange={(e) => setPf({ ...pf, amount: e.target.value })} className="h-9" />
              </div>
              <div>
                <Label>{t('finance.field.currency')}</Label>
                <Input value={pf.currency} onChange={(e) => setPf({ ...pf, currency: e.target.value })} className="h-9 font-mono" />
              </div>
            </div>
            <div>
              <Label>{t('finance.field.comment')}</Label>
              <Input value={pf.comment} onChange={(e) => setPf({ ...pf, comment: e.target.value })} className="h-9" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button disabled={!pfValid || saveMut.isPending} onClick={() => saveMut.mutate()}>
              {saveMut.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId != null}
        onOpenChange={(o) => !o && setDeleteId(null)}
        title={t('finance.deletePaymentTitle')}
        description={t('finance.deletePaymentDesc')}
        variant="destructive"
        confirmLabel={t('common.delete')}
        onConfirm={() => deleteId != null && delMut.mutate(deleteId)}
      />
    </div>
  )
}

// ── Rates tab ────────────────────────────────────────────────────

function RatesTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['finance-rates'], queryFn: financeApi.listRates, staleTime: 300_000 })
  const refreshMut = useMutation({
    mutationFn: financeApi.refreshRates,
    onSuccess: (r) => { toast.success(t('finance.ratesUpdated', { count: r.updated })); qc.invalidateQueries({ queryKey: ['finance-rates'] }) },
    onError: () => toast.error(t('common.error')),
  })
  const [edits, setEdits] = useState<Record<string, string>>({})
  const clearEdit = (cur: string) => setEdits((prev) => { const next = { ...prev }; delete next[cur]; return next })
  const setMut = useMutation({
    mutationFn: ({ cur, rate }: { cur: string; rate: number }) => financeApi.setRate(cur, rate),
    onSuccess: (_r, { cur }) => { toast.success(t('common.saved')); clearEdit(cur); qc.invalidateQueries({ queryKey: ['finance-rates'] }) },
    onError: () => toast.error(t('common.error')),
  })
  // Возврат на авто: снимаем ручной флаг и сразу тянем курс из источника
  const autoMut = useMutation({
    mutationFn: (cur: string) => financeApi.resetRateToAuto(cur),
    onSuccess: (r, cur) => {
      if (r.updated > 0) toast.success(t('finance.rateAutoRestored', { currency: cur }))
      else toast.warning(t('finance.rateAutoNotFetched', { currency: cur }))
      clearEdit(cur)
      qc.invalidateQueries({ queryKey: ['finance-rates'] })
    },
    onError: () => toast.error(t('common.error')),
  })

  if (isLoading) return <Skeleton className="h-40 w-full" />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t('finance.ratesHint')}</p>
        {canEdit && (
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}>
            <RefreshCw className={cn('w-4 h-4', refreshMut.isPending && 'animate-spin')} /> {t('finance.refreshRates')}
          </Button>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {(data?.items || []).filter((r) => r.currency !== 'RUB').map((r) => (
          <Card key={r.currency}>
            <CardContent className="py-3 flex items-center gap-3">
              <span className="font-mono text-white w-12">{r.currency}</span>
              <span className="text-xs text-muted-foreground">→ RUB</span>
              {canEdit ? (
                <Input
                  className="h-8 w-28 ml-auto text-sm"
                  value={edits[r.currency] ?? String(r.rate_rub)}
                  onChange={(e) => setEdits({ ...edits, [r.currency]: e.target.value })}
                  onBlur={(e) => {
                    const v = Number(e.target.value)
                    if (v > 0 && v !== r.rate_rub) setMut.mutate({ cur: r.currency, rate: v })
                    else clearEdit(r.currency)
                  }}
                />
              ) : (
                <span className="ml-auto font-mono text-white">{r.rate_rub}</span>
              )}
              {r.is_manual && <Badge variant="outline" className="text-[10px]">{t('finance.manual')}</Badge>}
              {r.is_manual && canEdit && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 px-2 text-xs"
                  title={t('finance.resetToAutoHint')}
                  onClick={() => autoMut.mutate(r.currency)}
                  disabled={autoMut.isPending}
                >
                  <RotateCcw className={cn('w-3.5 h-3.5', autoMut.isPending && autoMut.variables === r.currency && 'animate-spin')} />
                  {t('finance.resetToAuto')}
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ── Hosters tab (провайдеры + API-подключения) ───────────────────

const EMPTY_ACCOUNT_FORM = {
  adapter: '', base_url: '', credentials: {} as Record<string, string>,
  auto_sync: true, low_balance_threshold: '' as string,
}

function HostersTab({ canCreate, canEdit, canDelete, onAddItem }: {
  canCreate: boolean; canEdit: boolean; canDelete: boolean
  onAddItem: (providerId: number) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: provs, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-provs'], queryFn: financeApi.listProviders, staleTime: 300_000,
  })
  const { data: accounts } = useQuery({
    queryKey: ['finance-accounts'], queryFn: financeApi.listAccounts, staleTime: 60_000,
  })
  const { data: adapters } = useQuery({
    queryKey: ['finance-adapters'], queryFn: financeApi.listAdapters, staleTime: 600_000,
  })
  const { data: allItems } = useQuery({
    queryKey: ['finance-items', 'all'],
    queryFn: () => financeApi.listItems(),
    staleTime: 30_000,
  })

  const accountByProvider = useMemo(() => {
    const m = new Map<number, FinanceAccount>()
    for (const a of accounts?.items || []) m.set(a.provider_id, a)
    return m
  }, [accounts])

  // Записи по провайдерам — «сервера», заведённые вручную (хостеры без API)
  const itemsByProvider = useMemo(() => {
    const m = new Map<number, FinanceItem[]>()
    for (const it of allItems?.items || []) {
      if (it.provider_id == null || it.status !== 'active') continue
      const arr = m.get(it.provider_id) || []
      arr.push(it)
      m.set(it.provider_id, arr)
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => (a.next_due_at || '9999').localeCompare(b.next_due_at || '9999'))
    }
    return m
  }, [allItems])

  const [dialogProvider, setDialogProvider] = useState<FinanceProvider | null>(null)
  const [form, setForm] = useState(EMPTY_ACCOUNT_FORM)
  const [testResult, setTestResult] = useState<AccountTestResult | null>(null)
  const [deleteAccountId, setDeleteAccountId] = useState<number | null>(null)
  const [deleteProviderId, setDeleteProviderId] = useState<number | null>(null)
  const [deleteItemId, setDeleteItemId] = useState<number | null>(null)
  // ручное создание/редактирование хостера (не все хостеры заведены в панели)
  const [provForm, setProvForm] = useState<{ id: number | null; name: string; url: string } | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toggleExpand = (id: number) => setExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const fmtPeriod = (period: string) => {
    if (period === 'monthly') return t('finance.period.monthly')
    if (period === 'yearly') return t('finance.period.yearly')
    if (period === 'once') return t('finance.period.once')
    const d = /^days:(\d+)$/.exec(period)
    if (d) return t('finance.period.days', { count: Number(d[1]) })
    const m = /^months:(\d+)$/.exec(period)
    if (m) return t('finance.period.months', { count: Number(m[1]) })
    return period
  }
  const editingAccount = dialogProvider ? accountByProvider.get(dialogProvider.id) : undefined
  const selectedAdapter = (adapters?.items || []).find((a) => a.slug === form.adapter)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-accounts'] })
    qc.invalidateQueries({ queryKey: ['finance-snapshots'] })
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-upcoming'] })
    qc.invalidateQueries({ queryKey: ['finance-provs'] })
    qc.invalidateQueries({ queryKey: ['finance-summary'] })
  }

  const openDialog = (p: FinanceProvider) => {
    const acc = accountByProvider.get(p.id)
    setTestResult(null)
    setForm(acc ? {
      adapter: acc.adapter, base_url: acc.base_url || '', credentials: {},
      auto_sync: acc.auto_sync,
      low_balance_threshold: acc.low_balance_threshold != null ? String(acc.low_balance_threshold) : '',
    } : { ...EMPTY_ACCOUNT_FORM, base_url: p.url || '' })
    setDialogProvider(p)
  }

  const hasCreds = Object.values(form.credentials).some((v) => v.trim())
  const threshold = form.low_balance_threshold.trim() ? Number(form.low_balance_threshold) : null

  const saveMut = useMutation({
    mutationFn: () => {
      // base_url нужен только адаптерам с needs_base_url (self-hosted биллинги
      // типа BILLmanager); для Hostkey и подобных эндпоинт фиксирован — не шлём
      // адрес провайдера, иначе синк уйдёт не туда
      const base_url = selectedAdapter?.needs_base_url ? (form.base_url || null) : null
      if (editingAccount && !hasCreds) {
        return financeApi.updateAccount(editingAccount.id, {
          base_url, auto_sync: form.auto_sync, low_balance_threshold: threshold,
        })
      }
      return financeApi.createAccount({
        provider_id: dialogProvider!.id, adapter: form.adapter, base_url,
        credentials: form.credentials, auto_sync: form.auto_sync, low_balance_threshold: threshold,
      })
    },
    onSuccess: () => { toast.success(t('common.saved')); setDialogProvider(null); invalidate() },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.saveError')),
  })

  const testMut = useMutation({
    mutationFn: () => financeApi.testAccount(
      hasCreds || !editingAccount
        ? { adapter: form.adapter, base_url: form.base_url || null, credentials: form.credentials }
        : { account_id: editingAccount.id },
    ),
    onSuccess: (r) => setTestResult(r),
    onError: () => setTestResult({ status: 'error', error: t('common.error') }),
  })

  const syncMut = useMutation({
    mutationFn: (id: number) => financeApi.syncAccount(id),
    onSuccess: (r) => {
      if (r.status === 'ok') {
        toast.success(t('finance.syncDone', {
          balance: r.balance != null ? fmtMoney(r.balance, r.currency || '') : '—',
          services: r.services ?? 0,
        }))
      } else {
        toast.error(t('finance.syncError', { error: r.error || '' }))
      }
      invalidate()
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteAccount(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteAccountId(null); setDialogProvider(null); invalidate() },
  })

  const archiveProvMut = useMutation({
    mutationFn: (id: number) => financeApi.updateProvider(id, { archived: true }),
    onSuccess: (r) => {
      toast.success(t('finance.archive.providerArchived', { count: r.archived_items || 0 }))
      invalidate()
    },
    onError: () => toast.error(t('common.error')),
  })
  const deleteProvMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteProvider(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteProviderId(null); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const archiveItemMut = useMutation({
    mutationFn: (id: number) => financeApi.updateItem(id, { status: 'archived' }),
    onSuccess: () => { toast.success(t('finance.archive.itemArchived')); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const deleteItemMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteItem(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteItemId(null); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const saveProvMut = useMutation({
    mutationFn: async () => {
      const data = { name: provForm!.name.trim(), url: provForm!.url.trim() || undefined }
      if (provForm!.id != null) await financeApi.updateProvider(provForm!.id, data)
      else await financeApi.createProvider(data)
    },
    onSuccess: () => { toast.success(t('common.saved')); setProvForm(null); invalidate() },
    onError: () => toast.error(t('common.saveError')),
  })

  const visibleProvs = (provs?.items || []).filter((p) => !p.archived)

  const providerDialog = () => (
    <Dialog open={provForm !== null} onOpenChange={(o) => !o && setProvForm(null)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {provForm?.id != null ? t('finance.hoster.editProvider') : t('finance.hoster.addProvider')}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>{t('finance.field.name')}</Label>
            <Input value={provForm?.name || ''} placeholder="Hetzner / Aeza / …"
              onChange={(e) => provForm && setProvForm({ ...provForm, name: e.target.value })} />
          </div>
          <div>
            <Label>{t('finance.hoster.providerUrl')}</Label>
            <Input value={provForm?.url || ''} placeholder="https://my.hoster.com"
              onChange={(e) => provForm && setProvForm({ ...provForm, url: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button disabled={!provForm?.name.trim() || saveProvMut.isPending} onClick={() => saveProvMut.mutate()}>
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )

  const addProviderBtn = canCreate && (
    <Button size="sm" variant="outline" className="gap-1.5 shrink-0"
      onClick={() => setProvForm({ id: null, name: '', url: '' })}>
      <Plus className="w-4 h-4" /> {t('finance.hoster.addProvider')}
    </Button>
  )

  if (isError) return <QueryError onRetry={refetch} />
  if (isLoading) return <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
  if (!visibleProvs.length) {
    return (
      <>
        <EmptyState icon={Server} title={t('finance.noProviders')} description={t('finance.noProvidersHint')}
          action={addProviderBtn || undefined} />
        {providerDialog()}
      </>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm text-muted-foreground">{t('finance.hostersHint')}</p>
        {addProviderBtn}
      </div>
      <div className="space-y-1.5">
        {visibleProvs.map((p) => {
          const acc = accountByProvider.get(p.id)
          const low = acc?.balance != null && acc.low_balance_threshold != null && acc.balance < acc.low_balance_threshold
          const services = acc?.services || []
          const hasServices = services.length > 0
          const provItems = itemsByProvider.get(p.id) || []
          const canExpand = hasServices || provItems.length > 0 || canCreate
          const isOpen = expanded.has(p.id)
          const sortedServices = [...services].sort((a, b) => {
            if (!a.next_due_at) return 1
            if (!b.next_due_at) return -1
            return a.next_due_at.localeCompare(b.next_due_at)
          })
          // API-услуга и запись про один сервер — объединяем в одну строку
          // (данные из API + кнопки записи). Матч: (1) одна нода;
          // (2) уникальная цена внутри провайдера (1 услуга ↔ 1 запись).
          const itemByNode = new Map<string, FinanceItem>()
          for (const it of provItems) {
            if (it.node_uuid && !itemByNode.has(it.node_uuid)) itemByNode.set(it.node_uuid, it)
          }
          const mergedItemIds = new Set<number>()
          const svcRows: { s: FinanceService; linked?: FinanceItem }[] = sortedServices.map((s) => {
            const linked = s.node_uuid ? itemByNode.get(s.node_uuid) : undefined
            if (linked) mergedItemIds.add(linked.id)
            return { s, linked }
          })
          const itemsByPrice = new Map<number, FinanceItem[]>()
          for (const it of provItems) {
            if (mergedItemIds.has(it.id) || !(it.amount > 0)) continue
            const arr = itemsByPrice.get(it.amount) || []
            arr.push(it)
            itemsByPrice.set(it.amount, arr)
          }
          const svcPriceCount = new Map<number, number>()
          for (const r of svcRows) {
            if (!r.linked && r.s.price != null) svcPriceCount.set(r.s.price, (svcPriceCount.get(r.s.price) || 0) + 1)
          }
          for (const r of svcRows) {
            if (r.linked || r.s.price == null) continue
            const cands = itemsByPrice.get(r.s.price) || []
            if (cands.length === 1 && svcPriceCount.get(r.s.price) === 1) {
              r.linked = cands[0]
              mergedItemIds.add(cands[0].id)
            }
          }
          const standaloneItems = provItems.filter((it) => !mergedItemIds.has(it.id))
          return (
            <Card key={p.id}>
              <CardContent className="py-3">
                {/* хедер целиком раскрывает карточку — шеврон 20px слишком мелкая цель на мобиле */}
                <div className={cn('flex items-center gap-2.5 sm:gap-3', canExpand && 'cursor-pointer select-none')}
                  onClick={() => canExpand && toggleExpand(p.id)}>
                  {canExpand ? (
                    <button type="button" onClick={(e) => { e.stopPropagation(); toggleExpand(p.id) }}
                      className="shrink-0 text-primary-400 hover:text-primary-300 transition-colors"
                      aria-expanded={isOpen}
                      title={t(isOpen ? 'finance.hoster.hideServices' : 'finance.hoster.showServices')}>
                      <ChevronDown className={cn('w-5 h-5 transition-transform', isOpen && 'rotate-180')} />
                    </button>
                  ) : (
                    <Server className="w-5 h-5 text-primary-400 shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">{p.name}</span>
                      {acc && (
                        acc.last_sync_status === 'error' ? (
                          <Badge className="bg-red-500/20 text-red-300 text-[10px] shrink-0" title={acc.last_sync_error || ''}>
                            {t('finance.syncFailed')}
                          </Badge>
                        ) : (
                          <Badge className="bg-green-500/20 text-green-300 text-[10px] shrink-0">API</Badge>
                        )
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {p.url && <a href={p.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="hover:text-primary-400">{p.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')}</a>}
                      {p.url ? ' · ' : ''}{t('finance.itemsCount', { count: p.items_count || 0 })}
                      {hasServices && <span>{' · '}{t('finance.hoster.servicesCount', { count: services.length })}</span>}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    {acc?.balance != null && (
                      <>
                        <div className={cn('text-sm font-mono font-bold', low ? 'text-red-400' : 'text-white')}>
                          {fmtMoney(acc.balance, acc.balance_currency || '')}
                        </div>
                        {low ? (
                          <div className="text-[11px] text-red-400">{t('finance.lowBalance')}</div>
                        ) : acc.last_sync_at && (
                          <div className="text-[10px] text-muted-foreground">
                            {t('finance.lastSync')} {acc.last_sync_at.slice(5, 16).replace('T', ' ')}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                    {acc && canEdit && (
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('finance.syncNow')} aria-label={t('finance.syncNow')}
                        onClick={() => syncMut.mutate(acc.id)} disabled={syncMut.isPending}>
                        <RefreshCw className={cn('w-4 h-4', syncMut.isPending && 'animate-spin')} />
                      </Button>
                    )}
                    {(acc ? canEdit : canCreate) && (
                      <Button size="sm" variant={acc ? 'ghost' : 'outline'} className={cn('h-8 gap-1.5', acc ? 'w-8 p-0' : 'px-2 sm:px-3')}
                        title={acc ? t('finance.editConnection', { name: p.name }) : t('finance.connectApi')}
                        aria-label={acc ? t('finance.editConnection', { name: p.name }) : t('finance.connectApi')}
                        onClick={() => openDialog(p)}>
                        {acc ? <Settings2 className="w-4 h-4" /> : <><Zap className="w-4 h-4" /><span className="hidden sm:inline">{t('finance.connectApi')}</span></>}
                      </Button>
                    )}
                    {(canEdit || canDelete) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('common.actions')} aria-label={t('common.actions')}>
                            <MoreVertical className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {canEdit && (
                            <DropdownMenuItem onClick={() => setProvForm({ id: p.id, name: p.name, url: p.url || '' })}>
                              <Pencil className="w-4 h-4 mr-2" /> {t('finance.hoster.editProvider')}
                            </DropdownMenuItem>
                          )}
                          {canEdit && (
                            <DropdownMenuItem onClick={() => archiveProvMut.mutate(p.id)}>
                              <Archive className="w-4 h-4 mr-2" /> {t('finance.archive.archiveProvider')}
                            </DropdownMenuItem>
                          )}
                          {canDelete && (
                            <DropdownMenuItem className="text-red-400 focus:text-red-300" onClick={() => setDeleteProviderId(p.id)}>
                              <Trash2 className="w-4 h-4 mr-2" /> {t('finance.archive.deleteProvider')}
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </div>
              </CardContent>
              {isOpen && (
                <div className="border-t border-white/5 max-h-96 overflow-y-auto">
                  {hasServices && standaloneItems.length > 0 && (
                    <div className="px-4 pt-2 text-[10px] uppercase tracking-wider text-muted-foreground">{t('finance.hoster.fromApi')}</div>
                  )}
                  <div className="divide-y divide-white/5">
                    {svcRows.map(({ s, linked }, i) => (
                      <div key={s.external_id || `${p.id}-${i}`} className="px-4 py-2.5 flex items-center gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-sm text-white truncate">{s.name}</span>
                            {s.node_name ? (
                              <Badge variant="outline" className="text-[10px] text-primary-300 shrink-0" title={t('finance.hoster.nodeBadge')}>
                                {s.node_name}
                              </Badge>
                            ) : linked && linked.name !== s.name ? (
                              // не нода панели (панель, бот, мост) — показываем имя связанной записи
                              <Badge variant="outline" className="text-[10px] text-muted-foreground shrink-0" title={t('finance.hoster.linkedItem', { name: linked.name })}>
                                {linked.name}
                              </Badge>
                            ) : null}
                          </div>
                          {s.specs && <div className="text-xs text-muted-foreground truncate">{s.specs}</div>}
                        </div>
                        <div className="text-right shrink-0">
                          <div>
                            {s.price != null ? (
                              <span className="text-sm font-mono text-white">{fmtMoney(s.price, s.currency || acc?.balance_currency || '')}</span>
                            ) : (
                              <span className="text-sm text-muted-foreground">—</span>
                            )}
                            {s.period && <span className="text-[10px] text-muted-foreground ml-1">{fmtPeriod(s.period)}</span>}
                          </div>
                          {s.next_due_at && (
                            <div className="text-[11px] text-muted-foreground">
                              {t('finance.hoster.renewsAt')} {s.next_due_at.slice(0, 10)}
                            </div>
                          )}
                        </div>
                        {linked && (canEdit || canDelete) && (
                          <div className="flex items-center gap-1 shrink-0 -mr-2" title={t('finance.hoster.linkedItem', { name: linked.name })}>
                            {canEdit && (
                              <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('finance.archive.itemArchive')} aria-label={t('finance.archive.itemArchive')}
                                onClick={() => archiveItemMut.mutate(linked.id)} disabled={archiveItemMut.isPending}>
                                <Archive className="w-3.5 h-3.5" />
                              </Button>
                            )}
                            {canDelete && (
                              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-400 hover:text-red-300" title={t('common.delete')} aria-label={t('common.delete')}
                                onClick={() => setDeleteItemId(linked.id)}>
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  {standaloneItems.length > 0 && (
                    <>
                      {hasServices && (
                        <div className="px-4 pt-2 text-[10px] uppercase tracking-wider text-muted-foreground border-t border-white/5">{t('finance.hoster.manualItems')}</div>
                      )}
                      <div className="divide-y divide-white/5">
                        {standaloneItems.map((it) => (
                          <div key={`it-${it.id}`} className="px-4 py-2.5 flex items-center gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className="text-sm text-white truncate">{it.name}</span>
                                {it.node_name && (
                                  <Badge variant="outline" className="text-[10px] text-primary-300 shrink-0" title={t('finance.hoster.nodeBadge')}>
                                    {it.node_name}
                                  </Badge>
                                )}
                              </div>
                              {it.notes && <div className="text-xs text-muted-foreground truncate">{it.notes}</div>}
                            </div>
                            <div className="text-right shrink-0">
                              <div>
                                <span className={cn('text-sm font-mono', it.kind === 'income' ? 'text-green-400' : 'text-white')}>
                                  {fmtMoney(it.amount, it.currency)}
                                </span>
                                <span className="text-[10px] text-muted-foreground ml-1">
                                  {fmtPeriod(it.billing_cycle === 'days' ? `days:${it.cycle_days || 30}` : it.billing_cycle)}
                                </span>
                              </div>
                              {it.next_due_at && (
                                <div className="text-[11px] text-muted-foreground">
                                  {t('finance.hoster.renewsAt')} {it.next_due_at.slice(0, 10)}
                                </div>
                              )}
                            </div>
                            {(canEdit || canDelete) && (
                              <div className="flex items-center gap-1 shrink-0 -mr-2">
                                {canEdit && (
                                  <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('finance.archive.itemArchive')} aria-label={t('finance.archive.itemArchive')}
                                    onClick={() => archiveItemMut.mutate(it.id)} disabled={archiveItemMut.isPending}>
                                    <Archive className="w-3.5 h-3.5" />
                                  </Button>
                                )}
                                {canDelete && (
                                  <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-400 hover:text-red-300" title={t('common.delete')} aria-label={t('common.delete')}
                                    onClick={() => setDeleteItemId(it.id)}>
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </Button>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  {canCreate && (
                    <button type="button"
                      className="w-full px-4 py-2.5 text-sm text-primary-400 hover:text-primary-300 hover:bg-white/[0.02] text-left flex items-center gap-2 border-t border-white/5"
                      onClick={() => onAddItem(p.id)}>
                      <Plus className="w-4 h-4" /> {t('finance.hoster.addServer')}
                    </button>
                  )}
                </div>
              )}
            </Card>
          )
        })}
      </div>

      {/* Диалог подключения/настройки API */}
      <Dialog open={dialogProvider !== null} onOpenChange={(o) => !o && setDialogProvider(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingAccount
                ? t('finance.editConnection', { name: dialogProvider?.name })
                : t('finance.connectApiTo', { name: dialogProvider?.name })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('finance.adapter')}</Label>
              <Select value={form.adapter || undefined}
                onValueChange={(v) => { setForm({ ...form, adapter: v, credentials: {} }); setTestResult(null) }}>
                <SelectTrigger><SelectValue placeholder={t('finance.selectAdapter')} /></SelectTrigger>
                <SelectContent>
                  {(adapters?.items || []).map((a) => (
                    <SelectItem key={a.slug} value={a.slug}>{a.title}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedAdapter?.description && (
                <p className="text-[11px] text-muted-foreground mt-1">{selectedAdapter.description}</p>
              )}
            </div>
            {selectedAdapter?.needs_base_url && (
              <div>
                <Label>{t('finance.baseUrl')}</Label>
                <Input value={form.base_url} placeholder="https://my.hoster.com/billmgr"
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
              </div>
            )}
            {(selectedAdapter?.fields || []).map((f) => (
              <div key={f.name}>
                <Label>{f.label}</Label>
                <Input
                  type={f.type === 'password' ? 'password' : 'text'}
                  value={form.credentials[f.name] || ''}
                  placeholder={editingAccount ? t('finance.credsKeepHint') : (f.placeholder || '')}
                  onChange={(e) => setForm({ ...form, credentials: { ...form.credentials, [f.name]: e.target.value } })}
                />
                {f.help && <p className="text-[11px] text-muted-foreground mt-1">{f.help}</p>}
              </div>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('finance.lowBalanceThreshold')}</Label>
                <Input type="number" step="0.01" value={form.low_balance_threshold}
                  placeholder={t('finance.noThreshold')}
                  onChange={(e) => setForm({ ...form, low_balance_threshold: e.target.value })} />
              </div>
              <div className="flex items-end pb-2">
                <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
                  <input type="checkbox" checked={form.auto_sync}
                    onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })} />
                  {t('finance.autoSync')}
                </label>
              </div>
            </div>
            {testResult && (
              <div className={cn(
                'text-sm px-3 py-2 rounded-lg border',
                testResult.status === 'ok'
                  ? 'bg-green-500/10 border-green-500/20 text-green-300'
                  : 'bg-red-500/10 border-red-500/20 text-red-300',
              )}>
                {testResult.status === 'ok'
                  ? t('finance.testOk', {
                      balance: testResult.balance != null ? fmtMoney(testResult.balance, testResult.currency || '') : '—',
                      services: testResult.services?.length ?? 0,
                    })
                  : testResult.error}
              </div>
            )}
          </div>
          <DialogFooter className="flex-wrap gap-2">
            {editingAccount && canDelete && (
              <Button variant="ghost" className="text-red-400 hover:text-red-300 mr-auto"
                onClick={() => setDeleteAccountId(editingAccount.id)}>
                <Trash2 className="w-4 h-4 mr-1" /> {t('finance.disconnect')}
              </Button>
            )}
            <Button variant="outline" disabled={!form.adapter || testMut.isPending || (!hasCreds && !editingAccount)}
              onClick={() => testMut.mutate()}>
              {testMut.isPending ? t('finance.testing') : t('finance.testConnection')}
            </Button>
            <Button disabled={!form.adapter || saveMut.isPending || (!editingAccount && !hasCreds)}
              onClick={() => saveMut.mutate()}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {providerDialog()}

      <ConfirmDialog
        open={deleteAccountId !== null}
        onOpenChange={(o) => !o && setDeleteAccountId(null)}
        title={t('finance.disconnectTitle')}
        description={t('finance.disconnectDesc')}
        variant="destructive"
        onConfirm={() => deleteAccountId && deleteMut.mutate(deleteAccountId)}
      />
      <ConfirmDialog
        open={deleteProviderId !== null}
        onOpenChange={(o) => !o && setDeleteProviderId(null)}
        title={t('finance.archive.deleteProviderTitle')}
        description={t('finance.archive.deleteProviderDesc')}
        variant="destructive"
        onConfirm={() => deleteProviderId && deleteProvMut.mutate(deleteProviderId)}
      />
      <ConfirmDialog
        open={deleteItemId !== null}
        onOpenChange={(o) => !o && setDeleteItemId(null)}
        title={t('finance.archive.deleteItemTitle')}
        description={t('finance.archive.deleteItemDesc')}
        variant="destructive"
        onConfirm={() => deleteItemId && deleteItemMut.mutate(deleteItemId)}
      />
    </div>
  )
}

// ── Archive ──────────────────────────────────────────────────────

function ArchivedItemRow({ it, canEdit, canDelete, onRestore, onDelete }: {
  it: FinanceItem; canEdit: boolean; canDelete: boolean
  onRestore: (id: number) => void; onDelete: (id: number) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // историю оплат тянем лениво — только при раскрытии записи
  const { data: pays, isLoading } = useQuery({
    queryKey: ['finance-payments', 'item', it.id],
    queryFn: () => financeApi.listPayments({ item_id: it.id }),
    enabled: open,
    staleTime: 60_000,
  })
  return (
    <Card>
      <CardContent className="py-2.5 flex items-center gap-2.5">
        <button type="button" onClick={() => setOpen(!open)}
          className="shrink-0 text-primary-400 hover:text-primary-300 transition-colors"
          aria-expanded={open} aria-label={t('finance.archive.payments')}
          title={t('finance.archive.payments')}>
          <ChevronDown className={cn('w-4 h-4 transition-transform', open && 'rotate-180')} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-sm text-white truncate">{it.name}</div>
          <div className="text-xs text-muted-foreground truncate">
            {[it.provider_name, it.category_name].filter(Boolean).join(' · ')}
          </div>
        </div>
        <span className={cn('text-sm font-mono shrink-0', it.kind === 'income' ? 'text-green-400' : 'text-white')}>
          {fmtMoney(it.amount, it.currency)}
        </span>
        <div className="flex items-center gap-1 shrink-0 -mr-1">
          {canEdit && (
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('finance.archive.restore')}
              onClick={() => onRestore(it.id)}>
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          )}
          {canDelete && (
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-400 hover:text-red-300" title={t('common.delete')}
              onClick={() => onDelete(it.id)}>
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </CardContent>
      {open && (
        <div className="border-t border-white/5 divide-y divide-white/5 max-h-60 overflow-y-auto">
          {isLoading ? (
            <div className="px-4 py-2"><Skeleton className="h-5" /></div>
          ) : pays?.items.length ? (
            pays.items.map((pm) => (
              <div key={pm.id} className="px-4 py-2 flex items-center gap-3 text-sm">
                <span className="text-muted-foreground shrink-0">{pm.paid_at}</span>
                {pm.comment && <span className="text-xs text-muted-foreground truncate flex-1">{pm.comment}</span>}
                <span className={cn('ml-auto font-mono shrink-0', pm.kind === 'income' ? 'text-green-400' : 'text-white')}>
                  {fmtMoney(pm.amount, pm.currency)}
                </span>
              </div>
            ))
          ) : (
            <div className="px-4 py-2 text-sm text-muted-foreground">{t('finance.archive.noPayments')}</div>
          )}
        </div>
      )}
    </Card>
  )
}

function ArchiveTab({ canEdit, canDelete }: { canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: provs, isLoading: provsLoading } = useQuery({
    queryKey: ['finance-provs'], queryFn: financeApi.listProviders, staleTime: 300_000,
  })
  const { data: archived, isLoading, isError, refetch } = useQuery({
    queryKey: ['finance-items', 'archived'],
    queryFn: () => financeApi.listItems({ status: 'archived' }),
    staleTime: 30_000,
  })
  const [deleteItemId, setDeleteItemId] = useState<number | null>(null)
  const [deleteProviderId, setDeleteProviderId] = useState<number | null>(null)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['finance-items'] })
    qc.invalidateQueries({ queryKey: ['finance-provs'] })
    qc.invalidateQueries({ queryKey: ['finance-summary'] })
    qc.invalidateQueries({ queryKey: ['finance-upcoming'] })
  }

  const restoreItemMut = useMutation({
    mutationFn: (id: number) => financeApi.updateItem(id, { status: 'active' }),
    onSuccess: () => { toast.success(t('finance.archive.restored')); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const deleteItemMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteItem(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteItemId(null); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const restoreProvMut = useMutation({
    mutationFn: (id: number) => financeApi.updateProvider(id, { archived: false }),
    onSuccess: () => { toast.success(t('finance.archive.restored')); invalidate() },
    onError: () => toast.error(t('common.error')),
  })
  const deleteProvMut = useMutation({
    mutationFn: (id: number) => financeApi.deleteProvider(id),
    onSuccess: () => { toast.success(t('common.deleted')); setDeleteProviderId(null); invalidate() },
    onError: () => toast.error(t('common.error')),
  })

  const archivedProvs = (provs?.items || []).filter((p) => p.archived)
  const items = archived?.items || []

  if (isError) return <QueryError onRetry={refetch} />
  if (isLoading || provsLoading) {
    return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
  }
  if (!archivedProvs.length && !items.length) {
    return <EmptyState icon={Archive} title={t('finance.archive.empty')} description={t('finance.archive.emptyHint')} />
  }

  return (
    <div className="space-y-4">
      {archivedProvs.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-sm font-medium text-white">{t('finance.archive.hostersSection')}</h3>
          {archivedProvs.map((p) => (
            <Card key={p.id}>
              <CardContent className="py-2.5 flex items-center gap-2.5">
                <Server className="w-4 h-4 text-muted-foreground shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white truncate">{p.name}</div>
                  {p.url && <div className="text-xs text-muted-foreground truncate">{p.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')}</div>}
                </div>
                <div className="flex items-center gap-1 shrink-0 -mr-1">
                  {canEdit && (
                    <Button size="sm" variant="ghost" className="h-8 w-8 p-0" title={t('finance.archive.restore')}
                      onClick={() => restoreProvMut.mutate(p.id)}>
                      <RotateCcw className="w-3.5 h-3.5" />
                    </Button>
                  )}
                  {canDelete && (
                    <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-red-400 hover:text-red-300" title={t('common.delete')}
                      onClick={() => setDeleteProviderId(p.id)}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {items.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-sm font-medium text-white">{t('finance.archive.itemsSection')}</h3>
          {items.map((it) => (
            <ArchivedItemRow key={it.id} it={it} canEdit={canEdit} canDelete={canDelete}
              onRestore={(id) => restoreItemMut.mutate(id)} onDelete={(id) => setDeleteItemId(id)} />
          ))}
        </div>
      )}
      <ConfirmDialog
        open={deleteItemId !== null}
        onOpenChange={(o) => !o && setDeleteItemId(null)}
        title={t('finance.archive.deleteItemTitle')}
        description={t('finance.archive.deleteItemDesc')}
        variant="destructive"
        onConfirm={() => deleteItemId && deleteItemMut.mutate(deleteItemId)}
      />
      <ConfirmDialog
        open={deleteProviderId !== null}
        onOpenChange={(o) => !o && setDeleteProviderId(null)}
        title={t('finance.archive.deleteProviderTitle')}
        description={t('finance.archive.deleteProviderDesc')}
        variant="destructive"
        onConfirm={() => deleteProviderId && deleteProvMut.mutate(deleteProviderId)}
      />
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────

export default function Finance() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useTabParam('overview', ['overview', 'items', 'payments', 'hosters', 'rates', 'archive'])
  const canView = useHasPermission('finance', 'view')
  const canCreate = useHasPermission('finance', 'create')
  const canEdit = useHasPermission('finance', 'edit')
  const canDelete = useHasPermission('finance', 'delete')
  const [importOpen, setImportOpen] = useState(false)
  const [importCurrency, setImportCurrency] = useState('USD')
  // провайдер для предзаполнения диалога записи («Добавить сервер» из карточки хостера)
  const [prefillProvider, setPrefillProvider] = useState<number | null>(null)

  const importMut = useMutation({
    mutationFn: () => financeApi.importFromPanel(importCurrency),
    onSuccess: (r) => {
      toast.success(t('finance.importDone', { providers: r.providers, items: r.items, payments: r.payments }))
      if (r.retagged) toast.info(t('finance.importRetagged', { count: r.retagged, currency: importCurrency }))
      setImportOpen(false)
      qc.invalidateQueries({ queryKey: ['finance-items'] })
      qc.invalidateQueries({ queryKey: ['finance-summary'] })
      qc.invalidateQueries({ queryKey: ['finance-payments'] })
    },
    onError: () => toast.error(t('finance.importError')),
  })

  if (!canView) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">{t('common.noPermission', { defaultValue: 'No permission' })}</p>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6">
      <div className="page-header">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-header-title">{t('finance.title')}</h1>
            <InfoTooltip text={t('finance.tooltip')} side="right" />
          </div>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('finance.subtitle')}</p>
        </div>
        {canCreate && (
          <div className="page-header-actions">
            <Button variant="secondary" className="gap-2" onClick={() => setImportOpen(true)} disabled={importMut.isPending}>
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">{t('finance.importPanel')}</span>
            </Button>
          </div>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t('finance.tabs.overview')}</TabsTrigger>
          <TabsTrigger value="items">{t('finance.tabs.items')}</TabsTrigger>
          <TabsTrigger value="payments">{t('finance.tabs.payments')}</TabsTrigger>
          <TabsTrigger value="hosters">{t('finance.tabs.hosters')}</TabsTrigger>
          <TabsTrigger value="rates">{t('finance.tabs.rates')}</TabsTrigger>
          <TabsTrigger value="archive">{t('finance.tabs.archive')}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewTab /></TabsContent>
        <TabsContent value="items">
          <ItemsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete}
            prefillProvider={prefillProvider} onPrefillConsumed={() => setPrefillProvider(null)} />
        </TabsContent>
        <TabsContent value="payments"><PaymentsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="hosters">
          <HostersTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete}
            onAddItem={(id) => { setPrefillProvider(id); setTab('items') }} />
        </TabsContent>
        <TabsContent value="rates"><RatesTab canEdit={canEdit} /></TabsContent>
        <TabsContent value="archive"><ArchiveTab canEdit={canEdit} canDelete={canDelete} /></TabsContent>
      </Tabs>

      {/* Импорт из панели: панельные суммы безвалютные — выбираем валюту */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('finance.importPanel')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t('finance.importCurrency')}</Label>
            <CurrencySelect value={importCurrency} onChange={setImportCurrency} />
            <p className="text-xs text-muted-foreground">{t('finance.importCurrencyHint')}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => importMut.mutate()} disabled={importMut.isPending}>
              {t('finance.importRun')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
