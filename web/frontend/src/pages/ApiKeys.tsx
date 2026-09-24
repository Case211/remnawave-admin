import { useState, useMemo } from 'react'
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
  Pencil,
  Send,
  History,
  Loader2,
  RotateCw,
} from '@/components/brand/icons'
import {
  apiKeysApi,
  webhooksApi,
  type ApiKey,
  type ApiKeyCreated,
  type WebhookSubscription,
  type WebhookDelivery,
  type ApiKeyLimits,
  type WebhookTestResult,
} from '../api/apiKeys'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { PermissionGate } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useFormatters } from '@/lib/useFormatters'
import { useTabParam } from '@/lib/useTabParam'
import { toastMutationError } from '@/lib/mutationToast'
import { squadsApi } from '@/api/squads'

const COPY_RESET_MS = 3500

// ── Shared helpers ──────────────────────────────────────────────

function isValidUrl(value: string): boolean {
  if (!value) return false
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

function ttlToIsoString(ttl: string): string | undefined {
  if (!ttl || ttl === 'never') return undefined
  const now = Date.now()
  const ms: Record<string, number> = {
    '1d': 86400_000,
    '7d': 7 * 86400_000,
    '30d': 30 * 86400_000,
    '90d': 90 * 86400_000,
    '365d': 365 * 86400_000,
  }
  return ms[ttl] ? new Date(now + ms[ttl]).toISOString() : undefined
}

// ── API Keys Tab ────────────────────────────────────────────────

type LimitsForm = { ips: string; squads: string[]; tag: string }

const EMPTY_LIMITS: LimitsForm = { ips: '', squads: [], tag: '' }

function limitsFromKey(key: ApiKey): LimitsForm {
  return { ips: (key.allowed_ips || []).join('\n'), squads: key.user_squads || [], tag: key.user_tag || '' }
}

function limitsPayload(form: LimitsForm): ApiKeyLimits {
  return {
    allowed_ips: form.ips.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean),
    user_squads: form.squads,
    user_tag: form.tag.trim() || null,
  }
}

