import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
  status: string
  expire_at: string | null
  traffic_limit_bytes: number | null
  used_traffic_bytes: number
  lifetime_used_traffic_bytes: number
  hwid_device_limit: number
  hwid_device_count: number
  created_at: string | null
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

// Utility functions
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  return date.toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return 'Только что'
  if (diffMin < 60) return `${diffMin} мин назад`
  if (diffHours < 24) return `${diffHours} ч назад`
  if (diffDays < 7) return `${diffDays} дн назад`
  return formatDate(dateStr)
}

function getTrafficPercent(used: number, limit: number | null): number {
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const normalizedStatus = status.toLowerCase()
  const statusConfig: Record<string, { label: string; variant: 'success' | 'destructive' | 'warning' | 'secondary' }> = {
    active: { label: 'Активен', variant: 'success' },
    disabled: { label: 'Отключён', variant: 'destructive' },
    limited: { label: 'Ограничен', variant: 'warning' },
    expired: { label: 'Истёк', variant: 'secondary' },
  }

  const config = statusConfig[normalizedStatus] || { label: status, variant: 'secondary' as const }

  return <Badge variant={config.variant}>{config.label}</Badge>
}

// Traffic bar component
function TrafficBar({ used, limit }: { used: number; limit: number | null }) {
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
          {formatBytes(used)} / {isUnlimited ? '∞' : formatBytes(limit)}
        </span>
      </div>
    </div>
  )
}

