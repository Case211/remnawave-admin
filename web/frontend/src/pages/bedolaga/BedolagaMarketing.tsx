import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Plus,
  Pencil,
  Trash2,
  Send,
  BarChart3,
  Megaphone,
  Mail,
  XCircle,
  Clock,
  CheckCircle2,
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
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

// ── Types ──

interface Campaign {
  id: number
  name: string
  message_text?: string
  target_audience?: string
  status?: string
  scheduled_at?: string
  sent_at?: string
  promo_id?: number
  created_at?: string
}

interface CampaignStats {
  sent?: number
  delivered?: number
  read?: number
  clicked?: number
}

interface Mailing {
  id: number
  subject: string
  message_text?: string
  target_audience?: string
  status?: string
  scheduled_at?: string
  sent_count?: number
  total_count?: number
  created_at?: string
}

const statusIcons: Record<string, typeof Clock> = {
  draft: Clock,
  scheduled: Clock,
  sending: Send,
  sent: CheckCircle2,
  completed: CheckCircle2,
  cancelled: XCircle,
  failed: XCircle,
}

const statusColors: Record<string, string> = {
  draft: 'bg-dark-500/20 text-dark-300 border-dark-500/30',
  scheduled: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  sending: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  sent: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  cancelled: 'bg-red-500/20 text-red-400 border-red-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
}

const emptyCampaignForm = {
  name: '',
  message_text: '',
  target_audience: '',
  scheduled_at: '',
  promo_id: '',
}

const emptyMailingForm = {
  subject: '',
  message_text: '',
  target_audience: '',
  send_immediately: false,
  scheduled_at: '',
}

