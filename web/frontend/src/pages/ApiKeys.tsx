import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Key,
  Plus,
  Trash2,
  Copy,
  Check,
  Webhook,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react'
import { apiKeysApi, webhooksApi, type ApiKeyCreated } from '../api/apiKeys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { PermissionGate } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useFormatters } from '@/lib/useFormatters'

// ── API Keys Tab ────────────────────────────────────────────────

function ApiKeysTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>([])
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null)
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const { data: keys = [], isLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: apiKeysApi.list,
  })

  const { data: scopes = [] } = useQuery({
    queryKey: ['api-key-scopes'],
    queryFn: apiKeysApi.getScopes,
  })

  const createKey = useMutation({
    mutationFn: apiKeysApi.create,
    onSuccess: (data) => {
      setCreatedKey(data)
      setShowCreate(false)
      setNewKeyName('')
      setNewKeyScopes([])
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('apiKeys.createFailed'))
    },
  })

  const toggleKey = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiKeysApi.update(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })

  const deleteKey = useMutation({
    mutationFn: apiKeysApi.delete,
    onSuccess: () => {
      toast.success(t('apiKeys.deleted'))
      setConfirmDelete(null)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const toggleScope = (scope: string) => {
    setNewKeyScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <PermissionGate resource="api_keys" action="create">
          <Button onClick={() => setShowCreate(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            {t('apiKeys.createKey')}
          </Button>
        </PermissionGate>
        <a
          href="/api/v3/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-primary-400 hover:text-primary-300 flex items-center gap-1"
        >
          API Docs <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      {/* Keys list */}
      <Card className="border-dark-600 bg-dark-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Key className="w-4 h-4" />
            {t('apiKeys.keys')}
            <Badge variant="secondary" className="ml-auto">{keys.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}
            </div>
          ) : keys.length === 0 ? (
            <div className="text-center py-8 text-dark-300">
              <Key className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>{t('apiKeys.noKeys')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-colors"
                >
                  <Key className={`w-5 h-5 flex-shrink-0 ${key.is_active ? 'text-emerald-400' : 'text-dark-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-white truncate">{key.name}</p>
                      <code className="text-xs text-dark-300 bg-dark-600 px-1.5 py-0.5 rounded">
                        {key.key_prefix}...
                      </code>
                      {!key.is_active && (
                        <Badge variant="outline" className="text-xs text-red-400 border-red-500/20">
                          {t('apiKeys.disabled')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-dark-300">
                      {key.scopes.join(', ') || t('apiKeys.noScopes')}
                      {key.last_used_at && ` · ${t('apiKeys.lastUsed')}: ${formatDate(key.last_used_at)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <PermissionGate resource="api_keys" action="edit">
                      <Switch
                        checked={key.is_active}
                        onCheckedChange={(checked) => toggleKey.mutate({ id: key.id, is_active: checked })}
                      />
                    </PermissionGate>
                    <PermissionGate resource="api_keys" action="delete">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300"
                        onClick={() => setConfirmDelete(key.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </PermissionGate>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.createKey')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>{t('apiKeys.keyName')}</Label>
              <Input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder={t('apiKeys.keyNamePlaceholder')}
              />
            </div>
            <div>
              <Label>{t('apiKeys.scopes')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {scopes.map((scope) => (
                  <button
                    key={scope}
                    onClick={() => toggleScope(scope)}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      newKeyScopes.includes(scope)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-dark-700 text-dark-300 border-dark-500 hover:border-dark-400'
                    }`}
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!newKeyName.trim() || createKey.isPending}
              onClick={() => createKey.mutate({ name: newKeyName, scopes: newKeyScopes })}
            >
              {t('apiKeys.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Show created key */}
      <Dialog open={!!createdKey} onOpenChange={() => setCreatedKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.keyCreated')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-300">{t('apiKeys.keyCreatedWarning')}</p>
            </div>
            <div className="relative">
              <code className="block p-3 bg-dark-700 rounded-lg text-sm text-emerald-400 break-all pr-10">
                {createdKey?.raw_key}
              </code>
              <Button
                variant="ghost"
                size="icon"
                className="absolute top-2 right-2 h-7 w-7"
                onClick={() => createdKey && handleCopy(createdKey.raw_key)}
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setCreatedKey(null)}>{t('common.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title={t('apiKeys.confirmDelete')}
        description={t('apiKeys.confirmDeleteDesc')}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => {
          if (confirmDelete) deleteKey.mutate(confirmDelete)
        }}
      />
    </div>
  )
}


// ── Webhooks Tab ────────────────────────────────────────────────

function WebhooksTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', url: '', secret: '', events: [] as string[] })
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const { data: webhooks = [], isLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: webhooksApi.list,
  })

  const { data: events = [] } = useQuery({
    queryKey: ['webhook-events'],
    queryFn: webhooksApi.getEvents,
  })

  const createWebhook = useMutation({
    mutationFn: webhooksApi.create,
    onSuccess: () => {
      toast.success(t('apiKeys.webhookCreated'))
      setShowCreate(false)
      setForm({ name: '', url: '', secret: '', events: [] })
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('apiKeys.createFailed'))
    },
  })

  const toggleWebhook = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      webhooksApi.update(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })

  const deleteWebhook = useMutation({
    mutationFn: webhooksApi.delete,
    onSuccess: () => {
      toast.success(t('apiKeys.webhookDeleted'))
      setConfirmDelete(null)
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })

  const toggleEvent = (event: string) => {
    setForm((prev) => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter((e) => e !== event)
        : [...prev.events, event],
    }))
  }

  return (
    <div className="space-y-6">
      <PermissionGate resource="api_keys" action="create">
        <Button onClick={() => setShowCreate(true)} className="gap-2">
          <Plus className="w-4 h-4" />
          {t('apiKeys.createWebhook')}
        </Button>
      </PermissionGate>

      <Card className="border-dark-600 bg-dark-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Webhook className="w-4 h-4" />
            {t('apiKeys.webhooks')}
            <Badge variant="secondary" className="ml-auto">{webhooks.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}
            </div>
          ) : webhooks.length === 0 ? (
            <div className="text-center py-8 text-dark-300">
              <Webhook className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>{t('apiKeys.noWebhooks')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {webhooks.map((wh) => (
                <div
                  key={wh.id}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-colors"
                >
                  <Webhook className={`w-5 h-5 flex-shrink-0 ${wh.is_active ? 'text-blue-400' : 'text-dark-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-white truncate">{wh.name}</p>
                      {wh.has_secret && (
                        <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/20">
                          {t('apiKeys.signed')}
                        </Badge>
                      )}
                      {wh.failure_count > 0 && (
                        <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/20">
                          {wh.failure_count} {t('apiKeys.failures')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-dark-300 truncate">
                      {wh.url}
                    </p>
                    <p className="text-xs text-dark-400">
                      {wh.events.join(', ')}
                      {wh.last_triggered_at && ` · ${t('apiKeys.lastTriggered')}: ${formatDate(wh.last_triggered_at)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <PermissionGate resource="api_keys" action="edit">
                      <Switch
                        checked={wh.is_active}
                        onCheckedChange={(checked) => toggleWebhook.mutate({ id: wh.id, is_active: checked })}
                      />
                    </PermissionGate>
                    <PermissionGate resource="api_keys" action="delete">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300"
                        onClick={() => setConfirmDelete(wh.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </PermissionGate>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create webhook dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.createWebhook')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>{t('apiKeys.webhookName')}</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder={t('apiKeys.webhookNamePlaceholder')}
              />
            </div>
            <div>
              <Label>URL</Label>
              <Input
                value={form.url}
                onChange={(e) => setForm((p) => ({ ...p, url: e.target.value }))}
                placeholder="https://example.com/webhook"
              />
            </div>
            <div>
              <Label>{t('apiKeys.webhookSecret')}</Label>
              <Input
                value={form.secret}
                onChange={(e) => setForm((p) => ({ ...p, secret: e.target.value }))}
                placeholder={t('apiKeys.webhookSecretPlaceholder')}
              />
            </div>
            <div>
              <Label>{t('apiKeys.events')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {events.map((event) => (
                  <button
                    key={event}
                    onClick={() => toggleEvent(event)}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      form.events.includes(event)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-dark-700 text-dark-300 border-dark-500 hover:border-dark-400'
                    }`}
                  >
                    {event}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!form.name.trim() || !form.url.trim() || createWebhook.isPending}
              onClick={() => createWebhook.mutate(form)}
            >
              {t('apiKeys.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title={t('apiKeys.confirmDeleteWebhook')}
        description={t('apiKeys.confirmDeleteWebhookDesc')}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => {
          if (confirmDelete) deleteWebhook.mutate(confirmDelete)
        }}
      />
    </div>
  )
}


// ── Main Page ───────────────────────────────────────────────────

export default function ApiKeys() {
  const { t } = useTranslation()

  return (
    <PermissionGate resource="api_keys" action="view" fallback={null}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('apiKeys.title')}</h1>
          <p className="text-sm text-dark-300 mt-1">{t('apiKeys.subtitle')}</p>
        </div>

        <Tabs defaultValue="keys">
          <TabsList>
            <TabsTrigger value="keys">{t('apiKeys.tabs.keys')}</TabsTrigger>
            <TabsTrigger value="webhooks">{t('apiKeys.tabs.webhooks')}</TabsTrigger>
          </TabsList>

          <TabsContent value="keys" className="mt-4">
            <ApiKeysTab />
          </TabsContent>
          <TabsContent value="webhooks" className="mt-4">
            <WebhooksTab />
          </TabsContent>
        </Tabs>
      </div>
    </PermissionGate>
  )
}
