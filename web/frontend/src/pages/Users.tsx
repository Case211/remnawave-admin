import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  HiSearch,
  HiRefresh,
  HiChevronLeft,
  HiChevronRight,
  HiDotsVertical,
  HiEye,
  HiPencil,
  HiTrash,
  HiCheck,
  HiBan,
  HiSortAscending,
  HiSortDescending,
  HiFilter,
  HiX,
  HiChevronDown,
  HiChevronUp,
  HiPlus,
} from 'react-icons/hi'
import client from '../api/client'

// Types
interface UserListItem {
  uuid: string
  short_uuid: string
  username: string | null
  email: string | null
  status: string
  expire_at: string | null
  traffic_limit_bytes: number | null
  used_traffic_bytes: number
  hwid_device_limit: number
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
  const statusConfig: Record<string, { label: string; class: string }> = {
    active: { label: 'Активен', class: 'badge-success' },
    disabled: { label: 'Отключён', class: 'badge-danger' },
    limited: { label: 'Ограничен', class: 'badge-warning' },
    expired: { label: 'Истёк', class: 'badge-gray' },
  }

  const config = statusConfig[normalizedStatus] || { label: status, class: 'badge-gray' }

  return <span className={config.class}>{config.label}</span>
}

// Traffic bar component
function TrafficBar({ used, limit }: { used: number; limit: number | null }) {
  const percent = getTrafficPercent(used, limit)
  const colorClass =
    percent >= 90 ? 'bg-red-500' : percent >= 70 ? 'bg-yellow-500' : 'bg-green-500'
  const isUnlimited = !limit

  return (
    <div className="space-y-1">
      {isUnlimited ? (
        /* Unlimited: solid gradient bar with centered text */
        <div className="relative h-5 rounded-full overflow-hidden bg-gradient-to-r from-primary-600/30 to-cyan-600/30 border border-primary-500/20">
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-[11px] font-medium text-primary-200">
              {formatBytes(used)} / ∞
            </span>
          </div>
        </div>
      ) : (
        /* Limited: standard progress bar */
        <>
          <div className="flex items-center justify-between text-xs">
            <span className="text-dark-100">{formatBytes(used)}</span>
            <span className="text-dark-200">/ {formatBytes(limit)}</span>
          </div>
          <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
            <div
              className={`h-full ${colorClass} transition-all`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </>
      )}
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
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="btn-ghost p-1.5 rounded"
      >
        <HiDotsVertical className="w-4 h-4" />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          <div className="dropdown-menu w-40">
            <button
              onClick={() => {
                navigate(`/users/${user.uuid}`)
                setOpen(false)
              }}
              className="w-full px-3 py-2 text-left text-sm text-dark-100 hover:bg-dark-600 flex items-center gap-2"
            >
              <HiEye className="w-4 h-4" /> Просмотр
            </button>
            <button
              onClick={() => {
                navigate(`/users/${user.uuid}?edit=1`)
                setOpen(false)
              }}
              className="w-full px-3 py-2 text-left text-sm text-dark-100 hover:bg-dark-600 flex items-center gap-2"
            >
              <HiPencil className="w-4 h-4" /> Редактировать
            </button>
            <div className="border-t border-dark-400/20 my-1" />
            {user.status === 'disabled' ? (
              <button
                onClick={() => {
                  onEnable()
                  setOpen(false)
                }}
                className="w-full px-3 py-2 text-left text-sm text-green-400 hover:bg-dark-600 flex items-center gap-2"
              >
                <HiCheck className="w-4 h-4" /> Включить
              </button>
            ) : (
              <button
                onClick={() => {
                  onDisable()
                  setOpen(false)
                }}
                className="w-full px-3 py-2 text-left text-sm text-yellow-400 hover:bg-dark-600 flex items-center gap-2"
              >
                <HiBan className="w-4 h-4" /> Отключить
              </button>
            )}
            <button
              onClick={() => {
                if (confirm('Удалить пользователя?')) {
                  onDelete()
                }
                setOpen(false)
              }}
              className="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-dark-600 flex items-center gap-2"
            >
              <HiTrash className="w-4 h-4" /> Удалить
            </button>
          </div>
        </>
      )}
    </div>
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
  const Icon = isActive && currentOrder === 'asc' ? HiSortAscending : HiSortDescending

  return (
    <button
      onClick={() => onSort(field)}
      className={`flex items-center gap-1 hover:text-white transition-all duration-200 ${
        isActive ? 'text-primary-400' : ''
      }`}
    >
      {label}
      {isActive && <Icon className="w-4 h-4" />}
    </button>
  )
}

