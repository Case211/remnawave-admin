import {
  MoreVertical,
  Pencil,
  Trash2,
  Play,
  ArrowRight,
  Clock,
  Zap,
  Activity,
} from 'lucide-react'
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
import type { AutomationRule } from '../../api/automations'
import {
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
  toggleLoading: boolean
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
  toggleLoading,
}: RuleCardProps) {
  const TriggerIcon = TRIGGER_TYPE_ICONS[rule.trigger_type] || Zap

  return (
    <Card className="bg-dark-800/50 border-dark-700 hover:border-dark-600 transition-colors">
      <CardContent className="p-4">
        {/* Header: name + actions */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium text-white truncate">{rule.name}</h3>
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
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <MoreVertical className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canEdit && (
                    <DropdownMenuItem onClick={() => onEdit(rule)}>
                      <Pencil className="w-4 h-4 mr-2" /> Редактировать
                    </DropdownMenuItem>
                  )}
                  {canRun && (
                    <DropdownMenuItem onClick={() => onTest(rule.id)}>
                      <Play className="w-4 h-4 mr-2" /> Тестировать
                    </DropdownMenuItem>
                  )}
                  {canDelete && (
                    <DropdownMenuItem
                      onClick={() => onDelete(rule)}
                      className="text-red-400 focus:text-red-400"
                    >
                      <Trash2 className="w-4 h-4 mr-2" /> Удалить
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
          <Badge variant="outline" className="text-[10px] bg-dark-700/50 text-dark-300 border-dark-600">
            {triggerTypeLabel(rule.trigger_type)}
          </Badge>
        </div>

        {/* Trigger → Action */}
        <div className="p-2.5 rounded-md bg-dark-900/50 border border-dark-700/50 mb-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <TriggerIcon className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
            <span className="text-xs text-dark-200 truncate">{describeTrigger(rule)}</span>
          </div>
          <div className="flex items-center gap-2">
            <ArrowRight className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
            <span className="text-xs text-primary-400 truncate">{describeAction(rule)}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center justify-between text-xs text-dark-400">
          <div className="flex items-center gap-1">
            <Zap className="w-3 h-3" />
            <span>{rule.trigger_count} раз</span>
          </div>
          {rule.last_triggered_at && (
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{formatDateTime(rule.last_triggered_at)}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
