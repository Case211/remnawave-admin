import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw,
  Globe,
  MoreVertical,
  Pencil,
  Trash2,
  Play,
  Square,
  Wifi,
  WifiOff,
  Lock,
  ShieldCheck,
  Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import client from '../api/client'

// Types matching backend HostListItem
interface Host {
  uuid: string
  remark: string
  address: string
  port: number
  is_disabled: boolean
  inbound_uuid: string | null
  sni: string | null
  host: string | null
  path: string | null
  security: string | null
  alpn: string | null
  fingerprint: string | null
}

interface HostListResponse {
  items: Host[]
  total: number
}

// API functions
const fetchHosts = async (): Promise<Host[]> => {
  const { data } = await client.get('/hosts')
  return data.items || data
}

function getSecurityLabel(security: string | null): string {
  if (!security) return '-'
  const labels: Record<string, string> = {
    'tls': 'TLS',
    'reality': 'Reality',
    'none': 'Без шифрования',
    'xtls': 'XTLS',
  }
  return labels[security] || security
}

function getSecurityColor(security: string | null): string {
  if (!security || security === 'none') return 'text-red-400'
  if (security === 'reality') return 'text-green-400'
  if (security === 'tls' || security === 'xtls') return 'text-blue-400'
  return 'text-dark-200'
}

interface HostEditFormData {
  remark: string
  address: string
  port: string
  sni: string
  host: string
  path: string
  security: string
  alpn: string
  fingerprint: string
}

// Suppress unused interface warning — kept for API contract reference
void (undefined as unknown as HostListResponse)

