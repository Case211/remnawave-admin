import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw,
  Users,
  CreditCard,
  TrendingUp,
  MessageSquare,
  Tag,
  Handshake,
  Wifi,
  WifiOff,
  DollarSign,
  ArrowUpRight,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useHasPermission } from '@/components/PermissionGate'
import { useFormatters } from '@/lib/useFormatters'
import {
  bedolagaApi,
  type BedolagaUser,
  type BedolagaSubscription,
  type BedolagaTransaction,
} from '@/api/bedolaga'

export default function BedolagaPage() {
  const { t } = useTranslation()
  const { formatDate, formatCurrency } = useFormatters()
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('bedolaga', 'edit')
  const [activeTab, setActiveTab] = useState('overview')

  // ── Status ────────────────────────────────────────────────
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['bedolaga-status'],
    queryFn: bedolagaApi.getStatus,
    refetchInterval: 60000,
  })

  // ── Overview ──────────────────────────────────────────────
  const { data: overview } = useQuery({
    queryKey: ['bedolaga-overview'],
    queryFn: bedolagaApi.getOverview,
    enabled: status?.enabled === true,
  })

  const { data: revenue } = useQuery({
    queryKey: ['bedolaga-revenue'],
    queryFn: bedolagaApi.getRevenue,
    enabled: status?.enabled === true,
  })

  // ── Sync ──────────────────────────────────────────────────
  const syncMutation = useMutation({
    mutationFn: (entity?: string) => bedolagaApi.triggerSync(entity),
    onSuccess: () => {
      toast.success(t('bedolaga.sync.success'))
      queryClient.invalidateQueries({ queryKey: ['bedolaga-overview'] })
      queryClient.invalidateQueries({ queryKey: ['bedolaga-revenue'] })
      queryClient.invalidateQueries({ queryKey: ['bedolaga-status'] })
    },
    onError: () => toast.error(t('bedolaga.sync.error')),
  })

  // Not configured state
  if (!statusLoading && !status?.enabled) {
    return (
      <div className="space-y-6">
        <div className="page-header">
          <h1 className="page-header-title">{t('bedolaga.title')}</h1>
        </div>
        <Card className="border-dark-600 bg-dark-800">
          <CardContent className="p-8 text-center">
            <WifiOff className="w-12 h-12 mx-auto mb-3 text-dark-400" />
            <p className="text-dark-200">{t('bedolaga.notConfigured')}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-header-title">{t('bedolaga.title')}</h1>
          <p className="text-dark-200">{t('bedolaga.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={status?.connected ? 'default' : 'destructive'} className="gap-1.5">
            {status?.connected ? (
              <Wifi className="w-3 h-3" />
            ) : (
              <WifiOff className="w-3 h-3" />
            )}
            {status?.connected ? t('bedolaga.connected') : t('bedolaga.disconnected')}
          </Badge>
          {status?.bot_version && (
            <span className="text-xs text-dark-300">v{status.bot_version}</span>
          )}
          {canEdit && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => syncMutation.mutate(undefined)}
              disabled={syncMutation.isPending}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
              {syncMutation.isPending ? t('bedolaga.sync.syncing') : t('bedolaga.sync.trigger')}
            </Button>
          )}
        </div>
      </div>

      {/* Overview Cards */}
      {statusLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard
            icon={<Users className="w-5 h-5" />}
            label={t('bedolaga.overview.totalUsers')}
            value={overview?.total_users?.toLocaleString() ?? '0'}
          />
          <StatCard
            icon={<CreditCard className="w-5 h-5" />}
            label={t('bedolaga.overview.activeSubscriptions')}
            value={overview?.active_subscriptions?.toLocaleString() ?? '0'}
          />
          <StatCard
            icon={<DollarSign className="w-5 h-5" />}
            label={t('bedolaga.overview.totalRevenue')}
            value={formatCurrency(overview?.total_revenue ?? 0)}
          />
          <StatCard
            icon={<TrendingUp className="w-5 h-5" />}
            label={t('bedolaga.overview.totalTransactions')}
            value={overview?.total_transactions?.toLocaleString() ?? '0'}
          />
          <StatCard
            icon={<MessageSquare className="w-5 h-5" />}
            label={t('bedolaga.overview.openTickets')}
            value={overview?.open_tickets?.toLocaleString() ?? '0'}
          />
        </div>
      )}

      {/* Revenue summary */}
      {revenue && (
        <div className="grid grid-cols-3 gap-4">
          <Card className="border-dark-600 bg-dark-800">
            <CardContent className="p-4 flex items-center gap-3">
              <ArrowUpRight className="w-5 h-5 text-green-400" />
              <div>
                <p className="text-xs text-dark-300">{t('bedolaga.overview.revenueToday')}</p>
                <p className="text-lg font-semibold text-white">{formatCurrency(revenue.revenue_today)}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-dark-600 bg-dark-800">
            <CardContent className="p-4 flex items-center gap-3">
              <ArrowUpRight className="w-5 h-5 text-blue-400" />
              <div>
                <p className="text-xs text-dark-300">{t('bedolaga.overview.revenueWeek')}</p>
                <p className="text-lg font-semibold text-white">{formatCurrency(revenue.revenue_week)}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-dark-600 bg-dark-800">
            <CardContent className="p-4 flex items-center gap-3">
              <ArrowUpRight className="w-5 h-5 text-purple-400" />
              <div>
                <p className="text-xs text-dark-300">{t('bedolaga.overview.revenueMonth')}</p>
                <p className="text-lg font-semibold text-white">{formatCurrency(revenue.revenue_month)}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">
            <TrendingUp className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.overview')}
          </TabsTrigger>
          <TabsTrigger value="users">
            <Users className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.users')}
          </TabsTrigger>
          <TabsTrigger value="subscriptions">
            <CreditCard className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.subscriptions')}
          </TabsTrigger>
          <TabsTrigger value="transactions">
            <DollarSign className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.transactions')}
          </TabsTrigger>
          <TabsTrigger value="tickets">
            <MessageSquare className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.tickets')}
          </TabsTrigger>
          <TabsTrigger value="promos">
            <Tag className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.promos')}
          </TabsTrigger>
          <TabsTrigger value="partners">
            <Handshake className="w-4 h-4 mr-2" />
            {t('bedolaga.tabs.partners')}
          </TabsTrigger>
        </TabsList>

        {/* Users tab */}
        <TabsContent value="users" className="space-y-4">
          <UsersTab formatDate={formatDate} />
        </TabsContent>

        {/* Subscriptions tab */}
        <TabsContent value="subscriptions" className="space-y-4">
          <SubscriptionsTab formatDate={formatDate} formatCurrency={formatCurrency} />
        </TabsContent>

        {/* Transactions tab */}
        <TabsContent value="transactions" className="space-y-4">
          <TransactionsTab formatDate={formatDate} formatCurrency={formatCurrency} />
        </TabsContent>

        {/* Tickets tab */}
        <TabsContent value="tickets" className="space-y-4">
          <TicketsTab formatDate={formatDate} />
        </TabsContent>

        {/* Promo Codes tab */}
        <TabsContent value="promos" className="space-y-4">
          <PromoCodesTab formatDate={formatDate} />
        </TabsContent>

        {/* Partners tab */}
        <TabsContent value="partners" className="space-y-4">
          <PartnersTab formatCurrency={formatCurrency} />
        </TabsContent>

        {/* Overview tab - transaction stats */}
        <TabsContent value="overview" className="space-y-4">
          <OverviewTab formatCurrency={formatCurrency} />
        </TabsContent>
      </Tabs>
    </div>
  )
}


// ── Stat card component ─────────────────────────────────────────

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className="text-dark-300">{icon}</div>
          <div>
            <p className="text-xs text-dark-300">{label}</p>
            <p className="text-lg font-semibold text-white">{value}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}


