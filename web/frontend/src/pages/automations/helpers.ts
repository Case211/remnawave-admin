
import i18n from '../../i18n'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyConfig = Record<string, any>

const t = (key: string, opts?: Record<string, unknown>) => i18n.t(key, opts)

// ── Category ────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  users: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  nodes: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  violations: 'bg-red-500/20 text-red-400 border-red-500/30',
  system: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
}

export function categoryLabel(cat: string): string {
  return t(`automations.categories.${cat}`, { defaultValue: cat })
}

export function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] || 'bg-dark-700/50 text-dark-200 border-dark-600'
}

// ── Cron to human-readable ──────────────────────────────────

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

export function cronToHuman(expr: string): string {
  if (!expr || !expr.trim()) return ''

  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

  const dayNames = (i18n.t('automations.dayNames', { returnObjects: true }) || []) as string[]
  const dayNamesShort = (i18n.t('automations.dayNamesShort', { returnObjects: true }) || []) as string[]
  const monthNames = (i18n.t('automations.monthNames', { returnObjects: true }) || []) as string[]

  try {
    // Every N minutes: */N * * * *
    if (minute.startsWith('*/') && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      const n = parseInt(minute.slice(2))
      if (n === 1) return t('automations.cron.everyMinute')
      if (n === 5) return t('automations.cron.every5Min')
      if (n === 10) return t('automations.cron.every10Min')
      if (n === 15) return t('automations.cron.every15Min')
      if (n === 30) return t('automations.cron.every30Min')
      return t('automations.cron.everyNMin', { n })
    }

    // Every N hours: 0 */N * * *
    if (minute !== '*' && hour.startsWith('*/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      const n = parseInt(hour.slice(2))
      const m = pad2(parseInt(minute) || 0)
      if (n === 1) return t('automations.cron.everyHourAt', { m })
      return t('automations.cron.everyNHoursAt', { n, m })
    }

    // Every minute: * * * * *
    if (minute === '*' && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return t('automations.cron.everyMinute')
    }

    // Specific minute every hour: N * * * *
    if (/^\d+$/.test(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return t('automations.cron.everyHourAtMin', { m: pad2(parseInt(minute)) })
    }

    const isFixedMinute = /^\d+$/.test(minute)
    const isFixedHour = /^\d+$/.test(hour)
    const isAnyDay = dayOfMonth === '*'
    const isAnyMonth = month === '*'
    const isAnyDow = dayOfWeek === '*'

    // Daily: N N * * *
    if (isFixedMinute && isFixedHour && isAnyDay && isAnyMonth && isAnyDow) {
      return t('automations.cron.everyDayAt', { time: `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}` })
    }

    // Weekly: N N * * D
    if (isFixedMinute && isFixedHour && isAnyDay && isAnyMonth && !isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      // Could be a list: 1,3,5
      if (dayOfWeek.includes(',')) {
        const days = dayOfWeek.split(',').map((d) => dayNamesShort[parseInt(d)] || d)
        return t('automations.cron.daysComma', { days: days.join(', '), time })
      }
      // Range: 1-5
      if (dayOfWeek.includes('-')) {
        const [from, to] = dayOfWeek.split('-').map(Number)
        return t('automations.cron.daysRange', { from: dayNamesShort[from], to: dayNamesShort[to], time })
      }
      const d = parseInt(dayOfWeek)
      return t('automations.cron.everyWeekday', { day: dayNames[d] || dayOfWeek, time })
    }

    // Monthly: N N D * *
    if (isFixedMinute && isFixedHour && /^\d+$/.test(dayOfMonth) && isAnyMonth && isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      const d = parseInt(dayOfMonth)
      return t('automations.cron.monthlyAt', { day: d, time })
    }

    // Yearly: N N D M *
    if (isFixedMinute && isFixedHour && /^\d+$/.test(dayOfMonth) && /^\d+$/.test(month) && isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      const d = parseInt(dayOfMonth)
      const m = parseInt(month)
      return t('automations.cron.yearlyAt', { day: d, month: monthNames[m] || month, time })
    }
  } catch {
    // Fall through to raw expression
  }

  return expr
}

// ── Schedule presets for CronBuilder ────────────────────────

export interface CronPreset {
  id: string
  label: string
  description: string
  cron: string
}

export function getCronPresets(): CronPreset[] {
  const ids = [
    'every_5min', 'every_15min', 'every_30min', 'every_hour',
    'every_3hours', 'every_6hours', 'every_12hours',
    'daily_midnight', 'daily_3am', 'daily_9am', 'daily_23pm',
    'weekly_monday', 'monthly_1st',
  ]
  const crons: Record<string, string> = {
    every_5min: '*/5 * * * *', every_15min: '*/15 * * * *', every_30min: '*/30 * * * *',
    every_hour: '0 * * * *', every_3hours: '0 */3 * * *', every_6hours: '0 */6 * * *',
    every_12hours: '0 */12 * * *', daily_midnight: '0 0 * * *', daily_3am: '0 3 * * *',
    daily_9am: '0 9 * * *', daily_23pm: '0 23 * * *', weekly_monday: '0 9 * * 1',
    monthly_1st: '0 0 1 * *',
  }
  return ids.map((id) => ({
    id,
    label: t(`automations.cronPresets.${id}`, { defaultValue: id }),
    description: crons[id],
    cron: crons[id],
  }))
}

// Keep backward compat – lazy getter
export const CRON_PRESETS = new Proxy([] as CronPreset[], {
  get(_target, prop) {
    const presets = getCronPresets()
    if (prop === Symbol.iterator) return presets[Symbol.iterator].bind(presets)
    if (prop === 'length') return presets.length
    if (prop === 'map') return presets.map.bind(presets)
    if (prop === 'some') return presets.some.bind(presets)
    if (prop === 'find') return presets.find.bind(presets)
    if (prop === 'filter') return presets.filter.bind(presets)
    if (typeof prop === 'string' && !isNaN(Number(prop))) return presets[Number(prop)]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (presets as any)[prop]
  },
})

export function getIntervalPresets() {
  return [
    { value: 5, label: t('automations.intervalPresets.5', { defaultValue: '5 мин' }) },
    { value: 15, label: t('automations.intervalPresets.15', { defaultValue: '15 мин' }) },
    { value: 30, label: t('automations.intervalPresets.30', { defaultValue: '30 мин' }) },
    { value: 60, label: t('automations.intervalPresets.60', { defaultValue: '1 час' }) },
    { value: 120, label: t('automations.intervalPresets.120', { defaultValue: '2 часа' }) },
    { value: 360, label: t('automations.intervalPresets.360', { defaultValue: '6 часов' }) },
    { value: 720, label: t('automations.intervalPresets.720', { defaultValue: '12 часов' }) },
    { value: 1440, label: t('automations.intervalPresets.1440', { defaultValue: '24 часа' }) },
  ] as const
}

export const INTERVAL_PRESETS = new Proxy([] as unknown as ReturnType<typeof getIntervalPresets>, {
  get(_target, prop) {
    const presets = getIntervalPresets()
    if (prop === Symbol.iterator) return presets[Symbol.iterator].bind(presets)
    if (prop === 'length') return presets.length
    if (prop === 'map') return presets.map.bind(presets)
    if (prop === 'some') return presets.some.bind(presets)
    if (prop === 'find') return presets.find.bind(presets)
    if (prop === 'filter') return presets.filter.bind(presets)
    if (typeof prop === 'string' && !isNaN(Number(prop))) return presets[Number(prop)]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (presets as any)[prop]
  },
})

// ── Trigger description ─────────────────────────────────────

const OPERATOR_MAP: Record<string, string> = {
  '==': 'eq', '!=': 'neq', '>': 'gt', '>=': 'gte', '<': 'lt', '<=': 'lte',
  'contains': 'contains', 'not_contains': 'not_contains',
}

function eventLabel(event: string): string {
  const key = event.replace('.', '_')
  return t(`automations.events.${key}`, { defaultValue: event })
}

function metricLabel(metric: string): string {
  return t(`automations.metrics.${metric}`, { defaultValue: metric })
}

function operatorLabel(op: string): string {
  const key = OPERATOR_MAP[op] || op
  return t(`automations.operators.${key}`, { defaultValue: op })
}

export function describeTrigger(rule: { trigger_type: string; trigger_config: Record<string, unknown> }): string {
  const cfg = rule.trigger_config as AnyConfig

  if (rule.trigger_type === 'event') {
    const event = cfg.event || ''
    const label = eventLabel(event)
    const minScore = cfg.min_score
    const offlineMin = cfg.offline_minutes
    let desc = label
    if (minScore) desc += ` (score ≥ ${minScore})`
    if (offlineMin) desc += ` (> ${offlineMin} ${t('automations.cron.min')})`
    return desc
  }

  if (rule.trigger_type === 'schedule') {
    if (cfg.cron) {
      const human = cronToHuman(cfg.cron)
      return human !== cfg.cron ? human : t('automations.cron.schedulePrefix', { cron: cfg.cron })
    }
    if (cfg.interval_minutes) {
      const mins = cfg.interval_minutes
      if (mins < 60) return t('automations.cron.everyNMin', { n: mins })
      if (mins === 60) return t('automations.cron.everyHour')
      if (mins % 60 === 0) {
        const h = mins / 60
        if (h === 24) return t('automations.cron.every24Hours')
        return t('automations.cron.everyNHours', { n: h })
      }
      return t('automations.cron.everyNMin', { n: mins })
    }
    return t('automations.cron.bySchedule')
  }

  if (rule.trigger_type === 'threshold') {
    const metric = metricLabel(cfg.metric || '')
    const op = cfg.operator || '>='
    const opLabel = operatorLabel(op)
    return `${metric} ${opLabel} ${cfg.value ?? ''}`
  }

  return rule.trigger_type
}

// ── Action description ──────────────────────────────────────

function actionLabel(action: string): string {
  return t(`automations.actionTypes.${action}`, { defaultValue: action })
}

export function describeAction(rule: { action_type: string; action_config: Record<string, unknown> }): string {
  const cfg = rule.action_config as AnyConfig
  const base = actionLabel(rule.action_type)

  if (rule.action_type === 'notify') {
    const channel = cfg.channel === 'webhook' ? 'Webhook' : 'Telegram'
    return `${base} ${t('automations.cron.via')} ${channel}`
  }
  if (rule.action_type === 'block_user' && cfg.reason) {
    return `${base} (${cfg.reason})`
  }
  if (rule.action_type === 'cleanup_expired' && cfg.older_than_days) {
    return `${base} > ${cfg.older_than_days} ${t('automations.constructor.daysShort')}`
  }
  if (rule.action_type === 'restart_node' && cfg.node_uuid) {
    return `${base} (${t('automations.constructor.specificNode').toLowerCase()})`
  }
  return base
}

export function actionDescription(action: string): string {
  return t(`automations.actionDescs.${action}`, { defaultValue: '' })
}

export function actionTypeLabel(action: string): string {
  return actionLabel(action)
}

// ── Trigger type ────────────────────────────────────────────

export function triggerTypeLabel(type: string): string {
  return t(`automations.triggerTypes.${type}`, { defaultValue: type })
}

// ── Result badge ────────────────────────────────────────────

export function resultBadgeClass(result: string): string {
  switch (result) {
    case 'success':
      return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
    case 'error':
      return 'bg-red-500/20 text-red-400 border-red-500/30'
    case 'skipped':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
    default:
      return 'bg-dark-700/50 text-dark-200 border-dark-600'
  }
}

export function resultLabel(result: string): string {
  return t(`automations.results.${result}`, { defaultValue: result })
}

// ── Date formatting ─────────────────────────────────────────

function getLocale(): string {
  return i18n.language === 'en' ? 'en-US' : 'ru-RU'
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString(getLocale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString(getLocale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Constants for forms ─────────────────────────────────────

export function getTriggerTypes() {
  return [
    { value: 'event', label: t('automations.triggerTypes.event'), description: t('automations.triggerTypes.eventDesc') },
    { value: 'schedule', label: t('automations.triggerTypes.schedule'), description: t('automations.triggerTypes.scheduleDesc') },
    { value: 'threshold', label: t('automations.triggerTypes.threshold'), description: t('automations.triggerTypes.thresholdDesc') },
  ] as const
}
export const TRIGGER_TYPES = new Proxy([] as unknown as ReturnType<typeof getTriggerTypes>, {
  get(_target, prop) { const d = getTriggerTypes(); if (prop === 'map') return d.map.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getEventTypes() {
  return [
    { value: 'violation.detected', label: t('automations.events.violation_detected'), description: t('automations.events.violation_detectedDesc') },
    { value: 'node.went_offline', label: t('automations.events.node_went_offline'), description: t('automations.events.node_went_offlineDesc') },
    { value: 'user.traffic_exceeded', label: t('automations.events.user_traffic_exceeded'), description: t('automations.events.user_traffic_exceededDesc') },
  ] as const
}
export const EVENT_TYPES = new Proxy([] as unknown as ReturnType<typeof getEventTypes>, {
  get(_target, prop) { const d = getEventTypes(); if (prop === 'map') return d.map.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getThresholdMetrics() {
  return [
    { value: 'users_online', label: t('automations.metrics.users_online'), description: t('automations.metrics.users_onlineDesc') },
    { value: 'traffic_today', label: t('automations.metrics.traffic_today'), description: t('automations.metrics.traffic_todayDesc') },
    { value: 'node_uptime_percent', label: t('automations.metrics.node_uptime_percent'), description: t('automations.metrics.node_uptime_percentDesc') },
    { value: 'user_traffic_percent', label: t('automations.metrics.user_traffic_percent'), description: t('automations.metrics.user_traffic_percentDesc') },
    { value: 'user_node_traffic_gb', label: t('automations.metrics.user_node_traffic_gb'), description: t('automations.metrics.user_node_traffic_gbDesc') },
  ] as const
}
export const THRESHOLD_METRICS = new Proxy([] as unknown as ReturnType<typeof getThresholdMetrics>, {
  get(_target, prop) { const d = getThresholdMetrics(); if (prop === 'map') return d.map.bind(d); if (prop === 'find') return d.find.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getConditionOperators() {
  return [
    { value: '==', label: t('automations.operators.eq') },
    { value: '!=', label: t('automations.operators.neq') },
    { value: '>', label: t('automations.operators.gt') },
    { value: '>=', label: t('automations.operators.gte') },
    { value: '<', label: t('automations.operators.lt') },
    { value: '<=', label: t('automations.operators.lte') },
    { value: 'contains', label: t('automations.operators.contains') },
    { value: 'not_contains', label: t('automations.operators.not_contains') },
  ] as const
}
export const CONDITION_OPERATORS = new Proxy([] as unknown as ReturnType<typeof getConditionOperators>, {
  get(_target, prop) { const d = getConditionOperators(); if (prop === 'map') return d.map.bind(d); if (prop === 'find') return d.find.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getConditionFields() {
  return [
    { value: 'score', label: t('automations.conditionFields.score') },
    { value: 'percent', label: t('automations.conditionFields.percent') },
    { value: 'traffic_gb', label: t('automations.conditionFields.traffic_gb') },
    { value: 'uptime', label: t('automations.conditionFields.uptime') },
    { value: 'online_count', label: t('automations.conditionFields.online_count') },
    { value: 'days_expired', label: t('automations.conditionFields.days_expired') },
  ] as const
}
export const CONDITION_FIELDS = new Proxy([] as unknown as ReturnType<typeof getConditionFields>, {
  get(_target, prop) { const d = getConditionFields(); if (prop === 'map') return d.map.bind(d); if (prop === 'find') return d.find.bind(d); if (prop === 'some') return d.some.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getActionTypes() {
  return [
    { value: 'disable_user', label: t('automations.actionTypes.disable_user'), category: 'users', description: t('automations.actionTypes.disable_userDesc') },
    { value: 'block_user', label: t('automations.actionTypes.block_user'), category: 'users', description: t('automations.actionTypes.block_userDesc') },
    { value: 'notify', label: t('automations.actionTypes.notify'), category: 'system', description: t('automations.actionTypes.notifyDesc') },
    { value: 'restart_node', label: t('automations.actionTypes.restart_node'), category: 'nodes', description: t('automations.actionTypes.restart_nodeDesc') },
    { value: 'cleanup_expired', label: t('automations.actionTypes.cleanup_expired'), category: 'system', description: t('automations.actionTypes.cleanup_expiredDesc') },
    { value: 'reset_traffic', label: t('automations.actionTypes.reset_traffic'), category: 'users', description: t('automations.actionTypes.reset_trafficDesc') },
    { value: 'force_sync', label: t('automations.actionTypes.force_sync'), category: 'system', description: t('automations.actionTypes.force_syncDesc') },
  ] as const
}
export const ACTION_TYPES = new Proxy([] as unknown as ReturnType<typeof getActionTypes>, {
  get(_target, prop) { const d = getActionTypes(); if (prop === 'map') return d.map.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})

export function getCategories() {
  return [
    { value: 'users', label: t('automations.categories.users') },
    { value: 'nodes', label: t('automations.categories.nodes') },
    { value: 'violations', label: t('automations.categories.violations') },
    { value: 'system', label: t('automations.categories.system') },
  ] as const
}
export const CATEGORIES = new Proxy([] as unknown as ReturnType<typeof getCategories>, {
  get(_target, prop) { const d = getCategories(); if (prop === 'map') return d.map.bind(d); if (prop === 'length') return d.length; if (typeof prop === 'string' && !isNaN(Number(prop))) return d[Number(prop)]; return (d as any)[prop] }, // eslint-disable-line @typescript-eslint/no-explicit-any
})