// Online indicator
function OnlineIndicator({ onlineAt }: { onlineAt: string | null }) {
  if (!onlineAt) return <span className="text-dark-300 text-xs">Нет данных</span>

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
      <span className="text-dark-200 text-xs">{formatRelativeDate(onlineAt)}</span>
    </div>
  )
}

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
          <Eye className="w-4 h-4 mr-2" /> Просмотр
        </DropdownMenuItem>
        {canEdit && (
          <DropdownMenuItem onClick={() => navigate(`/users/${user.uuid}?edit=1`)}>
            <Pencil className="w-4 h-4 mr-2" /> Редактировать
          </DropdownMenuItem>
        )}
        {(canEdit || canDelete) && <DropdownMenuSeparator />}
        {canEdit && (
          user.status === 'disabled' ? (
            <DropdownMenuItem onClick={onEnable} className="text-green-400 focus:text-green-400">
              <Check className="w-4 h-4 mr-2" /> Включить
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={onDisable} className="text-yellow-400 focus:text-yellow-400">
              <Ban className="w-4 h-4 mr-2" /> Отключить
            </DropdownMenuItem>
          )
        )}
        {canDelete && (
          <DropdownMenuItem
            onClick={onDelete}
            className="text-red-400 focus:text-red-400"
          >
            <Trash2 className="w-4 h-4 mr-2" /> Удалить
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Sortable header
function SortHeader({
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
}

// Mobile user card
function MobileUserCard({
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
  return (
    <Card
      className="cursor-pointer active:bg-dark-700/50"
      onClick={onNavigate}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="min-w-0 flex-1">
            <p className="font-medium text-white truncate">
              {user.username || user.short_uuid}
            </p>
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
            <span title="HWID устройства">{user.hwid_device_count} / {user.hwid_device_limit || '∞'}</span>
            <span>Истекает: {formatDate(user.expire_at)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

interface Squad {
  uuid: string
  squadTag: string
  squadName?: string
}

interface CreateUserFormData {
  username: string
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
  const [form, setForm] = useState<CreateUserFormData>({
    username: '',
    telegram_id: '',
    description: '',
    traffic_limit_gb: '',
    is_unlimited: true,
    traffic_limit_strategy: 'MONTH',
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
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Создание пользователя</DialogTitle>
          <DialogDescription>Заполните данные для нового пользователя</DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label>Имя пользователя</Label>
            <Input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              placeholder="username"
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>Telegram ID</Label>
            <Input
              type="number"
              value={form.telegram_id}
              onChange={(e) => setForm({ ...form, telegram_id: e.target.value })}
              placeholder="123456789"
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>Описание</Label>
            <Input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Имя, email, заметки..."
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>Лимит трафика</Label>
            <div className="flex items-center gap-3 mt-1.5 mb-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_unlimited}
                  onChange={(e) => setForm({
                    ...form,
                    is_unlimited: e.target.checked,
                    traffic_limit_gb: e.target.checked ? '' : form.traffic_limit_gb,
                  })}
                  className="w-4 h-4 rounded border-dark-400/30 bg-dark-800 text-primary-500 focus:ring-primary-500/50"
                />
                <span className="text-sm text-dark-100">Безлимитный</span>
              </label>
            </div>
            {!form.is_unlimited && (
              <>
                <div className="relative">
                  <Input
                    type="number"
                    step="0.1"
                    min="0"
                    value={form.traffic_limit_gb}
                    onChange={(e) => setForm({ ...form, traffic_limit_gb: e.target.value })}
                    placeholder="Введите лимит"
                    className="pr-12"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-dark-200">ГБ</span>
                </div>
                <div className="mt-2">
                  <Label className="text-xs text-dark-300">Стратегия сброса</Label>
                  <select
                    value={form.traffic_limit_strategy}
                    onChange={(e) => setForm({ ...form, traffic_limit_strategy: e.target.value })}
                    className="mt-1 w-full rounded-md border border-dark-400/30 bg-dark-800 text-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    <option value="MONTH">Ежемесячный</option>
                    <option value="WEEK">Еженедельный</option>
                    <option value="DAY">Ежедневный</option>
                    <option value="NO_RESET">Без сброса</option>
                  </select>
                </div>
              </>
            )}
          </div>

          <div>
            <Label>Дата истечения</Label>
            <Input
              type="datetime-local"
              value={form.expire_at}
              onChange={(e) => setForm({ ...form, expire_at: e.target.value })}
              className="mt-1.5"
            />
            <p className="text-xs text-dark-300 mt-1">Оставьте пустым для бессрочной подписки</p>
          </div>

          <div>
            <Label>Лимит устройств (HWID)</Label>
            <Input
              type="number"
              min="0"
              value={form.hwid_device_limit}
              onChange={(e) => setForm({ ...form, hwid_device_limit: e.target.value })}
              className="mt-1.5"
            />
          </div>

          {/* External squad */}
          {externalSquads.length > 0 && (
            <div>
              <Label>Внешний сквад</Label>
              <select
                value={form.external_squad_uuid}
                onChange={(e) => setForm({ ...form, external_squad_uuid: e.target.value })}
                className="mt-1.5 w-full rounded-md border border-dark-400/30 bg-dark-800 text-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              >
                <option value="">Не выбран</option>
                {externalSquads.map((sq: Squad) => (
                  <option key={sq.uuid} value={sq.uuid}>
                    {sq.squadName || sq.squadTag || sq.uuid}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Internal squads */}
          {internalSquads.length > 0 && (
            <div>
              <Label>Внутренние сквады</Label>
              <div className="mt-1.5 space-y-1.5 max-h-32 overflow-y-auto">
                {internalSquads.map((sq: Squad) => (
                  <label key={sq.uuid} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.active_internal_squads.includes(sq.uuid)}
                      onChange={() => toggleInternalSquad(sq.uuid)}
                      className="w-4 h-4 rounded border-dark-400/30 bg-dark-800 text-primary-500 focus:ring-primary-500/50"
                    />
                    <span className="text-sm text-dark-100">
                      {sq.squadName || sq.squadTag || sq.uuid}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? 'Создание...' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function Users() {
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

  const activeFilterCount = [status, trafficType, expireFilter, onlineFilter, trafficUsage].filter(Boolean).length

  // Export handlers
  const handleExportCSV = () => {
    const items = data?.items
    if (!items?.length) return
    const exportData = items.map((u: any) => ({
      username: u.username || '',
      status: u.status,
      email: u.email || '',
      telegram_id: u.telegram_id || '',
      traffic_used: formatBytesForExport(u.used_traffic_bytes),
      traffic_limit: u.traffic_limit_bytes ? formatBytesForExport(u.traffic_limit_bytes) : 'Безлимит',
      hwid_count: u.hwid_device_count ?? 0,
      hwid_limit: u.hwid_device_limit ?? 0,
      online_at: u.online_at || '',
      expire_at: u.expire_at || '',
      created_at: u.created_at || '',
    }))
    exportCSV(exportData, `users-${new Date().toISOString().slice(0, 10)}`)
    toast.success('Экспорт CSV завершён')
  }
  const handleExportJSON = () => {
    const items = data?.items
    if (!items?.length) return
    exportJSON(items, `users-${new Date().toISOString().slice(0, 10)}`)
    toast.success('Экспорт JSON завершён')
  }

  // Saved filters
  const currentFilters: Record<string, unknown> = {
    ...(status && { status }),
    ...(trafficType && { trafficType }),
    ...(expireFilter && { expireFilter }),
    ...(onlineFilter && { onlineFilter }),
    ...(trafficUsage && { trafficUsage }),
  }
  const hasActiveFilters = activeFilterCount > 0
  const handleLoadFilter = (filters: Record<string, unknown>) => {
    setStatus((filters.status as string) || '')
    setTrafficType((filters.trafficType as string) || '')
    setExpireFilter((filters.expireFilter as string) || '')
    setOnlineFilter((filters.onlineFilter as string) || '')
    setTrafficUsage((filters.trafficUsage as string) || '')
    setShowFilters(true)
    setPage(1)
  }

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
      toast.success('Пользователь включён')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка включения')
    },
  })

  const disableUser = useMutation({
    mutationFn: (uuid: string) => client.post(`/users/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Пользователь отключён')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка отключения')
    },
  })

  const deleteUser = useMutation({
    mutationFn: (uuid: string) => client.delete(`/users/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success('Пользователь удалён')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка удаления')
    },
  })

  const createUser = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/users', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateModal(false)
      setCreateError('')
      toast.success('Пользователь создан')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || 'Ошибка создания')
      toast.error(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
  })

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
    setPage(1)
  }

  const resetFilters = () => {
    setSearch('')
    setStatus('')
    setTrafficType('')
    setExpireFilter('')
    setOnlineFilter('')
    setTrafficUsage('')
    setPage(1)
  }

  // Selection helpers
  const toggleSelect = (uuid: string) => {
    setSelectedUuids(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }
  const toggleSelectAll = () => {
    if (!users) return
    const pageUuids = users.map((u: any) => u.uuid)
    const allSelected = pageUuids.every((id: string) => selectedUuids.has(id))
    if (allSelected) {
      setSelectedUuids(prev => {
        const next = new Set(prev)
        pageUuids.forEach((id: string) => next.delete(id))
        return next
      })
    } else {
      setSelectedUuids(prev => {
        const next = new Set(prev)
        pageUuids.forEach((id: string) => next.add(id))
        return next
      })
    }
  }
  const clearSelection = () => setSelectedUuids(new Set())

  // Bulk mutations
  const bulkEnable = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/enable', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(`Включено: ${d.success}${d.failed ? `, ошибок: ${d.failed}` : ''}`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const bulkDisable = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/disable', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(`Отключено: ${d.success}${d.failed ? `, ошибок: ${d.failed}` : ''}`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const bulkDelete = useMutation({
    mutationFn: (uuids: string[]) => client.post('/users/bulk/delete', { uuids }),
    onSuccess: (res) => {
      const d = res.data
      toast.success(`Удалено: ${d.success}${d.failed ? `, ошибок: ${d.failed}` : ''}`)
      queryClient.invalidateQueries({ queryKey: ['users'] })
      clearSelection()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const hasAnyFilter = activeFilterCount > 0 || debouncedSearch

  const users = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Пользователи</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">
            Управление пользователями и подписками
          </p>
        </div>
        {canCreate && (
          <Button
            onClick={() => { setShowCreateModal(true); setCreateError('') }}
            className="self-start sm:self-auto"
          >
            <Plus className="w-4 h-4 mr-2" />
            <span className="hidden sm:inline">Создать пользователя</span>
            <span className="sm:hidden">Создать</span>
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
                placeholder="Поиск по имени, email, UUID, Telegram ID..."
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
                Фильтры
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
                  title={sortOrder === 'desc' ? 'По убыванию' : 'По возрастанию'}
                >
                  {sortOrder === 'desc' ? (
                    <ArrowDown className="w-5 h-5 text-primary-400" />
                  ) : (
                    <ArrowUp className="w-5 h-5 text-primary-400" />
                  )}
                </Button>

                <div className="relative flex-1 sm:flex-none sm:w-48">
                  <select
                    value={sortBy}
                    onChange={(e) => { setSortBy(e.target.value); setPage(1) }}
                    className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 appearance-none pr-8 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    <option value="created_at">Дата создания</option>
                    <option value="used_traffic_bytes">Трафик (текущий)</option>
                    <option value="lifetime_used_traffic_bytes">Трафик (за всё время)</option>
                    <option value="hwid_device_limit">Устройства (HWID)</option>
                    <option value="online_at">Последняя активность</option>
                    <option value="expire_at">Дата истечения</option>
                    <option value="traffic_limit_bytes">Лимит трафика</option>
                    <option value="username">Имя</option>
                    <option value="status">Статус</option>
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300 pointer-events-none" />
                </div>
              </div>

              <Button
                variant="secondary"
                size="icon"
                onClick={() => refetch()}
                disabled={isLoading}
                title="Обновить"
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
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">Статус</Label>
                    <select
                      value={status}
                      onChange={(e) => { setStatus(e.target.value); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value="">Все статусы</option>
                      <option value="active">Активные</option>
                      <option value="disabled">Отключённые</option>
                      <option value="limited">Ограниченные</option>
                      <option value="expired">Истёкшие</option>
                    </select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">Тип трафика</Label>
                    <select
                      value={trafficType}
                      onChange={(e) => { setTrafficType(e.target.value); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value="">Любой</option>
                      <option value="unlimited">Безлимитные</option>
                      <option value="limited">С лимитом</option>
                    </select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">Расход трафика</Label>
                    <select
                      value={trafficUsage}
                      onChange={(e) => { setTrafficUsage(e.target.value); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value="">Любой расход</option>
                      <option value="above_90">Более 90% лимита</option>
                      <option value="above_70">Более 70% лимита</option>
                      <option value="above_50">Более 50% лимита</option>
                      <option value="zero">Без трафика (0)</option>
                    </select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">Срок действия</Label>
                    <select
                      value={expireFilter}
                      onChange={(e) => { setExpireFilter(e.target.value); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value="">Любой срок</option>
                      <option value="expiring_7d">Истекает за 7 дней</option>
                      <option value="expiring_30d">Истекает за 30 дней</option>
                      <option value="expired">Уже истёк</option>
                      <option value="no_expiry">Бессрочные</option>
                    </select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">Активность</Label>
                    <select
                      value={onlineFilter}
                      onChange={(e) => { setOnlineFilter(e.target.value); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value="">Любая активность</option>
                      <option value="online_24h">Были онлайн за 24ч</option>
                      <option value="online_7d">Были онлайн за 7 дней</option>
                      <option value="online_30d">Были онлайн за 30 дней</option>
                      <option value="never">Никогда не подключались</option>
                    </select>
                  </div>

                  <div>
                    <Label className="text-[11px] uppercase tracking-wider text-dark-300">На странице</Label>
                    <select
                      value={perPage}
                      onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }}
                      className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1"
                    >
                      <option value={10}>10</option>
                      <option value={20}>20</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                    </select>
                  </div>
                </div>

                {hasAnyFilter && (
                  <div className="flex items-center justify-between pt-2">
                    <p className="text-xs text-dark-300">
                      Найдено: <span className="text-white font-medium">{total.toLocaleString()}</span> пользователей
                    </p>
                    <button
                      onClick={resetFilters}
                      className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                    >
                      <X className="w-3 h-3" />
                      Сбросить все фильтры
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
                    label={`Статус: ${({ active: 'Активные', disabled: 'Отключённые', limited: 'Ограниченные', expired: 'Истёкшие' } as Record<string, string>)[status] || status}`}
                    onRemove={() => { setStatus(''); setPage(1) }}
                  />
                )}
                {trafficType && (
                  <FilterChip
                    label={`Трафик: ${trafficType === 'unlimited' ? 'Безлимит' : 'С лимитом'}`}
                    onRemove={() => { setTrafficType(''); setPage(1) }}
                  />
                )}
                {trafficUsage && (
                  <FilterChip
                    label={`Расход: ${({ above_90: '>90%', above_70: '>70%', above_50: '>50%', zero: '0' } as Record<string, string>)[trafficUsage] || trafficUsage}`}
                    onRemove={() => { setTrafficUsage(''); setPage(1) }}
                  />
                )}
                {expireFilter && (
                  <FilterChip
                    label={`Срок: ${({ expiring_7d: '7 дней', expiring_30d: '30 дней', expired: 'Истёк', no_expiry: 'Бессрочные' } as Record<string, string>)[expireFilter] || expireFilter}`}
                    onRemove={() => { setExpireFilter(''); setPage(1) }}
                  />
                )}
                {onlineFilter && (
                  <FilterChip
                    label={`Онлайн: ${({ online_24h: '24ч', online_7d: '7д', online_30d: '30д', never: 'Никогда' } as Record<string, string>)[onlineFilter] || onlineFilter}`}
                    onRemove={() => { setOnlineFilter(''); setPage(1) }}
                  />
                )}
                <button onClick={resetFilters} className="text-[11px] text-dark-300 hover:text-primary-400 ml-1">
                  Сбросить все
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
                Ошибка загрузки пользователей: {(error as Error)?.message || 'Неизвестная ошибка'}
              </p>
              <Button variant="secondary" size="sm" onClick={() => refetch()}>
                Повторить
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
              {hasAnyFilter ? 'Пользователи не найдены' : 'Нет пользователей'}
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
              Выбрано: {selectedUuids.size}
              {(() => {
                const visibleCount = users.filter((u) => selectedUuids.has(u.uuid)).length
                if (visibleCount < selectedUuids.size) {
                  return <span className="text-dark-300 text-xs ml-1.5">(на странице: {visibleCount})</span>
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
              className="text-green-400 border-green-500/30 hover:bg-green-500/10"
            >
              Включить
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkDisable.mutate([...selectedUuids])}
              disabled={bulkEnable.isPending || bulkDisable.isPending || bulkDelete.isPending}
              className="text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10"
            >
              Отключить
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => bulkDelete.mutate([...selectedUuids])}
              disabled={bulkEnable.isPending || bulkDisable.isPending || bulkDelete.isPending}
              className="text-red-400 border-red-500/30 hover:bg-red-500/10"
            >
              Удалить
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={clearSelection}
              className="text-dark-300"
            >
              Отмена
            </Button>
          </div>
        </div>
      )}

      {/* Desktop: Users table */}
      <Card className="p-0 overflow-hidden hidden md:block animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                {canBulk && (
                  <th className="w-10 px-3">
                    <Checkbox
                      checked={users?.length > 0 && users.every((u: any) => selectedUuids.has(u.uuid))}
                      onCheckedChange={toggleSelectAll}
                    />
                  </th>
                )}
                <th><SortHeader label="Пользователь" field="username" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="Статус" field="status" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="Трафик" field="used_traffic_bytes" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="HWID" field="hwid_device_limit" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="Активность" field="online_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="Истекает" field="expire_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
                <th><SortHeader label="Создан" field="created_at" currentSort={sortBy} currentOrder={sortOrder} onSort={handleSort} /></th>
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
                    {hasAnyFilter ? 'Пользователи не найдены' : 'Нет пользователей'}
                  </td>
                </tr>
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
                        <span className="font-medium text-white">{user.username || user.short_uuid}</span>
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
                      <span className="text-dark-100 text-sm">{user.hwid_device_count} / {user.hwid_device_limit || '∞'}</span>
                    </td>
                    <td><OnlineIndicator onlineAt={user.online_at} /></td>
                    <td className="text-dark-200 text-sm">{formatDate(user.expire_at)}</td>
                    <td className="text-dark-200 text-sm">{formatDate(user.created_at)}</td>
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
            <>Показано {(page - 1) * perPage + 1}-{Math.min(page * perPage, total)} из {total.toLocaleString()}</>
          ) : (
            'Нет данных'
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
        title="Удалить пользователя?"
        description="Это действие нельзя отменить. Пользователь и все его данные будут удалены."
        confirmLabel="Удалить"
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
function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-primary-500/10 border border-primary-500/20 text-[11px] text-primary-300">
      {label}
      <button onClick={onRemove} className="hover:text-white ml-0.5">
        <X className="w-3 h-3" />
      </button>
    </span>
  )
}
