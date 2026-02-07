import { useState, useCallback } from 'react'
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
  HiGlobe,
  HiClock,
  HiUser,
  HiTrendingUp,
  HiChevronDown,
  HiChevronUp,
  HiLocationMarker,
  HiServer,
  HiDeviceMobile,
  HiIdentification,
  HiArrowLeft,
  HiExternalLink,
  HiChat,
} from 'react-icons/hi'
import client from '../api/client'

// ── Types ────────────────────────────────────────────────────────

interface Violation {
  id: number
  user_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  score: number
  severity: string
  recommended_action: string
  confidence: number
  action_taken: string | null
  notified: boolean
  detected_at: string
}

interface ViolationDetail {
  id: number
  user_uuid: string
  username: string | null
  email: string | null
  telegram_id: number | null
  score: number
  recommended_action: string
  confidence: number
  detected_at: string
  temporal_score: number
  geo_score: number
  asn_score: number
  profile_score: number
  device_score: number
  reasons: string[]
  countries: string[]
  asn_types: string[]
  ips: string[]
  action_taken: string | null
  action_taken_at: string | null
  action_taken_by: number | null
  notified_at: string | null
  raw_data: Record<string, unknown> | null
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

interface TopViolator {
  user_uuid: string
  username: string | null
  violations_count: number
  max_score: number
  avg_score: number
  last_violation_at: string
  actions: string[]
}

interface IPInfo {
  ip: string
  asn_org: string | null
  country: string | null
  city: string | null
  connection_type: string | null
  is_vpn: boolean
  is_proxy: boolean
  is_hosting: boolean
  is_mobile: boolean
}

// ── API ──────────────────────────────────────────────────────────

const fetchViolations = async (params: {
  page: number
  per_page: number
  severity?: string
  days: number
  resolved?: boolean
  min_score?: number
}): Promise<PaginatedResponse> => {
  const p: Record<string, unknown> = {
    page: params.page,
    per_page: params.per_page,
    days: params.days,
  }
  if (params.severity) p.severity = params.severity
  if (params.resolved !== undefined) p.resolved = params.resolved
  if (params.min_score !== undefined && params.min_score > 0) p.min_score = params.min_score
  const { data } = await client.get('/violations', { params: p })
  return data
}

const fetchViolationStats = async (days: number): Promise<ViolationStats> => {
  const { data } = await client.get('/violations/stats', { params: { days } })
  return data
}

const fetchViolationDetail = async (id: number): Promise<ViolationDetail> => {
  const { data } = await client.get(`/violations/${id}`)
  return data
}

const fetchTopViolators = async (days: number): Promise<TopViolator[]> => {
  const { data } = await client.get('/violations/top-violators', { params: { days, limit: 15 } })
  return data
}

const fetchIPLookup = async (ips: string[]): Promise<Record<string, IPInfo>> => {
  if (!ips.length) return {}
  const { data } = await client.post('/violations/ip-lookup', { ips })
  return data.results || {}
}

// ── Utilities ────────────────────────────────────────────────────

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

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getSeverityConfig(severity: string) {
  const config: Record<string, { label: string; class: string; iconClass: string; bg: string }> = {
    critical: {
      label: 'Критический',
      class: 'badge-danger',
      iconClass: 'text-red-400',
      bg: 'bg-red-500/10',
    },
    high: {
      label: 'Высокий',
      class: 'badge-warning',
      iconClass: 'text-yellow-400',
      bg: 'bg-yellow-500/10',
    },
    medium: {
      label: 'Средний',
      class: 'badge-info',
      iconClass: 'text-blue-400',
      bg: 'bg-blue-500/10',
    },
    low: {
      label: 'Низкий',
      class: 'badge-gray',
      iconClass: 'text-dark-200',
      bg: 'bg-dark-600/50',
    },
  }
  return config[severity] || config.low
}

function getSeverityFromScore(score: number): string {
  if (score >= 80) return 'critical'
  if (score >= 60) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

function getActionConfig(action: string | null) {
  if (!action) return { label: 'Ожидает', class: 'badge-warning' }
  const config: Record<string, { label: string; class: string }> = {
    block: { label: 'Заблокирован', class: 'badge-danger' },
    blocked: { label: 'Заблокирован', class: 'badge-danger' },
    warn: { label: 'Предупреждён', class: 'badge-info' },
    warned: { label: 'Предупреждён', class: 'badge-info' },
    ignore: { label: 'Отклонено', class: 'badge-gray' },
    dismissed: { label: 'Отклонено', class: 'badge-gray' },
    resolved: { label: 'Разрешено', class: 'badge-success' },
  }
  return config[action] || { label: action, class: 'badge-gray' }
}

function getRecommendedActionLabel(action: string): string {
  const labels: Record<string, string> = {
    no_action: 'Нет действий',
    monitor: 'Мониторинг',
    warn: 'Предупреждение',
    soft_block: 'Мягкая блокировка',
    temp_block: 'Временная блокировка',
    hard_block: 'Жёсткая блокировка',
  }
  return labels[action] || action
}

function getRecommendedActionClass(action: string): string {
  const cls: Record<string, string> = {
    no_action: 'text-green-400',
    monitor: 'text-blue-400',
    warn: 'text-yellow-400',
    soft_block: 'text-orange-400',
    temp_block: 'text-red-400',
    hard_block: 'text-red-500',
  }
  return cls[action] || 'text-dark-200'
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-red-400'
  if (score >= 60) return 'text-yellow-400'
  if (score >= 40) return 'text-blue-400'
  return 'text-green-400'
}

function getScoreBg(score: number): string {
  if (score >= 80) return 'bg-red-500/20'
  if (score >= 60) return 'bg-yellow-500/20'
  if (score >= 40) return 'bg-blue-500/20'
  return 'bg-green-500/20'
}

function getConnectionTypeLabel(type: string | null): string | null {
  if (!type) return null
  const labels: Record<string, string> = {
    residential: 'Домашний',
    mobile: 'Мобильный',
    mobile_isp: 'Моб. оператор',
    datacenter: 'Датацентр',
    hosting: 'Хостинг',
    vpn: 'VPN',
    unknown: 'Неизвестно',
  }
  return labels[type] || type
}

function getConnectionTypeBadge(info: IPInfo): { label: string; cls: string } | null {
  if (info.is_vpn) return { label: 'VPN', cls: 'text-red-400 bg-red-500/10 border-red-500/30' }
  if (info.is_proxy) return { label: 'Proxy', cls: 'text-orange-400 bg-orange-500/10 border-orange-500/30' }
  if (info.is_hosting) return { label: 'Хостинг', cls: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30' }
  if (info.is_mobile) return { label: 'Моб.', cls: 'text-blue-400 bg-blue-500/10 border-blue-500/30' }
  const typeLabel = getConnectionTypeLabel(info.connection_type)
  if (typeLabel && info.connection_type !== 'unknown') {
    return { label: typeLabel, cls: 'text-dark-200 bg-dark-600/50 border-dark-400/30' }
  }
  return null
}

// ── Score bar component ──────────────────────────────────────────

function ScoreBar({ label, score, icon }: { label: string; score: number; icon: React.ReactNode }) {
  const barColor =
    score >= 60 ? 'bg-red-500' : score >= 40 ? 'bg-yellow-500' : score >= 20 ? 'bg-blue-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 w-32 flex-shrink-0">
        <span className="text-dark-200">{icon}</span>
        <span className="text-sm text-dark-100">{label}</span>
      </div>
      <div className="flex-1 h-2 bg-dark-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      <span className={`text-sm font-medium w-10 text-right ${getScoreColor(score)}`}>
        {Math.round(score)}
      </span>
    </div>
  )
}

// ── Score circle component ───────────────────────────────────────

function ScoreCircle({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' | 'lg' }) {
  const sizeMap = { sm: 'w-10 h-10', md: 'w-14 h-14', lg: 'w-20 h-20' }
  const textMap = { sm: 'text-sm', md: 'text-xl', lg: 'text-3xl' }
  return (
    <div
      className={`${sizeMap[size]} rounded-full ${getScoreBg(score)} flex items-center justify-center flex-shrink-0`}
    >
      <span className={`font-bold ${getScoreColor(score)} ${textMap[size]}`}>{Math.round(score)}</span>
    </div>
  )
}

// ── Violation card ───────────────────────────────────────────────

function ViolationCard({
  violation,
  onBlock,
  onWarn,
  onDismiss,
  onViewDetail,
  onViewUser,
}: {
  violation: Violation
  onBlock: () => void
  onWarn: () => void
  onDismiss: () => void
  onViewDetail: () => void
  onViewUser: () => void
}) {
  const severityConfig = getSeverityConfig(violation.severity)
  const isPending = !violation.action_taken

  return (
    <div className="card hover:border-dark-400/40 transition-colors">
      <div className="flex items-start gap-3 md:gap-4">
        {/* Severity icon */}
        <div className={`hidden sm:flex p-2.5 rounded-lg flex-shrink-0 ${severityConfig.bg}`}>
          {violation.severity === 'critical' ? (
            <HiExclamation className={`w-6 h-6 ${severityConfig.iconClass}`} />
          ) : (
            <HiShieldExclamation className={`w-6 h-6 ${severityConfig.iconClass}`} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <button
              onClick={onViewUser}
              className="font-semibold text-white hover:text-primary-400 transition-colors"
            >
              {violation.username || violation.email || 'Неизвестный'}
            </button>
            <SeverityBadge severity={violation.severity} />
            <ActionBadge action={violation.action_taken} />
            {violation.notified && (
              <span className="text-xs text-dark-200" title="Уведомлён">
                <HiChat className="w-3.5 h-3.5 inline" />
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-dark-200 mb-1">
            <span className={getRecommendedActionClass(violation.recommended_action)}>
              {getRecommendedActionLabel(violation.recommended_action)}
            </span>
            {violation.confidence > 0 && (
              <span>Уверенность: {Math.round(violation.confidence * 100)}%</span>
            )}
          </div>

          {violation.email && (
            <p className="text-xs text-dark-200 mb-0.5 truncate">{violation.email}</p>
          )}

          <p className="text-xs text-dark-200 flex items-center gap-1">
            <HiClock className="w-3.5 h-3.5" />
            {formatTimeAgo(violation.detected_at)}
          </p>
        </div>

        {/* Score */}
        <ScoreCircle score={violation.score} />
      </div>

      {/* Actions for pending violations */}
      {isPending && (
        <div className="mt-4 pt-3 border-t border-dark-400/10 flex flex-wrap gap-2">
          <button onClick={onBlock} className="btn-danger text-xs sm:text-sm flex items-center gap-1">
            <HiBan className="w-4 h-4" />
            <span className="hidden sm:inline">Заблокировать</span>
            <span className="sm:hidden">Блок</span>
          </button>
          <button onClick={onWarn} className="btn-secondary text-xs sm:text-sm flex items-center gap-1">
            <HiExclamation className="w-4 h-4" />
            <span className="hidden sm:inline">Предупредить</span>
            <span className="sm:hidden">Пред.</span>
          </button>
          <button onClick={onDismiss} className="btn-ghost text-xs sm:text-sm flex items-center gap-1">
            <HiX className="w-4 h-4" /> Отклонить
          </button>
          <button
            onClick={onViewDetail}
            className="btn-ghost text-xs sm:text-sm flex items-center gap-1 ml-auto"
          >
            <HiEye className="w-4 h-4" />
            <span className="hidden sm:inline">Подробнее</span>
          </button>
        </div>
      )}

      {/* Resolved footer */}
      {!isPending && (
        <div className="mt-4 pt-3 border-t border-dark-400/10 flex items-center justify-between text-xs text-dark-200">
          <span>Действие: {getActionConfig(violation.action_taken).label}</span>
          <button
            onClick={onViewDetail}
            className="text-primary-400 hover:text-primary-300 flex items-center gap-1 transition-colors"
          >
            <HiEye className="w-4 h-4" /> Подробнее
          </button>
        </div>
      )}
    </div>
  )
}

// ── Badges ───────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={getSeverityConfig(severity).class}>{getSeverityConfig(severity).label}</span>
}

function ActionBadge({ action }: { action: string | null }) {
  const config = getActionConfig(action)
  return <span className={config.class}>{config.label}</span>
}

// ── Detail panel ─────────────────────────────────────────────────

function ViolationDetailPanel({
  violationId,
  onClose,
  onBlock,
  onWarn,
  onDismiss,
  onViewUser,
}: {
  violationId: number
  onClose: () => void
  onBlock: (id: number) => void
  onWarn: (id: number) => void
  onDismiss: (id: number) => void
  onViewUser: (uuid: string) => void
}) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ['violationDetail', violationId],
    queryFn: () => fetchViolationDetail(violationId),
  })

  const { data: ipInfo } = useQuery({
    queryKey: ['ipLookup', detail?.ips],
    queryFn: () => fetchIPLookup(detail!.ips),
    enabled: !!detail && detail.ips.length > 0,
  })

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="btn-ghost p-2">
            <HiArrowLeft className="w-5 h-5" />
          </button>
          <div className="h-6 w-48 bg-dark-700 rounded skeleton" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card">
            <div className="h-4 w-32 bg-dark-700 rounded skeleton mb-3" />
            <div className="h-20 bg-dark-700 rounded skeleton" />
          </div>
        ))}
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <button onClick={onClose} className="btn-ghost flex items-center gap-2">
          <HiArrowLeft className="w-5 h-5" /> Назад
        </button>
        <div className="card text-center py-8 text-dark-200">Нарушение не найдено</div>
      </div>
    )
  }

  const severity = getSeverityFromScore(detail.score)
  const severityConfig = getSeverityConfig(severity)
  const isPending = !detail.action_taken

  return (
    <div className="space-y-4 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={onClose} className="btn-ghost p-2">
          <HiArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-bold text-white truncate">
            Нарушение #{detail.id}
          </h2>
          <p className="text-sm text-dark-200">{formatDate(detail.detected_at)}</p>
        </div>
        <ScoreCircle score={detail.score} size="lg" />
      </div>

      {/* User info card */}
      <div className="card animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
          Пользователь
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <div className={`p-2 rounded-lg ${severityConfig.bg}`}>
            <HiUser className={`w-5 h-5 ${severityConfig.iconClass}`} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-white">{detail.username || 'Неизвестный'}</p>
            {detail.email && <p className="text-sm text-dark-200 truncate">{detail.email}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            <SeverityBadge severity={severity} />
            <ActionBadge action={detail.action_taken} />
          </div>
          <button
            onClick={() => onViewUser(detail.user_uuid)}
            className="btn-secondary text-sm flex items-center gap-1"
          >
            <HiExternalLink className="w-4 h-4" /> Профиль
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          <div className="text-center p-2 rounded-lg bg-dark-800/50">
            <p className="text-xs text-dark-200">Рекомендация</p>
            <p className={`text-sm font-medium ${getRecommendedActionClass(detail.recommended_action)}`}>
              {getRecommendedActionLabel(detail.recommended_action)}
            </p>
          </div>
          <div className="text-center p-2 rounded-lg bg-dark-800/50">
            <p className="text-xs text-dark-200">Уверенность</p>
            <p className="text-sm font-medium text-white">
              {Math.round(detail.confidence * 100)}%
            </p>
          </div>
          <div className="text-center p-2 rounded-lg bg-dark-800/50">
            <p className="text-xs text-dark-200">Стран</p>
            <p className="text-sm font-medium text-white">{detail.countries.length}</p>
          </div>
          <div className="text-center p-2 rounded-lg bg-dark-800/50">
            <p className="text-xs text-dark-200">IP-адресов</p>
            <p className="text-sm font-medium text-white">{detail.ips.length}</p>
          </div>
        </div>
      </div>

      {/* Score breakdown */}
      <div className="card animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-4">
          Разбор скоринга
        </h3>
        <div className="space-y-3">
          <ScoreBar
            label="Временной"
            score={detail.temporal_score}
            icon={<HiClock className="w-4 h-4" />}
          />
          <ScoreBar
            label="Гео"
            score={detail.geo_score}
            icon={<HiGlobe className="w-4 h-4" />}
          />
          <ScoreBar
            label="Провайдер"
            score={detail.asn_score}
            icon={<HiServer className="w-4 h-4" />}
          />
          <ScoreBar
            label="Профиль"
            score={detail.profile_score}
            icon={<HiIdentification className="w-4 h-4" />}
          />
          <ScoreBar
            label="Устройство"
            score={detail.device_score}
            icon={<HiDeviceMobile className="w-4 h-4" />}
          />
        </div>
        <div className="mt-4 pt-3 border-t border-dark-400/10 flex items-center justify-between">
          <span className="text-sm text-dark-200">Итоговый скор</span>
          <span className={`text-lg font-bold ${getScoreColor(detail.score)}`}>
            {Math.round(detail.score)} / 100
          </span>
        </div>
      </div>

      {/* Reasons */}
      {detail.reasons.length > 0 && (
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            Причины ({detail.reasons.length})
          </h3>
          <ul className="space-y-2">
            {detail.reasons.map((reason, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <HiExclamation className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
                <span className="text-dark-100">{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Geo & Network info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Countries */}
        {detail.countries.length > 0 && (
          <div className="card animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              <HiLocationMarker className="w-4 h-4 inline mr-1" />
              Страны
            </h3>
            <div className="flex flex-wrap gap-2">
              {detail.countries.map((country, i) => (
                <span key={i} className="badge-info">{country}</span>
              ))}
            </div>
          </div>
        )}

        {/* ASN types */}
        {detail.asn_types.length > 0 && (
          <div className="card animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              <HiServer className="w-4 h-4 inline mr-1" />
              Типы провайдеров
            </h3>
            <div className="flex flex-wrap gap-2">
              {detail.asn_types.map((asn, i) => (
                <span key={i} className="badge-gray">{asn}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* IPs */}
      {detail.ips.length > 0 && (
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            IP-адреса ({detail.ips.length})
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {detail.ips.map((ip, i) => {
              const info = ipInfo?.[ip]
              const badge = info ? getConnectionTypeBadge(info) : null
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 bg-dark-800/80 rounded px-3 py-2"
                >
                  <code className="text-xs text-dark-100 font-mono flex-shrink-0">{ip}</code>
                  {info ? (
                    <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                      {info.asn_org && (
                        <span className="text-xs text-primary-400 truncate max-w-[160px]" title={info.asn_org}>
                          {info.asn_org}
                        </span>
                      )}
                      {info.city && info.country && (
                        <span className="text-xs text-dark-200 truncate max-w-[120px]" title={`${info.city}, ${info.country}`}>
                          {info.city}
                        </span>
                      )}
                      {badge && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls}`}>
                          {badge.label}
                        </span>
                      )}
                    </div>
                  ) : ipInfo ? (
                    <span className="text-xs text-dark-300">—</span>
                  ) : (
                    <span className="text-xs text-dark-300 animate-pulse">...</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Admin action resolution info */}
      {detail.action_taken && detail.action_taken_at && (
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            Решение администратора
          </h3>
          <div className="flex items-center gap-3">
            <ActionBadge action={detail.action_taken} />
            <span className="text-sm text-dark-200">
              {formatDate(detail.action_taken_at)}
            </span>
          </div>
        </div>
      )}

      {/* Action buttons for pending */}
      {isPending && (
        <div className="card animate-fade-in-up border-primary-500/20" style={{ animationDelay: '0.35s' }}>
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            Принять решение
          </h3>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => onBlock(detail.id)}
              className="btn-danger flex items-center gap-2"
            >
              <HiBan className="w-4 h-4" /> Заблокировать
            </button>
            <button
              onClick={() => onWarn(detail.id)}
              className="btn-secondary flex items-center gap-2"
            >
              <HiExclamation className="w-4 h-4" /> Предупредить
            </button>
            <button
              onClick={() => onDismiss(detail.id)}
              className="btn-ghost flex items-center gap-2"
            >
              <HiX className="w-4 h-4" /> Отклонить
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Top violators tab ────────────────────────────────────────────

function TopViolatorsTab({ days, onViewUser }: { days: number; onViewUser: (uuid: string) => void }) {
  const { data: violators, isLoading } = useQuery({
    queryKey: ['topViolators', days],
    queryFn: () => fetchTopViolators(days),
  })

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="card">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 bg-dark-700 rounded-full skeleton" />
              <div className="flex-1">
                <div className="h-4 w-32 bg-dark-700 rounded skeleton mb-2" />
                <div className="h-3 w-48 bg-dark-700 rounded skeleton" />
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (!violators?.length) {
    return (
      <div className="card text-center py-12">
        <HiCheck className="w-12 h-12 text-green-500 mx-auto mb-3" />
        <p className="text-dark-200">Нет нарушителей за период</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {violators.map((v, i) => {
        const severity = getSeverityFromScore(v.max_score)
        return (
          <div
            key={v.user_uuid}
            className="card animate-fade-in-up hover:border-dark-400/40 transition-colors"
            style={{ animationDelay: `${i * 0.05}s` }}
          >
            <div className="flex items-center gap-3 md:gap-4">
              {/* Rank */}
              <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                i === 0 ? 'bg-red-500/20 text-red-400' :
                i === 1 ? 'bg-yellow-500/20 text-yellow-400' :
                i === 2 ? 'bg-orange-500/20 text-orange-400' :
                'bg-dark-600/50 text-dark-200'
              }`}>
                <span className="font-bold text-sm">#{i + 1}</span>
              </div>

              {/* User info */}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <button
                    onClick={() => onViewUser(v.user_uuid)}
                    className="font-semibold text-white hover:text-primary-400 transition-colors"
                  >
                    {v.username || 'Неизвестный'}
                  </button>
                  <SeverityBadge severity={severity} />
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-dark-200">
                  <span>
                    <HiShieldExclamation className="w-3.5 h-3.5 inline mr-0.5" />
                    {v.violations_count} нарушени{v.violations_count === 1 ? 'е' : v.violations_count < 5 ? 'я' : 'й'}
                  </span>
                  <span>Макс: {Math.round(v.max_score)}</span>
                  <span>Средн: {Math.round(v.avg_score)}</span>
                  <span>
                    <HiClock className="w-3.5 h-3.5 inline mr-0.5" />
                    {formatTimeAgo(v.last_violation_at)}
                  </span>
                </div>
              </div>

              {/* Max score */}
              <ScoreCircle score={v.max_score} size="sm" />
            </div>

            {/* Actions taken */}
            {v.actions.length > 0 && (
              <div className="mt-3 pt-3 border-t border-dark-400/10 flex flex-wrap gap-2">
                {v.actions.map((action, j) => (
                  <ActionBadge key={j} action={action} />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Stats overview ───────────────────────────────────────────────

function StatsOverview({ stats }: { stats: ViolationStats | undefined }) {
  const [showCountries, setShowCountries] = useState(false)

  if (!stats) return null

  const countryEntries = Object.entries(stats.by_country || {})
    .sort((a, b) => b[1] - a[1])

  return (
    <>
      {/* Main stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <p className="text-xs sm:text-sm text-dark-200">Критические</p>
          <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">{stats.critical}</p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <p className="text-xs sm:text-sm text-dark-200">Высокие</p>
          <p className="text-xl md:text-2xl font-bold text-yellow-400 mt-1">{stats.high}</p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <p className="text-xs sm:text-sm text-dark-200">Средние</p>
          <p className="text-xl md:text-2xl font-bold text-blue-400 mt-1">{stats.medium}</p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <p className="text-xs sm:text-sm text-dark-200">Низкие</p>
          <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">{stats.low}</p>
        </div>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4">
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <div className="flex items-center gap-2">
            <HiShieldExclamation className="w-5 h-5 text-primary-400" />
            <div>
              <p className="text-xs text-dark-200">Всего</p>
              <p className="text-lg font-bold text-white">{stats.total}</p>
            </div>
          </div>
        </div>
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <div className="flex items-center gap-2">
            <HiUser className="w-5 h-5 text-primary-400" />
            <div>
              <p className="text-xs text-dark-200">Уник. юзеров</p>
              <p className="text-lg font-bold text-white">{stats.unique_users}</p>
            </div>
          </div>
        </div>
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
          <div className="flex items-center gap-2">
            <HiTrendingUp className="w-5 h-5 text-primary-400" />
            <div>
              <p className="text-xs text-dark-200">Средн. скор</p>
              <p className="text-lg font-bold text-white">{Math.round(stats.avg_score)}</p>
            </div>
          </div>
        </div>
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
          <div className="flex items-center gap-2">
            <HiExclamation className="w-5 h-5 text-red-400" />
            <div>
              <p className="text-xs text-dark-200">Макс. скор</p>
              <p className="text-lg font-bold text-white">{Math.round(stats.max_score)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Countries (collapsible) */}
      {countryEntries.length > 0 && (
        <div className="card animate-fade-in-up" style={{ animationDelay: '0.45s' }}>
          <button
            onClick={() => setShowCountries(!showCountries)}
            className="flex items-center justify-between w-full text-left"
          >
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider flex items-center gap-2">
              <HiGlobe className="w-4 h-4" />
              По странам ({countryEntries.length})
            </h3>
            {showCountries ? (
              <HiChevronUp className="w-5 h-5 text-dark-200" />
            ) : (
              <HiChevronDown className="w-5 h-5 text-dark-200" />
            )}
          </button>
          {showCountries && (
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 animate-fade-in-down">
              {countryEntries.map(([country, count]) => (
                <div
                  key={country}
                  className="flex items-center justify-between bg-dark-800/50 rounded-lg px-3 py-2"
                >
                  <span className="text-sm text-dark-100">{country || 'Неизвестно'}</span>
                  <span className="text-sm font-medium text-primary-400">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  )
}

// ── Loading skeleton ─────────────────────────────────────────────

function ViolationSkeleton() {
  return (
    <div className="card">
      <div className="flex items-start gap-4">
        <div className="w-11 h-11 bg-dark-700 rounded-lg skeleton hidden sm:block" />
        <div className="flex-1">
          <div className="flex gap-2 mb-2">
            <div className="h-4 w-24 bg-dark-700 rounded skeleton" />
            <div className="h-4 w-16 bg-dark-700 rounded skeleton" />
          </div>
          <div className="h-3 w-48 bg-dark-700 rounded skeleton mb-2" />
          <div className="h-3 w-20 bg-dark-700 rounded skeleton" />
        </div>
        <div className="w-14 h-14 bg-dark-700 rounded-full skeleton" />
      </div>
    </div>
  )
}

// ── Main page component ──────────────────────────────────────────

type Tab = 'all' | 'pending' | 'top'

export default function Violations() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // State
  const [tab, setTab] = useState<Tab>('all')
  const [page, setPage] = useState(1)
  const [perPage] = useState(15)
  const [severity, setSeverity] = useState('')
  const [days, setDays] = useState(7)
  const [showFilters, setShowFilters] = useState(false)
  const [minScore, setMinScore] = useState(0)
  const [selectedViolationId, setSelectedViolationId] = useState<number | null>(null)

  // Derived filter for resolved status
  const resolved = tab === 'pending' ? false : undefined

  // Fetch violations list
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['violations', page, perPage, severity, days, resolved, minScore],
    queryFn: () =>
      fetchViolations({
        page,
        per_page: perPage,
        severity: severity || undefined,
        days,
        resolved,
        min_score: minScore,
      }),
    enabled: tab !== 'top',
  })

  // Fetch stats (always)
  const { data: stats } = useQuery({
    queryKey: ['violationStats', days],
    queryFn: () => fetchViolationStats(days),
  })

  // Mutations
  const resolveViolation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      client.post(`/violations/${id}/resolve`, { action }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      queryClient.invalidateQueries({ queryKey: ['topViolators'] })
      queryClient.invalidateQueries({ queryKey: ['violationDetail'] })
      setSelectedViolationId(null)
    },
  })

  const violations = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  const handleBlock = useCallback(
    (id: number) => resolveViolation.mutate({ id, action: 'block' }),
    [resolveViolation],
  )
  const handleWarn = useCallback(
    (id: number) => resolveViolation.mutate({ id, action: 'warn' }),
    [resolveViolation],
  )
  const handleDismiss = useCallback(
    (id: number) => resolveViolation.mutate({ id, action: 'ignore' }),
    [resolveViolation],
  )

  const handleTabChange = (newTab: Tab) => {
    setTab(newTab)
    setPage(1)
    setSelectedViolationId(null)
  }

  // Detail view
  if (selectedViolationId !== null) {
    return (
      <div className="space-y-6">
        <ViolationDetailPanel
          violationId={selectedViolationId}
          onClose={() => setSelectedViolationId(null)}
          onBlock={handleBlock}
          onWarn={handleWarn}
          onDismiss={handleDismiss}
          onViewUser={(uuid) => navigate(`/users/${uuid}`)}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Нарушения</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">
            Анти-абуз система и управление нарушениями
            {stats ? (
              <span className="text-dark-200 ml-1">
                — {stats.total} за{' '}
                {days === 1 ? 'сегодня' : days === 7 ? 'неделю' : days === 30 ? 'месяц' : `${days} дн`}
              </span>
            ) : null}
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
            onClick={() => {
              refetch()
              queryClient.invalidateQueries({ queryKey: ['violationStats'] })
              queryClient.invalidateQueries({ queryKey: ['topViolators'] })
            }}
            className="btn-secondary"
            disabled={isLoading}
          >
            <HiRefresh className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="card animate-fade-in-down">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4">
            <div>
              <label className="block text-xs text-dark-200 mb-1">Уровень</label>
              <select
                value={severity}
                onChange={(e) => {
                  setSeverity(e.target.value)
                  setPage(1)
                }}
                className="input"
              >
                <option value="">Все</option>
                <option value="critical">Критический</option>
                <option value="high">Высокий</option>
                <option value="medium">Средний</option>
                <option value="low">Низкий</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">Период</label>
              <select
                value={days}
                onChange={(e) => {
                  setDays(Number(e.target.value))
                  setPage(1)
                }}
                className="input"
              >
                <option value={1}>Сегодня</option>
                <option value={7}>Неделя</option>
                <option value={30}>Месяц</option>
                <option value={90}>3 месяца</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-dark-200 mb-1">
                Мин. скор: {minScore}
              </label>
              <input
                type="range"
                min={0}
                max={90}
                step={10}
                value={minScore}
                onChange={(e) => {
                  setMinScore(Number(e.target.value))
                  setPage(1)
                }}
                className="w-full h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={() => {
                  setSeverity('')
                  setDays(7)
                  setMinScore(0)
                  setPage(1)
                }}
                className="btn-ghost text-sm w-full"
              >
                Сбросить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-dark-800/50 rounded-lg p-1 animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        {([
          { key: 'all' as Tab, label: 'Все', count: stats?.total },
          { key: 'pending' as Tab, label: 'Ожидают', count: undefined },
          { key: 'top' as Tab, label: 'Топ нарушителей', count: undefined },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => handleTabChange(t.key)}
            className={`flex-1 sm:flex-none px-3 sm:px-4 py-2 text-xs sm:text-sm rounded-md font-medium transition-all ${
              tab === t.key
                ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30'
                : 'text-dark-200 hover:text-white hover:bg-dark-700/50'
            }`}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="ml-1.5 text-xs opacity-70">({t.count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Stats section */}
      <StatsOverview stats={stats} />

      {/* Content based on tab */}
      {tab === 'top' ? (
        <TopViolatorsTab days={days} onViewUser={(uuid) => navigate(`/users/${uuid}`)} />
      ) : (
        <>
          {/* Violations list */}
          <div className="space-y-3">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => <ViolationSkeleton key={i} />)
            ) : violations.length === 0 ? (
              <div className="card text-center py-12">
                <HiCheck className="w-12 h-12 text-green-500 mx-auto mb-3" />
                <p className="text-dark-200 text-lg">
                  {tab === 'pending' ? 'Нет ожидающих нарушений' : 'Нарушений не обнаружено'}
                </p>
                <p className="text-sm text-dark-200 mt-1">
                  {tab === 'pending'
                    ? 'Все нарушения обработаны'
                    : 'За выбранный период нет записей о нарушениях'}
                </p>
              </div>
            ) : (
              violations.map((violation, i) => (
                <div
                  key={violation.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 0.04}s` }}
                >
                  <ViolationCard
                    violation={violation}
                    onBlock={() => handleBlock(violation.id)}
                    onWarn={() => handleWarn(violation.id)}
                    onDismiss={() => handleDismiss(violation.id)}
                    onViewDetail={() => setSelectedViolationId(violation.id)}
                    onViewUser={() => navigate(`/users/${violation.user_uuid}`)}
                  />
                </div>
              ))
            )}
          </div>

          {/* Pagination */}
          {total > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 animate-fade-in" style={{ animationDelay: '0.1s' }}>
              <p className="text-sm text-dark-200 order-2 sm:order-1">
                Показано {(page - 1) * perPage + 1}–
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
          )}
        </>
      )}
    </div>
  )
}
