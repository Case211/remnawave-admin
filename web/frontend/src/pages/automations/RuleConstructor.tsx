import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
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
  HelpCircle,
  Loader2,
  Server,
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
import client from '../../api/client'
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

const TRIGGER_ICONS: Record<string, React.ElementType> = {
  event: Zap,
  schedule: Clock,
  threshold: Activity,
}

// Suggest category based on action type
const ACTION_CATEGORY_MAP: Record<string, string> = {
  disable_user: 'users',
  block_user: 'users',
  reset_traffic: 'users',
  notify: 'system',
  restart_node: 'nodes',
  cleanup_expired: 'system',
  force_sync: 'system',
}

export function RuleConstructor({ open, onOpenChange, editRule }: RuleConstructorProps) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const STEP_LABELS = [
    t('automations.constructor.steps.trigger'),
    t('automations.constructor.steps.conditions'),
    t('automations.constructor.steps.action'),
    t('automations.constructor.steps.review'),
  ]
  const STEP_DESCRIPTIONS = [
    t('automations.constructor.stepDescs.trigger'),
    t('automations.constructor.stepDescs.conditions'),
    t('automations.constructor.stepDescs.action'),
    t('automations.constructor.stepDescs.review'),
  ]

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

  // Target selectors
  const [targetNodeUuid, setTargetNodeUuid] = useState('')  // '' = all nodes

  // Fetch nodes for the target selector
  const { data: nodesList, isLoading: nodesLoading } = useQuery({
    queryKey: ['automation-nodes'],
    queryFn: async () => {
      const { data: resp } = await client.get('/nodes')
      return (resp.items || resp) as Array<{
        uuid: string
        name: string
        address: string
        is_connected: boolean
        is_disabled: boolean
      }>
    },
    enabled: open && actionType === 'restart_node',
    staleTime: 30_000,
  })

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

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const tc = editRule.trigger_config as Record<string, any>
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
        // Target selectors
        setTargetNodeUuid(ac.node_uuid?.toString() || '')

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
        setTargetNodeUuid('')
        setStep(1)
      }
    }
  }, [open, editRule])

  // Auto-suggest category when action type changes (only for new rules)
  useEffect(() => {
    if (!editRule && ACTION_CATEGORY_MAP[actionType]) {
      setCategory(ACTION_CATEGORY_MAP[actionType])
    }
  }, [actionType, editRule])

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
    if (actionType === 'restart_node' && targetNodeUuid) {
      return { node_uuid: targetNodeUuid }
    }
    return {}
  }

  const createMutation = useMutation({
    mutationFn: (data: AutomationRuleCreate) => automationsApi.create(data),
    onSuccess: () => {
      toast.success(t('automations.constructor.ruleCreated'))
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: () => toast.error(t('automations.constructor.createFailed')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: AutomationRuleUpdate }) =>
      automationsApi.update(id, data),
    onSuccess: () => {
      toast.success(t('automations.constructor.ruleUpdated'))
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      onOpenChange(false)
    },
    onError: () => toast.error(t('automations.constructor.updateFailed')),
  })

  const handleSave = () => {
    const validConditions = conditions
      .filter((c) => c.field && c.value)
      .map((c) => ({
        field: c.field,
        operator: c.operator,
        value: isNaN(Number(c.value)) ? c.value : Number(c.value),
      }))

    const payload = {
      name,
      description: description || null,
      is_enabled: editRule ? editRule.is_enabled : true,
      category,
      trigger_type: triggerType,
      trigger_config: buildTriggerConfig(),
      conditions: validConditions,
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
        if (scheduleMode === 'cron') return !!cronExpr.trim()
        return !!intervalMinutes
      }
      if (triggerType === 'threshold') return !!(thresholdMetric && thresholdValue)
    }
    if (step === 2) {
      // Allow proceeding with no conditions, but validate partial ones
      const hasPartial = conditions.some((c) => (c.field && !c.value) || (!c.field && c.value))
      return !hasPartial
    }
    if (step === 3) {
      if (!actionType) return false
      if (actionType === 'notify') {
        if (!notifyMessage.trim()) return false
        if (notifyChannel === 'webhook' && !webhookUrl.trim()) return false
      }
      return true
    }
    if (step === 4) return !!name.trim()
    return true
  }

  // Validation hint for current step
  const getValidationHint = (): string | null => {
    if (step === 1) {
      if (triggerType === 'schedule') {
        if (scheduleMode === 'cron' && !cronExpr.trim()) return t('automations.constructor.validationCron')
        if (scheduleMode === 'interval' && !intervalMinutes) return t('automations.constructor.validationInterval')
      }
      if (triggerType === 'threshold' && !thresholdValue) return t('automations.constructor.validationThreshold')
    }
    if (step === 2) {
      const hasPartial = conditions.some((c) => (c.field && !c.value) || (!c.field && c.value))
      if (hasPartial) return t('automations.constructor.validationConditions')
    }
    if (step === 3) {
      if (actionType === 'notify' && !notifyMessage.trim()) return t('automations.constructor.validationMessage')
      if (actionType === 'notify' && notifyChannel === 'webhook' && !webhookUrl.trim()) return t('automations.constructor.validationWebhook')
    }
    if (step === 4 && !name.trim()) return t('automations.constructor.validationName')
    return null
  }

  // Get the currently selected descriptions
  const selectedMetric = THRESHOLD_METRICS.find((m) => m.value === thresholdMetric)
  const validationHint = getValidationHint()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editRule ? t('automations.constructor.editTitle') : t('automations.constructor.newTitle')}
          </DialogTitle>
          <p className="text-xs text-dark-400 mt-1">
            {editRule
              ? t('automations.constructor.editSubtitle')
              : t('automations.constructor.newSubtitle')}
          </p>
        </DialogHeader>

        {/* Step indicator */}
        <div className="flex items-center gap-1 pb-2 border-b border-dark-700/50 mb-1">
          {[1, 2, 3, 4].map((s) => (
            <div key={s} className="flex items-center">
              <button
                onClick={() => { if (s < step) setStep(s) }}
                disabled={s > step}
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
                  s === step
                    ? 'bg-accent-teal text-white'
                    : s < step
                      ? 'bg-accent-teal/20 text-accent-teal cursor-pointer hover:bg-accent-teal/30'
                      : 'bg-dark-700 text-dark-400'
                }`}
              >
                {s < step ? <Check className="w-3.5 h-3.5" /> : s}
              </button>
              {s < 4 && (
                <div
                  className={`w-8 h-0.5 mx-1 ${
                    s < step ? 'bg-accent-teal/40' : 'bg-dark-700'
                  }`}
                />
              )}
            </div>
          ))}
          <div className="ml-3">
            <span className="text-xs font-medium text-dark-300">
              {STEP_LABELS[step - 1]}
            </span>
            <p className="text-[10px] text-dark-500">{STEP_DESCRIPTIONS[step - 1]}</p>
          </div>
        </div>

        {/* Step 1: Trigger */}
        {step === 1 && (
          <div className="space-y-4">
            {/* Trigger type selection */}
            <div>
              <Label className="text-sm font-medium text-white">{t('automations.constructor.triggerQuestion')}</Label>
              <p className="text-xs text-dark-400 mt-1">
                {t('automations.constructor.triggerHint')}
              </p>
              <div className="grid grid-cols-3 gap-2 mt-3">
                {TRIGGER_TYPES.map((tt) => {
                  const Icon = TRIGGER_ICONS[tt.value] || Zap
                  return (
                    <button
                      key={tt.value}
                      onClick={() => setTriggerType(tt.value)}
                      className={`p-3 rounded-lg border-2 text-left transition-all ${
                        triggerType === tt.value
                          ? 'border-accent-teal bg-accent-teal/10 shadow-sm shadow-accent-teal/10'
                          : 'border-dark-600 bg-dark-800 hover:border-dark-500 hover:bg-dark-750'
                      }`}
                    >
                      <Icon className={`w-4 h-4 mb-1.5 ${triggerType === tt.value ? 'text-accent-teal' : 'text-dark-300'}`} />
                      <p className="text-sm font-medium text-white">{tt.label}</p>
                      <p className="text-[11px] text-dark-400 mt-1 leading-snug">{tt.description}</p>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Event config */}
            {triggerType === 'event' && (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                  <div className="flex items-start gap-2">
                    <HelpCircle className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-blue-300/80">
                      {t('automations.constructor.eventHint')}
                    </p>
                  </div>
                </div>

                <div>
                  <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.eventQuestion')}</Label>
                  <div className="grid gap-2 mt-2">
                    {EVENT_TYPES.map((e) => (
                      <button
                        key={e.value}
                        onClick={() => setEventType(e.value)}
                        className={`flex items-start gap-3 p-3 rounded-lg border-2 text-left transition-all ${
                          eventType === e.value
                            ? 'border-accent-teal bg-accent-teal/10'
                            : 'border-dark-600 bg-dark-800 hover:border-dark-500'
                        }`}
                      >
                        <div className="flex-1">
                          <p className="text-sm font-medium text-white">{e.label}</p>
                          <p className="text-xs text-dark-400 mt-0.5">{e.description}</p>
                        </div>
                        {eventType === e.value && (
                          <Check className="w-4 h-4 text-accent-teal flex-shrink-0 mt-0.5" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
                {eventType === 'violation.detected' && (
                  <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                    <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.minScore')}</Label>
                    <p className="text-xs text-dark-400">
                      {t('automations.constructor.minScoreHint')}
                    </p>
                    <Input
                      type="number"
                      value={minScore}
                      onChange={(e) => setMinScore(e.target.value)}
                      className="bg-dark-900 border-dark-500 text-white w-32"
                      placeholder={t('automations.constructor.minScorePlaceholder')}
                    />
                    <p className="text-[11px] text-dark-500 italic">{t('automations.constructor.optionalField')}</p>
                  </div>
                )}
                {eventType === 'node.went_offline' && (
                  <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                    <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.minOffline')}</Label>
                    <p className="text-xs text-dark-400">
                      {t('automations.constructor.minOfflineHint')}
                    </p>
                    <Input
                      type="number"
                      value={offlineMinutes}
                      onChange={(e) => setOfflineMinutes(e.target.value)}
                      className="bg-dark-900 border-dark-500 text-white w-32"
                      placeholder={t('automations.constructor.minOfflinePlaceholder')}
                    />
                    {offlineMinutes && (
                      <p className="text-xs text-accent-teal">
                        {t('automations.constructor.firesAfterOffline', { minutes: offlineMinutes })}
                      </p>
                    )}
                    <p className="text-[11px] text-dark-500 italic">{t('automations.constructor.optionalField')}</p>
                  </div>
                )}
              </div>
            )}

            {/* Schedule config */}
            {triggerType === 'schedule' && (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                  <div className="flex items-start gap-2">
                    <HelpCircle className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-blue-300/80">
                      {t('automations.constructor.scheduleHint')}
                    </p>
                  </div>
                </div>

                {/* Sub-mode toggle */}
                <div className="flex gap-1 p-1 rounded-lg bg-dark-800 border-2 border-dark-600">
                  <button
                    onClick={() => setScheduleMode('cron')}
                    className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all ${
                      scheduleMode === 'cron'
                        ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30 shadow-sm'
                        : 'text-dark-300 hover:text-dark-200 border border-transparent'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5 inline mr-1.5" />
                    {t('automations.constructor.cronMode')}
                  </button>
                  <button
                    onClick={() => setScheduleMode('interval')}
                    className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all ${
                      scheduleMode === 'interval'
                        ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30 shadow-sm'
                        : 'text-dark-300 hover:text-dark-200 border border-transparent'
                    }`}
                  >
                    <Activity className="w-3.5 h-3.5 inline mr-1.5" />
                    {t('automations.constructor.intervalMode')}
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
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                  <div className="flex items-start gap-2">
                    <HelpCircle className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-blue-300/80">
                      {t('automations.constructor.thresholdHint')}
                    </p>
                  </div>
                </div>

                <div>
                  <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.metricQuestion')}</Label>
                  <div className="grid gap-2 mt-2">
                    {THRESHOLD_METRICS.map((m) => (
                      <button
                        key={m.value}
                        onClick={() => setThresholdMetric(m.value)}
                        className={`flex items-start gap-3 p-3 rounded-lg border-2 text-left transition-all ${
                          thresholdMetric === m.value
                            ? 'border-accent-teal bg-accent-teal/10'
                            : 'border-dark-600 bg-dark-800 hover:border-dark-500'
                        }`}
                      >
                        <div className="flex-1">
                          <p className="text-sm font-medium text-white">{m.label}</p>
                          <p className="text-xs text-dark-400 mt-0.5">{m.description}</p>
                        </div>
                        {thresholdMetric === m.value && (
                          <Check className="w-4 h-4 text-accent-teal flex-shrink-0 mt-0.5" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-3">
                  <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.triggerCondition')}</Label>
                  <p className="text-xs text-dark-400">
                    {t('automations.constructor.metricConditionHint', { metric: selectedMetric?.label || thresholdMetric })}
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-[11px] text-dark-400">{t('automations.constructor.comparison')}</Label>
                      <Select value={thresholdOperator} onValueChange={setThresholdOperator}>
                        <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
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
                      <Label className="text-[11px] text-dark-400">{t('automations.constructor.thresholdValue')} <span className="text-red-400">*</span></Label>
                      <Input
                        type="number"
                        value={thresholdValue}
                        onChange={(e) => setThresholdValue(e.target.value)}
                        className="mt-1 bg-dark-900 border-dark-500 text-white"
                        placeholder="90"
                      />
                    </div>
                  </div>
                  {thresholdValue && (
                    <div className="flex items-center gap-2 p-2.5 rounded-md bg-yellow-500/5 border border-yellow-500/20">
                      <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                      <span className="text-xs text-yellow-200/80">
                        {t('automations.constructor.firesWhen', {
                          metric: selectedMetric?.label || thresholdMetric,
                          operator: CONDITION_OPERATORS.find((o) => o.value === thresholdOperator)?.label || thresholdOperator,
                          value: thresholdValue,
                        })}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Category */}
            <div className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
              <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.categoryLabel')}</Label>
              <p className="text-xs text-dark-400">
                {t('automations.constructor.categoryHint')}{!editRule && ' ' + t('automations.constructor.categoryAutoHint')}
              </p>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="bg-dark-900 border-dark-500 text-white">
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
            <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-blue-300/90">{t('automations.constructor.conditionsTitle')}</p>
                  <p className="text-xs text-blue-300/60 mt-1 leading-relaxed">
                    {t('automations.constructor.conditionsHint')}
                  </p>
                </div>
              </div>
            </div>

            {conditions.map((cond, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-300 font-medium">{t('automations.constructor.conditionN', { n: idx + 1 })}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                    onClick={() => removeCondition(idx)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
                <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
                  <div>
                    <Label className="text-[11px] text-dark-400">{t('automations.constructor.field')}</Label>
                    <Select
                      value={cond.field || '_custom'}
                      onValueChange={(v) => updateCondition(idx, 'field', v === '_custom' ? '' : v)}
                    >
                      <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
                        <SelectValue placeholder={t('automations.constructor.selectField')} />
                      </SelectTrigger>
                      <SelectContent>
                        {CONDITION_FIELDS.map((f) => (
                          <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                        ))}
                        <SelectItem value="_custom">{t('automations.constructor.otherField')}</SelectItem>
                      </SelectContent>
                    </Select>
                    {/* Show custom input if field is not from preset */}
                    {!CONDITION_FIELDS.some((f) => f.value === cond.field) && (
                      <Input
                        value={cond.field}
                        onChange={(e) => updateCondition(idx, 'field', e.target.value)}
                        className="mt-1.5 bg-dark-900 border-dark-500 text-white"
                        placeholder={t('automations.constructor.fieldName')}
                      />
                    )}
                  </div>
                  <div className="w-36">
                    <Label className="text-[11px] text-dark-400">{t('automations.constructor.comparisonLabel')}</Label>
                    <Select
                      value={cond.operator}
                      onValueChange={(v) => updateCondition(idx, 'operator', v)}
                    >
                      <SelectTrigger className="mt-1 bg-dark-900 border-dark-500 text-white">
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
                    <Label className="text-[11px] text-dark-400">{t('automations.constructor.valueLabel')}</Label>
                    <Input
                      value={cond.value}
                      onChange={(e) => updateCondition(idx, 'value', e.target.value)}
                      className="mt-1 bg-dark-900 border-dark-500 text-white"
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
              className="text-xs border-dark-600 hover:border-dark-500"
            >
              <Plus className="w-3.5 h-3.5 mr-1" /> {t('automations.constructor.addCondition')}
            </Button>

            {conditions.length === 0 && (
              <div className="text-center py-6 rounded-lg border border-dashed border-dark-600 bg-dark-800/30">
                <Shield className="w-8 h-8 text-dark-500 mx-auto mb-2" />
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.noConditions')}
                </p>
                <p className="text-[11px] text-dark-500 mt-1">
                  {t('automations.constructor.noConditionsHint')}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Step 3: Action */}
        {step === 3 && (
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium text-white">{t('automations.constructor.actionQuestion')}</Label>
              <p className="text-xs text-dark-400 mt-1">
                {t('automations.constructor.actionHint')}
              </p>
              <div className="grid gap-2 mt-3">
                {ACTION_TYPES.map((a) => (
                  <button
                    key={a.value}
                    onClick={() => setActionType(a.value)}
                    className={`flex items-start gap-3 p-3 rounded-lg border-2 text-left transition-all ${
                      actionType === a.value
                        ? 'border-accent-teal bg-accent-teal/10'
                        : 'border-dark-600 bg-dark-800 hover:border-dark-500'
                    }`}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-white">{a.label}</p>
                        <Badge variant="outline" className="text-[9px] text-dark-400 border-dark-600">{a.category}</Badge>
                      </div>
                      <p className="text-xs text-dark-400 mt-0.5">{a.description}</p>
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
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-3">
                <div>
                  <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.notifyConfig')}</Label>
                  <p className="text-xs text-dark-400 mt-0.5">
                    {t('automations.constructor.notifyHint')}
                  </p>
                </div>
                <div>
                  <Label className="text-[11px] text-dark-400">{t('automations.constructor.deliveryChannel')}</Label>
                  <div className="flex gap-2 mt-1.5">
                    <button
                      onClick={() => setNotifyChannel('telegram')}
                      className={`flex-1 py-2.5 px-3 rounded-lg text-xs font-medium transition-all ${
                        notifyChannel === 'telegram'
                          ? 'bg-blue-500/20 text-blue-400 border-2 border-blue-500/40 shadow-sm'
                          : 'bg-dark-900 text-dark-300 border-2 border-dark-500 hover:border-dark-400'
                      }`}
                    >
                      Telegram
                    </button>
                    <button
                      onClick={() => setNotifyChannel('webhook')}
                      className={`flex-1 py-2.5 px-3 rounded-lg text-xs font-medium transition-all ${
                        notifyChannel === 'webhook'
                          ? 'bg-orange-500/20 text-orange-400 border-2 border-orange-500/40 shadow-sm'
                          : 'bg-dark-900 text-dark-300 border-2 border-dark-500 hover:border-dark-400'
                      }`}
                    >
                      Webhook
                    </button>
                  </div>
                </div>
                <div>
                  <Label className="text-[11px] text-dark-400">
                    {t('automations.constructor.messageText')} <span className="text-red-400">*</span>
                  </Label>
                  <Input
                    value={notifyMessage}
                    onChange={(e) => setNotifyMessage(e.target.value)}
                    className="mt-1 bg-dark-900 border-dark-500 text-white"
                    placeholder={t('automations.constructor.messagePlaceholder')}
                  />
                  <div className="mt-1.5 p-2 rounded-md bg-dark-900/50 border border-dark-600">
                    <p className="text-[11px] text-dark-400">
                      {t('automations.constructor.availableVars')}{' '}
                      <code className="text-accent-teal">{'{user}'}</code>,{' '}
                      <code className="text-accent-teal">{'{node}'}</code>,{' '}
                      <code className="text-accent-teal">{'{rule_name}'}</code>,{' '}
                      <code className="text-accent-teal">{'{timestamp}'}</code>
                    </p>
                  </div>
                </div>
                {notifyChannel === 'webhook' && (
                  <div>
                    <Label className="text-[11px] text-dark-400">
                      {t('automations.constructor.webhookUrl')} <span className="text-red-400">*</span>
                    </Label>
                    <Input
                      value={webhookUrl}
                      onChange={(e) => setWebhookUrl(e.target.value)}
                      className="mt-1 bg-dark-900 border-dark-500 text-white"
                      placeholder="https://example.com/webhook"
                    />
                    <p className="text-[11px] text-dark-500 mt-1">
                      {t('automations.constructor.webhookHint')}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Block user config */}
            {actionType === 'block_user' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.blockReason')}</Label>
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.blockReasonHint')}
                </p>
                <Input
                  value={blockReason}
                  onChange={(e) => setBlockReason(e.target.value)}
                  className="bg-dark-900 border-dark-500 text-white"
                  placeholder={t('automations.constructor.blockReasonPlaceholder')}
                />
                {triggerType === 'event' || triggerType === 'threshold' ? (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-blue-500/5 border border-blue-500/20">
                    <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                    <span className="text-[11px] text-blue-300/80">
                      {t('automations.constructor.targetAutomatic')}
                    </span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-yellow-500/5 border border-yellow-500/20">
                    <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                    <span className="text-[11px] text-yellow-300/80">
                      {t('automations.constructor.blockScheduleWarn')}
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-2 p-2 rounded-md bg-red-500/5 border border-red-500/20">
                  <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                  <span className="text-[11px] text-red-300/80">
                    {t('automations.constructor.blockWarning')}
                  </span>
                </div>
              </div>
            )}

            {/* Disable user warning */}
            {actionType === 'disable_user' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.disableUserTitle')}</Label>
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.disableUserHint')}
                </p>
                {triggerType === 'event' || triggerType === 'threshold' ? (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-blue-500/5 border border-blue-500/20">
                    <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                    <span className="text-[11px] text-blue-300/80">
                      {t('automations.constructor.targetAutomatic')}
                    </span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-yellow-500/5 border border-yellow-500/20">
                    <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                    <span className="text-[11px] text-yellow-300/80">
                      {t('automations.constructor.disableScheduleWarn')}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Cleanup config */}
            {actionType === 'cleanup_expired' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.cleanupTitle')}</Label>
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.cleanupHint')}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-dark-300">{t('automations.constructor.expiredOlderThan')}</span>
                  <Input
                    type="number"
                    value={cleanupDays}
                    onChange={(e) => setCleanupDays(e.target.value)}
                    className="bg-dark-900 border-dark-500 text-white w-20"
                    placeholder="30"
                  />
                  <span className="text-xs text-dark-300">{t('automations.constructor.days')}</span>
                </div>
              </div>
            )}

            {/* Restart node config with target selector */}
            {actionType === 'restart_node' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-3">
                <div>
                  <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.restartNodeTitle')}</Label>
                  <p className="text-xs text-dark-400 mt-0.5">
                    {t('automations.constructor.restartNodeHint')}
                  </p>
                </div>

                {/* Target node selection */}
                <div className="space-y-2">
                  <Label className="text-[11px] text-dark-400">
                    {t('automations.constructor.whichNode')}
                    {triggerType === 'event' && (
                      <span className="text-dark-500 ml-1">{t('automations.constructor.eventNodeHint')}</span>
                    )}
                  </Label>

                  {/* Mode toggle */}
                  <div className="flex gap-1 p-1 rounded-lg bg-dark-900 border border-dark-600">
                    <button
                      onClick={() => setTargetNodeUuid('')}
                      className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all ${
                        !targetNodeUuid
                          ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30 shadow-sm'
                          : 'text-dark-300 hover:text-dark-200 border border-transparent'
                      }`}
                    >
                      {triggerType === 'event' ? t('automations.constructor.fromTriggerOrAll') : t('automations.constructor.allNodes')}
                    </button>
                    <button
                      onClick={() => setTargetNodeUuid('_select')}
                      className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all ${
                        targetNodeUuid
                          ? 'bg-accent-teal/20 text-accent-teal border border-accent-teal/30 shadow-sm'
                          : 'text-dark-300 hover:text-dark-200 border border-transparent'
                      }`}
                    >
                      {t('automations.constructor.specificNode')}
                    </button>
                  </div>

                  {/* Node selector dropdown */}
                  {targetNodeUuid && (
                    <div>
                      {nodesLoading ? (
                        <div className="flex items-center gap-2 py-3 justify-center text-dark-400">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span className="text-xs">{t('automations.constructor.loadingNodes')}</span>
                        </div>
                      ) : nodesList && nodesList.length > 0 ? (
                        <Select
                          value={targetNodeUuid === '_select' ? '' : targetNodeUuid}
                          onValueChange={setTargetNodeUuid}
                        >
                          <SelectTrigger className="bg-dark-900 border-dark-500 text-white">
                            <SelectValue placeholder={t('automations.constructor.selectNode')} />
                          </SelectTrigger>
                          <SelectContent>
                            {nodesList.map((node) => (
                              <SelectItem key={node.uuid} value={node.uuid}>
                                <div className="flex items-center gap-2">
                                  <Server className="w-3 h-3 flex-shrink-0" />
                                  <span>{node.name}</span>
                                  <span className="text-dark-500 text-[10px]">{node.address}</span>
                                  <span
                                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                      node.is_connected ? 'bg-emerald-400' : 'bg-red-400'
                                    }`}
                                  />
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <p className="text-xs text-dark-500 py-2">{t('automations.constructor.noNodesFound')}</p>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 p-2 rounded-md bg-yellow-500/5 border border-yellow-500/20">
                  <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                  <span className="text-[11px] text-yellow-300/80">
                    {targetNodeUuid && targetNodeUuid !== '_select'
                      ? t('automations.constructor.restartSelectedWarn')
                      : t('automations.constructor.restartAllWarn')}
                  </span>
                </div>
              </div>
            )}

            {/* Reset traffic info */}
            {actionType === 'reset_traffic' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.resetTrafficTitle')}</Label>
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.resetTrafficHint')}
                </p>
                {triggerType === 'event' || triggerType === 'threshold' ? (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-blue-500/5 border border-blue-500/20">
                    <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                    <span className="text-[11px] text-blue-300/80">
                      {t('automations.constructor.targetAutomatic')}
                    </span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 p-2 rounded-md bg-yellow-500/5 border border-yellow-500/20">
                    <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                    <span className="text-[11px] text-yellow-300/80">
                      {t('automations.constructor.resetTrafficScheduleWarn')}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Force sync info */}
            {actionType === 'force_sync' && (
              <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-2">
                <Label className="text-xs font-medium text-dark-300">{t('automations.constructor.forceSyncTitle')}</Label>
                <p className="text-xs text-dark-400">
                  {t('automations.constructor.forceSyncHint')}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Name & Review */}
        {step === 4 && (
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-dark-800 border-2 border-dark-600 space-y-3">
              <div>
                <Label className="text-sm font-medium text-white">
                  {t('automations.constructor.ruleNameLabel')} <span className="text-red-400">*</span>
                </Label>
                <p className="text-xs text-dark-400 mt-0.5">
                  {t('automations.constructor.ruleNameHint')}
                </p>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-2 bg-dark-900 border-dark-500 text-white"
                  placeholder={t('automations.constructor.ruleNamePlaceholder')}
                />
              </div>
              <div>
                <Label className="text-xs text-dark-400">{t('automations.constructor.descriptionLabel')}</Label>
                <p className="text-[11px] text-dark-500 mt-0.5">
                  {t('automations.constructor.descriptionHint')}
                </p>
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="mt-1 bg-dark-900 border-dark-500 text-white"
                  placeholder={t('automations.constructor.descriptionPlaceholder')}
                />
                <p className="text-[11px] text-dark-500 mt-0.5 italic">{t('automations.constructor.optionalField')}</p>
              </div>
            </div>

            {/* Summary */}
            <div className="rounded-lg border-2 border-dark-600 bg-dark-800 p-4 space-y-4">
              <p className="text-xs font-semibold text-dark-300 uppercase tracking-wider">{t('automations.constructor.summary')}</p>

              {/* Category & type badges */}
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={`text-[10px] ${categoryColor(category)}`}>
                  {categoryLabel(category)}
                </Badge>
                <Badge variant="outline" className="text-[10px] bg-dark-700/50 text-dark-300 border-dark-500">
                  {triggerTypeLabel(triggerType)}
                </Badge>
              </div>

              {/* Trigger description */}
              <div className="p-3 rounded-lg bg-dark-900 border border-dark-600 space-y-1.5">
                <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">{t('automations.constructor.whenLabel')}</p>
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                  <span className="text-sm text-dark-200">
                    {describeTrigger({
                      trigger_type: triggerType,
                      trigger_config: buildTriggerConfig(),
                    })}
                  </span>
                </div>
              </div>

              {/* Conditions */}
              {conditions.filter((c) => c.field && c.value).length > 0 && (
                <div className="p-3 rounded-lg bg-dark-900 border border-dark-600 space-y-1.5">
                  <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">{t('automations.constructor.conditionsAllLabel')}</p>
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
              <div className="p-3 rounded-lg bg-dark-900 border border-dark-600 space-y-1.5">
                <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">{t('automations.constructor.thenLabel')}</p>
                <div className="flex items-center gap-2">
                  <ArrowRight className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
                  <span className="text-sm text-primary-400">
                    {describeAction({
                      action_type: actionType,
                      action_config: buildActionConfig(),
                    })}
                  </span>
                </div>
                {/* Target info */}
                {actionType === 'restart_node' && (
                  <div className="flex items-center gap-2 mt-1">
                    <Server className="w-3 h-3 text-dark-400 flex-shrink-0" />
                    <span className="text-xs text-dark-300">
                      {targetNodeUuid && targetNodeUuid !== '_select'
                        ? t('automations.constructor.nodeTarget', { name: nodesList?.find((n) => n.uuid === targetNodeUuid)?.name || targetNodeUuid })
                        : triggerType === 'event'
                          ? t('automations.constructor.targetFromTrigger')
                          : t('automations.constructor.targetAllNodes')}
                    </span>
                  </div>
                )}
                {['disable_user', 'block_user', 'reset_traffic'].includes(actionType) && (
                  <div className="flex items-center gap-2 mt-1">
                    <Info className="w-3 h-3 text-dark-400 flex-shrink-0" />
                    <span className="text-xs text-dark-300">
                      {triggerType === 'event' || triggerType === 'threshold'
                        ? t('automations.constructor.targetAutoFromTrigger')
                        : t('automations.constructor.targetUndefined')}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Footer navigation */}
        <DialogFooter className="flex justify-between sm:justify-between pt-4 border-t border-dark-700/50">
          <div>
            {step > 1 && (
              <Button variant="outline" size="sm" onClick={() => setStep((s) => s - 1)} className="border-dark-600">
                <ChevronLeft className="w-4 h-4 mr-1" /> {t('automations.constructor.back')}
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {validationHint && (
              <span className="text-[11px] text-yellow-400/80 max-w-[200px] text-right hidden sm:block">
                {validationHint}
              </span>
            )}
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              {t('automations.constructor.cancel')}
            </Button>
            {step < 4 ? (
              <Button
                size="sm"
                onClick={() => setStep((s) => s + 1)}
                disabled={!canProceed()}
                className="bg-accent-teal text-white hover:bg-accent-teal/90 disabled:opacity-40"
              >
                {t('automations.constructor.next')} <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={!canProceed() || isSaving}
                className="bg-accent-teal text-white hover:bg-accent-teal/90 disabled:opacity-40"
              >
                {isSaving
                  ? t('automations.constructor.saving')
                  : editRule
                    ? t('automations.constructor.save')
                    : t('automations.constructor.createRuleBtn')}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
