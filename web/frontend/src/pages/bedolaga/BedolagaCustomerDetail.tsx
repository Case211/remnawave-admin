import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
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
  Clock,
  HardDrive,
  Smartphone,
  RefreshCw,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  ArrowRightLeft,
  Gift,
  ShieldCheck,
  Star,
  Hash,
  AtSign,
  MessageCircle,
  Copy,
  Check,
  Pencil,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

// ── Helpers ──

function getInitials(user: any): string {
  if (user.username) return user.username.charAt(0).toUpperCase()
  if (user.first_name) return user.first_name.charAt(0).toUpperCase()
  return '#'
}

function getInitialColor(id: number): string {
  const colors = [
    'from-blue-500 to-blue-600',
    'from-emerald-500 to-emerald-600',
    'from-amber-500 to-amber-600',
    'from-violet-500 to-violet-600',
    'from-pink-500 to-pink-600',
    'from-cyan-500 to-cyan-600',
  ]
  return colors[id % colors.length]
}

function relativeTime(d?: string): string {
  if (!d) return '—'
  const now = Date.now()
  const diff = now - new Date(d).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'online'
  if (mins < 60) return `${mins} мин назад`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} ч назад`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} дн назад`
  return `${Math.floor(days / 30)} мес назад`
}

function isOnline(d?: string): boolean {
  if (!d) return false
  return Date.now() - new Date(d).getTime() < 5 * 60_000
}

