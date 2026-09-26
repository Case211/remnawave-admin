import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Download,
  Filter,
} from '@/components/brand/icons'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { automationsApi } from '../../api/automations'
import type { AutomationLogEntry } from '../../api/automations'
import { resultBadgeClass, resultLabel, formatDateTime, actionTypeLabel } from './helpers'

type ChainStepResult = { action?: string; result?: string; details?: { run_at?: string; reason?: string } }
// Причины, по которым отложенный шаг не встал в очередь
const NOT_QUEUED = ['already_scheduled', 'warning_not_delivered']

/** Почему шаг не выполнился — для отложенных шагов и предупреждений своими словами. */
function skipReason(entry: AutomationLogEntry, t: (key: string, opts?: Record<string, unknown>) => string): string | null {
  const reason = entry.details?.reason
  if (entry.result !== 'skipped' || typeof reason !== 'string') return null
  if (entry.details?.delayed) return t(`automations.delayed.reasons.${reason}`, { defaultValue: reason })
  if (entry.action_taken === 'warn_user') return t(`violations.warnReasons.${reason}`, { defaultValue: reason })
  return reason
}
import { exportCSV, exportJSON } from '../../lib/export'

const RESULT_ICON: Record<string, React.ElementType> = {
  success: CheckCircle,
  error: XCircle,
  skipped: AlertTriangle,
}

const RESULT_ICON_COLOR: Record<string, string> = {
  success: 'text-emerald-400',
  error: 'text-red-400',
  skipped: 'text-yellow-400',
}

