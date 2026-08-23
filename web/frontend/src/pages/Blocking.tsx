import { Fragment, useState, useCallback, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ShieldBan, Plus, Trash2, RefreshCw, Upload,
  Fingerprint, AlertTriangle, Ban, User,
  ShieldOff, ShieldCheck, Calendar, ShieldAlert,
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
  Search, ArrowUpDown, Users, ExternalLink, Gauge,
} from '@/components/brand/icons'
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
import { EmptyState } from '@/components/EmptyState'
import { useFormatters } from '@/lib/useFormatters'
import { cn } from '@/lib/utils'
import type { WhitelistItem } from '@/types/violations'

// ── Types ─────────────────────────────────────────────────────────

type HwidSort = 'recent' | 'oldest' | 'users' | 'active'

interface HwidBlacklistItem {
  id: number
  hwid: string
  action: string
  reason: string | null
  added_by_username: string | null
  created_at: string
  // счётчики считает бэкенд: сколько аккаунтов на устройстве, сколько из них
  // с живой подпиской и у скольких устройство уже отвязано
  users_total?: number
  users_active?: number
  users_removed?: number
}

interface HwidBlacklistUser {
  user_uuid: string
  username: string | null
  status: string | null
  platform: string | null
  device_model: string | null
  telegram_id?: number | null
  expire_at?: string | null
  removed_at?: string | null
}

interface BlockedIP {
  id: number
  ip_cidr: string
  reason: string | null
  added_by_username: string | null
  country_code: string | null
  asn_org: string | null
  expires_at: string | null
  created_at: string | null
  // счётчики считает бэкенд по истории подключений: без них из списка не
  // понять, отрезан один абузер или подсеть с живыми абонентами
  accounts?: number | null
  trial_accounts?: number | null
  last_seen?: string | null
}

type IpSort = 'recent' | 'oldest' | 'accounts' | 'expiring'

