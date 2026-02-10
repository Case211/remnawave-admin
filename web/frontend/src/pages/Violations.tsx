import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useHasPermission } from '@/components/PermissionGate'
import {
  ShieldAlert,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Check,
  Ban,
  X,
  Eye,
  AlertTriangle,
  Filter,
  Globe,
  Clock,
  User,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  MapPin,
  Server,
  Smartphone,
  Fingerprint,
  ArrowLeft,
  ExternalLink,
  MessageCircle,
} from 'lucide-react'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { InfoTooltip } from '@/components/InfoTooltip'
import { cn } from '@/lib/utils'
import { ExportDropdown } from '@/components/ExportDropdown'
import { SavedFiltersDropdown } from '@/components/SavedFiltersDropdown'
import { exportCSV, exportJSON } from '@/lib/export'

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
  ip?: string
  country?: string
  date_from?: string
  date_to?: string
}): Promise<PaginatedResponse> => {
  const p: Record<string, unknown> = {
    page: params.page,
    per_page: params.per_page,
    days: params.days,
  }
  if (params.severity) p.severity = params.severity
  if (params.resolved !== undefined) p.resolved = params.resolved
  if (params.min_score !== undefined && params.min_score > 0) p.min_score = params.min_score
  if (params.ip) p.ip = params.ip
  if (params.country) p.country = params.country
  if (params.date_from) p.date_from = params.date_from
  if (params.date_to) p.date_to = params.date_to
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
  const config: Record<string, { label: string; variant: 'destructive' | 'warning' | 'default' | 'secondary'; iconClass: string; bg: string }> = {
    critical: {
      label: 'Критический',
      variant: 'destructive',
      iconClass: 'text-red-400',
      bg: 'bg-red-500/10',
    },
    high: {
      label: 'Высокий',
      variant: 'warning',
      iconClass: 'text-yellow-400',
      bg: 'bg-yellow-500/10',
    },
    medium: {
      label: 'Средний',
      variant: 'default',
      iconClass: 'text-blue-400',
      bg: 'bg-blue-500/10',
    },
    low: {
      label: 'Низкий',
      variant: 'secondary',
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
  if (!action) return { label: 'Ожидает', variant: 'warning' as const }
  const config: Record<string, { label: string; variant: 'destructive' | 'default' | 'secondary' | 'success' | 'warning' }> = {
    block: { label: 'Заблокирован', variant: 'destructive' },
    blocked: { label: 'Заблокирован', variant: 'destructive' },
    warn: { label: 'Предупреждён', variant: 'default' },
    warned: { label: 'Предупреждён', variant: 'default' },
    ignore: { label: 'Отклонено', variant: 'secondary' },
    dismissed: { label: 'Отклонено', variant: 'secondary' },
    resolved: { label: 'Разрешено', variant: 'success' },
  }
  return config[action] || { label: action, variant: 'secondary' as const }
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
  canResolve,
  onBlock,
  onWarn,
  onDismiss,
  onViewDetail,
  onViewUser,
}: {
  violation: Violation
  canResolve: boolean
  onBlock: () => void
  onWarn: () => void
  onDismiss: () => void
  onViewDetail: () => void
  onViewUser: () => void
}) {
  const severityConfig = getSeverityConfig(violation.severity)
  const isPending = !violation.action_taken

  return (
    <Card className="hover:border-dark-400/40 transition-colors">
      <CardContent className="p-4">
        <div className="flex items-start gap-3 md:gap-4">
          {/* Severity icon */}
          <div className={`hidden sm:flex p-2.5 rounded-lg flex-shrink-0 ${severityConfig.bg}`}>
            {violation.severity === 'critical' ? (
              <AlertTriangle className={`w-6 h-6 ${severityConfig.iconClass}`} />
            ) : (
              <ShieldAlert className={`w-6 h-6 ${severityConfig.iconClass}`} />
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
                  <MessageCircle className="w-3.5 h-3.5 inline" />
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
              <Clock className="w-3.5 h-3.5" />
              {formatTimeAgo(violation.detected_at)}
            </p>
          </div>

          {/* Score */}
          <ScoreCircle score={violation.score} />
        </div>

        {/* Actions for pending violations */}
        {canResolve && isPending && (
          <div className="mt-4 pt-3 border-t border-dark-400/10 flex flex-wrap gap-2">
            <Button variant="destructive" size="sm" onClick={onBlock} className="gap-1">
              <Ban className="w-4 h-4" />
              <span className="hidden sm:inline">Заблокировать</span>
              <span className="sm:hidden">Блок</span>
            </Button>
            <Button variant="secondary" size="sm" onClick={onWarn} className="gap-1">
              <AlertTriangle className="w-4 h-4" />
              <span className="hidden sm:inline">Предупредить</span>
              <span className="sm:hidden">Пред.</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={onDismiss} className="gap-1">
              <X className="w-4 h-4" /> Отклонить
            </Button>
            <Button variant="ghost" size="sm" onClick={onViewDetail} className="gap-1 ml-auto">
              <Eye className="w-4 h-4" />
              <span className="hidden sm:inline">Подробнее</span>
            </Button>
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
              <Eye className="w-4 h-4" /> Подробнее
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Badges ───────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const config = getSeverityConfig(severity)
  return <Badge variant={config.variant}>{config.label}</Badge>
}

function ActionBadge({ action }: { action: string | null }) {
  const config = getActionConfig(action)
  return <Badge variant={config.variant}>{config.label}</Badge>
}

// ── Detail panel ─────────────────────────────────────────────────

interface HwidDevice {
  hwid: string
  platform: string | null
  os_version: string | null
  device_model: string | null
  app_version: string | null
  user_agent: string | null
  created_at: string | null
  updated_at: string | null
}

function getPlatformInfo(platform: string | null): { icon: string; label: string } {
  const p = (platform || '').toLowerCase()
  if (p.includes('windows') || p === 'win') return { icon: '🖥️', label: 'Windows' }
  if (p.includes('android')) return { icon: '📱', label: 'Android' }
  if (p.includes('ios') || p.includes('iphone') || p.includes('ipad')) return { icon: '📱', label: 'iOS' }
  if (p.includes('macos') || p.includes('mac') || p.includes('darwin')) return { icon: '💻', label: 'macOS' }
  if (p.includes('linux')) return { icon: '🐧', label: 'Linux' }
  return { icon: '📟', label: platform || 'Неизвестно' }
}

function ViolationDetailPanel({
  violationId,
  canResolve,
  onClose,
  onBlock,
  onWarn,
  onDismiss,
  onViewUser,
}: {
  violationId: number
  canResolve: boolean
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

  // Fetch HWID devices for the violation's user
  const { data: hwidDevices } = useQuery<HwidDevice[]>({
    queryKey: ['violation-user-hwid-devices', detail?.user_uuid],
    queryFn: async () => {
      const response = await client.get(`/users/${detail!.user_uuid}/hwid-devices`)
      return response.data
    },
    enabled: !!detail?.user_uuid,
  })

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={onClose}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <Skeleton className="h-6 w-48" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <Skeleton className="h-4 w-32 mb-3" />
              <Skeleton className="h-20 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={onClose} className="gap-2">
          <ArrowLeft className="w-5 h-5" /> Назад
        </Button>
        <Card>
          <CardContent className="text-center py-8 text-dark-200">Нарушение не найдено</CardContent>
        </Card>
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
        <Button variant="ghost" size="icon" onClick={onClose}>
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-bold text-white truncate">
            Нарушение #{detail.id}
          </h2>
          <p className="text-sm text-dark-200">{formatDate(detail.detected_at)}</p>
        </div>
        <ScoreCircle score={detail.score} size="lg" />
      </div>

      {/* User info card */}
      <Card className="animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            Пользователь
          </h3>
          <div className="flex flex-wrap items-center gap-3">
            <div className={`p-2 rounded-lg ${severityConfig.bg}`}>
              <User className={`w-5 h-5 ${severityConfig.iconClass}`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-white">{detail.username || 'Неизвестный'}</p>
              {detail.email && <p className="text-sm text-dark-200 truncate">{detail.email}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <SeverityBadge severity={severity} />
              <ActionBadge action={detail.action_taken} />
            </div>
            <Button variant="secondary" size="sm" onClick={() => onViewUser(detail.user_uuid)} className="gap-1">
              <ExternalLink className="w-4 h-4" /> Профиль
            </Button>
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
        </CardContent>
      </Card>

      {/* Score breakdown */}
      <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-4">
            Разбор скоринга
          </h3>
          <div className="space-y-3">
            <ScoreBar
              label="Временной"
              score={detail.temporal_score}
              icon={<Clock className="w-4 h-4" />}
            />
            <ScoreBar
              label="Гео"
              score={detail.geo_score}
              icon={<Globe className="w-4 h-4" />}
            />
            <ScoreBar
              label="Провайдер"
              score={detail.asn_score}
              icon={<Server className="w-4 h-4" />}
            />
            <ScoreBar
              label="Профиль"
              score={detail.profile_score}
              icon={<Fingerprint className="w-4 h-4" />}
            />
            <ScoreBar
              label="Устройство"
              score={detail.device_score}
              icon={<Smartphone className="w-4 h-4" />}
            />
          </div>
          <div className="mt-4 pt-3 border-t border-dark-400/10 flex items-center justify-between">
            <span className="text-sm text-dark-200">Итоговый скор</span>
            <span className={`text-lg font-bold ${getScoreColor(detail.score)}`}>
              {Math.round(detail.score)} / 100
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Reasons */}
      {detail.reasons.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              Причины ({detail.reasons.length})
            </h3>
            <ul className="space-y-2">
              {detail.reasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
                  <span className="text-dark-100">{reason}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Geo & Network info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Countries */}
        {detail.countries.length > 0 && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <CardContent className="p-4">
              <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
                <MapPin className="w-4 h-4 inline mr-1" />
                Страны
              </h3>
              <div className="flex flex-wrap gap-2">
                {detail.countries.map((country, i) => (
                  <Badge key={i} variant="default">{country}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ASN types */}
        {detail.asn_types.length > 0 && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
            <CardContent className="p-4">
              <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
                <Server className="w-4 h-4 inline mr-1" />
                Типы провайдеров
              </h3>
              <div className="flex flex-wrap gap-2">
                {detail.asn_types.map((asn, i) => (
                  <Badge key={i} variant="secondary">{asn}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* IPs */}
      {detail.ips.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardContent className="p-4">
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
          </CardContent>
        </Card>
      )}

      {/* HWID Devices */}
      {hwidDevices && hwidDevices.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.32s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              <Smartphone className="w-4 h-4 inline mr-1" />
              Устройства ({hwidDevices.length})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {hwidDevices.map((device, idx) => {
                const pi = getPlatformInfo(device.platform)
                return (
                  <div
                    key={device.hwid || idx}
                    className="bg-dark-800/80 rounded-lg p-3 border border-dark-600/20"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-base">{pi.icon}</span>
                      <span className="text-sm font-medium text-white">{pi.label}</span>
                      <span className="text-[10px] text-dark-400 bg-dark-700/50 px-1.5 py-0.5 rounded font-mono ml-auto">
                        #{idx + 1}
                      </span>
                    </div>
                    <div className="space-y-1 text-xs">
                      {device.device_model && (
                        <div className="flex justify-between">
                          <span className="text-dark-300">Модель</span>
                          <span className="text-dark-100 truncate ml-2 max-w-[60%] text-right">{device.device_model}</span>
                        </div>
                      )}
                      {device.os_version && (
                        <div className="flex justify-between">
                          <span className="text-dark-300">ОС</span>
                          <span className="text-dark-100 truncate ml-2 max-w-[60%] text-right">{device.os_version}</span>
                        </div>
                      )}
                      {device.user_agent && (
                        <div className="flex justify-between">
                          <span className="text-dark-300">User-Agent</span>
                          <span className="text-dark-100 truncate ml-2 max-w-[60%] text-right" title={device.user_agent}>{device.user_agent}</span>
                        </div>
                      )}
                      {device.created_at && (
                        <div className="flex justify-between">
                          <span className="text-dark-300">Добавлено</span>
                          <span className="text-dark-100">{formatDate(device.created_at)}</span>
                        </div>
                      )}
                    </div>
                    {device.hwid && (
                      <p className="text-[10px] text-dark-400 font-mono mt-1.5 truncate" title={device.hwid}>
                        HWID: {device.hwid}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Admin action resolution info */}
      {detail.action_taken && detail.action_taken_at && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              Решение администратора
            </h3>
            <div className="flex items-center gap-3">
              <ActionBadge action={detail.action_taken} />
              <span className="text-sm text-dark-200">
                {formatDate(detail.action_taken_at)}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Action buttons for pending */}
      {canResolve && isPending && (
        <Card className="animate-fade-in-up border-primary-500/20" style={{ animationDelay: '0.35s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              Принять решение
            </h3>
            <div className="flex flex-wrap gap-3">
              <Button variant="destructive" onClick={() => onBlock(detail.id)} className="gap-2">
                <Ban className="w-4 h-4" /> Заблокировать
              </Button>
              <Button variant="secondary" onClick={() => onWarn(detail.id)} className="gap-2">
                <AlertTriangle className="w-4 h-4" /> Предупредить
              </Button>
              <Button variant="ghost" onClick={() => onDismiss(detail.id)} className="gap-2">
                <X className="w-4 h-4" /> Отклонить
              </Button>
            </div>
          </CardContent>
        </Card>
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
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <Skeleton className="w-10 h-10 rounded-full" />
                <div className="flex-1">
                  <Skeleton className="h-4 w-32 mb-2" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!violators?.length) {
    return (
      <Card className="text-center py-12">
        <CardContent>
          <Check className="w-12 h-12 text-green-500 mx-auto mb-3" />
          <p className="text-dark-200">Нет нарушителей за период</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {violators.map((v, i) => {
        const severity = getSeverityFromScore(v.max_score)
        return (
          <Card
            key={v.user_uuid}
            className="animate-fade-in-up hover:border-dark-400/40 transition-colors"
            style={{ animationDelay: `${i * 0.05}s` }}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3 md:gap-4">
                {/* Rank */}
                <div className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0',
                  i === 0 ? 'bg-red-500/20 text-red-400' :
                  i === 1 ? 'bg-yellow-500/20 text-yellow-400' :
                  i === 2 ? 'bg-orange-500/20 text-orange-400' :
                  'bg-dark-600/50 text-dark-200'
                )}>
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
                      <ShieldAlert className="w-3.5 h-3.5 inline mr-0.5" />
                      {v.violations_count} нарушени{v.violations_count === 1 ? 'е' : v.violations_count < 5 ? 'я' : 'й'}
                    </span>
                    <span>Макс: {Math.round(v.max_score)}</span>
                    <span>Средн: {Math.round(v.avg_score)}</span>
                    <span>
                      <Clock className="w-3.5 h-3.5 inline mr-0.5" />
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
            </CardContent>
          </Card>
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
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">Критические</p>
              <InfoTooltip text="Скор 80–100. Серьёзные аномалии, требующие немедленного вмешательства." side="bottom" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">{stats.critical}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">Высокие</p>
              <InfoTooltip text="Скор 60–79. Подозрительная активность, рекомендуется проверка." side="bottom" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-yellow-400 mt-1">{stats.high}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">Средние</p>
              <InfoTooltip text="Скор 40–59. Незначительные отклонения, рекомендуется мониторинг." side="bottom" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-blue-400 mt-1">{stats.medium}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">Низкие</p>
              <InfoTooltip text="Скор 0–39. Информационные уведомления, не требующие действий." side="bottom" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">{stats.low}</p>
          </CardContent>
        </Card>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4">
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-primary-400" />
              <div>
                <div className="flex items-center gap-1">
                  <p className="text-xs text-dark-200">Всего</p>
                  <InfoTooltip text="Общее количество зафиксированных нарушений за выбранный период." side="bottom" iconClassName="w-3 h-3" />
                </div>
                <p className="text-lg font-bold text-white">{stats.total}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <User className="w-5 h-5 text-primary-400" />
              <div>
                <div className="flex items-center gap-1">
                  <p className="text-xs text-dark-200">Уник. юзеров</p>
                  <InfoTooltip text="Количество уникальных пользователей с нарушениями за выбранный период. Один пользователь может иметь несколько нарушений." side="bottom" iconClassName="w-3 h-3" />
                </div>
                <p className="text-lg font-bold text-white">{stats.unique_users}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.35s' }}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-primary-400" />
              <div>
                <div className="flex items-center gap-1">
                  <p className="text-xs text-dark-200">Средн. скор</p>
                  <InfoTooltip text="Средний скор нарушений (0–100). Рассчитывается на основе временных, геолокационных, ASN, профильных и устройственных аномалий." side="bottom" iconClassName="w-3 h-3" />
                </div>
                <p className="text-lg font-bold text-white">{Math.round(stats.avg_score)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              <div>
                <div className="flex items-center gap-1">
                  <p className="text-xs text-dark-200">Макс. скор</p>
                  <InfoTooltip text="Наивысший зафиксированный скор нарушения за выбранный период. Чем выше скор, тем больше аномалий обнаружено." side="bottom" iconClassName="w-3 h-3" />
                </div>
                <p className="text-lg font-bold text-white">{Math.round(stats.max_score)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Countries (collapsible) */}
      {countryEntries.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.45s' }}>
          <CardContent className="p-0">
            <button
              onClick={() => setShowCountries(!showCountries)}
              className="flex items-center justify-between w-full text-left p-4"
            >
              <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider flex items-center gap-2">
                <Globe className="w-4 h-4" />
                По странам ({countryEntries.length})
              </h3>
              {showCountries ? (
                <ChevronUp className="w-5 h-5 text-dark-200" />
              ) : (
                <ChevronDown className="w-5 h-5 text-dark-200" />
              )}
            </button>
            {showCountries && (
              <div className="px-4 pb-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 animate-fade-in-down">
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
          </CardContent>
        </Card>
      )}
    </>
  )
}

// ── Loading skeleton ─────────────────────────────────────────────

function ViolationSkeleton() {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          <Skeleton className="w-11 h-11 rounded-lg hidden sm:block" />
          <div className="flex-1">
            <div className="flex gap-2 mb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
            <Skeleton className="h-3 w-48 mb-2" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="w-14 h-14 rounded-full" />
        </div>
      </CardContent>
    </Card>
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
  const [ipFilter, setIpFilter] = useState('')
  const [countryFilter, setCountryFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [selectedViolationId, setSelectedViolationId] = useState<number | null>(null)

  const canResolve = useHasPermission('violations', 'resolve')

  // Export handlers
  const handleExportCSV = () => {
    const items = data?.items
    if (!items?.length) return
    const exportData = items.map((v: Violation) => ({
      date: v.detected_at || '',
      username: v.username || '',
      score: v.score,
      severity: v.severity,
      reasons: v.reasons?.join('; ') || '',
      countries: v.countries?.join(', ') || '',
      recommendation: v.recommended_action || '',
      status: v.status || '',
    }))
    exportCSV(exportData, `violations-${new Date().toISOString().slice(0, 10)}`)
    toast.success('Экспорт CSV завершён')
  }
  const handleExportJSON = () => {
    const items = data?.items
    if (!items?.length) return
    exportJSON(items, `violations-${new Date().toISOString().slice(0, 10)}`)
    toast.success('Экспорт JSON завершён')
  }

  // Saved filters
  const currentViolationFilters: Record<string, unknown> = {
    ...(severity && { severity }),
    ...(days !== 7 && { days }),
    ...(minScore > 0 && { minScore }),
    ...(ipFilter && { ipFilter }),
    ...(countryFilter && { countryFilter }),
    ...(dateFrom && { dateFrom }),
    ...(dateTo && { dateTo }),
  }
  const hasActiveViolationFilters = Object.keys(currentViolationFilters).length > 0
  const handleLoadViolationFilter = (filters: Record<string, unknown>) => {
    setSeverity((filters.severity as string) || '')
    setDays((filters.days as number) || 7)
    setMinScore((filters.minScore as number) || 0)
    setIpFilter((filters.ipFilter as string) || '')
    setCountryFilter((filters.countryFilter as string) || '')
    setDateFrom((filters.dateFrom as string) || '')
    setDateTo((filters.dateTo as string) || '')
    setShowFilters(true)
    setPage(1)
  }

  // Derived filter for resolved status
  const resolved = tab === 'pending' ? false : undefined

  // Fetch violations list
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['violations', page, perPage, severity, days, resolved, minScore, ipFilter, countryFilter, dateFrom, dateTo],
    queryFn: () =>
      fetchViolations({
        page,
        per_page: perPage,
        severity: severity || undefined,
        days,
        resolved,
        min_score: minScore,
        ...(ipFilter && { ip: ipFilter }),
        ...(countryFilter && { country: countryFilter }),
        ...(dateFrom && { date_from: dateFrom }),
        ...(dateTo && { date_to: dateTo }),
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
      toast.success('Нарушение обработано')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || 'Ошибка')
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
          canResolve={canResolve}
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
          <div className="flex items-center gap-2">
            <h1 className="page-header-title">Нарушения</h1>
            <InfoTooltip
              text="Система анти-абуза анализирует подключения пользователей и выявляет аномалии: подозрительные гео-перемещения, множественные ASN, необычные устройства и другие отклонения. Скор от 0 до 100 показывает степень подозрительности."
              side="right"
            />
          </div>
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
          <Button
            variant="secondary"
            onClick={() => setShowFilters(!showFilters)}
            className={cn('gap-2', showFilters && 'ring-2 ring-primary-500')}
          >
            <Filter className="w-4 h-4" />
            <span className="hidden sm:inline">Фильтры</span>
          </Button>
          <Button
            variant="secondary"
            size="icon"
            onClick={() => {
              refetch()
              queryClient.invalidateQueries({ queryKey: ['violationStats'] })
              queryClient.invalidateQueries({ queryKey: ['topViolators'] })
            }}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-5 h-5', isLoading && 'animate-spin')} />
          </Button>
          <ExportDropdown
            onExportCSV={handleExportCSV}
            onExportJSON={handleExportJSON}
            disabled={!data?.items?.length}
          />
          <SavedFiltersDropdown
            page="violations"
            currentFilters={currentViolationFilters}
            onLoadFilter={handleLoadViolationFilter}
            hasActiveFilters={hasActiveViolationFilters}
          />
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <Card className="animate-fade-in-down">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-4">
              <div>
                <label className="block text-xs text-dark-200 mb-1">Уровень</label>
                <select
                  value={severity}
                  onChange={(e) => {
                    setSeverity(e.target.value)
                    setPage(1)
                  }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
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
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
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
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSeverity('')
                    setDays(7)
                    setMinScore(0)
                    setPage(1)
                  }}
                  className="w-full"
                >
                  Сбросить
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
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
            className={cn(
              'flex-1 sm:flex-none px-3 sm:px-4 py-2 text-xs sm:text-sm rounded-md font-medium transition-all',
              tab === t.key
                ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30'
                : 'text-dark-200 hover:text-white hover:bg-dark-700/50'
            )}
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
              <Card className="text-center py-12">
                <CardContent>
                  <Check className="w-12 h-12 text-green-500 mx-auto mb-3" />
                  <p className="text-dark-200 text-lg">
                    {tab === 'pending' ? 'Нет ожидающих нарушений' : 'Нарушений не обнаружено'}
                  </p>
                  <p className="text-sm text-dark-200 mt-1">
                    {tab === 'pending'
                      ? 'Все нарушения обработаны'
                      : 'За выбранный период нет записей о нарушениях'}
                  </p>
                </CardContent>
              </Card>
            ) : (
              violations.map((violation, i) => (
                <div
                  key={violation.id}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${i * 0.04}s` }}
                >
                  <ViolationCard
                    violation={violation}
                    canResolve={canResolve}
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
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={() => setPage(page - 1)}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="w-5 h-5" />
                </Button>
                <span className="text-sm text-dark-200 min-w-[80px] text-center">
                  {page} / {pages}
                </span>
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={() => setPage(page + 1)}
                  disabled={page >= pages}
                >
                  <ChevronRight className="w-5 h-5" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
