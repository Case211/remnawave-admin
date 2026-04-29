import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import {
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Plus,
  Pencil,
  Trash2,
  Megaphone,
  Mail,
  Users,
  ExternalLink,
  Square,
} from 'lucide-react'
import client from '@/api/client'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

// ── Types (matching Bedolaga webapi) ──

interface Campaign {
  id: number
  name: string
  start_parameter?: string
  bonus_type?: string
  balance_bonus_kopeks?: number
  balance_bonus_rubles?: number
  subscription_duration_days?: number
  is_active?: boolean
  registrations_count?: number
  created_at?: string
}

interface Broadcast {
  id: number
  target_type?: string
  message_text?: string
  total_count?: number
  sent_count?: number
  failed_count?: number
  blocked_count?: number
  status?: string
  admin_name?: string
  created_at?: string
  completed_at?: string
}

interface Partner {
  id: number
  telegram_id?: number
  username?: string
  first_name?: string
  referral_code?: string
  effective_referral_commission_percent?: number
  invited_count?: number
  active_referrals?: number
  total_earned_kopeks?: number
  total_earned_rubles?: number
  month_earned_kopeks?: number
  month_earned_rubles?: number
  created_at?: string
  last_activity?: string
}

const statusColors: Record<string, string> = {
  pending: 'bg-dark-500/20 text-dark-300 border-dark-500/30',
  sending: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  stopped: 'bg-red-500/20 text-red-400 border-red-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
}

const bonusTypeLabels: Record<string, string> = {
  balance: 'Баланс',
  subscription: 'Подписка',
  tariff: 'Тариф',
  none: '—',
}

// ── Component ──

