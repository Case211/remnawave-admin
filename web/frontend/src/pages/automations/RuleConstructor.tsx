import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  Check,
  Zap,
  ArrowRight,
} from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  automationsApi,
  type AutomationRule,
  type AutomationRuleCreate,
  type AutomationRuleUpdate,
} from '../../api/automations'
import {
  TRIGGER_TYPES,
  EVENT_TYPES,
  THRESHOLD_METRICS,
  CONDITION_OPERATORS,
  ACTION_TYPES,
  CATEGORIES,
  describeTrigger,
  describeAction,
  categoryLabel,
  triggerTypeLabel,
} from './helpers'

interface Condition {
  field: string
  operator: string
  value: string
}

interface RuleConstructorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editRule: AutomationRule | null
}

export function RuleConstructor({ open, onOpenChange, editRule }: RuleConstructorProps) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('users')
  const [triggerType, setTriggerType] = useState('event')
  const [actionType, setActionType] = useState('notify')

  // Trigger config
  const [eventType, setEventType] = useState('violation.detected')
  const [minScore, setMinScore] = useState('')
  const [offlineMinutes, setOfflineMinutes] = useState('')
  const [cronExpr, setCronExpr] = useState('')
  const [intervalMinutes, setIntervalMinutes] = useState('')
  const [thresholdMetric, setThresholdMetric] = useState('users_online')
  const [thresholdOperator, setThresholdOperator] = useState('>=')
  const [thresholdValue, setThresholdValue] = useState('')

  // Conditions
  const [conditions, setConditions] = useState<Condition[]>([])

  // Action config
  const [notifyChannel, setNotifyChannel] = useState('telegram')
  const [notifyMessage, setNotifyMessage] = useState('')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [blockReason, setBlockReason] = useState('')
  const [cleanupDays, setCleanupDays] = useState('30')

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (open) {
      if (editRule) {
        // Pre-fill from existing rule
        setName(editRule.name)
        setDescription(editRule.description || '')
        setCategory(editRule.category)
        setTriggerType(editRule.trigger_type)
        setActionType(editRule.action_type)

        const tc = editRule.trigger_config as Record<string, any>
        const ac = editRule.action_config as Record<string, any>

        // Trigger config
        if (editRule.trigger_type === 'event') {
          setEventType(tc.event || 'violation.detected')
          setMinScore(tc.min_score?.toString() || '')
          setOfflineMinutes(tc.offline_minutes?.toString() || '')
        } else if (editRule.trigger_type === 'schedule') {
          setCronExpr(tc.cron || '')
          setIntervalMinutes(tc.interval_minutes?.toString() || '')
        } else if (editRule.trigger_type === 'threshold') {
          setThresholdMetric(tc.metric || 'users_online')
          setThresholdOperator(tc.operator || '>=')
          setThresholdValue(tc.value?.toString() || '')
        }

        // Conditions
        const conds = editRule.conditions as Array<Record<string, any>>
        setConditions(
          conds.map((c) => ({
            field: c.field || '',
            operator: c.operator || '>=',
            value: c.value?.toString() || '',
          }))
        )

        // Action config
        if (editRule.action_type === 'notify') {
          setNotifyChannel(ac.channel || 'telegram')
          setNotifyMessage(ac.message || '')
          setWebhookUrl(ac.webhook_url || '')
        } else if (editRule.action_type === 'block_user') {
          setBlockReason(ac.reason || '')
        } else if (editRule.action_type === 'cleanup_expired') {
          setCleanupDays(ac.older_than_days?.toString() || '30')
        }

        setStep(1)
      } else {
        // Reset to defaults
        setName('')
        setDescription('')
        setCategory('users')
        setTriggerType('event')
        setActionType('notify')
        setEventType('violation.detected')
        setMinScore('')
        setOfflineMinutes('')
        setCronExpr('')
        setIntervalMinutes('')
        setThresholdMetric('users_online')
        setThresholdOperator('>=')
        setThresholdValue('')
        setConditions([])
        setNotifyChannel('telegram')
        setNotifyMessage('')
        setWebhookUrl('')
        setBlockReason('')
        setCleanupDays('30')
        setStep(1)
      }
    }
  }, [open, editRule])

  // Build trigger_config
  const buildTriggerConfig = (): Record<string, unknown> => {
    if (triggerType === 'event') {
      const cfg: Record<string, unknown> = { event: eventType }
      if (minScore) cfg.min_score = parseInt(minScore)
      if (offlineMinutes) cfg.offline_minutes = parseInt(offlineMinutes)
      return cfg
    }
    if (triggerType === 'schedule') {
      if (cronExpr) return { cron: cronExpr }
      if (intervalMinutes) return { interval_minutes: parseInt(intervalMinutes) }
      return {}
    }
    if (triggerType === 'threshold') {
      return {
        metric: thresholdMetric,
        operator: thresholdOperator,
        value: parseFloat(thresholdValue) || 0,
      }
    }
    return {}
  }

  // Build action_config
  const buildActionConfig = (): Record<string, unknown> => {
    if (actionType === 'notify') {
      const cfg: Record<string, unknown> = { channel: notifyChannel, message: notifyMessage }
      if (notifyChannel === 'webhook') cfg.webhook_url = webhookUrl
      return cfg
    }
    if (actionType === 'block_user') {
      return { reason: blockReason || 'Blocked by automation' }
    }
    if (actionType === 'cleanup_expired') {
      return { older_than_days: parseInt(cleanupDays) || 30 }
    }
    return {}
  }

  const createMutation = useMutation({
    mutationFn: (data: AutomationRuleCreate) => automationsApi.create(data),
    onSuccess: () => {
      toast.success('Правило создано')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: () => toast.error('Не удалось создать правило'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: AutomationRuleUpdate }) =>
      automationsApi.update(id, data),
    onSuccess: () => {
      toast.success('Правило обновлено')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: () => toast.error('Не удалось обновить правило'),
  })

  const handleSave = () => {
    const payload = {
      name,
      description: description || null,
      category,
      trigger_type: triggerType,
      trigger_config: buildTriggerConfig(),
      conditions: conditions
        .filter((c) => c.field && c.value)
        .map((c) => ({
          field: c.field,
          operator: c.operator,
          value: isNaN(Number(c.value)) ? c.value : Number(c.value),
        })),
      action_type: actionType,
      action_config: buildActionConfig(),
    }

    if (editRule) {
      updateMutation.mutate({ id: editRule.id, data: payload })
    } else {
      createMutation.mutate(payload as AutomationRuleCreate)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  const addCondition = () => {
    setConditions((prev) => [...prev, { field: '', operator: '>=', value: '' }])
  }

  const removeCondition = (idx: number) => {
    setConditions((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateCondition = (idx: number, key: keyof Condition, val: string) => {
    setConditions((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, [key]: val } : c))
    )
  }

  const canProceed = (): boolean => {
    if (step === 1) {
      if (triggerType === 'event') return !!eventType
      if (triggerType === 'schedule') return !!(cronExpr || intervalMinutes)
      if (triggerType === 'threshold') return !!(thresholdMetric && thresholdValue)
    }
    if (step === 3) return !!actionType
    if (step === 4) return !!name.trim()
    return true
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editRule ? 'Редактирование правила' : 'Новое правило'}
          </DialogTitle>
        </DialogHeader>

        {/* Step indicator */}
        <div className="flex items-center gap-1 pb-2">
          {[1, 2, 3, 4].map((s) => (
            <div key={s} className="flex items-center">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
                  s === step
                    ? 'bg-accent-teal text-white'
                    : s < step
                      ? 'bg-accent-teal/20 text-accent-teal'
                      : 'bg-dark-700 text-dark-400'
                }`}
              >
                {s < step ? <Check className="w-3.5 h-3.5" /> : s}
              </div>
              {s < 4 && (
                <div
                  className={`w-8 h-0.5 mx-1 ${
                    s < step ? 'bg-accent-teal/40' : 'bg-dark-700'
                  }`}
                />
              )}
            </div>
          ))}
          <span className="ml-3 text-xs text-dark-400">
            {step === 1 && 'Триггер'}
            {step === 2 && 'Условия'}
            {step === 3 && 'Действие'}
            {step === 4 && 'Обзор'}
          </span>
        </div>

        {/* Step 1: Trigger */}
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Тип триггера</Label>
              <div className="grid grid-cols-3 gap-2 mt-2">
                {TRIGGER_TYPES.map((t) => (
                  <button
                    key={t.value}
                    onClick={() => setTriggerType(t.value)}
                    className={`p-3 rounded-lg border text-left transition-colors ${
                      triggerType === t.value
                        ? 'border-accent-teal bg-accent-teal/10'
                        : 'border-dark-700 bg-dark-800/50 hover:border-dark-600'
                    }`}
                  >
                    <p className="text-sm font-medium text-white">{t.label}</p>
                    <p className="text-[10px] text-dark-400 mt-1">{t.description}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Event config */}
            {triggerType === 'event' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Событие</Label>
                  <Select value={eventType} onValueChange={setEventType}>
                    <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EVENT_TYPES.map((e) => (
                        <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {eventType === 'violation.detected' && (
                  <div>
                    <Label className="text-xs">Мин. score (опц.)</Label>
                    <Input
                      type="number"
                      value={minScore}
                      onChange={(e) => setMinScore(e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="80"
                    />
                  </div>
                )}
                {eventType === 'node.went_offline' && (
                  <div>
                    <Label className="text-xs">Мин. минут офлайн (опц.)</Label>
                    <Input
                      type="number"
                      value={offlineMinutes}
                      onChange={(e) => setOfflineMinutes(e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="5"
                    />
                  </div>
                )}
              </div>
            )}

            {/* Schedule config */}
            {triggerType === 'schedule' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">CRON-выражение</Label>
                  <Input
                    value={cronExpr}
                    onChange={(e) => { setCronExpr(e.target.value); setIntervalMinutes('') }}
                    className="mt-1 bg-dark-800 border-dark-700 font-mono"
                    placeholder="0 3 * * *  (мин час день мес день_нед)"
                  />
                </div>
                <div className="text-center text-xs text-dark-500">или</div>
                <div>
                  <Label className="text-xs">Интервал (минуты)</Label>
                  <Input
                    type="number"
                    value={intervalMinutes}
                    onChange={(e) => { setIntervalMinutes(e.target.value); setCronExpr('') }}
                    className="mt-1 bg-dark-800 border-dark-700"
                    placeholder="60"
                  />
                </div>
              </div>
            )}

            {/* Threshold config */}
            {triggerType === 'threshold' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Метрика</Label>
                  <Select value={thresholdMetric} onValueChange={setThresholdMetric}>
                    <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {THRESHOLD_METRICS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Оператор</Label>
                    <Select value={thresholdOperator} onValueChange={setThresholdOperator}>
                      <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CONDITION_OPERATORS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-xs">Значение</Label>
                    <Input
                      type="number"
                      value={thresholdValue}
                      onChange={(e) => setThresholdValue(e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="90"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Category */}
            <div>
              <Label className="text-xs">Категория</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        {/* Step 2: Conditions */}
        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-dark-300">
              Дополнительные условия (необязательно). Все условия должны быть выполнены.
            </p>
            {conditions.map((cond, idx) => (
              <div key={idx} className="flex items-end gap-2">
                <div className="flex-1">
                  <Label className="text-xs">Поле</Label>
                  <Input
                    value={cond.field}
                    onChange={(e) => updateCondition(idx, 'field', e.target.value)}
                    className="mt-1 bg-dark-800 border-dark-700"
                    placeholder="score, percent..."
                  />
                </div>
                <div className="w-24">
                  <Label className="text-xs">Оператор</Label>
                  <Select
                    value={cond.operator}
                    onValueChange={(v) => updateCondition(idx, 'operator', v)}
                  >
                    <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CONDITION_OPERATORS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-28">
                  <Label className="text-xs">Значение</Label>
                  <Input
                    value={cond.value}
                    onChange={(e) => updateCondition(idx, 'value', e.target.value)}
                    className="mt-1 bg-dark-800 border-dark-700"
                    placeholder="80"
                  />
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 text-red-400 hover:text-red-300 flex-shrink-0"
                  onClick={() => removeCondition(idx)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}

            <Button
              variant="outline"
              size="sm"
              onClick={addCondition}
              className="text-xs"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> Добавить условие
            </Button>
          </div>
        )}

        {/* Step 3: Action */}
        {step === 3 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Действие</Label>
              <Select value={actionType} onValueChange={setActionType}>
                <SelectTrigger className="mt-2 bg-dark-800 border-dark-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ACTION_TYPES.map((a) => (
                    <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Notify config */}
            {actionType === 'notify' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Канал</Label>
                  <Select value={notifyChannel} onValueChange={setNotifyChannel}>
                    <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="telegram">Telegram</SelectItem>
                      <SelectItem value="webhook">Webhook</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Сообщение</Label>
                  <Input
                    value={notifyMessage}
                    onChange={(e) => setNotifyMessage(e.target.value)}
                    className="mt-1 bg-dark-800 border-dark-700"
                    placeholder="Используйте {переменные} из контекста"
                  />
                </div>
                {notifyChannel === 'webhook' && (
                  <div>
                    <Label className="text-xs">Webhook URL</Label>
                    <Input
                      value={webhookUrl}
                      onChange={(e) => setWebhookUrl(e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="https://..."
                    />
                  </div>
                )}
              </div>
            )}

            {/* Block user config */}
            {actionType === 'block_user' && (
              <div>
                <Label className="text-xs">Причина блокировки</Label>
                <Input
                  value={blockReason}
                  onChange={(e) => setBlockReason(e.target.value)}
                  className="mt-1 bg-dark-800 border-dark-700"
                  placeholder="Sharing detected (auto)"
                />
              </div>
            )}

            {/* Cleanup config */}
            {actionType === 'cleanup_expired' && (
              <div>
                <Label className="text-xs">Истекших более N дней</Label>
                <Input
                  type="number"
                  value={cleanupDays}
                  onChange={(e) => setCleanupDays(e.target.value)}
                  className="mt-1 bg-dark-800 border-dark-700"
                  placeholder="30"
                />
              </div>
            )}
          </div>
        )}

        {/* Step 4: Name & Review */}
        {step === 4 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Название</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-2 bg-dark-800 border-dark-700"
                placeholder="Мое правило автоматизации"
              />
            </div>
            <div>
              <Label className="text-xs">Описание (опц.)</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-1 bg-dark-800 border-dark-700"
                placeholder="Что делает это правило..."
              />
            </div>

            {/* Summary */}
            <div className="rounded-lg border border-dark-700 bg-dark-800/50 p-4 space-y-3">
              <p className="text-xs font-medium text-dark-400 uppercase">Сводка</p>
              <div className="flex items-center gap-2 text-sm">
                <Badge variant="outline" className="text-[10px]">
                  {categoryLabel(category)}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {triggerTypeLabel(triggerType)}
                </Badge>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Zap className="w-3.5 h-3.5 text-yellow-400" />
                <span className="text-dark-200">
                  {describeTrigger({
                    trigger_type: triggerType,
                    trigger_config: buildTriggerConfig(),
                  } as any)}
                </span>
                <ArrowRight className="w-3 h-3 text-dark-500" />
                <span className="text-primary-400">
                  {describeAction({
                    action_type: actionType,
                    action_config: buildActionConfig(),
                  } as any)}
                </span>
              </div>
              {conditions.length > 0 && (
                <p className="text-xs text-dark-400">
                  + {conditions.length} условий
                </p>
              )}
            </div>
          </div>
        )}

        {/* Footer navigation */}
        <DialogFooter className="flex justify-between sm:justify-between pt-4">
          <div>
            {step > 1 && (
              <Button variant="outline" size="sm" onClick={() => setStep((s) => s - 1)}>
                <ChevronLeft className="w-4 h-4 mr-1" /> Назад
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            {step < 4 ? (
              <Button
                size="sm"
                onClick={() => setStep((s) => s + 1)}
                disabled={!canProceed()}
                className="bg-accent-teal text-white hover:bg-accent-teal/90"
              >
                Далее <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={!canProceed() || isSaving}
                className="bg-accent-teal text-white hover:bg-accent-teal/90"
              >
                {isSaving
                  ? 'Сохранение...'
                  : editRule
                    ? 'Сохранить'
                    : 'Создать'}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