// ── Pagination helper ───────────────────────────────────────────

function PaginationControls({
  offset, limit, total, onPrev, onNext,
}: {
  offset: number; limit: number; total: number
  onPrev: () => void; onNext: () => void
}) {
  const page = Math.floor(offset / limit) + 1
  const totalPages = Math.ceil(total / limit)

  return (
    <div className="flex items-center justify-between px-4 py-3 text-sm text-dark-300">
      <span>{total} total</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onPrev} disabled={offset === 0}>
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <span>{page} / {totalPages || 1}</span>
        <Button variant="outline" size="sm" onClick={onNext} disabled={offset + limit >= total}>
          <ChevronRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  )
}


// ── Users Tab ───────────────────────────────────────────────────

function UsersTab({ formatDate }: { formatDate: (d: string) => string }) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 50

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-users', offset, search],
    queryFn: () => bedolagaApi.getUsers({ limit, offset, search: search || undefined }),
  })

  return (
    <>
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
          <Input
            placeholder={t('bedolaga.search')}
            value={search}
            onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
            className="pl-9"
          />
        </div>
      </div>

      <Card className="border-dark-600 bg-dark-800">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : !data?.items?.length ? (
            <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-b border-dark-600">
                    <tr>
                      <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ID</th>
                      <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Username</th>
                      <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Telegram ID</th>
                      <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Status</th>
                      <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Balance</th>
                      <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Registered</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-600">
                    {data.items.map((u: BedolagaUser) => (
                      <tr key={u.id} className="hover:bg-dark-700/50">
                        <td className="px-4 py-3 text-sm text-dark-200">{u.id}</td>
                        <td className="px-4 py-3 text-sm text-white">{u.username || u.first_name || '—'}</td>
                        <td className="px-4 py-3 text-sm text-dark-200 font-mono">{u.telegram_id || '—'}</td>
                        <td className="px-4 py-3">
                          <Badge variant={u.status === 'active' ? 'default' : 'secondary'} className="text-xs">
                            {u.status || '—'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-white">{u.balance_rubles.toFixed(2)} ₽</td>
                        <td className="px-4 py-3 text-sm text-dark-300">{u.created_at ? formatDate(u.created_at) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <PaginationControls
                offset={offset} limit={limit} total={data.total}
                onPrev={() => setOffset(Math.max(0, offset - limit))}
                onNext={() => setOffset(offset + limit)}
              />
            </>
          )}
        </CardContent>
      </Card>
    </>
  )
}


// ── Subscriptions Tab ───────────────────────────────────────────

function SubscriptionsTab({ formatDate, formatCurrency }: { formatDate: (d: string) => string; formatCurrency: (n: number) => string }) {
  const { t } = useTranslation()
  const [offset, setOffset] = useState(0)
  const limit = 50

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-subscriptions', offset],
    queryFn: () => bedolagaApi.getSubscriptions({ limit, offset }),
  })

  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : !data?.items?.length ? (
          <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-dark-600">
                  <tr>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ID</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Plan</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Status</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Trial</th>
                    <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Amount</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Provider</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Expires</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-600">
                  {data.items.map((s: BedolagaSubscription) => (
                    <tr key={s.id} className="hover:bg-dark-700/50">
                      <td className="px-4 py-3 text-sm text-dark-200">{s.id}</td>
                      <td className="px-4 py-3 text-sm text-white">{s.plan_name || '—'}</td>
                      <td className="px-4 py-3">
                        <Badge variant={s.status === 'active' ? 'default' : 'secondary'} className="text-xs">
                          {s.status || '—'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-dark-300">{s.is_trial ? 'Yes' : 'No'}</td>
                      <td className="px-4 py-3 text-sm text-right text-white">
                        {s.payment_amount != null ? formatCurrency(s.payment_amount) : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-dark-300">{s.payment_provider || '—'}</td>
                      <td className="px-4 py-3 text-sm text-dark-300">{s.expires_at ? formatDate(s.expires_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls
              offset={offset} limit={limit} total={data.total}
              onPrev={() => setOffset(Math.max(0, offset - limit))}
              onNext={() => setOffset(offset + limit)}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ── Transactions Tab ────────────────────────────────────────────

function TransactionsTab({ formatDate, formatCurrency }: { formatDate: (d: string) => string; formatCurrency: (n: number) => string }) {
  const { t } = useTranslation()
  const [offset, setOffset] = useState(0)
  const limit = 50

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-transactions', offset],
    queryFn: () => bedolagaApi.getTransactions({ limit, offset }),
  })

  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : !data?.items?.length ? (
          <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-dark-600">
                  <tr>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ID</th>
                    <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Amount</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Provider</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Status</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Type</th>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-600">
                  {data.items.map((tx: BedolagaTransaction) => (
                    <tr key={tx.id} className="hover:bg-dark-700/50">
                      <td className="px-4 py-3 text-sm text-dark-200">{tx.id}</td>
                      <td className="px-4 py-3 text-sm text-right text-white font-medium">
                        {formatCurrency(tx.amount)}
                      </td>
                      <td className="px-4 py-3 text-sm text-dark-300">{tx.provider || '—'}</td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={tx.status === 'completed' || tx.status === 'success' ? 'default' : 'secondary'}
                          className="text-xs"
                        >
                          {tx.status || '—'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-sm text-dark-300">{tx.type || '—'}</td>
                      <td className="px-4 py-3 text-sm text-dark-300">{tx.created_at ? formatDate(tx.created_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls
              offset={offset} limit={limit} total={data.total}
              onPrev={() => setOffset(Math.max(0, offset - limit))}
              onNext={() => setOffset(offset + limit)}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ── Tickets Tab (real-time) ─────────────────────────────────────

function TicketsTab({ formatDate }: { formatDate: (d: string) => string }) {
  const { t } = useTranslation()

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-tickets'],
    queryFn: () => bedolagaApi.getTickets({ limit: 50 }),
  })

  const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []

  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : !items.length ? (
          <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-dark-600">
                <tr>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ID</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">User</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Status</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Priority</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-600">
                {items.map((ticket: Record<string, unknown>) => (
                  <tr key={String(ticket.id)} className="hover:bg-dark-700/50">
                    <td className="px-4 py-3 text-sm text-dark-200">#{String(ticket.id)}</td>
                    <td className="px-4 py-3 text-sm text-white">{String(ticket.username || ticket.user_id || '—')}</td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={ticket.status === 'open' ? 'default' : 'secondary'}
                        className="text-xs"
                      >
                        {String(ticket.status || '—')}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm text-dark-300">{String(ticket.priority || '—')}</td>
                    <td className="px-4 py-3 text-sm text-dark-300">
                      {ticket.created_at ? formatDate(String(ticket.created_at)) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}


// ── Promo Codes Tab (real-time) ─────────────────────────────────

function PromoCodesTab({ formatDate }: { formatDate: (d: string) => string }) {
  const { t } = useTranslation()

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-promo-codes'],
    queryFn: () => bedolagaApi.getPromoCodes({ limit: 100 }),
  })

  const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []

  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : !items.length ? (
          <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-dark-600">
                <tr>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Code</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Active</th>
                  <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Discount</th>
                  <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Uses</th>
                  <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">Expires</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-600">
                {items.map((promo: Record<string, unknown>) => (
                  <tr key={String(promo.id)} className="hover:bg-dark-700/50">
                    <td className="px-4 py-3 text-sm text-white font-mono">{String(promo.code || '—')}</td>
                    <td className="px-4 py-3">
                      <Badge variant={promo.is_active ? 'default' : 'secondary'} className="text-xs">
                        {promo.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-white">
                      {promo.discount_percent ? `${promo.discount_percent}%` : promo.discount_amount ? `${promo.discount_amount} ₽` : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-dark-300">
                      {String(promo.used_count ?? 0)}{promo.max_uses ? ` / ${promo.max_uses}` : ''}
                    </td>
                    <td className="px-4 py-3 text-sm text-dark-300">
                      {promo.expires_at ? formatDate(String(promo.expires_at)) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}


// ── Partners Tab (real-time) ────────────────────────────────────

function PartnersTab({ formatCurrency }: { formatCurrency: (n: number) => string }) {
  const { t } = useTranslation()

  const { data: stats } = useQuery({
    queryKey: ['bedolaga-partner-stats'],
    queryFn: () => bedolagaApi.getPartnerStats(30),
  })

  const { data, isLoading } = useQuery({
    queryKey: ['bedolaga-partners'],
    queryFn: () => bedolagaApi.getPartners({ limit: 50 }),
  })

  const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []

  return (
    <>
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            icon={<Users className="w-5 h-5" />}
            label="Total Referrers"
            value={String(stats.total_referrers ?? 0)}
          />
          <StatCard
            icon={<Users className="w-5 h-5" />}
            label="Total Referrals"
            value={String(stats.total_referrals ?? 0)}
          />
          <StatCard
            icon={<DollarSign className="w-5 h-5" />}
            label="Total Earned"
            value={formatCurrency(stats.total_earned ?? 0)}
          />
        </div>
      )}

      <Card className="border-dark-600 bg-dark-800">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : !items.length ? (
            <div className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-dark-600">
                  <tr>
                    <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">User</th>
                    <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Referrals</th>
                    <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Earned</th>
                    <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">Commission</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-600">
                  {items.map((p: Record<string, unknown>) => (
                    <tr key={String(p.user_id)} className="hover:bg-dark-700/50">
                      <td className="px-4 py-3 text-sm text-white">{String(p.username || p.telegram_id || p.user_id)}</td>
                      <td className="px-4 py-3 text-sm text-right text-dark-200">{String(p.referral_count ?? 0)}</td>
                      <td className="px-4 py-3 text-sm text-right text-white">{formatCurrency(Number(p.total_earned ?? 0))}</td>
                      <td className="px-4 py-3 text-sm text-right text-dark-300">
                        {p.commission_rate != null ? `${Number(p.commission_rate) * 100}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  )
}


// ── Overview Tab (transaction stats) ─────────────────────────────

function OverviewTab({ formatCurrency }: { formatCurrency: (n: number) => string }) {
  const { t } = useTranslation()

  const { data: stats, isLoading } = useQuery({
    queryKey: ['bedolaga-tx-stats'],
    queryFn: bedolagaApi.getTransactionStats,
  })

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />
  }

  if (!stats) {
    return (
      <Card className="border-dark-600 bg-dark-800">
        <CardContent className="p-8 text-center text-dark-400">{t('bedolaga.noData')}</CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* By provider */}
      <Card className="border-dark-600 bg-dark-800">
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-white mb-3">Revenue by Provider</h3>
          {stats.by_provider && Object.keys(stats.by_provider).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(stats.by_provider).map(([provider, info]) => {
                const { amount, count } = info as { amount: number; count: number }
                return (
                  <div key={provider} className="flex items-center justify-between">
                    <span className="text-sm text-dark-200">{provider}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-dark-400">{count} tx</span>
                      <span className="text-sm font-medium text-white">{formatCurrency(amount)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-dark-400">{t('bedolaga.noData')}</p>
          )}
        </CardContent>
      </Card>

      {/* Daily chart (text-based) */}
      {Array.isArray(stats.by_day) && stats.by_day.length > 0 && (
        <Card className="border-dark-600 bg-dark-800">
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-white mb-3">Daily Revenue (last 30 days)</h3>
            <div className="space-y-1">
              {stats.by_day.slice(0, 14).map((d) => (
                <div key={d.day} className="flex items-center justify-between text-sm">
                  <span className="text-dark-300 font-mono text-xs">{d.day}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-dark-400">{d.count} tx</span>
                    <span className="text-white">{formatCurrency(d.amount)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