function formatDate(d?: string): string {
  if (!d) return '—'
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDateShort(d?: string): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

function daysUntil(d?: string): number | null {
  if (!d) return null
  const diff = new Date(d).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

const txTypeIcons: Record<string, typeof TrendingUp> = {
  payment: TrendingUp,
  deposit: TrendingUp,
  purchase: CreditCard,
  refund: TrendingDown,
  withdrawal: TrendingDown,
  bonus: Gift,
  referral: Star,
  subscription: Activity,
  transfer: ArrowRightLeft,
}

const txTypeColors: Record<string, string> = {
  payment: 'text-emerald-400 bg-emerald-500/10',
  deposit: 'text-emerald-400 bg-emerald-500/10',
  purchase: 'text-blue-400 bg-blue-500/10',
  refund: 'text-amber-400 bg-amber-500/10',
  withdrawal: 'text-red-400 bg-red-500/10',
  bonus: 'text-violet-400 bg-violet-500/10',
  referral: 'text-pink-400 bg-pink-500/10',
  subscription: 'text-cyan-400 bg-cyan-500/10',
  transfer: 'text-dark-200 bg-dark-500/10',
}

// ── Component ──

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
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [editDialog, setEditDialog] = useState(false)
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '', username: '' })

  // ── Queries ──

  const { data: user, isLoading } = useQuery({
    queryKey: ['bedolaga-customer', id],
    queryFn: () => client.get(`/bedolaga/customers/${id}`).then((r) => r.data),
    enabled: !!id,
    staleTime: 15_000,
  })

  const { data: txData } = useQuery({
    queryKey: ['bedolaga-customer-transactions', id],
    queryFn: () => client.get(`/bedolaga/customers/transactions?user_id=${id}&limit=20`).then((r) => r.data),
    enabled: !!id,
    staleTime: 30_000,
  })

  const { data: eventsData } = useQuery({
    queryKey: ['bedolaga-customer-events', id],
    queryFn: () => client.get(`/bedolaga/customers/events?user_id=${id}&limit=10`).then((r) => r.data),
    enabled: !!id,
    staleTime: 30_000,
  })

  const { data: remnawaveUser } = useQuery({
    queryKey: ['remnawave-user-by-tg', user?.telegram_id],
    queryFn: () => client.get(`/users?search=${user.telegram_id}&limit=1`).then((r) => {
      const items = r.data?.items || r.data?.users || []
      return Array.isArray(items) && items.length > 0 ? items[0] : null
    }),
    enabled: !!user?.telegram_id,
    staleTime: 60_000,
  })

  // ── Mutations ──

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

  const updateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      client.patch(`/bedolaga/customers/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-customer', id] })
      toast.success(t('bedolaga.customerDetail.userUpdated'))
      setEditDialog(false)
    },
    onError: () => toast.error(t('bedolaga.customerDetail.userUpdateError')),
  })

  const openEditDialog = () => {
    setEditForm({
      first_name: user?.first_name || '',
      last_name: user?.last_name || '',
      username: user?.username || '',
    })
    setEditDialog(true)
  }

  const handleEditSubmit = () => {
    const payload: Record<string, unknown> = {}
    if (editForm.first_name !== (user?.first_name || '')) payload.first_name = editForm.first_name
    if (editForm.last_name !== (user?.last_name || '')) payload.last_name = editForm.last_name
    if (editForm.username !== (user?.username || '')) payload.username = editForm.username
    if (Object.keys(payload).length === 0) { setEditDialog(false); return }
    updateMutation.mutate(payload)
  }

  const handleBalanceSubmit = () => {
    const kopeks = Math.round(parseFloat(balanceAmount) * 100)
    if (isNaN(kopeks)) return
    balanceMutation.mutate({ amount_kopeks: kopeks, reason: balanceReason || undefined })
  }

  const handleExtendSubmit = () => {
    const days = parseInt(extendDays)
    if (!days || days < 1) return
    extendMutation.mutate({ days })
  }

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 1500)
  }

  // ── Loading ──

  if (isLoading) {
    return (
      <div className="space-y-4 md:space-y-6">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div><Skeleton className="h-6 w-48 mb-1" /><Skeleton className="h-4 w-32" /></div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center mt-16 space-y-3">
        <User className="w-12 h-12 mx-auto text-dark-400" />
        <p className="text-dark-300 text-lg">{t('bedolaga.customerDetail.notFound')}</p>
        <Button variant="secondary" onClick={() => navigate('/bedolaga/customers')} className="gap-2">
          <ArrowLeft className="w-4 h-4" /> {t('bedolaga.customers.title')}
        </Button>
      </div>
    )
  }

  const sub = user.subscription
  const transactions = Array.isArray(txData?.items) ? txData.items : []
  const events = Array.isArray(eventsData?.items) ? eventsData.items : []
  const online = isOnline(user.last_activity)
  const balance = user.balance_rubles ?? 0
  const balancePositive = balance >= 0

  // Traffic calculations
  const trafficUsed = sub?.traffic_used_gb ?? 0
  const trafficLimit = sub?.traffic_limit_gb ?? null
  const trafficPercent = trafficLimit ? Math.min(100, (trafficUsed / trafficLimit) * 100) : null
  const subDaysLeft = daysUntil(sub?.end_date)

  return (
    <div className="space-y-4 md:space-y-6">
      {/* ── Header with avatar ── */}
      <div className="page-header">
        <div className="flex items-center gap-3 sm:gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/bedolaga/customers')} className="flex-shrink-0">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          {/* Large avatar */}
          <div className="relative flex-shrink-0">
            <div className={cn('flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 rounded-full text-white text-lg sm:text-xl font-bold bg-gradient-to-br shadow-lg', getInitialColor(user.id))}>
              {getInitials(user)}
            </div>
            {/* Online dot */}
            <span className={cn(
              'absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[var(--glass-bg)]',
              online ? 'bg-emerald-400 animate-pulse' : 'bg-dark-500'
            )} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="page-header-title truncate">
                {user.username || user.first_name || `#${user.id}`}
              </h1>
              <Badge className={cn('text-[10px]',
                user.status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'
              )}>
                {user.status}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-dark-300 text-sm">
              <span className="flex items-center gap-1">
                <span className={cn('w-2 h-2 rounded-full', online ? 'bg-emerald-400' : 'bg-dark-500')} />
                {relativeTime(user.last_activity)}
              </span>
              {user.telegram_id && <span className="hidden sm:inline">TG: {user.telegram_id}</span>}
            </div>
          </div>
        </div>
        <div className="page-header-actions">
          {remnawaveUser?.uuid && (
            <Link to={`/users/${remnawaveUser.uuid}`}>
              <Button variant="secondary" className="gap-2 text-xs">
                <ExternalLink className="w-4 h-4" />
                <span className="hidden sm:inline">Remnawave</span>
              </Button>
            </Link>
          )}
          <Button variant="secondary" size="icon" onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['bedolaga-customer', id] })
            queryClient.invalidateQueries({ queryKey: ['bedolaga-customer-transactions', id] })
          }}>
            <RefreshCw className="w-5 h-5" />
          </Button>
        </div>
      </div>

      {/* ── Quick stats row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Balance */}
        <Card className="glass-card">
          <CardContent className="p-3 sm:p-4">
            <p className="text-xs text-dark-300 mb-0.5">{t('bedolaga.customerDetail.balance')}</p>
            <p className={cn('text-xl sm:text-2xl font-bold', balancePositive ? 'text-white' : 'text-red-400 animate-pulse')}>
              {balance.toLocaleString()} ₽
            </p>
          </CardContent>
        </Card>
        {/* Subscription status */}
        <Card className="glass-card">
          <CardContent className="p-3 sm:p-4">
            <p className="text-xs text-dark-300 mb-0.5">{t('bedolaga.customerDetail.subscription')}</p>
            {sub ? (
              <div className="flex items-center gap-1.5">
                <Badge className={cn('text-[10px]', sub.is_trial ? 'bg-blue-500/20 text-blue-400' : sub.status === 'active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-dark-500/20 text-dark-300')}>
                  {sub.is_trial ? 'Trial' : sub.status}
                </Badge>
                {subDaysLeft != null && subDaysLeft > 0 && (
                  <span className={cn('text-xs font-medium', subDaysLeft <= 3 ? 'text-red-400' : subDaysLeft <= 7 ? 'text-amber-400' : 'text-dark-200')}>
                    {subDaysLeft}d
                  </span>
                )}
              </div>
            ) : (
              <p className="text-dark-400 text-sm">—</p>
            )}
          </CardContent>
        </Card>
        {/* Traffic */}
        <Card className="glass-card">
          <CardContent className="p-3 sm:p-4">
            <p className="text-xs text-dark-300 mb-0.5">{t('bedolaga.customerDetail.traffic')}</p>
            {trafficPercent !== null ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">{trafficUsed.toFixed(1)} / {trafficLimit} GB</p>
                <div className="h-1.5 w-full rounded-full bg-dark-600 overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all',
                      trafficPercent > 90 ? 'bg-red-500 animate-pulse' : trafficPercent > 70 ? 'bg-amber-500' : 'bg-emerald-500'
                    )}
                    style={{ width: `${trafficPercent}%` }}
                  />
                </div>
              </div>
            ) : (
              <p className="text-sm font-medium">{sub ? `${trafficUsed.toFixed(1)} GB` : '—'}</p>
            )}
          </CardContent>
        </Card>
        {/* Devices */}
        <Card className="glass-card">
          <CardContent className="p-3 sm:p-4">
            <p className="text-xs text-dark-300 mb-0.5">{t('bedolaga.customerDetail.devices')}</p>
            <p className="text-xl sm:text-2xl font-bold">{sub?.device_limit ?? '—'}</p>
          </CardContent>
        </Card>
      </div>

      {/* ── Main content — 3 columns on desktop ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Column 1: User info */}
        <Card className="glass-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
              <div className="flex items-center gap-2"><User className="w-4 h-4 text-blue-400" />{t('bedolaga.customerDetail.userInfo')}</div>
              <Button variant="ghost" size="sm" onClick={openEditDialog} className="gap-1 text-xs h-7">
                <Pencil className="w-3.5 h-3.5" /> {t('bedolaga.customerDetail.editUser')}
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-2.5">
            {/* Info rows with icons */}
            <InfoRow icon={AtSign} label={t('bedolaga.customerDetail.name')} value={`${user.first_name || ''} ${user.last_name || ''}`.trim() || '—'} />
            <InfoRow icon={User} label="Username" value={user.username || '—'} copyable onCopy={() => user.username && copyToClipboard(user.username, 'username')} copied={copiedField === 'username'} />
            <InfoRow icon={MessageCircle} label="Telegram ID" value={user.telegram_id ? String(user.telegram_id) : '—'} copyable={!!user.telegram_id} onCopy={() => user.telegram_id && copyToClipboard(String(user.telegram_id), 'tg')} copied={copiedField === 'tg'} />
            <InfoRow icon={Hash} label="ID" value={String(user.id)} />

            <Separator className="bg-[var(--glass-border)]" />

            <InfoRow icon={Calendar} label={t('bedolaga.customerDetail.registered')} value={formatDate(user.created_at)} />
            <InfoRow icon={Clock} label={t('bedolaga.customerDetail.lastActivity')} value={relativeTime(user.last_activity)} highlight={online} />

            {user.promo_group?.name && (
              <>
                <Separator className="bg-[var(--glass-border)]" />
                <InfoRow icon={Gift} label={t('bedolaga.customerDetail.promoGroup')} value={user.promo_group.name} />
              </>
            )}
            {user.referral_code && (
              <InfoRow icon={Star} label={t('bedolaga.customerDetail.referralCode')} value={user.referral_code} mono copyable onCopy={() => copyToClipboard(user.referral_code, 'ref')} copied={copiedField === 'ref'} />
            )}
            {user.email && (
              <InfoRow icon={AtSign} label="Email" value={user.email} copyable onCopy={() => copyToClipboard(user.email, 'email')} copied={copiedField === 'email'} />
            )}
          </CardContent>
        </Card>

        {/* Column 2: Balance + Subscription */}
        <div className="space-y-4">
          {/* Balance card */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
                <div className="flex items-center gap-2"><Wallet className="w-4 h-4 text-amber-400" />{t('bedolaga.customerDetail.balance')}</div>
                <Button variant="ghost" size="sm" onClick={() => setBalanceDialog(true)} className="gap-1 text-xs h-7">
                  <CreditCard className="w-3.5 h-3.5" /> {t('bedolaga.customerDetail.changeBalance')}
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="flex items-baseline gap-2">
                <p className={cn('text-3xl sm:text-4xl font-bold transition-colors', balancePositive ? 'text-white' : 'text-red-400')}>
                  {balance.toLocaleString()}
                </p>
                <span className="text-dark-300 text-lg">₽</span>
              </div>
              <p className="text-xs text-dark-400 mt-1">{(user.balance_kopeks ?? 0).toLocaleString()} {t('bedolaga.customerDetail.kopeks')}</p>
            </CardContent>
          </Card>

          {/* Subscription card */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2 justify-between">
                <div className="flex items-center gap-2"><Activity className="w-4 h-4 text-emerald-400" />{t('bedolaga.customerDetail.subscription')}</div>
                {sub && (
                  <Button variant="ghost" size="sm" onClick={() => setExtendDialog(true)} className="gap-1 text-xs h-7">
                    <Plus className="w-3.5 h-3.5" /> {t('bedolaga.customerDetail.extend')}
                  </Button>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {sub ? (
                <div className="space-y-3">
                  {/* Status + badge */}
                  <div className="flex items-center justify-between">
                    <Badge className={cn('text-xs px-2 py-0.5', sub.is_trial ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' : sub.status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-dark-500/20 text-dark-300 border-dark-500/30')}>
                      {sub.is_trial ? 'Trial' : sub.status}
                    </Badge>
                    {sub.autopay_enabled && (
                      <Badge className="text-[10px] bg-blue-500/20 text-blue-400 border-blue-500/30 gap-1">
                        <ShieldCheck className="w-3 h-3" /> {t('bedolaga.customerDetail.autopay')}
                      </Badge>
                    )}
                  </div>

                  {/* Valid until with countdown */}
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-dark-300 flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" />{t('bedolaga.customerDetail.validUntil')}</span>
                    <div className="flex items-center gap-2">
                      <span>{formatDateShort(sub.end_date)}</span>
                      {subDaysLeft != null && (
                        <Badge className={cn('text-[10px]',
                          subDaysLeft <= 0 ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                          subDaysLeft <= 3 ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                          subDaysLeft <= 7 ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                          'bg-dark-500/20 text-dark-200 border-dark-500/30'
                        )}>
                          {subDaysLeft <= 0 ? t('bedolaga.customers.subExpired') : `${subDaysLeft}d`}
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Traffic bar */}
                  <div>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                      <span className="text-dark-300 flex items-center gap-1.5"><HardDrive className="w-3.5 h-3.5" />{t('bedolaga.customerDetail.traffic')}</span>
                      <span>{trafficUsed.toFixed(1)} / {trafficLimit ?? '∞'} GB</span>
                    </div>
                    {trafficPercent !== null && (
                      <div className="h-2 w-full rounded-full bg-dark-600 overflow-hidden">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all duration-500',
                            trafficPercent > 90 ? 'bg-gradient-to-r from-red-500 to-red-400 animate-pulse' :
                            trafficPercent > 70 ? 'bg-gradient-to-r from-amber-500 to-amber-400' :
                            'bg-gradient-to-r from-emerald-500 to-emerald-400'
                          )}
                          style={{ width: `${trafficPercent}%` }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Devices */}
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-dark-300 flex items-center gap-1.5"><Smartphone className="w-3.5 h-3.5" />{t('bedolaga.customerDetail.devices')}</span>
                    <span>{sub.device_limit ?? '—'}</span>
                  </div>
                </div>
              ) : (
                <div className="text-center py-4">
                  <Activity className="w-8 h-8 mx-auto text-dark-400 mb-2 opacity-40" />
                  <p className="text-dark-400 text-sm">{t('bedolaga.customerDetail.noSubscription')}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Column 3: Transactions + Events */}
        <div className="space-y-4">
          {/* Transactions */}
          <Card className="glass-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Clock className="w-4 h-4 text-violet-400" />
                {t('bedolaga.customerDetail.recentTransactions')}
                {transactions.length > 0 && <span className="text-dark-400 text-xs font-normal">({transactions.length})</span>}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {transactions.length === 0 ? (
                <div className="text-center py-4">
                  <ArrowRightLeft className="w-8 h-8 mx-auto text-dark-400 mb-2 opacity-40" />
                  <p className="text-dark-400 text-sm">{t('bedolaga.customerDetail.noTransactions')}</p>
                </div>
              ) : (
                <div className="space-y-1 max-h-[320px] overflow-y-auto pr-1">
                  {transactions.map((tx: any) => {
                    const TxIcon = txTypeIcons[tx.type] || ArrowRightLeft
                    const colorClass = txTypeColors[tx.type] || txTypeColors.transfer
                    const isPositive = (tx.amount_kopeks ?? 0) > 0
                    return (
                      <div key={tx.id} className="flex items-center gap-2.5 py-2 border-b border-[var(--glass-border)] last:border-0 group hover:bg-[var(--glass-bg)] rounded px-1.5 -mx-1.5 transition-colors">
                        {/* Icon */}
                        <div className={cn('flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0', colorClass)}>
                          <TxIcon className="w-3.5 h-3.5" />
                        </div>
                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-medium truncate">{tx.type}</span>
                            <span className={cn('text-xs font-bold tabular-nums', isPositive ? 'text-emerald-400' : 'text-red-400')}>
                              {isPositive ? '+' : ''}{tx.amount_rubles?.toLocaleString()} ₽
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            {tx.description && <span className="text-[10px] text-dark-400 truncate mr-2">{tx.description}</span>}
                            <span className="text-[10px] text-dark-400 flex-shrink-0">{formatDateShort(tx.created_at)}</span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Subscription events */}
          {events.length > 0 && (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  {t('bedolaga.customerDetail.events')}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="space-y-1 max-h-[200px] overflow-y-auto pr-1">
                  {events.map((ev: any) => (
                    <div key={ev.id} className="flex items-center justify-between py-1.5 border-b border-[var(--glass-border)] last:border-0 text-xs">
                      <span className="text-dark-200">{ev.event_type || ev.type}</span>
                      <span className="text-dark-400">{formatDateShort(ev.created_at)}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* ── Balance dialog ── */}
      <Dialog open={balanceDialog} onOpenChange={setBalanceDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.customerDetail.changeBalance')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-dark-200">{t('bedolaga.customerDetail.changeBalanceDesc')}</p>
          <div className="space-y-3 py-2">
            <div>
              <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.amountRubles')}</label>
              <input
                type="number" step="0.01"
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
          <DialogFooter>
            <Button variant="secondary" onClick={() => setBalanceDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleBalanceSubmit} disabled={!balanceAmount || balanceMutation.isPending}>
              {balanceMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : t('common.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Extend dialog ── */}
      <Dialog open={extendDialog} onOpenChange={setExtendDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.customerDetail.extendSubscription')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-dark-200">{t('bedolaga.customerDetail.extendDesc')}</p>
          <div className="py-2">
            <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.days')}</label>
            <input
              type="number" min="1"
              value={extendDays}
              onChange={(e) => setExtendDays(e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
            />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setExtendDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleExtendSubmit} disabled={!extendDays || extendMutation.isPending}>
              {extendMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : t('bedolaga.customerDetail.extend')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit user dialog ── */}
      <Dialog open={editDialog} onOpenChange={setEditDialog}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.customerDetail.editUserTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.firstName')}</label>
              <input
                type="text"
                value={editForm.first_name}
                onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="text-xs text-dark-200 mb-1 block">{t('bedolaga.customerDetail.lastName')}</label>
              <input
                type="text"
                value={editForm.last_name}
                onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="text-xs text-dark-200 mb-1 block">Username</label>
              <input
                type="text"
                value={editForm.username}
                onChange={(e) => setEditForm({ ...editForm, username: e.target.value })}
                className="w-full h-10 px-3 rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setEditDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleEditSubmit} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── InfoRow component ──

function InfoRow({ icon: Icon, label, value, mono, copyable, onCopy, copied, highlight }: {
  icon: typeof User
  label: string
  value: string
  mono?: boolean
  copyable?: boolean
  onCopy?: () => void
  copied?: boolean
  highlight?: boolean
}) {
  return (
    <div className="flex items-center justify-between group text-sm">
      <span className="flex items-center gap-2 text-dark-300">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" />
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        <span className={cn(
          'text-right truncate max-w-[160px]',
          mono && 'font-mono text-xs',
          highlight && 'text-emerald-400 font-medium',
        )}>
          {value}
        </span>
        {copyable && onCopy && (
          <button onClick={onCopy} className="opacity-0 group-hover:opacity-100 transition-opacity text-dark-400 hover:text-white">
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </button>
        )}
      </div>
    </div>
  )
}
