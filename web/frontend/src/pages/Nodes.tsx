import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import { useHasPermission } from '@/components/PermissionGate'
import {
  RefreshCw,
  Activity,
  WifiOff,
  Globe,
  Users,
  BarChart3,
  Clock,
  MoreVertical,
  Pencil,
  Trash2,
  Play,
  Square,
  Plus,
  Key,
  Copy,
  ShieldCheck,
  AlertTriangle,
  Zap,
  Terminal,
  Scan,
  Loader2,
} from 'lucide-react'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import Billing from './Billing'

// Types
interface Node {
  uuid: string
  name: string
  address: string
  port: number
  is_connected: boolean
  is_disabled: boolean
  is_xray_running: boolean
  users_online: number
  xray_version: string | null
  message: string | null
  traffic_total_bytes: number
  traffic_today_bytes: number
  created_at: string
  last_seen_at: string | null
}

interface NodeEditFormData {
  name: string
  address: string
  port: string
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
  const [form, setForm] = useState<NodeEditFormData>({
    name: node.name,
    address: node.address,
    port: String(node.port),
  })

  useEffect(() => {
    setForm({
      name: node.name,
      address: node.address,
      port: String(node.port),
    })
  }, [node])

  const handleSubmit = () => {
    const updateData: Record<string, unknown> = {}
    if (form.name !== node.name) updateData.name = form.name
    if (form.address !== node.address) updateData.address = form.address
    const newPort = parseInt(form.port, 10)
    if (!isNaN(newPort) && newPort !== node.port) updateData.port = newPort
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
            disabled={isPending || !form.name.trim() || !form.address.trim() || !form.port}
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
    port: '62050',
  })
  const [selectedProfileUuid, setSelectedProfileUuid] = useState('')
  const [selectedInbounds, setSelectedInbounds] = useState<string[]>([])

  // Fetch config profiles
  const { data: configProfiles = [] } = useQuery({
    queryKey: ['config-profiles'],
    queryFn: resourcesApi.getConfigProfiles,
    enabled: open,
  })

  // Fetch inbounds for selected profile
  const { data: profileInbounds = [] } = useQuery<Inbound[]>({
    queryKey: ['config-profile-inbounds', selectedProfileUuid],
    queryFn: async () => {
      const { data } = await client.get(`/config-profiles/${selectedProfileUuid}/inbounds`)
      return Array.isArray(data) ? data : []
    },
    enabled: open && !!selectedProfileUuid,
  })

  // Reset form when modal closes
  useEffect(() => {
    if (!open) {
      setForm({ name: '', address: '', port: '62050' })
      setSelectedProfileUuid('')
      setSelectedInbounds([])
    }
  }, [open])

  // Reset inbounds when profile changes
  useEffect(() => {
    setSelectedInbounds([])
  }, [selectedProfileUuid])

  const toggleInbound = (uuid: string) => {
    setSelectedInbounds((prev) =>
      prev.includes(uuid) ? prev.filter((id) => id !== uuid) : [...prev, uuid]
    )
  }

  const selectAllInbounds = () => {
    if (selectedInbounds.length === profileInbounds.length) {
      setSelectedInbounds([])
    } else {
      setSelectedInbounds(profileInbounds.map((ib) => ib.uuid))
    }
  }

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

  const isValid = form.name.trim() && form.address.trim() && form.port && selectedProfileUuid && selectedInbounds.length > 0

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

          {/* Config Profile */}
          <div className="space-y-2">
            <Label>{t('nodes.createNode.configProfile')}</Label>
            <Select value={selectedProfileUuid} onValueChange={setSelectedProfileUuid}>
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

          {/* Inbounds */}
          {selectedProfileUuid && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{t('nodes.createNode.inbounds')}</Label>
                {profileInbounds.length > 0 && (
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline"
                    onClick={selectAllInbounds}
                  >
                    {selectedInbounds.length === profileInbounds.length
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
                      <Checkbox
                        checked={selectedInbounds.includes(ib.uuid)}
                        onCheckedChange={() => toggleInbound(ib.uuid)}
                      />
                      <span className="text-sm">{ib.tag}</span>
                      <span className="text-xs text-dark-300 ml-auto">{ib.type}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
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
                <Terminal className="w-4 h-4 mr-2" />
                {installMutation.isPending ? '...' : t('nodes.agentToken.installAgent')}
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
  userId: string
  ips: ({ ip: string; lastSeen?: string } | string)[]
}

function NodeUsersIpsDialog({ node, open, onClose }: { node: Node; open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
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
                    <p className="text-xs font-mono text-primary-300 mb-1.5 truncate">{u.userId}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {u.ips.map((ip, i) => {
                        const addr = typeof ip === 'string' ? ip : ip.ip
                        return (
                          <Badge key={i} variant="secondary" className="text-[10px] font-mono">
                            {addr}
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

// Node card component
function NodeCard({
  node,
  onRestart,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
  onTokenManage,
  onFetchIps,
  canEdit,
  canDelete,
}: {
  node: Node
  onRestart: () => void
  onEdit: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
  onTokenManage: () => void
  onFetchIps: () => void
  canEdit: boolean
  canDelete: boolean
}) {
  const { t } = useTranslation()
  const { formatBytes, formatTimeAgo } = useFormatters()
  const isOnline = node.is_connected && !node.is_disabled

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
              <h3 className="font-semibold text-white">{node.name}</h3>
              <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
                <Globe className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{node.address}:{node.port}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={statusVariant as 'success' | 'secondary' | 'destructive'}>
              {statusText}
            </Badge>

            {/* Actions menu */}
            {(canEdit || canDelete) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canEdit && (
                    <DropdownMenuItem onClick={onRestart}>
                      <RefreshCw className="w-4 h-4 mr-2" />
                      {t('nodes.actions.restart')}
                    </DropdownMenuItem>
                  )}
                  {canEdit && (
                    <DropdownMenuItem onClick={onEdit}>
                      <Pencil className="w-4 h-4 mr-2" />
                      {t('nodes.actions.edit')}
                    </DropdownMenuItem>
                  )}
                  {canEdit && (
                    <DropdownMenuItem onClick={onTokenManage}>
                      <Key className="w-4 h-4 mr-2" />
                      {t('nodes.actions.agentToken')}
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={onFetchIps}>
                    <Scan className="w-4 h-4 mr-2" />
                    {t('nodes.actions.fetchUsersIps')}
                  </DropdownMenuItem>
                  {(canEdit || canDelete) && <DropdownMenuSeparator />}
                  {canEdit && (
                    node.is_disabled ? (
                      <DropdownMenuItem onClick={onEnable} className="text-green-400 focus:text-green-400">
                        <Play className="w-4 h-4 mr-2" />
                        {t('nodes.actions.enable')}
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onClick={onDisable} className="text-yellow-400 focus:text-yellow-400">
                        <Square className="w-4 h-4 mr-2" />
                        {t('nodes.actions.disable')}
                      </DropdownMenuItem>
                    )
                  )}
                  {canDelete && (
                    <DropdownMenuItem
                      onClick={onDelete}
                      className="text-red-400 focus:text-red-400"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      {t('nodes.actions.delete')}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
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
              <span className="text-[10px] md:text-xs">{t('nodes.stats.total')}</span>
            </div>
            <p className="text-sm md:text-lg font-semibold text-white">
              {formatBytes(node.traffic_total_bytes)}
            </p>
          </div>
        </div>

        {/* Footer info */}
        <Separator className="mb-3" />
        <div className="flex items-center justify-between text-xs text-dark-200">
          <div className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {node.last_seen_at ? formatTimeAgo(node.last_seen_at) : t('nodes.status.never')}
          </div>
          {node.xray_version && (
            <span className="flex items-center gap-1 text-dark-300">
              <Zap className="w-3 h-3 text-yellow-400" />
              {node.xray_version}
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

export default function Nodes() {
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
  const [confirmAction, setConfirmAction] = useState<{ type: string; uuid: string } | null>(null)

  // Fetch nodes
  const { data: nodes = [], isLoading, refetch } = useQuery({
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

  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.enabled'), { description: getNodeName(uuid) })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.disabled'), { description: getNodeName(uuid) })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  const deleteNode = useMutation({
    mutationFn: (uuid: string) => client.delete(`/nodes/${uuid}`),
    onSuccess: (_data, uuid) => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
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
      setShowCreateModal(false)
      setCreateError('')
      toast.success(t('nodes.toast.created'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || t('nodes.toast.createError'))
      toast.error(t('nodes.toast.error'), { description: err.response?.data?.detail || err.message })
    },
  })

  // Sort: offline (problems) first, then disabled, then online
  const sortedNodes = [...nodes].sort((a, b) => {
    const priority = (n: Node) => {
      if (!n.is_connected && !n.is_disabled) return 0 // Offline — top priority
      if (n.is_disabled) return 1
      return 2 // Online — last
    }
    const diff = priority(a) - priority(b)
    if (diff !== 0) return diff
    return (a.name || '').localeCompare(b.name || '')
  })

  // Calculate stats
  const totalNodes = nodes.length
  const onlineNodes = nodes.filter((n) => n.is_connected && !n.is_disabled).length
  const offlineNodes = nodes.filter((n) => !n.is_connected && !n.is_disabled).length
  const disabledNodes = nodes.filter((n) => n.is_disabled).length
  const totalUsersOnline = nodes.reduce((sum, n) => sum + n.users_online, 0)

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('nodes.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('nodes.subtitle')}</p>
        </div>
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
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', isLoading && 'animate-spin')} />
            <span className="hidden sm:inline">{t('nodes.actions.refresh')}</span>
          </Button>
        </div>
      </div>

      <Tabs defaultValue="nodes">
        <TabsList>
          <TabsTrigger value="nodes">{t('nodes.tabs.nodes')}</TabsTrigger>
          <TabsTrigger value="billing">{t('nodes.tabs.billing')}</TabsTrigger>
        </TabsList>

        <TabsContent value="billing" className="mt-4">
          <Billing embedded />
        </TabsContent>

        <TabsContent value="nodes" className="space-y-6 mt-4">

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.total')}</p>
            <p className="text-xl md:text-2xl font-bold text-white mt-1">
              {isLoading ? '-' : totalNodes}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.online')}</p>
            <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
              {isLoading ? '-' : onlineNodes}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4 md:p-6">
            <p className="text-xs md:text-sm text-dark-200">{t('nodes.stats.offline')}</p>
            <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">
              {isLoading ? '-' : offlineNodes}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
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
      </div>

      {/* Nodes grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          // Loading skeletons
          Array.from({ length: 4 }).map((_, i) => <NodeSkeleton key={i} />)
        ) : sortedNodes.length === 0 ? (
          <div className="col-span-full">
            <Card className="text-center py-12">
              <CardContent>
                <WifiOff className="w-12 h-12 text-dark-300 mx-auto mb-3" />
                <p className="text-dark-200">{t('nodes.status.noNodes')}</p>
              </CardContent>
            </Card>
          </div>
        ) : (
          sortedNodes.map((node, i) => (
            <div key={node.uuid} className="animate-fade-in-up" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
              <NodeCard
                node={node}
                onRestart={() => restartNode.mutate(node.uuid)}
                onEdit={() => { setEditingNode(node); setEditError('') }}
                onEnable={() => enableNode.mutate(node.uuid)}
                onDisable={() => setConfirmAction({ type: 'disable', uuid: node.uuid })}
                onDelete={() => setConfirmAction({ type: 'delete', uuid: node.uuid })}
                onTokenManage={() => setTokenNode(node)}
                onFetchIps={() => setIpsNode(node)}
                canEdit={canEdit}
                canDelete={canDelete}
              />
            </div>
          ))
        )}
      </div>

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
          : ''
        }
        description={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.description')
          : confirmAction?.type === 'disable' ? t('nodes.disableConfirm.description', 'The node will stop accepting connections. You can re-enable it later.')
          : ''
        }
        confirmLabel={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.confirm')
          : confirmAction?.type === 'disable' ? t('nodes.actions.disable')
          : t('nodes.actions.confirm')
        }
        variant={confirmAction?.type === 'delete' ? 'destructive' : 'default'}
        onConfirm={() => {
          if (!confirmAction) return
          if (confirmAction.type === 'delete') deleteNode.mutate(confirmAction.uuid)
          if (confirmAction.type === 'disable') disableNode.mutate(confirmAction.uuid)
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
        </TabsContent>
      </Tabs>
    </div>
  )
}
