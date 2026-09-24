import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/lib/useTabParam'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  FileText,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  ShieldAlert,
  Eye as EyeIcon,
  Users,
  Play,
  ChevronDown,
  ChevronUp,
  Clock,
  Calendar,
  CalendarDays,
  Send,
  Trash2,
  Check,
} from '@/components/brand/icons'
import { reportsApi, type ViolationReport } from '../api/reports'
import { settingsOf } from '@/api/settings'
import client from '../api/client'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useHasPermission } from '@/components/PermissionGate'
import { countryFlag } from '@/components/nodes/nodeShared'
import { useProviderTypeLabel } from '@/components/violations/AsnDirectory'
import { getDisplayTimeZone, timeZoneLabel, useDisplayTimeZone } from '@/lib/timezone'
import { getLocale, useFormatters } from '@/lib/useFormatters'
import { useOpenUser } from '@/lib/useOpenUser'
import { useChartTheme } from '@/lib/useChartTheme'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'

const REPORT_TYPES = ['daily', 'weekly', 'monthly'] as const

export default function Reports() {
  const { t } = useTranslation()
  const canCreate = useHasPermission('reports', 'create')

  const [activeTab, setActiveTab] = useTabParam('reports', ['reports', 'schedule'], 'rtab')
  const [reportFilter, setReportFilter] = useState<string>('')
  const [expandedReport, setExpandedReport] = useState<number | null>(null)
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false)
  const [generateType, setGenerateType] = useState('daily')

  const { data: reports = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['violation-reports', reportFilter],
    queryFn: () => reportsApi.getReports(reportFilter || undefined),
  })

  const generateMutation = useMutation({
    mutationFn: (type: string) => reportsApi.generateReport(type),
    onSuccess: (data) => {
      setGenerateDialogOpen(false)
      refetch()
      if (data?.id) setExpandedReport(data.id)
      toast.success(t('reports.generated'))
    },
    onError: () => toast.error(t('reports.generateError')),
  })

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('reports.title')}</h1>
          <p className="text-dark-200 mt-1">{t('reports.subtitle')}</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="reports">
            <FileText className="w-4 h-4 mr-2" />
            {t('reports.tabs.reports')}
          </TabsTrigger>
          <TabsTrigger value="schedule">
            <Clock className="w-4 h-4 mr-2" />
            {t('reports.tabs.schedule')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="reports" className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            <Select value={reportFilter || 'all'} onValueChange={(v) => setReportFilter(v === 'all' ? '' : v)}>
              <SelectTrigger className="w-40" aria-label={t('reports.reportType')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('reports.filterAll')}</SelectItem>
                {REPORT_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>{t(`reports.types.${type}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetch()}
                aria-label={t('common.refresh')}
                title={t('common.refresh')}
              >
                <RefreshCw className={cn('w-4 h-4', isFetching && 'animate-spin')} />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setGenerateDialogOpen(true)}>
                  <Play className="w-4 h-4 mr-2" />
                  {t('reports.generate')}
                </Button>
              )}
            </div>
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : isError ? (
            <QueryError onRetry={refetch} />
          ) : reports.length === 0 ? (
            <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
              <CardContent className="p-2">
                <EmptyState icon={FileText} title={t('reports.empty')} />
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {reports.map((report) => (
                <ReportCard
                  key={report.id}
                  report={report}
                  expanded={expandedReport === report.id}
                  onToggle={() => setExpandedReport(expandedReport === report.id ? null : report.id)}
                />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="schedule" className="space-y-4">
          <ReportScheduleTab />
        </TabsContent>
      </Tabs>

      <Dialog open={generateDialogOpen} onOpenChange={setGenerateDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('reports.generateTitle')}</DialogTitle>
            <DialogDescription>{t('reports.generateDescription')}</DialogDescription>
          </DialogHeader>
          <div>
            <Label>{t('reports.reportType')}</Label>
            <Select value={generateType} onValueChange={setGenerateType}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REPORT_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>{t(`reports.generatePeriod.${type}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => generateMutation.mutate(generateType)} disabled={generateMutation.isPending}>
              {generateMutation.isPending ? t('reports.generating') : t('reports.generate')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Карточка отчёта ────────────────────────────────────────────

/** Период отчёта датами на часах панели; конец периода — не включительно. */
function formatPeriod(start: string, end: string): string {
  const timeZone = getDisplayTimeZone()
  const from = new Date(start)
  const to = new Date(new Date(end).getTime() - 1)
  const day = (d: Date) => d.toLocaleDateString(getLocale(), { timeZone, day: 'numeric', month: 'short', year: 'numeric' })
  const a = day(from)
  const b = day(to)
  return a === b ? a : `${a} — ${b}`
}

function severityOf(score: number): string {
  if (score >= 80) return 'text-red-400 bg-red-500/10 border-red-500/30'
  if (score >= 50) return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
  return 'text-blue-400 bg-blue-500/10 border-blue-500/30'
}

function TrendBadge({ report }: { report: ViolationReport }) {
  const { t } = useTranslation()
  if (report.trend_percent != null) {
    const up = report.trend_percent > 0
    const flat = Math.abs(report.trend_percent) < 0.05
    const Icon = flat ? Minus : up ? TrendingUp : TrendingDown
    return (
      <span
        className={cn('flex items-center gap-1 text-xs', flat ? 'text-dark-300' : up ? 'text-red-400' : 'text-green-400')}
        title={t('reports.trendHint', { prev: report.prev_total_violations ?? 0 })}
      >
        <Icon className="w-4 h-4" />
        {up ? '+' : ''}{report.trend_percent.toFixed(1)}%
      </span>
    )
  }
  // Было ноль — процента нет, но рост есть
  if (report.prev_total_violations === 0 && report.total_violations > 0) {
    return (
      <span className="flex items-center gap-1 text-xs text-red-400" title={t('reports.trendHint', { prev: 0 })}>
        <TrendingUp className="w-4 h-4" />
        {t('reports.trendFromZero')}
      </span>
    )
  }
  return null
}

function ReportCard({ report, expanded, onToggle }: {
  report: ViolationReport
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const counters = [
    { key: 'critical', value: report.critical_count, Icon: ShieldAlert, cls: 'text-red-400' },
    { key: 'warning', value: report.warning_count, Icon: AlertTriangle, cls: 'text-yellow-400' },
    { key: 'monitor', value: report.monitor_count, Icon: EyeIcon, cls: 'text-blue-400' },
  ]

  return (
    <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)] transition-colors">
      <CardContent className="p-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="w-full text-left p-4 hover:bg-[var(--glass-bg-hover)]/30 rounded-lg transition-colors"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="text-xs">{t(`reports.types.${report.report_type}`, { defaultValue: report.report_type })}</Badge>
                <span className="text-sm text-white font-medium">{formatPeriod(report.period_start, report.period_end)}</span>
              </div>
              <div className="flex items-center gap-x-4 gap-y-1 mt-2 flex-wrap text-xs">
                {counters.map(({ key, value, Icon, cls }) => (
                  <span key={key} className={cn('flex items-center gap-1', value ? cls : 'text-dark-400')}>
                    <Icon className="w-3.5 h-3.5" />
                    {t(`reports.severity.${key}`)}: {value}
                  </span>
                ))}
                <span className="flex items-center gap-1 text-dark-300">
                  <Users className="w-3.5 h-3.5" />
                  {t('reports.uniqueUsers')}: {report.unique_users}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <TrendBadge report={report} />
              <div className="text-right">
                <div className="text-lg font-semibold text-white tabular-nums leading-none">{report.total_violations}</div>
                <div className="text-[10px] text-dark-300 mt-0.5">{t('reports.violationsTotal')}</div>
              </div>
              {expanded ? <ChevronUp className="w-4 h-4 text-dark-400" /> : <ChevronDown className="w-4 h-4 text-dark-400" />}
            </div>
          </div>
        </button>
        {expanded && <ReportDetails report={report} />}
      </CardContent>
    </Card>
  )
}

function ReportDetails({ report }: { report: ViolationReport }) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const openUser = useOpenUser()
  const providerLabel = useProviderTypeLabel()
  const queryClient = useQueryClient()
  const canCreate = useHasPermission('reports', 'create')
  const canDelete = useHasPermission('reports', 'delete')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['violation-reports'] })
  const sendMutation = useMutation({
    mutationFn: () => reportsApi.sendReport(report.id),
    onSuccess: () => { invalidate(); toast.success(t('reports.sent')) },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) =>
      toast.error(t('reports.sendError'), { description: err.response?.data?.detail }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => reportsApi.deleteReport(report.id),
    onSuccess: () => { invalidate(); toast.success(t('common.deleted')) },
    onError: () => toast.error(t('common.error')),
  })

  const top = report.top_violators || []
  const sorted = (m: Record<string, number> | null) => Object.entries(m || {}).sort(([, a], [, b]) => b - a)
  const countries = sorted(report.by_country)
  const providers = sorted(report.by_asn_type)
  const actions = sorted(report.by_action)
  // Текст отчёта — телеграмный HTML; тут показываем как есть, без разметки
  const plainText = (report.message_text || '').replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')

  return (
    <div className="px-4 pb-4 space-y-4 border-t border-[var(--glass-border)] pt-4">
      {report.scoped && (
        <p className="text-xs text-dark-300">{t('reports.scopedHint')}</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Section title={t('reports.topViolators')}>
          {top.length === 0 ? (
            <p className="text-xs text-dark-400">{t('reports.noViolators')}</p>
          ) : (
            <div className="space-y-1.5">
              {top.map((v, i) => {
                const name = v.username || v.email || (v.user_uuid ? v.user_uuid.slice(0, 8) : '—')
                return (
                  <div key={v.user_uuid || i} className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="text-dark-400 tabular-nums w-4 text-right">{i + 1}</span>
                      <span
                        className={cn('truncate text-dark-100', v.user_uuid && 'cursor-pointer hover:text-primary-400 hover:underline')}
                        {...(v.user_uuid ? openUser(v.user_uuid) : {})}
                      >
                        {name}
                      </span>
                    </span>
                    <span className="flex items-center gap-2 shrink-0 text-dark-300">
                      {t('reports.violationsCount', { count: v.violations_count })}
                      {v.max_score != null && (
                        <span
                          className={cn('px-1.5 py-0.5 rounded border tabular-nums', severityOf(v.max_score))}
                          title={t('reports.maxScore')}
                        >
                          {Math.round(v.max_score)}
                        </span>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        <div className="space-y-4">
          {countries.length > 0 && (
            <Section title={t('reports.byCountry')}>
              <ChipList items={countries.slice(0, 10).map(([code, n]) => ({ key: code, label: `${countryFlag(code)} ${code}`.trim(), n }))} />
            </Section>
          )}
          {providers.length > 0 && (
            <Section title={t('reports.byAsnType')}>
              <ChipList items={providers.map(([type, n]) => ({ key: type, label: providerLabel(type), n }))} />
            </Section>
          )}
          {actions.length > 0 && (
            <Section title={t('reports.byAction')}>
              <ChipList items={actions.map(([action, n]) => ({
                key: action,
                label: t(`violations.recommendedActions.${action}`, { defaultValue: action }),
                n,
              }))} />
            </Section>
          )}
        </div>
      </div>

      {plainText && (
        <details className="group">
          <summary className="text-xs font-medium text-dark-300 cursor-pointer hover:text-white select-none">
            {t('reports.messageText')}
          </summary>
          <pre className="mt-2 p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] text-xs text-dark-100 whitespace-pre-wrap font-sans">
            {plainText}
          </pre>
        </details>
      )}

      <div className="flex items-center justify-between gap-2 flex-wrap pt-1">
        <span className="text-xs text-dark-300 flex items-center gap-1">
          {report.sent_at ? (
            <><Check className="w-3.5 h-3.5 text-green-400" />{t('reports.sentAt', { time: formatDate(report.sent_at) })}</>
          ) : (
            t('reports.notSent')
          )}
        </span>
        <div className="flex gap-2">
          {canCreate && report.message_text && (
            <Button size="sm" variant="secondary" onClick={() => sendMutation.mutate()} disabled={sendMutation.isPending}>
              <Send className="w-3.5 h-3.5 mr-1.5" />
              {report.sent_at ? t('reports.sendAgain') : t('reports.send')}
            </Button>
          )}
          {canDelete && (
            <Button
              size="sm"
              variant="ghost"
              className="text-red-400 hover:text-red-300"
              onClick={() => setConfirmDelete(true)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              {t('common.delete')}
            </Button>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('reports.deleteTitle')}
        description={t('reports.deleteDescription')}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => { setConfirmDelete(false); deleteMutation.mutate() }}
      />
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-medium text-dark-300 mb-2">{title}</h4>
      {children}
    </div>
  )
}

function ChipList({ items }: { items: { key: string; label: string; n: number }[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item.key} variant="outline" className="text-xs font-normal">
          {item.label}
          <span className="ml-1.5 text-white tabular-nums">{item.n}</span>
        </Badge>
      ))}
    </div>
  )
}

// ── Report Schedule Tab ────────────────────────────────────────

interface ScheduleSettings {
  reports_enabled: string
  reports_daily_enabled: string
  reports_daily_time: string
  reports_weekly_enabled: string
  reports_weekly_day: string
  reports_weekly_time: string
  reports_monthly_enabled: string
  reports_monthly_day: string
  reports_monthly_time: string
}

function ReportScheduleTab() {
  const { t } = useTranslation()
  const timeZone = useDisplayTimeZone()
  const queryClient = useQueryClient()
  const canView = useHasPermission('settings', 'view')
  const canEdit = useHasPermission('settings', 'edit')

  // Ключ ['settings'] общий с «Настройками» и «Бэкапами»: в кэше лежит полный
  // ответ, а нужный кусок берём через select — иначе страницы портят друг другу кэш
  const { data: settingsData, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => (await client.get('/settings')).data,
    enabled: canView,
    select: (data) => settingsOf(data, 'reports') as unknown as ScheduleSettings,
  })

  const updateMutation = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => {
      await client.put(`/settings/${key}`, { value })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.success(t('common.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateSetting = (key: string, value: string) => {
    if (!canEdit) return
    updateMutation.mutate({ key, value })
  }

  const toBool = (v: string | undefined) => v === 'true' || v === '1'

  if (!canView) {
    return (
      <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
        <CardContent className="p-6 text-center text-sm text-dark-200">{t('reports.schedule.noPermission')}</CardContent>
      </Card>
    )
  }
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-48 w-full" />)}
      </div>
    )
  }
  if (isError || !settingsData) return <QueryError onRetry={refetch} />

  const s = settingsData
  const dayNames = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    .map((d) => t(`reports.schedule.${d}`))
  const timeLabel = t('reports.schedule.time', { zone: timeZoneLabel(timeZone) })

  return (
    <div className="space-y-4">
      <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
        <CardContent className="p-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white">{t('reports.schedule.globalEnabled')}</p>
            <p className="text-xs text-dark-300">{t('reports.schedule.globalDescription')}</p>
          </div>
          <Switch
            checked={toBool(s.reports_enabled)}
            onCheckedChange={(v) => updateSetting('reports_enabled', v ? 'true' : 'false')}
            disabled={!canEdit}
            aria-label={t('reports.schedule.globalEnabled')}
          />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ScheduleCard
          icon={<Calendar className="w-4 h-4 text-cyan-400" />}
          title={t('reports.schedule.daily')}
          enabled={toBool(s.reports_daily_enabled)}
          onToggle={(v) => updateSetting('reports_daily_enabled', v ? 'true' : 'false')}
          toggleDisabled={!canEdit || !toBool(s.reports_enabled)}
        >
          <TimeField
            label={timeLabel}
            value={s.reports_daily_time || '09:00'}
            onCommit={(v) => updateSetting('reports_daily_time', v)}
            disabled={!canEdit || !toBool(s.reports_daily_enabled)}
          />
        </ScheduleCard>

        <ScheduleCard
          icon={<CalendarDays className="w-4 h-4 text-green-400" />}
          title={t('reports.schedule.weekly')}
          enabled={toBool(s.reports_weekly_enabled)}
          onToggle={(v) => updateSetting('reports_weekly_enabled', v ? 'true' : 'false')}
          toggleDisabled={!canEdit || !toBool(s.reports_enabled)}
        >
          <div>
            <Label className="text-xs text-dark-300">{t('reports.schedule.dayOfWeek')}</Label>
            <Select
              value={s.reports_weekly_day || '0'}
              onValueChange={(v) => updateSetting('reports_weekly_day', v)}
              disabled={!canEdit || !toBool(s.reports_weekly_enabled)}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {dayNames.map((name, i) => (
                  <SelectItem key={i} value={String(i)}>{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <TimeField
            label={timeLabel}
            value={s.reports_weekly_time || '10:00'}
            onCommit={(v) => updateSetting('reports_weekly_time', v)}
            disabled={!canEdit || !toBool(s.reports_weekly_enabled)}
          />
        </ScheduleCard>

        <ScheduleCard
          icon={<CalendarDays className="w-4 h-4 text-yellow-400" />}
          title={t('reports.schedule.monthly')}
          enabled={toBool(s.reports_monthly_enabled)}
          onToggle={(v) => updateSetting('reports_monthly_enabled', v ? 'true' : 'false')}
          toggleDisabled={!canEdit || !toBool(s.reports_enabled)}
        >
          <div>
            <Label className="text-xs text-dark-300">{t('reports.schedule.dayOfMonth')}</Label>
            <Select
              value={s.reports_monthly_day || '1'}
              onValueChange={(v) => updateSetting('reports_monthly_day', v)}
              disabled={!canEdit || !toBool(s.reports_monthly_enabled)}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <SelectItem key={d} value={String(d)}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <TimeField
            label={timeLabel}
            value={s.reports_monthly_time || '10:00'}
            onCommit={(v) => updateSetting('reports_monthly_time', v)}
            disabled={!canEdit || !toBool(s.reports_monthly_enabled)}
          />
        </ScheduleCard>
      </div>
    </div>
  )
}

function ScheduleCard({ icon, title, enabled, onToggle, toggleDisabled, children }: {
  icon: React.ReactNode
  title: string
  enabled: boolean
  onToggle: (v: boolean) => void
  toggleDisabled: boolean
  children: React.ReactNode
}) {
  return (
    <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon}
            <span className="text-sm font-medium text-white">{title}</span>
          </div>
          <Switch checked={enabled} onCheckedChange={onToggle} disabled={toggleDisabled} aria-label={title} />
        </div>
        {children}
      </CardContent>
    </Card>
  )
}

/** Время сохраняется, когда поле отпустили, а не на каждую цифру:
 *  иначе в настройку улетали недописанные значения и сыпались тосты. */
function TimeField({ label, value, onCommit, disabled }: {
  label: string
  value: string
  onCommit: (v: string) => void
  disabled: boolean
}) {
  const chart = useChartTheme()
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])

  const commit = () => {
    if (/^\d{2}:\d{2}$/.test(draft) && draft !== value) onCommit(draft)
    else setDraft(value)
  }

  return (
    <div>
      <Label className="text-xs text-dark-300">{label}</Label>
      <Input
        type="time"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
        disabled={disabled}
        className="mt-1"
        style={{ colorScheme: chart.isLight ? 'light' : 'dark' }}
      />
    </div>
  )
}
