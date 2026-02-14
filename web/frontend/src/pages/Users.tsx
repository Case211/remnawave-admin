import { useState, useEffect, useRef, memo, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'
import { useFormatters } from '@/lib/useFormatters'
import {
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
  Eye,
  Pencil,
  Trash2,
  Check,
  Ban,
  ArrowUp,
  ArrowDown,
  Filter,
  X,
  ChevronDown,
  ChevronUp,
  Plus,
  User,
  Wifi,
  Users as UsersIcon,
  Infinity,
} from 'lucide-react'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { useHasPermission } from '../components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ExportDropdown } from '@/components/ExportDropdown'
import { SavedFiltersDropdown } from '@/components/SavedFiltersDropdown'
import { exportCSV, exportJSON, formatBytesForExport } from '@/lib/export'

// Types
interface UserListItem {
  uuid: string
  short_uuid: string
  username: string | null
  email: string | null
  description: string | null
  tag: string | null
  status: string
  expire_at: string | null
  traffic_limit_bytes: number | null
  traffic_limit_strategy: string | null
  used_traffic_bytes: number
  lifetime_used_traffic_bytes: number
  hwid_device_limit: number
  hwid_device_count: number
  external_squad_uuid: string | null
  created_at: string | null
  updated_at: string | null
  online_at: string | null
}

interface PaginatedResponse {
  items: UserListItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

// API functions
const fetchUsers = async (params: {
  page: number
  per_page: number
  search?: string
  status?: string
  traffic_type?: string
  expire_filter?: string
  online_filter?: string
  traffic_usage?: string
  sort_by: string
  sort_order: string
}): Promise<PaginatedResponse> => {
  const { data } = await client.get('/users', { params })
  return data
}

function getTrafficPercent(used: number, limit: number | null): number {
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

// Status badge component
const StatusBadge = memo(function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const normalizedStatus = status.toLowerCase()
  const statusConfig: Record<string, { labelKey: string; variant: 'success' | 'destructive' | 'warning' | 'secondary' }> = {
    active: { labelKey: 'users.statuses.active', variant: 'success' },
    disabled: { labelKey: 'users.statuses.disabled', variant: 'destructive' },
    limited: { labelKey: 'users.statuses.limited', variant: 'warning' },
    expired: { labelKey: 'users.statuses.expired', variant: 'secondary' },
  }

  const config = statusConfig[normalizedStatus] || { labelKey: '', variant: 'secondary' as const }

  return <Badge variant={config.variant}>{config.labelKey ? t(config.labelKey) : status}</Badge>
})

// Traffic bar component
const TrafficBar = memo(function TrafficBar({ used, limit }: { used: number; limit: number | null }) {
  const { formatBytes } = useFormatters()
  const percent = getTrafficPercent(used, limit)
  const isUnlimited = !limit

  const gradientClass = isUnlimited
    ? 'from-primary-600/30 to-cyan-600/30 border-primary-500/20'
    : percent >= 90
    ? 'from-red-600/30 to-red-500/20 border-red-500/20'
    : percent >= 70
    ? 'from-yellow-600/30 to-yellow-500/20 border-yellow-500/20'
    : 'from-primary-600/30 to-cyan-600/30 border-primary-500/20'

  const textClass = isUnlimited
    ? 'text-primary-200'
    : percent >= 90
    ? 'text-red-200'
    : percent >= 70
    ? 'text-yellow-200'
    : 'text-primary-200'

  return (
    <div className={`relative h-5 rounded-full overflow-hidden bg-gradient-to-r ${gradientClass} border`}>
      {!isUnlimited && percent > 0 && (
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-full transition-all",
            percent >= 90 ? 'bg-red-500/20' : percent >= 70 ? 'bg-yellow-500/20' : 'bg-primary-500/20'
          )}
          style={{ width: `${percent}%` }}
        />
      )}
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`text-[11px] font-medium ${textClass}`}>
          {formatBytes(used)} / {isUnlimited ? '\u221E' : formatBytes(limit)}
        </span>
      </div>
    </div>
  )
})

