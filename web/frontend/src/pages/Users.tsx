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

function getTrafficPercent(used: number, limit: number | null): number {
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const statusConfig: Record<string, { label: string; class: string }> = {
    active: { label: 'Активен', class: 'badge-success' },
    disabled: { label: 'Отключён', class: 'badge-danger' },
    limited: { label: 'Ограничен', class: 'badge-warning' },
    expired: { label: 'Истёк', class: 'badge-gray' },
  }

  const config = statusConfig[status] || { label: status, class: 'badge-gray' }

  return <span className={config.class}>{config.label}</span>
}

// Traffic bar component
function TrafficBar({ used, limit }: { used: number; limit: number | null }) {
  const percent = getTrafficPercent(used, limit)
  const colorClass =
    percent >= 90 ? 'bg-red-500' : percent >= 70 ? 'bg-yellow-500' : 'bg-green-500'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-dark-100">{formatBytes(used)}</span>
        <span className="text-dark-200">
          {limit ? `/ ${formatBytes(limit)}` : '∞'}
        </span>
      </div>
      {limit && (
        <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden">
          <div
            className={`h-full ${colorClass} transition-all`}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
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
        <span>Истекает: {formatDate(user.expire_at)}</span>
        <span>Создан: {formatDate(user.created_at)}</span>
      </div>
    </div>
  )
}

export default function Users() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // State
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [status, setStatus] = useState('')
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1) // Reset page on search
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  // Fetch users
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['users', page, perPage, debouncedSearch, status, sortBy, sortOrder],
    queryFn: () =>
      fetchUsers({
        page,
        per_page: perPage,
        search: debouncedSearch || undefined,
        status: status || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      }),
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

  // Handle status filter
  const handleStatusChange = (newStatus: string) => {
    setStatus(newStatus)
    setPage(1)
  }

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
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex flex-col sm:flex-row gap-3 md:gap-4">
          <div className="flex-1 relative">
            <HiSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-200" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по имени, email, UUID..."
              className="input pl-10"
            />
          </div>
          <div className="flex gap-2">
            <select
              value={status}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="input flex-1 sm:w-48 sm:flex-none"
            >
              <option value="">Все статусы</option>
              <option value="active">Активные</option>
              <option value="disabled">Отключённые</option>
              <option value="limited">Ограниченные</option>
              <option value="expired">Истёкшие</option>
            </select>
            <button
              onClick={() => refetch()}
              className="btn-secondary flex-shrink-0"
              disabled={isLoading}
            >
              <HiRefresh className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

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
            {debouncedSearch || status
              ? 'Пользователи не найдены'
              : 'Нет пользователей'}
          </div>
        ) : (
          users.map((user) => (
            <MobileUserCard
              key={user.uuid}
              user={user}
              onNavigate={() => navigate(`/users/${user.uuid}`)}
              onEnable={() => enableUser.mutate(user.uuid)}
              onDisable={() => disableUser.mutate(user.uuid)}
              onDelete={() => deleteUser.mutate(user.uuid)}
            />
          ))
        )}
      </div>

      {/* Desktop: Users table */}
      <div className="card p-0 overflow-hidden hidden md:block">
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
                <th>Трафик</th>
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
                    <td></td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-dark-200">
                    {debouncedSearch || status
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
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
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
    </div>
  )
}
