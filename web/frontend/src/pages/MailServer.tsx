/**
 * Mail Server page — embedded mail server management with tabs for:
 * - Domains (setup, DNS records)
 * - Queue (outbound email logs)
 * - Inbox (received emails)
 * - Compose (send emails)
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Globe, Send, Inbox, ListOrdered, Plus, Trash2, RefreshCw,
  CheckCircle2, XCircle, Copy, Mail, Eye, MailOpen, X, Ban,
  RotateCcw, Search, KeyRound, Pencil,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  mailserverApi,
  type MailDomain,
  type DnsRecord,
  type EmailQueueItem,
  type QueueStats,
  type InboxItem,
  type InboxDetail,
  type SmtpCredential,
} from '@/api/mailserver'
import { cn } from '@/lib/utils'

// ── Helpers ────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString()
}

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  sending: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  sent: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  cancelled: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
}

// ── Main Component ─────────────────────────────────────────────

export default function MailServer() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('mailserver', 'edit')
  const canCreate = useHasPermission('mailserver', 'create')
  const canDelete = useHasPermission('mailserver', 'delete')

  const [tab, setTab] = useState('domains')

  return (
    <div className="space-y-6 animate-fade-in min-w-0 overflow-x-hidden">
      <div>
        <h1 className="text-2xl font-bold text-white">{t('mailServer.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('mailServer.subtitle')}</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-dark-700/50 border border-dark-400/20 overflow-x-auto no-scrollbar">
          <TabsTrigger value="domains" className="gap-1.5">
            <Globe className="w-4 h-4" />
            <span className="hidden sm:inline">{t('mailServer.tabs.domains')}</span>
          </TabsTrigger>
          <TabsTrigger value="queue" className="gap-1.5">
            <ListOrdered className="w-4 h-4" />
            <span className="hidden sm:inline">{t('mailServer.tabs.queue')}</span>
          </TabsTrigger>
          <TabsTrigger value="inbox" className="gap-1.5">
            <Inbox className="w-4 h-4" />
            <span className="hidden sm:inline">{t('mailServer.tabs.inbox')}</span>
          </TabsTrigger>
          <TabsTrigger value="compose" className="gap-1.5">
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">{t('mailServer.tabs.compose')}</span>
          </TabsTrigger>
          <TabsTrigger value="credentials" className="gap-1.5">
            <KeyRound className="w-4 h-4" />
            <span className="hidden sm:inline">{t('mailServer.tabs.credentials')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="domains"><DomainsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="queue"><QueueTab canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="inbox"><InboxTab canEdit={canEdit} canDelete={canDelete} /></TabsContent>
        <TabsContent value="compose"><ComposeTab /></TabsContent>
        <TabsContent value="credentials"><CredentialsTab canCreate={canCreate} canEdit={canEdit} canDelete={canDelete} /></TabsContent>
      </Tabs>
    </div>
  )
}

// ── Domains Tab ───────────────────────────────────────────────

function DomainsTab({ canCreate, canEdit, canDelete }: { canCreate: boolean; canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newDomain, setNewDomain] = useState('')
  const [newFromName, setNewFromName] = useState('')
  const [inboundEnabled, setInboundEnabled] = useState(false)
  const [selectedDomain, setSelectedDomain] = useState<number | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: domains, isLoading } = useQuery({
    queryKey: ['mailserver-domains'],
    queryFn: mailserverApi.listDomains,
  })

  const createMut = useMutation({
    mutationFn: () => mailserverApi.createDomain({
      domain: newDomain,
      from_name: newFromName || undefined,
      inbound_enabled: inboundEnabled,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-domains'] })
      toast.success(t('mailServer.domainCreated'))
      setShowAdd(false)
      setNewDomain('')
      setNewFromName('')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => mailserverApi.deleteDomain(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-domains'] })
      toast.success(t('mailServer.domainDeleted'))
      setDeleteId(null)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      mailserverApi.updateDomain(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mailserver-domains'] }),
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const checkDnsMut = useMutation({
    mutationFn: (id: number) => mailserverApi.checkDns(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-domains'] })
      toast.success(t('mailServer.dnsChecked'))
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  if (isLoading) return <div className="space-y-3">{[1, 2].map(i => <Skeleton key={i} className="h-32 w-full" />)}</div>

  return (
    <div className="space-y-4">
      {/* Add domain button */}
      {canCreate && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setShowAdd(true)} className="gap-1.5">
            <Plus className="w-4 h-4" /> {t('mailServer.addDomain')}
          </Button>
        </div>
      )}

      {/* Domain cards */}
      {!domains?.length ? (
        <Card className="bg-dark-700/50 border-dark-400/20">
          <CardContent className="py-12 text-center">
            <Globe className="w-12 h-12 mx-auto text-dark-300 mb-3" />
            <p className="text-muted-foreground">{t('mailServer.noDomains')}</p>
          </CardContent>
        </Card>
      ) : (
        domains.map((d) => (
          <DomainCard
            key={d.id}
            domain={d}
            canEdit={canEdit}
            canDelete={canDelete}
            onToggle={(active) => toggleMut.mutate({ id: d.id, is_active: active })}
            onCheckDns={() => checkDnsMut.mutate(d.id)}
            onDelete={() => setDeleteId(d.id)}
            onViewDns={() => setSelectedDomain(d.id)}
          />
        ))
      )}

      {/* Add domain dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('mailServer.addDomain')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('mailServer.domainName')}</Label>
              <Input
                placeholder="example.com"
                value={newDomain}
                onChange={(e) => setNewDomain(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label>{t('mailServer.senderName')}</Label>
              <Input
                placeholder={t('mailServer.senderNamePlaceholder')}
                value={newFromName}
                onChange={(e) => setNewFromName(e.target.value)}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">{t('mailServer.senderNameHint')}</p>
            </div>
            <div className="flex items-center gap-3">
              <Switch checked={inboundEnabled} onCheckedChange={setInboundEnabled} />
              <Label>{t('mailServer.enableInbound')}</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => createMut.mutate()} disabled={!newDomain || createMut.isPending}>
              {createMut.isPending ? t('common.saving') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* DNS records dialog */}
      {selectedDomain && (
        <DnsRecordsDialog domainId={selectedDomain} onClose={() => setSelectedDomain(null)} />
      )}

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={() => setDeleteId(null)}
        title={t('mailServer.deleteDomain')}
        description={t('mailServer.deleteDomainConfirm')}
        onConfirm={() => deleteId && deleteMut.mutate(deleteId)}
        variant="destructive"
      />
    </div>
  )
}

