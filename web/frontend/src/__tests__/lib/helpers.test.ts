import { describe, it, expect } from 'vitest'
import {
  cronToHuman,
  categoryLabel,
  categoryColor,
  describeTrigger,
  describeAction,
  actionTypeLabel,
  actionDescription,
  triggerTypeLabel,
  resultBadgeClass,
  resultLabel,
  formatDate,
  formatDateTime,
} from '@/pages/automations/helpers'

// ── cronToHuman ──────────────────────────────────────────────

describe('cronToHuman', () => {
  it('returns empty string for empty input', () => {
    expect(cronToHuman('')).toBe('')
    expect(cronToHuman('  ')).toBe('')
  })

  it('returns raw expression for invalid cron (wrong number of parts)', () => {
    expect(cronToHuman('* * *')).toBe('* * *')
    expect(cronToHuman('1 2 3 4 5 6')).toBe('1 2 3 4 5 6')
  })

  it('parses every minute', () => {
    expect(cronToHuman('* * * * *')).toBe('Каждую минуту')
  })

  it('parses every N minutes', () => {
    expect(cronToHuman('*/1 * * * *')).toBe('Каждую минуту')
    expect(cronToHuman('*/5 * * * *')).toBe('Каждые 5 минут')
    expect(cronToHuman('*/10 * * * *')).toBe('Каждые 10 минут')
    expect(cronToHuman('*/15 * * * *')).toBe('Каждые 15 минут')
    expect(cronToHuman('*/30 * * * *')).toBe('Каждые 30 минут')
    expect(cronToHuman('*/7 * * * *')).toBe('Каждые 7 мин.')
  })

  it('parses every N hours', () => {
    expect(cronToHuman('0 */1 * * *')).toBe('Каждый час в 00 мин.')
    expect(cronToHuman('0 */3 * * *')).toBe('Каждые 3 ч. в 00 мин.')
    expect(cronToHuman('30 */6 * * *')).toBe('Каждые 6 ч. в 30 мин.')
  })

  it('parses specific minute every hour', () => {
    expect(cronToHuman('15 * * * *')).toBe('Каждый час в :15')
    expect(cronToHuman('0 * * * *')).toBe('Каждый час в :00')
    expect(cronToHuman('45 * * * *')).toBe('Каждый час в :45')
  })

  it('parses daily', () => {
    expect(cronToHuman('0 0 * * *')).toBe('Каждый день в 00:00')
    expect(cronToHuman('30 9 * * *')).toBe('Каждый день в 09:30')
    expect(cronToHuman('0 23 * * *')).toBe('Каждый день в 23:00')
  })

  it('parses weekly (single day)', () => {
    expect(cronToHuman('0 9 * * 1')).toBe('Каждый понедельник в 09:00')
    expect(cronToHuman('0 9 * * 0')).toBe('Каждый воскресенье в 09:00')
    expect(cronToHuman('30 18 * * 5')).toBe('Каждый пятницу в 18:30')
  })

  it('parses weekly (comma-separated days)', () => {
    expect(cronToHuman('0 9 * * 1,3,5')).toBe('Пн, Ср, Пт в 09:00')
  })

  it('parses weekly (day range)', () => {
    expect(cronToHuman('0 9 * * 1-5')).toBe('Пн\u2013Пт в 09:00')
  })

  it('parses monthly', () => {
    expect(cronToHuman('0 0 1 * *')).toBe('1-го числа каждого месяца в 00:00')
    expect(cronToHuman('30 12 15 * *')).toBe('15-го числа каждого месяца в 12:30')
  })

  it('parses yearly', () => {
    expect(cronToHuman('0 0 1 1 *')).toBe('1 января в 00:00')
    expect(cronToHuman('0 12 25 12 *')).toBe('25 декабря в 12:00')
  })
})

// ── Category helpers ─────────────────────────────────────────

describe('categoryLabel', () => {
  it('returns known category labels', () => {
    expect(categoryLabel('users')).toBe('Пользователи')
    expect(categoryLabel('nodes')).toBe('Ноды')
    expect(categoryLabel('violations')).toBe('Нарушения')
    expect(categoryLabel('system')).toBe('Система')
  })

  it('returns raw string for unknown category', () => {
    expect(categoryLabel('unknown')).toBe('unknown')
  })
})

describe('categoryColor', () => {
  it('returns color classes for known categories', () => {
    expect(categoryColor('users')).toContain('bg-blue-500')
    expect(categoryColor('nodes')).toContain('bg-emerald-500')
    expect(categoryColor('violations')).toContain('bg-red-500')
    expect(categoryColor('system')).toContain('bg-purple-500')
  })

  it('returns default classes for unknown category', () => {
    expect(categoryColor('foo')).toContain('bg-dark-700')
  })
})

// ── Trigger description ──────────────────────────────────────