interface BlockedIPUser {
  user_uuid: string
  username: string | null
  status: string | null
  telegram_id: number | null
  email: string | null
  expire_at: string | null
  conns: number
  first_seen: string | null
  last_seen: string | null
  sample_ip: string | null
  is_trial: boolean
  is_active: boolean
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

interface ThrottleItem {
  user_uuid: string
  username: string | null
  rate_kbit: number
  reason: string | null
  created_by_username: string | null
  created_at: string
  until: string | null
}

const fetchThrottles = async (): Promise<{ items: ThrottleItem[]; total: number }> => {
  const { data } = await client.get('/violations/throttles')
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
  const { formatDate } = useFormatters()

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

  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<IpSort>('recent')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['blocked-ips', offset],
    queryFn: () => fetchBlockedIPs(PAGE_SIZE, offset),
    placeholderData: (prev) => prev,
  })

  // Кто заходил с адреса — тянем только для раскрытой строки
  const { data: ipUsers, isFetching: ipUsersFetching } = useQuery({
    queryKey: ['blocked-ip-users', expandedId],
    queryFn: async () => {
      const { data } = await client.get(`/blocked-ips/${expandedId}/users`)
      return data as { ip_cidr: string; users: BlockedIPUser[]; total: number }
    },
    enabled: expandedId !== null,
  })

  const rawItems = Array.isArray(data?.items) ? data.items : []
  const total = data?.total ?? 0

  const stats = {
    total,
    forever: rawItems.filter((i) => !i.expires_at).length,
    temporary: rawItems.filter((i) => !!i.expires_at).length,
    affecting: rawItems.filter((i) => (i.accounts ?? 0) > 0).length,
  }

  const ipQuery = search.trim().toLowerCase()
  const items = rawItems
    .filter((i) => !ipQuery
      || i.ip_cidr.toLowerCase().includes(ipQuery)
      || (i.reason || '').toLowerCase().includes(ipQuery)
      || (i.asn_org || '').toLowerCase().includes(ipQuery))
    .sort((a, b) => {
      if (sortBy === 'accounts') return (b.accounts ?? 0) - (a.accounts ?? 0)
      if (sortBy === 'oldest') return (a.created_at || '').localeCompare(b.created_at || '')
      if (sortBy === 'expiring') {
        // бессрочные в конец: у них нет даты, по которой их можно торопить
        if (!a.expires_at) return 1
        if (!b.expires_at) return -1
        return a.expires_at.localeCompare(b.expires_at)
      }
      return (b.created_at || '').localeCompare(a.created_at || '')
    })

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

      {/* Сводка: сколько записей и сколько из них кого-то реально задевают */}
      {rawItems.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <HwidStatTile label={t('blockedIPs.stats.total')} value={stats.total} icon={ShieldBan} />
          <HwidStatTile label={t('blockedIPs.stats.forever')} value={stats.forever} icon={Ban} tone="red" />
          <HwidStatTile label={t('blockedIPs.stats.temporary')} value={stats.temporary} icon={Calendar} tone="amber" />
          <HwidStatTile
            label={t('blockedIPs.stats.affecting')}
            value={stats.affecting}
            icon={Users}
            tone={stats.affecting > 0 ? 'red' : 'muted'}
            active={sortBy === 'accounts'}
            onClick={() => setSortBy('accounts')}
          />
        </div>
      )}

      {/* Поиск и сортировка */}
      {rawItems.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('blockedIPs.searchPlaceholder')}
              className="pl-9"
            />
          </div>
          <Select value={sortBy} onValueChange={(v) => setSortBy(v as IpSort)}>
            <SelectTrigger className="w-full sm:w-[210px]">
              <ArrowUpDown className="w-3.5 h-3.5 mr-1.5 text-dark-400" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">{t('blockedIPs.sort.recent')}</SelectItem>
              <SelectItem value="oldest">{t('blockedIPs.sort.oldest')}</SelectItem>
              <SelectItem value="accounts">{t('blockedIPs.sort.accounts')}</SelectItem>
              <SelectItem value="expiring">{t('blockedIPs.sort.expiring')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('blockedIPs.columns.ipCidr')}</TableHead>
              <TableHead className="hidden sm:table-cell">{t('blockedIPs.columns.country')}</TableHead>
              <TableHead className="hidden md:table-cell">{t('blockedIPs.columns.asnProvider')}</TableHead>
              <TableHead>{t('blockedIPs.columns.affects')}</TableHead>
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
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                  <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell className="hidden md:table-cell"><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell className="hidden lg:table-cell"><Skeleton className="h-4 w-24" /></TableCell>
                  {canDelete && <TableCell><Skeleton className="h-8 w-8" /></TableCell>}
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={canDelete ? 9 : 8} className="py-12 text-center text-muted-foreground">
                  {t('blockedIPs.empty')}
                </TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <Fragment key={item.id}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                >
                  <TableCell className="font-mono text-sm">
                    <span className="inline-flex items-center gap-1.5">
                      {expandedId === item.id
                        ? <ChevronUp className="h-3.5 w-3.5 text-dark-300 shrink-0" />
                        : <ChevronDown className="h-3.5 w-3.5 text-dark-300 shrink-0" />}
                      {item.ip_cidr}
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {item.country_code ? <span title={item.country_code}>{item.country_code}</span> : '—'}
                  </TableCell>
                  <TableCell className="hidden md:table-cell max-w-[200px] truncate">{item.asn_org || '—'}</TableCell>
                  <TableCell>
                    {(item.accounts ?? 0) > 0 ? (
                      <span className="inline-flex items-center gap-1.5 flex-wrap">
                        <Badge variant="outline" className="text-[10px] gap-1">
                          <Users className="h-3 w-3" />
                          {item.accounts}
                        </Badge>
                        {(item.trial_accounts ?? 0) > 0 && (
                          <Badge className="text-[10px] bg-amber-500/20 text-amber-300 border-amber-500/40">
                            {t('blockedIPs.trialsBadge', { count: item.trial_accounts ?? 0 })}
                          </Badge>
                        )}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[150px] truncate">{item.reason || '—'}</TableCell>
                  <TableCell className="hidden lg:table-cell">{item.added_by_username || '—'}</TableCell>
                  <TableCell className="hidden md:table-cell text-xs text-muted-foreground">{formatDate(item.created_at)}</TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                    {item.expires_at ? formatDate(item.expires_at) : t('blockedIPs.forever')}
                  </TableCell>
                  {canDelete && (
                    <TableCell>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-red-500 hover:text-red-600"
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(item) }}
                        aria-label={t('common.delete')}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
                {expandedId === item.id && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={canDelete ? 9 : 8} className="bg-[var(--glass-bg)]/30 py-3">
                      <BlockedIpUsers
                        users={ipUsers?.users}
                        loading={ipUsersFetching && !ipUsers}
                      />
                    </TableCell>
                  </TableRow>
                )}
                </Fragment>
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('violations', 'create')
  const [addOpen, setAddOpen] = useState(false)
  const [newHwid, setNewHwid] = useState('')
  const [newAction, setNewAction] = useState<'alert' | 'block'>('alert')
  const [newReason, setNewReason] = useState('')
  const [expandedHwid, setExpandedHwid] = useState<string | null>(null)
  const [confirmRemoveHwid, setConfirmRemoveHwid] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [actionFilter, setActionFilter] = useState<'all' | 'block' | 'alert'>('all')
  const [sortBy, setSortBy] = useState<HwidSort>('recent')

  const { data, isLoading } = useQuery({
    queryKey: ['hwid-blacklist'],
    queryFn: async () => {
      const { data } = await client.get('/violations/hwid-blacklist')
      return data as { items: HwidBlacklistItem[]; total: number }
    },
  })

  const { data: usersData, isFetching: usersFetching } = useQuery({
    queryKey: ['hwid-blacklist-users', expandedHwid],
    queryFn: async () => {
      const { data } = await client.get(`/violations/hwid-blacklist/${expandedHwid}/users`)
      return data as { users: HwidBlacklistUser[]; total: number }
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

  const items = data?.items ?? []
  const stats = {
    total: items.length,
    block: items.filter((i) => i.action === 'block').length,
    alert: items.filter((i) => i.action === 'alert').length,
    live: items.filter((i) => (i.users_active ?? 0) > 0).length,
  }

  const query = search.trim().toLowerCase()
  const visible = items
    .filter((i) => actionFilter === 'all' || i.action === actionFilter)
    .filter((i) => !query
      || i.hwid.toLowerCase().includes(query)
      || (i.reason || '').toLowerCase().includes(query))
    .sort((a, b) => {
      if (sortBy === 'users') return (b.users_total ?? 0) - (a.users_total ?? 0)
      if (sortBy === 'active') return (b.users_active ?? 0) - (a.users_active ?? 0)
      if (sortBy === 'oldest') return a.created_at.localeCompare(b.created_at)
      return b.created_at.localeCompare(a.created_at)
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

      {/* Сводка: клик по плитке — тот же фильтр, что и в селекте ниже */}
      {items.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <HwidStatTile
            label={t('violations.hwidBlacklist.stats.total')}
            value={stats.total}
            icon={Fingerprint}
            active={actionFilter === 'all'}
            onClick={() => setActionFilter('all')}
          />
          <HwidStatTile
            label={t('violations.hwidBlacklist.actionBlock')}
            value={stats.block}
            icon={Ban}
            tone="red"
            active={actionFilter === 'block'}
            onClick={() => setActionFilter('block')}
          />
          <HwidStatTile
            label={t('violations.hwidBlacklist.actionAlert')}
            value={stats.alert}
            icon={AlertTriangle}
            tone="amber"
            active={actionFilter === 'alert'}
            onClick={() => setActionFilter('alert')}
          />
          <HwidStatTile
            label={t('violations.hwidBlacklist.stats.live')}
            value={stats.live}
            icon={ShieldAlert}
            tone={stats.live > 0 ? 'red' : 'muted'}
            onClick={() => setSortBy('active')}
          />
        </div>
      )}

      {/* Поиск и сортировка */}
      {items.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('violations.hwidBlacklist.searchPlaceholder')}
              className="pl-9"
            />
          </div>
          <Select value={sortBy} onValueChange={(v) => setSortBy(v as HwidSort)}>
            <SelectTrigger className="w-full sm:w-[210px]">
              <ArrowUpDown className="w-3.5 h-3.5 mr-1.5 text-dark-400" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">{t('violations.hwidBlacklist.sort.recent')}</SelectItem>
              <SelectItem value="oldest">{t('violations.hwidBlacklist.sort.oldest')}</SelectItem>
              <SelectItem value="users">{t('violations.hwidBlacklist.sort.users')}</SelectItem>
              <SelectItem value="active">{t('violations.hwidBlacklist.sort.active')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

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

      <ConfirmDialog
        open={confirmRemoveHwid !== null}
        onOpenChange={(open) => { if (!open) setConfirmRemoveHwid(null) }}
        title={t('violations.hwidBlacklist.confirmRemove', { defaultValue: 'Снять HWID-блокировку?' })}
        description={t('violations.hwidBlacklist.confirmRemoveDesc', { defaultValue: 'HWID будет удалён из чёрного списка.' })}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => { if (confirmRemoveHwid) removeMutation.mutate(confirmRemoveHwid) }}
      />

      {/* List */}
      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : !items.length ? (
        <Card>
          <CardContent className="p-2">
            <EmptyState icon={Fingerprint} title={t('violations.hwidBlacklist.empty')} size="sm" />
          </CardContent>
        </Card>
      ) : !visible.length ? (
        <Card>
          <CardContent className="p-2">
            <EmptyState icon={Search} title={t('violations.hwidBlacklist.nothingFound')} size="sm" />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {visible.map((item) => {
            const expanded = expandedHwid === item.hwid
            const live = (item.users_active ?? 0) > 0
            return (
              <Card key={item.id} className={cn('p-0 overflow-hidden transition-colors', live && 'border-red-500/40')}>
                <div className="flex items-center justify-between p-3 sm:p-4 gap-2">
                  <button
                    onClick={() => setExpandedHwid(expanded ? null : item.hwid)}
                    className="flex-1 text-left flex items-center gap-3 min-w-0"
                    aria-expanded={expanded}
                  >
                    {expanded
                      ? <ChevronUp className="w-4 h-4 text-dark-300 shrink-0" />
                      : <ChevronDown className="w-4 h-4 text-dark-300 shrink-0" />}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-mono text-white truncate">{item.hwid}</p>
                        {live && (
                          <Badge className="text-[10px] bg-red-500/20 text-red-300 border-red-500/40 gap-1">
                            <ShieldAlert className="w-3 h-3" />
                            {t('violations.hwidBlacklist.badgeLive', { count: item.users_active ?? 0 })}
                          </Badge>
                        )}
                        {(item.users_total ?? 0) > 0 && (
                          <Badge variant="outline" className="text-[10px] gap-1">
                            <Users className="w-3 h-3" />
                            {item.users_total}
                          </Badge>
                        )}
                        {(item.users_removed ?? 0) > 0 && (
                          <Badge variant="outline" className="text-[10px] text-amber-300 border-amber-500/30">
                            {t('violations.hwidBlacklist.badgeUnlinked', { count: item.users_removed ?? 0 })}
                          </Badge>
                        )}
                      </div>
                      <p className="text-[11px] text-dark-400 mt-0.5">
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
                      <Button variant="ghost" size="sm" onClick={() => setConfirmRemoveHwid(item.hwid)} className="text-dark-400 hover:text-red-400 h-8 w-8 p-0" aria-label={t('common.delete')}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                </div>

                {expanded && (
                  <div className="border-t border-[var(--glass-border)] px-4 py-3 bg-[var(--glass-bg)]/30">
                    {usersFetching && !usersData ? (
                      <Skeleton className="h-10 w-full" />
                    ) : !usersData?.users?.length ? (
                      <div className="text-xs text-dark-400 space-y-1">
                        <p>{t('violations.hwidBlacklist.noUsers')}</p>
                        <p className="text-dark-500">{t('violations.hwidBlacklist.noUsersHint')}</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-xs text-dark-400 mb-2">
                          {t('violations.hwidBlacklist.affectedUsers', { count: usersData.total })}
                        </p>
                        <div className="space-y-1">
                          {usersData.users.map((u) => (
                            <HwidUserRow
                              key={u.user_uuid}
                              user={u}
                              onOpen={() => navigate(`/users/${u.user_uuid}`)}
                            />
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** Кто заходил с заблокированного адреса — разворот строки стоп-листа. */
function BlockedIpUsers({ users, loading }: { users?: BlockedIPUser[]; loading: boolean }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const navigate = useNavigate()

  if (loading) return <Skeleton className="h-10 w-full" />
  if (!users?.length) {
    return (
      <div className="text-xs text-dark-400 space-y-1">
        <p>{t('blockedIPs.noUsers')}</p>
        <p className="text-dark-500">{t('blockedIPs.noUsersHint')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <p className="text-xs text-dark-400 mb-2">{t('blockedIPs.affectedUsers', { count: users.length })}</p>
      {users.map((u) => (
        <button
          key={u.user_uuid}
          type="button"
          onClick={() => navigate(`/users/${u.user_uuid}`)}
          className="w-full flex items-center gap-2 text-xs rounded-md px-2 py-1.5 text-left hover:bg-[var(--glass-bg-hover)] transition-colors group"
        >
          <User className="w-3 h-3 text-dark-400 shrink-0" />
          <span className="text-white truncate">{u.username || u.user_uuid.slice(0, 8)}</span>
          {u.telegram_id && <span className="text-dark-400 shrink-0">#{u.telegram_id}</span>}
          {u.is_trial && (
            <Badge className="text-[9px] py-0 bg-amber-500/20 text-amber-300 border-amber-500/40 shrink-0">
              {t('blockedIPs.trialLabel')}
            </Badge>
          )}
          <span className="flex-1" />
          <span className="text-dark-400 shrink-0">{t('blockedIPs.connsShort', { count: u.conns })}</span>
          {u.last_seen && (
            <span className="text-dark-400 shrink-0 hidden sm:inline">{formatDate(u.last_seen)}</span>
          )}
          <Badge className={cn('text-[9px] py-0 shrink-0', u.is_active ? 'bg-green-500/20 text-green-400' : 'bg-dark-600 text-dark-300')}>
            {u.status || '—'}
          </Badge>
          <ExternalLink className="w-3 h-3 text-dark-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
        </button>
      ))}
    </div>
  )
}

/** Плитка сводки: она же переключатель фильтра. */
function HwidStatTile({
  label, value, icon: Icon, tone = 'default', active, onClick,
}: {
  label: string
  value: number
  icon: typeof Fingerprint
  tone?: 'default' | 'red' | 'amber' | 'muted'
  active?: boolean
  onClick?: () => void
}) {
  const toneClass = {
    red: 'text-red-400',
    amber: 'text-amber-400',
    muted: 'text-dark-400',
    default: 'text-primary-400',
  }[tone]
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
        active
          ? 'border-primary-500/50 bg-primary-500/10'
          : 'border-[var(--glass-border)] bg-[var(--glass-bg)]/40 hover:bg-[var(--glass-bg)]',
      )}
    >
      <Icon className={cn('w-4 h-4 shrink-0', toneClass)} />
      <div className="min-w-0">
        <p className="text-base font-semibold text-white leading-none">{value}</p>
        <p className="text-[11px] text-dark-300 truncate mt-1">{label}</p>
      </div>
    </button>
  )
}

/** Строка пользователя на устройстве из списка — с переходом в его карточку. */
function HwidUserRow({ user, onOpen }: { user: HwidBlacklistUser; onOpen: () => void }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const active = user.status === 'ACTIVE'
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full flex items-center gap-2 text-xs rounded-md px-2 py-1.5 -mx-2 text-left hover:bg-[var(--glass-bg-hover)] transition-colors group"
    >
      <User className="w-3 h-3 text-dark-400 shrink-0" />
      <span className="text-white truncate">{user.username || user.user_uuid.slice(0, 8)}</span>
      {user.telegram_id && <span className="text-dark-400 shrink-0">#{user.telegram_id}</span>}
      {user.platform && <span className="text-dark-400 shrink-0">{user.platform}</span>}
      {user.device_model && <span className="text-dark-400 truncate hidden sm:inline">{user.device_model}</span>}
      <span className="flex-1" />
      {user.removed_at && (
        <Badge variant="outline" className="text-[9px] py-0 text-amber-300 border-amber-500/30 shrink-0">
          {t('violations.hwidBlacklist.unlinked')}
        </Badge>
      )}
      {user.expire_at && (
        <span className="text-dark-400 shrink-0 hidden sm:inline">{formatDate(user.expire_at)}</span>
      )}
      {user.status && (
        <Badge className={cn('text-[9px] py-0 shrink-0', active ? 'bg-green-500/20 text-green-400' : 'bg-dark-600 text-dark-300')}>
          {user.status}
        </Badge>
      )}
      <ExternalLink className="w-3 h-3 text-dark-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
    </button>
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

// ══════════════════════════════════════════════════════════════════
// Ограничения скорости («мягкая блокировка»)
// ══════════════════════════════════════════════════════════════════

function ThrottlesTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const canResolve = useHasPermission('violations', 'resolve')
  const [addOpen, setAddOpen] = useState(false)
  const [uuid, setUuid] = useState('')
  const [rate, setRate] = useState('')
  const [hours, setHours] = useState('')
  const [reason, setReason] = useState('')
  const [confirmLift, setConfirmLift] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['throttles'],
    queryFn: fetchThrottles,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['throttles'] })
    queryClient.invalidateQueries({ queryKey: ['violations'] })
  }

  const addMutation = useMutation({
    mutationFn: (body: { user_uuid: string; rate_kbit?: number; expires_in_hours?: number; reason?: string }) =>
      client.post('/violations/throttle', body),
    onSuccess: (res) => {
      refresh()
      toast.success(
        res?.data?.moved_to_squad
          ? t('violations.throttles.toast.addedWithSquad')
          : t('violations.throttles.toast.added'),
      )
      setAddOpen(false)
      setUuid(''); setRate(''); setHours(''); setReason('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const liftMutation = useMutation({
    mutationFn: (userUuid: string) => client.delete(`/violations/throttle/${userUuid}`),
    onSuccess: (res) => {
      refresh()
      toast.success(
        res?.data?.squads_restored
          ? t('violations.throttles.toast.liftedWithSquad')
          : t('violations.throttles.toast.lifted'),
      )
      setConfirmLift(null)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const items = data?.items || []

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t('violations.throttles.description')}</p>

      {canResolve && (
        <div className="flex justify-end">
          <Button onClick={() => setAddOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            {t('violations.throttles.add')}
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-2">
            <EmptyState
              icon={Gauge}
              title={t('violations.throttles.empty')}
              description={t('violations.throttles.emptyDesc')}
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <Card key={item.user_uuid}>
              <CardContent className="flex flex-wrap items-center gap-3 p-4">
                <Gauge className="h-5 w-5 shrink-0 text-amber-500" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{item.username || item.user_uuid.slice(0, 8)}</span>
                    <Badge variant="secondary">{item.rate_kbit} {t('violations.throttles.kbit')}</Badge>
                    {item.until ? (
                      <Badge variant="outline" className="gap-1">
                        <Calendar className="h-3 w-3" />
                        {formatDate(item.until)}
                      </Badge>
                    ) : (
                      <Badge variant="outline">{t('violations.throttles.forever')}</Badge>
                    )}
                  </div>
                  {item.reason && (
                    <p className="mt-1 text-sm text-muted-foreground">{item.reason}</p>
                  )}
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {t('violations.throttles.by', {
                      who: item.created_by_username || '—',
                      when: formatDate(item.created_at),
                    })}
                  </p>
                </div>
                {canResolve && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmLift(item.user_uuid)}
                    disabled={liftMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('violations.throttles.addTitle')}</DialogTitle>
            <DialogDescription>{t('violations.throttles.addDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm">{t('violations.whitelist.userUuid')}</label>
              <Input value={uuid} onChange={(e) => setUuid(e.target.value)} placeholder="uuid" />
            </div>
            <div>
              <label className="mb-1 block text-sm">{t('violations.throttles.rate')}</label>
              <Input
                type="number"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder={t('violations.throttles.ratePlaceholder')}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm">{t('violations.throttles.hours')}</label>
              <Input
                type="number"
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                placeholder={t('violations.throttles.hoursPlaceholder')}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm">{t('violations.whitelist.reason')}</label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => addMutation.mutate({
                user_uuid: uuid.trim(),
                rate_kbit: rate ? Number(rate) : undefined,
                expires_in_hours: hours ? Number(hours) : undefined,
                reason: reason.trim() || undefined,
              })}
              disabled={!uuid.trim() || addMutation.isPending}
            >
              {t('violations.throttles.add')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmLift}
        onOpenChange={(open) => { if (!open) setConfirmLift(null) }}
        title={t('violations.throttles.liftTitle')}
        description={t('violations.throttles.liftDesc')}
        confirmLabel={t('violations.throttles.lift')}
        onConfirm={() => { if (confirmLift) liftMutation.mutate(confirmLift) }}
      />
    </div>
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
        <Card>
          <CardContent className="p-2">
            <EmptyState
              icon={ShieldCheck}
              title={t('violations.whitelist.empty')}
              description={t('violations.whitelist.emptyDesc')}
              size="lg"
            />
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
                      aria-label={t('common.delete')}
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
          <TabsTrigger value="throttles" className="gap-1.5">
            <Gauge className="w-4 h-4" />
            {t('blocking.tabs.throttles')}
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
        <TabsContent value="throttles">
          <ThrottlesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