// Host edit modal
function HostEditModal({
  host,
  onClose,
  onSave,
  isPending,
  error,
}: {
  host: Host
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const [form, setForm] = useState<HostEditFormData>({
    remark: host.remark || '',
    address: host.address || '',
    port: String(host.port),
    sni: host.sni || '',
    host: host.host || '',
    path: host.path || '',
    security: host.security || 'none',
    alpn: host.alpn || '',
    fingerprint: host.fingerprint || '',
  })

  useEffect(() => {
    setForm({
      remark: host.remark || '',
      address: host.address || '',
      port: String(host.port),
      sni: host.sni || '',
      host: host.host || '',
      path: host.path || '',
      security: host.security || 'none',
      alpn: host.alpn || '',
      fingerprint: host.fingerprint || '',
    })
  }, [host])

  const handleSubmit = () => {
    const updateData: Record<string, unknown> = {}
    if (form.remark !== (host.remark || '')) updateData.remark = form.remark
    if (form.address !== (host.address || '')) updateData.address = form.address
    const newPort = parseInt(form.port, 10)
    if (!isNaN(newPort) && newPort !== host.port) updateData.port = newPort
    if (form.sni !== (host.sni || '')) updateData.sni = form.sni || null
    if (form.host !== (host.host || '')) updateData.host = form.host || null
    if (form.path !== (host.path || '')) updateData.path = form.path || null
    if (form.security !== (host.security || 'none')) updateData.security = form.security
    if (form.alpn !== (host.alpn || '')) updateData.alpn = form.alpn || null
    if (form.fingerprint !== (host.fingerprint || '')) updateData.fingerprint = form.fingerprint || null

    if (Object.keys(updateData).length === 0) {
      onClose()
      return
    }
    onSave(updateData)
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Редактирование хоста</DialogTitle>
          <DialogDescription>Измените параметры хоста и нажмите сохранить</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Название</Label>
            <Input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              placeholder="Название хоста"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Адрес</Label>
              <Input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="IP или домен"
              />
            </div>
            <div className="space-y-2">
              <Label>Порт</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                placeholder="Порт"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Безопасность</Label>
            <Select value={form.security} onValueChange={(value) => setForm({ ...form, security: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Без шифрования</SelectItem>
                <SelectItem value="tls">TLS</SelectItem>
                <SelectItem value="reality">Reality</SelectItem>
                <SelectItem value="xtls">XTLS</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>SNI</Label>
            <Input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              placeholder="Server Name Indication"
            />
          </div>

          <div className="space-y-2">
            <Label>Host</Label>
            <Input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              placeholder="Host header"
            />
          </div>

          <div className="space-y-2">
            <Label>Path</Label>
            <Input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="font-mono text-sm"
              placeholder="/path"
            />
          </div>

          <div className="space-y-2">
            <Label>ALPN</Label>
            <Input
              type="text"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              placeholder="h2,http/1.1"
            />
          </div>

          <div className="space-y-2">
            <Label>Fingerprint</Label>
            <Input
              type="text"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              placeholder="chrome, firefox, safari..."
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isPending}
          >
            Отмена
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
          >
            {isPending ? 'Сохранение...' : 'Сохранить'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Host create modal
function HostCreateModal({
  onClose,
  onSave,
  isPending,
  error,
}: {
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const [form, setForm] = useState<HostEditFormData>({
    remark: '',
    address: '',
    port: '443',
    sni: '',
    host: '',
    path: '',
    security: 'tls',
    alpn: '',
    fingerprint: '',
  })

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {
      remark: form.remark.trim(),
      address: form.address.trim(),
    }
    const port = parseInt(form.port, 10)
    if (!isNaN(port)) createData.port = port
    createData.security = form.security
    if (form.sni.trim()) createData.sni = form.sni.trim()
    if (form.host.trim()) createData.host = form.host.trim()
    if (form.path.trim()) createData.path = form.path.trim()
    if (form.alpn.trim()) createData.alpn = form.alpn.trim()
    if (form.fingerprint.trim()) createData.fingerprint = form.fingerprint.trim()
    onSave(createData)
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Добавление хоста</DialogTitle>
          <DialogDescription>Заполните параметры нового хоста</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Название</Label>
            <Input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              placeholder="Название хоста"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Адрес</Label>
              <Input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="IP или домен"
              />
            </div>
            <div className="space-y-2">
              <Label>Порт</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                placeholder="Порт"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Безопасность</Label>
            <Select value={form.security} onValueChange={(value) => setForm({ ...form, security: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Без шифрования</SelectItem>
                <SelectItem value="tls">TLS</SelectItem>
                <SelectItem value="reality">Reality</SelectItem>
                <SelectItem value="xtls">XTLS</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>SNI</Label>
            <Input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              placeholder="Server Name Indication"
            />
          </div>

          <div className="space-y-2">
            <Label>Host</Label>
            <Input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              placeholder="Host header"
            />
          </div>

          <div className="space-y-2">
            <Label>Path</Label>
            <Input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="font-mono text-sm"
              placeholder="/path"
            />
          </div>

          <div className="space-y-2">
            <Label>ALPN</Label>
            <Input
              type="text"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              placeholder="h2,http/1.1"
            />
          </div>

          <div className="space-y-2">
            <Label>Fingerprint</Label>
            <Input
              type="text"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              placeholder="chrome, firefox, safari..."
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isPending}
          >
            Отмена
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
          >
            {isPending ? 'Создание...' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Host card component
function HostCard({
  host,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
}: {
  host: Host
  onEdit: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  return (
    <Card className={cn('relative', host.is_disabled && 'opacity-60')}>
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn(
              'p-2.5 rounded-lg',
              host.is_disabled ? 'bg-gray-500/10' : 'bg-green-500/10'
            )}>
              {host.is_disabled ? (
                <WifiOff className="w-5 h-5 text-dark-200" />
              ) : (
                <Wifi className="w-5 h-5 text-green-400" />
              )}
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-white truncate">{host.remark || 'Без имени'}</h3>
              <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
                <Globe className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{host.address}:{host.port}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={host.is_disabled ? 'secondary' : 'success'}>
              {host.is_disabled ? 'Откл.' : 'Активен'}
            </Badge>

            {/* Actions menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onEdit}>
                  <Pencil className="w-4 h-4 mr-2" />
                  Редактировать
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {host.is_disabled ? (
                  <DropdownMenuItem
                    onSelect={onEnable}
                    className="text-green-400 focus:text-green-400"
                  >
                    <Play className="w-4 h-4 mr-2" />
                    Включить
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem
                    onSelect={onDisable}
                    className="text-yellow-400 focus:text-yellow-400"
                  >
                    <Square className="w-4 h-4 mr-2" />
                    Отключить
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem
                  onSelect={() => { if (confirm('Удалить хост?')) onDelete() }}
                  className="text-red-400 focus:text-red-400"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Удалить
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">Безопасность</span>
            <p className={cn('font-medium', getSecurityColor(host.security))}>
              {host.security === 'reality' && <ShieldCheck className="w-3.5 h-3.5 inline mr-1" />}
              {host.security === 'tls' && <Lock className="w-3.5 h-3.5 inline mr-1" />}
              {getSecurityLabel(host.security)}
            </p>
          </div>
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">SNI</span>
            <p className="font-medium text-white truncate">{host.sni || '-'}</p>
          </div>
          {host.host && (
            <div className="bg-dark-800/50 rounded-lg p-2">
              <span className="text-dark-200 text-xs">Host</span>
              <p className="font-medium text-white truncate">{host.host}</p>
            </div>
          )}
          {host.path && (
            <div className="bg-dark-800/50 rounded-lg p-2">
              <span className="text-dark-200 text-xs">Path</span>
              <p className="font-medium text-white truncate font-mono text-xs">{host.path}</p>
            </div>
          )}
          {host.alpn && (
            <div className="bg-dark-800/50 rounded-lg p-2">
              <span className="text-dark-200 text-xs">ALPN</span>
              <p className="font-medium text-white truncate">{host.alpn}</p>
            </div>
          )}
          {host.fingerprint && (
            <div className="bg-dark-800/50 rounded-lg p-2">
              <span className="text-dark-200 text-xs">Fingerprint</span>
              <p className="font-medium text-white truncate">{host.fingerprint}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Loading skeleton
function HostSkeleton() {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <Skeleton className="w-10 h-10 rounded-lg" />
            <div>
              <Skeleton className="h-4 w-32 rounded mb-2" />
              <Skeleton className="h-3 w-24 rounded" />
            </div>
          </div>
          <Skeleton className="h-5 w-16 rounded" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Skeleton className="h-12 rounded-lg" />
          <Skeleton className="h-12 rounded-lg" />
        </div>
      </CardContent>
    </Card>
  )
}

export default function Hosts() {
  const queryClient = useQueryClient()
  const [editingHost, setEditingHost] = useState<Host | null>(null)
  const [editError, setEditError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')

  // Fetch hosts
  const { data: hosts = [], isLoading, refetch } = useQuery({
    queryKey: ['hosts'],
    queryFn: fetchHosts,
    refetchInterval: 30000,
  })

  // Mutations
  const enableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/enable`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  const disableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/disable`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  const deleteHost = useMutation({
    mutationFn: (uuid: string) => client.delete(`/hosts/${uuid}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  const updateHost = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Record<string, unknown> }) =>
      client.patch(`/hosts/${uuid}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      setEditingHost(null)
      setEditError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || 'Ошибка сохранения')
    },
  })

  const createHost = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/hosts', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      setShowCreateModal(false)
      setCreateError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
  })

  // Stats
  const totalHosts = hosts.length
  const activeHosts = hosts.filter((h) => !h.is_disabled).length
  const disabledHosts = hosts.filter((h) => h.is_disabled).length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Хосты</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Управление хостами подключений</p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            onClick={() => { setShowCreateModal(true); setCreateError('') }}
            className="gap-2"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">Добавить</span>
          </Button>
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading}
            className="gap-2"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            <span className="hidden sm:inline">Обновить</span>
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">Всего</p>
            <p className="text-xl md:text-2xl font-bold text-white mt-1">
              {isLoading ? '-' : totalHosts}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">Активные</p>
            <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
              {isLoading ? '-' : activeHosts}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">Отключены</p>
            <p className="text-xl md:text-2xl font-bold text-dark-200 mt-1">
              {isLoading ? '-' : disabledHosts}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Hosts grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <HostSkeleton key={i} />)
        ) : hosts.length === 0 ? (
          <Card className="col-span-full">
            <CardContent className="py-12 text-center">
              <Globe className="w-12 h-12 text-dark-300 mx-auto mb-3" />
              <p className="text-dark-200">Нет хостов</p>
            </CardContent>
          </Card>
        ) : (
          hosts.map((host, i) => (
            <div key={host.uuid} className="animate-fade-in-up" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
              <HostCard
                host={host}
                onEdit={() => { setEditingHost(host); setEditError('') }}
                onEnable={() => enableHost.mutate(host.uuid)}
                onDisable={() => disableHost.mutate(host.uuid)}
                onDelete={() => deleteHost.mutate(host.uuid)}
              />
            </div>
          ))
        )}
      </div>

      {/* Edit modal */}
      {editingHost && (
        <HostEditModal
          host={editingHost}
          onClose={() => { setEditingHost(null); setEditError('') }}
          onSave={(data) => updateHost.mutate({ uuid: editingHost.uuid, data })}
          isPending={updateHost.isPending}
          error={editError}
        />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <HostCreateModal
          onClose={() => { setShowCreateModal(false); setCreateError('') }}
          onSave={(data) => createHost.mutate(data)}
          isPending={createHost.isPending}
          error={createError}
        />
      )}
    </div>
  )
}