// Mobile user card component
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
    <div
      className="card cursor-pointer active:bg-dark-700/50"
      onClick={onNavigate}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-white truncate">
            {user.username || user.short_uuid}
          </p>
          {user.email && (
            <p className="text-xs text-dark-200 truncate">{user.email}</p>
          )}
        </div>
        <div className="flex items-center gap-2 ml-2" onClick={(e) => e.stopPropagation()}>
          <StatusBadge status={user.status} />
          <UserActions
            user={user}
            onEnable={onEnable}
            onDisable={onDisable}
            onDelete={onDelete}
          />
        </div>
      </div>
      <div className="mb-3">
        <TrafficBar
          used={user.used_traffic_bytes}
          limit={user.traffic_limit_bytes}
        />
      </div>
      <div className="flex items-center justify-between text-xs text-dark-200">
        <OnlineIndicator onlineAt={user.online_at} />
        <span>Истекает: {formatDate(user.expire_at)}</span>
      </div>
    </div>
  )
}

interface CreateUserFormData {
  username: string
  email: string
  traffic_limit_gb: string
  is_unlimited: boolean
  expire_at: string
  hwid_device_limit: string
}

function CreateUserModal({
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
  const [form, setForm] = useState<CreateUserFormData>({
    username: '',
    email: '',
    traffic_limit_gb: '',
    is_unlimited: true,
    expire_at: '',
    hwid_device_limit: '0',
  })

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {}
    if (form.username.trim()) createData.username = form.username.trim()
    if (form.email.trim()) createData.email = form.email.trim()

    if (!form.is_unlimited && form.traffic_limit_gb) {
      const val = parseFloat(form.traffic_limit_gb)
      if (!isNaN(val) && val > 0) {
        createData.traffic_limit_bytes = Math.round(val * 1024 * 1024 * 1024)
      }
    } else {
      createData.traffic_limit_bytes = null
    }

    if (form.expire_at) {
      createData.expire_at = new Date(form.expire_at).toISOString()
    }

    const hwid = parseInt(form.hwid_device_limit, 10)
    if (!isNaN(hwid)) {
      createData.hwid_device_limit = hwid
    }

    onSave(createData)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md card border border-dark-400/20 animate-scale-in max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Создание пользователя</h2>
          <button onClick={onClose} className="btn-ghost p-1.5 rounded">
            <HiX className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Имя пользователя</label>
            <input
              type="text"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="input"
              placeholder="username"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="input"
              placeholder="user@example.com"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Лимит трафика</label>
            <div className="flex items-center gap-3 mb-2">
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
              <div className="relative">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={form.traffic_limit_gb}
                  onChange={(e) => setForm({ ...form, traffic_limit_gb: e.target.value })}
                  placeholder="Введите лимит"
                  className="input pr-12"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-dark-200">ГБ</span>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Дата истечения</label>
            <input
              type="datetime-local"
              value={form.expire_at}
              onChange={(e) => setForm({ ...form, expire_at: e.target.value })}
              className="input"
            />
            <p className="text-xs text-dark-300 mt-1">Оставьте пустым для бессрочной подписки</p>
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Лимит устройств (HWID)</label>
            <input
              type="number"
              min="0"
              value={form.hwid_device_limit}
              onChange={(e) => setForm({ ...form, hwid_device_limit: e.target.value })}
              className="input"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={isPending}
            className="btn-secondary px-4 py-2"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={isPending}
            className="btn-primary px-4 py-2"
          >
            {isPending ? 'Создание...' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Users() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')

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

  // Count active filters (excluding search)
  const activeFilterCount = [status, trafficType, expireFilter, onlineFilter, trafficUsage].filter(Boolean).length

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
    },
  })

  const disableUser = useMutation({
    mutationFn: (uuid: string) => client.post(`/users/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const deleteUser = useMutation({
    mutationFn: (uuid: string) => client.delete(`/users/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const createUser = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/users', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowCreateModal(false)
      setCreateError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
  })

  // Handle sort
  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
    setPage(1)
  }

  // Reset all filters
  const resetFilters = () => {
    setSearch('')
    setStatus('')
    setTrafficType('')
    setExpireFilter('')
    setOnlineFilter('')
    setTrafficUsage('')
    setPage(1)
  }

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
          <p className="text-dark-200 mt-1 text-sm md:text-base">
            Управление пользователями и подписками
          </p>
        </div>
        <button
          onClick={() => { setShowCreateModal(true); setCreateError('') }}
          className="btn-primary flex items-center gap-2 self-start sm:self-auto"
        >
          <HiPlus className="w-4 h-4" />
          <span className="hidden sm:inline">Создать пользователя</span>
          <span className="sm:hidden">Создать</span>
        </button>
      </div>

      {/* Search + Filter toggle */}
      <div className="card">
        <div className="flex flex-col gap-3">
          {/* Row 1: Search + filter toggle + refresh */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 relative">
              <HiSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-200" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по имени, email, UUID, Telegram ID..."
                className="input pl-10"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`btn-secondary flex items-center gap-2 flex-1 sm:flex-none ${
                  activeFilterCount > 0 ? 'border-primary-500/50 text-primary-400' : ''
                }`}
              >
                <HiFilter className="w-4 h-4" />
                <span className="sm:inline">Фильтры</span>
                {activeFilterCount > 0 && (
                  <span className="bg-primary-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                    {activeFilterCount}
                  </span>
                )}
                {showFilters ? <HiChevronUp className="w-4 h-4" /> : <HiChevronDown className="w-4 h-4" />}
              </button>
              <button
                onClick={() => refetch()}
                className="btn-secondary flex-shrink-0"
                disabled={isLoading}
              >
                <HiRefresh className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Row 2: Expandable filters */}
          {showFilters && (
            <div className="pt-3 border-t border-dark-400/20 space-y-3 animate-fade-in">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {/* Status */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">Статус</label>
                  <select
                    value={status}
                    onChange={(e) => { setStatus(e.target.value); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value="">Все статусы</option>
                    <option value="active">Активные</option>
                    <option value="disabled">Отключённые</option>
                    <option value="limited">Ограниченные</option>
                    <option value="expired">Истёкшие</option>
                  </select>
                </div>

                {/* Traffic type */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">Тип трафика</label>
                  <select
                    value={trafficType}
                    onChange={(e) => { setTrafficType(e.target.value); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value="">Любой</option>
                    <option value="unlimited">Безлимитные</option>
                    <option value="limited">С лимитом</option>
                  </select>
                </div>

                {/* Traffic usage */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">Расход трафика</label>
                  <select
                    value={trafficUsage}
                    onChange={(e) => { setTrafficUsage(e.target.value); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value="">Любой расход</option>
                    <option value="above_90">Более 90% лимита</option>
                    <option value="above_70">Более 70% лимита</option>
                    <option value="above_50">Более 50% лимита</option>
                    <option value="zero">Без трафика (0)</option>
                  </select>
                </div>

                {/* Expiration */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">Срок действия</label>
                  <select
                    value={expireFilter}
                    onChange={(e) => { setExpireFilter(e.target.value); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value="">Любой срок</option>
                    <option value="expiring_7d">Истекает за 7 дней</option>
                    <option value="expiring_30d">Истекает за 30 дней</option>
                    <option value="expired">Уже истёк</option>
                    <option value="no_expiry">Бессрочные</option>
                  </select>
                </div>

                {/* Online status */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">Активность</label>
                  <select
                    value={onlineFilter}
                    onChange={(e) => { setOnlineFilter(e.target.value); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value="">Любая активность</option>
                    <option value="online_24h">Были онлайн за 24ч</option>
                    <option value="online_7d">Были онлайн за 7 дней</option>
                    <option value="online_30d">Были онлайн за 30 дней</option>
                    <option value="never">Никогда не подключались</option>
                  </select>
                </div>

                {/* Per page */}
                <div>
                  <label className="block text-[11px] text-dark-300 uppercase tracking-wider mb-1">На странице</label>
                  <select
                    value={perPage}
                    onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }}
                    className="input text-sm"
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                </div>
              </div>

              {/* Reset button */}
              {hasAnyFilter && (
                <div className="flex items-center justify-between pt-2">
                  <p className="text-xs text-dark-300">
                    Найдено: <span className="text-white font-medium">{total.toLocaleString()}</span> пользователей
                  </p>
                  <button
                    onClick={resetFilters}
                    className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                  >
                    <HiX className="w-3 h-3" />
                    Сбросить все фильтры
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Active filters chips (when panel is collapsed) */}
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
              <button
                onClick={resetFilters}
                className="text-[11px] text-dark-300 hover:text-primary-400 ml-1"
              >
                Сбросить все
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="card border border-red-500/30 bg-red-500/10">
          <div className="flex items-center justify-between">
            <p className="text-red-400 text-sm">
              Ошибка загрузки пользователей: {(error as Error)?.message || 'Неизвестная ошибка'}
            </p>
            <button onClick={() => refetch()} className="btn-secondary text-sm">
              Повторить
            </button>
          </div>
        </div>
      )}

      {/* Mobile: User cards */}
      <div className="md:hidden space-y-3">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card animate-fade-in">
              <div className="flex items-center justify-between mb-3">
                <div className="h-4 w-32 bg-dark-700 rounded" />
                <div className="h-5 w-20 bg-dark-700 rounded" />
              </div>
              <div className="h-4 w-full bg-dark-700 rounded mb-3" />
              <div className="flex justify-between">
                <div className="h-3 w-24 bg-dark-700 rounded" />
                <div className="h-3 w-24 bg-dark-700 rounded" />
              </div>
            </div>
          ))
        ) : users.length === 0 ? (
          <div className="card text-center py-8 text-dark-200">
            {hasAnyFilter
              ? 'Пользователи не найдены'
              : 'Нет пользователей'}
          </div>
        ) : (
          users.map((user, i) => (
            <div key={user.uuid} className="animate-fade-in-up" style={{ animationDelay: `${i * 0.04}s` }}>
              <MobileUserCard
                user={user}
                onNavigate={() => navigate(`/users/${user.uuid}`)}
                onEnable={() => enableUser.mutate(user.uuid)}
                onDisable={() => disableUser.mutate(user.uuid)}
                onDelete={() => deleteUser.mutate(user.uuid)}
              />
            </div>
          ))
        )}
      </div>

      {/* Desktop: Users table */}
      <div className="card p-0 overflow-hidden hidden md:block animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>
                  <SortHeader
                    label="Пользователь"
                    field="username"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th>
                  <SortHeader
                    label="Статус"
                    field="status"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th>
                  <SortHeader
                    label="Трафик"
                    field="used_traffic_bytes"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th>
                  <SortHeader
                    label="Активность"
                    field="online_at"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th>
                  <SortHeader
                    label="Истекает"
                    field="expire_at"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th>
                  <SortHeader
                    label="Создан"
                    field="created_at"
                    currentSort={sortBy}
                    currentOrder={sortOrder}
                    onSort={handleSort}
                  />
                </th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                // Loading skeleton
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td>
                      <div className="h-4 w-32 skeleton rounded" />
                    </td>
                    <td>
                      <div className="h-5 w-20 skeleton rounded" />
                    </td>
                    <td>
                      <div className="h-4 w-24 skeleton rounded" />
                    </td>
                    <td>
                      <div className="h-4 w-20 skeleton rounded" />
                    </td>
                    <td>
                      <div className="h-4 w-20 skeleton rounded" />
                    </td>
                    <td>
                      <div className="h-4 w-20 skeleton rounded" />
                    </td>
                    <td></td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-dark-200">
                    {hasAnyFilter
                      ? 'Пользователи не найдены'
                      : 'Нет пользователей'}
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr
                    key={user.uuid}
                    className="cursor-pointer hover:bg-dark-600/50"
                    onClick={() => navigate(`/users/${user.uuid}`)}
                  >
                    <td>
                      <div>
                        <span className="font-medium text-white">
                          {user.username || user.short_uuid}
                        </span>
                        {user.email && (
                          <p className="text-xs text-dark-200">{user.email}</p>
                        )}
                      </div>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <StatusBadge status={user.status} />
                    </td>
                    <td className="min-w-[140px]">
                      <TrafficBar
                        used={user.used_traffic_bytes}
                        limit={user.traffic_limit_bytes}
                      />
                    </td>
                    <td>
                      <OnlineIndicator onlineAt={user.online_at} />
                    </td>
                    <td className="text-dark-200 text-sm">
                      {formatDate(user.expire_at)}
                    </td>
                    <td className="text-dark-200 text-sm">
                      {formatDate(user.created_at)}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <UserActions
                        user={user}
                        onEnable={() => enableUser.mutate(user.uuid)}
                        onDisable={() => disableUser.mutate(user.uuid)}
                        onDelete={() => deleteUser.mutate(user.uuid)}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 animate-fade-in" style={{ animationDelay: '0.15s' }}>
        <p className="text-sm text-dark-200 order-2 sm:order-1">
          {total > 0 ? (
            <>
              Показано {(page - 1) * perPage + 1}-
              {Math.min(page * perPage, total)} из {total.toLocaleString()}
            </>
          ) : (
            'Нет данных'
          )}
        </p>
        <div className="flex items-center gap-2 order-1 sm:order-2">
          <button
            onClick={() => setPage(page - 1)}
            disabled={page <= 1}
            className="btn-secondary p-2"
          >
            <HiChevronLeft className="w-5 h-5" />
          </button>
          <span className="text-sm text-dark-200 min-w-[80px] text-center">
            {page} / {pages}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={page >= pages}
            className="btn-secondary p-2"
          >
            <HiChevronRight className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Create user modal */}
      {showCreateModal && (
        <CreateUserModal
          onClose={() => { setShowCreateModal(false); setCreateError('') }}
          onSave={(data) => createUser.mutate(data)}
          isPending={createUser.isPending}
          error={createError}
        />
      )}
    </div>
  )
}

// Filter chip component
function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-primary-500/10 border border-primary-500/20 text-[11px] text-primary-300">
      {label}
      <button onClick={onRemove} className="hover:text-white ml-0.5">
        <HiX className="w-3 h-3" />
      </button>
    </span>
  )
}
