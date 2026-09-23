import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useDeferredAction } from '@/lib/useDeferredAction'
import { toastMutationError } from '@/lib/mutationToast'
import { cmpVersions } from '@/lib/version'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { useUserLinkProps } from '@/lib/useOpenUser'
import { useHasPermission } from '@/components/PermissionGate'
import {
  RefreshCw,
  Activity,
  WifiOff,
  Globe,
  Users,
  BarChart3,
  Clock,
  Plus,
  Key,
  Copy,
  ShieldCheck,
  AlertTriangle,
  Zap,
  Terminal,
  Scan,
  Loader2,
  Bot,
  BotOff,
  GripVertical,
  ArrowUp,
  ArrowUpDown,
  RotateCcw,
  Search,
  Upload,
  X,
} from '@/components/brand/icons'
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  TouchSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  useSortable,
  arrayMove,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import client from '../api/client'
import { resourcesApi } from '../api/resources'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ViewToggle } from '@/components/ViewToggle'
import { useViewMode } from '@/lib/useViewMode'
import { NodesTable } from '@/components/nodes/NodesTable'
import { NodeCompactCard } from '@/components/nodes/NodeCompactCard'
import { NodeShaperDialog } from '@/components/nodes/NodeShaperDialog'
import { ShaperBadge } from '@/components/nodes/ShaperBadge'
import {
  NodeActionsMenu,
  agentStatus,
  countryFlag,
  nodeStatus,
  type AgentStatus,
  type NodeActions,
  type NodeRow,
  type NodeStatus,
} from '@/components/nodes/nodeShared'

// Types
interface Node extends NodeRow {
  is_xray_running: boolean
  message: string | null
  proxy_url?: string | null
  created_at: string
  // Node-agent state (independent of Panel's is_connected)
  agent_v2_last_ping?: string | null
  agent_version?: string | null
}

interface NodeEditFormData {
  name: string
  address: string
  port: string
  note: string
  proxy_url: string
  node_consumption_multiplier: string
}

// API functions
const fetchNodes = async (): Promise<Node[]> => {
  const { data } = await client.get('/nodes', { params: { per_page: 500 } })
  return data.items || data
}

