import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Download,
  Filter,
} from 'lucide-react'
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
import { resultBadgeClass, resultLabel, formatDateTime, actionTypeLabel } from './helpers'
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
  const [page, setPage] = useState(1)
  const [ruleIdFilter, setRuleIdFilter] = useState('')
  const [resultFilter, setResultFilter] = useState<string>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

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
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-dark-400" />
          <span className="text-sm text-dark-400">Фильтры:</span>
        </div>

        <Input
          placeholder="ID правила"
          value={ruleIdFilter}
          onChange={(e) => { setRuleIdFilter(e.target.value); setPage(1) }}
          className="w-28 h-8 text-xs bg-dark-800 border-dark-700"
          type="number"
        />

        <Select
          value={resultFilter}
          onValueChange={(v) => { setResultFilter(v === 'all' ? '' : v); setPage(1) }}
        >
          <SelectTrigger className="w-32 h-8 text-xs bg-dark-800 border-dark-700">
            <SelectValue placeholder="Результат" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все</SelectItem>
            <SelectItem value="success">Успех</SelectItem>
            <SelectItem value="error">Ошибка</SelectItem>
            <SelectItem value="skipped">Пропущено</SelectItem>
          </SelectContent>
        </Select>

        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
          className="w-36 h-8 text-xs bg-dark-800 border-dark-700"
          placeholder="С"
        />
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
          className="w-36 h-8 text-xs bg-dark-800 border-dark-700"
          placeholder="По"
        />

        <div className="ml-auto flex gap-2">
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
            <Skeleton key={i} className="h-16 bg-dark-800" />
          ))}
        </div>
      ) : !data?.items?.length ? (
        <div className="text-center py-12 text-dark-400">
          Нет записей в логе
        </div>
      ) : (
        <div className="space-y-2">
          {data.items.map((entry) => {
            const Icon = RESULT_ICON[entry.result] || AlertTriangle
            const iconColor = RESULT_ICON_COLOR[entry.result] || 'text-dark-400'

            return (
              <div
                key={entry.id}
                className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-700/50 hover:border-dark-600 transition-colors"
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
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-dark-400">
                    <span>{actionTypeLabel(entry.action_taken)}</span>
                    {entry.target_type && (
                      <>
                        <span className="text-dark-600">/</span>
                        <span>
                          {entry.target_type}
                          {entry.target_id && `: ${entry.target_id.substring(0, 12)}...`}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <div className="text-xs text-dark-500 flex-shrink-0">
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
            Стр. {data.page} из {data.pages} ({data.total} записей)
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
              disabled={page >= data.pages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
