import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  HiShieldExclamation,
  HiRefresh,
  HiChevronLeft,
  HiChevronRight,
  HiCheck,
  HiBan,
  HiX,
  HiEye,
  HiExclamation,
  HiFilter,
} from 'react-icons/hi'
import client from '../api/client'

// Types
interface Violation {
  id: number
  user_uuid: string
  username: string | null
  score: number
  severity: string
  reasons: string[]
  details: Record<string, unknown> | null
  action_taken: string | null
  resolved_by: string | null
  resolved_at: string | null
  detected_at: string
}

interface ViolationStats {
  total: number
  critical: number
  high: number
  medium: number
  low: number
  unique_users: number
  avg_score: number
  max_score: number
  by_action: Record<string, number>
  by_country: Record<string, number>
}

interface PaginatedResponse {
  items: Violation[]
  total: number
  page: number
  per_page: number
  pages: number
}

// API functions
const fetchViolations = async (params: {
  page: number
  per_page: number
  severity?: string
  days: number
}): Promise<PaginatedResponse> => {
  const { data } = await client.get('/violations', { params })
  return data
}

const fetchViolationStats = async (): Promise<ViolationStats> => {
  const { data } = await client.get('/violations/stats')
  return data
}

// Utility functions
function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'Только что'
  if (diffMin < 60) return `${diffMin} мин назад`
  if (diffHour < 24) return `${diffHour} ч назад`
  if (diffDay < 7) return `${diffDay} дн назад`
  return date.toLocaleDateString('ru-RU')
}

function getSeverityConfig(severity: string): { label: string; class: string; icon: string } {
  const config: Record<string, { label: string; class: string; icon: string }> = {
    critical: { label: 'Критический', class: 'badge-danger', icon: 'text-red-400' },
    high: { label: 'Высокий', class: 'badge-warning', icon: 'text-yellow-400' },
    medium: { label: 'Средний', class: 'badge-info', icon: 'text-blue-400' },
    low: { label: 'Низкий', class: 'badge-gray', icon: 'text-gray-400' },
  }
  return config[severity] || { label: severity, class: 'badge-gray', icon: 'text-gray-400' }
}

function getActionConfig(action: string | null): { label: string; class: string } {
  if (!action) return { label: 'Ожидает', class: 'badge-warning' }

  const config: Record<string, { label: string; class: string }> = {
    blocked: { label: 'Заблокирован', class: 'badge-danger' },
    warned: { label: 'Предупреждён', class: 'badge-info' },
    dismissed: { label: 'Отклонено', class: 'badge-gray' },
    resolved: { label: 'Разрешено', class: 'badge-success' },
  }
  return config[action] || { label: action, class: 'badge-gray' }
}

// Severity badge component
function SeverityBadge({ severity }: { severity: string }) {
  const config = getSeverityConfig(severity)
  return <span className={config.class}>{config.label}</span>
}

// Action badge component
function ActionBadge({ action }: { action: string | null }) {
  const config = getActionConfig(action)
  return <span className={config.class}>{config.label}</span>
}

// Score indicator
function ScoreIndicator({ score }: { score: number }) {
  const colorClass =
    score >= 80 ? 'text-red-400' : score >= 60 ? 'text-yellow-400' : 'text-green-400'
  const bgClass =
    score >= 80 ? 'bg-red-500/20' : score >= 60 ? 'bg-yellow-500/20' : 'bg-green-500/20'

  return (
    <div className={`px-3 py-2 rounded-lg ${bgClass} text-center`}>
      <p className={`text-2xl font-bold ${colorClass}`}>{score}</p>
      <p className="text-xs text-gray-500">Score</p>
    </div>
  )
}

