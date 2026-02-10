import type { AutomationRule, AutomationTemplate } from '../../api/automations'

// ── Category ────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  users: 'Пользователи',
  nodes: 'Ноды',
  violations: 'Нарушения',
  system: 'Система',
}

const CATEGORY_COLORS: Record<string, string> = {
  users: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  nodes: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  violations: 'bg-red-500/20 text-red-400 border-red-500/30',
  system: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
}

export function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat
}

export function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] || 'bg-dark-700/50 text-dark-200 border-dark-600'
}

// ── Cron to human-readable ──────────────────────────────────

const DAY_NAMES = ['воскресенье', 'понедельник', 'вторник', 'среду', 'четверг', 'пятницу', 'субботу']
const DAY_NAMES_SHORT = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
const MONTH_NAMES = [
  '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

export function cronToHuman(expr: string): string {
  if (!expr || !expr.trim()) return ''

  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

  try {
    // Every N minutes: */N * * * *
    if (minute.startsWith('*/') && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      const n = parseInt(minute.slice(2))
      if (n === 1) return 'Каждую минуту'
      if (n === 5) return 'Каждые 5 минут'
      if (n === 10) return 'Каждые 10 минут'
      if (n === 15) return 'Каждые 15 минут'
      if (n === 30) return 'Каждые 30 минут'
      return `Каждые ${n} мин.`
    }

    // Every N hours: 0 */N * * *
    if (minute !== '*' && hour.startsWith('*/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      const n = parseInt(hour.slice(2))
      const m = parseInt(minute) || 0
      if (n === 1) return `Каждый час в ${pad2(m)} мин.`
      return `Каждые ${n} ч. в ${pad2(m)} мин.`
    }

    // Every minute: * * * * *
    if (minute === '*' && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return 'Каждую минуту'
    }

    // Specific minute every hour: N * * * *
    if (/^\d+$/.test(minute) && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return `Каждый час в :${pad2(parseInt(minute))}`
    }

    const isFixedMinute = /^\d+$/.test(minute)
    const isFixedHour = /^\d+$/.test(hour)
    const isAnyDay = dayOfMonth === '*'
    const isAnyMonth = month === '*'
    const isAnyDow = dayOfWeek === '*'

    // Daily: N N * * *
    if (isFixedMinute && isFixedHour && isAnyDay && isAnyMonth && isAnyDow) {
      return `Каждый день в ${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
    }

    // Weekly: N N * * D
    if (isFixedMinute && isFixedHour && isAnyDay && isAnyMonth && !isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      // Could be a list: 1,3,5
      if (dayOfWeek.includes(',')) {
        const days = dayOfWeek.split(',').map((d) => DAY_NAMES_SHORT[parseInt(d)] || d)
        return `${days.join(', ')} в ${time}`
      }
      // Range: 1-5
      if (dayOfWeek.includes('-')) {
        const [from, to] = dayOfWeek.split('-').map(Number)
        return `${DAY_NAMES_SHORT[from]}\u2013${DAY_NAMES_SHORT[to]} в ${time}`
      }
      const d = parseInt(dayOfWeek)
      return `Каждый ${DAY_NAMES[d] || dayOfWeek} в ${time}`
    }

    // Monthly: N N D * *
    if (isFixedMinute && isFixedHour && /^\d+$/.test(dayOfMonth) && isAnyMonth && isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      const d = parseInt(dayOfMonth)
      return `${d}-го числа каждого месяца в ${time}`
    }

    // Yearly: N N D M *
    if (isFixedMinute && isFixedHour && /^\d+$/.test(dayOfMonth) && /^\d+$/.test(month) && isAnyDow) {
      const time = `${pad2(parseInt(hour))}:${pad2(parseInt(minute))}`
      const d = parseInt(dayOfMonth)
      const m = parseInt(month)
      return `${d} ${MONTH_NAMES[m] || month} в ${time}`
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

export const CRON_PRESETS: CronPreset[] = [
  { id: 'every_5min', label: 'Каждые 5 минут', description: '*/5 * * * *', cron: '*/5 * * * *' },
  { id: 'every_15min', label: 'Каждые 15 минут', description: '*/15 * * * *', cron: '*/15 * * * *' },
  { id: 'every_30min', label: 'Каждые 30 минут', description: '*/30 * * * *', cron: '*/30 * * * *' },
  { id: 'every_hour', label: 'Каждый час', description: '0 * * * *', cron: '0 * * * *' },
  { id: 'every_3hours', label: 'Каждые 3 часа', description: '0 */3 * * *', cron: '0 */3 * * *' },
  { id: 'every_6hours', label: 'Каждые 6 часов', description: '0 */6 * * *', cron: '0 */6 * * *' },
  { id: 'every_12hours', label: 'Каждые 12 часов', description: '0 */12 * * *', cron: '0 */12 * * *' },
  { id: 'daily_midnight', label: 'Каждый день в 00:00', description: '0 0 * * *', cron: '0 0 * * *' },
  { id: 'daily_3am', label: 'Каждый день в 03:00', description: '0 3 * * *', cron: '0 3 * * *' },
  { id: 'daily_9am', label: 'Каждый день в 09:00', description: '0 9 * * *', cron: '0 9 * * *' },
  { id: 'daily_23pm', label: 'Каждый день в 23:00', description: '0 23 * * *', cron: '0 23 * * *' },
  { id: 'weekly_monday', label: 'Каждый понедельник в 09:00', description: '0 9 * * 1', cron: '0 9 * * 1' },
  { id: 'monthly_1st', label: '1-го числа каждого месяца', description: '0 0 1 * *', cron: '0 0 1 * *' },
]

export const INTERVAL_PRESETS = [
  { value: 5, label: '5 мин' },
  { value: 15, label: '15 мин' },
  { value: 30, label: '30 мин' },
  { value: 60, label: '1 час' },
  { value: 120, label: '2 часа' },
  { value: 360, label: '6 часов' },
  { value: 720, label: '12 часов' },
  { value: 1440, label: '24 часа' },
] as const

// ── Trigger description ─────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  'violation.detected': 'Обнаружено нарушение',
  'node.went_offline': 'Нода ушла офлайн',
  'user.traffic_exceeded': 'Трафик пользователя превышен',
}

const METRIC_LABELS: Record<string, string> = {
  users_online: 'Пользователей онлайн',
  traffic_today: 'Трафик за сегодня (ГБ)',
  node_uptime_percent: 'Аптайм ноды (%)',
  user_traffic_percent: 'Использование трафика (%)',
}

const OPERATOR_LABELS: Record<string, string> = {
  '==': 'равно',
  '!=': 'не равно',
  '>': 'больше',
  '>=': 'больше или равно',
  '<': 'меньше',
  '<=': 'меньше или равно',
  'contains': 'содержит',
  'not_contains': 'не содержит',
}

export function describeTrigger(rule: AutomationRule | AutomationTemplate): string {
  const cfg = rule.trigger_config as Record<string, any>

  if (rule.trigger_type === 'event') {
    const event = cfg.event || ''
    const label = EVENT_LABELS[event] || event
    const minScore = cfg.min_score
    const offlineMin = cfg.offline_minutes
    let desc = label
    if (minScore) desc += ` (score \u2265 ${minScore})`
    if (offlineMin) desc += ` (> ${offlineMin} мин)`
    return desc
  }

  if (rule.trigger_type === 'schedule') {
    if (cfg.cron) {
      const human = cronToHuman(cfg.cron)
      return human !== cfg.cron ? human : `Расписание: ${cfg.cron}`
    }
    if (cfg.interval_minutes) {
      const mins = cfg.interval_minutes
      if (mins < 60) return `Каждые ${mins} мин.`
      if (mins === 60) return 'Каждый час'
      if (mins % 60 === 0) {
        const h = mins / 60
        if (h === 24) return 'Каждые 24 часа'
        return `Каждые ${h} ч.`
      }
      return `Каждые ${mins} мин.`
    }
    return 'По расписанию'
  }

  if (rule.trigger_type === 'threshold') {
    const metric = METRIC_LABELS[cfg.metric] || cfg.metric || ''
    const op = cfg.operator || '>='
    const opLabel = OPERATOR_LABELS[op] || op
    return `${metric} ${opLabel} ${cfg.value ?? ''}`
  }

  return rule.trigger_type
}

// ── Action description ──────────────────────────────────────

const ACTION_LABELS: Record<string, string> = {
  disable_user: 'Отключить пользователя',
  block_user: 'Заблокировать пользователя',
  notify: 'Отправить уведомление',
  restart_node: 'Перезапустить ноду',
  cleanup_expired: 'Очистить истёкших',
  reset_traffic: 'Сбросить трафик',
  force_sync: 'Принудительная синхр.',
}

const ACTION_DESCRIPTIONS: Record<string, string> = {
  disable_user: 'Автоматически отключает учётную запись пользователя',
  block_user: 'Блокирует пользователя с указанной причиной',
  notify: 'Отправляет уведомление в Telegram или Webhook',
  restart_node: 'Отправляет команду перезапуска на ноду',
  cleanup_expired: 'Отключает пользователей с истёкшей подпиской',
  reset_traffic: 'Сбрасывает счётчики трафика пользователей',
  force_sync: 'Принудительно синхронизирует конфигурацию нод',
}

export function describeAction(rule: AutomationRule | AutomationTemplate): string {
  const cfg = rule.action_config as Record<string, any>
  const base = ACTION_LABELS[rule.action_type] || rule.action_type

  if (rule.action_type === 'notify') {
    const channel = cfg.channel === 'webhook' ? 'Webhook' : 'Telegram'
    return `${base} через ${channel}`
  }
  if (rule.action_type === 'block_user' && cfg.reason) {
    return `${base} (${cfg.reason})`
  }
  if (rule.action_type === 'cleanup_expired' && cfg.older_than_days) {
    return `${base} старше ${cfg.older_than_days} дн.`
  }
  return base
}

export function actionDescription(action: string): string {
  return ACTION_DESCRIPTIONS[action] || ''
}

export function actionTypeLabel(action: string): string {
  return ACTION_LABELS[action] || action
}

// ── Trigger type ────────────────────────────────────────────

const TRIGGER_TYPE_LABELS: Record<string, string> = {
  event: 'Событие',
  schedule: 'Расписание',
  threshold: 'Порог',
}

export function triggerTypeLabel(type: string): string {
  return TRIGGER_TYPE_LABELS[type] || type
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
  switch (result) {
    case 'success': return 'Успех'
    case 'error': return 'Ошибка'
    case 'skipped': return 'Пропущено'
    default: return result
  }
}

// ── Date formatting ─────────────────────────────────────────

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Constants for forms ─────────────────────────────────────

export const TRIGGER_TYPES = [
  { value: 'event', label: 'Событие', description: 'Реакция на конкретное событие в системе' },
  { value: 'schedule', label: 'Расписание', description: 'Запуск по времени или через интервал' },
  { value: 'threshold', label: 'Порог', description: 'Срабатывает при достижении порога метрики' },
] as const

export const EVENT_TYPES = [
  { value: 'violation.detected', label: 'Обнаружено нарушение', description: 'Система обнаружила нарушение у пользователя' },
  { value: 'node.went_offline', label: 'Нода ушла офлайн', description: 'Узел потерял связь и стал недоступен' },
  { value: 'user.traffic_exceeded', label: 'Трафик превышен', description: 'Пользователь исчерпал лимит трафика' },
] as const

export const THRESHOLD_METRICS = [
  { value: 'users_online', label: 'Пользователей онлайн', description: 'Текущее количество активных подключений' },
  { value: 'traffic_today', label: 'Трафик за сегодня (ГБ)', description: 'Суммарный трафик за текущие сутки' },
  { value: 'node_uptime_percent', label: 'Аптайм ноды (%)', description: 'Процент времени доступности узла' },
  { value: 'user_traffic_percent', label: 'Использование трафика (%)', description: 'Процент использования от лимита' },
] as const

export const CONDITION_OPERATORS = [
  { value: '==', label: 'равно (=)' },
  { value: '!=', label: 'не равно (\u2260)' },
  { value: '>', label: 'больше (>)' },
  { value: '>=', label: 'больше или равно (\u2265)' },
  { value: '<', label: 'меньше (<)' },
  { value: '<=', label: 'меньше или равно (\u2264)' },
] as const

export const CONDITION_FIELDS = [
  { value: 'score', label: 'Оценка (score)' },
  { value: 'percent', label: 'Процент (%)' },
  { value: 'traffic_gb', label: 'Трафик (ГБ)' },
  { value: 'uptime', label: 'Аптайм (%)' },
  { value: 'online_count', label: 'Кол-во онлайн' },
  { value: 'days_expired', label: 'Дней истекло' },
] as const

export const ACTION_TYPES = [
  { value: 'disable_user', label: 'Отключить пользователя', category: 'users', description: 'Деактивирует аккаунт пользователя' },
  { value: 'block_user', label: 'Заблокировать пользователя', category: 'users', description: 'Блокирует аккаунт с указанием причины' },
  { value: 'notify', label: 'Отправить уведомление', category: 'system', description: 'Telegram или Webhook-уведомление' },
  { value: 'restart_node', label: 'Перезапустить ноду', category: 'nodes', description: 'Отправляет команду перезапуска' },
  { value: 'cleanup_expired', label: 'Очистить истёкших', category: 'system', description: 'Удаляет просроченные подписки' },
  { value: 'reset_traffic', label: 'Сбросить трафик', category: 'users', description: 'Обнуляет счётчики трафика' },
  { value: 'force_sync', label: 'Синхронизация нод', category: 'system', description: 'Принудительно обновляет конфигурацию' },
] as const

export const CATEGORIES = [
  { value: 'users', label: 'Пользователи' },
  { value: 'nodes', label: 'Ноды' },
  { value: 'violations', label: 'Нарушения' },
  { value: 'system', label: 'Система' },
] as const
