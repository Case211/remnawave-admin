import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ShieldBan, Plus, Trash2, RefreshCw, Upload,
  Fingerprint, AlertTriangle, Ban, User,
  ShieldOff, ShieldCheck, Calendar,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { toast } from 'sonner'
import { useHasPermission } from '../components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useFormatters } from '@/lib/useFormatters'
import { cn } from '@/lib/utils'
import type { WhitelistItem } from '@/types/violations'

// ── Types ─────────────────────────────────────────────────────────

interface BlockedIP {
  id: number
  ip_cidr: string
  reason: string | null
  added_by_username: string | null
  country_code: string | null
  asn_org: string | null
  expires_at: string | null
  created_at: string | null
}

interface BlockedIPListResponse {
  items: BlockedIP[]
  total: number
}

// ── API ───────────────────────────────────────────────────────────

const DURATION_OPTIONS: { value: string; hours: number | null }[] = [
  { value: 'forever', hours: null },
  { value: '1h', hours: 1 },
  { value: '24h', hours: 24 },
  { value: '7d', hours: 168 },
  { value: '30d', hours: 720 },
]

const fetchBlockedIPs = async (limit: number, offset: number): Promise<BlockedIPListResponse> => {
  const { data } = await client.get('/blocked-ips', { params: { limit, offset } })
  return data
}

const fetchWhitelist = async (limit: number, offset: number): Promise<{ items: WhitelistItem[]; total: number }> => {
  const { data } = await client.get('/violations/whitelist', { params: { limit, offset } })
  return data
}

const ANALYZER_KEYS = ['temporal', 'geo', 'asn', 'profile', 'device', 'hwid'] as const

const PAGE_SIZE = 50

// ══════════════════════════════════════════════════════════════════
// Blocked IPs Tab
// ══════════════════════════════════════════════════════════════════

function BlockedIPsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const canCreate = useHasPermission('blocked_ips', 'create')
  const canDelete = useHasPermission('blocked_ips', 'delete')

  const [offset, setOffset] = useState(0)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<BlockedIP | null>(null)

  const [addIpCidr, setAddIpCidr] = useState('')
  const [addReason, setAddReason] = useState('')
  const [addDuration, setAddDuration] = useState('forever')

  const [bulkIps, setBulkIps] = useState('')
  const [bulkReason, setBulkReason] = useState('')
  const [bulkDuration, setBulkDuration] = useState('forever')

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['blocked-ips', offset],
    queryFn: () => fetchBlockedIPs(PAGE_SIZE, offset),
    placeholderData: (prev) => prev,
  })

  const items = Array.isArray(data?.items) ? data.items : []
  const total = data?.total ?? 0

  const addMutation = useMutation({
    mutationFn: (body: { ip_cidr: string; reason?: string; expires_in_hours?: number | null }) =>
      client.post('/blocked-ips', body),
    onSuccess: () => {
      toast.success(t('blockedIPs.addSuccess'))
      queryClient.invalidateQueries({ queryKey: ['blocked-ips'] })
      resetAddForm()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || t('blockedIPs.addError'))
    },
  })

  const bulkMutation = useMutation({
    mutationFn: (body: { ips: string[]; reason?: string; expires_in_hours?: number | null }) =>
      client.post('/blocked-ips/bulk', body),
    onSuccess: () => {
      toast.success(t('blockedIPs.bulkSuccess'))
      queryClient.invalidateQueries({ queryKey: ['blocked-ips'] })
      resetBulkForm()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || t('blockedIPs.bulkError'))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => client.delete(`/blocked-ips/${id}`),
    onSuccess: () => {
      toast.success(t('blockedIPs.deleteSuccess'))
      queryClient.invalidateQueries({ queryKey: ['blocked-ips'] })
      setDeleteTarget(null)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || t('blockedIPs.deleteError'))
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => client.post('/blocked-ips/sync'),
    onSuccess: () => {
      toast.success(t('blockedIPs.syncSuccess'))
      queryClient.invalidateQueries({ queryKey: ['blocked-ips'] })
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || t('blockedIPs.syncError'))
    },
  })

  const getDurationHours = (value: string): number | null => {
    return DURATION_OPTIONS.find((d) => d.value === value)?.hours ?? null
  }

  const resetAddForm = useCallback(() => {
    setAddDialogOpen(false)
    setAddIpCidr('')
    setAddReason('')
    setAddDuration('forever')
  }, [])

  const resetBulkForm = useCallback(() => {
    setBulkDialogOpen(false)
    setBulkIps('')
    setBulkReason('')
    setBulkDuration('forever')
  }, [])

  const handleAdd = () => {
    if (!addIpCidr.trim()) return
    const hours = getDurationHours(addDuration)
    addMutation.mutate({
      ip_cidr: addIpCidr.trim(),
      reason: addReason.trim() || undefined,
      expires_in_hours: hours,
    })
  }

  const handleBulk = () => {
    const ips = bulkIps.split('\n').map((l) => l.trim()).filter(Boolean)
    if (ips.length === 0) return
    const hours = getDurationHours(bulkDuration)
    bulkMutation.mutate({
      ips,
      reason: bulkReason.trim() || undefined,
      expires_in_hours: hours,
    })
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    try { return new Date(dateStr).toLocaleString() } catch { return dateStr }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2">
        {canCreate && (
          <>
            <Button size="sm" onClick={() => setAddDialogOpen(true)}>
              <Plus className="mr-1 h-4 w-4" />
              {t('blockedIPs.addIP')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setBulkDialogOpen(true)}>
              <Upload className="mr-1 h-4 w-4" />
              {t('blockedIPs.bulkBlock')}
            </Button>
          </>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
        >
          <RefreshCw className={`mr-1 h-4 w-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
          {t('blockedIPs.sync')}
        </Button>
        {!isLoading && (
          <span className="text-sm text-muted-foreground ml-auto">({total})</span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('blockedIPs.columns.ipCidr')}</TableHead>
              <TableHead className="hidden sm:table-cell">{t('blockedIPs.columns.country')}</TableHead>
              <TableHead className="hidden md:table-cell">{t('blockedIPs.columns.asnProvider')}</TableHead>
              <TableHead>{t('blockedIPs.columns.reason')}</TableHead>
              <TableHead className="hidden lg:table-cell">{t('blockedIPs.columns.addedBy')}</TableHead>
              <TableHead className="hidden md:table-cell">{t('blockedIPs.columns.created')}</TableHead>
              <TableHead className="hidden lg:table-cell">{t('blockedIPs.columns.expires')}</TableHead>
              {canDelete && <TableHead className="w-[60px]">{t('blockedIPs.columns.actions')}</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                  <TableCell className="hidden sm:table-cell"><Skeleton className="h-4 w-8" /></TableCell>
                  <TableCell className="hidden md:table-cell"><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                  <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell className="hidden md:table-cell"><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-24" /></TableCell>
                  {canDelete && <TableCell><Skeleton className="h-8 w-8" /></TableCell>}
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={canDelete ? 8 : 7} className="py-12 text-center text-muted-foreground">
                  {t('blockedIPs.empty')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono text-sm">{item.ip_cidr}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {item.country_code ? <span title={item.country_code}>{item.country_code}</span> : '—'}
                  </TableCell>
                  <TableCell className="hidden md:table-cell max-w-[200px] truncate">{item.asn_org || '—'}</TableCell>
                  <TableCell className="max-w-[150px] truncate">{item.reason || '—'}</TableCell>
                  <TableCell className="hidden lg:table-cell">{item.added_by_username || '—'}</TableCell>
                  <TableCell className="hidden md:table-cell text-xs text-muted-foreground">{formatDate(item.created_at)}</TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                    {item.expires_at ? formatDate(item.expires_at) : t('blockedIPs.forever')}
                  </TableCell>
                  {canDelete && (
                    <TableCell>
                      <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500 hover:text-red-600" onClick={() => setDeleteTarget(item)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{t('blockedIPs.pagination', { current: currentPage, total: totalPages })}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0 || isFetching} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              {t('common.previous')}
            </Button>
            <Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= total || isFetching} onClick={() => setOffset(offset + PAGE_SIZE)}>
              {t('common.next')}
            </Button>
          </div>
        </div>
      )}

      {/* Add IP Dialog */}
      <Dialog open={addDialogOpen} onOpenChange={(open) => { if (!open) resetAddForm(); else setAddDialogOpen(true) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('blockedIPs.addDialog.title')}</DialogTitle>
            <DialogDescription>{t('blockedIPs.addDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="add-ip">{t('blockedIPs.addDialog.ipCidr')}</Label>
              <Input id="add-ip" placeholder="192.168.1.0/24" value={addIpCidr} onChange={(e) => setAddIpCidr(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="add-reason">{t('blockedIPs.addDialog.reason')}</Label>
              <Input id="add-reason" placeholder={t('blockedIPs.addDialog.reasonPlaceholder')} value={addReason} onChange={(e) => setAddReason(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t('blockedIPs.addDialog.duration')}</Label>
              <Select value={addDuration} onValueChange={setAddDuration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DURATION_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{t(`blockedIPs.durations.${opt.value}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetAddForm}>{t('common.cancel')}</Button>
            <Button onClick={handleAdd} disabled={!addIpCidr.trim() || addMutation.isPending}>
              {addMutation.isPending ? t('common.loading') : t('blockedIPs.addDialog.submit')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Block Dialog */}
      <Dialog open={bulkDialogOpen} onOpenChange={(open) => { if (!open) resetBulkForm(); else setBulkDialogOpen(true) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('blockedIPs.bulkDialog.title')}</DialogTitle>
            <DialogDescription>{t('blockedIPs.bulkDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bulk-ips">{t('blockedIPs.bulkDialog.ips')}</Label>
              <textarea
                id="bulk-ips"
                className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                placeholder={t('blockedIPs.bulkDialog.ipsPlaceholder')}
                value={bulkIps}
                onChange={(e) => setBulkIps(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bulk-reason">{t('blockedIPs.bulkDialog.reason')}</Label>
              <Input id="bulk-reason" placeholder={t('blockedIPs.addDialog.reasonPlaceholder')} value={bulkReason} onChange={(e) => setBulkReason(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t('blockedIPs.bulkDialog.duration')}</Label>
              <Select value={bulkDuration} onValueChange={setBulkDuration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DURATION_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{t(`blockedIPs.durations.${opt.value}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetBulkForm}>{t('common.cancel')}</Button>
            <Button onClick={handleBulk} disabled={!bulkIps.trim() || bulkMutation.isPending}>
              {bulkMutation.isPending ? t('common.loading') : t('blockedIPs.bulkDialog.submit')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}
        title={t('blockedIPs.deleteDialog.title')}
        description={t('blockedIPs.deleteDialog.description', { ip: deleteTarget?.ip_cidr })}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget.id) }}
      />
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// HWID Blacklist Tab
// ══════════════════════════════════════════════════════════════════

function HwidBlacklistTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('violations', 'create')
  const [addOpen, setAddOpen] = useState(false)
  const [newHwid, setNewHwid] = useState('')
  const [newAction, setNewAction] = useState<'alert' | 'block'>('alert')
  const [newReason, setNewReason] = useState('')
  const [expandedHwid, setExpandedHwid] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['hwid-blacklist'],
    queryFn: async () => {
      const { data } = await client.get('/violations/hwid-blacklist')
      return data as { items: Array<{ id: number; hwid: string; action: string; reason: string | null; added_by_username: string | null; created_at: string }>; total: number }
    },
  })

  const { data: usersData } = useQuery({
    queryKey: ['hwid-blacklist-users', expandedHwid],
    queryFn: async () => {
      const { data } = await client.get(`/violations/hwid-blacklist/${expandedHwid}/users`)
      return data as { users: Array<{ user_uuid: string; username: string | null; status: string | null; platform: string | null; device_model: string | null }>; total: number }
    },
    enabled: !!expandedHwid,
  })

  const addMutation = useMutation({
    mutationFn: () => client.post('/violations/hwid-blacklist', { hwid: newHwid.trim(), action: newAction, reason: newReason.trim() || null }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['hwid-blacklist'] })
      const affected = (res.data as { affected_users?: number })?.affected_users || 0
      toast.success(t('violations.hwidBlacklist.added', { count: affected }))
      setAddOpen(false)
      setNewHwid('')
      setNewAction('alert')
      setNewReason('')
    },
    onError: () => toast.error(t('common.error')),
  })

  const removeMutation = useMutation({
    mutationFn: (hwid: string) => client.delete(`/violations/hwid-blacklist/${hwid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hwid-blacklist'] })
      toast.success(t('violations.hwidBlacklist.removed'))
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-white">{t('violations.hwidBlacklist.title')}</h3>
          <p className="text-xs text-dark-300 mt-0.5">{t('violations.hwidBlacklist.description')}</p>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setAddOpen(true)} className="gap-1">
            <Plus className="w-4 h-4" /> {t('violations.hwidBlacklist.add')}
          </Button>
        )}
      </div>

      {/* Add dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="w-[95vw] max-w-md">
          <DialogHeader>
            <DialogTitle>{t('violations.hwidBlacklist.addTitle')}</DialogTitle>
            <DialogDescription>{t('violations.hwidBlacklist.addDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="text-xs font-medium text-dark-300 mb-1 block">HWID</label>
              <input
                value={newHwid}
                onChange={(e) => setNewHwid(e.target.value)}
                placeholder="a1b2c3d4e5f6..."
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm font-mono text-white placeholder:text-dark-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-dark-300 mb-1 block">{t('violations.hwidBlacklist.action')}</label>
              <div className="grid grid-cols-2 gap-2">
                {(['alert', 'block'] as const).map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setNewAction(a)}
                    className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors',
                      newAction === a
                        ? a === 'block' ? 'border-red-500/50 bg-red-500/10 text-red-400' : 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[var(--glass-border)] bg-[var(--glass-bg)] text-dark-300',
                    )}
                  >
                    {a === 'block' ? <Ban className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                    {a === 'block' ? t('violations.hwidBlacklist.actionBlock') : t('violations.hwidBlacklist.actionAlert')}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-dark-400 mt-1">
                {newAction === 'block' ? t('violations.hwidBlacklist.actionBlockHint') : t('violations.hwidBlacklist.actionAlertHint')}
              </p>
            </div>
            <div>
              <label className="text-xs font-medium text-dark-300 mb-1 block">{t('violations.hwidBlacklist.reason')}</label>
              <input
                value={newReason}
                onChange={(e) => setNewReason(e.target.value)}
                placeholder={t('violations.hwidBlacklist.reasonPlaceholder')}
                className="flex h-10 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white placeholder:text-dark-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => addMutation.mutate()} disabled={!newHwid.trim() || addMutation.isPending}>
              {addMutation.isPending ? t('common.saving') : t('violations.hwidBlacklist.addButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* List */}
      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : !data?.items?.length ? (
        <Card><CardContent className="py-8 text-center text-dark-300 text-sm">{t('violations.hwidBlacklist.empty')}</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {data.items.map((item) => (
            <Card key={item.id} className="p-0 overflow-hidden">
              <div className="flex items-center justify-between p-3 sm:p-4">
                <button
                  onClick={() => setExpandedHwid(expandedHwid === item.hwid ? null : item.hwid)}
                  className="flex-1 text-left flex items-center gap-3 min-w-0"
                >
                  <Fingerprint className="w-4 h-4 text-dark-300 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-mono text-white truncate">{item.hwid}</p>
                    <p className="text-[11px] text-dark-400">
                      {item.added_by_username && <span>{item.added_by_username} · </span>}
                      {formatDate(item.created_at)}
                      {item.reason && <span> · {item.reason}</span>}
                    </p>
                  </div>
                </button>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge className={cn(
                    'text-[10px]',
                    item.action === 'block' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-amber-500/20 text-amber-400 border-amber-500/30',
                  )}>
                    {item.action === 'block' ? t('violations.hwidBlacklist.actionBlock') : t('violations.hwidBlacklist.actionAlert')}
                  </Badge>
                  {canEdit && (
                    <Button variant="ghost" size="sm" onClick={() => removeMutation.mutate(item.hwid)} className="text-dark-400 hover:text-red-400 h-8 w-8 p-0">
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </div>
              </div>
              {expandedHwid === item.hwid && usersData && (
                <div className="border-t border-[var(--glass-border)] px-4 py-3 bg-[var(--glass-bg)]/30">
                  <p className="text-xs text-dark-400 mb-2">{t('violations.hwidBlacklist.affectedUsers', { count: usersData.total })}</p>
                  {usersData.users.length === 0 ? (
                    <p className="text-xs text-dark-400">{t('violations.hwidBlacklist.noUsers')}</p>
                  ) : (
                    <div className="space-y-1">
                      {usersData.users.map((u) => (
                        <div key={u.user_uuid} className="flex items-center gap-2 text-xs">
                          <User className="w-3 h-3 text-dark-400" />
                          <span className="text-white">{u.username || u.user_uuid.slice(0, 8)}</span>
                          {u.platform && <span className="text-dark-400">{u.platform}</span>}
                          {u.device_model && <span className="text-dark-400">{u.device_model}</span>}
                          {u.status && (
                            <Badge className={cn('text-[9px] py-0', u.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' : 'bg-dark-600 text-dark-300')}>
                              {u.status}
                            </Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Whitelist Tab
// ══════════════════════════════════════════════════════════════════

function WhitelistAddDialog({
  open,
  onOpenChange,
  userUuid: initialUserUuid,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  userUuid: string
  onSubmit: (data: { user_uuid: string; reason?: string; expires_in_days?: number; excluded_analyzers?: string[] }) => void
}) {
  const { t } = useTranslation()
  const [userUuid, setUserUuid] = useState(initialUserUuid)
  const [reason, setReason] = useState('')
  const [duration, setDuration] = useState<string>('forever')
  const [exclusionMode, setExclusionMode] = useState<'full' | 'partial'>('full')
  const [selectedAnalyzers, setSelectedAnalyzers] = useState<Set<string>>(new Set())

  useEffect(() => { setUserUuid(initialUserUuid) }, [initialUserUuid])

  useEffect(() => {
    if (open) {
      setExclusionMode('full')
      setSelectedAnalyzers(new Set())
      setReason('')
      setDuration('forever')
    }
  }, [open])

  const toggleAnalyzer = (key: string) => {
    setSelectedAnalyzers(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const isValidUuid = UUID_RE.test(userUuid.trim())

  const handleSubmit = () => {
    if (!userUuid.trim() || !isValidUuid) return
    if (exclusionMode === 'partial' && selectedAnalyzers.size === 0) return
    const expiresInDays = duration === 'forever' ? undefined : parseInt(duration, 10)
    onSubmit({
      user_uuid: userUuid.trim(),
      reason: reason.trim() || undefined,
      expires_in_days: expiresInDays,
      excluded_analyzers: exclusionMode === 'partial' && selectedAnalyzers.size > 0
        ? Array.from(selectedAnalyzers)
        : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('violations.whitelist.addTitle')}</DialogTitle>
          <DialogDescription className="text-sm text-dark-200">
            {initialUserUuid || t('violations.whitelist.emptyDesc')}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {!initialUserUuid && (
            <div>
              <label className="text-sm font-medium text-dark-100 mb-1.5 block">
                {t('violations.whitelist.userUuid')}
              </label>
              <input
                type="text"
                value={userUuid}
                onChange={(e) => setUserUuid(e.target.value)}
                placeholder={t('violations.whitelist.userUuidPlaceholder')}
                className="w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
              />
            </div>
          )}
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.whitelist.reason')}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t('violations.whitelist.reasonPlaceholder')}
              className="w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/40 min-h-[80px] resize-none"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.whitelist.duration')}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'forever', label: t('violations.whitelist.forever') },
                { value: '7', label: t('violations.whitelist.days7') },
                { value: '30', label: t('violations.whitelist.days30') },
                { value: '90', label: t('violations.whitelist.days90') },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDuration(opt.value)}
                  className={cn(
                    'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                    duration === opt.value
                      ? 'bg-primary-600/20 text-primary-400 border-primary-500/30'
                      : 'bg-[var(--glass-bg)] text-dark-200 border-[var(--glass-border)] hover:text-white hover:border-[var(--glass-border)]/40'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.exclusions.mode')}
            </label>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <button
                onClick={() => setExclusionMode('full')}
                className={cn(
                  'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                  exclusionMode === 'full'
                    ? 'bg-primary-600/20 text-primary-400 border-primary-500/30'
                    : 'bg-[var(--glass-bg)] text-dark-200 border-[var(--glass-border)] hover:text-white hover:border-[var(--glass-border)]/40'
                )}
              >
                {t('violations.exclusions.fullWhitelist')}
              </button>
              <button
                onClick={() => setExclusionMode('partial')}
                className={cn(
                  'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                  exclusionMode === 'partial'
                    ? 'bg-primary/20 text-primary-400 border-primary/30'
                    : 'bg-[var(--glass-bg)] text-dark-200 border-[var(--glass-border)] hover:text-white hover:border-[var(--glass-border)]/40'
                )}
              >
                {t('violations.exclusions.partialExclusion')}
              </button>
            </div>
            {exclusionMode === 'partial' && (
              <div className="space-y-1.5 mt-2">
                {ANALYZER_KEYS.map(key => (
                  <label
                    key={key}
                    className={cn(
                      'flex items-center gap-2.5 px-3 py-2 rounded-md cursor-pointer transition-all border',
                      selectedAnalyzers.has(key)
                        ? 'bg-primary/10 border-primary/30 text-primary-400'
                        : 'bg-[var(--glass-bg)] border-[var(--glass-border)]/15 text-dark-200 hover:border-[var(--glass-border)]'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedAnalyzers.has(key)}
                      onChange={() => toggleAnalyzer(key)}
                      className="rounded border-[var(--glass-border)] bg-[var(--glass-bg)] text-primary-500 focus:ring-primary-500/40"
                    />
                    <span className="text-sm">{t(`violations.analyzers.${key}`)}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!userUuid.trim() || (!initialUserUuid && !isValidUuid) || (exclusionMode === 'partial' && selectedAnalyzers.size === 0)}
            className="gap-2"
          >
            <ShieldOff className="w-4 h-4" />
            {t('violations.whitelist.addButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function WhitelistTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const canResolve = useHasPermission('violations', 'resolve')
  const [wlPage, setWlPage] = useState(1)
  const perPage = 20
  const [confirmRemoveUuid, setConfirmRemoveUuid] = useState<string | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [manualUuid, setManualUuid] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['violationWhitelist', wlPage],
    queryFn: () => fetchWhitelist(perPage, (wlPage - 1) * perPage),
  })

  const addMutation = useMutation({
    mutationFn: (body: { user_uuid: string; reason?: string; expires_in_days?: number; excluded_analyzers?: string[] }) =>
      client.post('/violations/whitelist', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      toast.success(t('violations.toast.whitelistAdded'))
      setAddDialogOpen(false)
      setManualUuid('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (userUuid: string) => client.delete(`/violations/whitelist/${userUuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      toast.success(t('violations.toast.whitelistRemoved'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const isExpired = (expiresAt: string | null) => {
    if (!expiresAt) return false
    return new Date(expiresAt) < new Date()
  }

  return (
    <div className="space-y-4">
      {canResolve && (
        <div className="flex justify-end">
          <Button onClick={() => setAddDialogOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            {t('violations.whitelist.addButton')}
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="text-center py-12">
          <CardContent>
            <ShieldCheck className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
            <p className="text-dark-200 text-lg">{t('violations.whitelist.empty')}</p>
            <p className="text-sm text-dark-200 mt-1">{t('violations.whitelist.emptyDesc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => (
            <Card
              key={item.id}
              className={cn(
                'hover:border-[var(--glass-border)]/40 transition-colors animate-fade-in-up',
                isExpired(item.expires_at) && 'opacity-60'
              )}
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  <div className="p-2.5 rounded-lg bg-primary/10 flex-shrink-0">
                    <ShieldOff className="w-5 h-5 text-primary-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="font-semibold text-white">
                        {item.username || item.email || item.user_uuid.slice(0, 8)}
                      </span>
                      {isExpired(item.expires_at) && (
                        <Badge variant="secondary" className="text-xs">{t('violations.whitelist.expired')}</Badge>
                      )}
                      {item.excluded_analyzers ? (
                        <Badge variant="outline" className="text-xs text-primary-400 border-primary/30">
                          {t('violations.exclusions.partialExclusion')}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs text-primary-400 border-primary/30">
                          {t('violations.exclusions.fullWhitelist')}
                        </Badge>
                      )}
                    </div>
                    {Array.isArray(item.excluded_analyzers) && item.excluded_analyzers.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1">
                        {item.excluded_analyzers.map(a => (
                          <Badge key={a} variant="secondary" className="text-xs bg-primary/10 text-primary-400 border-primary/20">
                            {t(`violations.analyzers.${a}`)}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-dark-200">
                      {item.reason && <span>{item.reason}</span>}
                      <span>
                        <Calendar className="w-3.5 h-3.5 inline mr-0.5" />
                        {t('violations.whitelist.addedBy')}: {item.added_by_username || '—'}
                      </span>
                      <span>{formatDate(item.added_at)}</span>
                      {item.expires_at ? (
                        <span>{t('violations.whitelist.expiresAt')}: {formatDate(item.expires_at)}</span>
                      ) : (
                        <span className="text-primary-400">{t('violations.whitelist.noExpiration')}</span>
                      )}
                    </div>
                  </div>
                  {canResolve && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmRemoveUuid(item.user_uuid)}
                      className="text-dark-300 hover:text-red-400 flex-shrink-0"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-2 pt-2">
          <Button variant="ghost" size="sm" disabled={wlPage <= 1} onClick={() => setWlPage(wlPage - 1)}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-dark-200">{wlPage} / {totalPages}</span>
          <Button variant="ghost" size="sm" disabled={wlPage >= totalPages} onClick={() => setWlPage(wlPage + 1)}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      <WhitelistAddDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        userUuid={manualUuid}
        onSubmit={(data) => addMutation.mutate(data)}
      />

      <ConfirmDialog
        open={confirmRemoveUuid !== null}
        onOpenChange={(open) => { if (!open) setConfirmRemoveUuid(null) }}
        title={t('violations.whitelist.confirmRemove')}
        description={t('violations.whitelist.confirmRemoveDesc')}
        variant="destructive"
        onConfirm={() => {
          if (confirmRemoveUuid) removeMutation.mutate(confirmRemoveUuid)
          setConfirmRemoveUuid(null)
        }}
      />
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════════════════════════════

type BlockingTab = 'ip' | 'hwid' | 'whitelist'

export default function Blocking() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const rawTab = (params.get('tab') || 'ip') as BlockingTab
  const validTabs: BlockingTab[] = ['ip', 'hwid', 'whitelist']
  const tab = validTabs.includes(rawTab) ? rawTab : 'ip'

  const handleTabChange = (newTab: string) => {
    setParams({ tab: newTab === 'ip' ? '' : newTab }, { replace: true })
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ShieldBan className="h-6 w-6 text-red-500" />
        <h1 className="text-xl font-semibold sm:text-2xl">{t('blocking.title')}</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-2">{t('blocking.description')}</p>

      <Separator />

      {/* Tabs */}
      <Tabs value={tab} onValueChange={handleTabChange} className="w-full">
        <TabsList>
          <TabsTrigger value="ip" className="gap-1.5">
            <ShieldBan className="w-4 h-4" />
            {t('blocking.tabs.ip')}
          </TabsTrigger>
          <TabsTrigger value="hwid" className="gap-1.5">
            <Fingerprint className="w-4 h-4" />
            {t('blocking.tabs.hwid')}
          </TabsTrigger>
          <TabsTrigger value="whitelist" className="gap-1.5">
            <ShieldCheck className="w-4 h-4" />
            {t('blocking.tabs.whitelist')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ip">
          <BlockedIPsTab />
        </TabsContent>
        <TabsContent value="hwid">
          <HwidBlacklistTab />
        </TabsContent>
        <TabsContent value="whitelist">
          <WhitelistTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