export default function BedolagaMarketing() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [tab, setTab] = useState('campaigns')
  const [cPage, setCPage] = useState(1)
  const [bPage, setBPage] = useState(1)
  const [pPage, setPPage] = useState(1)
  const perPage = 20

  // Campaign dialog
  const [campaignDialog, setCampaignDialog] = useState(false)
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null)
  const [campaignForm, setCampaignForm] = useState({ name: '', start_parameter: '', bonus_type: 'none', balance_bonus_kopeks: '', subscription_duration_days: '', is_active: true })
  const [deleteCampaign, setDeleteCampaign] = useState<Campaign | null>(null)

  // Broadcast dialog
  const [broadcastDialog, setBroadcastDialog] = useState(false)
  const [broadcastForm, setBroadcastForm] = useState({ target: 'all', message_text: '' })

  // ── Queries ──

  const { data: cData, isLoading: cLoading, refetch: cRefetch } = useQuery<{ items?: Campaign[]; total?: number }>({
    queryKey: ['bedolaga-campaigns', cPage],
    queryFn: () => client.get(`/bedolaga/marketing/campaigns?limit=${perPage}&offset=${(cPage - 1) * perPage}`).then((r) => r.data),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
  const campaigns: Campaign[] = Array.isArray(cData?.items) ? cData.items : []
  const cTotal = cData?.total || 0
  const cPages = Math.max(1, Math.ceil(cTotal / perPage))

  const { data: bData, isLoading: bLoading, refetch: bRefetch } = useQuery<{ items?: Broadcast[]; total?: number }>({
    queryKey: ['bedolaga-broadcasts', bPage],
    queryFn: () => client.get(`/bedolaga/marketing/broadcasts?limit=${perPage}&offset=${(bPage - 1) * perPage}`).then((r) => r.data),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
  const broadcasts: Broadcast[] = Array.isArray(bData?.items) ? bData.items : []
  const bTotal = bData?.total || 0
  const bPages = Math.max(1, Math.ceil(bTotal / perPage))

  const { data: pData, isLoading: pLoading, refetch: pRefetch } = useQuery<{ items?: Partner[]; total?: number }>({
    queryKey: ['bedolaga-partners', pPage],
    queryFn: () => client.get(`/bedolaga/marketing/partners?limit=${perPage}&offset=${(pPage - 1) * perPage}`).then((r) => r.data),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
  const partners: Partner[] = Array.isArray(pData?.items) ? pData.items : []
  const pTotal = pData?.total || 0
  const pPages = Math.max(1, Math.ceil(pTotal / perPage))

  // ── Mutations ──

  const createCampaignMut = useMutation({
    mutationFn: (p: Record<string, unknown>) => client.post('/bedolaga/marketing/campaigns', p),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-campaigns'] }); setCampaignDialog(false); toast.success(t('bedolaga.marketing.campaignCreated')) },
    onError: () => toast.error(t('bedolaga.marketing.campaignCreateError')),
  })
  const updateCampaignMut = useMutation({
    mutationFn: ({ id, p }: { id: number; p: Record<string, unknown> }) => client.patch(`/bedolaga/marketing/campaigns/${id}`, p),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-campaigns'] }); setCampaignDialog(false); toast.success(t('bedolaga.marketing.campaignUpdated')) },
    onError: () => toast.error(t('bedolaga.marketing.campaignUpdateError')),
  })
  const deleteCampaignMut = useMutation({
    mutationFn: (id: number) => client.delete(`/bedolaga/marketing/campaigns/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-campaigns'] }); setDeleteCampaign(null); toast.success(t('bedolaga.marketing.campaignDeleted')) },
    onError: () => toast.error(t('bedolaga.marketing.campaignDeleteError')),
  })
  const createBroadcastMut = useMutation({
    mutationFn: (p: Record<string, unknown>) => client.post('/bedolaga/marketing/broadcasts', p),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-broadcasts'] }); setBroadcastDialog(false); toast.success(t('bedolaga.marketing.mailingCreated')) },
    onError: () => toast.error(t('bedolaga.marketing.mailingCreateError')),
  })
  const stopBroadcastMut = useMutation({
    mutationFn: (id: number) => client.post(`/bedolaga/marketing/broadcasts/${id}/stop`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-broadcasts'] }); toast.success(t('bedolaga.marketing.mailingCancelled')) },
    onError: () => toast.error(t('bedolaga.marketing.mailingCancelError')),
  })

  // ── Handlers ──

  const openCreateCampaign = () => {
    setEditingCampaign(null)
    setCampaignForm({ name: '', start_parameter: '', bonus_type: 'none', balance_bonus_kopeks: '', subscription_duration_days: '', is_active: true })
    setCampaignDialog(true)
  }
  const openEditCampaign = (c: Campaign) => {
    setEditingCampaign(c)
    setCampaignForm({ name: c.name, start_parameter: c.start_parameter || '', bonus_type: c.bonus_type || 'none', balance_bonus_kopeks: c.balance_bonus_kopeks?.toString() || '', subscription_duration_days: c.subscription_duration_days?.toString() || '', is_active: c.is_active ?? true })
    setCampaignDialog(true)
  }
  const submitCampaign = () => {
    const payload: Record<string, unknown> = { name: campaignForm.name, start_parameter: campaignForm.start_parameter, bonus_type: campaignForm.bonus_type, is_active: campaignForm.is_active }
    if (campaignForm.balance_bonus_kopeks) payload.balance_bonus_kopeks = parseInt(campaignForm.balance_bonus_kopeks)
    if (campaignForm.subscription_duration_days) payload.subscription_duration_days = parseInt(campaignForm.subscription_duration_days)
    if (editingCampaign) updateCampaignMut.mutate({ id: editingCampaign.id, p: payload })
    else createCampaignMut.mutate(payload)
  }
  const submitBroadcast = () => {
    createBroadcastMut.mutate({ target: broadcastForm.target, message_text: broadcastForm.message_text })
  }

  const { formatDateShort: formatDate, locale } = useFormatters()
  const formatRubles = (kopeks?: number) => kopeks ? `${(kopeks / 100).toLocaleString(locale)} ₽` : '0 ₽'
  const refetchAll = () => { cRefetch(); bRefetch(); pRefetch() }
  const cSaving = createCampaignMut.isPending || updateCampaignMut.isPending

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('bedolaga.marketing.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm">{t('bedolaga.marketing.subtitle')}</p>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" size="icon" onClick={refetchAll} disabled={cLoading || bLoading || pLoading}>
            <RefreshCw className={cn('w-5 h-5', (cLoading || bLoading || pLoading) && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-[var(--glass-bg)] border border-[var(--glass-border)]">
          <TabsTrigger value="campaigns" className="gap-1.5">
            <Megaphone className="w-4 h-4" />
            {t('bedolaga.marketing.campaigns')}
            {cTotal > 0 && <span className="text-dark-400 text-xs">({cTotal})</span>}
          </TabsTrigger>
          <TabsTrigger value="broadcasts" className="gap-1.5">
            <Mail className="w-4 h-4" />
            {t('bedolaga.marketing.mailings')}
            {bTotal > 0 && <span className="text-dark-400 text-xs">({bTotal})</span>}
          </TabsTrigger>
          <TabsTrigger value="partners" className="gap-1.5">
            <Users className="w-4 h-4" />
            {t('bedolaga.marketing.partners')}
            {pTotal > 0 && <span className="text-dark-400 text-xs">({pTotal})</span>}
          </TabsTrigger>
        </TabsList>

        {/* ── Campaigns ── */}
        <TabsContent value="campaigns" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Button onClick={openCreateCampaign} className="gap-2"><Plus className="w-4 h-4" />{t('bedolaga.marketing.createCampaign')}</Button>
          </div>
          <Card className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">{t('bedolaga.marketing.campaignName')}</th>
                    <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.marketing.bonusType')}</th>
                    <th className="text-center p-3 font-medium hidden md:table-cell">{t('bedolaga.marketing.registrations')}</th>
                    <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.status')}</th>
                    <th className="text-right p-3 font-medium">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {cLoading && !campaigns.length ? (
                    Array.from({ length: 3 }).map((_, i) => <tr key={i} className="border-b border-[var(--glass-border)]"><td className="p-3" colSpan={5}><Skeleton className="h-5 w-full" /></td></tr>)
                  ) : campaigns.length === 0 ? (
                    <tr><td colSpan={5} className="p-8 text-center text-dark-300"><Megaphone className="w-8 h-8 mx-auto mb-2 opacity-40" />{t('bedolaga.marketing.noCampaigns')}</td></tr>
                  ) : campaigns.map((c) => (
                    <tr key={c.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors">
                      <td className="p-3">
                        <span className="font-medium">{c.name}</span>
                        {c.start_parameter && <p className="text-[10px] text-dark-400 font-mono mt-0.5">{c.start_parameter}</p>}
                      </td>
                      <td className="p-3 hidden sm:table-cell text-xs">
                        <Badge className="text-[10px] bg-[var(--glass-bg-hover)]">{bonusTypeLabels[c.bonus_type || 'none'] || c.bonus_type}</Badge>
                        {c.balance_bonus_rubles ? <span className="ml-1 text-emerald-400">{c.balance_bonus_rubles} ₽</span> : null}
                        {c.subscription_duration_days ? <span className="ml-1">{c.subscription_duration_days}d</span> : null}
                      </td>
                      <td className="p-3 text-center hidden md:table-cell font-medium">{c.registrations_count ?? 0}</td>
                      <td className="p-3 hidden lg:table-cell">
                        <Badge className={cn('text-[10px]', c.is_active ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-dark-500/20 text-dark-300 border-dark-500/30')}>
                          {c.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEditCampaign(c)}><Pencil className="w-4 h-4 text-dark-300" /></Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDeleteCampaign(c)}><Trash2 className="w-4 h-4 text-dark-300 hover:text-red-400" /></Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {cPages > 1 && <Pagination page={cPage} pages={cPages} total={cTotal} perPage={perPage} onPageChange={setCPage} t={t} />}
          </Card>
        </TabsContent>

        {/* ── Broadcasts ── */}
        <TabsContent value="broadcasts" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Button onClick={() => { setBroadcastForm({ target: 'all', message_text: '' }); setBroadcastDialog(true) }} className="gap-2">
              <Plus className="w-4 h-4" />{t('bedolaga.marketing.createMailing')}
            </Button>
          </div>
          <Card className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">{t('bedolaga.marketing.audience')}</th>
                    <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.marketing.status')}</th>
                    <th className="text-center p-3 font-medium hidden md:table-cell">{t('bedolaga.marketing.progress')}</th>
                    <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.createdAt')}</th>
                    <th className="text-right p-3 font-medium">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {bLoading && !broadcasts.length ? (
                    Array.from({ length: 3 }).map((_, i) => <tr key={i} className="border-b border-[var(--glass-border)]"><td className="p-3" colSpan={5}><Skeleton className="h-5 w-full" /></td></tr>)
                  ) : broadcasts.length === 0 ? (
                    <tr><td colSpan={5} className="p-8 text-center text-dark-300"><Mail className="w-8 h-8 mx-auto mb-2 opacity-40" />{t('bedolaga.marketing.noMailings')}</td></tr>
                  ) : broadcasts.map((b) => (
                    <tr key={b.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors">
                      <td className="p-3">
                        <span className="font-medium">{b.target_type || '—'}</span>
                        {b.message_text && <p className="text-xs text-dark-300 mt-0.5 truncate max-w-[200px]">{b.message_text}</p>}
                        {b.admin_name && <p className="text-[10px] text-dark-400 mt-0.5">by {b.admin_name}</p>}
                      </td>
                      <td className="p-3 hidden sm:table-cell">
                        <Badge className={cn('text-[10px]', statusColors[b.status || ''] || statusColors.pending)}>{b.status || 'pending'}</Badge>
                      </td>
                      <td className="p-3 text-center hidden md:table-cell">
                        <span className="font-medium">{b.sent_count ?? 0}</span>
                        <span className="text-dark-400">/{b.total_count ?? 0}</span>
                        {(b.failed_count ?? 0) > 0 && <span className="text-red-400 text-xs ml-1">({b.failed_count} fail)</span>}
                      </td>
                      <td className="p-3 hidden lg:table-cell text-dark-300 text-xs">{formatDate(b.created_at)}</td>
                      <td className="p-3 text-right">
                        {b.status === 'sending' && (
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => stopBroadcastMut.mutate(b.id)} disabled={stopBroadcastMut.isPending}>
                            <Square className="w-4 h-4 text-red-400" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {bPages > 1 && <Pagination page={bPage} pages={bPages} total={bTotal} perPage={perPage} onPageChange={setBPage} t={t} />}
          </Card>
        </TabsContent>

        {/* ── Partners ── */}
        <TabsContent value="partners" className="space-y-4 mt-4">
          <Card className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">{t('bedolaga.customers.user')}</th>
                    <th className="text-center p-3 font-medium hidden sm:table-cell">{t('bedolaga.customerDetail.refInvited')}</th>
                    <th className="text-center p-3 font-medium hidden md:table-cell">%</th>
                    <th className="text-right p-3 font-medium hidden md:table-cell">{t('bedolaga.marketing.monthEarned')}</th>
                    <th className="text-right p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.totalEarned')}</th>
                    <th className="text-right p-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {pLoading && !partners.length ? (
                    Array.from({ length: 3 }).map((_, i) => <tr key={i} className="border-b border-[var(--glass-border)]"><td className="p-3" colSpan={6}><Skeleton className="h-5 w-full" /></td></tr>)
                  ) : partners.length === 0 ? (
                    <tr><td colSpan={6} className="p-8 text-center text-dark-300"><Users className="w-8 h-8 mx-auto mb-2 opacity-40" />{t('bedolaga.marketing.noPartners')}</td></tr>
                  ) : partners.map((p) => (
                    <tr key={p.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] cursor-pointer transition-colors" onClick={() => navigate(`/bedolaga/customers/${p.id}`)}>
                      <td className="p-3">
                        <span className="font-medium">{p.username || p.first_name || `#${p.id}`}</span>
                        {p.referral_code && <p className="text-[10px] text-dark-400 font-mono mt-0.5">{p.referral_code}</p>}
                      </td>
                      <td className="p-3 text-center hidden sm:table-cell">
                        <span className="font-medium">{p.invited_count ?? 0}</span>
                        {p.active_referrals != null && <span className="text-dark-400 text-xs ml-1">({p.active_referrals} act)</span>}
                      </td>
                      <td className="p-3 text-center hidden md:table-cell">
                        <Badge className="text-[10px] bg-[var(--glass-bg-hover)]">{p.effective_referral_commission_percent ?? 0}%</Badge>
                      </td>
                      <td className="p-3 text-right hidden md:table-cell text-emerald-400 text-xs font-medium tabular-nums">{formatRubles(p.month_earned_kopeks)}</td>
                      <td className="p-3 text-right hidden lg:table-cell text-xs tabular-nums">{formatRubles(p.total_earned_kopeks)}</td>
                      <td className="p-3 text-right"><ExternalLink className="w-4 h-4 text-dark-400" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pPages > 1 && <Pagination page={pPage} pages={pPages} total={pTotal} perPage={perPage} onPageChange={setPPage} t={t} />}
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Campaign dialog ── */}
      <Dialog open={campaignDialog} onOpenChange={setCampaignDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingCampaign ? t('bedolaga.marketing.editCampaign') : t('bedolaga.marketing.createCampaign')}</DialogTitle>
            <DialogDescription>{t('bedolaga.marketing.campaignDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.campaignName')}</label>
              <input value={campaignForm.name} onChange={(e) => setCampaignForm({ ...campaignForm, name: e.target.value })} className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">Start parameter (deep-link)</label>
              <input value={campaignForm.start_parameter} onChange={(e) => setCampaignForm({ ...campaignForm, start_parameter: e.target.value })} placeholder="summer2026" className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.bonusType')}</label>
              <select value={campaignForm.bonus_type} onChange={(e) => setCampaignForm({ ...campaignForm, bonus_type: e.target.value })} className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                <option value="none">—</option>
                <option value="balance">{t('bedolaga.promo.typeBalance')}</option>
                <option value="subscription">{t('bedolaga.promo.typeSubscription')}</option>
                <option value="tariff">{t('bedolaga.marketing.tariff')}</option>
              </select>
            </div>
            {campaignForm.bonus_type === 'balance' && (
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.balanceBonus')}</label>
                <input type="number" min="0" value={campaignForm.balance_bonus_kopeks} onChange={(e) => setCampaignForm({ ...campaignForm, balance_bonus_kopeks: e.target.value })} className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
              </div>
            )}
            {campaignForm.bonus_type === 'subscription' && (
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.bonusDays')}</label>
                <input type="number" min="1" value={campaignForm.subscription_duration_days} onChange={(e) => setCampaignForm({ ...campaignForm, subscription_duration_days: e.target.value })} className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
              </div>
            )}
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={campaignForm.is_active} onChange={(e) => setCampaignForm({ ...campaignForm, is_active: e.target.checked })} className="rounded border-[var(--glass-border)]" />
              <span className="text-sm">{t('bedolaga.promo.isActive')}</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setCampaignDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={submitCampaign} disabled={!campaignForm.name || !campaignForm.start_parameter || cSaving}>
              {cSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : editingCampaign ? t('common.save') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete campaign */}
      <Dialog open={!!deleteCampaign} onOpenChange={() => setDeleteCampaign(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>{t('bedolaga.marketing.deleteCampaignConfirm')}</DialogTitle></DialogHeader>
          <p className="text-sm text-dark-200 py-2">{t('bedolaga.marketing.deleteCampaignText', { name: deleteCampaign?.name })}</p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteCampaign(null)}>{t('common.cancel')}</Button>
            <Button variant="destructive" onClick={() => deleteCampaign && deleteCampaignMut.mutate(deleteCampaign.id)} disabled={deleteCampaignMut.isPending}>{t('common.delete')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Broadcast dialog */}
      <Dialog open={broadcastDialog} onOpenChange={setBroadcastDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.marketing.createMailing')}</DialogTitle>
            <DialogDescription>{t('bedolaga.marketing.broadcastDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.audience')}</label>
              <select value={broadcastForm.target} onChange={(e) => setBroadcastForm({ ...broadcastForm, target: e.target.value })} className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                <option value="all">{t('bedolaga.marketing.allUsers')}</option>
                <option value="active">{t('bedolaga.marketing.targetActive')}</option>
                <option value="trial">{t('bedolaga.marketing.targetTrial')}</option>
                <option value="no">{t('bedolaga.marketing.targetNoSub')}</option>
                <option value="expired">{t('bedolaga.marketing.targetExpired')}</option>
                <option value="expiring">{t('bedolaga.marketing.targetExpiring')}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.messageText')}</label>
              <textarea value={broadcastForm.message_text} onChange={(e) => setBroadcastForm({ ...broadcastForm, message_text: e.target.value })} rows={4} maxLength={4000} className="flex w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none" />
              <p className="text-[10px] text-dark-400 mt-1">{broadcastForm.message_text.length}/4000</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setBroadcastDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={submitBroadcast} disabled={!broadcastForm.message_text || createBroadcastMut.isPending}>
              {createBroadcastMut.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Pagination ──

function Pagination({ page, pages, total, perPage, onPageChange, t }: { page: number; pages: number; total: number; perPage: number; onPageChange: (p: number) => void; t: (key: string) => string }) {
  return (
    <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
      <span>{(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} {t('common.of')} {total}</span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page <= 1} onClick={() => onPageChange(page - 1)}><ChevronLeft className="w-4 h-4" /></Button>
        <span className="px-2">{page} / {pages}</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" disabled={page >= pages} onClick={() => onPageChange(page + 1)}><ChevronRight className="w-4 h-4" /></Button>
      </div>
    </div>
  )
}
