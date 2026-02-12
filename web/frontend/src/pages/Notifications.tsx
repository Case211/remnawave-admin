/**
 * Notifications page — full notification center with tabs for:
 * - Notifications list with filters
 * - Alert rules management
 * - Alert logs
 * - Channel settings (per-admin)
 * - SMTP config (superadmin only)
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Bell, BellRing, Settings2, Shield, Mail, MessageSquare, Webhook,
  Check, Trash2, Plus, Power, PowerOff, Pencil, Send, AlertTriangle,
  CheckCircle2, XCircle, ChevronDown, ChevronRight, Info, MonitorSmartphone,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  notificationsApi,
  type Notification,
  type AlertRule,
  type AlertLog,
  type NotificationChannel,
  type SmtpConfig,
} from '@/api/notifications'
import { cn } from '@/lib/utils'

// ── Helpers ────────────────────────────────────────────────────

function timeAgo(dateStr: string | null, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return t('common.justNow')
  if (diff < 3600) return t('common.minutesAgo', { count: Math.floor(diff / 60) })
  if (diff < 86400) return t('common.hoursAgo', { count: Math.floor(diff / 3600) })
  return t('common.daysAgo', { count: Math.floor(diff / 86400) })
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString()
}

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
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('notifications', 'edit')
  const canCreate = useHasPermission('notifications', 'create')
  const canDelete = useHasPermission('notifications', 'delete')

  const [tab, setTab] = useState('notifications')

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{t('notifications.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('notifications.subtitle')}</p>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="bg-dark-700/50 p-1">
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="w-4 h-4" />
            {t('notifications.tabs.notifications')}
          </TabsTrigger>
          <TabsTrigger value="alertRules" className="gap-2">
            <Shield className="w-4 h-4" />
            {t('notifications.tabs.alertRules')}
          </TabsTrigger>
          <TabsTrigger value="alertLogs" className="gap-2">
            <AlertTriangle className="w-4 h-4" />
            {t('notifications.tabs.alertLogs')}
          </TabsTrigger>
          <TabsTrigger value="channels" className="gap-2">
            <Settings2 className="w-4 h-4" />
            {t('notifications.tabs.channels')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="notifications">
          <NotificationsTab />
        </TabsContent>
        <TabsContent value="alertRules">
          <AlertRulesTab canEdit={canEdit} canCreate={canCreate} canDelete={canDelete} />
        </TabsContent>
        <TabsContent value="alertLogs">
          <AlertLogsTab canEdit={canEdit} />
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
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [filterRead, setFilterRead] = useState<string>('all')
  const [filterSeverity, setFilterSeverity] = useState<string>('all')

  const params: Record<string, unknown> = { page, per_page: 20 }
  if (filterRead === 'unread') params.is_read = false
  if (filterRead === 'read') params.is_read = true
  if (filterSeverity !== 'all') params.severity = filterSeverity

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', params],
    queryFn: () => notificationsApi.list(params as Parameters<typeof notificationsApi.list>[0]),
    refetchInterval: 15000,
  })

  const markAllRead = useMutation({
    mutationFn: () => notificationsApi.markRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
      toast.success(t('notifications.allMarkedRead'))
    },
  })

  const deleteOld = useMutation({
    mutationFn: () => notificationsApi.deleteOld(30),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      toast.success(t('notifications.oldDeleted'))
    },
  })

  const deleteOne = useMutation({
    mutationFn: (id: number) => notificationsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
    },
  })

  const items = data?.items || []
  const total = data?.total || 0
  const pages = data?.pages || 1

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex-1">
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
            <div className="flex-1">
              <Label className="text-xs text-dark-300 mb-1 block">{t('notifications.filters.severity')}</Label>
              <Select value={filterSeverity} onValueChange={setFilterSeverity}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('common.all')}</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => markAllRead.mutate()}>
                <Check className="w-4 h-4 mr-1" />
                {t('notifications.markAllRead')}
              </Button>
              <Button variant="outline" size="sm" onClick={() => deleteOld.mutate()} className="text-red-400">
                <Trash2 className="w-4 h-4 mr-1" />
                {t('notifications.deleteOld')}
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
                  className={cn(
                    'flex items-start gap-3 px-4 py-3 border-l-2 hover:bg-dark-600/30 transition-colors',
                    n.is_read ? 'border-l-transparent opacity-60' : `border-l-2 ${n.severity === 'critical' ? 'border-l-red-500' : n.severity === 'warning' ? 'border-l-yellow-500' : 'border-l-cyan-500'}`,
                  )}
                >
                  <div className={cn('w-2 h-2 rounded-full mt-2 flex-shrink-0', SEVERITY_DOT[n.severity] || 'bg-cyan-400')} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={cn('text-sm', n.is_read ? 'text-dark-200' : 'text-white font-medium')}>{n.title}</p>
                      <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', SEVERITY_BADGE[n.severity])}>
                        {n.severity}
                      </Badge>
                      {n.type !== 'info' && (
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">{n.type}</Badge>
                      )}
                    </div>
                    {n.body && <p className="text-xs text-dark-300 mt-0.5">{n.body}</p>}
                    <p className="text-[10px] text-dark-400 mt-1">{formatDate(n.created_at)}</p>
                  </div>
                  <button
                    onClick={() => deleteOne.mutate(n.id)}
                    className="text-dark-400 hover:text-red-400 transition-colors p-1"
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
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Tab: Alert Rules
// ══════════════════════════════════════════════════════════════════

function AlertRulesTab({ canEdit, canCreate, canDelete }: { canEdit: boolean; canCreate: boolean; canDelete: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: () => notificationsApi.listAlertRules(),
  })

  const toggleRule = useMutation({
    mutationFn: (id: number) => notificationsApi.toggleAlertRule(id),
    onSuccess: (rule) => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      toast.success(rule.is_enabled ? t('notifications.alerts.ruleEnabled') : t('notifications.alerts.ruleDisabled'))
    },
  })

  const deleteRule = useMutation({
    mutationFn: (id: number) => notificationsApi.deleteAlertRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      toast.success(t('notifications.alerts.ruleDeleted'))
      setDeleteId(null)
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Badge variant="outline">{rules.length} {t('notifications.alerts.rules')}</Badge>
          <Badge variant="outline" className="text-green-400 border-green-500/30">
            {rules.filter(r => r.is_enabled).length} {t('notifications.alerts.active')}
          </Badge>
        </div>
        {canCreate && (
          <Button onClick={() => { setEditingRule(null); setDialogOpen(true) }} size="sm">
            <Plus className="w-4 h-4 mr-1" />
            {t('notifications.alerts.createRule')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      ) : rules.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-dark-300">
            <Shield className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p>{t('notifications.alerts.noRules')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {rules.map((rule) => (
            <Card key={rule.id} className={cn(!rule.is_enabled && 'opacity-50')}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="text-sm font-medium text-white">{rule.name}</h4>
                      <Badge variant="outline" className={cn('text-[10px] px-1.5', SEVERITY_BADGE[rule.severity])}>
                        {rule.severity}
                      </Badge>
                      {!rule.is_enabled && (
                        <Badge variant="outline" className="text-[10px] px-1.5 text-dark-400">
                          {t('notifications.alerts.disabled')}
                        </Badge>
                      )}
                    </div>
                    {rule.description && (
                      <p className="text-xs text-dark-300 mb-2">{rule.description}</p>
                    )}
                    <div className="flex flex-wrap gap-4 text-xs text-dark-400">
                      <span>{t('notifications.alerts.metric')}: <span className="text-dark-200">{rule.metric}</span></span>
                      <span>{t('notifications.alerts.condition')}: <span className="text-dark-200">{rule.operator} {rule.threshold}</span></span>
                      <span>{t('notifications.alerts.cooldown')}: <span className="text-dark-200">{rule.cooldown_minutes} {t('notifications.alerts.min')}</span></span>
                      <span>{t('notifications.alerts.triggered')}: <span className="text-dark-200">{rule.trigger_count}x</span></span>
                      {rule.channels && rule.channels.length > 0 && (
                        <span>{t('notifications.alerts.channelsLabel')}: <span className="text-dark-200">{rule.channels.join(', ')}</span></span>
                      )}
                      {rule.last_triggered_at && (
                        <span>{t('notifications.alerts.lastTriggered')}: <span className="text-dark-200">{formatDate(rule.last_triggered_at)}</span></span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {canEdit && (
                      <>
                        <Button
                          variant="ghost" size="icon"
                          onClick={() => toggleRule.mutate(rule.id)}
                          className={rule.is_enabled ? 'text-green-400' : 'text-dark-400'}
                        >
                          {rule.is_enabled ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => { setEditingRule(rule); setDialogOpen(true) }}>
                          <Pencil className="w-4 h-4" />
                        </Button>
                      </>
                    )}
                    {canDelete && (
                      <Button variant="ghost" size="icon" className="text-red-400" onClick={() => setDeleteId(rule.id)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Alert Rule Dialog */}
      {dialogOpen && (
        <AlertRuleDialog
          rule={editingRule}
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
        />
      )}

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteId !== null}
        title={t('notifications.alerts.deleteConfirmTitle')}
        description={t('notifications.alerts.deleteConfirmDesc')}
        onConfirm={() => deleteId && deleteRule.mutate(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  )
}

