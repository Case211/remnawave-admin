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
  Clock,
  AlertTriangle,
  Activity,
  Shield,
  Info,
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
  CONDITION_FIELDS,
  ACTION_TYPES,
  CATEGORIES,
  describeTrigger,
  describeAction,
  categoryLabel,
  categoryColor,
  triggerTypeLabel,
} from './helpers'
import { CronBuilder } from './CronBuilder'
import { IntervalPicker } from './IntervalPicker'

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

const STEP_LABELS = ['Триггер', 'Условия', 'Действие', 'Обзор']

const TRIGGER_ICONS: Record<string, React.ElementType> = {
  event: Zap,
  schedule: Clock,
  threshold: Activity,
}

export function RuleConstructor({ open, onOpenChange, editRule }: RuleConstructorProps) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)

  // Schedule sub-mode: 'cron' or 'interval'
  const [scheduleMode, setScheduleMode] = useState<'cron' | 'interval'>('cron')

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
          setScheduleMode(tc.cron ? 'cron' : 'interval')
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
        setScheduleMode('cron')
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
      if (scheduleMode === 'cron' && cronExpr) return { cron: cronExpr }
      if (scheduleMode === 'interval' && intervalMinutes) return { interval_minutes: parseInt(intervalMinutes) }
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
      if (triggerType === 'schedule') {
        if (scheduleMode === 'cron') return !!cronExpr
        return !!intervalMinutes
      }
      if (triggerType === 'threshold') return !!(thresholdMetric && thresholdValue)
    }
    if (step === 3) return !!actionType
    if (step === 4) return !!name.trim()
    return true
  }

  // Get the currently selected descriptions
  const selectedMetric = THRESHOLD_METRICS.find((m) => m.value === thresholdMetric)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editRule ? 'Редактирование правила' : 'Новое правило автоматизации'}
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
            {STEP_LABELS[step - 1]}
          </span>
        </div>

        {/* Step 1: Trigger */}
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Когда запускать правило?</Label>
              <p className="text-[11px] text-dark-500 mt-0.5">Выберите тип события, которое будет активировать автоматизацию</p>
              <div className="grid grid-cols-3 gap-2 mt-2">
                {TRIGGER_TYPES.map((t) => {
                  const Icon = TRIGGER_ICONS[t.value] || Zap
                  return (
                    <button
                      key={t.value}
                      onClick={() => setTriggerType(t.value)}
                      className={`p-3 rounded-lg border text-left transition-colors ${
                        triggerType === t.value
                          ? 'border-accent-teal bg-accent-teal/10'
                          : 'border-dark-700 bg-dark-800/50 hover:border-dark-600'
                      }`}
                    >
                      <Icon className={`w-4 h-4 mb-1.5 ${triggerType === t.value ? 'text-accent-teal' : 'text-dark-400'}`} />
                      <p className="text-sm font-medium text-white">{t.label}</p>
                      <p className="text-[10px] text-dark-400 mt-1">{t.description}</p>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Event config */}
            {triggerType === 'event' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs text-dark-400">Какое событие отслеживать?</Label>
                  <div className="grid gap-1.5 mt-1.5">
                    {EVENT_TYPES.map((e) => (
                      <button
                        key={e.value}
                        onClick={() => setEventType(e.value)}
                        className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-colors ${
                          eventType === e.value
                            ? 'border-accent-teal bg-accent-teal/10'
                            : 'border-dark-700/50 bg-dark-800/30 hover:border-dark-600'
                        }`}
                      >
                        <div className="flex-1">
                          <p className="text-sm font-medium text-white">{e.label}</p>
                          <p className="text-[10px] text-dark-500 mt-0.5">{e.description}</p>
                        </div>
                        {eventType === e.value && (
                          <Check className="w-4 h-4 text-accent-teal flex-shrink-0 mt-0.5" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
                {eventType === 'violation.detected' && (
                  <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-2">
                    <Label className="text-xs text-dark-400">Минимальная оценка нарушения (необязательно)</Label>
                    <p className="text-[10px] text-dark-500">Правило сработает только если score нарушения не ниже указанного значения</p>
                    <Input
                      type="number"
                      value={minScore}
                      onChange={(e) => setMinScore(e.target.value)}
                      className="bg-dark-800 border-dark-700 w-32"
                      placeholder="например 80"
                    />
                  </div>
                )}
                {eventType === 'node.went_offline' && (
                  <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-2">
                    <Label className="text-xs text-dark-400">Минимальное время офлайн (необязательно)</Label>
                    <p className="text-[10px] text-dark-500">Сработает только если нода недоступна дольше указанного количества минут</p>
                    <Input
                      type="number"
                      value={offlineMinutes}
                      onChange={(e) => setOfflineMinutes(e.target.value)}
                      className="bg-dark-800 border-dark-700 w-32"
                      placeholder="например 5"
                    />
                    {offlineMinutes && (
                      <p className="text-[10px] text-accent-teal">
                        Сработает после {offlineMinutes} мин. офлайн
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Schedule config */}
            {triggerType === 'schedule' && (
              <div className="space-y-3">
                {/* Sub-mode toggle */}
                <div className="flex gap-1 p-0.5 rounded-lg bg-dark-900/50 border border-dark-700/50">
                  <button
                    onClick={() => setScheduleMode('cron')}
                    className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition-colors ${
                      scheduleMode === 'cron'
                        ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30'
                        : 'text-dark-400 hover:text-dark-200 border border-transparent'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5 inline mr-1.5" />
                    По расписанию
                  </button>
                  <button
                    onClick={() => setScheduleMode('interval')}
                    className={`flex-1 py-1.5 px-3 rounded-md text-xs font-medium transition-colors ${
                      scheduleMode === 'interval'
                        ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30'
                        : 'text-dark-400 hover:text-dark-200 border border-transparent'
                    }`}
                  >
                    <Activity className="w-3.5 h-3.5 inline mr-1.5" />
                    Через интервал
                  </button>
                </div>

                {scheduleMode === 'cron' && (
                  <CronBuilder value={cronExpr} onChange={(v) => { setCronExpr(v); setIntervalMinutes('') }} />
                )}

                {scheduleMode === 'interval' && (
                  <IntervalPicker value={intervalMinutes} onChange={(v) => { setIntervalMinutes(v); setCronExpr('') }} />
                )}
              </div>
            )}

            {/* Threshold config */}
            {triggerType === 'threshold' && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs text-dark-400">Какую метрику отслеживать?</Label>
                  <div className="grid gap-1.5 mt-1.5">
                    {THRESHOLD_METRICS.map((m) => (
                      <button
                        key={m.value}
                        onClick={() => setThresholdMetric(m.value)}
                        className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-colors ${
                          thresholdMetric === m.value
                            ? 'border-accent-teal bg-accent-teal/10'
                            : 'border-dark-700/50 bg-dark-800/30 hover:border-dark-600'
                        }`}
                      >
                        <div className="flex-1">
                          <p className="text-sm font-medium text-white">{m.label}</p>
                          <p className="text-[10px] text-dark-500 mt-0.5">{m.description}</p>
                        </div>
                        {thresholdMetric === m.value && (
                          <Check className="w-4 h-4 text-accent-teal flex-shrink-0 mt-0.5" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-3">
                  <Label className="text-xs text-dark-400">Условие срабатывания</Label>
                  <p className="text-[10px] text-dark-500">
                    Правило сработает когда «{selectedMetric?.label || thresholdMetric}» будет соответствовать условию
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-[10px] text-dark-500">Сравнение</Label>
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
                      <Label className="text-[10px] text-dark-500">Пороговое значение</Label>
                      <Input
                        type="number"
                        value={thresholdValue}
                        onChange={(e) => setThresholdValue(e.target.value)}
                        className="mt-1 bg-dark-800 border-dark-700"
                        placeholder="90"
                      />
                    </div>
                  </div>
                  {thresholdValue && (
                    <div className="flex items-center gap-2 p-2 rounded-md bg-dark-800/50 border border-dark-700/30">
                      <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                      <span className="text-[11px] text-dark-300">
                        Сработает когда {selectedMetric?.label || thresholdMetric}{' '}
                        {CONDITION_OPERATORS.find((o) => o.value === thresholdOperator)?.label || thresholdOperator}{' '}
                        {thresholdValue}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Category */}
            <div>
              <Label className="text-xs text-dark-400">Категория правила</Label>
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
            <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-dark-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-dark-300">Дополнительные условия</p>
                  <p className="text-[10px] text-dark-500 mt-0.5">
                    Необязательный шаг. Добавьте условия, если хотите, чтобы правило
                    срабатывало только при выполнении всех указанных критериев.
                  </p>
                </div>
              </div>
            </div>

            {conditions.map((cond, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-dark-800/30 border border-dark-700/50 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-dark-500 font-medium">Условие {idx + 1}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-red-400 hover:text-red-300"
                    onClick={() => removeCondition(idx)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
                  <div>
                    <Label className="text-[10px] text-dark-500">Поле</Label>
                    <Select
                      value={cond.field || '_custom'}
                      onValueChange={(v) => updateCondition(idx, 'field', v === '_custom' ? '' : v)}
                    >
                      <SelectTrigger className="mt-1 bg-dark-800 border-dark-700">
                        <SelectValue placeholder="Выберите поле" />
                      </SelectTrigger>
                      <SelectContent>
                        {CONDITION_FIELDS.map((f) => (
                          <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                        ))}
                        <SelectItem value="_custom">Другое...</SelectItem>
                      </SelectContent>
                    </Select>
                    {(cond.field === '' || !CONDITION_FIELDS.some((f) => f.value === cond.field)) && cond.field !== '' && null}
                    {/* Show custom input if field is not from preset */}
                    {!CONDITION_FIELDS.some((f) => f.value === cond.field) && (
                      <Input
                        value={cond.field}
                        onChange={(e) => updateCondition(idx, 'field', e.target.value)}
                        className="mt-1.5 bg-dark-800 border-dark-700"
                        placeholder="Название поля"
                      />
                    )}
                  </div>
                  <div className="w-36">
                    <Label className="text-[10px] text-dark-500">Сравнение</Label>
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
                  <div className="w-24">
                    <Label className="text-[10px] text-dark-500">Значение</Label>
                    <Input
                      value={cond.value}
                      onChange={(e) => updateCondition(idx, 'value', e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="80"
                    />
                  </div>
                </div>
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

            {conditions.length === 0 && (
              <p className="text-xs text-dark-500 text-center py-4">
                Нет дополнительных условий. Нажмите «Далее» чтобы продолжить без условий.
              </p>
            )}
          </div>
        )}

        {/* Step 3: Action */}
        {step === 3 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Что сделать при срабатывании?</Label>
              <p className="text-[11px] text-dark-500 mt-0.5">Выберите действие, которое будет выполнено автоматически</p>
              <div className="grid gap-1.5 mt-2">
                {ACTION_TYPES.map((a) => (
                  <button
                    key={a.value}
                    onClick={() => setActionType(a.value)}
                    className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-colors ${
                      actionType === a.value
                        ? 'border-accent-teal bg-accent-teal/10'
                        : 'border-dark-700/50 bg-dark-800/30 hover:border-dark-600'
                    }`}
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white">{a.label}</p>
                      <p className="text-[10px] text-dark-500 mt-0.5">{a.description}</p>
                    </div>
                    {actionType === a.value && (
                      <Check className="w-4 h-4 text-accent-teal flex-shrink-0 mt-0.5" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Notify config */}
            {actionType === 'notify' && (
              <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-3">
                <Label className="text-xs text-dark-400">Настройка уведомления</Label>
                <div>
                  <Label className="text-[10px] text-dark-500">Куда отправить?</Label>
                  <div className="flex gap-1.5 mt-1.5">
                    <button
                      onClick={() => setNotifyChannel('telegram')}
                      className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-colors ${
                        notifyChannel === 'telegram'
                          ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                          : 'bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600'
                      }`}
                    >
                      Telegram
                    </button>
                    <button
                      onClick={() => setNotifyChannel('webhook')}
                      className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-colors ${
                        notifyChannel === 'webhook'
                          ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                          : 'bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600'
                      }`}
                    >
                      Webhook
                    </button>
                  </div>
                </div>
                <div>
                  <Label className="text-[10px] text-dark-500">Текст сообщения</Label>
                  <Input
                    value={notifyMessage}
                    onChange={(e) => setNotifyMessage(e.target.value)}
                    className="mt-1 bg-dark-800 border-dark-700"
                    placeholder="Например: Сработала автоматизация для {user}"
                  />
                  <p className="text-[10px] text-dark-500 mt-1">Используйте {'{переменные}'} для подстановки данных из контекста</p>
                </div>
                {notifyChannel === 'webhook' && (
                  <div>
                    <Label className="text-[10px] text-dark-500">URL для Webhook</Label>
                    <Input
                      value={webhookUrl}
                      onChange={(e) => setWebhookUrl(e.target.value)}
                      className="mt-1 bg-dark-800 border-dark-700"
                      placeholder="https://example.com/webhook"
                    />
                  </div>
                )}
              </div>
            )}

            {/* Block user config */}
            {actionType === 'block_user' && (
              <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-2">
                <Label className="text-xs text-dark-400">Причина блокировки</Label>
                <p className="text-[10px] text-dark-500">Эта причина будет отображаться в карточке пользователя</p>
                <Input
                  value={blockReason}
                  onChange={(e) => setBlockReason(e.target.value)}
                  className="bg-dark-800 border-dark-700"
                  placeholder="Например: Обнаружен шеринг аккаунта"
                />
              </div>
            )}

            {/* Cleanup config */}
            {actionType === 'cleanup_expired' && (
              <div className="p-3 rounded-lg bg-dark-900/50 border border-dark-700/50 space-y-2">
                <Label className="text-xs text-dark-400">Порог для очистки</Label>
                <p className="text-[10px] text-dark-500">Отключить пользователей, у которых подписка истекла более N дней назад</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-dark-400">Истекших более</span>
                  <Input
                    type="number"
                    value={cleanupDays}
                    onChange={(e) => setCleanupDays(e.target.value)}
                    className="bg-dark-800 border-dark-700 w-20"
                    placeholder="30"
                  />
                  <span className="text-xs text-dark-400">дней</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Name & Review */}
        {step === 4 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Название правила</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-2 bg-dark-800 border-dark-700"
                placeholder="Например: Блокировка при шеринге"
              />
            </div>
            <div>
              <Label className="text-xs text-dark-400">Описание (необязательно)</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-1 bg-dark-800 border-dark-700"
                placeholder="Кратко опишите назначение этого правила"
              />
            </div>

            {/* Summary */}
            <div className="rounded-lg border border-dark-700 bg-dark-800/50 p-4 space-y-4">
              <p className="text-xs font-medium text-dark-400 uppercase tracking-wider">Сводка правила</p>

              {/* Category & type badges */}
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={`text-[10px] ${categoryColor(category)}`}>
                  {categoryLabel(category)}
                </Badge>
                <Badge variant="outline" className="text-[10px] bg-dark-700/50 text-dark-300 border-dark-600">
                  {triggerTypeLabel(triggerType)}
                </Badge>
              </div>

              {/* Trigger description */}
              <div className="p-3 rounded-md bg-dark-900/50 border border-dark-700/50 space-y-1.5">
                <p className="text-[10px] text-dark-500 font-medium uppercase tracking-wider">Когда</p>
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                  <span className="text-sm text-dark-200">
                    {describeTrigger({
                      trigger_type: triggerType,
                      trigger_config: buildTriggerConfig(),
                    } as any)}
                  </span>
                </div>
              </div>

              {/* Conditions */}
              {conditions.filter((c) => c.field && c.value).length > 0 && (
                <div className="p-3 rounded-md bg-dark-900/50 border border-dark-700/50 space-y-1.5">
                  <p className="text-[10px] text-dark-500 font-medium uppercase tracking-wider">При условиях</p>
                  {conditions.filter((c) => c.field && c.value).map((c, i) => {
                    const fieldLabel = CONDITION_FIELDS.find((f) => f.value === c.field)?.label || c.field
                    const opLabel = CONDITION_OPERATORS.find((o) => o.value === c.operator)?.label || c.operator
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <Shield className="w-3 h-3 text-blue-400 flex-shrink-0" />
                        <span className="text-xs text-dark-300">
                          {fieldLabel} {opLabel} {c.value}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Action description */}
              <div className="p-3 rounded-md bg-dark-900/50 border border-dark-700/50 space-y-1.5">
                <p className="text-[10px] text-dark-500 font-medium uppercase tracking-wider">Тогда</p>
                <div className="flex items-center gap-2">
                  <ArrowRight className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
                  <span className="text-sm text-primary-400">
                    {describeAction({
                      action_type: actionType,
                      action_config: buildActionConfig(),
                    } as any)}
                  </span>
                </div>
              </div>
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
                    : 'Создать правило'}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
