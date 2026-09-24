/**
 * Notifications page — full notification center with tabs for:
 * - Notifications list with filters
 * - Channel settings (per-admin)
 * - SMTP config (superadmin only)
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useTabParam } from '@/lib/useTabParam'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Bell, Settings2, Mail, MessageSquare, Webhook,
  Check, Trash2, Plus, Send, MailOpen,
} from '@/components/brand/icons'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { usePermissionStore } from '@/store/permissionStore'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  notificationsApi,
  type SmtpConfig,
} from '@/api/notifications'
import { cn } from '@/lib/utils'
import { QueryError } from '@/components/QueryError'
import { useFormatters } from '@/lib/useFormatters'

// ── Helpers ────────────────────────────────────────────────────

const SEVERITY_BADGE: Record<string, string> = {
  info: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  success: 'bg-green-500/20 text-green-400 border-green-500/30',
}

const SEVERITY_DOT: Record<string, string> = {
  info: 'bg-cyan-400',
  warning: 'bg-yellow-400',
  critical: 'bg-red-400',
  success: 'bg-green-400',
}

// ── Main Component ─────────────────────────────────────────────

export default function Notifications() {
  const { t } = useTranslation()

  const [tab, setTab] = useTabParam('notifications', ['notifications', 'channels'])

  return (
    <div className="space-y-6 animate-fade-in min-w-0 overflow-x-hidden">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t('notifications.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('notifications.subtitle')}</p>
        <p className="text-xs text-dark-400 mt-2">
          {t('notifications.alertsMoved')}{' '}
          <Link to="/automations" className="text-primary-400 hover:underline">{t('notifications.alertsMovedLink')}</Link>
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab} className="w-full min-w-0">
        <TabsList className="bg-[var(--glass-bg)] p-1 w-full flex overflow-x-auto no-scrollbar">
          <TabsTrigger value="notifications" className="gap-1.5 sm:gap-2 flex-1 min-w-0 px-2 sm:px-3">
            <Bell className="w-4 h-4 flex-shrink-0" />
            <span className="hidden sm:inline truncate">{t('notifications.tabs.notifications')}</span>
          </TabsTrigger>
          <TabsTrigger value="channels" className="gap-1.5 sm:gap-2 flex-1 min-w-0 px-2 sm:px-3">
            <Settings2 className="w-4 h-4 flex-shrink-0" />
            <span className="hidden sm:inline truncate">{t('notifications.tabs.channels')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="notifications">
          <NotificationsTab />
        </TabsContent>
        <TabsContent value="channels">
          <ChannelsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Tab: Notifications
// ══════════════════════════════════════════════════════════════════

function NotificationsTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [filterRead, setFilterRead] = useState<string>('all')
  const [filterSeverity, setFilterSeverity] = useState<string>('all')
  const [confirmDeleteOld, setConfirmDeleteOld] = useState(false)
  const [confirmDeleteRead, setConfirmDeleteRead] = useState(false)

  const params: Record<string, unknown> = { page, per_page: 20 }
  if (filterRead === 'unread') params.is_read = false
  if (filterRead === 'read') params.is_read = true
  if (filterSeverity !== 'all') params.severity = filterSeverity

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['notifications', params],
    queryFn: () => notificationsApi.list(params as Parameters<typeof notificationsApi.list>[0]),
    refetchInterval: 30_000,
  })

  const markAllRead = useMutation({
    mutationFn: () => notificationsApi.markRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
      toast.success(t('notifications.allMarkedRead'))
    },
    onError: () => toast.error(t('common.error')),
  })

  // После массового удаления сбрасываем список, счётчик в шапке и выпадашку
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] })
    queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
    queryClient.invalidateQueries({ queryKey: ['notifications-recent'] })
  }

  const deleteOld = useMutation({
    mutationFn: () => notificationsApi.deleteOld(30),
    onSuccess: () => {
      invalidateAll()
      setPage(1)
      toast.success(t('notifications.oldDeleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  // «Очистить прочитанные»: все прочитанные любого возраста, непрочитанные остаются
  const deleteRead = useMutation({
    mutationFn: () => notificationsApi.deleteRead(),
    onSuccess: (r) => {
      invalidateAll()
      setPage(1)
      toast.success(t('notifications.readDeleted', { count: r.deleted }))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteOne = useMutation({
    mutationFn: (id: number) => notificationsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
    },
    onError: () => toast.error(t('common.error')),
  })

  const items = data?.items || []
  const total = data?.total || 0
  const pages = data?.pages || 1

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
            <div className="flex-1 min-w-0">
              <Label className="text-xs text-dark-300 mb-1 block">{t('notifications.filters.readStatus')}</Label>
              <Select value={filterRead} onValueChange={setFilterRead}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('common.all')}</SelectItem>
                  <SelectItem value="unread">{t('notifications.filters.unread')}</SelectItem>
                  <SelectItem value="read">{t('notifications.filters.read')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 min-w-0">
              <Label className="text-xs text-dark-300 mb-1 block">{t('notifications.filters.severity')}</Label>
              <Select value={filterSeverity} onValueChange={setFilterSeverity}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('common.all')}</SelectItem>
                  <SelectItem value="info">{t('notifications.filters.severityInfo')}</SelectItem>
                  <SelectItem value="warning">{t('notifications.filters.severityWarning')}</SelectItem>
                  <SelectItem value="critical">{t('notifications.filters.severityCritical')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <Button variant="outline" size="sm" onClick={() => markAllRead.mutate()} className="flex-1 sm:flex-none">
                <Check className="w-4 h-4 mr-1" />
                <span className="truncate">{t('notifications.markAllRead')}</span>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setConfirmDeleteRead(true)} className="text-red-400 flex-1 sm:flex-none">
                <MailOpen className="w-4 h-4 mr-1" />
                <span className="truncate">{t('notifications.deleteRead')}</span>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setConfirmDeleteOld(true)} className="text-red-400 flex-1 sm:flex-none">
                <Trash2 className="w-4 h-4 mr-1" />
                <span className="truncate">{t('notifications.deleteOld')}</span>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* List */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          ) : isError ? (
            <div className="p-4"><QueryError onRetry={refetch} /></div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-dark-300">
              <Bell className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>{t('notifications.noNotifications')}</p>
            </div>
          ) : (
            <div className="divide-y divide-dark-400/10">
              {items.map((n) => (
                <div
                  key={n.id}
                  onClick={() => { if (n.link) navigate(n.link) }}
                  className={cn(
                    'flex items-start gap-2 sm:gap-3 px-3 sm:px-4 py-3 border-l-2 hover:bg-[var(--glass-bg-hover)]/30 transition-colors',
                    n.link && 'cursor-pointer',
                    n.is_read ? 'border-l-transparent opacity-60' : `border-l-2 ${n.severity === 'critical' ? 'border-l-red-500' : n.severity === 'warning' ? 'border-l-yellow-500' : 'border-l-cyan-500'}`,
                  )}
                >
                  <div className={cn('w-2 h-2 rounded-full mt-2 flex-shrink-0', SEVERITY_DOT[n.severity] || 'bg-cyan-400')} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className={cn('text-sm', n.is_read ? 'text-dark-200' : 'text-white font-medium')}>{n.title}</p>
                      <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0 flex-shrink-0', SEVERITY_BADGE[n.severity])}>
                        {n.severity}
                      </Badge>
                      {n.type !== 'info' && (
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0 flex-shrink-0">{n.type}</Badge>
                      )}
                    </div>
                    {n.body && <p className="text-xs text-dark-300 mt-0.5">{n.body}</p>}
                    <p className="text-[10px] text-dark-400 mt-1">{n.created_at ? formatDate(n.created_at) : '\u2014'}</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteOne.mutate(n.id) }}
                    className="text-dark-400 hover:text-red-400 transition-colors p-1"
                    aria-label={t('common.delete')}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            &laquo;
          </Button>
          <span className="text-sm text-dark-300 self-center">
            {page} / {pages} ({total})
          </span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            &raquo;
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={confirmDeleteOld}
        onOpenChange={setConfirmDeleteOld}
        title={t('notifications.deleteOldConfirmTitle')}
        description={t('notifications.deleteOldConfirmDesc')}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => deleteOld.mutate()}
      />
      <ConfirmDialog
        open={confirmDeleteRead}
        onOpenChange={setConfirmDeleteRead}
        title={t('notifications.deleteReadConfirmTitle')}
        description={t('notifications.deleteReadConfirmDesc')}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => deleteRead.mutate()}
      />
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Tab: Channels (per-admin) + SMTP config (superadmin)
// ══════════════════════════════════════════════════════════════════

function ChannelsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [deleteChannelId, setDeleteChannelId] = useState<number | null>(null)
  const isSuperadmin = usePermissionStore((s) => s.role) === 'superadmin'

  const { data: channels = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['notification-channels'],
    queryFn: () => notificationsApi.listChannels(),
  })

  const deleteChannel = useMutation({
    mutationFn: (id: number) => notificationsApi.deleteChannel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
      toast.success(t('notifications.channels.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const toggleChannel = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      notificationsApi.updateChannel(id, { is_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
    },
    onError: () => toast.error(t('common.error')),
  })

  const channelIcons: Record<string, typeof Mail> = {
    telegram: MessageSquare,
    webhook: Webhook,
    email: Mail,
  }

  return (
    <div className="space-y-6">
      {/* Per-admin channels */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">{t('notifications.channels.title')}</h3>
          <Button onClick={() => setAddDialogOpen(true)} size="sm">
            <Plus className="w-4 h-4 mr-1" />
            {t('notifications.channels.add')}
          </Button>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
          </div>
        ) : isError ? (
          <QueryError onRetry={refetch} />
        ) : channels.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-dark-300">
              <Settings2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>{t('notifications.channels.noChannels')}</p>
              <p className="text-xs mt-1">{t('notifications.channels.noChannelsHint')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {channels.map((ch) => {
              const Icon = channelIcons[ch.channel_type] || Bell
              return (
                <Card key={ch.id}>
                  <CardContent className="p-3 sm:p-4 flex items-center gap-3 sm:gap-4">
                    <div className="w-10 h-10 rounded-lg bg-[var(--glass-bg-hover)] flex items-center justify-center flex-shrink-0">
                      <Icon className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-medium text-white capitalize">{ch.channel_type}</h4>
                        {ch.is_enabled ? (
                          <Badge variant="outline" className="text-[10px] text-green-400 border-green-500/30">{t('common.enabled')}</Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px] text-dark-400">{t('common.disabled')}</Badge>
                        )}
                      </div>
                      <p className="text-xs text-dark-300 mt-0.5 truncate">
                        {ch.channel_type === 'telegram' && (ch.config?.chat_id || '—')}
                        {ch.channel_type === 'webhook' && (ch.config?.url || '—')}
                        {ch.channel_type === 'email' && (ch.config?.email || '—')}
                      </p>
                    </div>
                    <Switch
                      checked={ch.is_enabled}
                      onCheckedChange={(v) => toggleChannel.mutate({ id: ch.id, enabled: v })}
                    />
                    <Button variant="ghost" size="icon" className="text-red-400" onClick={() => setDeleteChannelId(ch.id)} aria-label={t('common.delete')}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* SMTP Config (superadmin only — backend requires require_superadmin()) */}
      {isSuperadmin && <SmtpConfigSection />}

      {/* Add channel dialog */}
      {addDialogOpen && (
        <AddChannelDialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} />
      )}

      <ConfirmDialog
        open={deleteChannelId !== null}
        onOpenChange={(open) => { if (!open) setDeleteChannelId(null) }}
        title={t('notifications.channels.deleteConfirmTitle', { defaultValue: 'Удалить канал?' })}
        description={t('notifications.channels.deleteConfirmDesc', { defaultValue: 'Канал уведомлений будет удалён. Алерты перестанут отправляться в него.' })}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => { if (deleteChannelId !== null) deleteChannel.mutate(deleteChannelId) }}
      />
    </div>
  )
}

// ── Add Channel Dialog ──────────────────────────────────────────

function AddChannelDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [type, setType] = useState('telegram')
  const [config, setConfig] = useState<Record<string, string>>({})

  const createMutation = useMutation({
    mutationFn: () => notificationsApi.createChannel({ channel_type: type, is_enabled: true, config }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
      toast.success(t('notifications.channels.created'))
      onClose()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => toast.error(err.response?.data?.detail || t('common.error')),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('notifications.channels.add')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <Label>{t('notifications.channels.type')}</Label>
            <Select value={type} onValueChange={(v) => { setType(v); setConfig({}) }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="telegram">{t('notifications.channels.telegram')}</SelectItem>
                <SelectItem value="webhook">{t('notifications.channels.webhook')}</SelectItem>
                <SelectItem value="email">{t('notifications.channels.email')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {type === 'telegram' && (
            <>
              <div>
                <Label>{t('notifications.channels.chatId')}</Label>
                <Input
                  value={config.chat_id || ''}
                  onChange={(e) => setConfig({ ...config, chat_id: e.target.value })}
                  placeholder="-1001234567890"
                />
              </div>
              <div>
                <Label>Topic ID ({t('notifications.channels.optional')})</Label>
                <Input
                  value={config.topic_id || ''}
                  onChange={(e) => setConfig({ ...config, topic_id: e.target.value })}
                  placeholder="0"
                />
              </div>
            </>
          )}

          {type === 'webhook' && (
            <div>
              <Label>{t('notifications.channels.webhookUrl')}</Label>
              <Input
                value={config.url || ''}
                onChange={(e) => setConfig({ ...config, url: e.target.value })}
                placeholder="https://discord.com/api/webhooks/..."
              />
              <p className="text-xs text-dark-400 mt-1">{t('notifications.channels.webhookHint')}</p>
            </div>
          )}

          {type === 'email' && (
            <div>
              <Label>{t('notifications.channels.emailLabel')}</Label>
              <Input
                type="email"
                value={config.email || ''}
                onChange={(e) => setConfig({ ...config, email: e.target.value })}
                placeholder="admin@example.com"
              />
              <p className="text-xs text-dark-400 mt-1">{t('notifications.channels.emailHint')}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
            {createMutation.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── SMTP Config Section ─────────────────────────────────────────

function SmtpConfigSection() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [testEmail, setTestEmail] = useState('')

  const { data: smtp, isError: isSmtpError, refetch: refetchSmtp } = useQuery({
    queryKey: ['smtp-config'],
    queryFn: () => notificationsApi.getSmtpConfig(),
    retry: false,
  })

  const [form, setForm] = useState<Partial<SmtpConfig> & { password?: string }>({})

  const updateSmtp = useMutation({
    mutationFn: () => notificationsApi.updateSmtpConfig(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smtp-config'] })
      toast.success(t('notifications.smtp.saved'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => toast.error(err.response?.data?.detail || t('common.error')),
  })

  const testSmtp = useMutation({
    mutationFn: () => notificationsApi.testSmtp(testEmail),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(t('notifications.smtp.testSuccess'))
      } else {
        toast.error(t('notifications.smtp.testFailed'))
      }
    },
    onError: () => toast.error(t('notifications.smtp.testFailed')),
  })

  // Populate form when data loads
  const [populated, setPopulated] = useState(false)
  useEffect(() => {
    if (smtp && !populated) {
      setForm({
        host: smtp.host,
        port: smtp.port,
        username: smtp.username || '',
        from_email: smtp.from_email,
        from_name: smtp.from_name,
        use_tls: smtp.use_tls,
        use_ssl: smtp.use_ssl,
        is_enabled: smtp.is_enabled,
      })
      setPopulated(true)
    }
  }, [smtp, populated])

  if (isSmtpError) {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Mail className="w-5 h-5 text-cyan-400" />
          {t('notifications.smtp.title')}
        </h3>
        <QueryError onRetry={refetchSmtp} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
        <Mail className="w-5 h-5 text-cyan-400" />
        {t('notifications.smtp.title')}
      </h3>

      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label>{t('notifications.smtp.host')}</Label>
              <Input
                value={form.host || ''}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="smtp.gmail.com"
              />
            </div>
            <div>
              <Label>{t('notifications.smtp.port')}</Label>
              <Input
                type="number"
                value={form.port || 587}
                onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || 587 })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label>{t('notifications.smtp.username')}</Label>
              <Input
                value={form.username || ''}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="user@gmail.com"
              />
            </div>
            <div>
              <Label>{t('notifications.smtp.password')}</Label>
              <Input
                type="password"
                value={form.password || ''}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="********"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label>{t('notifications.smtp.fromEmail')}</Label>
              <Input
                value={form.from_email || ''}
                onChange={(e) => setForm({ ...form, from_email: e.target.value })}
                placeholder="noreply@example.com"
              />
            </div>
            <div>
              <Label>{t('notifications.smtp.fromName')}</Label>
              <Input
                value={form.from_name || ''}
                onChange={(e) => setForm({ ...form, from_name: e.target.value })}
                placeholder={t('mailServer.senderNamePlaceholder')}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            <div className="flex items-center gap-2">
              <Switch
                checked={form.use_tls ?? true}
                onCheckedChange={(v) => setForm({ ...form, use_tls: v, use_ssl: v ? false : form.use_ssl })}
              />
              <Label>{t('notifications.channels.tlsStarttls')}</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.use_ssl ?? false}
                onCheckedChange={(v) => setForm({ ...form, use_ssl: v, use_tls: v ? false : form.use_tls })}
              />
              <Label>{t('notifications.channels.ssl')}</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_enabled ?? false}
                onCheckedChange={(v) => setForm({ ...form, is_enabled: v })}
              />
              <Label>{t('notifications.smtp.enabled')}</Label>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <Button onClick={() => updateSmtp.mutate()} disabled={updateSmtp.isPending} className="w-full sm:w-auto">
              {updateSmtp.isPending ? t('common.saving') : t('common.save')}
            </Button>
            <div className="flex-1 flex gap-2 min-w-0">
              <Input
                placeholder={t('notifications.smtp.testEmailPlaceholder')}
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                className="min-w-0"
                aria-label="Email"
              />
              <Button variant="outline" onClick={() => testSmtp.mutate()} disabled={!testEmail || testSmtp.isPending} className="flex-shrink-0">
                <Send className="w-4 h-4 mr-1" />
                {t('notifications.smtp.test')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
