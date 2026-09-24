import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  MoreVertical,
  Pencil,
  Trash2,
  Play,
  ArrowRight,
  Clock,
  Zap,
  Activity,
} from '@/components/brand/icons'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { automationsApi, type AutomationRule } from '../../api/automations'
import {
  resultBadgeClass,
  resultLabel,
  categoryColor,
  categoryLabel,
  describeTrigger,
  describeAction,
  formatDateTime,
  triggerTypeLabel,
} from './helpers'

const TRIGGER_TYPE_ICONS: Record<string, React.ElementType> = {
  event: Zap,
  schedule: Clock,
  threshold: Activity,
}

interface RuleCardProps {
  rule: AutomationRule
  canEdit: boolean
  canDelete: boolean
  canRun: boolean
  onToggle: (id: number) => void
  onEdit: (rule: AutomationRule) => void
  onDelete: (rule: AutomationRule) => void
  onTest: (id: number) => void
  onRunNow: (id: number) => void
  toggleLoading: boolean
}

/** Последние срабатывания правила — прямо в карточке, с переходом к цели */
function RuleLog({ ruleId }: { ruleId: number }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['automation-rule-log', ruleId],
    queryFn: () => automationsApi.logs({ rule_id: ruleId, per_page: 10 }),
    staleTime: 15_000,
  })
  const items = data?.items ?? []
  if (isLoading) return <p className="text-xs text-dark-400 py-2">{t('common.loading')}</p>
  if (items.length === 0) return <p className="text-xs text-dark-400 py-2">{t('automations.ruleCard.logEmpty')}</p>
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((entry) => (
        <li key={entry.id} className="flex items-center gap-2 text-[11px]">
          <span className="text-dark-400 whitespace-nowrap">{entry.triggered_at ? formatDateTime(entry.triggered_at) : ''}</span>
          <Badge variant="outline" className={`text-[10px] ${resultBadgeClass(entry.result)}`}>{resultLabel(entry.result)}</Badge>
          {entry.target_type === 'user' && entry.target_id && (
            <Link to={`/users/${entry.target_id}`} className="ml-auto whitespace-nowrap text-primary-400 hover:underline">
              {t('automations.ruleCard.openUser')}
            </Link>
          )}
          {entry.target_type === 'node' && entry.target_id && (
            <Link to="/servers?tab=nodes" className="ml-auto whitespace-nowrap text-primary-400 hover:underline">
              {t('automations.ruleCard.openNode')}
            </Link>
          )}
        </li>
      ))}
    </ul>
  )
}

export function RuleCard({
  rule,
  canEdit,
  canDelete,
  canRun,
  onToggle,
  onEdit,
  onDelete,
  onTest,
  onRunNow,
  toggleLoading,
}: RuleCardProps) {
  const { t } = useTranslation()
  const [showLog, setShowLog] = useState(false)
  const extraCount = rule.extra_actions?.length ?? 0
  const TriggerIcon = TRIGGER_TYPE_ICONS[rule.trigger_type] || Zap

  return (
    <Card className={`border-2 transition-all ${
      rule.is_enabled
        ? 'bg-[var(--glass-bg)] border-[var(--glass-border)] hover:border-[var(--glass-border)]'
        : 'bg-[var(--glass-bg)]/30 border-[var(--glass-border)] opacity-70 hover:opacity-90'
    }`}>
      <CardContent className="p-4">
        {/* Header: name + actions */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-2">
              <h3 className="min-w-0 text-sm font-medium text-white line-clamp-2 break-words">{rule.name}</h3>
              {!rule.is_enabled && (
                <Badge variant="outline" className="text-[9px] text-dark-400 border-[var(--glass-border)] flex-shrink-0">
                  {t('automations.ruleCard.off')}
                </Badge>
              )}
            </div>
            {rule.description && (
              <p className="text-xs text-dark-400 mt-1 line-clamp-2">{rule.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {canEdit && (
              <Switch
                checked={rule.is_enabled}
                onCheckedChange={() => onToggle(rule.id)}
                disabled={toggleLoading}
                className="data-[state=checked]:bg-accent-teal"
              />
            )}
            {(canEdit || canDelete || canRun) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('common.openMenu')}>
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canEdit && (
                    <DropdownMenuItem onClick={() => onEdit(rule)}>
                      <Pencil className="w-4 h-4 mr-2" /> {t('automations.ruleCard.edit')}
                    </DropdownMenuItem>
                  )}
                  {canRun && (
                    <DropdownMenuItem onClick={() => onTest(rule.id)}>
                      <Play className="w-4 h-4 mr-2" /> {t('automations.ruleCard.test')}
                    </DropdownMenuItem>
                  )}
                  {canRun && rule.trigger_type === 'schedule' && (
                    <DropdownMenuItem onClick={() => onRunNow(rule.id)}>
                      <Zap className="w-4 h-4 mr-2" /> {t('automations.ruleCard.runNow')}
                    </DropdownMenuItem>
                  )}
                  {canDelete && (
                    <DropdownMenuItem
                      onClick={() => onDelete(rule)}
                      className="text-red-400 focus:text-red-400"
                    >
                      <Trash2 className="w-4 h-4 mr-2" /> {t('automations.ruleCard.delete')}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          <Badge
            variant="outline"
            className={`text-[10px] ${categoryColor(rule.category)}`}
          >
            {categoryLabel(rule.category)}
          </Badge>
          <Badge variant="outline" className="text-[10px] bg-[var(--glass-bg)] text-dark-300 border-[var(--glass-border)]">
            {triggerTypeLabel(rule.trigger_type)}
          </Badge>
        </div>

        {/* Trigger -> Action */}
        <div className="p-2.5 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] mb-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <TriggerIcon className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
            <span className="text-xs text-dark-200 truncate">{describeTrigger(rule)}</span>
          </div>
          <div className="w-full h-px bg-[var(--glass-bg)]" />
          <div className="flex items-center gap-2">
            <ArrowRight className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
            <span className="text-xs text-primary-400 truncate">
              {describeAction(rule)}
              {extraCount > 0 && ` ${t('automations.ruleCard.andMore', { count: extraCount })}`}
            </span>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center justify-between text-xs text-dark-400 pt-1 border-t border-[var(--glass-border)]/50">
          <div className="flex items-center gap-1">
            <Zap className="w-3 h-3" />
            <span>{rule.trigger_count} {t('automations.ruleCard.times')}</span>
          </div>
          {rule.last_triggered_at && (
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{formatDateTime(rule.last_triggered_at)}</span>
            </div>
          )}
          {rule.trigger_count > 0 && (
            <button
              type="button"
              onClick={() => setShowLog((v) => !v)}
              aria-expanded={showLog}
              className="text-primary-400 hover:underline"
            >
              {t('automations.ruleCard.log')}
            </button>
          )}
        </div>
        {showLog && <RuleLog ruleId={rule.id} />}
      </CardContent>
    </Card>
  )
}
