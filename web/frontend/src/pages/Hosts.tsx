import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
// useFormatters available for locale-aware formatting
import { useHasPermission } from '@/components/PermissionGate'
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
} from '@/components/brand/icons'
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
import { ConfirmDialog } from '@/components/ConfirmDialog'
import client from '../api/client'
import { ViewToggle } from '@/components/ViewToggle'
import { useViewMode } from '@/lib/useViewMode'
import { HostsTable } from '@/components/hosts/HostsTable'
import { HostCompactCard } from '@/components/hosts/HostCompactCard'

// Types matching backend HostListItem
interface Host {
  uuid: string
  remark: string
  address: string
  port: number
  is_disabled: boolean
  is_hidden: boolean
  inbound_uuid: string | null
  inbound: { uuid: string; tag: string; type: string } | null
  tag: string | null
  server_description: string | null
  security_layer: string | null
  view_position: number | null
  sni: string | null
  host: string | null
  path: string | null
  security: string | null
  alpn: string | null
  fingerprint: string | null
  tags: string[] | null
  mihomo_ip_version: string | null
  pinned_peer_cert_sha256: string | null
  verify_peer_cert_by_name: boolean
  shuffle_host: boolean
  mihomo_x25519: string | null
  nodes: { uuid: string; name: string }[] | null
  excluded_internal_squads: { uuid: string; name: string }[] | null
  allowed_actions?: string[] | null
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
  tag: string
  mihomo_ip_version: string
  pinned_peer_cert_sha256: string
  verify_peer_cert_by_name: boolean
  server_description: string
  is_hidden: boolean
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
  const { t } = useTranslation()
  const [form, setForm] = useState<HostEditFormData>({
    remark: host.remark || '',
    address: host.address || '',
    port: String(host.port),
    sni: host.sni || '',
    host: host.host || '',
    path: host.path || '',
    security: host.security_layer || host.security || 'none',
    alpn: host.alpn || '',
    fingerprint: host.fingerprint || '',
    tag: (host.tags || []).join(', '),
    mihomo_ip_version: host.mihomo_ip_version || '',
    pinned_peer_cert_sha256: host.pinned_peer_cert_sha256 || '',
    verify_peer_cert_by_name: host.verify_peer_cert_by_name || false,
    server_description: host.server_description || '',
    is_hidden: host.is_hidden || false,
  })