// Online indicator
const OnlineIndicator = memo(function OnlineIndicator({ onlineAt }: { onlineAt: string | null }) {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
  if (!onlineAt) return <span className="text-dark-300 text-xs">{t('users.noData')}</span>

  const date = new Date(onlineAt)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffHours = diffMs / 3600000

  let dotColor = 'bg-gray-500'
  if (diffHours < 1) dotColor = 'bg-green-500'
  else if (diffHours < 24) dotColor = 'bg-yellow-500'
  else if (diffHours < 168) dotColor = 'bg-orange-500'

  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} flex-shrink-0`} />
      <span className="text-dark-200 text-xs">{formatTimeAgo(onlineAt)}</span>
    </div>
  )
})

// Action dropdown
function UserActions({
  user,
  onEnable,
  onDisable,
  onDelete,
}: {
  user: UserListItem
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const canEdit = useHasPermission('users', 'edit')
  const canDelete = useHasPermission('users', 'delete')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <MoreVertical className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuItem onClick={() => navigate(`/users/${user.uuid}`)}>
          <Eye className="w-4 h-4 mr-2" /> {t('users.actions.view')}
        </DropdownMenuItem>
        {canEdit && (
          <DropdownMenuItem onClick={() => navigate(`/users/${user.uuid}?edit=1`)}>
            <Pencil className="w-4 h-4 mr-2" /> {t('users.actions.edit')}
          </DropdownMenuItem>
        )}
        {(canEdit || canDelete) && <DropdownMenuSeparator />}
        {canEdit && (
          user.status === 'disabled' ? (
            <DropdownMenuItem onClick={onEnable} className="text-green-400 focus:text-green-400">
              <Check className="w-4 h-4 mr-2" /> {t('users.actions.enable')}
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={onDisable} className="text-yellow-400 focus:text-yellow-400">
              <Ban className="w-4 h-4 mr-2" /> {t('users.actions.disable')}
            </DropdownMenuItem>
          )
        )}
        {canDelete && (
          <DropdownMenuItem
            onClick={onDelete}
            className="text-red-400 focus:text-red-400"
          >
            <Trash2 className="w-4 h-4 mr-2" /> {t('users.actions.delete')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Sortable header
const SortHeader = memo(function SortHeader({
  label,
  field,
  currentSort,
  currentOrder,
  onSort,
}: {
  label: string
  field: string
  currentSort: string
  currentOrder: string
  onSort: (field: string) => void
}) {
  const isActive = currentSort === field
  const Icon = isActive && currentOrder === 'asc' ? ArrowUp : ArrowDown

  return (
    <button
      onClick={() => onSort(field)}
      className={cn(
        "flex items-center gap-1 hover:text-white transition-all duration-200",
        isActive && "text-primary-400"
      )}
    >
      {label}
      {isActive && <Icon className="w-4 h-4" />}
    </button>
  )
})

// Mobile user card
const MobileUserCard = memo(function MobileUserCard({
  user,
  onNavigate,
  onEnable,
  onDisable,
  onDelete,
}: {
  user: UserListItem
  onNavigate: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const { formatDateShort } = useFormatters()
  return (
    <Card
      className="cursor-pointer active:bg-dark-700/50"
      onClick={onNavigate}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <p className="font-medium text-white truncate">
                {user.username || user.short_uuid}
              </p>
              {user.tag && (
                <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20 flex-shrink-0">{user.tag}</span>
              )}
            </div>
            {user.description && (
              <p className="text-xs text-dark-300 truncate" title={user.description}>{user.description}</p>
            )}
            {user.email && (
              <p className="text-xs text-dark-200 truncate">{user.email}</p>
            )}
          </div>
          <div className="flex items-center gap-2 ml-2" onClick={(e) => e.stopPropagation()}>
            <StatusBadge status={user.status} />
            <UserActions user={user} onEnable={onEnable} onDisable={onDisable} onDelete={onDelete} />
          </div>
        </div>
        <div className="mb-3">
          <TrafficBar used={user.used_traffic_bytes} limit={user.traffic_limit_bytes} />
        </div>
        <div className="flex items-center justify-between text-xs text-dark-200">
          <OnlineIndicator onlineAt={user.online_at} />
          <div className="flex items-center gap-3">
            <span title={t('users.hwidDevices')}>{user.hwid_device_count} / {user.hwid_device_limit || '\u221E'}</span>
            <span>{t('users.expires')}: {user.expire_at ? formatDateShort(user.expire_at) : '\u2014'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
})

interface Squad {
  uuid: string
  squadTag: string
  squadName?: string
  name?: string
  tag?: string
}

interface CreateUserFormData {
  username: string
  email: string
  tag: string
  telegram_id: string
  description: string
  traffic_limit_gb: string
  is_unlimited: boolean
  traffic_limit_strategy: string
  expire_at: string
  hwid_device_limit: string
  external_squad_uuid: string
  active_internal_squads: string[]
}

function CreateUserModal({
  open,
  onClose,
  onSave,
  isPending,
  error,
}: {
  open: boolean
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState<CreateUserFormData>({
    username: '',
    email: '',
    tag: '',
    telegram_id: '',
    description: '',
    traffic_limit_gb: '',
    is_unlimited: true,
    traffic_limit_strategy: 'NO_RESET',
    expire_at: '',
    hwid_device_limit: '0',
    external_squad_uuid: '',
    active_internal_squads: [],
  })

  const { data: internalSquads = [] } = useQuery<Squad[]>({
    queryKey: ['internal-squads'],
    queryFn: async () => {
      const { data } = await client.get('/users/meta/internal-squads')
      return Array.isArray(data) ? data : []
    },
    enabled: open,
  })

  const { data: externalSquads = [] } = useQuery<Squad[]>({
    queryKey: ['external-squads'],
    queryFn: async () => {
      const { data } = await client.get('/users/meta/external-squads')
      return Array.isArray(data) ? data : []
    },
    enabled: open,
  })

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {}
    if (form.username.trim()) createData.username = form.username.trim()

    if (form.telegram_id.trim()) {
      const tgId = parseInt(form.telegram_id.trim(), 10)
      if (!isNaN(tgId)) createData.telegram_id = tgId
    }

    if (form.email.trim()) createData.email = form.email.trim()
    if (form.tag.trim()) createData.tag = form.tag.trim().toUpperCase()
    if (form.description.trim()) createData.description = form.description.trim()

    if (!form.is_unlimited && form.traffic_limit_gb) {
      const val = parseFloat(form.traffic_limit_gb)
      if (!isNaN(val) && val > 0) {
        createData.traffic_limit_bytes = Math.round(val * 1024 * 1024 * 1024)
      }
    } else {
      createData.traffic_limit_bytes = null
    }

    createData.traffic_limit_strategy = form.traffic_limit_strategy

    if (form.expire_at) {
      createData.expire_at = new Date(form.expire_at).toISOString()
    }

    const hwid = parseInt(form.hwid_device_limit, 10)
    if (!isNaN(hwid)) {
      createData.hwid_device_limit = hwid
    }

    if (form.external_squad_uuid) {
      createData.external_squad_uuid = form.external_squad_uuid
    }

    if (form.active_internal_squads.length > 0) {
      createData.active_internal_squads = form.active_internal_squads
    }

    onSave(createData)
  }

  const toggleInternalSquad = (uuid: string) => {
    setForm(prev => ({
      ...prev,
      active_internal_squads: prev.active_internal_squads.includes(uuid)
        ? prev.active_internal_squads.filter(u => u !== uuid)
        : [...prev.active_internal_squads, uuid],
    }))
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="w-5 h-5 text-primary-400" />
            {t('users.createModal.title')}
          </DialogTitle>
          <DialogDescription>{t('users.createModal.description')}</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-2">
            <X className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-5">
          {/* Section: Basic info */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-medium text-dark-300 uppercase tracking-wider">
              <User className="w-3.5 h-3.5" />
              {t('users.createModal.basicInfo')}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.username')}</Label>
                <Input
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  placeholder="username"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.telegramId')}</Label>
                <Input
                  type="number"
                  value={form.telegram_id}
                  onChange={(e) => setForm({ ...form, telegram_id: e.target.value })}
                  placeholder="123456789"
                  className="mt-1"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.email')}</Label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="user@example.com"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.tag')}</Label>
                <Input
                  value={form.tag}
                  onChange={(e) => setForm({ ...form, tag: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })}
                  placeholder="MY_TAG"
                  maxLength={16}
                  className="mt-1 font-mono"
                />
                <p className="text-[10px] text-dark-300 mt-0.5">{t('users.createModal.tagHint')}</p>
              </div>
            </div>

            <div>
              <Label className="text-xs text-dark-200">{t('users.createModal.descriptionLabel')}</Label>
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder={t('users.createModal.descriptionPlaceholder')}
                className="mt-1"
              />
            </div>
          </div>

          <Separator className="bg-dark-400/15" />

          {/* Section: Traffic */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-medium text-dark-300 uppercase tracking-wider">
              <Wifi className="w-3.5 h-3.5" />
              {t('users.createModal.trafficAndLimits')}
            </div>

            <div className="flex items-center justify-between">
              <Label className="text-sm text-dark-100 flex items-center gap-2">
                <Infinity className="w-4 h-4 text-dark-300" />
                {t('users.createModal.unlimitedTraffic')}
              </Label>
              <Switch
                checked={form.is_unlimited}
                onCheckedChange={(checked) => setForm({
                  ...form,
                  is_unlimited: checked,
                  traffic_limit_gb: checked ? '' : form.traffic_limit_gb,
                })}
              />
            </div>

            {!form.is_unlimited && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-fade-in">
                <div>
                  <Label className="text-xs text-dark-200">{t('users.createModal.trafficLimit')}</Label>
                  <div className="relative mt-1">
                    <Input
                      type="number"
                      step="0.1"
                      min="0"
                      value={form.traffic_limit_gb}
                      onChange={(e) => setForm({ ...form, traffic_limit_gb: e.target.value })}
                      placeholder="0.0"
                      className="pr-12"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-dark-300 font-medium">{t('users.createModal.gb')}</span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-dark-200">{t('users.createModal.resetStrategy')}</Label>
                  <Select
                    value={form.traffic_limit_strategy}
                    onValueChange={(value) => setForm({ ...form, traffic_limit_strategy: value })}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MONTH">{t('users.strategies.monthly')}</SelectItem>
                      <SelectItem value="WEEK">{t('users.strategies.weekly')}</SelectItem>
                      <SelectItem value="DAY">{t('users.strategies.daily')}</SelectItem>
                      <SelectItem value="NO_RESET">{t('users.strategies.noReset')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.expireDate')}</Label>
                <Input
                  type="datetime-local"
                  value={form.expire_at}
                  onChange={(e) => setForm({ ...form, expire_at: e.target.value })}
                  className="mt-1"
                />
                <p className="text-[10px] text-dark-300 mt-0.5">{t('users.createModal.expireHint')}</p>
              </div>
              <div>
                <Label className="text-xs text-dark-200">{t('users.createModal.hwidLimit')}</Label>
                <Input
                  type="number"
                  min="0"
                  value={form.hwid_device_limit}
                  onChange={(e) => setForm({ ...form, hwid_device_limit: e.target.value })}
                  className="mt-1"
                />
                <p className="text-[10px] text-dark-300 mt-0.5">{t('users.createModal.hwidHint')}</p>
              </div>
            </div>
          </div>

          {/* Section: Squads */}
          {(externalSquads.length > 0 || internalSquads.length > 0) && (
            <>
              <Separator className="bg-dark-400/15" />
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-medium text-dark-300 uppercase tracking-wider">
                  <UsersIcon className="w-3.5 h-3.5" />
                  {t('users.createModal.squads')}
                </div>

                {externalSquads.length > 0 && (
                  <div>
                    <Label className="text-xs text-dark-200">{t('users.createModal.externalSquad')}</Label>
                    <Select
                      value={form.external_squad_uuid || '_none'}
                      onValueChange={(value) => setForm({ ...form, external_squad_uuid: value === '_none' ? '' : value })}
                    >
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder={t('users.createModal.notSelected')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none">{t('users.createModal.notSelected')}</SelectItem>
                        {externalSquads.map((sq: Squad) => (
                          <SelectItem key={sq.uuid} value={sq.uuid}>
                            {sq.squadName || sq.name || sq.squadTag || sq.tag || sq.uuid}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {internalSquads.length > 0 && (
                  <div>
                    <Label className="text-xs text-dark-200">{t('users.createModal.internalSquads')}</Label>
                    <div className="mt-1.5 space-y-1 max-h-32 overflow-y-auto rounded-md border border-dark-400/20 p-2">
                      {internalSquads.map((sq: Squad) => (
                        <label
                          key={sq.uuid}
                          className="flex items-center gap-2.5 cursor-pointer rounded-md px-2 py-1.5 hover:bg-dark-600/50 transition-colors"
                        >
                          <Checkbox
                            checked={form.active_internal_squads.includes(sq.uuid)}
                            onCheckedChange={() => toggleInternalSquad(sq.uuid)}
                          />
                          <span className="text-sm text-dark-100">
                            {sq.squadName || sq.name || sq.squadTag || sq.tag || sq.uuid}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            {t('users.cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                {t('users.creating')}
              </>
            ) : (
              <>
                <Plus className="w-4 h-4 mr-2" />
                {t('users.create')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function Users() {
  const { t } = useTranslation()
  const { formatDateShort, formatNumber } = useFormatters()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canCreate = useHasPermission('users', 'create')
  const canBulk = useHasPermission('users', 'bulk_operations')

  const [selectedUuids, setSelectedUuids] = useState<Set<string>>(new Set())
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')
  const [deleteConfirmUuid, setDeleteConfirmUuid] = useState<string | null>(null)

  // State
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState('')
  const [trafficType, setTrafficType] = useState('')
  const [expireFilter, setExpireFilter] = useState('')
  const [onlineFilter, setOnlineFilter] = useState('')
  const [trafficUsage, setTrafficUsage] = useState('')
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')
  const [showFilters, setShowFilters] = useState(false)

  const activeFilterCount = useMemo(
    () => [status, trafficType, expireFilter, onlineFilter, trafficUsage].filter(Boolean).length,
    [status, trafficType, expireFilter, onlineFilter, trafficUsage],
  )

  // Export handlers
  const handleExportCSV = () => {
    const items = data?.items
    if (!items?.length) return
    const exportData = items.map((u) => ({
      username: u.username || '',
      status: u.status,
      email: u.email || '',
      traffic_used: formatBytesForExport(u.used_traffic_bytes),
      traffic_limit: u.traffic_limit_bytes ? formatBytesForExport(u.traffic_limit_bytes) : t('users.unlimited'),
      hwid_count: u.hwid_device_count ?? 0,
      hwid_limit: u.hwid_device_limit ?? 0,
      online_at: u.online_at || '',
      expire_at: u.expire_at || '',
      created_at: u.created_at || '',
    }))
    exportCSV(exportData, `users-${new Date().toISOString().slice(0, 10)}`)
    toast.success(t('users.toasts.csvExported'))
  }
  const handleExportJSON = () => {
    const items = data?.items
    if (!items?.length) return
    exportJSON(items, `users-${new Date().toISOString().slice(0, 10)}`)
    toast.success(t('users.toasts.jsonExported'))
  }

  // Saved filters
  const currentFilters = useMemo<Record<string, unknown>>(() => ({
    ...(status && { status }),
    ...(trafficType && { trafficType }),
    ...(expireFilter && { expireFilter }),
    ...(onlineFilter && { onlineFilter }),
    ...(trafficUsage && { trafficUsage }),
  }), [status, trafficType, expireFilter, onlineFilter, trafficUsage])
  const hasActiveFilters = activeFilterCount > 0
  const handleLoadFilter = useCallback((filters: Record<string, unknown>) => {
    setStatus((filters.status as string) || '')
    setTrafficType((filters.trafficType as string) || '')
    setExpireFilter((filters.expireFilter as string) || '')
    setOnlineFilter((filters.onlineFilter as string) || '')
    setTrafficUsage((filters.trafficUsage as string) || '')
    setShowFilters(true)
    setPage(1)
  }, [])

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  // Fetch users
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['users', page, perPage, debouncedSearch, status, trafficType, expireFilter, onlineFilter, trafficUsage, sortBy, sortOrder],
    queryFn: () =>
      fetchUsers({
        page,
        per_page: perPage,
        search: debouncedSearch || undefined,
        status: status || undefined,
        traffic_type: trafficType || undefined,
        expire_filter: expireFilter || undefined,
        online_filter: onlineFilter || undefined,
        traffic_usage: trafficUsage || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      }),
    retry: 2,
  })

  // Mutations
  const enableUser = useMutation({
    mutationFn: (uuid: string) => client.post(`/users/${uuid}/enable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('users.toasts.userEnabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('users.toasts.enableError'))
    },
  })

  const disableUser = useMutation({
    mutationFn: (uuid: string) => client.post(`/users/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('users.toasts.userDisabled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('users.toasts.disableError'))
    },
  })

  const deleteUser = useMutation({
    mutationFn: (uuid: string) => client.delete(`/users/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('users.toasts.userDeleted'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('users.toasts.deleteError'))
    },
  })

  const createUser = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/users', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateModal(false)
      setCreateError('')
      toast.success(t('users.toasts.userCreated'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || t('users.toasts.createError'))
      toast.error(err.response?.data?.detail || err.message || t('users.toasts.createError'))
    },
  })

  const handleSort = useCallback((field: string) => {
    setSortBy((prev) => {
      if (prev === field) {
        setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
        return prev
      }
      setSortOrder('desc')
      return field
    })
    setPage(1)
  }, [])

  const resetFilters = useCallback(() => {
    setSearch('')
    setStatus('')
    setTrafficType('')
    setExpireFilter('')
    setOnlineFilter('')
    setTrafficUsage('')
    setPage(1)
  }, [])

  // Selection helpers
  const toggleSelect = useCallback((uuid: string) => {
    setSelectedUuids(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }, [])
  const toggleSelectAll = useCallback(() => {
    const items = data?.items
    if (!items) return
    const pageUuids = items.map((u) => u.uuid)
    setSelectedUuids(prev => {
      const allSelected = pageUuids.every((id: string) => prev.has(id))
      const next = new Set(prev)
      if (allSelected) {
        pageUuids.forEach((id: string) => next.delete(id))
      } else {
        pageUuids.forEach((id: string) => next.add(id))
      }
      return next
    })
  }, [data?.items])
  const clearSelection = useCallback(() => setSelectedUuids(new Set()), [])

  // Bulk mutations
  const bulkEnable = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/enable', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(t('users.toasts.bulkEnabled', { success: d.success, failed: d.failed || 0 }))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('users.toasts.error')) },
  })
  const bulkDisable = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/disable', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(t('users.toasts.bulkDisabled', { success: d.success, failed: d.failed || 0 }))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('users.toasts.error')) },
  })
  const bulkDelete = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/delete', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(t('users.toasts.bulkDeleted', { success: d.success, failed: d.failed || 0 }))
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || t('users.toasts.error')) },
  })

  const hasAnyFilter = activeFilterCount > 0 || debouncedSearch

  const users = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  // Virtual scrolling for large page sizes (50+ rows)
  const tableContainerRef = useRef<HTMLDivElement>(null)
  const useVirtual = users.length > 30
  const rowVirtualizer = useVirtualizer({
    count: users.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 56,
    overscan: 10,
  })

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('users.title')}</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">
            {t('users.subtitle')}
          </p>
        </div>
        {canCreate && (
          <Button
            onClick={() => { setShowCreateModal(true); setCreateError('') }}
            className="self-start sm:self-auto"
          >
            <Plus className="w-4 h-4 mr-2" />
            <span className="hidden sm:inline">{t('users.createUser')}</span>
            <span className="sm:hidden">{t('users.create')}</span>
          </Button>
        )}
      </div>

      {/* Search + Filter/Sort controls */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-3">
            {/* Row 1: Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-200" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('users.searchPlaceholder')}
                className="pl-10"
              />
            </div>

            {/* Row 2: Filters | Sort | Refresh */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowFilters(!showFilters)}
                className={cn(
                  "flex-1 sm:flex-none",
                  activeFilterCount > 0 && "border-primary-500/50 text-primary-400"
                )}
              >
                <Filter className="w-4 h-4 mr-2" />
                {t('users.filters.title')}
                {activeFilterCount > 0 && (
                  <span className="bg-primary-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center ml-2">
                    {activeFilterCount}
                  </span>
                )}
                {showFilters ? <ChevronUp className="w-4 h-4 ml-1" /> : <ChevronDown className="w-4 h-4 ml-1" />}
              </Button>

              <Separator orientation="vertical" className="hidden sm:block h-6" />

              <div className="flex items-center gap-2 flex-1 sm:flex-none">
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={() => { setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc'); setPage(1) }}
                  title={sortOrder === 'desc' ? t('users.sort.descending') : t('users.sort.ascending')}
                >
                  {sortOrder === 'desc' ? (
                    <ArrowDown className="w-5 h-5 text-primary-400" />
                  ) : (
                    <ArrowUp className="w-5 h-5 text-primary-400" />
                  )}
                </Button>

                <div className="flex-1 sm:flex-none sm:w-48">
                  <Select value={sortBy} onValueChange={(value) => { setSortBy(value); setPage(1) }}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="created_at">{t('users.sort.createdAt')}</SelectItem>
                      <SelectItem value="used_traffic_bytes">{t('users.sort.trafficCurrent')}</SelectItem>
                      <SelectItem value="lifetime_used_traffic_bytes">{t('users.sort.trafficLifetime')}</SelectItem>
                      <SelectItem value="hwid_device_limit">{t('users.sort.hwidDevices')}</SelectItem>
                      <SelectItem value="online_at">{t('users.sort.lastActivity')}</SelectItem>
                      <SelectItem value="expire_at">{t('users.sort.expireDate')}</SelectItem>
                      <SelectItem value="traffic_limit_bytes">{t('users.sort.trafficLimit')}</SelectItem>
                      <SelectItem value="username">{t('users.sort.name')}</SelectItem>
                      <SelectItem value="status">{t('users.sort.status')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button
                variant="secondary"
                size="icon"
                onClick={() => refetch()}
                disabled={isLoading}
                title={t('users.refresh')}
              >
                <RefreshCw className={cn("w-5 h-5", isLoading && "animate-spin")} />
              </Button>

              <ExportDropdown
                onExportCSV={handleExportCSV}
                onExportJSON={handleExportJSON}
                disabled={!data?.items?.length}
              />
              <SavedFiltersDropdown
                page="users"
                currentFilters={currentFilters}
                onLoadFilter={handleLoadFilter}
                hasActiveFilters={hasActiveFilters}
              />
            </div>

            {/* Expandable filter panel */}
            {showFilters && (
              <div className="pt-3 border-t border-dark-400/20 space-y-3 animate-fade-in">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.status')}</Label>
                    <Select value={status || '_all'} onValueChange={(v) => { setStatus(v === '_all' ? '' : v); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_all">{t('users.filters.allStatuses')}</SelectItem>
                        <SelectItem value="active">{t('users.filters.statusActive')}</SelectItem>
                        <SelectItem value="disabled">{t('users.filters.statusDisabled')}</SelectItem>
                        <SelectItem value="limited">{t('users.filters.statusLimited')}</SelectItem>
                        <SelectItem value="expired">{t('users.filters.statusExpired')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.trafficType')}</Label>
                    <Select value={trafficType || '_all'} onValueChange={(v) => { setTrafficType(v === '_all' ? '' : v); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_all">{t('users.filters.any')}</SelectItem>
                        <SelectItem value="unlimited">{t('users.filters.unlimited')}</SelectItem>
                        <SelectItem value="limited">{t('users.filters.withLimit')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.trafficUsage')}</Label>
                    <Select value={trafficUsage || '_all'} onValueChange={(v) => { setTrafficUsage(v === '_all' ? '' : v); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_all">{t('users.filters.anyUsage')}</SelectItem>
                        <SelectItem value="above_90">{t('users.filters.above90')}</SelectItem>
                        <SelectItem value="above_70">{t('users.filters.above70')}</SelectItem>
                        <SelectItem value="above_50">{t('users.filters.above50')}</SelectItem>
                        <SelectItem value="zero">{t('users.filters.zeroTraffic')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.expiry')}</Label>
                    <Select value={expireFilter || '_all'} onValueChange={(v) => { setExpireFilter(v === '_all' ? '' : v); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_all">{t('users.filters.anyExpiry')}</SelectItem>
                        <SelectItem value="expiring_7d">{t('users.filters.expiring7d')}</SelectItem>
                        <SelectItem value="expiring_30d">{t('users.filters.expiring30d')}</SelectItem>
                        <SelectItem value="expired">{t('users.filters.alreadyExpired')}</SelectItem>
                        <SelectItem value="no_expiry">{t('users.filters.noExpiry')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.activity')}</Label>
                    <Select value={onlineFilter || '_all'} onValueChange={(v) => { setOnlineFilter(v === '_all' ? '' : v); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_all">{t('users.filters.anyActivity')}</SelectItem>
                        <SelectItem value="online_24h">{t('users.filters.online24h')}</SelectItem>
                        <SelectItem value="online_7d">{t('users.filters.online7d')}</SelectItem>
                        <SelectItem value="online_30d">{t('users.filters.online30d')}</SelectItem>
                        <SelectItem value="never">{t('users.filters.neverConnected')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">{t('users.filters.perPage')}</Label>
                    <Select value={String(perPage)} onValueChange={(v) => { setPerPage(Number(v)); setPage(1) }}>
                      <SelectTrigger className="mt-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="10">10</SelectItem>
                        <SelectItem value="20">20</SelectItem>
                        <SelectItem value="50">50</SelectItem>
                        <SelectItem value="100">100</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {hasAnyFilter && (
                  <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-dark-300">
                      {t('users.found')}: <span className="text-white font-medium">{formatNumber(total)}</span> {t('users.usersCount')}
                    </p>
                    <button
                      onClick={resetFilters}
                      className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                    >
                      <X className="w-3 h-3" />
                      {t('users.resetAllFilters')}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Active filters chips */}
            {!showFilters && activeFilterCount > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                {status && (
                  <FilterChip
                    label={`${t('users.filters.status')}: ${({ active: t('users.filters.statusActive'), disabled: t('users.filters.statusDisabled'), limited: t('users.filters.statusLimited'), expired: t('users.filters.statusExpired') } as Record<string, string>)[status] || status}`}
                    onRemove={() => { setStatus(''); setPage(1) }}
                  />
                )}
                {trafficType && (
                  <FilterChip
                    label={`${t('users.filters.trafficType')}: ${trafficType === 'unlimited' ? t('users.unlimited') : t('users.filters.withLimit')}`}
                    onRemove={() => { setTrafficType(''); setPage(1) }}
                  />
                )}
                {trafficUsage && (
                  <FilterChip
                    label={`${t('users.filters.trafficUsage')}: ${({ above_90: '>90%', above_70: '>70%', above_50: '>50%', zero: '0' } as Record<string, string>)[trafficUsage] || trafficUsage}`}
                    onRemove={() => { setTrafficUsage(''); setPage(1) }}
                  />
                )}
                {expireFilter && (
                  <FilterChip
                    label={`${t('users.filters.expiry')}: ${({ expiring_7d: t('users.filters.expiring7d'), expiring_30d: t('users.filters.expiring30d'), expired: t('users.filters.alreadyExpired'), no_expiry: t('users.filters.noExpiry') } as Record<string, string>)[expireFilter] || expireFilter}`}
                    onRemove={() => { setExpireFilter(''); setPage(1) }}
                  />
                )}
                {onlineFilter && (
                  <FilterChip
                    label={`${t('users.filters.activity')}: ${({ online_24h: t('users.filters.online24h'), online_7d: t('users.filters.online7d'), online_30d: t('users.filters.online30d'), never: t('users.filters.neverConnected') } as Record<string, string>)[onlineFilter] || onlineFilter}`}
                    onRemove={() => { setOnlineFilter(''); setPage(1) }}
                  />
                )}
                <button onClick={resetFilters} className="text-[11px] text-dark-300 hover:text-primary-400 ml-1">
                  {t('users.resetAll')}
                </button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Error state */}
      {isError && (
        <Card className="border-red-500/30 bg-red-500/10">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-red-400 text-sm">
                {t('users.loadError')}: {(error as Error)?.message || t('users.unknownError')}
              </p>
              <Button variant="secondary" size="sm" onClick={() => refetch()}>
                {t('users.retry')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Mobile: User cards */}
      <div className="md:hidden space-y-3">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-5 w-20" />
                </div>
                <Skeleton className="h-4 w-full mb-3" />
                <div className="flex justify-between">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </CardContent>
            </Card>
          ))
        ) : users.length === 0 ? (
          <Card>
            <CardContent className="p-4 text-center py-8 text-muted-foreground">
              {hasAnyFilter ? t('users.usersNotFound') : t('users.noUsers')}
            </CardContent>
          </Card>
        ) : (
          users.map((user, i) => (
            <div key={user.uuid} className="animate-fade-in-up" style={{ animationDelay: `${i * 0.04}s` }}>
              <MobileUserCard
                user={user}
                onNavigate={() => navigate(`/users/${user.uuid}`)}
                onEnable={() => enableUser.mutate(user.uuid)}
                onDisable={() => disableUser.mutate(user.uuid)}
                onDelete={() => setDeleteConfirmUuid(user.uuid)}
              />
            </div>
          ))
        )}
      </div>

      {/* Bulk action toolbar */}
      {selectedUuids.size > 0 && canBulk && (
        <div className="sticky bottom-4 z-30 mx-auto max-w-3xl animate-fade-in-up">
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-dark-400/20 bg-dark-700/95 backdrop-blur-xl shadow-deep">
            <span className="text-sm text-white font-medium">
              {t('users.bulkSelected', { count: selectedUuids.size })}
              {(() => {
                const visibleCount = users.filter((u) => selectedUuids.has(u.uuid)).length
                if (visibleCount < selectedUuids.size) {
                  return <span className="text-dark-300 text-xs ml-1.5">({t('users.bulkOnPage', { count: visibleCount })})</span>
                }
                return null
              })()}
            </span>
            <div className="flex-1" />
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkEnable.mutate([...selectedUuids])}
              disabled={bulkEnable.isPending || bulkDisable.isPending || bulkDelete.isPending}
              className="text-green-400 border-green-500/30 hover:bg-green-500/10 gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              {t('users.bulkEnable')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkDisable.mutate([...selectedUuids])}
              disabled={bulkEnable.isPending || bulkDisable.isPending || bulkDelete.isPending}
              className="text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10 gap-1.5"
            >
              <Ban className="w-3.5 h-3.5" />
              {t('users.bulkDisable')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkDelete.mutate([...selectedUuids])}
              disabled={bulkEnable.isPending || bulkDisable.isPending || bulkDelete.isPending}
              className="text-red-400 border-red-500/30 hover:bg-red-500/10 gap-1.5"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {t('users.bulkDelete')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={clearSelection}
              className="text-dark-300 gap-1.5"
            >
              <X className="w-3.5 h-3.5" />
              {t('users.cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Desktop: Users table with virtual scrolling for large page sizes */}
      <Card className="p-0 overflow-hidden hidden md:block animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <div
          ref={tableContainerRef}
          className="overflow-auto"
          style={useVirtual && !isLoading ? { maxHeight: '70vh' } : undefined}
        >
          <table className="table">
            <thead className={useVirtual ? 'sticky top-0 z-10 bg-dark-800' : undefined}>
              <tr>
                {canBulk && (
                  <th className="w-10 px-3">
                    <Checkbox
                      checked={users?.length > 0 && users.every((u) => selectedUuids.has(u.uuid))}
                      onCheckedChange={toggleSelectAll}
                    />
                  </th>
                )}
                <th><SortHeader label={t('users.table.user')} field="username" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.status')} field="status" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.traffic')} field="used_traffic_bytes" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.hwid')} field="hwid_device_limit" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.activity')} field="online_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.expires')} field="expire_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label={t('users.table.created')} field="created_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td><Skeleton className="h-4 w-32" /></td>
                    <td><Skeleton className="h-5 w-20" /></td>
                    <td><Skeleton className="h-4 w-24" /></td>
                    <td><Skeleton className="h-4 w-8 mx-auto" /></td>
                    <td><Skeleton className="h-4 w-20" /></td>
                    <td><Skeleton className="h-4 w-20" /></td>
                    <td><Skeleton className="h-4 w-20" /></td>
                    <td></td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-muted-foreground">
                    {hasAnyFilter ? t('users.usersNotFound') : t('users.noUsers')}
                  </td>
                </tr>
              ) : useVirtual ? (
                <>
                  {/* Virtual spacer top */}
                  {rowVirtualizer.getVirtualItems()[0]?.start > 0 && (
                    <tr><td colSpan={9} style={{ height: rowVirtualizer.getVirtualItems()[0].start, padding: 0 }} /></tr>
                  )}
                  {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                    const user = users[virtualRow.index]
                    return (
                      <tr
                        key={user.uuid}
                        data-index={virtualRow.index}
                        ref={rowVirtualizer.measureElement}
                        className="cursor-pointer hover:bg-dark-600/50"
                        onClick={() => navigate(`/users/${user.uuid}`)}
                      >
                        {canBulk && (
                          <td className="px-3" onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              checked={selectedUuids.has(user.uuid)}
                              onCheckedChange={() => toggleSelect(user.uuid)}
                            />
                          </td>
                        )}
                        <td>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-medium text-white">{user.username || user.short_uuid}</span>
                              {user.tag && (
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20">{user.tag}</span>
                              )}
                            </div>
                            {user.description && <p className="text-xs text-dark-300 truncate max-w-[200px]" title={user.description}>{user.description}</p>}
                            {user.email && <p className="text-xs text-dark-200">{user.email}</p>}
                          </div>
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <StatusBadge status={user.status} />
                        </td>
                        <td className="min-w-[140px]">
                          <TrafficBar used={user.used_traffic_bytes} limit={user.traffic_limit_bytes} />
                        </td>
                        <td className="text-center">
                          <span className="text-dark-100 text-sm">{user.hwid_device_count} / {user.hwid_device_limit || '\u221E'}</span>
                        </td>
                        <td><OnlineIndicator onlineAt={user.online_at} /></td>
                        <td className="text-dark-200 text-sm">{user.expire_at ? formatDateShort(user.expire_at) : '\u2014'}</td>
                        <td className="text-dark-200 text-sm">{user.created_at ? formatDateShort(user.created_at) : '\u2014'}</td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <UserActions
                            user={user}
                            onEnable={() => enableUser.mutate(user.uuid)}
                            onDisable={() => disableUser.mutate(user.uuid)}
                            onDelete={() => setDeleteConfirmUuid(user.uuid)}
                          />
                        </td>
                      </tr>
                    )
                  })}
                  {/* Virtual spacer bottom */}
                  {(() => {
                    const items = rowVirtualizer.getVirtualItems()
                    const lastItem = items[items.length - 1]
                    const bottomPad = lastItem ? rowVirtualizer.getTotalSize() - lastItem.end : 0
                    return bottomPad > 0 ? <tr><td colSpan={9} style={{ height: bottomPad, padding: 0 }} /></tr> : null
                  })()}
                </>
              ) : (
                users.map((user) => (
                  <tr
                    key={user.uuid}
                    className="cursor-pointer hover:bg-dark-600/50"
                    onClick={() => navigate(`/users/${user.uuid}`)}
                  >
                    {canBulk && (
                      <td className="px-3" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selectedUuids.has(user.uuid)}
                          onCheckedChange={() => toggleSelect(user.uuid)}
                        />
                      </td>
                    )}
                    <td>
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-white">{user.username || user.short_uuid}</span>
                          {user.tag && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-300 border border-primary-500/20">{user.tag}</span>
                          )}
                        </div>
                        {user.description && <p className="text-xs text-dark-300 truncate max-w-[200px]" title={user.description}>{user.description}</p>}
                        {user.email && <p className="text-xs text-dark-200">{user.email}</p>}
                      </div>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <StatusBadge status={user.status} />
                    </td>
                    <td className="min-w-[140px]">
                      <TrafficBar used={user.used_traffic_bytes} limit={user.traffic_limit_bytes} />
                    </td>
                    <td className="text-center">
                      <span className="text-dark-100 text-sm">{user.hwid_device_count} / {user.hwid_device_limit || '\u221E'}</span>
                    </td>
                    <td><OnlineIndicator onlineAt={user.online_at} /></td>
                    <td className="text-dark-200 text-sm">{user.expire_at ? formatDateShort(user.expire_at) : '\u2014'}</td>
                    <td className="text-dark-200 text-sm">{user.created_at ? formatDateShort(user.created_at) : '\u2014'}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <UserActions
                        user={user}
                        onEnable={() => enableUser.mutate(user.uuid)}
                        onDisable={() => disableUser.mutate(user.uuid)}
                        onDelete={() => setDeleteConfirmUuid(user.uuid)}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Pagination */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 animate-fade-in" style={{ animationDelay: '0.15s' }}>
        <p className="text-sm text-muted-foreground order-2 sm:order-1">
          {total > 0 ? (
            <>{t('users.showing', { from: (page - 1) * perPage + 1, to: Math.min(page * perPage, total), total: formatNumber(total) })}</>
          ) : (
            t('users.noData')
          )}
        </p>
        <div className="flex items-center gap-2 order-1 sm:order-2">
          <Button variant="secondary" size="icon" onClick={() => setPage(page - 1)} disabled={page <= 1}>
            <ChevronLeft className="w-5 h-5" />
          </Button>
          <span className="text-sm text-muted-foreground min-w-[80px] text-center">{page} / {pages}</span>
          <Button variant="secondary" size="icon" onClick={() => setPage(page + 1)} disabled={page >= pages}>
            <ChevronRight className="w-5 h-5" />
          </Button>
        </div>
      </div>

      {/* Create user modal */}
      <CreateUserModal
        open={showCreateModal}
        onClose={() => { setShowCreateModal(false); setCreateError('') }}
        onSave={(data) => createUser.mutate(data)}
        isPending={createUser.isPending}
        error={createError}
      />

      <ConfirmDialog
        open={deleteConfirmUuid !== null}
        onOpenChange={(open) => { if (!open) setDeleteConfirmUuid(null) }}
        title={t('users.deleteConfirm.title')}
        description={t('users.deleteConfirm.description')}
        confirmLabel={t('users.deleteConfirm.confirm')}
        variant="destructive"
        onConfirm={() => {
          if (deleteConfirmUuid) {
            deleteUser.mutate(deleteConfirmUuid)
            setDeleteConfirmUuid(null)
          }
        }}
      />
    </div>
  )
}

// Filter chip component
const FilterChip = memo(function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-primary-500/10 border border-primary-500/20 text-[11px] text-primary-300">
      {label}
      <button onClick={onRemove} className="hover:text-white ml-0.5">
        <X className="w-3 h-3" />
      </button>
    </span>
  )
})
