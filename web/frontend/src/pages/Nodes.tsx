import { useState, useEffect } from 'react'
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
} from 'lucide-react'
import client from '../api/client'
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
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ConfirmDialog'

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
  const { data } = await client.get('/nodes')
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

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {
      name: form.name.trim(),
      address: form.address.trim(),
    }
    const port = parseInt(form.port, 10)
    if (!isNaN(port)) createData.port = port
    onSave(createData)
  }

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
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
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
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
    },
  })

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const envConfig = generatedToken
    ? `AGENT_NODE_UUID=${node.uuid}\nAGENT_AUTH_TOKEN=${generatedToken}\nAGENT_COLLECTOR_URL=https://your-admin-bot.com`
    : null

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
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
            <div className="p-3 bg-dark-800/50 rounded-lg">
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
                  <pre className="text-xs text-primary-300 font-mono bg-dark-900/50 p-2.5 rounded overflow-x-auto whitespace-pre-wrap break-all">{generatedToken}</pre>
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
                      <pre className="text-[11px] text-dark-200 font-mono bg-dark-900/50 p-2.5 rounded overflow-x-auto whitespace-pre-wrap break-all">{envConfig}</pre>
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

            {/* Actions */}
            <div className="flex items-center gap-2 pt-2">
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

// Node card component
function NodeCard({
  node,
  onRestart,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
  onTokenManage,
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
    <Card className={cn('relative', node.is_disabled && 'opacity-60')}>
      <CardHeader className="pb-0">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'p-2.5 rounded-lg',
                isOnline
                  ? 'bg-green-500/10'
                  : node.is_disabled
                    ? 'bg-gray-500/10'
                    : 'bg-red-500/10'
              )}
            >
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
        <div className="grid grid-cols-3 gap-2 md:gap-4 mb-4">
          <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
            <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
              <Users className="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-xs">{t('nodes.stats.online')}</span>
            </div>
            <p className="text-base md:text-lg font-semibold text-white">{node.users_online}</p>
          </div>
          <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
            <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="text-[10px] md:text-xs">{t('nodes.stats.today')}</span>
            </div>
            <p className="text-sm md:text-lg font-semibold text-white">
              {formatBytes(node.traffic_today_bytes)}
            </p>
          </div>
          <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
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
            <div className="w-11 h-11 bg-dark-700 rounded-lg" />
            <div>
              <div className="h-4 w-32 bg-dark-700 rounded mb-2" />
              <div className="h-3 w-24 bg-dark-700 rounded" />
            </div>
          </div>
          <div className="h-5 w-16 bg-dark-700 rounded" />
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="grid grid-cols-3 gap-4 mb-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-3 bg-dark-800/50 rounded-lg">
              <div className="h-3 w-12 bg-dark-700 rounded mx-auto mb-2" />
              <div className="h-5 w-8 bg-dark-700 rounded mx-auto" />
            </div>
          ))}
        </div>
        <div className="h-3 w-20 bg-dark-700 rounded" />
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
  const [confirmAction, setConfirmAction] = useState<{ type: string; uuid: string } | null>(null)

  // Fetch nodes
  const { data: nodes = [], isLoading, refetch } = useQuery({
    queryKey: ['nodes'],
    queryFn: fetchNodes,
    refetchInterval: 30000, // Fallback polling (WebSocket handles real-time)
  })

  // Mutations
  const restartNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/restart`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.restarted'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
    },
  })

  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.enabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
    },
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.disabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
    },
  })

  const deleteNode = useMutation({
    mutationFn: (uuid: string) => client.delete(`/nodes/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      toast.success(t('nodes.toast.deleted'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
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
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
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
      toast.error(t('nodes.toast.error') + ': ' + (err.response?.data?.detail || err.message))
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
                onDisable={() => disableNode.mutate(node.uuid)}
                onDelete={() => setConfirmAction({ type: 'delete', uuid: node.uuid })}
                onTokenManage={() => setTokenNode(node)}
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
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.title') : ''
        }
        description={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.description') : ''
        }
        confirmLabel={
          confirmAction?.type === 'delete' ? t('nodes.deleteConfirm.confirm') : t('nodes.actions.confirm')
        }
        variant={confirmAction?.type === 'delete' ? 'destructive' : 'default'}
        onConfirm={() => {
          if (!confirmAction) return
          if (confirmAction.type === 'delete') deleteNode.mutate(confirmAction.uuid)
          setConfirmAction(null)
        }}
      />
    </div>
  )
}