// ── Alert Rule Dialog ───────────────────────────────────────────

function AlertRuleDialog({ rule, open, onClose }: { rule: AlertRule | null; open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const isEdit = !!rule

  const [form, setForm] = useState({
    name: rule?.name || '',
    description: rule?.description || '',
    metric: rule?.metric || 'cpu_usage_percent',
    operator: rule?.operator || 'gt',
    threshold: rule?.threshold ?? 90,
    severity: rule?.severity || 'warning',
    cooldown_minutes: rule?.cooldown_minutes ?? 30,
    channels: rule?.channels || ['in_app'],
    is_enabled: rule?.is_enabled ?? true,
    escalation_minutes: rule?.escalation_minutes ?? 0,
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      isEdit
        ? notificationsApi.updateAlertRule(rule!.id, form)
        : notificationsApi.createAlertRule(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      toast.success(isEdit ? t('notifications.alerts.ruleUpdated') : t('notifications.alerts.ruleCreated'))
      onClose()
    },
    onError: () => toast.error(t('common.error')),
  })

  const metrics = [
    { value: 'cpu_usage_percent', label: 'CPU (%)' },
    { value: 'ram_usage_percent', label: 'RAM (%)' },
    { value: 'disk_usage_percent', label: t('notifications.alerts.metricDisk') },
    { value: 'node_offline_minutes', label: t('notifications.alerts.metricNodeOffline') },
    { value: 'traffic_today_gb', label: t('notifications.alerts.metricTraffic') },
    { value: 'users_online', label: t('notifications.alerts.metricUsersOnline') },
  ]

  const operators = [
    { value: 'gt', label: '>' },
    { value: 'gte', label: '>=' },
    { value: 'lt', label: '<' },
    { value: 'lte', label: '<=' },
    { value: 'eq', label: '=' },
  ]

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('notifications.alerts.editRule') : t('notifications.alerts.createRule')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <Label>{t('notifications.alerts.name')}</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('notifications.alerts.namePlaceholder')}
            />
          </div>

          <div>
            <Label>{t('notifications.alerts.description')}</Label>
            <Input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder={t('notifications.alerts.descriptionPlaceholder')}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>{t('notifications.alerts.metric')}</Label>
              <Select value={form.metric} onValueChange={(v) => setForm({ ...form, metric: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {metrics.map((m) => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('notifications.alerts.operator')}</Label>
              <Select value={form.operator} onValueChange={(v) => setForm({ ...form, operator: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {operators.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('notifications.alerts.threshold')}</Label>
              <Input
                type="number"
                value={form.threshold}
                onChange={(e) => setForm({ ...form, threshold: parseFloat(e.target.value) || 0 })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('notifications.alerts.severityLabel')}</Label>
              <Select value={form.severity} onValueChange={(v) => setForm({ ...form, severity: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('notifications.alerts.cooldown')} ({t('notifications.alerts.min')})</Label>
              <Input
                type="number"
                value={form.cooldown_minutes}
                onChange={(e) => setForm({ ...form, cooldown_minutes: parseInt(e.target.value) || 30 })}
              />
            </div>
          </div>

          <div>
            <Label>{t('notifications.alerts.escalation')} ({t('notifications.alerts.min')}, 0 = {t('notifications.alerts.off')})</Label>
            <Input
              type="number"
              value={form.escalation_minutes}
              onChange={(e) => setForm({ ...form, escalation_minutes: parseInt(e.target.value) || 0 })}
            />
          </div>

          {/* Channel selection */}
          <div>
            <Label className="mb-2 block">{t('notifications.alerts.channelsLabel')}</Label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { key: 'in_app', label: t('notifications.alerts.channelInApp'), Icon: MonitorSmartphone },
                { key: 'telegram', label: 'Telegram', Icon: MessageSquare },
                { key: 'webhook', label: 'Webhook', Icon: Webhook },
                { key: 'email', label: 'Email', Icon: Mail },
              ].map(({ key, label, Icon }) => {
                const checked = form.channels.includes(key)
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      const next = checked
                        ? form.channels.filter((c) => c !== key)
                        : [...form.channels, key]
                      setForm({ ...form, channels: next.length > 0 ? next : ['in_app'] })
                    }}
                    className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors text-left',
                      checked
                        ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-400'
                        : 'border-dark-400/20 bg-dark-800 text-dark-300 hover:border-dark-400/40',
                    )}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="flex-1">{label}</span>
                    {checked && <Check className="w-3.5 h-3.5" />}
                  </button>
                )
              })}
            </div>
            <p className="text-[10px] text-dark-400 mt-1">{t('notifications.alerts.channelsHint')}</p>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              checked={form.is_enabled}
              onCheckedChange={(v) => setForm({ ...form, is_enabled: v })}
            />
            <Label>{t('notifications.alerts.enabled')}</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => saveMutation.mutate()} disabled={!form.name || saveMutation.isPending}>
            {saveMutation.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ══════════════════════════════════════════════════════════════════
// Tab: Alert Logs
// ══════════════════════════════════════════════════════════════════

function AlertLogsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [filterAcknowledged, setFilterAcknowledged] = useState<string>('all')

  const params: Record<string, unknown> = { page, per_page: 20 }
  if (filterAcknowledged === 'unacked') params.acknowledged = false
  if (filterAcknowledged === 'acked') params.acknowledged = true

  const { data, isLoading } = useQuery({
    queryKey: ['alert-logs', params],
    queryFn: () => notificationsApi.listAlertLogs(params as Parameters<typeof notificationsApi.listAlertLogs>[0]),
    refetchInterval: 15000,
  })

  const ackAll = useMutation({
    mutationFn: () => notificationsApi.acknowledgeAlerts(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-logs'] })
      toast.success(t('notifications.alertLogs.allAcknowledged'))
    },
  })

  const ackOne = useMutation({
    mutationFn: (id: number) => notificationsApi.acknowledgeAlerts([id]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-logs'] }),
  })

  const items = data?.items || []
  const pages = data?.pages || 1

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex-1">
              <Label className="text-xs text-dark-300 mb-1 block">{t('notifications.alertLogs.status')}</Label>
              <Select value={filterAcknowledged} onValueChange={setFilterAcknowledged}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('common.all')}</SelectItem>
                  <SelectItem value="unacked">{t('notifications.alertLogs.unacknowledged')}</SelectItem>
                  <SelectItem value="acked">{t('notifications.alertLogs.acknowledged')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {canEdit && (
              <Button variant="outline" size="sm" onClick={() => ackAll.mutate()}>
                <Check className="w-4 h-4 mr-1" />
                {t('notifications.alertLogs.ackAll')}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-dark-300">
              <CheckCircle2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>{t('notifications.alertLogs.noLogs')}</p>
            </div>
          ) : (
            <div className="divide-y divide-dark-400/10">
              {items.map((log) => (
                <div key={log.id} className="flex items-start gap-3 px-4 py-3">
                  <div className={cn('w-2 h-2 rounded-full mt-2 flex-shrink-0', SEVERITY_DOT[log.severity || 'info'])} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm text-white font-medium">{log.rule_name || `Rule #${log.rule_id}`}</p>
                      {log.severity && (
                        <Badge variant="outline" className={cn('text-[10px] px-1.5', SEVERITY_BADGE[log.severity])}>
                          {log.severity}
                        </Badge>
                      )}
                      {log.acknowledged && (
                        <Badge variant="outline" className="text-[10px] px-1.5 text-green-400 border-green-500/30">
                          <Check className="w-3 h-3 mr-0.5" />
                          {t('notifications.alertLogs.acked')}
                        </Badge>
                      )}
                    </div>
                    {log.details && <p className="text-xs text-dark-300 mt-0.5">{log.details}</p>}
                    <div className="flex gap-4 mt-1 text-[10px] text-dark-400">
                      {log.metric_value !== null && (
                        <span>{t('notifications.alerts.value')}: {log.metric_value?.toFixed(1)}</span>
                      )}
                      {log.threshold_value !== null && (
                        <span>{t('notifications.alerts.threshold')}: {log.threshold_value?.toFixed(1)}</span>
                      )}
                      <span>{formatDate(log.created_at)}</span>
                    </div>
                  </div>
                  {canEdit && !log.acknowledged && (
                    <Button variant="ghost" size="icon" onClick={() => ackOne.mutate(log.id)} className="text-cyan-400">
                      <Check className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>&laquo;</Button>
          <span className="text-sm text-dark-300 self-center">{page} / {pages}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>&raquo;</Button>
        </div>
      )}
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
  const [addType, setAddType] = useState('telegram')

  const { data: channels = [], isLoading } = useQuery({
    queryKey: ['notification-channels'],
    queryFn: () => notificationsApi.listChannels(),
  })

  const deleteChannel = useMutation({
    mutationFn: (id: number) => notificationsApi.deleteChannel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
      toast.success(t('notifications.channels.deleted'))
    },
  })

  const toggleChannel = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      notificationsApi.updateChannel(id, { is_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-channels'] })
    },
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
                  <CardContent className="p-4 flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center flex-shrink-0">
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
                    <Button variant="ghost" size="icon" className="text-red-400" onClick={() => deleteChannel.mutate(ch.id)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* SMTP Config (superadmin) */}
      <PermissionGate resource="admins" action="edit">
        <SmtpConfigSection />
      </PermissionGate>

      {/* Add channel dialog */}
      {addDialogOpen && (
        <AddChannelDialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} />
      )}
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
    onError: () => toast.error(t('common.error')),
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
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="webhook">Webhook</SelectItem>
                <SelectItem value="email">Email</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {type === 'telegram' && (
            <>
              <div>
                <Label>Chat ID</Label>
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
              <Label>Webhook URL</Label>
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
              <Label>Email</Label>
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

  const { data: smtp, isLoading } = useQuery({
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
    onError: () => toast.error(t('common.error')),
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
  const populatedRef = useState(false)
  if (smtp && !populatedRef[0]) {
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
    populatedRef[1](true)
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-white flex items-center gap-2">
        <Mail className="w-5 h-5 text-cyan-400" />
        {t('notifications.smtp.title')}
      </h3>

      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
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

          <div className="grid grid-cols-2 gap-3">
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

          <div className="grid grid-cols-2 gap-3">
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
                placeholder="Remnawave Admin"
              />
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Switch
                checked={form.use_tls ?? true}
                onCheckedChange={(v) => setForm({ ...form, use_tls: v, use_ssl: v ? false : form.use_ssl })}
              />
              <Label>TLS (STARTTLS)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.use_ssl ?? false}
                onCheckedChange={(v) => setForm({ ...form, use_ssl: v, use_tls: v ? false : form.use_tls })}
              />
              <Label>SSL</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_enabled ?? false}
                onCheckedChange={(v) => setForm({ ...form, is_enabled: v })}
              />
              <Label>{t('notifications.smtp.enabled')}</Label>
            </div>
          </div>

          <div className="flex gap-3">
            <Button onClick={() => updateSmtp.mutate()} disabled={updateSmtp.isPending}>
              {updateSmtp.isPending ? t('common.saving') : t('common.save')}
            </Button>
            <div className="flex-1 flex gap-2">
              <Input
                placeholder={t('notifications.smtp.testEmailPlaceholder')}
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
              />
              <Button variant="outline" onClick={() => testSmtp.mutate()} disabled={!testEmail || testSmtp.isPending}>
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