  useEffect(() => {
    setForm({
      remark: host.remark || '',
      address: host.address || '',
      port: String(host.port),
      sni: host.sni || '',
      host: host.host || '',
      path: host.path || '',
      security: host.security_layer || host.security || 'none',
      alpn: host.alpn || '',
      fingerprint: host.fingerprint || '',
      tag: (host.tags || []).join(', '),
      mihomo_ip_version: host.mihomo_ip_version || '',
      pinned_peer_cert_sha256: host.pinned_peer_cert_sha256 || '',
      verify_peer_cert_by_name: host.verify_peer_cert_by_name || false,
      server_description: host.server_description || '',
      is_hidden: host.is_hidden || false,
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
    const curSecurity = host.security_layer || host.security || 'none'
    if (form.security !== curSecurity) updateData.security_layer = form.security
    if (form.alpn !== (host.alpn || '')) updateData.alpn = form.alpn || null
    if (form.fingerprint !== (host.fingerprint || '')) updateData.fingerprint = form.fingerprint || null
    const curTags = (host.tags || []).join(', ')
    if (form.tag !== curTags) updateData.tags = form.tag ? form.tag.split(',').map((s) => s.trim()).filter(Boolean) : null
    if (form.mihomo_ip_version !== (host.mihomo_ip_version || '')) updateData.mihomo_ip_version = form.mihomo_ip_version || null
    if (form.pinned_peer_cert_sha256 !== (host.pinned_peer_cert_sha256 || '')) updateData.pinned_peer_cert_sha256 = form.pinned_peer_cert_sha256 || null
    if (form.verify_peer_cert_by_name !== (host.verify_peer_cert_by_name || false)) updateData.verify_peer_cert_by_name = form.verify_peer_cert_by_name
    if (form.server_description !== (host.server_description || '')) updateData.server_description = form.server_description || null
    if (form.is_hidden !== (host.is_hidden || false)) updateData.is_hidden = form.is_hidden

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
          <DialogTitle>{t('hosts.editHost.title')}</DialogTitle>
          <DialogDescription>{t('hosts.editHost.description')}</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('hosts.editHost.name')}</Label>
            <Input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              placeholder={t('hosts.editHost.namePlaceholder')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>{t('hosts.editHost.address')}</Label>
              <Input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder={t('hosts.editHost.addressPlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('hosts.editHost.port')}</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                placeholder={t('hosts.editHost.port')}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.security.label')}</Label>
            <Select value={form.security} onValueChange={(value) => setForm({ ...form, security: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('hosts.security.none')}</SelectItem>
                <SelectItem value="tls">{t('hosts.security.tls')}</SelectItem>
                <SelectItem value="reality">{t('hosts.security.reality')}</SelectItem>
                <SelectItem value="xtls">{t('hosts.security.xtls')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.sni')}</Label>
            <Input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              placeholder={t('hosts.form.sniPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.host')}</Label>
            <Input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              placeholder={t('hosts.form.hostPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.path')}</Label>
            <Input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="font-mono text-sm"
              placeholder={t('hosts.form.pathPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.alpn')}</Label>
            <Input
              type="text"
              list="host-alpn-options"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              placeholder={t('hosts.form.alpnPlaceholder')}
            />
            <datalist id="host-alpn-options">
              <option value="h3,h2,http/1.1" />
              <option value="h3,h2" />
              <option value="h2,http/1.1" />
              <option value="h2" />
              <option value="h3" />
              <option value="http/1.1" />
            </datalist>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.fingerprint')}</Label>
            <Input
              type="text"
              list="host-fp-options"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              placeholder={t('hosts.form.fingerprintPlaceholder')}
            />
            <datalist id="host-fp-options">
              <option value="chrome" />
              <option value="firefox" />
              <option value="safari" />
              <option value="ios" />
              <option value="android" />
              <option value="edge" />
              <option value="randomized" />
              <option value="random" />
            </datalist>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.mihomoIpVersion')}</Label>
            <select
              value={form.mihomo_ip_version}
              onChange={(e) => setForm({ ...form, mihomo_ip_version: e.target.value })}
              className="flex h-9 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">{t('hosts.form.mihomoIpVersionDefault')}</option>
              <option value="dual">dual</option>
              <option value="ipv4">ipv4</option>
              <option value="ipv6">ipv6</option>
              <option value="ipv4-prefer">ipv4-prefer</option>
              <option value="ipv6-prefer">ipv6-prefer</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.pinnedPeerCert')}</Label>
            <Input
              type="text"
              value={form.pinned_peer_cert_sha256}
              onChange={(e) => setForm({ ...form, pinned_peer_cert_sha256: e.target.value })}
              placeholder={t('hosts.form.pinnedPeerCertPlaceholder')}
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.verify_peer_cert_by_name}
              onChange={(e) => setForm({ ...form, verify_peer_cert_by_name: e.target.checked })}
              className="rounded border-[var(--glass-border)] accent-primary-500"
            />
            <span className="text-sm text-dark-100">{t('hosts.form.verifyPeerCert')}</span>
          </label>

          <div className="space-y-2">
            <Label>{t('hosts.editHost.tag')}</Label>
            <Input
              type="text"
              value={form.tag}
              onChange={(e) => setForm({ ...form, tag: e.target.value })}
              placeholder={t('hosts.editHost.tagPlaceholder')}
              maxLength={32}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.editHost.serverDescription')}</Label>
            <Input
              type="text"
              value={form.server_description}
              onChange={(e) => setForm({ ...form, server_description: e.target.value })}
              placeholder={t('hosts.editHost.serverDescriptionPlaceholder')}
              maxLength={30}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="edit-is-hidden"
              checked={form.is_hidden}
              onChange={(e) => setForm({ ...form, is_hidden: e.target.checked })}
              className="w-4 h-4 rounded border-[var(--glass-border)] bg-[var(--glass-bg)] text-primary-500 focus:ring-primary-500/50"
            />
            <Label htmlFor="edit-is-hidden" className="cursor-pointer">{t('hosts.editHost.hiddenHost')}</Label>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isPending}
          >
            {t('hosts.actions.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
          >
            {isPending ? t('hosts.actions.saving') : t('hosts.actions.save')}
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
  const { t } = useTranslation()
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
    tag: '',
    mihomo_ip_version: '',
    pinned_peer_cert_sha256: '',
    verify_peer_cert_by_name: false,
    server_description: '',
    is_hidden: false,
  })

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {
      remark: form.remark.trim(),
      address: form.address.trim(),
    }
    const port = parseInt(form.port, 10)
    if (!isNaN(port)) createData.port = port
    createData.security_layer = form.security
    if (form.sni.trim()) createData.sni = form.sni.trim()
    if (form.host.trim()) createData.host = form.host.trim()
    if (form.path.trim()) createData.path = form.path.trim()
    if (form.alpn.trim()) createData.alpn = form.alpn.trim()
    if (form.fingerprint.trim()) createData.fingerprint = form.fingerprint.trim()
    if (form.tag.trim()) createData.tags = form.tag.split(',').map((s) => s.trim()).filter(Boolean)
    if (form.mihomo_ip_version) createData.mihomo_ip_version = form.mihomo_ip_version
    if (form.pinned_peer_cert_sha256.trim()) createData.pinned_peer_cert_sha256 = form.pinned_peer_cert_sha256.trim()
    if (form.verify_peer_cert_by_name) createData.verify_peer_cert_by_name = true
    if (form.server_description.trim()) createData.server_description = form.server_description.trim()
    if (form.is_hidden) createData.is_hidden = true
    onSave(createData)
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('hosts.createHost.title')}</DialogTitle>
          <DialogDescription>{t('hosts.createHost.description')}</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('hosts.editHost.name')}</Label>
            <Input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              placeholder={t('hosts.editHost.namePlaceholder')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>{t('hosts.editHost.address')}</Label>
              <Input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder={t('hosts.editHost.addressPlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('hosts.editHost.port')}</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                placeholder={t('hosts.editHost.port')}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.security.label')}</Label>
            <Select value={form.security} onValueChange={(value) => setForm({ ...form, security: value })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('hosts.security.none')}</SelectItem>
                <SelectItem value="tls">{t('hosts.security.tls')}</SelectItem>
                <SelectItem value="reality">{t('hosts.security.reality')}</SelectItem>
                <SelectItem value="xtls">{t('hosts.security.xtls')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.sni')}</Label>
            <Input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              placeholder={t('hosts.form.sniPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.host')}</Label>
            <Input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              placeholder={t('hosts.form.hostPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.path')}</Label>
            <Input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="font-mono text-sm"
              placeholder={t('hosts.form.pathPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.alpn')}</Label>
            <Input
              type="text"
              list="host-alpn-options"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              placeholder={t('hosts.form.alpnPlaceholder')}
            />
            <datalist id="host-alpn-options">
              <option value="h3,h2,http/1.1" />
              <option value="h3,h2" />
              <option value="h2,http/1.1" />
              <option value="h2" />
              <option value="h3" />
              <option value="http/1.1" />
            </datalist>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.fingerprint')}</Label>
            <Input
              type="text"
              list="host-fp-options"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              placeholder={t('hosts.form.fingerprintPlaceholder')}
            />
            <datalist id="host-fp-options">
              <option value="chrome" />
              <option value="firefox" />
              <option value="safari" />
              <option value="ios" />
              <option value="android" />
              <option value="edge" />
              <option value="randomized" />
              <option value="random" />
            </datalist>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.mihomoIpVersion')}</Label>
            <select
              value={form.mihomo_ip_version}
              onChange={(e) => setForm({ ...form, mihomo_ip_version: e.target.value })}
              className="flex h-9 w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="">{t('hosts.form.mihomoIpVersionDefault')}</option>
              <option value="dual">dual</option>
              <option value="ipv4">ipv4</option>
              <option value="ipv6">ipv6</option>
              <option value="ipv4-prefer">ipv4-prefer</option>
              <option value="ipv6-prefer">ipv6-prefer</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.form.pinnedPeerCert')}</Label>
            <Input
              type="text"
              value={form.pinned_peer_cert_sha256}
              onChange={(e) => setForm({ ...form, pinned_peer_cert_sha256: e.target.value })}
              placeholder={t('hosts.form.pinnedPeerCertPlaceholder')}
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.verify_peer_cert_by_name}
              onChange={(e) => setForm({ ...form, verify_peer_cert_by_name: e.target.checked })}
              className="rounded border-[var(--glass-border)] accent-primary-500"
            />
            <span className="text-sm text-dark-100">{t('hosts.form.verifyPeerCert')}</span>
          </label>

          <div className="space-y-2">
            <Label>{t('hosts.editHost.tag')}</Label>
            <Input
              type="text"
              value={form.tag}
              onChange={(e) => setForm({ ...form, tag: e.target.value })}
              placeholder={t('hosts.editHost.tagPlaceholder')}
              maxLength={32}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('hosts.editHost.serverDescription')}</Label>
            <Input
              type="text"
              value={form.server_description}
              onChange={(e) => setForm({ ...form, server_description: e.target.value })}
              placeholder={t('hosts.editHost.serverDescriptionPlaceholder')}
              maxLength={30}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="create-is-hidden"
              checked={form.is_hidden}
              onChange={(e) => setForm({ ...form, is_hidden: e.target.checked })}
              className="w-4 h-4 rounded border-[var(--glass-border)] bg-[var(--glass-bg)] text-primary-500 focus:ring-primary-500/50"
            />
            <Label htmlFor="create-is-hidden" className="cursor-pointer">{t('hosts.editHost.hiddenHost')}</Label>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isPending}
          >
            {t('hosts.actions.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
          >
            {isPending ? t('hosts.actions.creating') : t('hosts.actions.create')}
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
  canEdit,
  canDelete,
}: {
  host: Host
  onEdit: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
  canEdit: boolean
  canDelete: boolean
}) {
  const { t } = useTranslation()
  const scopeAllowsEdit = host.allowed_actions == null || host.allowed_actions.includes('edit')
  const scopeAllowsDelete = host.allowed_actions == null || host.allowed_actions.includes('delete')
  const effectiveCanEdit = canEdit && scopeAllowsEdit
  const effectiveCanDelete = canDelete && scopeAllowsDelete

  const getSecurityLabel = (h: Host): string => {
    const sec = h.security_layer || h.security
    if (!sec) return '-'
    const labels: Record<string, string> = {
      'tls': t('hosts.security.tls'),
      'reality': t('hosts.security.reality'),
      'none': t('hosts.security.none'),
      'xtls': t('hosts.security.xtls'),
      'default': t('hosts.security.default'),
    }
    return labels[sec] || sec
  }

  const getSecurityColor = (h: Host): string => {
    const sec = h.security_layer || h.security
    if (!sec || sec === 'none') return 'text-red-400'
    if (sec === 'reality') return 'text-green-400'
    if (sec === 'tls' || sec === 'xtls') return 'text-blue-400'
    return 'text-dark-200'
  }

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
              <div className="flex items-center gap-1.5">
                <h3 className="font-semibold text-white truncate">{host.remark || t('hosts.statusNoName')}</h3>
                {host.tags && host.tags.length > 0 && (
                  <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20 flex-shrink-0">{host.tags.join(', ')}</span>
                )}
                {host.is_hidden && (
                  <span className="text-[10px] px-1 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 flex-shrink-0">{t('hosts.statusHidden')}</span>
                )}
              </div>
              <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
                <Globe className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{host.address}:{host.port}</span>
              </p>
              {host.server_description && (
                <p className="text-xs text-dark-300 truncate">{host.server_description}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={host.is_disabled ? 'secondary' : 'success'}>
              {host.is_disabled ? t('hosts.statusDisabled') : t('hosts.statusActive')}
            </Badge>

            {/* Actions menu */}
            {(effectiveCanEdit || effectiveCanDelete) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('common.openMenu')}>
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {effectiveCanEdit && (
                    <DropdownMenuItem onSelect={onEdit}>
                      <Pencil className="w-4 h-4 mr-2" />
                      {t('hosts.actions.edit')}
                    </DropdownMenuItem>
                  )}
                  {effectiveCanEdit && <DropdownMenuSeparator />}
                  {effectiveCanEdit && (
                    host.is_disabled ? (
                      <DropdownMenuItem
                        onSelect={onEnable}
                        className="text-green-400 focus:text-green-400"
                      >
                        <Play className="w-4 h-4 mr-2" />
                        {t('hosts.actions.enable')}
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem
                        onSelect={onDisable}
                        className="text-yellow-400 focus:text-yellow-400"
                      >
                        <Square className="w-4 h-4 mr-2" />
                        {t('hosts.actions.disable')}
                      </DropdownMenuItem>
                    )
                  )}
                  {effectiveCanDelete && (
                    <DropdownMenuItem
                      onSelect={onDelete}
                      className="text-red-400 focus:text-red-400"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      {t('hosts.actions.delete')}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="bg-[var(--glass-bg)] rounded-lg p-2">
            <span className="text-dark-200 text-xs">{t('hosts.security.label')}</span>
            <p className={cn('font-medium', getSecurityColor(host))}>
              {(host.security_layer || host.security) === 'reality' && <ShieldCheck className="w-3.5 h-3.5 inline mr-1" />}
              {(host.security_layer || host.security) === 'tls' && <Lock className="w-3.5 h-3.5 inline mr-1" />}
              {getSecurityLabel(host)}
            </p>
          </div>
          <div className="bg-[var(--glass-bg)] rounded-lg p-2">
            <span className="text-dark-200 text-xs">{t('hosts.form.sni')}</span>
            <p className="font-medium text-white truncate">{host.sni || '-'}</p>
          </div>
          {host.inbound && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.form.inbound')}</span>
              <p className="font-medium text-white truncate">{host.inbound.tag}</p>
              <p className="text-[10px] text-dark-300">{host.inbound.type}</p>
            </div>
          )}
          {host.nodes && host.nodes.length > 0 && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.detail.nodes')} ({host.nodes.length})</span>
              <p className="font-medium text-white truncate text-xs">{host.nodes.map(n => n.name).join(', ')}</p>
            </div>
          )}
          {host.host && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.form.host')}</span>
              <p className="font-medium text-white truncate">{host.host}</p>
            </div>
          )}
          {host.path && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.form.path')}</span>
              <p className="font-medium text-white truncate font-mono text-xs">{host.path}</p>
            </div>
          )}
          {host.alpn && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.form.alpn')}</span>
              <p className="font-medium text-white truncate">{host.alpn}</p>
            </div>
          )}
          {host.fingerprint && (
            <div className="bg-[var(--glass-bg)] rounded-lg p-2">
              <span className="text-dark-200 text-xs">{t('hosts.form.fingerprint')}</span>
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
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canCreate = useHasPermission('hosts', 'create')
  const canEdit = useHasPermission('hosts', 'edit')
  const canDelete = useHasPermission('hosts', 'delete')
  const [editingHost, setEditingHost] = useState<Host | null>(null)
  const [editError, setEditError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')
  const [deleteConfirmUuid, setDeleteConfirmUuid] = useState<string | null>(null)
  const [viewMode, setViewMode] = useViewMode('hosts')

  // Fetch hosts
  const { data: hosts = [], isLoading, refetch } = useQuery({
    queryKey: ['hosts'],
    queryFn: fetchHosts,
    refetchInterval: 30000,
  })

  // Mutations
  const enableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/enable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      toast.success(t('hosts.toast.enabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('hosts.toast.error'))
    },
  })

  const disableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      toast.success(t('hosts.toast.disabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('hosts.toast.error'))
    },
  })

  const deleteHost = useMutation({
    mutationFn: (uuid: string) => client.delete(`/hosts/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      toast.success(t('hosts.toast.deleted'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('hosts.toast.error'))
    },
  })

  const updateHost = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Record<string, unknown> }) =>
      client.patch(`/hosts/${uuid}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      setEditingHost(null)
      setEditError('')
      toast.success(t('hosts.toast.updated'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || t('hosts.toast.saveError'))
      toast.error(err.response?.data?.detail || err.message || t('hosts.toast.saveError'))
    },
  })

  const createHost = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/hosts', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      setShowCreateModal(false)
      setCreateError('')
      toast.success(t('hosts.toast.created'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || t('hosts.toast.createError'))
      toast.error(err.response?.data?.detail || err.message || t('hosts.toast.createError'))
    },
  })

  // Stats
  const totalHosts = hosts.length
  const activeHosts = hosts.filter((h) => !h.is_disabled).length
  const disabledHosts = hosts.filter((h) => h.is_disabled).length
  const hiddenHosts = hosts.filter((h) => h.is_hidden).length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('hosts.title')}</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">{t('hosts.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          {canCreate && (
            <Button
              onClick={() => { setShowCreateModal(true); setCreateError('') }}
              className="gap-2"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">{t('hosts.actions.add')}</span>
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading}
            className="gap-2"
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
            <span className="hidden sm:inline">{t('hosts.actions.refresh')}</span>
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4">
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">{t('hosts.stats.total')}</p>
            <p className="text-xl md:text-2xl font-bold text-white mt-1">
              {isLoading ? '-' : totalHosts}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">{t('hosts.stats.active')}</p>
            <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
              {isLoading ? '-' : activeHosts}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">{t('hosts.stats.disabled')}</p>
            <p className="text-xl md:text-2xl font-bold text-dark-200 mt-1">
              {isLoading ? '-' : disabledHosts}
            </p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <CardContent className="p-4">
            <p className="text-xs md:text-sm text-dark-200">{t('hosts.stats.hidden')}</p>
            <p className="text-xl md:text-2xl font-bold text-yellow-400 mt-1">
              {isLoading ? '-' : hiddenHosts}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Toolbar: view toggle */}
      {!isLoading && hosts.length > 0 && (
        <div className="flex items-center justify-end">
          <ViewToggle mode={viewMode} onChange={setViewMode} />
        </div>
      )}

      {/* Hosts list */}
      {!isLoading && viewMode === 'table' && hosts.length > 0 ? (
        <HostsTable
          hosts={hosts}
          canEdit={canEdit}
          canDelete={canDelete}
          onEdit={(h) => { setEditingHost(hosts.find((x) => x.uuid === h.uuid) ?? null); setEditError('') }}
          onEnable={(h) => enableHost.mutate(h.uuid)}
          onDisable={(h) => disableHost.mutate(h.uuid)}
          onDelete={(h) => setDeleteConfirmUuid(h.uuid)}
        />
      ) : (
        <div
          className={cn(
            'grid gap-4',
            viewMode === 'compact'
              ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
              : 'grid-cols-1 lg:grid-cols-2',
          )}
        >
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <HostSkeleton key={i} />)
          ) : hosts.length === 0 ? (
            <Card className="col-span-full">
              <CardContent className="py-12 text-center">
                <Globe className="w-12 h-12 text-dark-300 mx-auto mb-3" />
                <p className="text-dark-200">{t('hosts.statusNoHosts')}</p>
              </CardContent>
            </Card>
          ) : (
            hosts.map((host, i) => (
              <div key={host.uuid} className="animate-fade-in-up" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
                {viewMode === 'compact' ? (
                  <HostCompactCard
                    host={host}
                    canEdit={canEdit}
                    canDelete={canDelete}
                    onEdit={(h) => { setEditingHost(hosts.find((x) => x.uuid === h.uuid) ?? null); setEditError('') }}
                    onEnable={(h) => enableHost.mutate(h.uuid)}
                    onDisable={(h) => disableHost.mutate(h.uuid)}
                    onDelete={(h) => setDeleteConfirmUuid(h.uuid)}
                  />
                ) : (
                  <HostCard
                    host={host}
                    onEdit={() => { setEditingHost(host); setEditError('') }}
                    onEnable={() => enableHost.mutate(host.uuid)}
                    onDisable={() => disableHost.mutate(host.uuid)}
                    onDelete={() => setDeleteConfirmUuid(host.uuid)}
                    canEdit={canEdit}
                    canDelete={canDelete}
                  />
                )}
              </div>
            ))
          )}
        </div>
      )}

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

      {/* Confirm delete dialog */}
      <ConfirmDialog
        open={deleteConfirmUuid !== null}
        onOpenChange={(open) => { if (!open) setDeleteConfirmUuid(null) }}
        title={t('hosts.deleteConfirm.title')}
        description={t('hosts.deleteConfirm.description')}
        confirmLabel={t('hosts.deleteConfirm.confirm')}
        variant="destructive"
        onConfirm={() => {
          if (deleteConfirmUuid) {
            deleteHost.mutate(deleteConfirmUuid)
            setDeleteConfirmUuid(null)
          }
        }}
      />
    </div>
  )
}