describe('describeTrigger', () => {
  it('describes event trigger', () => {
    const result = describeTrigger({
      trigger_type: 'event',
      trigger_config: { event: 'violation.detected' },
    })
    expect(result).toBe('Обнаружено нарушение')
  })

  it('describes event trigger with min_score', () => {
    const result = describeTrigger({
      trigger_type: 'event',
      trigger_config: { event: 'violation.detected', min_score: 80 },
    })
    expect(result).toContain('score')
    expect(result).toContain('80')
  })

  it('describes event trigger with offline_minutes', () => {
    const result = describeTrigger({
      trigger_type: 'event',
      trigger_config: { event: 'node.went_offline', offline_minutes: 5 },
    })
    expect(result).toContain('5 мин')
  })

  it('describes schedule trigger with cron', () => {
    const result = describeTrigger({
      trigger_type: 'schedule',
      trigger_config: { cron: '*/5 * * * *' },
    })
    expect(result).toBe('Каждые 5 минут')
  })

  it('describes schedule trigger with interval_minutes', () => {
    const result = describeTrigger({
      trigger_type: 'schedule',
      trigger_config: { interval_minutes: 30 },
    })
    expect(result).toBe('Каждые 30 мин.')
  })

  it('describes schedule with hourly interval', () => {
    expect(describeTrigger({
      trigger_type: 'schedule',
      trigger_config: { interval_minutes: 60 },
    })).toBe('Каждый час')
  })

  it('describes schedule with multi-hour interval', () => {
    expect(describeTrigger({
      trigger_type: 'schedule',
      trigger_config: { interval_minutes: 360 },
    })).toBe('Каждые 6 ч.')
  })

  it('describes threshold trigger', () => {
    const result = describeTrigger({
      trigger_type: 'threshold',
      trigger_config: { metric: 'users_online', operator: '>=', value: 100 },
    })
    expect(result).toContain('Пользователей онлайн')
    expect(result).toContain('больше или равно')
    expect(result).toContain('100')
  })

  it('returns trigger_type for unknown types', () => {
    expect(describeTrigger({
      trigger_type: 'custom',
      trigger_config: {},
    })).toBe('custom')
  })
})

// ── Action description ───────────────────────────────────────

describe('describeAction', () => {
  it('describes basic action', () => {
    expect(describeAction({
      action_type: 'disable_user',
      action_config: {},
    })).toBe('Отключить пользователя')
  })

  it('describes notify action with channel', () => {
    expect(describeAction({
      action_type: 'notify',
      action_config: { channel: 'webhook' },
    })).toContain('Webhook')

    expect(describeAction({
      action_type: 'notify',
      action_config: { channel: 'telegram' },
    })).toContain('Telegram')
  })

  it('describes block_user with reason', () => {
    const result = describeAction({
      action_type: 'block_user',
      action_config: { reason: 'Sharing detected' },
    })
    expect(result).toContain('Sharing detected')
  })

  it('describes cleanup_expired with older_than_days', () => {
    const result = describeAction({
      action_type: 'cleanup_expired',
      action_config: { older_than_days: 30 },
    })
    expect(result).toContain('30 дн.')
  })

  it('describes restart_node with node_uuid', () => {
    const result = describeAction({
      action_type: 'restart_node',
      action_config: { node_uuid: 'abc-123' },
    })
    expect(result).toContain('конкретная')
  })

  it('returns action_type for unknown action', () => {
    expect(describeAction({
      action_type: 'custom_action',
      action_config: {},
    })).toBe('custom_action')
  })
})

describe('actionTypeLabel', () => {
  it('returns labels for known actions', () => {
    expect(actionTypeLabel('disable_user')).toBe('Отключить пользователя')
    expect(actionTypeLabel('notify')).toBe('Отправить уведомление')
  })

  it('returns raw string for unknown action', () => {
    expect(actionTypeLabel('unknown')).toBe('unknown')
  })
})

describe('actionDescription', () => {
  it('returns descriptions for known actions', () => {
    expect(actionDescription('disable_user')).toContain('отключает')
  })

  it('returns empty string for unknown action', () => {
    expect(actionDescription('unknown')).toBe('')
  })
})

// ── Trigger type label ───────────────────────────────────────

describe('triggerTypeLabel', () => {
  it('returns labels', () => {
    expect(triggerTypeLabel('event')).toBe('Событие')
    expect(triggerTypeLabel('schedule')).toBe('Расписание')
    expect(triggerTypeLabel('threshold')).toBe('Порог')
  })

  it('returns raw string for unknown type', () => {
    expect(triggerTypeLabel('custom')).toBe('custom')
  })
})

// ── Result badge ─────────────────────────────────────────────

describe('resultBadgeClass', () => {
  it('returns correct classes for known results', () => {
    expect(resultBadgeClass('success')).toContain('emerald')
    expect(resultBadgeClass('error')).toContain('red')
    expect(resultBadgeClass('skipped')).toContain('yellow')
  })

  it('returns default classes for unknown result', () => {
    expect(resultBadgeClass('unknown')).toContain('dark')
  })
})

describe('resultLabel', () => {
  it('returns labels for known results', () => {
    expect(resultLabel('success')).toBe('Успех')
    expect(resultLabel('error')).toBe('Ошибка')
    expect(resultLabel('skipped')).toBe('Пропущено')
  })

  it('returns raw string for unknown result', () => {
    expect(resultLabel('pending')).toBe('pending')
  })
})

// ── Date formatting ──────────────────────────────────────────

describe('formatDate', () => {
  it('returns dash for null', () => {
    expect(formatDate(null)).toBe('\u2014')
  })

  it('formats a valid date string', () => {
    const result = formatDate('2024-03-15T12:00:00Z')
    // Should contain day, month, year in some format
    expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
})

describe('formatDateTime', () => {
  it('returns dash for null', () => {
    expect(formatDateTime(null)).toBe('\u2014')
  })

  it('formats a valid datetime string', () => {
    const result = formatDateTime('2024-03-15T14:30:00Z')
    // Should contain date and time
    expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
})