export default function BedolagaMarketing() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [tab, setTab] = useState('campaigns')
  const [cPage, setCPage] = useState(1)
  const [mPage, setMPage] = useState(1)
  const perPage = 20

  // Campaign dialogs
  const [campaignDialog, setCampaignDialog] = useState(false)
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null)
  const [campaignForm, setCampaignForm] = useState(emptyCampaignForm)
  const [deleteCampaign, setDeleteCampaign] = useState<Campaign | null>(null)
  const [sendCampaign, setSendCampaign] = useState<Campaign | null>(null)
  const [statsCampaign, setStatsCampaign] = useState<Campaign | null>(null)

  // Mailing dialogs
  const [mailingDialog, setMailingDialog] = useState(false)
  const [mailingForm, setMailingForm] = useState(emptyMailingForm)
  const [cancelMailing, setCancelMailing] = useState<Mailing | null>(null)

  // ── Campaign queries ──

  const { data: cData, isLoading: cLoading, refetch: cRefetch } = useQuery<{ items?: Campaign[]; total?: number }>({
    queryKey: ['bedolaga-campaigns', cPage, perPage],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(perPage), offset: String((cPage - 1) * perPage) })
      return client.get(`/bedolaga/marketing/campaigns?${params}`).then((r) => r.data)
    },
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  const campaigns: Campaign[] = Array.isArray(cData?.items) ? cData.items : []
  const cTotal = cData?.total || 0
  const cTotalPages = Math.max(1, Math.ceil(cTotal / perPage))

  const { data: campaignStatsData, isLoading: campaignStatsLoading } = useQuery({
    queryKey: ['bedolaga-campaign-stats', statsCampaign?.id],
    queryFn: () => client.get(`/bedolaga/marketing/campaigns/${statsCampaign!.id}/stats`).then((r) => r.data),
    enabled: !!statsCampaign,
  })

  // ── Mailing queries ──

  const { data: mData, isLoading: mLoading, refetch: mRefetch } = useQuery<{ items?: Mailing[]; total?: number }>({
    queryKey: ['bedolaga-mailings', mPage, perPage],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(perPage), offset: String((mPage - 1) * perPage) })
      return client.get(`/bedolaga/marketing/mailings?${params}`).then((r) => r.data)
    },
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  const mailings: Mailing[] = Array.isArray(mData?.items) ? mData.items : []
  const mTotal = mData?.total || 0
  const mTotalPages = Math.max(1, Math.ceil(mTotal / perPage))

  // ── Campaign mutations ──

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

  const sendCampaignMut = useMutation({
    mutationFn: (id: number) => client.post(`/bedolaga/marketing/campaigns/${id}/send`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-campaigns'] }); setSendCampaign(null); toast.success(t('bedolaga.marketing.campaignSent')) },
    onError: () => toast.error(t('bedolaga.marketing.campaignSendError')),
  })

  // ── Mailing mutations ──

  const createMailingMut = useMutation({
    mutationFn: (p: Record<string, unknown>) => client.post('/bedolaga/marketing/mailings', p),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-mailings'] }); setMailingDialog(false); toast.success(t('bedolaga.marketing.mailingCreated')) },
    onError: () => toast.error(t('bedolaga.marketing.mailingCreateError')),
  })

  const cancelMailingMut = useMutation({
    mutationFn: (id: number) => client.post(`/bedolaga/marketing/mailings/${id}/cancel`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['bedolaga-mailings'] }); setCancelMailing(null); toast.success(t('bedolaga.marketing.mailingCancelled')) },
    onError: () => toast.error(t('bedolaga.marketing.mailingCancelError')),
  })

  // ── Handlers ──

  const openCreateCampaign = () => {
    setEditingCampaign(null)
    setCampaignForm(emptyCampaignForm)
    setCampaignDialog(true)
  }

  const openEditCampaign = (c: Campaign) => {
    setEditingCampaign(c)
    setCampaignForm({
      name: c.name,
      message_text: c.message_text || '',
      target_audience: c.target_audience || '',
      scheduled_at: c.scheduled_at?.slice(0, 16) || '',
      promo_id: c.promo_id?.toString() || '',
    })
    setCampaignDialog(true)
  }

  const submitCampaign = () => {
    const payload: Record<string, unknown> = {
      name: campaignForm.name,
      message_text: campaignForm.message_text,
    }
    if (campaignForm.target_audience) payload.target_audience = campaignForm.target_audience
    if (campaignForm.scheduled_at) payload.scheduled_at = campaignForm.scheduled_at
    if (campaignForm.promo_id) payload.promo_id = parseInt(campaignForm.promo_id)

    if (editingCampaign) {
      updateCampaignMut.mutate({ id: editingCampaign.id, p: payload })
    } else {
      createCampaignMut.mutate(payload)
    }
  }

  const submitMailing = () => {
    const payload: Record<string, unknown> = {
      subject: mailingForm.subject,
      message_text: mailingForm.message_text,
      send_immediately: mailingForm.send_immediately,
    }
    if (mailingForm.target_audience) payload.target_audience = mailingForm.target_audience
    if (mailingForm.scheduled_at) payload.scheduled_at = mailingForm.scheduled_at
    createMailingMut.mutate(payload)
  }

  const formatDate = (d?: string) => {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  const StatusBadge = ({ status }: { status?: string }) => {
    const s = status || 'draft'
    const Icon = statusIcons[s] || Clock
    return (
      <Badge className={cn('text-[10px] gap-1', statusColors[s] || statusColors.draft)}>
        <Icon className="w-3 h-3" />
        {s}
      </Badge>
    )
  }

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
          <Button variant="secondary" size="icon" onClick={() => tab === 'campaigns' ? cRefetch() : mRefetch()} disabled={cLoading || mLoading}>
            <RefreshCw className={cn('w-5 h-5', (cLoading || mLoading) && 'animate-spin')} />
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
          <TabsTrigger value="mailings" className="gap-1.5">
            <Mail className="w-4 h-4" />
            {t('bedolaga.marketing.mailings')}
            {mTotal > 0 && <span className="text-dark-400 text-xs">({mTotal})</span>}
          </TabsTrigger>
        </TabsList>

        {/* ── Campaigns Tab ── */}
        <TabsContent value="campaigns" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Button onClick={openCreateCampaign} className="gap-2">
              <Plus className="w-4 h-4" />
              {t('bedolaga.marketing.createCampaign')}
            </Button>
          </div>

          <Card className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">{t('bedolaga.marketing.campaignName')}</th>
                    <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.marketing.status')}</th>
                    <th className="text-left p-3 font-medium hidden md:table-cell">{t('bedolaga.marketing.audience')}</th>
                    <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.scheduledAt')}</th>
                    <th className="text-right p-3 font-medium">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {cLoading && !campaigns.length ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="border-b border-[var(--glass-border)]">
                        <td className="p-3"><Skeleton className="h-5 w-32" /></td>
                        <td className="p-3 hidden sm:table-cell"><Skeleton className="h-5 w-16" /></td>
                        <td className="p-3 hidden md:table-cell"><Skeleton className="h-5 w-20" /></td>
                        <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-24" /></td>
                        <td className="p-3"><Skeleton className="h-5 w-20" /></td>
                      </tr>
                    ))
                  ) : campaigns.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-dark-300">
                        <Megaphone className="w-8 h-8 mx-auto mb-2 opacity-40" />
                        {t('bedolaga.marketing.noCampaigns')}
                      </td>
                    </tr>
                  ) : (
                    campaigns.map((c) => (
                      <tr key={c.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors">
                        <td className="p-3">
                          <span className="font-medium">{c.name}</span>
                          {c.message_text && (
                            <p className="text-xs text-dark-300 mt-0.5 truncate max-w-[200px]">{c.message_text}</p>
                          )}
                        </td>
                        <td className="p-3 hidden sm:table-cell"><StatusBadge status={c.status} /></td>
                        <td className="p-3 hidden md:table-cell text-dark-300 text-xs">{c.target_audience || t('bedolaga.marketing.allUsers')}</td>
                        <td className="p-3 hidden lg:table-cell text-dark-300 text-xs">{formatDate(c.scheduled_at)}</td>
                        <td className="p-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setStatsCampaign(c)}>
                              <BarChart3 className="w-4 h-4 text-dark-300 hover:text-white" />
                            </Button>
                            {(!c.status || c.status === 'draft') && (
                              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setSendCampaign(c)}>
                                <Send className="w-4 h-4 text-dark-300 hover:text-emerald-400" />
                              </Button>
                            )}
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEditCampaign(c)}>
                              <Pencil className="w-4 h-4 text-dark-300 hover:text-white" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDeleteCampaign(c)}>
                              <Trash2 className="w-4 h-4 text-dark-300 hover:text-red-400" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {cTotalPages > 1 && (
              <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
                <span>{(cPage - 1) * perPage + 1}–{Math.min(cPage * perPage, cTotal)} {t('common.of')} {cTotal}</span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" disabled={cPage <= 1} onClick={() => setCPage(cPage - 1)}><ChevronLeft className="w-4 h-4" /></Button>
                  <span className="px-2">{cPage} / {cTotalPages}</span>
                  <Button variant="ghost" size="icon" disabled={cPage >= cTotalPages} onClick={() => setCPage(cPage + 1)}><ChevronRight className="w-4 h-4" /></Button>
                </div>
              </div>
            )}
          </Card>
        </TabsContent>

        {/* ── Mailings Tab ── */}
        <TabsContent value="mailings" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Button onClick={() => { setMailingForm(emptyMailingForm); setMailingDialog(true) }} className="gap-2">
              <Plus className="w-4 h-4" />
              {t('bedolaga.marketing.createMailing')}
            </Button>
          </div>

          <Card className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">{t('bedolaga.marketing.mailingSubject')}</th>
                    <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.marketing.status')}</th>
                    <th className="text-left p-3 font-medium hidden md:table-cell">{t('bedolaga.marketing.audience')}</th>
                    <th className="text-center p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.progress')}</th>
                    <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.marketing.createdAt')}</th>
                    <th className="text-right p-3 font-medium">{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {mLoading && !mailings.length ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="border-b border-[var(--glass-border)]">
                        <td className="p-3"><Skeleton className="h-5 w-32" /></td>
                        <td className="p-3 hidden sm:table-cell"><Skeleton className="h-5 w-16" /></td>
                        <td className="p-3 hidden md:table-cell"><Skeleton className="h-5 w-20" /></td>
                        <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-16" /></td>
                        <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-20" /></td>
                        <td className="p-3"><Skeleton className="h-5 w-12" /></td>
                      </tr>
                    ))
                  ) : mailings.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-dark-300">
                        <Mail className="w-8 h-8 mx-auto mb-2 opacity-40" />
                        {t('bedolaga.marketing.noMailings')}
                      </td>
                    </tr>
                  ) : (
                    mailings.map((m) => (
                      <tr key={m.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors">
                        <td className="p-3">
                          <span className="font-medium">{m.subject}</span>
                          {m.message_text && (
                            <p className="text-xs text-dark-300 mt-0.5 truncate max-w-[200px]">{m.message_text}</p>
                          )}
                        </td>
                        <td className="p-3 hidden sm:table-cell"><StatusBadge status={m.status} /></td>
                        <td className="p-3 hidden md:table-cell text-dark-300 text-xs">{m.target_audience || t('bedolaga.marketing.allUsers')}</td>
                        <td className="p-3 text-center hidden lg:table-cell">
                          {m.total_count ? (
                            <span className="font-medium">{m.sent_count ?? 0}<span className="text-dark-400">/{m.total_count}</span></span>
                          ) : '—'}
                        </td>
                        <td className="p-3 hidden lg:table-cell text-dark-300 text-xs">{formatDate(m.created_at)}</td>
                        <td className="p-3 text-right">
                          {m.status === 'sending' || m.status === 'scheduled' ? (
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setCancelMailing(m)}>
                              <XCircle className="w-4 h-4 text-dark-300 hover:text-red-400" />
                            </Button>
                          ) : null}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {mTotalPages > 1 && (
              <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
                <span>{(mPage - 1) * perPage + 1}–{Math.min(mPage * perPage, mTotal)} {t('common.of')} {mTotal}</span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" disabled={mPage <= 1} onClick={() => setMPage(mPage - 1)}><ChevronLeft className="w-4 h-4" /></Button>
                  <span className="px-2">{mPage} / {mTotalPages}</span>
                  <Button variant="ghost" size="icon" disabled={mPage >= mTotalPages} onClick={() => setMPage(mPage + 1)}><ChevronRight className="w-4 h-4" /></Button>
                </div>
              </div>
            )}
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Campaign Create/Edit Dialog ── */}
      <Dialog open={campaignDialog} onOpenChange={setCampaignDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingCampaign ? t('bedolaga.marketing.editCampaign') : t('bedolaga.marketing.createCampaign')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.campaignName')}</label>
              <input
                value={campaignForm.name}
                onChange={(e) => setCampaignForm({ ...campaignForm, name: e.target.value })}
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.messageText')}</label>
              <textarea
                value={campaignForm.message_text}
                onChange={(e) => setCampaignForm({ ...campaignForm, message_text: e.target.value })}
                rows={4}
                className="flex w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.audience')}</label>
                <input
                  value={campaignForm.target_audience}
                  onChange={(e) => setCampaignForm({ ...campaignForm, target_audience: e.target.value })}
                  placeholder={t('bedolaga.marketing.allUsers')}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.scheduledAt')}</label>
                <input
                  type="datetime-local"
                  value={campaignForm.scheduled_at}
                  onChange={(e) => setCampaignForm({ ...campaignForm, scheduled_at: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.promoId')}</label>
              <input
                type="number"
                value={campaignForm.promo_id}
                onChange={(e) => setCampaignForm({ ...campaignForm, promo_id: e.target.value })}
                placeholder={t('bedolaga.marketing.promoIdPlaceholder')}
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setCampaignDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={submitCampaign} disabled={!campaignForm.name || !campaignForm.message_text || cSaving}>
              {cSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : editingCampaign ? t('common.save') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Campaign delete confirm */}
      <Dialog open={!!deleteCampaign} onOpenChange={() => setDeleteCampaign(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>{t('bedolaga.marketing.deleteCampaignConfirm')}</DialogTitle></DialogHeader>
          <p className="text-sm text-dark-200 py-2">{t('bedolaga.marketing.deleteCampaignText', { name: deleteCampaign?.name })}</p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteCampaign(null)}>{t('common.cancel')}</Button>
            <Button variant="destructive" onClick={() => deleteCampaign && deleteCampaignMut.mutate(deleteCampaign.id)} disabled={deleteCampaignMut.isPending}>
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Campaign send confirm */}
      <Dialog open={!!sendCampaign} onOpenChange={() => setSendCampaign(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>{t('bedolaga.marketing.sendCampaignConfirm')}</DialogTitle></DialogHeader>
          <p className="text-sm text-dark-200 py-2">{t('bedolaga.marketing.sendCampaignText', { name: sendCampaign?.name })}</p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setSendCampaign(null)}>{t('common.cancel')}</Button>
            <Button onClick={() => sendCampaign && sendCampaignMut.mutate(sendCampaign.id)} disabled={sendCampaignMut.isPending} className="gap-1.5">
              <Send className="w-4 h-4" />
              {t('bedolaga.marketing.send')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Campaign stats dialog */}
      <Dialog open={!!statsCampaign} onOpenChange={() => setStatsCampaign(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.marketing.campaignStats')}: {statsCampaign?.name}</DialogTitle>
          </DialogHeader>
          {campaignStatsLoading ? (
            <div className="space-y-3 py-4"><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-3/4" /></div>
          ) : campaignStatsData ? (
            <div className="grid grid-cols-2 gap-3 py-4">
              {['sent', 'delivered', 'read', 'clicked'].map((key) => (
                <div key={key} className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                  <p className="text-xs text-dark-300">{t(`bedolaga.marketing.stat_${key}`)}</p>
                  <p className="text-lg font-semibold">{(campaignStatsData as CampaignStats)[key as keyof CampaignStats] ?? 0}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-dark-300 py-4">{t('bedolaga.marketing.noStats')}</p>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Mailing Create Dialog ── */}
      <Dialog open={mailingDialog} onOpenChange={setMailingDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{t('bedolaga.marketing.createMailing')}</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.mailingSubject')}</label>
              <input
                value={mailingForm.subject}
                onChange={(e) => setMailingForm({ ...mailingForm, subject: e.target.value })}
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.messageText')}</label>
              <textarea
                value={mailingForm.message_text}
                onChange={(e) => setMailingForm({ ...mailingForm, message_text: e.target.value })}
                rows={4}
                className="flex w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.audience')}</label>
                <input
                  value={mailingForm.target_audience}
                  onChange={(e) => setMailingForm({ ...mailingForm, target_audience: e.target.value })}
                  placeholder={t('bedolaga.marketing.allUsers')}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.marketing.scheduledAt')}</label>
                <input
                  type="datetime-local"
                  value={mailingForm.scheduled_at}
                  onChange={(e) => setMailingForm({ ...mailingForm, scheduled_at: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={mailingForm.send_immediately}
                onChange={(e) => setMailingForm({ ...mailingForm, send_immediately: e.target.checked })}
                className="rounded border-[var(--glass-border)]"
              />
              <span className="text-sm">{t('bedolaga.marketing.sendImmediately')}</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setMailingDialog(false)}>{t('common.cancel')}</Button>
            <Button onClick={submitMailing} disabled={!mailingForm.subject || !mailingForm.message_text || createMailingMut.isPending}>
              {createMailingMut.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mailing cancel confirm */}
      <Dialog open={!!cancelMailing} onOpenChange={() => setCancelMailing(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>{t('bedolaga.marketing.cancelMailingConfirm')}</DialogTitle></DialogHeader>
          <p className="text-sm text-dark-200 py-2">{t('bedolaga.marketing.cancelMailingText', { subject: cancelMailing?.subject })}</p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setCancelMailing(null)}>{t('common.cancel')}</Button>
            <Button variant="destructive" onClick={() => cancelMailing && cancelMailingMut.mutate(cancelMailing.id)} disabled={cancelMailingMut.isPending}>
              {t('bedolaga.marketing.cancelMailing')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