// ── Domain Card ───────────────────────────────────────────────

function DomainCard({
  domain,
  canEdit,
  canDelete,
  onToggle,
  onCheckDns,
  onDelete,
  onViewDns,
}: {
  domain: MailDomain
  canEdit: boolean
  canDelete: boolean
  onToggle: (active: boolean) => void
  onCheckDns: () => void
  onDelete: () => void
  onViewDns: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editingFromName, setEditingFromName] = useState(false)
  const [fromNameValue, setFromNameValue] = useState(domain.from_name || '')
  const dnsCount = [domain.dns_mx_ok, domain.dns_spf_ok, domain.dns_dkim_ok, domain.dns_dmarc_ok, domain.dns_ptr_ok].filter(Boolean).length

  const updateFromNameMut = useMutation({
    mutationFn: () => mailserverApi.updateDomain(domain.id, { from_name: fromNameValue || null } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-domains'] })
      setEditingFromName(false)
      toast.success(t('mailServer.senderNameUpdated'))
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  return (
    <Card className="bg-dark-700/50 border-dark-400/20">
      <CardContent className="p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center",
              domain.is_active ? "bg-green-500/20" : "bg-dark-600"
            )}>
              <Globe className={cn("w-5 h-5", domain.is_active ? "text-green-400" : "text-dark-300")} />
            </div>
            <div>
              <h3 className="text-white font-semibold">{domain.domain}</h3>
              <p className="text-xs text-muted-foreground">
                DNS: {dnsCount}/5 &middot;
                {domain.outbound_enabled && ` ${t('mailServer.outbound')}`}
                {domain.inbound_enabled && ` ${t('mailServer.inbound')}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {canEdit && (
              <Switch
                checked={domain.is_active}
                onCheckedChange={onToggle}
              />
            )}
            <Button size="sm" variant="outline" onClick={onCheckDns} className="gap-1">
              <RefreshCw className="w-3.5 h-3.5" /> {t('mailServer.checkDns')}
            </Button>
            <Button size="sm" variant="outline" onClick={onViewDns}>
              {t('mailServer.viewRecords')}
            </Button>
            {canDelete && (
              <Button size="sm" variant="ghost" onClick={onDelete} className="text-red-400 hover:text-red-300">
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Sender name */}
        <div className="flex items-center gap-3 mt-4 p-3 rounded-lg bg-dark-600/30 border border-dark-400/10">
          <div className="flex-1 min-w-0">
            <span className="text-xs text-muted-foreground">{t('mailServer.senderName')}:</span>
            {editingFromName ? (
              <div className="flex items-center gap-2 mt-1">
                <Input
                  value={fromNameValue}
                  onChange={(e) => setFromNameValue(e.target.value)}
                  placeholder={t('mailServer.senderNamePlaceholder')}
                  className="h-8 text-sm"
                />
                <Button size="sm" variant="outline" className="h-8 shrink-0" onClick={() => updateFromNameMut.mutate()} disabled={updateFromNameMut.isPending}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="h-8 shrink-0" onClick={() => { setEditingFromName(false); setFromNameValue(domain.from_name || '') }}>
                  <X className="w-3.5 h-3.5" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-sm text-white">{domain.from_name || <span className="text-dark-300 italic">{t('mailServer.notSet')}</span>}</span>
                {canEdit && (
                  <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setEditingFromName(true)}>
                    <Mail className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* DNS status badges */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-4">
          {(['mx', 'spf', 'dkim', 'dmarc', 'ptr'] as const).map((rec) => {
            const ok = domain[`dns_${rec}_ok` as keyof MailDomain] as boolean
            return (
              <div key={rec} className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm",
                ok
                  ? "bg-green-500/10 border-green-500/30 text-green-400"
                  : "bg-dark-600/50 border-dark-400/20 text-dark-200"
              )}>
                {ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                {rec.toUpperCase()}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── DNS Records Dialog ────────────────────────────────────────

function DnsRecordsDialog({ domainId, onClose }: { domainId: number; onClose: () => void }) {
  const { t } = useTranslation()

  const { data: records, isLoading } = useQuery({
    queryKey: ['mailserver-dns-records', domainId],
    queryFn: () => mailserverApi.getDnsRecords(domainId),
  })

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success(t('common.copied'))
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('mailServer.dnsRecords')}</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="space-y-3">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
        ) : (
          <div className="space-y-3 max-h-[60vh] overflow-y-auto">
            {records?.map((rec, idx) => (
              <div
                key={idx}
                className={cn(
                  "p-4 rounded-lg border",
                  rec.is_configured
                    ? "bg-green-500/5 border-green-500/30"
                    : "bg-dark-600/50 border-dark-400/20"
                )}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {rec.record_type}
                    </Badge>
                    <span className="text-sm font-medium text-white">{rec.purpose}</span>
                  </div>
                  {rec.is_configured ? (
                    <CheckCircle2 className="w-4 h-4 text-green-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-400" />
                  )}
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground">{t('mailServer.host')}:</span>
                    <code className="text-dark-100 break-all">{rec.host}</code>
                  </div>
                  <div className="flex items-start gap-1">
                    <span className="text-muted-foreground shrink-0">{t('mailServer.value')}:</span>
                    <code className="text-dark-100 break-all flex-1">{rec.value}</code>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 w-5 p-0 shrink-0"
                      onClick={() => copyToClipboard(rec.value)}
                    >
                      <Copy className="w-3 h-3" />
                    </Button>
                  </div>
                  {rec.current_value && (
                    <div className="flex items-start gap-1">
                      <span className="text-muted-foreground shrink-0">{t('mailServer.current')}:</span>
                      <code className="text-dark-200 break-all">{rec.current_value}</code>
                    </div>
                  )}
                  {rec.purpose === 'PTR' && (
                    <p className="text-amber-400/80 mt-1.5">{t('mailServer.ptrHint')}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Queue Tab ─────────────────────────────────────────────────

function QueueTab({ canEdit, canDelete }: { canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: stats } = useQuery({
    queryKey: ['mailserver-queue-stats'],
    queryFn: mailserverApi.getQueueStats,
    refetchInterval: 10000,
  })

  const { data: queue, isLoading } = useQuery({
    queryKey: ['mailserver-queue', statusFilter],
    queryFn: () => mailserverApi.listQueue({
      status: statusFilter === 'all' ? undefined : statusFilter,
      limit: 100,
    }),
    refetchInterval: 10000,
  })

  const retryMut = useMutation({
    mutationFn: mailserverApi.retryQueueItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-queue'] })
      toast.success(t('mailServer.retryQueued'))
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const cancelMut = useMutation({
    mutationFn: mailserverApi.cancelQueueItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-queue'] })
      toast.success(t('mailServer.cancelled'))
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  return (
    <div className="space-y-4">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: t('mailServer.pending'), value: stats.pending, color: 'text-yellow-400' },
            { label: t('mailServer.sent'), value: stats.sent, color: 'text-green-400' },
            { label: t('mailServer.failed'), value: stats.failed, color: 'text-red-400' },
            { label: t('mailServer.total'), value: stats.total, color: 'text-white' },
          ].map((s) => (
            <Card key={s.label} className="bg-dark-700/50 border-dark-400/20">
              <CardContent className="p-3 text-center">
                <div className={cn("text-2xl font-bold", s.color)}>{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('mailServer.allStatuses')}</SelectItem>
            <SelectItem value="pending">{t('mailServer.pending')}</SelectItem>
            <SelectItem value="sent">{t('mailServer.sent')}</SelectItem>
            <SelectItem value="failed">{t('mailServer.failed')}</SelectItem>
            <SelectItem value="cancelled">{t('mailServer.cancelledStatus')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Queue list */}
      {isLoading ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : !queue?.length ? (
        <Card className="bg-dark-700/50 border-dark-400/20">
          <CardContent className="py-12 text-center">
            <ListOrdered className="w-12 h-12 mx-auto text-dark-300 mb-3" />
            <p className="text-muted-foreground">{t('mailServer.noQueueItems')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {queue.map((item) => (
            <Card key={item.id} className="bg-dark-700/50 border-dark-400/20">
              <CardContent className="p-3 sm:p-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className={cn("text-xs", STATUS_BADGE[item.status])}>
                        {item.status}
                      </Badge>
                      {item.category && (
                        <Badge variant="outline" className="text-xs">{item.category}</Badge>
                      )}
                    </div>
                    <p className="text-sm text-white truncate">{item.subject}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {item.from_email} &rarr; {item.to_email}
                    </p>
                    {item.last_error && (
                      <p className="text-xs text-red-400 truncate mt-1">{item.last_error}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-muted-foreground">
                      {item.attempts}/{item.max_attempts}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(item.sent_at || item.created_at)}
                    </span>
                    {canEdit && item.status === 'failed' && (
                      <Button size="sm" variant="ghost" onClick={() => retryMut.mutate(item.id)} title={t('mailServer.retry')}>
                        <RotateCcw className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    {canEdit && (item.status === 'pending' || item.status === 'failed') && (
                      <Button size="sm" variant="ghost" onClick={() => cancelMut.mutate(item.id)} className="text-red-400" title={t('mailServer.cancel')}>
                        <Ban className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Inbox Tab ─────────────────────────────────────────────────

function InboxTab({ canEdit, canDelete }: { canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: inbox, isLoading } = useQuery({
    queryKey: ['mailserver-inbox'],
    queryFn: () => mailserverApi.listInbox({ limit: 100 }),
    refetchInterval: 30000,
  })

  const { data: detail } = useQuery({
    queryKey: ['mailserver-inbox-detail', selectedId],
    queryFn: () => mailserverApi.getInboxItem(selectedId!),
    enabled: !!selectedId,
  })

  const markReadMut = useMutation({
    mutationFn: (ids: number[]) => mailserverApi.markRead(ids),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mailserver-inbox'] }),
  })

  const deleteMut = useMutation({
    mutationFn: mailserverApi.deleteInboxItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-inbox'] })
      setSelectedId(null)
      setDeleteId(null)
      toast.success(t('mailServer.messageDeleted'))
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const openMessage = (item: InboxItem) => {
    setSelectedId(item.id)
    if (!item.is_read && canEdit) {
      markReadMut.mutate([item.id])
    }
  }

  if (isLoading) return <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>

  return (
    <div className="space-y-4">
      {/* Actions bar */}
      <div className="flex items-center gap-3">
        {canEdit && inbox && inbox.some(m => !m.is_read) && (
          <Button size="sm" variant="outline" onClick={() => markReadMut.mutate([])} className="gap-1.5">
            <MailOpen className="w-4 h-4" /> {t('mailServer.markAllRead')}
          </Button>
        )}
      </div>

      {/* Inbox list + detail */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Message list */}
        <div className="space-y-1">
          {!inbox?.length ? (
            <Card className="bg-dark-700/50 border-dark-400/20">
              <CardContent className="py-12 text-center">
                <Inbox className="w-12 h-12 mx-auto text-dark-300 mb-3" />
                <p className="text-muted-foreground">{t('mailServer.noMessages')}</p>
              </CardContent>
            </Card>
          ) : (
            inbox.map((item) => (
              <div
                key={item.id}
                onClick={() => openMessage(item)}
                className={cn(
                  "p-3 rounded-lg border cursor-pointer transition-colors",
                  item.id === selectedId
                    ? "bg-primary/10 border-primary/30"
                    : "bg-dark-700/50 border-dark-400/20 hover:border-dark-300/30",
                  !item.is_read && "border-l-2 border-l-primary"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className={cn("text-sm truncate", !item.is_read ? "text-white font-semibold" : "text-dark-100")}>
                    {item.from_header || item.mail_from || t('mailServer.unknown')}
                  </p>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {formatDate(item.date_header || item.created_at)}
                  </span>
                </div>
                <p className="text-sm text-dark-200 truncate">{item.subject || t('mailServer.noSubject')}</p>
                <div className="flex items-center gap-2 mt-1">
                  {item.has_attachments && (
                    <Badge variant="outline" className="text-xs">{item.attachment_count} att.</Badge>
                  )}
                  {item.is_spam && (
                    <Badge variant="outline" className="text-xs bg-red-500/20 text-red-400 border-red-500/30">spam</Badge>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Detail panel */}
        {detail ? (
          <Card className="bg-dark-700/50 border-dark-400/20">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base text-white truncate">{detail.subject || t('mailServer.noSubject')}</CardTitle>
                <div className="flex items-center gap-1">
                  {canDelete && (
                    <Button size="sm" variant="ghost" className="text-red-400" onClick={() => setDeleteId(detail.id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => setSelectedId(null)}>
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-xs space-y-1">
                <p><span className="text-muted-foreground">{t('mailServer.from')}:</span> <span className="text-dark-100">{detail.from_header || detail.mail_from}</span></p>
                <p><span className="text-muted-foreground">{t('mailServer.to')}:</span> <span className="text-dark-100">{detail.to_header || detail.rcpt_to}</span></p>
                <p><span className="text-muted-foreground">{t('mailServer.date')}:</span> <span className="text-dark-100">{formatDate(detail.date_header)}</span></p>
                {detail.remote_ip && (
                  <p><span className="text-muted-foreground">IP:</span> <span className="text-dark-100">{detail.remote_ip}</span></p>
                )}
              </div>
              <div className="border-t border-dark-400/20 pt-3">
                {detail.body_html ? (
                  <iframe
                    sandbox=""
                    srcDoc={detail.body_html}
                    className="w-full min-h-[200px] border-0 bg-white rounded"
                    title="Email content"
                  />
                ) : (
                  <pre className="text-sm text-dark-100 whitespace-pre-wrap break-words">{detail.body_text || t('mailServer.noContent')}</pre>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="bg-dark-700/50 border-dark-400/20 hidden lg:block">
            <CardContent className="py-20 text-center">
              <Mail className="w-12 h-12 mx-auto text-dark-300 mb-3" />
              <p className="text-muted-foreground">{t('mailServer.selectMessage')}</p>
            </CardContent>
          </Card>
        )}
      </div>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={() => setDeleteId(null)}
        title={t('mailServer.deleteMessage')}
        description={t('mailServer.deleteMessageConfirm')}
        onConfirm={() => deleteId && deleteMut.mutate(deleteId)}
        variant="destructive"
      />
    </div>
  )
}

// ── Compose Tab ───────────────────────────────────────────────

function ComposeTab() {
  const { t } = useTranslation()
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')

  const { data: domains } = useQuery({
    queryKey: ['mailserver-domains'],
    queryFn: mailserverApi.listDomains,
  })

  const activeDomains = domains?.filter(d => d.is_active && d.outbound_enabled) || []
  const [selectedDomainId, setSelectedDomainId] = useState<string>('')

  const sendMut = useMutation({
    mutationFn: () => {
      const domain = activeDomains.find(d => String(d.id) === selectedDomainId)
      return mailserverApi.sendEmail({
        to_email: to,
        subject,
        body_text: body,
        from_email: domain ? `noreply@${domain.domain}` : undefined,
        from_name: domain?.from_name || undefined,
        domain_id: domain?.id,
      })
    },
    onSuccess: () => {
      toast.success(t('mailServer.emailQueued'))
      setTo('')
      setSubject('')
      setBody('')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const testMut = useMutation({
    mutationFn: () => {
      const domain = activeDomains.find(d => String(d.id) === selectedDomainId)
      return mailserverApi.sendTestEmail({
        to_email: to,
        from_email: domain ? `test@${domain.domain}` : undefined,
        from_name: domain?.from_name || undefined,
      })
    },
    onSuccess: () => toast.success(t('mailServer.testSent')),
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  return (
    <Card className="bg-dark-700/50 border-dark-400/20">
      <CardHeader>
        <CardTitle className="text-white">{t('mailServer.compose')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Domain selector */}
        {activeDomains.length > 0 && (
          <div>
            <Label>{t('mailServer.fromDomain')}</Label>
            <Select value={selectedDomainId} onValueChange={setSelectedDomainId}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder={t('mailServer.selectDomain')} />
              </SelectTrigger>
              <SelectContent>
                {activeDomains.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    noreply@{d.domain}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div>
          <Label>{t('mailServer.to')}</Label>
          <Input
            placeholder="user@example.com"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="mt-1"
          />
        </div>

        <div>
          <Label>{t('mailServer.subject')}</Label>
          <Input
            placeholder={t('mailServer.subjectPlaceholder')}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="mt-1"
          />
        </div>

        <div>
          <Label>{t('mailServer.body')}</Label>
          <Textarea
            placeholder={t('mailServer.bodyPlaceholder')}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            className="mt-1 font-mono text-sm"
          />
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => sendMut.mutate()}
            disabled={!to || !subject || sendMut.isPending}
            className="gap-1.5"
          >
            <Send className="w-4 h-4" />
            {sendMut.isPending ? t('mailServer.sending') : t('mailServer.send')}
          </Button>
          <Button
            variant="outline"
            onClick={() => testMut.mutate()}
            disabled={!to || testMut.isPending}
            className="gap-1.5"
          >
            <Mail className="w-4 h-4" />
            {t('mailServer.sendTest')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Credentials Tab ──────────────────────────────────────────

function CredentialsTab({ canCreate, canEdit, canDelete }: { canCreate: boolean; canEdit: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editCred, setEditCred] = useState<SmtpCredential | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  // Form state
  const [formUsername, setFormUsername] = useState('')
  const [formPassword, setFormPassword] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formDomains, setFormDomains] = useState('')
  const [formMaxPerHour, setFormMaxPerHour] = useState(100)

  const { data: credentials, isLoading } = useQuery({
    queryKey: ['mailserver-smtp-credentials'],
    queryFn: mailserverApi.listSmtpCredentials,
  })

  const resetForm = () => {
    setFormUsername('')
    setFormPassword('')
    setFormDescription('')
    setFormDomains('')
    setFormMaxPerHour(100)
  }

  const openAdd = () => {
    resetForm()
    setShowAdd(true)
  }

  const openEdit = (cred: SmtpCredential) => {
    setFormUsername(cred.username)
    setFormPassword('')
    setFormDescription(cred.description || '')
    setFormDomains((cred.allowed_from_domains || []).join(', '))
    setFormMaxPerHour(cred.max_send_per_hour)
    setEditCred(cred)
  }

  const parseDomains = (raw: string): string[] =>
    raw.split(',').map(s => s.trim()).filter(Boolean)

  const createMut = useMutation({
    mutationFn: () => mailserverApi.createSmtpCredential({
      username: formUsername,
      password: formPassword,
      description: formDescription || undefined,
      allowed_from_domains: parseDomains(formDomains),
      max_send_per_hour: formMaxPerHour,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-smtp-credentials'] })
      toast.success(t('mailServer.credentials.created'))
      setShowAdd(false)
      resetForm()
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const updateMut = useMutation({
    mutationFn: () => mailserverApi.updateSmtpCredential(editCred!.id, {
      ...(formPassword ? { password: formPassword } : {}),
      description: formDescription || undefined,
      allowed_from_domains: parseDomains(formDomains),
      max_send_per_hour: formMaxPerHour,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-smtp-credentials'] })
      toast.success(t('mailServer.credentials.updated'))
      setEditCred(null)
      resetForm()
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      mailserverApi.updateSmtpCredential(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mailserver-smtp-credentials'] }),
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => mailserverApi.deleteSmtpCredential(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mailserver-smtp-credentials'] })
      toast.success(t('mailServer.credentials.deleted'))
      setDeleteId(null)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || t('common.error')),
  })

  if (isLoading) return <div className="space-y-3">{[1, 2].map(i => <Skeleton key={i} className="h-24 w-full" />)}</div>

  return (
    <div className="space-y-4">
      {/* Header + add button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t('mailServer.credentials.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('mailServer.credentials.subtitle')}</p>
        </div>
        {canCreate && (
          <Button size="sm" onClick={openAdd} className="gap-1.5">
            <Plus className="w-4 h-4" /> {t('mailServer.credentials.add')}
          </Button>
        )}
      </div>

      {/* Connection info banner */}
      <Card className="bg-dark-700/30 border-dark-400/10">
        <CardContent className="p-3">
          <p className="text-xs text-muted-foreground mb-1.5">{t('mailServer.credentials.connectionInfo')}</p>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <span><span className="text-muted-foreground">{t('mailServer.credentials.port')}:</span> <span className="text-white font-mono">587</span></span>
            <span><span className="text-muted-foreground">{t('mailServer.credentials.auth')}:</span> <span className="text-white">PLAIN / LOGIN</span></span>
          </div>
        </CardContent>
      </Card>

      {/* Credentials list */}
      {!credentials?.length ? (
        <Card className="bg-dark-700/50 border-dark-400/20">
          <CardContent className="py-12 text-center">
            <KeyRound className="w-12 h-12 mx-auto text-dark-300 mb-3" />
            <p className="text-muted-foreground">{t('mailServer.credentials.noCredentials')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {credentials.map((cred) => (
            <Card key={cred.id} className="bg-dark-700/50 border-dark-400/20">
              <CardContent className="p-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={cn(
                      "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                      cred.is_active ? "bg-green-500/20" : "bg-dark-600"
                    )}>
                      <KeyRound className={cn("w-4 h-4", cred.is_active ? "text-green-400" : "text-dark-300")} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-white font-semibold font-mono text-sm">{cred.username}</span>
                        <Badge variant="outline" className={cn("text-xs",
                          cred.is_active
                            ? "bg-green-500/20 text-green-400 border-green-500/30"
                            : "bg-red-500/20 text-red-400 border-red-500/30"
                        )}>
                          {cred.is_active ? t('mailServer.credentials.active') : t('mailServer.credentials.inactive')}
                        </Badge>
                      </div>
                      {cred.description && (
                        <p className="text-xs text-muted-foreground truncate">{cred.description}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {/* Stats */}
                    <div className="text-xs text-muted-foreground text-right mr-2 hidden sm:block">
                      <div>{t('mailServer.credentials.maxPerHour')}: <span className="text-dark-100">{cred.max_send_per_hour}</span></div>
                      <div>
                        {t('mailServer.credentials.lastLogin')}:{' '}
                        <span className="text-dark-100">
                          {cred.last_login_at ? formatDate(cred.last_login_at) : t('mailServer.credentials.never')}
                        </span>
                      </div>
                    </div>
                    {canEdit && (
                      <Switch
                        checked={cred.is_active}
                        onCheckedChange={(checked) => toggleMut.mutate({ id: cred.id, is_active: checked })}
                      />
                    )}
                    {canEdit && (
                      <Button size="sm" variant="ghost" onClick={() => openEdit(cred)} title={t('mailServer.credentials.edit')}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    {canDelete && (
                      <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300" onClick={() => setDeleteId(cred.id)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>

                {/* Allowed domains chips */}
                {cred.allowed_from_domains && cred.allowed_from_domains.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    <span className="text-xs text-muted-foreground">{t('mailServer.credentials.allowedDomains')}:</span>
                    {cred.allowed_from_domains.map((d) => (
                      <Badge key={d} variant="outline" className="text-xs font-mono">{d}</Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('mailServer.credentials.add')}</DialogTitle>
          </DialogHeader>
          <CredentialForm
            username={formUsername}
            onUsernameChange={setFormUsername}
            password={formPassword}
            onPasswordChange={setFormPassword}
            description={formDescription}
            onDescriptionChange={setFormDescription}
            domains={formDomains}
            onDomainsChange={setFormDomains}
            maxPerHour={formMaxPerHour}
            onMaxPerHourChange={setFormMaxPerHour}
            isNew
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formUsername || !formPassword || createMut.isPending}>
              {createMut.isPending ? t('common.saving') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={editCred !== null} onOpenChange={() => setEditCred(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('mailServer.credentials.edit')}: {editCred?.username}</DialogTitle>
          </DialogHeader>
          <CredentialForm
            username={formUsername}
            onUsernameChange={setFormUsername}
            password={formPassword}
            onPasswordChange={setFormPassword}
            description={formDescription}
            onDescriptionChange={setFormDescription}
            domains={formDomains}
            onDomainsChange={setFormDomains}
            maxPerHour={formMaxPerHour}
            onMaxPerHourChange={setFormMaxPerHour}
            isNew={false}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditCred(null)}>{t('common.cancel')}</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={() => setDeleteId(null)}
        title={t('mailServer.credentials.deleteTitle')}
        description={t('mailServer.credentials.deleteConfirm')}
        onConfirm={() => deleteId && deleteMut.mutate(deleteId)}
        variant="destructive"
      />
    </div>
  )
}

// ── Credential Form (shared between add/edit) ───────────────

function CredentialForm({
  username, onUsernameChange,
  password, onPasswordChange,
  description, onDescriptionChange,
  domains, onDomainsChange,
  maxPerHour, onMaxPerHourChange,
  isNew,
}: {
  username: string; onUsernameChange: (v: string) => void
  password: string; onPasswordChange: (v: string) => void
  description: string; onDescriptionChange: (v: string) => void
  domains: string; onDomainsChange: (v: string) => void
  maxPerHour: number; onMaxPerHourChange: (v: number) => void
  isNew: boolean
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      <div>
        <Label>{t('mailServer.credentials.username')}</Label>
        <Input
          placeholder={t('mailServer.credentials.usernamePlaceholder')}
          value={username}
          onChange={(e) => onUsernameChange(e.target.value)}
          className="mt-1 font-mono"
          disabled={!isNew}
        />
      </div>
      <div>
        <Label>{isNew ? t('mailServer.credentials.password') : t('mailServer.credentials.newPassword')}</Label>
        <Input
          type="password"
          placeholder={t('mailServer.credentials.passwordPlaceholder')}
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          className="mt-1"
        />
        {!isNew && (
          <p className="text-xs text-muted-foreground mt-1">{t('mailServer.credentials.newPasswordHint')}</p>
        )}
      </div>
      <div>
        <Label>{t('mailServer.credentials.description')}</Label>
        <Input
          placeholder={t('mailServer.credentials.descriptionPlaceholder')}
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          className="mt-1"
        />
      </div>
      <div>
        <Label>{t('mailServer.credentials.allowedDomains')}</Label>
        <Input
          placeholder={t('mailServer.credentials.allowedDomainsPlaceholder')}
          value={domains}
          onChange={(e) => onDomainsChange(e.target.value)}
          className="mt-1 font-mono"
        />
        <p className="text-xs text-muted-foreground mt-1">{t('mailServer.credentials.allowedDomainsHint')}</p>
      </div>
      <div>
        <Label>{t('mailServer.credentials.maxPerHour')}</Label>
        <Input
          type="number"
          min={1}
          max={10000}
          value={maxPerHour}
          onChange={(e) => onMaxPerHourChange(Number(e.target.value))}
          className="mt-1 w-32"
        />
      </div>
    </div>
  )
}
