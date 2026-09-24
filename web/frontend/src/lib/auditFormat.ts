import type { TFunction } from 'i18next'
import { formatDateUtil } from '@/lib/useFormatters'

/** Форматирование записей журнала аудита — общее для страницы журнала и истории в карточках. */

// Обработчики пишут «user.create», API v3 — «users.create»: это один раздел
export function resourceKey(resource: string): string {
  return resource.endsWith('s') && resource !== 'settings' ? resource.slice(0, -1) : resource === 'setting' ? 'settings' : resource
}

export function resourceStyleKey(resource: string): string {
  const key = resourceKey(resource)
  return key === 'settings' ? key : `${key}s`
}

export function getResourceLabel(t: TFunction, resource: string): string {
  return t(`audit.resources.${resourceKey(resource)}`, { defaultValue: resource })
}

export function getActionLabelT(t: TFunction, action: string): string {
  return t(`audit.actions.${action}`, { defaultValue: action.replace(/_/g, ' ') })
}

export function getDetailLabel(t: TFunction, key: string): string {
  return t(`audit.details_map.${key}`, { defaultValue: key.replace(/_/g, ' ') })
}

export function parseAction(fullAction: string): { resource: string; action: string } {
  const dot = fullAction.indexOf('.')
  if (dot === -1) return { resource: '', action: fullAction }
  return { resource: fullAction.slice(0, dot), action: fullAction.slice(dot + 1) }
}

export function getActionColor(action: string): string {
  // Semantic: destructive actions stay red
  if (action.includes('delete') || action === 'disable' || action.includes('revoke'))
    return 'bg-red-500/20 text-red-400 border-red-500/30'
  // Semantic: create/enable stay green
  if (action === 'create' || action === 'enable')
    return 'bg-green-500/20 text-green-400 border-green-500/30'
  // Neutral actions use muted style
  if (action === 'logout')
    return 'bg-muted text-muted-foreground border-border'
  // Default: theme accent
  return 'bg-primary/20 text-primary-400 border-primary/30'
}

export function tryParseJSON(str: string | null): Record<string, unknown> | null {
  if (!str) return null
  try {
    const parsed = JSON.parse(str)
    return typeof parsed === 'object' && parsed !== null ? parsed : null
  } catch {
    return null
  }
}

function formatBytesRaw(bytes: unknown): string {
  const num = Number(bytes)
  if (isNaN(num) || num === 0) return '0'
  if (num >= 1125899906842624) return `${(num / 1125899906842624).toFixed(1)} PB`
  if (num >= 1099511627776) return `${(num / 1099511627776).toFixed(1)} TB`
  if (num >= 1073741824) return `${(num / 1073741824).toFixed(1)} GB`
  if (num >= 1048576) return `${(num / 1048576).toFixed(1)} MB`
  return `${(num / 1024).toFixed(0)} KB`
}

export type Change = { __from: unknown; __to: unknown }

export function isChange(value: unknown): value is Change {
  return typeof value === 'object' && value !== null && '__to' in value
}

export function formatDetailValue(t: TFunction, key: string, value: unknown): string {
  if (isChange(value)) {
    return `${formatDetailValue(t, key, value.__from)} \u2192 ${formatDetailValue(t, key, value.__to)}`
  }
  if (value === null || value === undefined) return '\u2014'
  if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no')
  if (key === 'data_limit' && typeof value === 'number') return formatBytesRaw(value)
  if (key === 'expire_date' && typeof value === 'string') {
    return formatDateUtil(value)
  }
  if (key === 'new_state') return value === 'enabled' ? t('common.enabled') : t('common.disabled')
  if (key === 'is_disabled') return value ? t('common.yes') : t('common.no')
  if (key === 'is_active') return value ? t('common.yes') : t('common.no')
  if (Array.isArray(value)) {
    return value.length > 5 ? `${value.slice(0, 5).join(', ')} \u2026 +${value.length - 5}` : value.join(', ')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function getDescription(
  t: TFunction,
  resource: string,
  action: string,
  resourceId: string | null,
  details: Record<string, unknown> | null,
): string {
  const target = (details?.username as string)
    || (details?.name as string)
    || (details?.remark as string)
    || (details?.setting as string)
    || resourceId
    || ''

  // Special case for automation toggle
  if (resource === 'automation' && action === 'toggle') {
    const name = (details?.name as string) || target
    return details?.new_state === 'enabled'
      ? t('audit.descriptions.automation.toggle_on', { target: name })
      : t('audit.descriptions.automation.toggle_off', { target: name })
  }

  const key = `audit.descriptions.${action}.${resourceKey(resource)}`
  const result = t(key, { target, defaultValue: '' })
  if (result) return target && !result.includes(target) ? `${result} ${target}` : result

  // Fallback: generate a generic description
  const actionLabel = getActionLabelT(t, action).toLowerCase()
  const resourceLabel = getResourceLabel(t, resource).toLowerCase()
  return `${actionLabel} ${resourceLabel}${target ? ` ${target}` : ''}`
}

/** Get top N detail entries, excluding keys already used in description */
export function getVisibleDetails(details: Record<string, unknown> | null): [string, unknown][] {
  if (!details) return []
  const skipKeys = new Set(['setting', 'changes', 'old'])
  const entries: [string, unknown][] = []
  // «Было → стало»: {changes: {поле: [старое, новое]}} и {value, old} у настроек
  const changes = details.changes
  if (changes && typeof changes === 'object' && !Array.isArray(changes)) {
    for (const [k, v] of Object.entries(changes as Record<string, unknown>)) {
      entries.push(Array.isArray(v) && v.length === 2 ? [k, { __from: v[0], __to: v[1] }] : [k, v])
    }
  }
  for (const [k, v] of Object.entries(details)) {
    if (skipKeys.has(k)) continue
    if (k === 'value' && 'old' in details) entries.push([k, { __from: details.old, __to: v }])
    else entries.push([k, v])
  }
  return entries
}
