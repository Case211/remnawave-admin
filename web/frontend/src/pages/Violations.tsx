import { useState, useCallback, useEffect, memo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { useHasPermission } from '@/components/PermissionGate'
import { useFormatters } from '@/lib/useFormatters'
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
  Users,
  ArrowLeft,
  ExternalLink,
  MessageCircle,
  XCircle,
  Trash2,
  ShieldOff,
  ShieldCheck,
  Plus,
  Calendar,
} from 'lucide-react'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { InfoTooltip } from '@/components/InfoTooltip'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { ExportDropdown } from '@/components/ExportDropdown'
import { SavedFiltersDropdown } from '@/components/SavedFiltersDropdown'
import { exportCSV, exportJSON } from '@/lib/export'
import Reports from './Reports'
import type {
  Violation,
  ViolationDetail,
  ViolationStats,
  PaginatedResponse,
  TopViolator,
  IPInfo,
  WhitelistItem,
} from '@/types/violations'

const ANALYZER_KEYS = ['temporal', 'geo', 'asn', 'profile', 'device', 'hwid'] as const

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

const fetchWhitelist = async (limit: number, offset: number): Promise<{ items: WhitelistItem[]; total: number }> => {
  const { data } = await client.get('/violations/whitelist', { params: { limit, offset } })
  return data
}

// ── Utilities ────────────────────────────────────────────────────