// Node edit modal
function NodeEditModal({
  node,
  open,
  onOpenChange,
  onSave,
  isPending,
  error,
}: {
  node: Node
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const { t } = useTranslation()
  const initForm = (): NodeEditFormData => ({
    name: node.name,
    address: node.address,
    port: String(node.port),
    note: node.note || '',
    proxy_url: node.proxy_url || '',
    node_consumption_multiplier: node.node_consumption_multiplier != null ? String(node.node_consumption_multiplier) : '',
  })
  const [form, setForm] = useState<NodeEditFormData>(initForm)
  const initialProfile = node.config_profile_uuid || ''
  const initialInbounds = node.active_inbound_uuids || []
  const [profileUuid, setProfileUuid] = useState(initialProfile)
  const [inbounds, setInbounds] = useState<string[]>(initialInbounds)

  useEffect(() => {
    setForm(initForm())
    setProfileUuid(node.config_profile_uuid || '')
    setInbounds(node.active_inbound_uuids || [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node])

  const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x))
  const profileChanged = profileUuid !== initialProfile || !sameSet(inbounds, initialInbounds)

  // Порт 1–65535, множитель — неотрицательное число или пусто
  const portNum = Number(form.port)
  const portValid = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535
  const multValid = form.node_consumption_multiplier === '' ||
    (Number.isFinite(Number(form.node_consumption_multiplier)) && Number(form.node_consumption_multiplier) >= 0)

  const handleSubmit = () => {
    const updateData: Record<string, unknown> = {}
    if (form.name !== node.name) updateData.name = form.name
    if (form.address !== node.address) updateData.address = form.address
    const newPort = parseInt(form.port, 10)
    if (!isNaN(newPort) && newPort !== node.port) updateData.port = newPort
    if (form.note !== (node.note || '')) updateData.note = form.note || null
    if (form.proxy_url !== (node.proxy_url || '')) updateData.proxy_url = form.proxy_url || null
    const curMult = node.node_consumption_multiplier != null ? String(node.node_consumption_multiplier) : ''
    if (form.node_consumption_multiplier !== curMult) {
      const m = parseFloat(form.node_consumption_multiplier)
      if (form.node_consumption_multiplier === '') updateData.node_consumption_multiplier = null
      else if (!isNaN(m)) updateData.node_consumption_multiplier = m
    }
    // Панель принимает профиль и inbound'ы только парой
    if (profileChanged && profileUuid) {
      updateData.config_profile_uuid = profileUuid
      updateData.active_inbounds = inbounds
    }
    if (Object.keys(updateData).length === 0) {
      onOpenChange(false)
      return
    }
    onSave(updateData)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('nodes.editNode.title')}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('nodes.editNode.description')}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('nodes.editNode.name')}</Label>
            <Input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('nodes.editNode.namePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.address')}</Label>
            <Input
              type="text"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder={t('nodes.editNode.addressPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.port')}</Label>
            <Input
              type="number"
              min={1}
              max={65535}
              value={form.port}
              onChange={(e) => setForm({ ...form, port: e.target.value })}
              placeholder={t('nodes.editNode.port')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.note')}</Label>
            <Input
              type="text"
              maxLength={255}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder={t('nodes.editNode.notePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.proxyUrl')}</Label>
            <Input
              type="text"
              value={form.proxy_url}
              onChange={(e) => setForm({ ...form, proxy_url: e.target.value })}
              placeholder="socks5://user:pass@host:port"
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.nodeConsumptionMultiplier')}</Label>
            <Input
              type="number"
              step="0.1"
              min={0}
              value={form.node_consumption_multiplier}
              onChange={(e) => setForm({ ...form, node_consumption_multiplier: e.target.value })}
              placeholder="1.0"
            />
          </div>
          <ProfileInboundsPicker
            enabled={open}
            profileUuid={profileUuid}
            inbounds={inbounds}
            onChange={(profile, ibs) => { setProfileUuid(profile); setInbounds(ibs) }}
          />
          {profileChanged && (
            <p className="text-xs text-amber-300/90">{t('nodes.editNode.profileWarning')}</p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t('nodes.actions.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              isPending || !form.name.trim() || !form.address.trim() || !portValid || !multValid ||
              (!!profileUuid && inbounds.length === 0)
            }
          >
            {isPending ? t('nodes.actions.saving') : t('nodes.actions.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Inbound type from config profiles API
interface Inbound {
  uuid: string
  tag: string
  type: string
}

/**
 * Профиль конфигурации и inbound'ы ноды — в окнах создания и правки.
 * Смена профиля сбрасывает выбранные inbound'ы: у другого профиля они свои.
 */
function ProfileInboundsPicker({
  enabled,
  profileUuid,
  inbounds,
  onChange,
}: {
  enabled: boolean
  profileUuid: string
  inbounds: string[]
  onChange: (profileUuid: string, inbounds: string[]) => void
}) {
  const { t } = useTranslation()

  const { data: configProfiles = [] } = useQuery({
    queryKey: ['config-profiles'],
    queryFn: resourcesApi.getConfigProfiles,
    enabled,
  })

  const { data: profileInbounds = [] } = useQuery<Inbound[]>({
    queryKey: ['config-profile-inbounds', profileUuid],
    queryFn: async () => {
      const { data } = await client.get(`/config-profiles/${profileUuid}/inbounds`)
      return Array.isArray(data) ? data : []
    },
    enabled: enabled && !!profileUuid,
  })

  const toggleInbound = (uuid: string) =>
    onChange(profileUuid, inbounds.includes(uuid) ? inbounds.filter((id) => id !== uuid) : [...inbounds, uuid])

  const toggleAll = () =>
    onChange(profileUuid, inbounds.length === profileInbounds.length ? [] : profileInbounds.map((ib) => ib.uuid))

  return (
    <>
      <div className="space-y-2">
        <Label>{t('nodes.createNode.configProfile')}</Label>
        <Select value={profileUuid} onValueChange={(uuid) => onChange(uuid, [])}>
          <SelectTrigger>
            <SelectValue placeholder={t('nodes.createNode.selectProfile')} />
          </SelectTrigger>
          <SelectContent>
            {configProfiles.map((p: { uuid: string; name: string }) => (
              <SelectItem key={p.uuid} value={p.uuid}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {profileUuid && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{t('nodes.createNode.inbounds')}</Label>
            {profileInbounds.length > 0 && (
              <button type="button" className="text-xs text-primary hover:underline" onClick={toggleAll}>
                {inbounds.length === profileInbounds.length
                  ? t('nodes.createNode.deselectAll')
                  : t('nodes.createNode.selectAll')}
              </button>
            )}
          </div>
          {profileInbounds.length === 0 ? (
            <p className="text-sm text-dark-300">{t('nodes.createNode.noInbounds')}</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto rounded-lg border border-dark-600 p-3">
              {profileInbounds.map((ib) => (
                <label key={ib.uuid} className="flex items-center gap-2 cursor-pointer">
                  <Checkbox checked={inbounds.includes(ib.uuid)} onCheckedChange={() => toggleInbound(ib.uuid)} />
                  <span className="text-sm">{ib.tag}</span>
                  <span className="text-xs text-dark-300 ml-auto">{ib.type}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  )
}

// Node create modal
function NodeCreateModal({
  open,
  onOpenChange,
  onSave,
  isPending,
  error,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState<NodeEditFormData>({
    name: '',
    address: '',
    port: '2222',
    note: '',
    proxy_url: '',
    node_consumption_multiplier: '',
  })
  const [selectedProfileUuid, setSelectedProfileUuid] = useState('')
  const [selectedInbounds, setSelectedInbounds] = useState<string[]>([])

  // Reset form when modal closes
  useEffect(() => {
    if (!open) {
      setForm({ name: '', address: '', port: '2222', note: '', proxy_url: '', node_consumption_multiplier: '' })
      setSelectedProfileUuid('')
      setSelectedInbounds([])
    }
  }, [open])

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {
      name: form.name.trim(),
      address: form.address.trim(),
      config_profile_uuid: selectedProfileUuid,
      active_inbounds: selectedInbounds,
    }
    const port = parseInt(form.port, 10)
    if (!isNaN(port)) createData.port = port
    onSave(createData)
  }

  const portNum = Number(form.port)
  const portValid = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535
  const isValid = form.name.trim() && form.address.trim() && portValid && selectedProfileUuid && selectedInbounds.length > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('nodes.createNode.title')}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('nodes.createNode.description')}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('nodes.editNode.name')}</Label>
            <Input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={t('nodes.editNode.namePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.address')}</Label>
            <Input
              type="text"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder={t('nodes.editNode.addressPlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('nodes.editNode.port')}</Label>
            <Input
              type="number"
              min={1}
              max={65535}
              value={form.port}
              onChange={(e) => setForm({ ...form, port: e.target.value })}
              placeholder={t('nodes.editNode.port')}
            />
          </div>

          <ProfileInboundsPicker
            enabled={open}
            profileUuid={selectedProfileUuid}
            inbounds={selectedInbounds}
            onChange={(profile, inbounds) => { setSelectedProfileUuid(profile); setSelectedInbounds(inbounds) }}
          />
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t('nodes.actions.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !isValid}
          >
            {isPending ? t('nodes.actions.creating') : t('nodes.actions.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Agent token management modal
function AgentTokenModal({
  node,
  open,
  onOpenChange,
}: {
  node: Node
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [generatedToken, setGeneratedToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [tokenConfirmAction, setTokenConfirmAction] = useState<'generate' | 'revoke' | null>(null)
  const [installCommand, setInstallCommand] = useState<string | null>(null)
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current)
    }
  }, [])

  const { data: tokenStatus, isLoading } = useQuery<{ has_token: boolean; masked_token: string | null }>({
    queryKey: ['node-agent-token', node.uuid],
    queryFn: async () => {
      const { data } = await client.get(`/nodes/${node.uuid}/agent-token`)
      return data
    },
  })

  const generateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await client.post(`/nodes/${node.uuid}/agent-token/generate`)
      return data
    },
    onSuccess: (data) => {
      setGeneratedToken(data.token)
      queryClient.invalidateQueries({ queryKey: ['node-agent-token', node.uuid] })
      toast.success(t('nodes.toast.tokenGenerated'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: async () => {
      await client.post(`/nodes/${node.uuid}/agent-token/revoke`)
    },
    onSuccess: () => {
      setGeneratedToken(null)
      queryClient.invalidateQueries({ queryKey: ['node-agent-token', node.uuid] })
      toast.success(t('nodes.toast.tokenRevoked'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const installMutation = useMutation({
    mutationFn: async () => {
      const { data } = await client.post(`/nodes/${node.uuid}/agent-install`)
      return data
    },
    onSuccess: (data) => {
      setInstallCommand(data.install_command)
      if (data.token) setGeneratedToken(data.token)
      queryClient.invalidateQueries({ queryKey: ['node-agent-token', node.uuid] })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Fallback for non-HTTPS or restricted contexts
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current)
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000)
  }

  // Auto-detect backend URL from current page origin (strip port — behind reverse proxy)
  const backendUrl = `${window.location.protocol}//${window.location.hostname}`
  const wsUrl = backendUrl.replace(/^http/, 'ws')

  const envConfig = generatedToken
    ? `AGENT_NODE_UUID=${node.uuid}\nAGENT_AUTH_TOKEN=${generatedToken}\nAGENT_COLLECTOR_URL=${backendUrl}\nAGENT_WS_URL=${wsUrl}\nAGENT_COMMAND_ENABLED=true`
    : null

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-primary-400" />
            <DialogTitle>{t('nodes.agentToken.title')}</DialogTitle>
          </div>
          <DialogDescription>
            {t('nodes.agentToken.node')}: <span className="text-white font-medium">{node.name}</span>
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8 text-center">
            <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Token status */}
            <div className="p-3 bg-[var(--glass-bg)] rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-200">{t('nodes.agentToken.status')}</span>
                {tokenStatus?.has_token ? (
                  <span className="flex items-center gap-1.5 text-sm text-green-400">
                    <ShieldCheck className="w-4 h-4" />
                    {t('nodes.agentToken.installed')}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-sm text-yellow-400">
                    <AlertTriangle className="w-4 h-4" />
                    {t('nodes.agentToken.notInstalled')}
                  </span>
                )}
              </div>
              {tokenStatus?.masked_token && !generatedToken && (
                <p className="text-xs text-dark-300 font-mono mt-2">{tokenStatus.masked_token}</p>
              )}
            </div>

            {/* Версия агента: что стоит на ноде и надо ли обновлять */}
            {(node.has_agent_token || node.agent_v2_connected) && (
              <AgentVersionRow node={node} />
            )}

            {/* Generated token display */}
            {generatedToken && (
              <div className="p-3 bg-primary-500/5 border border-primary-500/20 rounded-lg space-y-3">
                <div className="flex items-center gap-1.5 text-xs text-yellow-400">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {t('nodes.agentToken.saveWarning')}
                </div>
                <div className="relative">
                  <pre className="text-xs text-primary-300 font-mono bg-[var(--glass-bg)] p-2.5 rounded overflow-x-auto whitespace-pre-wrap break-all">{generatedToken}</pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-1.5 right-1.5 h-7 w-7 text-dark-300 hover:text-white"
                    onClick={() => copyToClipboard(generatedToken)}
                    title={t('nodes.agentToken.copyToken')}
                    aria-label={t('common.copy')}
                  >
                    <Copy className="w-4 h-4" />
                  </Button>
                </div>

                {/* Env config hint */}
                {envConfig && (
                  <div>
                    <p className="text-xs text-dark-300 mb-1.5">{t('nodes.agentToken.envHint')}:</p>
                    <div className="relative">
                      <pre className="text-[11px] text-dark-200 font-mono bg-[var(--glass-bg)] p-2.5 rounded overflow-x-auto whitespace-pre-wrap break-all">{envConfig}</pre>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-1.5 right-1.5 h-7 w-7 text-dark-300 hover:text-white"
                        onClick={() => copyToClipboard(envConfig)}
                        title={t('nodes.agentToken.copyConfig')}
                        aria-label={t('common.copy')}
                      >
                        <Copy className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                )}

                {copied && (
                  <p className="text-xs text-green-400">{t('nodes.agentToken.copied')}</p>
                )}
              </div>
            )}

            {/* Install command */}
            {installCommand && (
              <div className="p-3 bg-[var(--glass-bg)] border border-green-500/20 rounded-lg space-y-2">
                <p className="text-xs text-dark-300">{t('nodes.agentToken.installHint')}</p>
                <div className="relative">
                  <pre className="text-[11px] text-green-300 font-mono bg-[var(--glass-bg)] p-2.5 rounded overflow-x-auto whitespace-pre-wrap break-all">{installCommand}</pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-1.5 right-1.5 h-7 w-7 text-dark-300 hover:text-white"
                    onClick={() => copyToClipboard(installCommand)}
                    title={t('nodes.agentToken.copyCommand')}
                    aria-label={t('common.copy')}
                  >
                    <Copy className="w-4 h-4" />
                  </Button>
                </div>
                {copied && (
                  <p className="text-xs text-green-400">{t('nodes.agentToken.copied')}</p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 flex-wrap pt-2">
              <Button
                variant="secondary"
                onClick={() => installMutation.mutate()}
                disabled={installMutation.isPending}
              >
                {installMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Terminal className="w-4 h-4 mr-2" />}
                {t('nodes.agentToken.installAgent')}
              </Button>

              <Button
                onClick={() => {
                  if (tokenStatus?.has_token && !generatedToken) {
                    setTokenConfirmAction('generate')
                  } else {
                    generateMutation.mutate()
                  }
                }}
                disabled={generateMutation.isPending}
              >
                <Key className="w-4 h-4 mr-2" />
                {generateMutation.isPending ? t('nodes.agentToken.generating') : tokenStatus?.has_token ? t('nodes.agentToken.regenerate') : t('nodes.agentToken.generate')}
              </Button>

              {tokenStatus?.has_token && (
                <Button
                  variant="secondary"
                  className="text-red-400 hover:text-red-300"
                  onClick={() => {
                    setTokenConfirmAction('revoke')
                  }}
                  disabled={revokeMutation.isPending}
                >
                  {revokeMutation.isPending ? t('nodes.agentToken.revoking') : t('nodes.agentToken.revoke')}
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      open={tokenConfirmAction !== null}
      onOpenChange={(open) => { if (!open) setTokenConfirmAction(null) }}
      title={tokenConfirmAction === 'generate' ? t('nodes.agentToken.confirmGenerate') : t('nodes.agentToken.confirmRevoke')}
      description={tokenConfirmAction === 'generate' ? t('nodes.agentToken.confirmGenerateDesc') : t('nodes.agentToken.confirmRevokeDesc')}
      confirmLabel={tokenConfirmAction === 'generate' ? t('nodes.agentToken.generate') : t('nodes.agentToken.revoke')}
      variant={tokenConfirmAction === 'revoke' ? 'destructive' : 'default'}
      onConfirm={() => {
        if (tokenConfirmAction === 'generate') generateMutation.mutate()
        if (tokenConfirmAction === 'revoke') revokeMutation.mutate()
        setTokenConfirmAction(null)
      }}
    />
    </>
  )
}

// ── Node Users IPs Dialog ──────────────────────────────────────

interface NodeUserIps {
  userId: number | string
  /** Подставляет наш бэкенд по числовому id панели; null — юзера нет в базе */
  uuid?: string | null
  username?: string | null
  ips: ({ ip: string; lastSeen?: string } | string)[]
}

function NodeUsersIpsDialog({ node, open, onClose }: { node: Node; open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
  const userLink = useUserLinkProps()
  const [jobId, setJobId] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)
  const [result, setResult] = useState<{
    isCompleted: boolean; isFailed: boolean
    progress?: { total: number; completed: number; percent: number }
    result?: { success: boolean; nodeUuid: string; users: NodeUserIps[] } | null
  } | null>(null)

  useEffect(() => {
    if (!open) { setJobId(null); setPolling(false); setResult(null); return }
    let cancelled = false
    ;(async () => {
      try {
        const { data } = await client.post(`/users/node/${node.uuid}/fetch-users-ips`)
        if (cancelled) return
        setJobId(data.jobId || data.response?.jobId)
        setPolling(true)
      } catch { if (!cancelled) toast.error(t('nodes.fetchUsersIps.error')) }
    })()
    return () => { cancelled = true }
  }, [open, node.uuid, t])

  useEffect(() => {
    if (!polling || !jobId) return
    let cancelled = false
    const poll = setInterval(async () => {
      try {
        const { data } = await client.get(`/users/node/${node.uuid}/fetch-users-ips/result/${jobId}`)
        if (cancelled) return
        setResult(data)
        if (data.isCompleted || data.isFailed) { setPolling(false); clearInterval(poll) }
      } catch { /* keep polling */ }
    }, 1500)
    return () => { cancelled = true; clearInterval(poll) }
  }, [polling, jobId, node.uuid])

  const users = result?.result?.users || []
  const totalIps = users.reduce((sum, u) => sum + u.ips.length, 0)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Scan className="w-5 h-5 text-primary-400" />
            {t('nodes.fetchUsersIps.title')}
          </DialogTitle>
          <DialogDescription>
            {node.name}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-3">
          {!result?.isCompleted && !result?.isFailed && (
            <div className="py-6 text-center space-y-3">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-primary-400" />
              <p className="text-sm text-dark-200">
                {result?.progress
                  ? `${t('nodes.fetchUsersIps.scanning')} ${result.progress.percent}%`
                  : t('nodes.fetchUsersIps.starting')}
              </p>
              {result?.progress && (
                <div className="w-full h-1.5 bg-dark-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500 rounded-full transition-all duration-300"
                    style={{ width: `${result.progress.percent}%` }}
                  />
                </div>
              )}
            </div>
          )}

          {result?.isFailed && (
            <div className="py-6 text-center">
              <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
              <p className="text-sm text-red-400">{t('nodes.fetchUsersIps.failed')}</p>
            </div>
          )}

          {result?.isCompleted && users.length === 0 && (
            <div className="py-6 text-center">
              <p className="text-sm text-dark-200">{t('nodes.fetchUsersIps.noResults')}</p>
            </div>
          )}

          {result?.isCompleted && users.length > 0 && (
            <>
              <p className="text-xs text-dark-300">
                {t('nodes.fetchUsersIps.found')}: {users.length} {t('nodes.fetchUsersIps.users')}, {totalIps} IP
              </p>
              <div className="space-y-2">
                {users.map((u) => (
                  <div key={u.userId} className="bg-[var(--glass-bg)] rounded-lg border border-[var(--glass-border)] p-2.5">
                    {u.uuid ? (
                      <a
                        href={`/users/${u.uuid}`}
                        {...userLink(u.uuid)}
                        className="block text-sm font-medium text-primary-300 hover:underline mb-1.5 truncate"
                      >
                        {u.username || u.uuid}
                      </a>
                    ) : (
                      <p className="text-xs font-mono text-dark-300 mb-1.5 truncate">
                        {t('nodes.fetchUsersIps.unknownUser', { id: u.userId })}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {u.ips.map((ip, i) => {
                        const addr = typeof ip === 'string' ? ip : ip.ip
                        const seen = typeof ip === 'string' ? undefined : ip.lastSeen
                        return (
                          <Badge
                            key={i}
                            variant="secondary"
                            className="text-[10px] font-mono"
                            title={seen ? t('nodes.fetchUsersIps.lastSeen', { ago: formatTimeAgo(seen) }) : undefined}
                          >
                            {addr}
                            {seen && <span className="ml-1 text-dark-300">· {formatTimeAgo(seen)}</span>}
                          </Badge>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Строка версии агента в диалоге токена: «что стоит» vs «что актуально».
// Обновление агента — обычный git pull на ноде (или fleet-скрипт «Обновление
// агента»), после него версия в панели поднимется сама со следующим батчем.
function AgentVersionRow({ node }: { node: Node }) {
  const { t } = useTranslation()
  const latest = useAgentLatestVersion()
  const outdated = agentOutdated(node.agent_version, latest)
  return (
    <div className="p-3 bg-[var(--glass-bg)] rounded-lg space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-sm text-dark-200">{t('nodes.agent.versionLabel')}</span>
        <span className={cn('text-sm font-mono', outdated ? 'text-amber-300' : 'text-green-400')}>
          {node.agent_version || t('nodes.agent.versionUnknownShort')}
          {latest && !outdated && node.agent_version && ` · ${t('nodes.agent.upToDate')}`}
        </span>
      </div>
      {outdated && (
        <p className="text-xs text-amber-300/90">
          {t('nodes.agent.updateHint', { version: latest })}
        </p>
      )}
    </div>
  )
}

// Эталонная версия агента с бэка — для бейджа «доступно обновление»
function useAgentLatestVersion(): string {
  const { data } = useQuery({
    queryKey: ['agent-meta'],
    queryFn: async () => (await client.get('/nodes/agent-meta')).data as { latest_agent_version: string },
    staleTime: Infinity,
  })
  return data?.latest_agent_version || ''
}

// Агент «устарел», только если эталон панели новее того, что стоит на ноде.
// Раньше строки сравнивались на неравенство, и агент 1.8.1 при эталоне 1.5.0
// (панель отстала от агента) получал «доступна версия v1.5.0». Неизвестная
// версия (старый агент её не репортит) по-прежнему считается устаревшей.
function agentOutdated(current: string | null | undefined, latest: string): boolean {
  if (!latest) return false
  if (!current) return true
  return cmpVersions(latest, current) > 0
}

// Compact agent-state badge shown next to status badge on each node card.
function AgentBadge({ node }: { node: Node }) {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
  const latest = useAgentLatestVersion()

  if (node.agent_v2_connected) {
    // подключён, но версия отстаёт от эталона (или агент её ещё не репортит)
    const outdated = agentOutdated(node.agent_version, latest)
    const versionInfo = node.agent_version
      ? t('nodes.agent.version', { version: node.agent_version })
      : t('nodes.agent.versionUnknown')
    const title = [
      node.agent_v2_last_ping
        ? t('nodes.agent.connectedSince', { ago: formatTimeAgo(node.agent_v2_last_ping) })
        : t('nodes.agent.connected'),
      versionInfo,
      outdated ? t('nodes.agent.updateAvailable', { version: latest }) : '',
    ].filter(Boolean).join(' · ')
    return (
      <Badge
        variant="outline"
        className={cn(
          'gap-1 px-1.5 py-0 text-[10px] h-5',
          outdated
            ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
            : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
        )}
        title={title}
      >
        <Bot className="w-3 h-3" />
        <span className="hidden sm:inline">{t('nodes.agent.connected')}</span>
        {outdated && <ArrowUp className="w-3 h-3" aria-label={t('nodes.agent.updateAvailable', { version: latest })} />}
      </Badge>
    )
  }

  if (node.has_agent_token) {
    return (
      <Badge
        variant="outline"
        className="border-amber-500/40 bg-amber-500/10 text-amber-300 gap-1 px-1.5 py-0 text-[10px] h-5"
        title={
          node.agent_v2_last_ping
            ? t('nodes.agent.offlineSince', { ago: formatTimeAgo(node.agent_v2_last_ping) })
            : t('nodes.agent.offlineNever')
        }
      >
        <Bot className="w-3 h-3" />
        <span className="hidden sm:inline">{t('nodes.agent.offline')}</span>
      </Badge>
    )
  }

  return (
    <Badge
      variant="outline"
      className="border-dark-400/40 bg-dark-500/10 text-dark-200 gap-1 px-1.5 py-0 text-[10px] h-5"
      title={t('nodes.agent.missingHint')}
    >
      <BotOff className="w-3 h-3" />
      <span className="hidden sm:inline">{t('nodes.agent.missing')}</span>
    </Badge>
  )
}

/** Аптайм коротко: «21 д 4 ч», «3 ч 12 мин», «45 мин». */
function formatUptime(seconds: number, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return t('nodes.metrics.uptimeDays', { d, h })
  if (h > 0) return t('nodes.metrics.uptimeHours', { h, m })
  return t('nodes.metrics.uptimeMinutes', { m })
}

// Node card component
function NodeCard({
  node,
  actions,
  canEdit,
  canDelete,
  dragHandle,
  isDragging,
}: {
  node: Node
  actions: NodeActions
  canEdit: boolean
  canDelete: boolean
  dragHandle?: React.ReactNode
  isDragging?: boolean
}) {
  const { t } = useTranslation()
  const { formatBytes, formatSpeed, formatTimeAgo } = useFormatters()
  const isOnline = node.is_connected && !node.is_disabled
  const status = nodeStatus(node)

  const statusVariant = node.is_disabled
    ? 'secondary'
    : node.is_connected
      ? 'success'
      : 'destructive'
  const statusText = node.is_disabled
    ? t('nodes.status.disabled')
    : node.is_connected
      ? t('nodes.status.online')
      : t('nodes.status.offline')

  return (
    <Card className={cn(
      'relative group transition-all duration-300',
      node.is_disabled && 'opacity-60',
      isDragging && 'ring-2 ring-primary-500/60 shadow-[0_0_24px_-4px_rgba(99,102,241,0.45)]',
      isOnline
        ? 'hover:-translate-y-0.5 hover:shadow-[0_0_20px_-6px_rgba(34,197,94,0.2)]'
        : !node.is_disabled && 'hover:shadow-[0_0_20px_-6px_rgba(239,68,68,0.15)]'
    )}>
      {/* Status color bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg transition-all duration-300 group-hover:w-[4px]"
        style={{
          background: isOnline
            ? 'linear-gradient(180deg, #22c55e 0%, rgba(34,197,94,0.3) 100%)'
            : node.is_disabled
              ? 'linear-gradient(180deg, #6b7280 0%, rgba(107,114,128,0.3) 100%)'
              : 'linear-gradient(180deg, #ef4444 0%, rgba(239,68,68,0.3) 100%)',
        }}
      />
      <CardHeader className="pb-0">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {dragHandle}
            <div
              className={cn(
                'relative p-2.5 rounded-lg',
                isOnline
                  ? 'bg-green-500/10'
                  : node.is_disabled
                    ? 'bg-gray-500/10'
                    : 'bg-red-500/10'
              )}
            >
              {isOnline && (
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-green-400 animate-pulse shadow-[0_0_6px_rgba(74,222,128,0.6)]" />
              )}
              {isOnline ? (
                <Activity className="w-6 h-6 text-green-400" />
              ) : (
                <WifiOff
                  className={cn('w-6 h-6', node.is_disabled ? 'text-dark-200' : 'text-red-400')}
                />
              )}
            </div>
            <div>
              <h3 className="font-semibold text-white">
                {countryFlag(node.country_code)} {node.name}
              </h3>
              <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
                <Globe className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{node.address}:{node.port}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <ShaperBadge state={node.shaper_state} />
            <AgentBadge node={node} />

            <Badge variant={statusVariant as 'success' | 'secondary' | 'destructive'}>
              {statusText}
            </Badge>

            <NodeActionsMenu node={node} canEdit={canEdit} canDelete={canDelete} actions={actions} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 md:gap-4 mb-4">
          <div className="text-center p-2 md:p-3 bg-[var(--glass-bg)] rounded-lg">
            <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
              <Users className="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-xs">{t('nodes.stats.online')}</span>
            </div>
            <p className="text-base md:text-lg font-semibold text-white">{node.users_online}</p>
          </div>
          <div className="text-center p-2 md:p-3 bg-[var(--glass-bg)] rounded-lg">
            <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-xs">{t('nodes.stats.today')}</span>
            </div>
            <p className="text-sm md:text-lg font-semibold text-white">
              {formatBytes(node.traffic_today_bytes)}
            </p>
          </div>
          <div className="text-center p-2 md:p-3 bg-[var(--glass-bg)] rounded-lg">
            <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-xs" title={t('nodes.stats.periodHint', { day: node.traffic_reset_day ?? 1 })}>
                {t('nodes.stats.period')}
              </span>
            </div>
            <p className="text-sm md:text-lg font-semibold text-white">
              {formatBytes(node.traffic_total_bytes)}
            </p>
          </div>
        </div>

        {/* Живые метрики машины: панель их присылает, раньше они не показывались */}
        {isOnline && (
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-dark-200 font-mono">
            <span title={t('nodes.metrics.speed')}>
              <span className="text-blue-400">↓{formatSpeed(node.download_speed_bps || 0)}</span>{' '}
              <span className="text-emerald-400">↑{formatSpeed(node.upload_speed_bps || 0)}</span>
            </span>
            {node.cpu_usage != null && <span>CPU {Math.round(node.cpu_usage)}%</span>}
            {node.memory_usage != null && <span>RAM {Math.round(node.memory_usage)}%</span>}
            {node.uptime_seconds != null && (
              <span title={t('nodes.metrics.uptime')}>⏱ {formatUptime(node.uptime_seconds, t)}</span>
            )}
          </div>
        )}

        {node.note && (
          <p className="mb-3 text-xs text-dark-200 italic truncate" title={node.note}>📝 {node.note}</p>
        )}

        {/* Footer info */}
        <Separator className="mb-3" />
        <div className="flex items-center justify-between text-xs text-dark-200">
          <div className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {node.last_status_change
              ? t(`nodes.since.${status}`, { ago: formatTimeAgo(node.last_status_change) })
              : '—'}
          </div>
          {(node.xray_version || node.node_version) && (
            <span className="flex items-center gap-1 text-dark-300" title={t('nodes.metrics.versions')}>
              <Zap className="w-3 h-3 text-yellow-400" />
              {[node.xray_version && `xray ${node.xray_version}`, node.node_version && `node ${node.node_version}`]
                .filter(Boolean)
                .join(' · ')}
            </span>
          )}
        </div>

        {/* Error message */}
        {node.message && !node.is_connected && (
          <div className="mt-3 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
            {node.message}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Loading skeleton
function NodeSkeleton() {
  return (
    <Card className="animate-fade-in">
      <CardHeader className="pb-0">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 bg-[var(--glass-bg)] rounded-lg" />
            <div>
              <div className="h-4 w-32 bg-[var(--glass-bg)] rounded mb-2" />
              <div className="h-3 w-24 bg-[var(--glass-bg)] rounded" />
            </div>
          </div>
          <div className="h-5 w-16 bg-[var(--glass-bg)] rounded" />
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-3 bg-[var(--glass-bg)] rounded-lg">
              <div className="h-3 w-12 bg-[var(--glass-bg)] rounded mx-auto mb-2" />
              <div className="h-5 w-8 bg-[var(--glass-bg)] rounded mx-auto" />
            </div>
          ))}
        </div>
        <div className="h-3 w-20 bg-[var(--glass-bg)] rounded" />
      </CardContent>
    </Card>
  )
}

// ── Sorting presets ─────────────────────────────────────────────

type SortPreset = 'auto' | 'panel' | 'name' | 'address' | 'users' | 'today' | 'total' | 'lastSeen'
  | 'created' | 'xray' | 'agent' | 'custom'

const SORT_PRESETS: SortPreset[] = ['auto', 'panel', 'name', 'address', 'users', 'today', 'total',
  'lastSeen', 'created', 'xray', 'agent', 'custom']

interface SortState {
  preset: SortPreset
  customOrder: string[]
}

const SORT_STORAGE_KEY = 'nodes-sort-state-v1'

const DEFAULT_SORT_STATE: SortState = { preset: 'auto', customOrder: [] }

function loadSortState(): SortState {
  try {
    const raw = localStorage.getItem(SORT_STORAGE_KEY)
    if (!raw) return DEFAULT_SORT_STATE
    const parsed = JSON.parse(raw) as Partial<SortState>
    const preset = SORT_PRESETS.includes(parsed.preset as SortPreset)
      ? (parsed.preset as SortPreset)
      : 'auto'
    const customOrder = Array.isArray(parsed.customOrder)
      ? parsed.customOrder.filter((x): x is string => typeof x === 'string')
      : []
    return { preset, customOrder }
  } catch {
    return DEFAULT_SORT_STATE
  }
}

function saveSortState(state: SortState) {
  try {
    localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* quota or disabled storage — ignore */
  }
}

function autoPriority(n: Node): number {
  if (!n.is_connected && !n.is_disabled) return 0 // offline — top
  if (n.is_disabled) return 1
  return 2
}

// Статус агента для сортировки: подключён → есть токен, но офлайн → нет агента
function agentPriority(n: Node): number {
  if (n.agent_v2_connected) return 0
  if (n.has_agent_token) return 1
  return 2
}

function compareByPreset(preset: SortPreset, a: Node, b: Node): number {
  switch (preset) {
    case 'name':
      return (a.name || '').localeCompare(b.name || '')
    case 'address':
      return (a.address || '').localeCompare(b.address || '', undefined, { numeric: true })
    case 'users':
      return (b.users_online || 0) - (a.users_online || 0)
    case 'today':
      return (b.traffic_today_bytes || 0) - (a.traffic_today_bytes || 0)
    case 'total':
      return (b.traffic_total_bytes || 0) - (a.traffic_total_bytes || 0)
    case 'lastSeen': {
      const at = a.last_status_change ? Date.parse(a.last_status_change) : 0
      const bt = b.last_status_change ? Date.parse(b.last_status_change) : 0
      return bt - at
    }
    case 'created':
      return Date.parse(b.created_at || '') - Date.parse(a.created_at || '')
    case 'xray':
      return (b.xray_version || '').localeCompare(a.xray_version || '', undefined, { numeric: true })
    case 'panel': {
      // Порядок в панели — он же порядок локаций в подписке у клиентов
      const diff = (a.view_position ?? Number.MAX_SAFE_INTEGER) - (b.view_position ?? Number.MAX_SAFE_INTEGER)
      return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '')
    }
    case 'agent': {
      const diff = agentPriority(a) - agentPriority(b)
      return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '')
    }
    case 'auto':
    default: {
      const diff = autoPriority(a) - autoPriority(b)
      return diff !== 0 ? diff : (a.name || '').localeCompare(b.name || '')
    }
  }
}

function applySortPreset(nodes: Node[], state: SortState): Node[] {
  if (state.preset === 'custom') {
    const indexOf = (uuid: string) => {
      const i = state.customOrder.indexOf(uuid)
      return i === -1 ? Number.MAX_SAFE_INTEGER : i
    }
    const sorted = [...nodes].sort((a, b) => {
      const ai = indexOf(a.uuid)
      const bi = indexOf(b.uuid)
      if (ai !== bi) return ai - bi
      // fallback for nodes not in stored order: keep auto order
      return compareByPreset('auto', a, b)
    })
    return sorted
  }
  return [...nodes].sort((a, b) => compareByPreset(state.preset, a, b))
}

// ── Sortable wrapper for NodeCard ───────────────────────────────

function SortableNodeCard({
  node,
  enabled,
  ...props
}: {
  node: Node
  enabled: boolean
  actions: NodeActions
  canEdit: boolean
  canDelete: boolean
}) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: node.uuid,
    disabled: !enabled,
  })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
  }

  const handle = enabled ? (
    <button
      type="button"
      ref={(el) => {
        // attach drag handle ref via attributes — handle is the listener target
        if (el) el.setAttribute('data-drag-handle', '1')
      }}
      className={cn(
        'flex items-center justify-center h-7 w-5 -ml-1 rounded text-dark-300 cursor-grab touch-none',
        'md:opacity-0 md:group-hover:opacity-100 transition-opacity',
        'hover:text-white hover:bg-white/5 active:cursor-grabbing',
      )}
      aria-label={t('nodes.sort.dragHandle', { defaultValue: 'Перетащите для изменения порядка' })}
      title={t('nodes.sort.dragHandle', { defaultValue: 'Перетащите для изменения порядка' })}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="w-4 h-4" />
    </button>
  ) : undefined

  return (
    <div ref={setNodeRef} style={style}>
      <NodeCard
        node={node}
        {...props}
        dragHandle={handle}
        isDragging={isDragging}
      />
    </div>
  )
}

/** embedded — вкладка страницы «Сервера»: заголовок рисует она. */
export default function Nodes({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canCreate = useHasPermission('nodes', 'create')
  const canEdit = useHasPermission('nodes', 'edit')
  const canDelete = useHasPermission('nodes', 'delete')
  const [editingNode, setEditingNode] = useState<Node | null>(null)
  const [editError, setEditError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')
  const [tokenNode, setTokenNode] = useState<Node | null>(null)
  const [ipsNode, setIpsNode] = useState<Node | null>(null)
  const [shaperNode, setShaperNode] = useState<Node | null>(null)
  const [confirmAction, setConfirmAction] = useState<{ type: string; uuid: string } | null>(null)
  const { schedule: scheduleAction } = useDeferredAction()
  const [sortState, setSortStateRaw] = useState<SortState>(() => loadSortState())
  const [viewMode, setViewMode] = useViewMode('nodes')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | NodeStatus>('all')
  const [agentFilter, setAgentFilter] = useState<'all' | AgentStatus>('all')

  const setSortState = (next: SortState | ((prev: SortState) => SortState)) => {
    setSortStateRaw((prev) => {
      const value = typeof next === 'function' ? (next as (p: SortState) => SortState)(prev) : next
      saveSortState(value)
      return value
    })
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // Fetch nodes
  const { data: nodes = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['nodes'],
    queryFn: fetchNodes,
    refetchInterval: 30000, // Fallback polling (WebSocket handles real-time)
  })

  // Mutations
  /** Find node name by UUID for descriptive toasts */
  const getNodeName = (uuid: string) => nodes.find((n) => n.uuid === uuid)?.name || uuid.slice(0, 8)

  const restartNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/restart`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.restarted'), { description: getNodeName(uuid) })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const retryLabel = t('common.retry', { defaultValue: 'Повторить' })
  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.enabled'), { description: getNodeName(uuid) })
    },
    onError: (err, uuid) => toastMutationError(err, t('nodes.toast.error'), () => enableNode.mutate(uuid), retryLabel),
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.disabled'), { description: getNodeName(uuid) })
    },
    onError: (err, uuid) => toastMutationError(err, t('nodes.toast.error'), () => disableNode.mutate(uuid), retryLabel),
  })

  const deleteNode = useMutation({
    mutationFn: (uuid: string) => client.delete(`/nodes/${uuid}`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      toast.success(t('nodes.toast.deleted'), { description: getNodeName(uuid) })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const updateNode = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Record<string, unknown> }) =>
      client.patch(`/nodes/${uuid}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setEditingNode(null)
      setEditError('')
      toast.success(t('nodes.toast.updated'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || t('nodes.toast.saveError'))
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const createNode = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/nodes', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      setShowCreateModal(false)
      setCreateError('')
      toast.success(t('nodes.toast.created'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || t('nodes.toast.createError'))
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  // Диплинк ?node=<uuid> (из «Флота», уведомлений): подвести к карточке и
  // подсветить; параметр после этого снимается, чтобы не залипать
  const [searchParams, setSearchParams] = useSearchParams()
  const focusUuid = searchParams.get('node')
  const [highlightUuid, setHighlightUuid] = useState<string | null>(null)
  useEffect(() => {
    if (!focusUuid || !nodes.some((n) => n.uuid === focusUuid)) return
    setHighlightUuid(focusUuid)
    requestAnimationFrame(() => {
      document.querySelector(`[data-node-uuid="${focusUuid}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
    const timer = setTimeout(() => setHighlightUuid(null), 2500)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('node')
      return next
    }, { replace: true })
    return () => clearTimeout(timer)
  }, [focusUuid, nodes, setSearchParams])

  // Одни и те же действия для всех трёх видов. Ноду берём из свежего списка:
  // строка таблицы может быть копией со старыми полями.
  const pick = (n: NodeRow) => nodes.find((x) => x.uuid === n.uuid) ?? null
  const nodeActions: NodeActions = {
    onRestart: (n) => setConfirmAction({ type: 'restart', uuid: n.uuid }),
    onEdit: (n) => { setEditingNode(pick(n)); setEditError('') },
    onEnable: (n) => enableNode.mutate(n.uuid),
    onDisable: (n) => setConfirmAction({ type: 'disable', uuid: n.uuid }),
    onDelete: (n) => setConfirmAction({ type: 'delete', uuid: n.uuid }),
    onTokenManage: (n) => setTokenNode(pick(n)),
    onFetchIps: (n) => setIpsNode(pick(n)),
    onShaper: (n) => setShaperNode(pick(n)),
  }

  // Apply sort preset (or stored custom order)
  const sortedNodes = applySortPreset(nodes, sortState)
  const sortedIds = sortedNodes.map((n) => n.uuid)

  // Поиск и фильтры: порядок не меняют, только прячут лишнее
  const query = search.trim().toLowerCase()
  const visibleNodes = sortedNodes.filter((n) =>
    (statusFilter === 'all' || nodeStatus(n) === statusFilter) &&
    (agentFilter === 'all' || agentStatus(n) === agentFilter) &&
    (!query || [n.name, n.address, n.note, n.country_code].some((v) => v?.toLowerCase().includes(query))),
  )
  const filtersActive = !!query || statusFilter !== 'all' || agentFilter !== 'all'
  const resetFilters = () => { setSearch(''); setStatusFilter('all'); setAgentFilter('all') }
  const toggleStatusFilter = (s: NodeStatus) => setStatusFilter((prev) => (prev === s ? 'all' : s))

  // Свой порядок из браузера — в панель, где он станет порядком локаций в подписке
  const saveOrderToPanel = useMutation({
    mutationFn: () => client.post('/nodes/reorder', { uuids: sortedIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setSortState({ preset: 'panel', customOrder: [] })
      toast.success(t('nodes.sort.savedToPanel'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = sortedIds.indexOf(String(active.id))
    const newIndex = sortedIds.indexOf(String(over.id))
    if (oldIndex < 0 || newIndex < 0) return
    const reordered = arrayMove(sortedIds, oldIndex, newIndex)
    // Dragging always switches to "custom" preset and fixes the order
    setSortState({ preset: 'custom', customOrder: reordered })
  }

  const resetCustomOrder = () => {
    setSortState({ preset: 'auto', customOrder: [] })
  }

  // Calculate stats
  const totalNodes = nodes.length
  const onlineNodes = nodes.filter((n) => n.is_connected && !n.is_disabled).length
  const offlineNodes = nodes.filter((n) => !n.is_connected && !n.is_disabled).length
  const disabledNodes = nodes.filter((n) => n.is_disabled).length
  const totalUsersOnline = nodes.reduce((sum, n) => sum + n.users_online, 0)
  const agentsConnected = nodes.filter((n) => n.agent_v2_connected).length
  const agentsMissing = nodes.filter((n) => !n.has_agent_token).length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className={embedded ? 'flex justify-end' : 'page-header'}>
        {!embedded && (
          <div>
            <h1 className="page-header-title">{t('nodes.title')}</h1>
            <p className="text-dark-200 mt-1 text-sm md:text-base">{t('nodes.subtitle')}</p>
          </div>
        )}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          {canCreate && (
            <Button
              onClick={() => { setShowCreateModal(true); setCreateError('') }}
            >
              <Plus className="w-4 h-4 mr-2" />
              <span className="hidden sm:inline">{t('nodes.actions.add')}</span>
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', isFetching && 'animate-spin')} />
            <span className="hidden sm:inline">{t('nodes.actions.refresh')}</span>
          </Button>
        </div>
      </div>

      <div className="space-y-6">

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.total')}</p>
            <p className="text-xl md:text-2xl font-bold text-white mt-1">
              {isLoading ? '-' : totalNodes}
            </p>
          </CardContent>
        </Card>
        <Card
          role="button"
          tabIndex={0}
          onClick={() => toggleStatusFilter('online')}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleStatusFilter('online')}
          title={t('nodes.filter.byStatusHint')}
          className={cn(
            'text-center animate-fade-in-up cursor-pointer transition-shadow',
            statusFilter === 'online' && 'ring-2 ring-primary-400/60',
          )}
          style={{ animationDelay: '0.1s' }}
        >
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.online')}</p>
            <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
              {isLoading ? '-' : onlineNodes}
            </p>
          </CardContent>
        </Card>
        <Card
          role="button"
          tabIndex={0}
          onClick={() => toggleStatusFilter('offline')}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleStatusFilter('offline')}
          title={t('nodes.filter.byStatusHint')}
          className={cn(
            'text-center animate-fade-in-up cursor-pointer transition-shadow',
            statusFilter === 'offline' && 'ring-2 ring-primary-400/60',
          )}
          style={{ animationDelay: '0.15s' }}
        >
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.offline')}</p>
            <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">
              {isLoading ? '-' : offlineNodes}
            </p>
          </CardContent>
        </Card>
        <Card
          role="button"
          tabIndex={0}
          onClick={() => toggleStatusFilter('disabled')}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleStatusFilter('disabled')}
          title={t('nodes.filter.byStatusHint')}
          className={cn(
            'text-center animate-fade-in-up cursor-pointer transition-shadow',
            statusFilter === 'disabled' && 'ring-2 ring-primary-400/60',
          )}
          style={{ animationDelay: '0.2s' }}
        >
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.disabled')}</p>
            <p className="text-xl md:text-2xl font-bold text-dark-200 mt-1">
              {isLoading ? '-' : disabledNodes}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center col-span-2 sm:col-span-1 animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.users')}</p>
            <p className="text-xl md:text-2xl font-bold text-primary-400 mt-1">
              {isLoading ? '-' : totalUsersOnline}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center col-span-2 sm:col-span-1 animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.agents')}</p>
            <p className="text-xl md:text-2xl font-bold text-emerald-400 mt-1">
              {isLoading ? '-' : agentsConnected}
            </p>
            {!isLoading && agentsMissing > 0 && (
              <p className="text-[10px] text-amber-400 mt-0.5">
                {t('nodes.stats.agentsMissing', { count: agentsMissing })}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Toolbar: search, filters, sort + view toggle */}
      {!isLoading && nodes.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative w-full sm:w-56">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dark-300 pointer-events-none" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('nodes.filter.search')}
              className="h-8 pl-8 text-xs"
              aria-label={t('nodes.filter.search')}
            />
          </div>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as 'all' | NodeStatus)}>
            <SelectTrigger className="h-8 w-[140px] text-xs" aria-label={t('nodes.table.status')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">{t('nodes.filter.anyStatus')}</SelectItem>
              {(['online', 'offline', 'disabled'] as const).map((s) => (
                <SelectItem key={s} value={s} className="text-xs">{t(`nodes.status.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={agentFilter} onValueChange={(v) => setAgentFilter(v as 'all' | AgentStatus)}>
            <SelectTrigger className="h-8 w-[150px] text-xs" aria-label={t('nodes.table.agent')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">{t('nodes.filter.anyAgent')}</SelectItem>
              {(['connected', 'offline', 'missing'] as const).map((s) => (
                <SelectItem key={s} value={s} className="text-xs">{t(`nodes.agent.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {filtersActive && (
            <Button variant="ghost" size="sm" className="h-8 px-2 text-xs text-dark-200 hover:text-white" onClick={resetFilters}>
              <X className="w-3.5 h-3.5 mr-1" />
              {t('nodes.filter.reset')}
            </Button>
          )}
          {viewMode !== 'table' && (
            <>
              <div className="flex items-center gap-1.5 text-xs text-dark-200">
                <ArrowUpDown className="w-3.5 h-3.5" />
                <span>{t('nodes.sort.label', { defaultValue: 'Сортировка' })}</span>
              </div>
              <Select
                value={sortState.preset}
                onValueChange={(v) =>
                  setSortState((prev) => {
                    const next = v as SortPreset
                    // When user picks "custom" without dragging yet — seed customOrder from current visible order
                    if (next === 'custom' && prev.customOrder.length === 0) {
                      return { preset: 'custom', customOrder: sortedIds }
                    }
                    return { ...prev, preset: next }
                  })
                }
              >
                <SelectTrigger className="h-8 w-[240px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_PRESETS.map((p) => (
                    <SelectItem key={p} value={p} className="text-xs">
                      {t(`nodes.sort.preset.${p}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {sortState.preset === 'custom' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 text-xs text-dark-200 hover:text-white"
                  onClick={resetCustomOrder}
                  title={t('nodes.sort.resetCustom', { defaultValue: 'Сбросить порядок' })}
                >
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                  {t('nodes.sort.resetCustom', { defaultValue: 'Сбросить порядок' })}
                </Button>
              )}
              {sortState.preset === 'custom' && canEdit && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  onClick={() => saveOrderToPanel.mutate()}
                  disabled={saveOrderToPanel.isPending}
                  title={t('nodes.sort.saveToPanelHint')}
                >
                  {saveOrderToPanel.isPending
                    ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                    : <Upload className="w-3.5 h-3.5 mr-1.5" />}
                  {t('nodes.sort.saveToPanel')}
                </Button>
              )}
            </>
          )}
          <ViewToggle mode={viewMode} onChange={setViewMode} className="ml-auto" />
        </div>
      )}

      {/* Nodes list */}
      {!isLoading && viewMode === 'table' && nodes.length > 0 ? (
        <NodesTable
          nodes={visibleNodes}
          canEdit={canEdit}
          canDelete={canDelete}
          {...nodeActions}
        />
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={visibleNodes.map((n) => n.uuid)} strategy={rectSortingStrategy}>
            <div
              className={cn(
                'grid gap-4',
                viewMode === 'compact'
                  ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
                  : 'grid-cols-1 lg:grid-cols-2',
              )}
            >
              {isLoading ? (
                // Loading skeletons
                Array.from({ length: 4 }).map((_, i) => <NodeSkeleton key={i} />)
              ) : visibleNodes.length === 0 ? (
                <div className="col-span-full">
                  <Card className="text-center py-12">
                    <CardContent>
                      <WifiOff className="w-12 h-12 text-dark-300 mx-auto mb-3" />
                      <p className="text-dark-200">
                        {filtersActive ? t('nodes.filter.nothingFound') : t('nodes.status.noNodes')}
                      </p>
                      {filtersActive && (
                        <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={resetFilters}>
                          {t('nodes.filter.reset')}
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                </div>
              ) : (
                visibleNodes.map((node, i) => (
                  <div
                    key={node.uuid}
                    data-node-uuid={node.uuid}
                    className={cn(
                      'animate-fade-in-up rounded-xl transition-shadow duration-500',
                      highlightUuid === node.uuid && 'ring-2 ring-primary-400/70',
                    )}
                    style={{ animationDelay: `${0.05 + i * 0.04}s` }}
                  >
                    {viewMode === 'compact' ? (
                      <NodeCompactCard
                        node={node}
                        canEdit={canEdit}
                        canDelete={canDelete}
                        {...nodeActions}
                      />
                    ) : (
                      <SortableNodeCard
                        node={node}
                        enabled
                        actions={nodeActions}
                        canEdit={canEdit}
                        canDelete={canDelete}
                      />
                    )}
                  </div>
                ))
              )}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Edit modal */}
      {editingNode && (
        <NodeEditModal
          node={editingNode}
          open={!!editingNode}
          onOpenChange={(open) => { if (!open) { setEditingNode(null); setEditError('') } }}
          onSave={(data) => updateNode.mutate({ uuid: editingNode.uuid, data })}
          isPending={updateNode.isPending}
          error={editError}
        />
      )}

      {/* Create modal */}
      <NodeCreateModal
        open={showCreateModal}
        onOpenChange={(open) => { if (!open) { setShowCreateModal(false); setCreateError('') } else { setShowCreateModal(true) } }}
        onSave={(data) => createNode.mutate(data)}
        isPending={createNode.isPending}
        error={createError}
      />

      {/* Agent token modal */}
      {tokenNode && (
        <AgentTokenModal
          node={tokenNode}
          open={!!tokenNode}
          onOpenChange={(open) => { if (!open) setTokenNode(null) }}
        />
      )}

      {/* Confirm dialog */}
      <ConfirmDialog
        open={confirmAction !== null}
        onOpenChange={(open) => { if (!open) setConfirmAction(null) }}
        title={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.title')
          : confirmAction?.type === 'disable' ? t('nodes.disableConfirm.title', 'Disable node?')
          : confirmAction?.type === 'restart' ? t('nodes.restartConfirm.title')
          : ''
        }
        description={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.description')
          : confirmAction?.type === 'disable' ? t('nodes.disableConfirm.description', 'The node will stop accepting connections. You can re-enable it later.')
          : confirmAction?.type === 'restart'
            ? t('nodes.restartConfirm.description', {
                name: getNodeName(confirmAction.uuid),
                count: nodes.find((n) => n.uuid === confirmAction.uuid)?.users_online ?? 0,
              })
          : ''
        }
        confirmLabel={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.confirm')
          : confirmAction?.type === 'disable' ? t('nodes.actions.disable')
          : confirmAction?.type === 'restart' ? t('nodes.actions.restart')
          : t('nodes.actions.confirm')
        }
        variant={confirmAction?.type === 'delete' ? 'destructive' : 'default'}
        onConfirm={() => {
          if (!confirmAction) return
          if (confirmAction.type === 'delete') deleteNode.mutate(confirmAction.uuid)
          if (confirmAction.type === 'restart') restartNode.mutate(confirmAction.uuid)
          if (confirmAction.type === 'disable') {
            const uuid = confirmAction.uuid
            scheduleAction(`node-disable-${uuid}`, {
              message: t('nodes.deferred.disable', { defaultValue: 'Нода будет отключена через 5 сек' }),
              undoLabel: t('common.undo', { defaultValue: 'Отменить' }),
              onCommit: () => disableNode.mutate(uuid),
            })
          }
          setConfirmAction(null)
        }}
      />

      {/* Node Users IPs dialog */}
      {ipsNode && (
        <NodeUsersIpsDialog
          node={ipsNode}
          open={!!ipsNode}
          onClose={() => setIpsNode(null)}
        />
      )}

      {/* Шейпер клиентов ноды */}
      {shaperNode && (
        <NodeShaperDialog
          node={shaperNode}
          open={!!shaperNode}
          onOpenChange={(open) => { if (!open) setShaperNode(null) }}
        />
      )}
      </div>
    </div>
  )
}
