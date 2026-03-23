import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Search,
  RefreshCw,
  Filter,
  ChevronLeft,
  ChevronRight,
  Plus,
  Pencil,
  Trash2,
  BarChart3,
  Ticket,
  Copy,
  Check,
} from 'lucide-react'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface Promo {
  id: number
  code: string
  discount_percent?: number
  discount_amount_kopeks?: number
  bonus_days?: number
  bonus_traffic_gb?: number
  max_uses?: number
  used_count?: number
  is_active?: boolean
  expires_at?: string
  description?: string
  created_at?: string
}

interface PromoStats {
  total_uses?: number
  unique_users?: number
  total_discount_kopeks?: number
  conversions?: number
}

const emptyForm = {
  code: '',
  discount_percent: '',
  discount_amount_kopeks: '',
  bonus_days: '',
  bonus_traffic_gb: '',
  max_uses: '',
  expires_at: '',
  is_active: true,
  description: '',
}

export default function BedolagaPromo() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterActive, setFilterActive] = useState('')
  const [page, setPage] = useState(1)
  const [showFilters, setShowFilters] = useState(false)
  const perPage = 20

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingPromo, setEditingPromo] = useState<Promo | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [deleteConfirm, setDeleteConfirm] = useState<Promo | null>(null)
  const [statsPromo, setStatsPromo] = useState<Promo | null>(null)
  const [copiedCode, setCopiedCode] = useState<number | null>(null)

  const handleSearch = useCallback((value: string) => {
    setSearch(value)
    const timeout = setTimeout(() => {
      setDebouncedSearch(value)
      setPage(1)
    }, 400)
    return () => clearTimeout(timeout)
  }, [])

  // ── Queries ──

  const { data, isLoading, refetch } = useQuery<{ items?: Promo[]; total?: number }>({
    queryKey: ['bedolaga-promos', page, perPage, debouncedSearch, filterActive],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('limit', String(perPage))
      params.set('offset', String((page - 1) * perPage))
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (filterActive) params.set('is_active', filterActive)
      return client.get(`/bedolaga/promo?${params}`).then((r) => r.data)
    },
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['bedolaga-promo-stats', statsPromo?.id],
    queryFn: () => client.get(`/bedolaga/promo/${statsPromo!.id}/stats`).then((r) => r.data),
    enabled: !!statsPromo,
  })

  const promos: Promo[] = Array.isArray(data?.items) ? data.items : []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  // ── Mutations ──

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => client.post('/bedolaga/promo', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-promos'] })
      setDialogOpen(false)
      toast.success(t('bedolaga.promo.created'))
    },
    onError: () => toast.error(t('bedolaga.promo.createError')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) =>
      client.patch(`/bedolaga/promo/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-promos'] })
      setDialogOpen(false)
      toast.success(t('bedolaga.promo.updated'))
    },
    onError: () => toast.error(t('bedolaga.promo.updateError')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => client.delete(`/bedolaga/promo/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedolaga-promos'] })
      setDeleteConfirm(null)
      toast.success(t('bedolaga.promo.deleted'))
    },
    onError: () => toast.error(t('bedolaga.promo.deleteError')),
  })

  // ── Handlers ──

  const openCreate = () => {
    setEditingPromo(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEdit = (promo: Promo) => {
    setEditingPromo(promo)
    setForm({
      code: promo.code,
      discount_percent: promo.discount_percent?.toString() || '',
      discount_amount_kopeks: promo.discount_amount_kopeks?.toString() || '',
      bonus_days: promo.bonus_days?.toString() || '',
      bonus_traffic_gb: promo.bonus_traffic_gb?.toString() || '',
      max_uses: promo.max_uses?.toString() || '',
      expires_at: promo.expires_at?.slice(0, 16) || '',
      is_active: promo.is_active ?? true,
      description: promo.description || '',
    })
    setDialogOpen(true)
  }

  const handleSubmit = () => {
    const payload: Record<string, unknown> = { code: form.code }
    if (form.discount_percent) payload.discount_percent = parseInt(form.discount_percent)
    if (form.discount_amount_kopeks) payload.discount_amount_kopeks = parseInt(form.discount_amount_kopeks)
    if (form.bonus_days) payload.bonus_days = parseInt(form.bonus_days)
    if (form.bonus_traffic_gb) payload.bonus_traffic_gb = parseFloat(form.bonus_traffic_gb)
    if (form.max_uses) payload.max_uses = parseInt(form.max_uses)
    if (form.expires_at) payload.expires_at = form.expires_at
    if (form.description) payload.description = form.description
    payload.is_active = form.is_active

    if (editingPromo) {
      updateMutation.mutate({ id: editingPromo.id, payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const copyCode = (promo: Promo) => {
    navigator.clipboard.writeText(promo.code)
    setCopiedCode(promo.id)
    setTimeout(() => setCopiedCode(null), 1500)
  }

  const formatDate = (d?: string) => {
    if (!d) return '—'
    return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  }

  const formatRubles = (kopeks?: number) => {
    if (!kopeks) return '0 ₽'
    return `${(kopeks / 100).toLocaleString('ru-RU')} ₽`
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('bedolaga.promo.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm">
            {t('bedolaga.promo.subtitle')}
            {total > 0 && <span className="text-dark-300 ml-1">({total})</span>}
          </p>
        </div>
        <div className="page-header-actions">
          <Button onClick={openCreate} className="gap-2">
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">{t('bedolaga.promo.create')}</span>
          </Button>
          <Button variant="secondary" onClick={() => setShowFilters(!showFilters)} className={cn('gap-2', showFilters && 'ring-2 ring-primary-500')}>
            <Filter className="w-4 h-4" />
            <span className="hidden sm:inline">{t('common.filters')}</span>
          </Button>
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('w-5 h-5', isLoading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
        <input
          type="text"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder={t('bedolaga.promo.searchPlaceholder')}
          className="w-full h-10 pl-10 pr-4 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] text-sm placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
        />
      </div>

      {/* Filters */}
      {showFilters && (
        <Card className="glass-card animate-fade-in-down">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.status')}</label>
                <select value={filterActive} onChange={(e) => { setFilterActive(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                  <option value="">{t('common.all')}</option>
                  <option value="true">{t('bedolaga.promo.active')}</option>
                  <option value="false">{t('bedolaga.promo.inactive')}</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--glass-border)] text-dark-300 text-xs uppercase tracking-wider">
                <th className="text-left p-3 font-medium">{t('bedolaga.promo.code')}</th>
                <th className="text-left p-3 font-medium hidden sm:table-cell">{t('bedolaga.promo.discount')}</th>
                <th className="text-left p-3 font-medium hidden md:table-cell">{t('bedolaga.promo.bonus')}</th>
                <th className="text-center p-3 font-medium hidden lg:table-cell">{t('bedolaga.promo.uses')}</th>
                <th className="text-left p-3 font-medium hidden lg:table-cell">{t('bedolaga.promo.expires')}</th>
                <th className="text-right p-3 font-medium">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !promos.length ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--glass-border)]">
                    <td className="p-3"><Skeleton className="h-5 w-24" /></td>
                    <td className="p-3 hidden sm:table-cell"><Skeleton className="h-5 w-16" /></td>
                    <td className="p-3 hidden md:table-cell"><Skeleton className="h-5 w-20" /></td>
                    <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-12" /></td>
                    <td className="p-3 hidden lg:table-cell"><Skeleton className="h-5 w-20" /></td>
                    <td className="p-3"><Skeleton className="h-5 w-20" /></td>
                  </tr>
                ))
              ) : promos.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-dark-300">
                    <Ticket className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    {t('bedolaga.promo.noResults')}
                  </td>
                </tr>
              ) : (
                promos.map((promo) => (
                  <tr key={promo.id} className="border-b border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)] transition-colors">
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <code className="font-mono font-medium text-primary-400">{promo.code}</code>
                        <button onClick={() => copyCode(promo)} className="text-dark-400 hover:text-white transition-colors">
                          {copiedCode === promo.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                        <Badge className={cn('text-[10px]', promo.is_active ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-dark-500/20 text-dark-300 border-dark-500/30')}>
                          {promo.is_active ? t('bedolaga.promo.active') : t('bedolaga.promo.inactive')}
                        </Badge>
                      </div>
                      {promo.description && <p className="text-xs text-dark-300 mt-0.5">{promo.description}</p>}
                    </td>
                    <td className="p-3 hidden sm:table-cell">
                      {promo.discount_percent ? `${promo.discount_percent}%` : promo.discount_amount_kopeks ? formatRubles(promo.discount_amount_kopeks) : '—'}
                    </td>
                    <td className="p-3 hidden md:table-cell text-xs">
                      {promo.bonus_days ? `+${promo.bonus_days} ${t('bedolaga.promo.days')}` : ''}
                      {promo.bonus_days && promo.bonus_traffic_gb ? ', ' : ''}
                      {promo.bonus_traffic_gb ? `+${promo.bonus_traffic_gb} GB` : ''}
                      {!promo.bonus_days && !promo.bonus_traffic_gb && '—'}
                    </td>
                    <td className="p-3 text-center hidden lg:table-cell">
                      <span className="font-medium">{promo.used_count ?? 0}</span>
                      {promo.max_uses && <span className="text-dark-400">/{promo.max_uses}</span>}
                    </td>
                    <td className="p-3 hidden lg:table-cell text-dark-300 text-xs">
                      {formatDate(promo.expires_at)}
                    </td>
                    <td className="p-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setStatsPromo(promo)}>
                          <BarChart3 className="w-4 h-4 text-dark-300 hover:text-white" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(promo)}>
                          <Pencil className="w-4 h-4 text-dark-300 hover:text-white" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setDeleteConfirm(promo)}>
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

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-3 border-t border-[var(--glass-border)] text-xs text-dark-300">
            <span>
              {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} {t('common.of')} {total}
            </span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="px-2">{page} / {totalPages}</span>
              <Button variant="ghost" size="icon" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingPromo ? t('bedolaga.promo.edit') : t('bedolaga.promo.create')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.code')}</label>
              <input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                placeholder="SUMMER2026"
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.discountPercent')}</label>
                <input
                  type="number" min="0" max="100"
                  value={form.discount_percent}
                  onChange={(e) => setForm({ ...form, discount_percent: e.target.value })}
                  placeholder="0"
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.discountAmount')}</label>
                <input
                  type="number" min="0"
                  value={form.discount_amount_kopeks}
                  onChange={(e) => setForm({ ...form, discount_amount_kopeks: e.target.value })}
                  placeholder={t('bedolaga.promo.inKopeks')}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.bonusDays')}</label>
                <input
                  type="number" min="0"
                  value={form.bonus_days}
                  onChange={(e) => setForm({ ...form, bonus_days: e.target.value })}
                  placeholder="0"
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.bonusTraffic')}</label>
                <input
                  type="number" min="0" step="0.1"
                  value={form.bonus_traffic_gb}
                  onChange={(e) => setForm({ ...form, bonus_traffic_gb: e.target.value })}
                  placeholder="0 GB"
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.maxUses')}</label>
                <input
                  type="number" min="0"
                  value={form.max_uses}
                  onChange={(e) => setForm({ ...form, max_uses: e.target.value })}
                  placeholder={t('bedolaga.promo.unlimited')}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.expiresAt')}</label>
                <input
                  type="datetime-local"
                  value={form.expires_at}
                  onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">{t('bedolaga.promo.description')}</label>
              <input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder={t('bedolaga.promo.descriptionPlaceholder')}
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="rounded border-[var(--glass-border)]"
              />
              <span className="text-sm">{t('bedolaga.promo.isActive')}</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleSubmit} disabled={!form.code || isSaving}>
              {isSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : editingPromo ? t('common.save') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.promo.deleteConfirm')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-dark-200 py-2">
            {t('bedolaga.promo.deleteConfirmText', { code: deleteConfirm?.code })}
          </p>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>{t('common.cancel')}</Button>
            <Button variant="destructive" onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.id)} disabled={deleteMutation.isPending}>
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Stats dialog */}
      <Dialog open={!!statsPromo} onOpenChange={() => setStatsPromo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('bedolaga.promo.stats')}: <code className="text-primary-400">{statsPromo?.code}</code></DialogTitle>
          </DialogHeader>
          {statsLoading ? (
            <div className="space-y-3 py-4">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : statsData ? (
            <div className="grid grid-cols-2 gap-3 py-4">
              <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <p className="text-xs text-dark-300">{t('bedolaga.promo.totalUses')}</p>
                <p className="text-lg font-semibold">{(statsData as PromoStats).total_uses ?? 0}</p>
              </div>
              <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <p className="text-xs text-dark-300">{t('bedolaga.promo.uniqueUsers')}</p>
                <p className="text-lg font-semibold">{(statsData as PromoStats).unique_users ?? 0}</p>
              </div>
              <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <p className="text-xs text-dark-300">{t('bedolaga.promo.totalDiscount')}</p>
                <p className="text-lg font-semibold">{formatRubles((statsData as PromoStats).total_discount_kopeks)}</p>
              </div>
              <div className="p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]">
                <p className="text-xs text-dark-300">{t('bedolaga.promo.conversions')}</p>
                <p className="text-lg font-semibold">{(statsData as PromoStats).conversions ?? 0}</p>
              </div>
            </div>
          ) : (
            <p className="text-dark-300 py-4">{t('bedolaga.promo.noStats')}</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
