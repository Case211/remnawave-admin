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

export function describeTrigger(rule: AutomationRule | AutomationTemplate): string {
  const cfg = rule.trigger_config as Record<string, any>

  if (rule.trigger_type === 'event') {
    const event = cfg.event || ''
    const label = EVENT_LABELS[event] || event
    const minScore = cfg.min_score
    const offlineMin = cfg.offline_minutes
    let desc = label
    if (minScore) desc += ` (score >= ${minScore})`
    if (offlineMin) desc += ` (> ${offlineMin} мин)`
    return desc
  }

  if (rule.trigger_type === 'schedule') {
    if (cfg.cron) return `CRON: ${cfg.cron}`
    if (cfg.interval_minutes) return `Каждые ${cfg.interval_minutes} мин`
    return 'По расписанию'
  }

  if (rule.trigger_type === 'threshold') {
    const metric = METRIC_LABELS[cfg.metric] || cfg.metric || ''
    return `${metric} ${cfg.operator || '>='} ${cfg.value ?? ''}`
  }

  return rule.trigger_type
}

// ── Action description ──────────────────────────────────────

const ACTION_LABELS: Record<string, string> = {
  disable_user: 'Отключить пользователя',
  block_user: 'Заблокировать пользователя',
  notify: 'Уведомить',
  restart_node: 'Перезапустить ноду',
  cleanup_expired: 'Очистить истёкших',
  reset_traffic: 'Сбросить трафик',
  force_sync: 'Принудительная синхр.',
}

export function describeAction(rule: AutomationRule | AutomationTemplate): string {
  const cfg = rule.action_config as Record<string, any>
  const base = ACTION_LABELS[rule.action_type] || rule.action_type

  if (rule.action_type === 'notify') {
    const channel = cfg.channel === 'webhook' ? 'Webhook' : 'Telegram'
    return `${base} (${channel})`
  }
  if (rule.action_type === 'block_user' && cfg.reason) {
    return `${base}: ${cfg.reason}`
  }
  if (rule.action_type === 'cleanup_expired' && cfg.older_than_days) {
    return `${base} > ${cfg.older_than_days} дн.`
  }
  return base
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
  { value: 'event', label: 'Событие', description: 'Срабатывает при определённом событии' },
  { value: 'schedule', label: 'Расписание', description: 'CRON или интервал' },
  { value: 'threshold', label: 'Порог', description: 'При превышении метрики' },
] as const

export const EVENT_TYPES = [
  { value: 'violation.detected', label: 'Обнаружено нарушение' },
  { value: 'node.went_offline', label: 'Нода ушла офлайн' },
  { value: 'user.traffic_exceeded', label: 'Трафик превышен' },
] as const

export const THRESHOLD_METRICS = [
  { value: 'users_online', label: 'Пользователей онлайн' },
  { value: 'traffic_today', label: 'Трафик за сегодня (ГБ)' },
  { value: 'node_uptime_percent', label: 'Аптайм ноды (%)' },
  { value: 'user_traffic_percent', label: 'Использование трафика (%)' },
] as const

export const CONDITION_OPERATORS = [
  { value: '==', label: '=' },
  { value: '!=', label: '!=' },
  { value: '>', label: '>' },
  { value: '>=', label: '>=' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
] as const

export const ACTION_TYPES = [
  { value: 'disable_user', label: 'Отключить пользователя', category: 'users' },
  { value: 'block_user', label: 'Заблокировать пользователя', category: 'users' },
  { value: 'notify', label: 'Уведомить (Telegram/Webhook)', category: 'system' },
  { value: 'restart_node', label: 'Перезапустить ноду', category: 'nodes' },
  { value: 'cleanup_expired', label: 'Очистить истёкших', category: 'system' },
  { value: 'reset_traffic', label: 'Сбросить трафик', category: 'users' },
  { value: 'force_sync', label: 'Принудительная синхронизация', category: 'system' },
] as const

export const CATEGORIES = [
  { value: 'users', label: 'Пользователи' },
  { value: 'nodes', label: 'Ноды' },
  { value: 'violations', label: 'Нарушения' },
  { value: 'system', label: 'Система' },
] as const