// Violation card component
function ViolationCard({
  violation,
  onBlock,
  onWarn,
  onDismiss,
  onView,
}: {
  violation: Violation
  onBlock: () => void
  onWarn: () => void
  onDismiss: () => void
  onView: () => void
}) {
  const severityConfig = getSeverityConfig(violation.severity)
  const isPending = !violation.action_taken

  return (
    <div className="card">
      <div className="flex items-start gap-3 md:gap-4">
        {/* Icon - hidden on very small screens */}
        <div
          className={`hidden sm:block p-2.5 rounded-lg flex-shrink-0 ${
            violation.severity === 'critical'
              ? 'bg-red-500/10'
              : violation.severity === 'high'
                ? 'bg-yellow-500/10'
                : 'bg-blue-500/10'
          }`}
        >
          {violation.severity === 'critical' ? (
            <HiExclamation className={`w-6 h-6 ${severityConfig.icon}`} />
          ) : (
            <HiShieldExclamation className={`w-6 h-6 ${severityConfig.icon}`} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-semibold text-white">
              {violation.username || 'Неизвестный'}
            </span>
            <SeverityBadge severity={violation.severity} />
            <ActionBadge action={violation.action_taken} />
          </div>
          <p className="text-sm text-gray-400 mb-2">{violation.reasons.join(', ')}</p>
          <p className="text-xs text-gray-500">{formatTimeAgo(violation.detected_at)}</p>
        </div>

        {/* Score */}
        <ScoreIndicator score={violation.score} />
      </div>

      {/* Actions */}
      {isPending && (
        <div className="mt-4 pt-4 border-t border-dark-700 flex flex-wrap gap-2">
          <button
            onClick={onBlock}
            className="btn-danger text-xs sm:text-sm flex items-center gap-1"
          >
            <HiBan className="w-4 h-4" /> <span className="hidden sm:inline">Заблокировать</span><span className="sm:hidden">Блок</span>
          </button>
          <button
            onClick={onWarn}
            className="btn-secondary text-xs sm:text-sm flex items-center gap-1"
          >
            <HiExclamation className="w-4 h-4" /> <span className="hidden sm:inline">Предупредить</span><span className="sm:hidden">Пред.</span>
          </button>
          <button
            onClick={onDismiss}
            className="btn-ghost text-xs sm:text-sm flex items-center gap-1"
          >
            <HiX className="w-4 h-4" /> Отклонить
          </button>
          <button
            onClick={onView}
            className="btn-ghost text-xs sm:text-sm flex items-center gap-1 ml-auto"
          >
            <HiEye className="w-4 h-4" /> <span className="hidden sm:inline">Подробнее</span>
          </button>
        </div>
      )}

      {/* Resolved info */}
      {!isPending && violation.resolved_at && (
        <div className="mt-4 pt-4 border-t border-dark-700 flex items-center justify-between text-xs text-gray-500">
          <span>
            Решено: {formatTimeAgo(violation.resolved_at)}
            {violation.resolved_by && ` (${violation.resolved_by})`}
          </span>
          <button
            onClick={onView}
            className="text-primary-400 hover:text-primary-300 flex items-center gap-1"
          >
            <HiEye className="w-4 h-4" /> Подробнее
          </button>
        </div>
      )}
    </div>
  )
}

// Loading skeleton
function ViolationSkeleton() {
  return (
    <div className="card animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-11 h-11 bg-dark-700 rounded-lg" />
        <div className="flex-1">
          <div className="flex gap-2 mb-2">
            <div className="h-4 w-24 bg-dark-700 rounded" />
            <div className="h-4 w-16 bg-dark-700 rounded" />
          </div>
          <div className="h-3 w-48 bg-dark-700 rounded mb-2" />
          <div className="h-3 w-20 bg-dark-700 rounded" />
        </div>
        <div className="w-16 h-16 bg-dark-700 rounded-lg" />
      </div>
    </div>
  )
}

export default function Violations() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // State
  const [page, setPage] = useState(1)
  const [perPage] = useState(10)
  const [severity, setSeverity] = useState('')
  const [days, setDays] = useState(7)
  const [showFilters, setShowFilters] = useState(false)

  // Fetch violations
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['violations', page, perPage, severity, days],
    queryFn: () =>
      fetchViolations({
        page,
        per_page: perPage,
        severity: severity || undefined,
        days,
      }),
  })

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['violationStats'],
    queryFn: fetchViolationStats,
  })

  // Mutations
  const resolveViolation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      client.post(`/violations/${id}/resolve`, { action }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
    },
  })

  const violations = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Нарушения</h1>
          <p className="text-gray-400 mt-1 text-sm md:text-base">
            Система анти-абуза и управление нарушениями
          </p>
        </div>
        <div className="page-header-actions">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`btn-secondary flex items-center gap-2 ${showFilters ? 'ring-2 ring-primary-500' : ''}`}
          >
            <HiFilter className="w-4 h-4" />
            <span className="hidden sm:inline">Фильтры</span>
          </button>
          <button
            onClick={() => refetch()}
            className="btn-secondary"
            disabled={isLoading}
          >
            <HiRefresh className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="card">
          <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-3 md:gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Уровень</label>
              <select
                value={severity}
                onChange={(e) => {
                  setSeverity(e.target.value)
                  setPage(1)
                }}
                className="input w-full sm:w-40"
              >
                <option value="">Все</option>
                <option value="critical">Критический</option>
                <option value="high">Высокий</option>
                <option value="medium">Средний</option>
                <option value="low">Низкий</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Период</label>
              <select
                value={days}
                onChange={(e) => {
                  setDays(Number(e.target.value))
                  setPage(1)
                }}
                className="input w-full sm:w-40"
              >
                <option value={1}>Сегодня</option>
                <option value={7}>Неделя</option>
                <option value={30}>Месяц</option>
                <option value={90}>3 месяца</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card text-center">
          <p className="text-sm text-gray-400">Критические</p>
          <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">
            {stats?.critical ?? '-'}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Высокие</p>
          <p className="text-xl md:text-2xl font-bold text-yellow-400 mt-1">
            {stats?.high ?? '-'}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Средние</p>
          <p className="text-xl md:text-2xl font-bold text-blue-400 mt-1">
            {stats?.medium ?? '-'}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Низкие</p>
          <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
            {stats?.low ?? '-'}
          </p>
        </div>
      </div>

      {/* Violations list */}
      <div className="space-y-4">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => <ViolationSkeleton key={i} />)
        ) : violations.length === 0 ? (
          <div className="card text-center py-12">
            <HiCheck className="w-12 h-12 text-green-500 mx-auto mb-3" />
            <p className="text-gray-400">Нарушений не обнаружено</p>
            <p className="text-sm text-gray-500 mt-1">
              За выбранный период нет записей о нарушениях
            </p>
          </div>
        ) : (
          violations.map((violation) => (
            <ViolationCard
              key={violation.id}
              violation={violation}
              onBlock={() =>
                resolveViolation.mutate({ id: violation.id, action: 'blocked' })
              }
              onWarn={() =>
                resolveViolation.mutate({ id: violation.id, action: 'warned' })
              }
              onDismiss={() =>
                resolveViolation.mutate({ id: violation.id, action: 'dismissed' })
              }
              onView={() => navigate(`/users/${violation.user_uuid}`)}
            />
          ))
        )}
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-sm text-gray-400 order-2 sm:order-1">
            Показано {(page - 1) * perPage + 1}-
            {Math.min(page * perPage, total)} из {total}
          </p>
          <div className="flex items-center gap-2 order-1 sm:order-2">
            <button
              onClick={() => setPage(page - 1)}
              disabled={page <= 1}
              className="btn-secondary p-2"
            >
              <HiChevronLeft className="w-5 h-5" />
            </button>
            <span className="text-sm text-gray-400 min-w-[80px] text-center">
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
      )}
    </div>
  )
}