export function LogsTimeline() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [ruleIdFilter, setRuleIdFilter] = useState('')
  const [resultFilter, setResultFilter] = useState<string>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data: rulesData } = useQuery({
    queryKey: ['automation-rule-names'],
    queryFn: () => automationsApi.list({ per_page: 100 }),
    staleTime: 60_000,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['automation-logs', page, ruleIdFilter, resultFilter, dateFrom, dateTo],
    queryFn: () =>
      automationsApi.logs({
        page,
        per_page: 30,
        rule_id: ruleIdFilter ? parseInt(ruleIdFilter) : undefined,
        result: resultFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
  })

  const handleExportCsv = () => {
    if (!data?.items?.length) return
    const rows = data.items.map((l) => ({
      id: l.id,
      rule_id: l.rule_id,
      rule_name: l.rule_name || '',
      triggered_at: l.triggered_at || '',
      target_type: l.target_type || '',
      target_id: l.target_id || '',
      action_taken: l.action_taken,
      result: l.result,
    }))
    exportCSV(rows, 'automation-logs')
  }

  const handleExportJson = () => {
    if (!data?.items?.length) return
    exportJSON(data.items, 'automation-logs')
  }

  return (
    <div className="space-y-4">
      {/* Filters: на телефоне — сетка на всю ширину */}
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-3">
        <div className="hidden sm:flex items-center gap-2">
          <Filter className="w-4 h-4 text-dark-400" />
          <span className="text-sm text-dark-400">{t('automations.logsTab.filters')}</span>
        </div>

        {/* Правило — по названию, а не по номеру */}
        <Select
          value={ruleIdFilter || 'all'}
          onValueChange={(v) => { setRuleIdFilter(v === 'all' ? '' : v); setPage(1) }}
        >
          <SelectTrigger className="col-span-2 w-full sm:w-56 h-8 text-xs bg-[var(--glass-bg)] border-[var(--glass-border)]">
            <SelectValue placeholder={t('automations.logsTab.allRules')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('automations.logsTab.allRules')}</SelectItem>
            {(rulesData?.items ?? []).map((r) => (
              <SelectItem key={r.id} value={String(r.id)}>{r.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={resultFilter}
          onValueChange={(v) => { setResultFilter(v === 'all' ? '' : v); setPage(1) }}
        >
          <SelectTrigger className="col-span-2 w-full sm:w-32 h-8 text-xs bg-[var(--glass-bg)] border-[var(--glass-border)]">
            <SelectValue placeholder={t('automations.logsTab.resultPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('automations.logsTab.all')}</SelectItem>
            <SelectItem value="success">{t('automations.logsTab.success')}</SelectItem>
            <SelectItem value="error">{t('automations.logsTab.error')}</SelectItem>
            <SelectItem value="skipped">{t('automations.logsTab.skipped')}</SelectItem>
          </SelectContent>
        </Select>

        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
          aria-label={t('automations.logsTab.from')}
          className="w-full sm:w-36 h-8 text-xs bg-[var(--glass-bg)] border-[var(--glass-border)]"
          placeholder={t('automations.logsTab.from')}
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
          aria-label={t('automations.logsTab.to')}
          className="w-full sm:w-36 h-8 text-xs bg-[var(--glass-bg)] border-[var(--glass-border)]"
          placeholder={t('automations.logsTab.to')}
        />

        <div className="col-span-2 flex justify-end gap-2 sm:ml-auto">
          <Button variant="outline" size="sm" onClick={handleExportCsv} disabled={!data?.items?.length}>
            <Download className="w-3.5 h-3.5 mr-1" /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportJson} disabled={!data?.items?.length}>
            <Download className="w-3.5 h-3.5 mr-1" /> JSON
          </Button>
        </div>
      </div>

      {/* Timeline */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 bg-[var(--glass-bg)]" />
          ))}
        </div>
      ) : !data?.items?.length ? (
        <div className="text-center py-12 text-dark-400">
          {t('automations.logsTab.noLogs')}
        </div>
      ) : (
        <div className="space-y-2">
          {data.items.map((entry) => {
            const Icon = RESULT_ICON[entry.result] || AlertTriangle
            const iconColor = RESULT_ICON_COLOR[entry.result] || 'text-dark-400'
            const reason = skipReason(entry, t)
            // Отложенные шаги этого срабатывания: что и когда выполнится, а что не поставлено и почему
            const waiting = ((entry.details?.then as ChainStepResult[] | undefined) ?? []).filter(
              (s) => s.result === 'scheduled' || (s.result === 'skipped' && NOT_QUEUED.includes(s.details?.reason ?? '')),
            )

            return (
              <div
                key={entry.id}
                className="flex items-center gap-3 p-3 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)]/50 hover:border-[var(--glass-border)] transition-colors"
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${iconColor}`} />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-white">
                      {entry.rule_name || `Rule #${entry.rule_id}`}
                    </span>
                    <Badge
                      variant="outline"
                      className={`text-[10px] ${resultBadgeClass(entry.result)}`}
                    >
                      {resultLabel(entry.result)}
                    </Badge>
                    {!!entry.details?.delayed && (
                      <span className="text-[10px] text-dark-300">{t('automations.delayed.badge')}</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1 text-xs text-dark-400">
                    {/* На телефоне дата — в строке с деталями: справа ей нет места */}
                    <span className="sm:hidden text-dark-500">{formatDateTime(entry.triggered_at)}</span>
                    <span>{actionTypeLabel(entry.action_taken)}</span>
                    {entry.target_type && (
                      <>
                        <span className="text-dark-600">/</span>
                        <span>
                          {entry.target_type}
                          {entry.target_id && `: ${entry.target_id.length > 12 ? entry.target_id.substring(0, 12) + '\u2026' : entry.target_id}`}
                        </span>
                      </>
                    )}
                    {reason && (
                      <>
                        <span className="text-dark-600">·</span>
                        <span className="text-yellow-300/80">{reason}</span>
                      </>
                    )}
                  </div>
                  {waiting.map((step, i) => (
                    <div key={i} className="mt-1 flex items-center gap-1.5 text-xs text-dark-300">
                      <Clock className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                      {step.result === 'scheduled'
                        ? t('automations.delayed.scheduled', {
                          action: actionTypeLabel(step.action || ''),
                          time: formatDateTime(step.details?.run_at ?? null),
                        })
                        : t('automations.delayed.notQueued', {
                          action: actionTypeLabel(step.action || ''),
                          reason: t(`automations.delayed.reasons.${step.details?.reason}`),
                        })}
                    </div>
                  ))}
                </div>

                <div className="hidden sm:block text-xs text-dark-500 flex-shrink-0">
                  {formatDateTime(entry.triggered_at)}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-dark-400">
            {t('automations.logsTab.page', { page: data.page, pages: data.pages, total: data.total })}
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10 md:h-8 md:w-8"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              aria-label={t('common.previousPage')}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-10 w-10 md:h-8 md:w-8"
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page >= data.pages}
              aria-label={t('common.nextPage')}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