/** Ограничения ключа: адреса, с которых он работает, и юзеры, которых он видит */
function KeyLimitsFields({ value, onChange }: { value: LimitsForm; onChange: (v: LimitsForm) => void }) {
  const { t } = useTranslation()
  const { data: squads = [] } = useQuery({ queryKey: ['squads-internal'], queryFn: squadsApi.listInternal, staleTime: 60_000 })
  return (
    <div className="space-y-3 rounded-lg border border-[var(--glass-border)] p-3">
      <p className="text-xs font-medium text-dark-200">{t('apiKeys.limits.title')}</p>
      <div>
        <Label htmlFor="key-ips">{t('apiKeys.limits.ips')}</Label>
        <textarea
          id="key-ips"
          rows={2}
          value={value.ips}
          onChange={(e) => onChange({ ...value, ips: e.target.value })}
          placeholder="203.0.113.10&#10;198.51.100.0/24"
          className="mt-1 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 font-mono text-xs"
        />
        <p className="mt-1 text-[11px] text-dark-400">{t('apiKeys.limits.ipsHint')}</p>
      </div>
      <div>
        <Label>{t('apiKeys.limits.squads')}</Label>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {squads.map((squad) => {
            const on = value.squads.includes(squad.uuid)
            return (
              <button
                key={squad.uuid}
                type="button"
                aria-pressed={on}
                onClick={() => onChange({ ...value, squads: on ? value.squads.filter((s) => s !== squad.uuid) : [...value.squads, squad.uuid] })}
                className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                  on ? 'bg-primary/20 text-primary-400 border-primary/40' : 'bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)]'
                }`}
              >
                {squad.name}
              </button>
            )
          })}
        </div>
      </div>
      <div>
        <Label htmlFor="key-tag">{t('apiKeys.limits.tag')}</Label>
        <Input id="key-tag" value={value.tag} maxLength={64} onChange={(e) => onChange({ ...value, tag: e.target.value })} />
      </div>
      <p className="text-[11px] text-dark-400">{t('apiKeys.limits.usersHint')}</p>
    </div>
  )
}

function ApiKeysTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>([])
  const [newKeyTtl, setNewKeyTtl] = useState<string>('never')
  const [newKeyDesc, setNewKeyDesc] = useState('')
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null)
  const [keySaved, setKeySaved] = useState(false)
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [confirmRotate, setConfirmRotate] = useState<number | null>(null)
  const [editKey, setEditKey] = useState<ApiKey | null>(null)
  const [editName, setEditName] = useState('')
  const [editScopes, setEditScopes] = useState<string[]>([])
  const [editDesc, setEditDesc] = useState('')
  const [newKeyLimits, setNewKeyLimits] = useState<LimitsForm>(EMPTY_LIMITS)
  const [editLimits, setEditLimits] = useState<LimitsForm>(EMPTY_LIMITS)
  const [rotateGrace, setRotateGrace] = useState('0')
  const [requestsKey, setRequestsKey] = useState<ApiKey | null>(null)

  const retryLabel = t('common.retry', { defaultValue: 'Повторить' })

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
      setNewKeyTtl('never')
      setNewKeyDesc('')
      setNewKeyLimits(EMPTY_LIMITS)
      setKeySaved(false)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.createFailed'), () => createKey.mutate(vars), retryLabel),
  })

  const rotateKey = useMutation({
    mutationFn: apiKeysApi.rotate,
    onSuccess: (data) => {
      setCreatedKey(data)
      setKeySaved(false)
      setConfirmRotate(null)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.rotateFailed', { defaultValue: 'Rotate failed' }), () => rotateKey.mutate(vars), retryLabel),
  })

  const toggleKey = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiKeysApi.update(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.updateFailed'), () => toggleKey.mutate(vars), retryLabel),
  })

  const updateKey = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { name?: string; scopes?: string[]; description?: string | null } & ApiKeyLimits }) =>
      apiKeysApi.update(id, payload as Parameters<typeof apiKeysApi.update>[1]),
    onSuccess: () => {
      toast.success(t('apiKeys.updated', { defaultValue: 'Ключ обновлён' }))
      setEditKey(null)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.updateFailed'), () => updateKey.mutate(vars), retryLabel),
  })

  const deleteKey = useMutation({
    mutationFn: apiKeysApi.delete,
    onSuccess: () => {
      toast.success(t('apiKeys.deleted'))
      setConfirmDelete(null)
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err, id) =>
      toastMutationError(err, t('apiKeys.deleteFailed'), () => deleteKey.mutate(id), retryLabel),
  })

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), COPY_RESET_MS)
  }

  const toggleScope = (scope: string, scopeState: string[], setter: (s: string[]) => void) => {
    setter(scopeState.includes(scope) ? scopeState.filter((s) => s !== scope) : [...scopeState, scope])
  }

  const openEdit = (key: ApiKey) => {
    setEditKey(key)
    setEditName(key.name)
    setEditScopes(key.scopes)
    setEditDesc(key.description || '')
    setEditLimits(limitsFromKey(key))
  }

  const closeCreatedDialog = () => {
    if (!keySaved) return
    setCreatedKey(null)
    setKeySaved(false)
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
          {t('apiKeys.apiDocs')} <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      {/* Keys list */}
      <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
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
              {keys.map((key) => {
                const expired = key.expires_at && new Date(key.expires_at) < new Date()
                return (
                  <div
                    key={key.id}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors"
                  >
                    <Key className={`w-5 h-5 flex-shrink-0 ${key.is_active && !expired ? 'text-emerald-400' : 'text-dark-400'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-white truncate">{key.name}</p>
                        <code className="text-xs text-dark-300 bg-[var(--glass-bg-hover)] px-1.5 py-0.5 rounded">
                          {key.key_prefix}...
                        </code>
                        {!key.is_active && (
                          <Badge variant="outline" className="text-xs text-red-400 border-red-500/20">
                            {t('apiKeys.disabled')}
                          </Badge>
                        )}
                        {expired && (
                          <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/20">
                            {t('apiKeys.expired', { defaultValue: 'Истёк' })}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-dark-300">
                        {key.scopes.join(', ') || t('apiKeys.noScopes')}
                        {key.last_used_at && ` · ${t('apiKeys.lastUsed')}: ${formatDate(key.last_used_at)}`}
                        {key.expires_at && ` · ${t('apiKeys.expiresAt', { defaultValue: 'Истекает' })}: ${formatDate(key.expires_at)}`}
                      </p>
                      {(key.allowed_ips?.length > 0 || key.user_squads?.length > 0 || key.user_tag || key.prev_valid_until) && (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {key.allowed_ips?.length > 0 && (
                            <Badge variant="outline" className="text-[10px]" title={key.allowed_ips.join(', ')}>
                              {t('apiKeys.limits.ipsBadge', { count: key.allowed_ips.length })}
                            </Badge>
                          )}
                          {(key.user_squads?.length > 0 || key.user_tag) && (
                            <Badge variant="outline" className="text-[10px]">{t('apiKeys.limits.usersBadge')}</Badge>
                          )}
                          {key.prev_valid_until && (
                            <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/30">
                              {t('apiKeys.prevValidUntil', { date: formatDate(key.prev_valid_until) })}
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <PermissionGate resource="api_keys" action="edit">
                        <Switch
                          aria-label={t('apiKeys.toggleActive', { defaultValue: 'Переключить активность' })}
                          checked={key.is_active}
                          onCheckedChange={(checked) => toggleKey.mutate({ id: key.id, is_active: checked })}
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-label={t('apiKeys.requests.title')}
                          title={t('apiKeys.requests.title')}
                          onClick={() => setRequestsKey(key)}
                        >
                          <History className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-label={t('apiKeys.rotate', { defaultValue: 'Rotate key' })}
                          title={t('apiKeys.rotate', { defaultValue: 'Rotate key' })}
                          onClick={() => { setRotateGrace('0'); setConfirmRotate(key.id) }}
                        >
                          <RotateCw className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          aria-label={t('common.edit')}
                          onClick={() => openEdit(key)}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                      </PermissionGate>
                      <PermissionGate resource="api_keys" action="delete">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-red-400 hover:text-red-300"
                          aria-label={t('common.delete')}
                          onClick={() => setConfirmDelete(key.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </PermissionGate>
                    </div>
                  </div>
                )
              })}
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
                autoFocus
              />
            </div>
            <div>
              <Label>{t('apiKeys.ttl', { defaultValue: 'Срок действия' })}</Label>
              <Select value={newKeyTtl} onValueChange={setNewKeyTtl}>
                <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">{t('apiKeys.ttlNever', { defaultValue: 'Никогда' })}</SelectItem>
                  <SelectItem value="1d">1 {t('apiKeys.day', { defaultValue: 'день' })}</SelectItem>
                  <SelectItem value="7d">7 {t('apiKeys.days', { defaultValue: 'дней' })}</SelectItem>
                  <SelectItem value="30d">30 {t('apiKeys.days', { defaultValue: 'дней' })}</SelectItem>
                  <SelectItem value="90d">90 {t('apiKeys.days', { defaultValue: 'дней' })}</SelectItem>
                  <SelectItem value="365d">365 {t('apiKeys.days', { defaultValue: 'дней' })}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('apiKeys.scopes')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {scopes.map((scope) => (
                  <button
                    key={scope}
                    type="button"
                    aria-pressed={newKeyScopes.includes(scope)}
                    onClick={() => toggleScope(scope, newKeyScopes, setNewKeyScopes)}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      newKeyScopes.includes(scope)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)] hover:border-[var(--glass-border)]'
                    }`}
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label>{t('apiKeys.description', { defaultValue: 'Description' })}</Label>
              <Input
                value={newKeyDesc}
                onChange={(e) => setNewKeyDesc(e.target.value)}
                placeholder={t('apiKeys.descriptionPlaceholder', { defaultValue: 'Optional — what is this key used for?' })}
              />
            </div>
            <KeyLimitsFields value={newKeyLimits} onChange={setNewKeyLimits} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!newKeyName.trim() || createKey.isPending}
              onClick={() => createKey.mutate({
                name: newKeyName,
                scopes: newKeyScopes,
                expires_at: ttlToIsoString(newKeyTtl),
                description: newKeyDesc || undefined,
                ...limitsPayload(newKeyLimits),
              })}
            >
              {createKey.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('apiKeys.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Show created key — closing requires checkbox confirm */}
      <Dialog
        open={!!createdKey}
        onOpenChange={(open) => {
          if (!open) closeCreatedDialog()
        }}
      >
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
              <code className="block p-3 bg-[var(--glass-bg)] rounded-lg text-sm text-emerald-400 break-all pr-10">
                {createdKey?.raw_key}
              </code>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('common.copy', { defaultValue: 'Копировать' })}
                className="absolute top-2 right-2 h-7 w-7"
                onClick={() => createdKey && handleCopy(createdKey.raw_key)}
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
            <label className="flex items-start gap-2 cursor-pointer">
              <Checkbox
                checked={keySaved}
                onCheckedChange={(c) => setKeySaved(c === true)}
                className="mt-0.5"
              />
              <span className="text-sm text-dark-200">
                {t('apiKeys.confirmSaved', { defaultValue: 'Я сохранил ключ в безопасном месте' })}
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button onClick={closeCreatedDialog} disabled={!keySaved}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editKey} onOpenChange={(open) => !open && setEditKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.editKey', { defaultValue: 'Редактировать ключ' })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>{t('apiKeys.keyName')}</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div>
              <Label>{t('apiKeys.description', { defaultValue: 'Description' })}</Label>
              <Input value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
            </div>
            <div>
              <Label>{t('apiKeys.scopes')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {scopes.map((scope) => (
                  <button
                    key={scope}
                    type="button"
                    aria-pressed={editScopes.includes(scope)}
                    onClick={() => toggleScope(scope, editScopes, setEditScopes)}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      editScopes.includes(scope)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)]'
                    }`}
                  >
                    {scope}
                  </button>
                ))}
              </div>
            </div>
            <KeyLimitsFields value={editLimits} onChange={setEditLimits} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditKey(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!editName.trim() || updateKey.isPending}
              onClick={() => editKey && updateKey.mutate({
                id: editKey.id,
                payload: { name: editName, scopes: editScopes, description: editDesc || null as unknown as string, ...limitsPayload(editLimits) },
              })}
            >
              {updateKey.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('common.save')}
            </Button>
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

      <Dialog open={!!confirmRotate} onOpenChange={(open) => !open && setConfirmRotate(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.confirmRotate', { defaultValue: 'Rotate this API key?' })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-dark-200">{t('apiKeys.rotateGraceDesc')}</p>
            <Select value={rotateGrace} onValueChange={setRotateGrace}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['0', '1', '6', '24', '72'].map((h) => (
                  <SelectItem key={h} value={h}>
                    {h === '0' ? t('apiKeys.rotateNow') : t('apiKeys.rotateGraceHours', { count: Number(h) })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRotate(null)}>{t('common.cancel')}</Button>
            <Button
              variant={rotateGrace === '0' ? 'destructive' : 'default'}
              disabled={rotateKey.isPending}
              onClick={() => confirmRotate && rotateKey.mutate({ id: confirmRotate, graceHours: Number(rotateGrace) })}
            >
              {rotateKey.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('apiKeys.rotate', { defaultValue: 'Rotate' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {requestsKey && <KeyRequestsDialog apiKey={requestsKey} onClose={() => setRequestsKey(null)} />}
    </div>
  )
}


// ── Webhooks Tab ────────────────────────────────────────────────

function WebhooksTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', url: '', secret: '', events: [] as string[], signature_version: 'v2' as 'v1' | 'v2', description: '' })
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [editWebhook, setEditWebhook] = useState<WebhookSubscription | null>(null)
  const [editForm, setEditForm] = useState({ name: '', url: '', secret: '', events: [] as string[], changeSecret: false, signature_version: 'v2' as 'v1' | 'v2', description: '' })
  const [testWebhookId, setTestWebhookId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<WebhookTestResult | null>(null)
  const [historyWebhookId, setHistoryWebhookId] = useState<number | null>(null)

  const retryLabel = t('common.retry', { defaultValue: 'Повторить' })

  const { data: webhooks = [], isLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: webhooksApi.list,
  })

  const { data: events = [] } = useQuery({
    queryKey: ['webhook-events'],
    queryFn: webhooksApi.getEvents,
  })

  const urlValid = useMemo(() => !form.url || isValidUrl(form.url), [form.url])
  const editUrlValid = useMemo(() => !editForm.url || isValidUrl(editForm.url), [editForm.url])

  const createWebhook = useMutation({
    mutationFn: webhooksApi.create,
    onSuccess: () => {
      toast.success(t('apiKeys.webhookCreated'))
      setShowCreate(false)
      setForm({ name: '', url: '', secret: '', events: [], signature_version: 'v2', description: '' })
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.createFailed'), () => createWebhook.mutate(vars), retryLabel),
  })

  const toggleWebhook = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      webhooksApi.update(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhooks'] }),
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.webhookUpdateFailed'), () => toggleWebhook.mutate(vars), retryLabel),
  })

  const updateWebhook = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { name?: string; url?: string; secret?: string; events?: string[]; signature_version?: 'v1' | 'v2'; description?: string | null } }) =>
      webhooksApi.update(id, payload as Parameters<typeof webhooksApi.update>[1]),
    onSuccess: () => {
      toast.success(t('apiKeys.webhookUpdated', { defaultValue: 'Webhook обновлён' }))
      setEditWebhook(null)
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
    onError: (err, vars) =>
      toastMutationError(err, t('apiKeys.webhookUpdateFailed'), () => updateWebhook.mutate(vars), retryLabel),
  })

  const deleteWebhook = useMutation({
    mutationFn: webhooksApi.delete,
    onSuccess: () => {
      toast.success(t('apiKeys.webhookDeleted'))
      setConfirmDelete(null)
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
    onError: (err, id) =>
      toastMutationError(err, t('apiKeys.webhookDeleteFailed'), () => deleteWebhook.mutate(id), retryLabel),
  })

  const testWebhook = useMutation({
    mutationFn: (id: number) => webhooksApi.test(id),
    onSuccess: (data) => {
      setTestResult(data)
    },
    onError: (err, id) =>
      toastMutationError(err, t('apiKeys.testFailed', { defaultValue: 'Тест не удался' }), () => testWebhook.mutate(id), retryLabel),
  })

  const toggleEvent = (event: string, state: string[], setter: (s: string[]) => void) => {
    setter(state.includes(event) ? state.filter((e) => e !== event) : [...state, event])
  }

  const openEdit = (wh: WebhookSubscription) => {
    setEditWebhook(wh)
    setEditForm({
      name: wh.name,
      url: wh.url,
      secret: '',
      events: wh.events,
      changeSecret: false,
      signature_version: wh.signature_version || 'v2',
      description: wh.description || '',
    })
  }

  const runTest = (id: number) => {
    setTestWebhookId(id)
    setTestResult(null)
    testWebhook.mutate(id)
  }

  return (
    <div className="space-y-6">
      <PermissionGate resource="api_keys" action="create">
        <Button onClick={() => setShowCreate(true)} className="gap-2">
          <Plus className="w-4 h-4" />
          {t('apiKeys.createWebhook')}
        </Button>
      </PermissionGate>

      <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
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
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors"
                >
                  <Webhook className={`w-5 h-5 flex-shrink-0 ${wh.is_active ? 'text-blue-400' : 'text-dark-400'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-white truncate">{wh.name}</p>
                      {wh.has_secret && (
                        <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/20">
                          {t('apiKeys.signed')} · {wh.signature_version || 'v1'}
                        </Badge>
                      )}
                      {wh.auto_disabled_at && (
                        <Badge variant="outline" className="text-xs text-red-400 border-red-500/30" title={wh.disabled_reason || ''}>
                          {t('apiKeys.autoDisabled', { defaultValue: 'Auto-disabled' })}
                        </Badge>
                      )}
                      {wh.failure_count > 0 && (
                        <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/20">
                          {wh.failure_count} {t('apiKeys.failures')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-dark-300 truncate">{wh.url}</p>
                    <p className="text-xs text-dark-400">
                      {wh.events.join(', ')}
                      {wh.last_triggered_at && ` · ${t('apiKeys.lastTriggered')}: ${formatDate(wh.last_triggered_at)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <PermissionGate resource="api_keys" action="edit">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        aria-label={t('apiKeys.testWebhook', { defaultValue: 'Тест webhook' })}
                        title={t('apiKeys.testWebhook', { defaultValue: 'Тест webhook' })}
                        onClick={() => runTest(wh.id)}
                        disabled={testWebhook.isPending && testWebhookId === wh.id}
                      >
                        {testWebhook.isPending && testWebhookId === wh.id
                          ? <Loader2 className="w-4 h-4 animate-spin" />
                          : <Send className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        aria-label={t('apiKeys.deliveryHistory', { defaultValue: 'История вызовов' })}
                        title={t('apiKeys.deliveryHistory', { defaultValue: 'История вызовов' })}
                        onClick={() => setHistoryWebhookId(wh.id)}
                      >
                        <History className="w-4 h-4" />
                      </Button>
                      <Switch
                        aria-label={t('apiKeys.toggleActive', { defaultValue: 'Переключить активность' })}
                        checked={wh.is_active}
                        onCheckedChange={(checked) => toggleWebhook.mutate({ id: wh.id, is_active: checked })}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        aria-label={t('common.edit')}
                        onClick={() => openEdit(wh)}
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                    </PermissionGate>
                    <PermissionGate resource="api_keys" action="delete">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300"
                        aria-label={t('common.delete')}
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

      {/* Create dialog */}
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
                autoFocus
              />
            </div>
            <div>
              <Label>{t('apiKeys.url')}</Label>
              <Input
                type="url"
                value={form.url}
                onChange={(e) => setForm((p) => ({ ...p, url: e.target.value }))}
                placeholder="https://example.com/webhook"
                aria-invalid={!urlValid}
              />
              {!urlValid && (
                <p className="text-xs text-red-400 mt-1">
                  {t('apiKeys.urlInvalid', { defaultValue: 'URL должен начинаться с http:// или https://' })}
                </p>
              )}
            </div>
            <div>
              <Label>{t('apiKeys.webhookSecret')}</Label>
              <Input
                value={form.secret}
                onChange={(e) => setForm((p) => ({ ...p, secret: e.target.value }))}
                placeholder={t('apiKeys.webhookSecretPlaceholder')}
              />
              <p className="text-xs text-dark-400 mt-1">
                {t('apiKeys.secretHint', { defaultValue: 'Подпись отправляется в заголовке X-Webhook-Signature (HMAC-SHA256)' })}
              </p>
            </div>
            <div>
              <Label>{t('apiKeys.signatureVersion', { defaultValue: 'Signature version' })}</Label>
              <Select
                value={form.signature_version}
                onValueChange={(v) => setForm((p) => ({ ...p, signature_version: v as 'v1' | 'v2' }))}
              >
                <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="v2">{t('apiKeys.versionV2')}</SelectItem>
                  <SelectItem value="v1">{t('apiKeys.versionV1')}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-dark-400 mt-1">
                {t('apiKeys.signatureHint', { defaultValue: 'v2 prepends timestamp to HMAC input and sends X-Webhook-Timestamp for replay protection.' })}
              </p>
            </div>
            <div>
              <Label>{t('apiKeys.description', { defaultValue: 'Description' })}</Label>
              <Input
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                placeholder={t('apiKeys.webhookDescPlaceholder', { defaultValue: 'Optional — what does this webhook do?' })}
              />
            </div>
            <div>
              <Label>{t('apiKeys.events')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {events.map((event) => (
                  <button
                    key={event}
                    type="button"
                    aria-pressed={form.events.includes(event)}
                    onClick={() => toggleEvent(event, form.events, (e) => setForm((p) => ({ ...p, events: e })))}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      form.events.includes(event)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)]'
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
              disabled={!form.name.trim() || !isValidUrl(form.url) || createWebhook.isPending}
              onClick={() => createWebhook.mutate(form)}
            >
              {createWebhook.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('apiKeys.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editWebhook} onOpenChange={(open) => !open && setEditWebhook(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.editWebhook', { defaultValue: 'Редактировать webhook' })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>{t('apiKeys.webhookName')}</Label>
              <Input value={editForm.name} onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <Label>{t('apiKeys.url')}</Label>
              <Input
                type="url"
                value={editForm.url}
                onChange={(e) => setEditForm((p) => ({ ...p, url: e.target.value }))}
                aria-invalid={!editUrlValid}
              />
              {!editUrlValid && (
                <p className="text-xs text-red-400 mt-1">
                  {t('apiKeys.urlInvalid', { defaultValue: 'URL должен начинаться с http:// или https://' })}
                </p>
              )}
            </div>
            <div>
              <div className="flex items-center justify-between">
                <Label>{t('apiKeys.webhookSecret')}</Label>
                <label className="flex items-center gap-2 text-xs text-dark-300 cursor-pointer">
                  <Checkbox
                    checked={editForm.changeSecret}
                    onCheckedChange={(c) => setEditForm((p) => ({ ...p, changeSecret: c === true, secret: '' }))}
                  />
                  {t('apiKeys.changeSecret', { defaultValue: 'Сменить секрет' })}
                </label>
              </div>
              {editForm.changeSecret && (
                <Input
                  className="mt-2"
                  value={editForm.secret}
                  onChange={(e) => setEditForm((p) => ({ ...p, secret: e.target.value }))}
                  placeholder={t('apiKeys.webhookSecretPlaceholder')}
                />
              )}
            </div>
            <div>
              <Label>{t('apiKeys.signatureVersion', { defaultValue: 'Signature version' })}</Label>
              <Select
                value={editForm.signature_version}
                onValueChange={(v) => setEditForm((p) => ({ ...p, signature_version: v as 'v1' | 'v2' }))}
              >
                <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="v2">{t('apiKeys.versionV2')}</SelectItem>
                  <SelectItem value="v1">{t('apiKeys.versionV1')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('apiKeys.description', { defaultValue: 'Description' })}</Label>
              <Input
                value={editForm.description}
                onChange={(e) => setEditForm((p) => ({ ...p, description: e.target.value }))}
              />
            </div>
            <div>
              <Label>{t('apiKeys.events')}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {events.map((event) => (
                  <button
                    key={event}
                    type="button"
                    aria-pressed={editForm.events.includes(event)}
                    onClick={() => toggleEvent(event, editForm.events, (e) => setEditForm((p) => ({ ...p, events: e })))}
                    className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                      editForm.events.includes(event)
                        ? 'bg-primary/20 text-primary-400 border-primary/40'
                        : 'bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)]'
                    }`}
                  >
                    {event}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditWebhook(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!editForm.name.trim() || !isValidUrl(editForm.url) || updateWebhook.isPending}
              onClick={() => editWebhook && updateWebhook.mutate({
                id: editWebhook.id,
                payload: {
                  name: editForm.name,
                  url: editForm.url,
                  events: editForm.events,
                  signature_version: editForm.signature_version,
                  description: editForm.description || null as unknown as string,
                  ...(editForm.changeSecret && editForm.secret ? { secret: editForm.secret } : {}),
                },
              })}
            >
              {updateWebhook.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Test result dialog */}
      <Dialog open={!!testResult} onOpenChange={(open) => !open && setTestResult(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('apiKeys.testResult', { defaultValue: 'Результат теста' })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-sm text-dark-300">{t('apiKeys.httpLabel')}</span>
              <Badge variant={testResult?.status_code && testResult.status_code >= 200 && testResult.status_code < 300 ? 'success' : 'destructive'}>
                {testResult?.status_code ?? t('apiKeys.testFailed', { defaultValue: 'Ошибка' })}
              </Badge>
              {testResult?.duration_ms != null && (
                <span className="text-xs text-dark-400">{testResult.duration_ms} ms</span>
              )}
            </div>
            {testResult?.error && (
              <div className="text-sm text-red-400">{testResult.error}</div>
            )}
            {testResult?.response_body && (
              <pre className="text-xs bg-[var(--glass-bg)] p-3 rounded-lg max-h-[300px] overflow-auto whitespace-pre-wrap break-all">
                {testResult.response_body}
              </pre>
            )}
          </div>
          <DialogFooter>
            <Button onClick={() => setTestResult(null)}>{t('common.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delivery history dialog */}
      {historyWebhookId !== null && (
        <DeliveryHistoryDialog
          webhookId={historyWebhookId}
          onClose={() => setHistoryWebhookId(null)}
        />
      )}

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


function KeyRequestsDialog({ apiKey, onClose }: { apiKey: ApiKey; onClose: () => void }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['api-key-requests', apiKey.id],
    queryFn: () => apiKeysApi.requests(apiKey.id),
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('apiKeys.requests.title')} — {apiKey.name}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[500px] overflow-auto py-2">
          {isLoading ? (
            <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : requests.length === 0 ? (
            <p className="py-8 text-center text-dark-400">{t('apiKeys.requests.empty')}</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-dark-400">
                  <th className="py-1 pr-2 font-medium">{t('apiKeys.requests.time')}</th>
                  <th className="py-1 pr-2 font-medium">{t('apiKeys.requests.request')}</th>
                  <th className="py-1 pr-2 font-medium">{t('apiKeys.requests.status')}</th>
                  <th className="py-1 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--glass-border)]">
                    <td className="py-1 pr-2 whitespace-nowrap text-dark-300">{formatDate(r.created_at)}</td>
                    <td className="py-1 pr-2 font-mono text-dark-100 break-all">{r.method} {r.path}</td>
                    <td className="py-1 pr-2">
                      <Badge variant={r.status_code < 400 ? 'success' : 'destructive'}>{r.status_code}</Badge>
                    </td>
                    <td className="py-1 font-mono text-dark-300">{r.ip_address || '\u2014'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <DialogFooter>
          <Button onClick={onClose}>{t('common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeliveryHistoryDialog({ webhookId, onClose }: { webhookId: number; onClose: () => void }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const [eventFilter, setEventFilter] = useState('all')
  const [outcome, setOutcome] = useState<'all' | 'ok' | 'failed'>('all')
  const { data: events = [] } = useQuery({ queryKey: ['webhook-events'], queryFn: webhooksApi.getEvents })
  const { data: deliveries = [], isLoading } = useQuery({
    queryKey: ['webhook-deliveries', webhookId, eventFilter, outcome],
    queryFn: () => webhooksApi.deliveries(webhookId, {
      event: eventFilter === 'all' ? undefined : eventFilter,
      outcome: outcome === 'all' ? undefined : outcome,
    }),
  })
  const redeliver = useMutation({
    mutationFn: (deliveryId: number) => webhooksApi.redeliver(webhookId, deliveryId),
    onSuccess: (result) => {
      const ok = result.status_code != null && result.status_code >= 200 && result.status_code < 300
      if (ok) toast.success(t('apiKeys.redelivered', { status: result.status_code }))
      else toast.error(t('apiKeys.redeliverFailed', { error: result.error || result.status_code || '?' }))
      queryClient.invalidateQueries({ queryKey: ['webhook-deliveries', webhookId] })
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('apiKeys.deliveryHistory', { defaultValue: 'История вызовов' })}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          <Select value={eventFilter} onValueChange={setEventFilter}>
            <SelectTrigger className="w-[220px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('apiKeys.allEvents')}</SelectItem>
              {events.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={outcome} onValueChange={(v) => setOutcome(v as 'all' | 'ok' | 'failed')}>
            <SelectTrigger className="w-[160px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('apiKeys.outcome.all')}</SelectItem>
              <SelectItem value="ok">{t('apiKeys.outcome.ok')}</SelectItem>
              <SelectItem value="failed">{t('apiKeys.outcome.failed')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2 py-2 max-h-[500px] overflow-auto">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}
            </div>
          ) : deliveries.length === 0 ? (
            <p className="text-center text-dark-400 py-8">
              {t('apiKeys.noDeliveries', { defaultValue: 'Пока вызовов не было' })}
            </p>
          ) : (
            deliveries.map((d: WebhookDelivery) => {
              const success = d.status_code >= 200 && d.status_code < 300
              return (
                <div key={d.id} className="px-3 py-2 rounded-lg bg-[var(--glass-bg)]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={success ? 'success' : 'destructive'}>{d.status_code || 'ERR'}</Badge>
                    <code className="text-xs text-dark-200">{d.event}</code>
                    <span className="text-xs text-dark-400 ml-auto">{formatDate(d.sent_at)}</span>
                    {d.duration_ms != null && (
                      <span className="text-xs text-dark-400">{d.duration_ms} ms</span>
                    )}
                    {d.can_redeliver && (
                      <PermissionGate resource="api_keys" action="edit">
                        <Button
                          variant="ghost" size="sm" className="h-6 px-2 text-xs"
                          disabled={redeliver.isPending}
                          onClick={() => redeliver.mutate(d.id)}
                        >
                          {t('apiKeys.redeliver')}
                        </Button>
                      </PermissionGate>
                    )}
                  </div>
                  {d.error && <p className="text-xs text-red-400 mt-1">{d.error}</p>}
                  {d.response_body && (
                    <details className="mt-1">
                      <summary className="text-xs text-dark-400 cursor-pointer hover:text-dark-200">
                        {t('apiKeys.showResponse', { defaultValue: 'Показать ответ' })}
                      </summary>
                      <pre className="text-xs bg-[var(--glass-bg-hover)] p-2 mt-1 rounded max-h-[200px] overflow-auto whitespace-pre-wrap break-all">
                        {d.response_body}
                      </pre>
                    </details>
                  )}
                </div>
              )
            })
          )}
        </div>
        <DialogFooter>
          <Button onClick={onClose}>{t('common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


// ── Main Page ───────────────────────────────────────────────────

export default function ApiKeys() {
  const { t } = useTranslation()
  const [tab, setTab] = useTabParam('keys', ['keys', 'webhooks'])

  return (
    <PermissionGate resource="api_keys" action="view" fallback={null}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('apiKeys.title')}</h1>
          <p className="text-sm text-dark-300 mt-1">{t('apiKeys.subtitle')}</p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
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