function getSeverityConfig(severity: string) {
  const config: Record<string, { labelKey: string; variant: 'destructive' | 'warning' | 'default' | 'secondary'; iconClass: string; bg: string }> = {
    critical: {
      labelKey: 'violations.severity.critical',
      variant: 'destructive',
      iconClass: 'text-red-400',
      bg: 'bg-red-500/10',
    },
    high: {
      labelKey: 'violations.severity.high',
      variant: 'warning',
      iconClass: 'text-yellow-400',
      bg: 'bg-yellow-500/10',
    },
    medium: {
      labelKey: 'violations.severity.medium',
      variant: 'default',
      iconClass: 'text-blue-400',
      bg: 'bg-blue-500/10',
    },
    low: {
      labelKey: 'violations.severity.low',
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
  if (!action) return { labelKey: 'violations.actionStatuses.pending', variant: 'warning' as const }
  const config: Record<string, { labelKey: string; variant: 'destructive' | 'default' | 'secondary' | 'success' | 'warning' }> = {
    block: { labelKey: 'violations.actionStatuses.blocked', variant: 'destructive' },
    blocked: { labelKey: 'violations.actionStatuses.blocked', variant: 'destructive' },
    warn: { labelKey: 'violations.actionStatuses.warned', variant: 'default' },
    warned: { labelKey: 'violations.actionStatuses.warned', variant: 'default' },
    ignore: { labelKey: 'violations.actionStatuses.dismissed', variant: 'secondary' },
    dismissed: { labelKey: 'violations.actionStatuses.dismissed', variant: 'secondary' },
    annulled: { labelKey: 'violations.actionStatuses.annulled', variant: 'secondary' },
    resolved: { labelKey: 'violations.actionStatuses.resolved', variant: 'success' },
  }
  return config[action] || { labelKey: action, variant: 'secondary' as const }
}

function getRecommendedActionLabelKey(action: string): string {
  const keys: Record<string, string> = {
    no_action: 'violations.recommendedActions.no_action',
    monitor: 'violations.recommendedActions.monitor',
    warn: 'violations.recommendedActions.warn',
    soft_block: 'violations.recommendedActions.soft_block',
    temp_block: 'violations.recommendedActions.temp_block',
    hard_block: 'violations.recommendedActions.hard_block',
  }
  return keys[action] || action
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

function getConnectionTypeLabelKey(type: string | null): string | null {
  if (!type) return null
  const keys: Record<string, string> = {
    residential: 'violations.connectionTypes.residential',
    mobile: 'violations.connectionTypes.mobile',
    mobile_isp: 'violations.connectionTypes.mobile_isp',
    datacenter: 'violations.connectionTypes.datacenter',
    hosting: 'violations.connectionTypes.hosting',
    vpn: 'violations.connectionTypes.vpn',
    unknown: 'violations.connectionTypes.unknown',
  }
  return keys[type] || type
}

function getConnectionTypeBadge(info: IPInfo, t: (key: string) => string): { label: string; cls: string } | null {
  if (info.is_vpn) return { label: 'VPN', cls: 'text-red-400 bg-red-500/10 border-red-500/30' }
  if (info.is_proxy) return { label: 'Proxy', cls: 'text-orange-400 bg-orange-500/10 border-orange-500/30' }
  if (info.is_hosting) return { label: t('violations.connectionTypes.hosting'), cls: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30' }
  if (info.is_mobile) return { label: t('violations.connectionTypes.mobileShort'), cls: 'text-blue-400 bg-blue-500/10 border-blue-500/30' }
  const typeLabelKey = getConnectionTypeLabelKey(info.connection_type)
  if (typeLabelKey && info.connection_type !== 'unknown') {
    return { label: t(typeLabelKey), cls: 'text-dark-200 bg-dark-600/50 border-dark-400/30' }
  }
  return null
}

// ── Score bar component ──────────────────────────────────────────

const ScoreBar = memo(function ScoreBar({ label, score, weight, icon }: { label: string; score: number; weight?: number; icon: React.ReactNode }) {
  const barColor =
    score >= 60 ? 'bg-red-500' : score >= 40 ? 'bg-yellow-500' : score >= 20 ? 'bg-blue-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 w-40 flex-shrink-0">
        <span className="text-dark-200">{icon}</span>
        <span className="text-sm text-dark-100">{label}</span>
        {weight != null && (
          <span className="text-xs text-dark-400">×{weight}</span>
        )}
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
})

// ── Score circle component ───────────────────────────────────────

const ScoreCircle = memo(function ScoreCircle({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' | 'lg' }) {
  const sizeMap = { sm: 'w-10 h-10', md: 'w-14 h-14', lg: 'w-20 h-20' }
  const textMap = { sm: 'text-sm', md: 'text-xl', lg: 'text-3xl' }
  return (
    <div
      className={`${sizeMap[size]} rounded-full ${getScoreBg(score)} flex items-center justify-center flex-shrink-0`}
    >
      <span className={`font-bold ${getScoreColor(score)} ${textMap[size]}`}>{Math.round(score)}</span>
    </div>
  )
})

// ── Violation card ───────────────────────────────────────────────

const ViolationCard = memo(function ViolationCard({
  violation,
  canResolve,
  onBlock,
  onWarn,
  onDismiss,
  onAnnul,
  onWhitelist,
  onViewDetail,
  onViewUser,
}: {
  violation: Violation
  canResolve: boolean
  onBlock: () => void
  onWarn: () => void
  onDismiss: () => void
  onAnnul: () => void
  onWhitelist: () => void
  onViewDetail: () => void
  onViewUser: () => void
}) {
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()
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
                {violation.username || violation.email || t('common.unknown')}
              </button>
              <SeverityBadge severity={violation.severity} />
              <ActionBadge action={violation.action_taken} />
              {violation.notified && (
                <span className="text-xs text-dark-200" title={t('violations.notified')}>
                  <MessageCircle className="w-3.5 h-3.5 inline" />
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-dark-200 mb-1">
              <span className={getRecommendedActionClass(violation.recommended_action)}>
                {t(getRecommendedActionLabelKey(violation.recommended_action))}
              </span>
              {violation.confidence > 0 && (
                <span>{t('violations.confidence')}: {Math.round(violation.confidence * 100)}%</span>
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
              <span className="hidden sm:inline">{t('violations.actions.block')}</span>
              <span className="sm:hidden">{t('violations.actions.blockShort')}</span>
            </Button>
            <Button variant="secondary" size="sm" onClick={onWarn} className="gap-1">
              <AlertTriangle className="w-4 h-4" />
              <span className="hidden sm:inline">{t('violations.actions.warn')}</span>
              <span className="sm:hidden">{t('violations.actions.warnShort')}</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={onDismiss} className="gap-1">
              <X className="w-4 h-4" /> {t('violations.actions.dismiss')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onAnnul} className="gap-1 text-dark-300 hover:text-dark-100">
              <XCircle className="w-4 h-4" /> {t('violations.actions.annul')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onWhitelist} className="gap-1 text-dark-300 hover:text-emerald-400" title={t('violations.whitelist.addButton')}>
              <ShieldOff className="w-4 h-4" />
              <span className="hidden sm:inline">{t('violations.whitelist.addButton')}</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={onViewDetail} className="gap-1 ml-auto">
              <Eye className="w-4 h-4" />
              <span className="hidden sm:inline">{t('common.details')}</span>
            </Button>
          </div>
        )}

        {/* Resolved footer */}
        {!isPending && (
          <div className="mt-4 pt-3 border-t border-dark-400/10 flex items-center justify-between text-xs text-dark-200">
            <span>{t('violations.actionLabel')}: {t(getActionConfig(violation.action_taken).labelKey)}</span>
            <button
              onClick={onViewDetail}
              className="text-primary-400 hover:text-primary-300 flex items-center gap-1 transition-colors"
            >
              <Eye className="w-4 h-4" /> {t('common.details')}
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  )
})

// ── Badges ───────────────────────────────────────────────────────

const SeverityBadge = memo(function SeverityBadge({ severity }: { severity: string }) {
  const { t } = useTranslation()
  const config = getSeverityConfig(severity)
  return <Badge variant={config.variant}>{t(config.labelKey)}</Badge>
})

const ActionBadge = memo(function ActionBadge({ action }: { action: string | null }) {
  const { t } = useTranslation()
  const config = getActionConfig(action)
  return <Badge variant={config.variant}>{t(config.labelKey)}</Badge>
})

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

function getPlatformInfo(platform: string | null, unknownLabel: string): { icon: string; label: string } {
  const p = (platform || '').toLowerCase()
  if (p.includes('windows') || p === 'win') return { icon: '🖥️', label: 'Windows' }
  if (p.includes('android')) return { icon: '📱', label: 'Android' }
  if (p.includes('ios') || p.includes('iphone') || p.includes('ipad')) return { icon: '📱', label: 'iOS' }
  if (p.includes('macos') || p.includes('mac') || p.includes('darwin')) return { icon: '💻', label: 'macOS' }
  if (p.includes('linux')) return { icon: '🐧', label: 'Linux' }
  return { icon: '📟', label: platform || unknownLabel }
}

function ViolationDetailPanel({
  violationId,
  canResolve,
  onClose,
  onBlock,
  onWarn,
  onDismiss,
  onAnnul,
  onAnnulAll,
  onWhitelist,
  onViewUser,
}: {
  violationId: number
  canResolve: boolean
  onClose: () => void
  onBlock: (id: number) => void
  onWarn: (id: number) => void
  onDismiss: (id: number) => void
  onAnnul: (id: number) => void
  onAnnulAll: (userUuid: string) => void
  onWhitelist: (userUuid: string) => void
  onViewUser: (uuid: string) => void
}) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()

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
          <ArrowLeft className="w-5 h-5" /> {t('common.back')}
        </Button>
        <Card>
          <CardContent className="text-center py-8 text-dark-200">{t('violations.detail.notFound')}</CardContent>
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
            {t('violations.detail.title', { id: detail.id })}
          </h2>
          <p className="text-sm text-dark-200">{formatDate(detail.detected_at)}</p>
        </div>
        <ScoreCircle score={detail.score} size="lg" />
      </div>

      {/* User info card */}
      <Card className="animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
            {t('violations.detail.user')}
          </h3>
          <div className="flex flex-wrap items-center gap-3">
            <div className={`p-2 rounded-lg ${severityConfig.bg}`}>
              <User className={`w-5 h-5 ${severityConfig.iconClass}`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-white">{detail.username || t('common.unknown')}</p>
              {detail.email && <p className="text-sm text-dark-200 truncate">{detail.email}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <SeverityBadge severity={severity} />
              <ActionBadge action={detail.action_taken} />
            </div>
            <Button variant="secondary" size="sm" onClick={() => onViewUser(detail.user_uuid)} className="gap-1">
              <ExternalLink className="w-4 h-4" /> {t('common.profile')}
            </Button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
            <div className="text-center p-2 rounded-lg bg-dark-800/50">
              <p className="text-xs text-dark-200">{t('violations.detail.recommendation')}</p>
              <p className={`text-sm font-medium ${getRecommendedActionClass(detail.recommended_action)}`}>
                {t(getRecommendedActionLabelKey(detail.recommended_action))}
              </p>
            </div>
            <div className="text-center p-2 rounded-lg bg-dark-800/50">
              <p className="text-xs text-dark-200">{t('violations.confidence')}</p>
              <p className="text-sm font-medium text-white">
                {Math.round(detail.confidence * 100)}%
              </p>
            </div>
            <div className="text-center p-2 rounded-lg bg-dark-800/50">
              <p className="text-xs text-dark-200">{t('violations.detail.countries')}</p>
              <p className="text-sm font-medium text-white">{detail.countries.length}</p>
            </div>
            <div className="text-center p-2 rounded-lg bg-dark-800/50">
              <p className="text-xs text-dark-200">{t('violations.detail.ipAddresses')}</p>
              <p className="text-sm font-medium text-white">{detail.ips.length}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Score breakdown */}
      <Card className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-4">
            {t('violations.detail.scoreBreakdown')}
          </h3>
          <div className="space-y-3">
            <ScoreBar
              label={t('violations.detail.temporal')}
              score={detail.temporal_score}
              weight={0.20}
              icon={<Clock className="w-4 h-4" />}
            />
            <ScoreBar
              label={t('violations.detail.geo')}
              score={detail.geo_score}
              weight={0.20}
              icon={<Globe className="w-4 h-4" />}
            />
            <ScoreBar
              label={t('violations.detail.provider')}
              score={detail.asn_score}
              weight={0.10}
              icon={<Server className="w-4 h-4" />}
            />
            <ScoreBar
              label={t('violations.detail.profileScore')}
              score={detail.profile_score}
              weight={0.15}
              icon={<Fingerprint className="w-4 h-4" />}
            />
            <ScoreBar
              label={t('violations.detail.device')}
              score={detail.device_score}
              weight={0.10}
              icon={<Smartphone className="w-4 h-4" />}
            />
            <ScoreBar
              label={t('violations.detail.hwid')}
              score={detail.hwid_score}
              weight={0.25}
              icon={<Users className="w-4 h-4" />}
            />
          </div>
          <div className="mt-4 pt-3 border-t border-dark-400/10 flex items-center justify-between">
            <span className="text-sm text-dark-200">{t('violations.detail.finalScore')}</span>
            <span className={`text-lg font-bold ${getScoreColor(detail.score)}`}>
              {Math.round(detail.score)} / 100
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Reasons */}
      {Array.isArray(detail.reasons) && detail.reasons.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              {t('violations.detail.reasons')} ({detail.reasons.length})
            </h3>
            <ul className="space-y-2">
              {(Array.isArray(detail.reasons) ? detail.reasons : []).map((reason, i) => (
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
        {Array.isArray(detail.countries) && detail.countries.length > 0 && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <CardContent className="p-4">
              <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
                <MapPin className="w-4 h-4 inline mr-1" />
                {t('violations.detail.countriesTitle')}
              </h3>
              <div className="flex flex-wrap gap-2">
                {(Array.isArray(detail.countries) ? detail.countries : []).map((country, i) => (
                  <Badge key={i} variant="default">{country}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ASN types */}
        {Array.isArray(detail.asn_types) && detail.asn_types.length > 0 && (
          <Card className="animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
            <CardContent className="p-4">
              <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
                <Server className="w-4 h-4 inline mr-1" />
                {t('violations.detail.providerTypes')}
              </h3>
              <div className="flex flex-wrap gap-2">
                {(Array.isArray(detail.asn_types) ? detail.asn_types : []).map((asn, i) => (
                  <Badge key={i} variant="secondary">{asn}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* IPs */}
      {Array.isArray(detail.ips) && detail.ips.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              {t('violations.detail.ipTitle')} ({detail.ips.length})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {(Array.isArray(detail.ips) ? detail.ips : []).map((ip, i) => {
                const info = ipInfo?.[ip]
                const badge = info ? getConnectionTypeBadge(info, t) : null
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
      {Array.isArray(hwidDevices) && hwidDevices.length > 0 && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.32s' }}>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-dark-200 uppercase tracking-wider mb-3">
              <Smartphone className="w-4 h-4 inline mr-1" />
              {t('violations.detail.devicesTitle')} ({hwidDevices.length})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {hwidDevices.map((device, idx) => {
                const pi = getPlatformInfo(device.platform, t('common.unknown'))
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
                          <span className="text-dark-300">{t('violations.detail.model')}</span>
                          <span className="text-dark-100 truncate ml-2 max-w-[60%] text-right">{device.device_model}</span>
                        </div>
                      )}
                      {device.os_version && (
                        <div className="flex justify-between">
                          <span className="text-dark-300">{t('violations.detail.os')}</span>
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
                          <span className="text-dark-300">{t('violations.detail.addedAt')}</span>
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
              {t('violations.detail.adminDecision')}
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
              {t('violations.actions.resolve')}
            </h3>
            <div className="flex flex-wrap gap-3">
              <Button variant="destructive" onClick={() => onBlock(detail.id)} className="gap-2">
                <Ban className="w-4 h-4" /> {t('violations.actions.block')}
              </Button>
              <Button variant="secondary" onClick={() => onWarn(detail.id)} className="gap-2">
                <AlertTriangle className="w-4 h-4" /> {t('violations.actions.warn')}
              </Button>
              <Button variant="ghost" onClick={() => onDismiss(detail.id)} className="gap-2">
                <X className="w-4 h-4" /> {t('violations.actions.dismiss')}
              </Button>
              <Button variant="ghost" onClick={() => onAnnul(detail.id)} className="gap-2 text-dark-300 hover:text-dark-100">
                <XCircle className="w-4 h-4" /> {t('violations.actions.annul')}
              </Button>
              <Button variant="ghost" onClick={() => onAnnulAll(detail.user_uuid)} className="gap-2 text-dark-300 hover:text-dark-100">
                <Trash2 className="w-4 h-4" /> {t('violations.actions.annulAll')}
              </Button>
              <Button variant="ghost" onClick={() => onWhitelist(detail.user_uuid)} className="gap-2 text-dark-300 hover:text-emerald-400">
                <ShieldOff className="w-4 h-4" /> {t('violations.whitelist.addButton')}
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
  const { t } = useTranslation()
  const { formatTimeAgo } = useFormatters()

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
          <p className="text-dark-200">{t('violations.topViolators.noViolators')}</p>
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
                      {v.username || t('common.unknown')}
                    </button>
                    <SeverityBadge severity={severity} />
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-dark-200">
                    <span>
                      <ShieldAlert className="w-3.5 h-3.5 inline mr-0.5" />
                      {t('violations.topViolators.violationsCount_many', { count: v.violations_count })}
                    </span>
                    <span>{t('violations.topViolators.max')}: {Math.round(v.max_score)}</span>
                    <span>{t('violations.topViolators.avg')}: {Math.round(v.avg_score)}</span>
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
              {Array.isArray(v.actions) && v.actions.length > 0 && (
                <div className="mt-3 pt-3 border-t border-dark-400/10 flex flex-wrap gap-2">
                  {(Array.isArray(v.actions) ? v.actions : []).map((action, j) => (
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

// ── Whitelist dialog ─────────────────────────────────────────────

function WhitelistAddDialog({
  open,
  onOpenChange,
  userUuid: initialUserUuid,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  userUuid: string
  onSubmit: (data: { user_uuid: string; reason?: string; expires_in_days?: number; excluded_analyzers?: string[] }) => void
}) {
  const { t } = useTranslation()
  const [userUuid, setUserUuid] = useState(initialUserUuid)
  const [reason, setReason] = useState('')
  const [duration, setDuration] = useState<string>('forever')
  const [exclusionMode, setExclusionMode] = useState<'full' | 'partial'>('full')
  const [selectedAnalyzers, setSelectedAnalyzers] = useState<Set<string>>(new Set())

  // Sync when prop changes
  useEffect(() => { setUserUuid(initialUserUuid) }, [initialUserUuid])

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setExclusionMode('full')
      setSelectedAnalyzers(new Set())
      setReason('')
      setDuration('forever')
    }
  }, [open])

  const toggleAnalyzer = (key: string) => {
    setSelectedAnalyzers(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleSubmit = () => {
    if (!userUuid.trim()) return
    const expiresInDays = duration === 'forever' ? undefined : parseInt(duration, 10)
    onSubmit({
      user_uuid: userUuid.trim(),
      reason: reason.trim() || undefined,
      expires_in_days: expiresInDays,
      excluded_analyzers: exclusionMode === 'partial' && selectedAnalyzers.size > 0
        ? Array.from(selectedAnalyzers)
        : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('violations.whitelist.addTitle')}</DialogTitle>
          <DialogDescription className="text-sm text-dark-200">
            {initialUserUuid || t('violations.whitelist.emptyDesc')}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {!initialUserUuid && (
            <div>
              <label className="text-sm font-medium text-dark-100 mb-1.5 block">
                {t('violations.whitelist.userUuid')}
              </label>
              <input
                type="text"
                value={userUuid}
                onChange={(e) => setUserUuid(e.target.value)}
                placeholder={t('violations.whitelist.userUuidPlaceholder')}
                className="w-full rounded-md border border-dark-400/30 bg-dark-800 px-3 py-2 text-sm text-white placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
              />
            </div>
          )}
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.whitelist.reason')}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t('violations.whitelist.reasonPlaceholder')}
              className="w-full rounded-md border border-dark-400/30 bg-dark-800 px-3 py-2 text-sm text-white placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/40 min-h-[80px] resize-none"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.whitelist.duration')}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'forever', label: t('violations.whitelist.forever') },
                { value: '7', label: t('violations.whitelist.days7') },
                { value: '30', label: t('violations.whitelist.days30') },
                { value: '90', label: t('violations.whitelist.days90') },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDuration(opt.value)}
                  className={cn(
                    'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                    duration === opt.value
                      ? 'bg-primary-600/20 text-primary-400 border-primary-500/30'
                      : 'bg-dark-700/50 text-dark-200 border-dark-400/20 hover:text-white hover:border-dark-400/40'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          {/* Exclusion mode */}
          <div>
            <label className="text-sm font-medium text-dark-100 mb-1.5 block">
              {t('violations.exclusions.mode')}
            </label>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <button
                onClick={() => setExclusionMode('full')}
                className={cn(
                  'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                  exclusionMode === 'full'
                    ? 'bg-primary-600/20 text-primary-400 border-primary-500/30'
                    : 'bg-dark-700/50 text-dark-200 border-dark-400/20 hover:text-white hover:border-dark-400/40'
                )}
              >
                {t('violations.exclusions.fullWhitelist')}
              </button>
              <button
                onClick={() => setExclusionMode('partial')}
                className={cn(
                  'px-3 py-2 rounded-md text-sm font-medium transition-all border',
                  exclusionMode === 'partial'
                    ? 'bg-amber-600/20 text-amber-400 border-amber-500/30'
                    : 'bg-dark-700/50 text-dark-200 border-dark-400/20 hover:text-white hover:border-dark-400/40'
                )}
              >
                {t('violations.exclusions.partialExclusion')}
              </button>
            </div>
            {exclusionMode === 'partial' && (
              <div className="space-y-1.5 mt-2">
                {ANALYZER_KEYS.map(key => (
                  <label
                    key={key}
                    className={cn(
                      'flex items-center gap-2.5 px-3 py-2 rounded-md cursor-pointer transition-all border',
                      selectedAnalyzers.has(key)
                        ? 'bg-amber-600/10 border-amber-500/30 text-amber-300'
                        : 'bg-dark-700/30 border-dark-400/15 text-dark-200 hover:border-dark-400/30'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedAnalyzers.has(key)}
                      onChange={() => toggleAnalyzer(key)}
                      className="rounded border-dark-400/30 bg-dark-800 text-primary-500 focus:ring-primary-500/40"
                    />
                    <span className="text-sm">{t(`violations.analyzers.${key}`)}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSubmit} className="gap-2">
            <ShieldOff className="w-4 h-4" />
            {t('violations.whitelist.addButton')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Whitelist tab ────────────────────────────────────────────────

function WhitelistTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const canResolve = useHasPermission('violations', 'resolve')
  const [wlPage, setWlPage] = useState(1)
  const perPage = 20
  const [confirmRemoveUuid, setConfirmRemoveUuid] = useState<string | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [manualUuid, setManualUuid] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['violationWhitelist', wlPage],
    queryFn: () => fetchWhitelist(perPage, (wlPage - 1) * perPage),
  })

  const addMutation = useMutation({
    mutationFn: (body: { user_uuid: string; reason?: string; expires_in_days?: number; excluded_analyzers?: string[] }) =>
      client.post('/violations/whitelist', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      toast.success(t('violations.toast.whitelistAdded'))
      setAddDialogOpen(false)
      setManualUuid('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (userUuid: string) => client.delete(`/violations/whitelist/${userUuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      toast.success(t('violations.toast.whitelistRemoved'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const isExpired = (expiresAt: string | null) => {
    if (!expiresAt) return false
    return new Date(expiresAt) < new Date()
  }

  return (
    <div className="space-y-4">
      {/* Header with add button */}
      {canResolve && (
        <div className="flex justify-end">
          <Button onClick={() => setAddDialogOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            {t('violations.whitelist.addButton')}
          </Button>
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="text-center py-12">
          <CardContent>
            <ShieldCheck className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
            <p className="text-dark-200 text-lg">{t('violations.whitelist.empty')}</p>
            <p className="text-sm text-dark-200 mt-1">{t('violations.whitelist.emptyDesc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => (
            <Card
              key={item.id}
              className={cn(
                'hover:border-dark-400/40 transition-colors animate-fade-in-up',
                isExpired(item.expires_at) && 'opacity-60'
              )}
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  <div className="p-2.5 rounded-lg bg-emerald-500/10 flex-shrink-0">
                    <ShieldOff className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="font-semibold text-white">
                        {item.username || item.email || item.user_uuid.slice(0, 8)}
                      </span>
                      {isExpired(item.expires_at) && (
                        <Badge variant="secondary" className="text-xs">{t('violations.whitelist.expired')}</Badge>
                      )}
                      {item.excluded_analyzers ? (
                        <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/30">
                          {t('violations.exclusions.partialExclusion')}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/30">
                          {t('violations.exclusions.fullWhitelist')}
                        </Badge>
                      )}
                    </div>
                    {Array.isArray(item.excluded_analyzers) && item.excluded_analyzers.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1">
                        {item.excluded_analyzers.map(a => (
                          <Badge key={a} variant="secondary" className="text-xs bg-amber-600/10 text-amber-300 border-amber-500/20">
                            {t(`violations.analyzers.${a}`)}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-dark-200">
                      {item.reason && <span>{item.reason}</span>}
                      <span>
                        <Calendar className="w-3.5 h-3.5 inline mr-0.5" />
                        {t('violations.whitelist.addedBy')}: {item.added_by_username || '—'}
                      </span>
                      <span>{formatDate(item.added_at)}</span>
                      {item.expires_at ? (
                        <span>
                          {t('violations.whitelist.expiresAt')}: {formatDate(item.expires_at)}
                        </span>
                      ) : (
                        <span className="text-emerald-400">{t('violations.whitelist.noExpiration')}</span>
                      )}
                    </div>
                  </div>
                  {canResolve && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmRemoveUuid(item.user_uuid)}
                      className="text-dark-300 hover:text-red-400 flex-shrink-0"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-2 pt-2">
          <Button variant="ghost" size="sm" disabled={wlPage <= 1} onClick={() => setWlPage(wlPage - 1)}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-dark-200">{wlPage} / {totalPages}</span>
          <Button variant="ghost" size="sm" disabled={wlPage >= totalPages} onClick={() => setWlPage(wlPage + 1)}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Add dialog (manual UUID) */}
      <WhitelistAddDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        userUuid={manualUuid}
        onSubmit={(data) => addMutation.mutate(data)}
      />

      {/* Confirm remove dialog */}
      <ConfirmDialog
        open={confirmRemoveUuid !== null}
        onOpenChange={(open) => { if (!open) setConfirmRemoveUuid(null) }}
        title={t('violations.whitelist.confirmRemove')}
        description={t('violations.whitelist.confirmRemoveDesc')}
        variant="destructive"
        onConfirm={() => {
          if (confirmRemoveUuid) removeMutation.mutate(confirmRemoveUuid)
          setConfirmRemoveUuid(null)
        }}
      />
    </div>
  )
}

// ── Stats overview ───────────────────────────────────────────────

function StatsOverview({ stats }: { stats: ViolationStats | undefined }) {
  const { t } = useTranslation()
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
              <p className="text-xs sm:text-sm text-dark-200">{t('violations.severity.critical')}</p>
              <InfoTooltip text={t('violations.severityTooltips.critical')} side="right" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">{stats.critical}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">{t('violations.severity.high')}</p>
              <InfoTooltip text={t('violations.severityTooltips.high')} side="right" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-yellow-400 mt-1">{stats.high}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">{t('violations.severity.medium')}</p>
              <InfoTooltip text={t('violations.severityTooltips.medium')} side="right" iconClassName="w-3.5 h-3.5" />
            </div>
            <p className="text-xl md:text-2xl font-bold text-blue-400 mt-1">{stats.medium}</p>
          </CardContent>
        </Card>
        <Card className="text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <CardContent className="p-4">
            <div className="flex items-center justify-center gap-1">
              <p className="text-xs sm:text-sm text-dark-200">{t('violations.severity.low')}</p>
              <InfoTooltip text={t('violations.severityTooltips.low')} side="right" iconClassName="w-3.5 h-3.5" />
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
                  <p className="text-xs text-dark-200">{t('violations.stats.total')}</p>
                  <InfoTooltip text={t('violations.stats.totalTooltip')} side="right" iconClassName="w-3 h-3" />
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
                  <p className="text-xs text-dark-200">{t('violations.stats.uniqueUsers')}</p>
                  <InfoTooltip text={t('violations.stats.uniqueUsersTooltip')} side="right" iconClassName="w-3 h-3" />
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
                  <p className="text-xs text-dark-200">{t('violations.stats.avgScore')}</p>
                  <InfoTooltip text={t('violations.stats.avgScoreTooltip')} side="right" iconClassName="w-3 h-3" />
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
                  <p className="text-xs text-dark-200">{t('violations.stats.maxScore')}</p>
                  <InfoTooltip text={t('violations.stats.maxScoreTooltip')} side="right" iconClassName="w-3 h-3" />
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
                {t('violations.stats.byCountries')} ({countryEntries.length})
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
                    <span className="text-sm text-dark-100">{country || t('common.unknown')}</span>
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

type Tab = 'all' | 'pending' | 'top' | 'reports' | 'whitelist'

export default function Violations() {
  const { t } = useTranslation()
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

  // Export handlers — CSV uses server-side endpoint for full export with proper escaping
  const handleExportCSV = () => {
    const params = new URLSearchParams()
    params.set('days', String(days))
    if (minScore > 0) params.set('min_score', String(minScore))
    if (severity) params.set('severity', severity)
    if (resolved !== undefined) params.set('resolved', String(resolved))
    const baseUrl = client.defaults.baseURL || ''
    window.open(`${baseUrl}/violations/export/csv?${params.toString()}`, '_blank')
    toast.success(t('common.export.csvDone'))
  }
  const handleExportJSON = () => {
    const items = data?.items
    if (!items?.length) return
    exportJSON(items, `violations-${new Date().toISOString().slice(0, 10)}`)
    toast.success(t('common.export.jsonDone'))
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
    refetchInterval: tab === 'pending' ? 30000 : false,
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
      toast.success(t('violations.toast.resolved'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
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

  const annulViolation = useMutation({
    mutationFn: (id: number) => client.post(`/violations/${id}/annul`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      queryClient.invalidateQueries({ queryKey: ['topViolators'] })
      queryClient.invalidateQueries({ queryKey: ['violationDetail'] })
      setSelectedViolationId(null)
      toast.success(t('violations.toast.annulled'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const annulAllViolations = useMutation({
    mutationFn: (userUuid: string) => client.post(`/violations/user/${userUuid}/annul-all`),
    onSuccess: (_data, _userUuid) => {
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      queryClient.invalidateQueries({ queryKey: ['topViolators'] })
      queryClient.invalidateQueries({ queryKey: ['violationDetail'] })
      setSelectedViolationId(null)
      toast.success(t('violations.toast.annulledAll'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const handleAnnul = useCallback(
    (id: number) => annulViolation.mutate(id),
    [annulViolation],
  )
  const handleAnnulAll = useCallback(
    (userUuid: string) => annulAllViolations.mutate(userUuid),
    [annulAllViolations],
  )

  // Whitelist
  const [whitelistDialogOpen, setWhitelistDialogOpen] = useState(false)
  const [whitelistUserUuid, setWhitelistUserUuid] = useState('')

  const addToWhitelist = useMutation({
    mutationFn: (body: { user_uuid: string; reason?: string; expires_in_days?: number; excluded_analyzers?: string[] }) =>
      client.post('/violations/whitelist', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['violationWhitelist'] })
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      queryClient.invalidateQueries({ queryKey: ['violationStats'] })
      setWhitelistDialogOpen(false)
      toast.success(t('violations.toast.whitelistAdded'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  const handleWhitelist = useCallback(
    (userUuid: string) => {
      setWhitelistUserUuid(userUuid)
      setWhitelistDialogOpen(true)
    },
    [],
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
          onAnnul={handleAnnul}
          onAnnulAll={handleAnnulAll}
          onWhitelist={handleWhitelist}
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
            <h1 className="page-header-title">{t('violations.title')}</h1>
            <InfoTooltip
              text={t('violations.tooltip')}
              side="right"
            />
          </div>
          <p className="text-dark-200 mt-1 text-sm md:text-base">
            {t('violations.subtitle')}
            {stats ? (
              <span className="text-dark-200 ml-1">
                {t('violations.periodSummary', {
                  count: stats.total,
                  period: days === 1 ? t('violations.periodToday') : days === 7 ? t('violations.periodWeek') : days === 30 ? t('violations.periodMonth') : t('violations.periodDays', { count: days }),
                })}
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
            <span className="hidden sm:inline">{t('common.filters')}</span>
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
                <label className="block text-xs text-dark-200 mb-1">{t('violations.filters.level')}</label>
                <select
                  value={severity}
                  onChange={(e) => {
                    setSeverity(e.target.value)
                    setPage(1)
                  }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                >
                  <option value="">{t('common.all')}</option>
                  <option value="critical">{t('violations.severity.critical')}</option>
                  <option value="high">{t('violations.severity.high')}</option>
                  <option value="medium">{t('violations.severity.medium')}</option>
                  <option value="low">{t('violations.severity.low')}</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('violations.filters.period')}</label>
                <select
                  value={days}
                  onChange={(e) => {
                    setDays(Number(e.target.value))
                    setPage(1)
                  }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                >
                  <option value={1}>{t('violations.filters.today')}</option>
                  <option value={7}>{t('violations.filters.week')}</option>
                  <option value={30}>{t('violations.filters.month')}</option>
                  <option value={90}>{t('violations.filters.threeMonths')}</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">
                  {t('violations.filters.minScore')}: {minScore}
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
                    setIpFilter('')
                    setCountryFilter('')
                    setDateFrom('')
                    setDateTo('')
                    setPage(1)
                  }}
                  className="w-full"
                >
                  {t('violations.filters.reset')}
                </Button>
              </div>
            </div>
            {/* Advanced filters */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 md:gap-4 mt-3 pt-3 border-t border-dark-400/10">
              <div>
                <label className="block text-xs text-dark-200 mb-1">IP</label>
                <input
                  type="text"
                  placeholder="192.168.1.1"
                  value={ipFilter}
                  onChange={(e) => { setIpFilter(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('violations.filters.country') || 'Country'}</label>
                <input
                  type="text"
                  placeholder="RU, US, DE..."
                  value={countryFilter}
                  onChange={(e) => { setCountryFilter(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('violations.filters.dateFrom') || 'From'}</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                />
              </div>
              <div>
                <label className="block text-xs text-dark-200 mb-1">{t('violations.filters.dateTo') || 'To'}</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-white ring-offset-background placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-dark-800"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-dark-800/50 rounded-lg p-1 animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        {([
          { key: 'all' as Tab, label: t('violations.tabs.all'), count: stats?.total },
          { key: 'pending' as Tab, label: t('violations.tabs.pending'), count: undefined },
          { key: 'top' as Tab, label: t('violations.tabs.topViolators'), count: undefined },
          { key: 'whitelist' as Tab, label: t('violations.whitelist.tab'), count: undefined },
          { key: 'reports' as Tab, label: t('violations.tabs.reports'), count: undefined },
        ]).map((tabItem) => (
          <button
            key={tabItem.key}
            onClick={() => handleTabChange(tabItem.key)}
            className={cn(
              'flex-1 sm:flex-none px-3 sm:px-4 py-2 text-xs sm:text-sm rounded-md font-medium transition-all',
              tab === tabItem.key
                ? 'bg-primary-600/20 text-primary-400 border border-primary-500/30'
                : 'text-dark-200 hover:text-white hover:bg-dark-700/50'
            )}
          >
            {tabItem.label}
            {tabItem.count !== undefined && tabItem.count > 0 && (
              <span className="ml-1.5 text-xs opacity-70">({tabItem.count})</span>
            )}
          </button>
        ))}
      </div>

      {/* Content based on tab */}
      {tab === 'reports' ? (
        <Reports embedded />
      ) : tab === 'top' ? (
        <TopViolatorsTab days={days} onViewUser={(uuid) => navigate(`/users/${uuid}`)} />
      ) : tab === 'whitelist' ? (
        <WhitelistTab />
      ) : (
        <>
        {/* Stats section */}
        <StatsOverview stats={stats} />
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
                    {tab === 'pending' ? t('violations.noPending') : t('violations.noViolations')}
                  </p>
                  <p className="text-sm text-dark-200 mt-1">
                    {tab === 'pending'
                      ? t('violations.allProcessed')
                      : t('violations.noRecords')}
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
                    onAnnul={() => handleAnnul(violation.id)}
                    onWhitelist={() => handleWhitelist(violation.user_uuid)}
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
                {t('common.shown')} {(page - 1) * perPage + 1}–
                {Math.min(page * perPage, total)} {t('common.of')} {total}
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
        </>
      )}

      {/* Whitelist add dialog */}
      <WhitelistAddDialog
        open={whitelistDialogOpen}
        onOpenChange={setWhitelistDialogOpen}
        userUuid={whitelistUserUuid}
        onSubmit={(data) => addToWhitelist.mutate(data)}
      />
    </div>
  )
}
