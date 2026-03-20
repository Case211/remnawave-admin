import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  ArrowLeft,
  User,
  CreditCard,
  Activity,
  Calendar,
  Wallet,
  Plus,
  Minus,
  Clock,
  HardDrive,
  Smartphone,
  RefreshCw,
  ExternalLink,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ConfirmDialog'

export default function BedolagaCustomerDetail() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [balanceDialog, setBalanceDialog] = useState(false)
  const [balanceAmount, setBalanceAmount] = useState('')
  const [balanceReason, setBalanceReason] = useState('')
  const [extendDialog, setExtendDialog] = useState(false)
  const [extendDays, setExtendDays] = useState('7')

  // Fetch user
  const { data: user, isLoading } = useQuery({
    queryKey: ['bedolaga-customer', id],
    queryFn: () => client.get(`/bedolaga/customers/${id}`).then((r) => r.data),
    enabled: !!id,
    staleTime: 15_000,
  })

  // Fetch transactions
  const { data: txData } = useQuery({
    queryKey: ['bedolaga-customer-transactions', id],
    queryFn: () => client.get(`/bedolaga/customers/transactions?user_id=${id}&limit=10`).then((r) => r.data),
    enabled: !!id,
    staleTime: 30_000,
  })

  // Mutations
  const balanceMutation = useMutation({
    mutationFn: (data: { amount_kopeks: number; reason?: string }) =>
      client.post(`/bedolaga/customers/${id}/balance`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-customer', id] })
      queryClient.invalidateQueries({ queryKey: ['bedolaga-customer-transactions', id] })
      toast.success(t('bedolaga.customerDetail.balanceUpdated'))
      setBalanceDialog(false)
      setBalanceAmount('')
      setBalanceReason('')
    },
    onError: () => toast.error(t('common.error')),
  })

  const extendMutation = useMutation({
    mutationFn: (data: { days: number }) =>
      client.post(`/bedolaga/customers/subscriptions/${user?.subscription?.id}/extend`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-customer', id] })
      toast.success(t('bedolaga.customerDetail.subscriptionExtended'))
      setExtendDialog(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const formatDate = (d?: string) => {
    if (!d) return '—'
    return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-48" /><Skeleton className="h-48" />
        </div>
      </div>
    )
  }

  if (!user) {
    return <div className="text-center text-dark-300 mt-12">{t('bedolaga.customerDetail.notFound')}</div>
  }

  const sub = user.subscription
  const transactions = txData?.items || []

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/bedolaga/customers')}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="page-header-title">
                {user.username || user.first_name || `#${user.id}`}
              </h1>
              <Badge className={cn('text-[10px]',
                user.status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'
              )}>
                {user.status}
              </Badge>
            </div>
            <p className="text-dark-300 text-sm">
              ID: {user.id}
              {user.telegram_id && <span className="ml-2">TG: {user.telegram_id}</span>}
            </p>
          </div>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" size="icon" onClick={() => queryClient.invalidateQueries({ queryKey: ['bedolaga-customer', id] })}>
            <RefreshCw className="w-5 h-5" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* User info */}
        <Card className="glass-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <User className="w-4 h-4 text-blue-400" />
              {t('bedolaga.customerDetail.userInfo')}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.name')}</span><span>{user.first_name} {user.last_name || ''}</span></div>
            <div className="flex justify-between"><span className="text-dark-300">Username</span><span>{user.username || '—'}</span></div>
            <div className="flex justify-between"><span className="text-dark-300">Telegram ID</span><span>{user.telegram_id || '—'}</span></div>
            <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.registered')}</span><span>{formatDate(user.created_at)}</span></div>
            <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.lastActivity')}</span><span>{formatDate(user.last_activity)}</span></div>
            {user.promo_group?.name && (
              <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.promoGroup')}</span><span>{user.promo_group.name}</span></div>
            )}
            {user.referral_code && (
              <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.referralCode')}</span><span className="font-mono text-xs">{user.referral_code}</span></div>
            )}
          </CardContent>
        </Card>

        {/* Balance */}
        <Card className="glass-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
              <div className="flex items-center gap-2"><Wallet className="w-4 h-4 text-amber-400" />{t('bedolaga.customerDetail.balance')}</div>
              <Button variant="ghost" size="sm" onClick={() => setBalanceDialog(true)} className="gap-1 text-xs">
                <CreditCard className="w-3.5 h-3.5" /> {t('bedolaga.customerDetail.changeBalance')}
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-3xl font-bold">{(user.balance_rubles ?? 0).toLocaleString()} ₽</p>
            <p className="text-xs text-dark-300 mt-1">{(user.balance_kopeks ?? 0).toLocaleString()} {t('bedolaga.customerDetail.kopeks')}</p>
          </CardContent>
        </Card>

        {/* Subscription */}
        <Card className="glass-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
              <div className="flex items-center gap-2"><Activity className="w-4 h-4 text-emerald-400" />{t('bedolaga.customerDetail.subscription')}</div>
              {sub && (
                <Button variant="ghost" size="sm" onClick={() => setExtendDialog(true)} className="gap-1 text-xs">
                  <Plus className="w-3.5 h-3.5" /> {t('bedolaga.customerDetail.extend')}
                </Button>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {sub ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-dark-300">{t('bedolaga.customerDetail.status')}</span>
                  <Badge className={cn('text-[10px]', sub.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-dark-500/20 text-dark-300')}>
                    {sub.is_trial ? 'Trial' : sub.status}
                  </Badge>
                </div>
                <div className="flex justify-between"><span className="text-dark-300"><Calendar className="w-3.5 h-3.5 inline mr-1" />{t('bedolaga.customerDetail.validUntil')}</span><span>{formatDate(sub.end_date)}</span></div>
                <div className="flex justify-between"><span className="text-dark-300"><HardDrive className="w-3.5 h-3.5 inline mr-1" />{t('bedolaga.customerDetail.traffic')}</span><span>{sub.traffic_used_gb?.toFixed(1) ?? 0} / {sub.traffic_limit_gb ?? '∞'} GB</span></div>
                <div className="flex justify-between"><span className="text-dark-300"><Smartphone className="w-3.5 h-3.5 inline mr-1" />{t('bedolaga.customerDetail.devices')}</span><span>{sub.device_limit ?? '—'}</span></div>
                {sub.autopay_enabled && (
                  <div className="flex justify-between"><span className="text-dark-300">{t('bedolaga.customerDetail.autopay')}</span><Badge className="text-[10px] bg-blue-500/20 text-blue-400">ON</Badge></div>
                )}
              </div>
            ) : (
              <p className="text-dark-400 text-sm">{t('bedolaga.customerDetail.noSubscription')}</p>
            )}
          </CardContent>
        </Card>

        {/* Recent transactions */}
        <Card className="glass-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="w-4 h-4 text-violet-400" />
              {t('bedolaga.customerDetail.recentTransactions')}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {transactions.length === 0 ? (
              <p className="text-dark-400 text-sm">{t('bedolaga.customerDetail.noTransactions')}</p>
            ) : (
              <div className="space-y-1.5 max-h-[240px] overflow-y-auto">
                {transactions.map((tx: any) => (
                  <div key={tx.id} className="flex items-center justify-between py-1.5 border-b border-[var(--glass-border)] last:border-0 text-xs">
                    <div>
                      <span className={tx.amount_kopeks > 0 ? 'text-emerald-400' : 'text-red-400'}>
                        {tx.amount_kopeks > 0 ? '+' : ''}{tx.amount_rubles?.toLocaleString()} ₽
                      </span>
                      <span className="text-dark-400 ml-2">{tx.type}</span>
                    </div>
                    <span className="text-dark-400">{formatDate(tx.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Balance dialog */}
      <ConfirmDialog
        open={balanceDialog}
        onOpenChange={setBalanceDialog}
        title={t('bedolaga.customerDetail.changeBalance')}
        description={t('bedolaga.customerDetail.changeBalanceDesc')}
        onConfirm={() => {
          const kopeks = Math.round(parseFloat(balanceAmount) * 100)
          if (!kopeks || isNaN(kopeks)) return
          balanceMutation.mutate({ amount_kopeks: kopeks, reason: balanceReason || undefined })
        }}
        confirmText={t('common.confirm')}
        variant="default"
      >
        <div className="space-y-3">
          <div>
            <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.amountRubles')}</label>
            <input
              type="number"
              step="0.01"
              value={balanceAmount}
              onChange={(e) => setBalanceAmount(e.target.value)}
              placeholder="+100 или -50"
              className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
            />
          </div>
          <div>
            <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.reason')}</label>
            <input
              type="text"
              value={balanceReason}
              onChange={(e) => setBalanceReason(e.target.value)}
              placeholder={t('bedolaga.customerDetail.reasonPlaceholder')}
              className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
            />
          </div>
        </div>
      </ConfirmDialog>

      {/* Extend dialog */}
      <ConfirmDialog
        open={extendDialog}
        onOpenChange={setExtendDialog}
        title={t('bedolaga.customerDetail.extendSubscription')}
        description={t('bedolaga.customerDetail.extendDesc')}
        onConfirm={() => {
          const days = parseInt(extendDays)
          if (!days || days < 1) return
          extendMutation.mutate({ days })
        }}
        confirmText={t('bedolaga.customerDetail.extend')}
        variant="default"
      >
        <div>
          <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.days')}</label>
          <input
            type="number"
            min="1"
            value={extendDays}
            onChange={(e) => setExtendDays(e.target.value)}
            className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          />
        </div>
      </ConfirmDialog>
    </div>
  )
}
