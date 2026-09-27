import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'
import i18n from '@/i18n'
import {
  formatDetailValue, getActionLabelT, getDescription, getResourceLabel, getVisibleDetails, parseAction,
  resourceKey, translateAuditAction,
} from '@/lib/auditFormat'

// i18next-заглушка: возвращает defaultValue, а для известного ключа — перевод
const dict: Record<string, string> = {
  'audit.descriptions.update.user': 'Изменён пользователь',
  'audit.descriptions.enable.user': 'Включён пользователь',
  'audit.feed.users.sync_hwid': 'Синхронизация HWID',
  'audit.actions.create': 'Создание',
  'audit.resources.finance': 'Финансы',
}
const t = ((key: string, opts?: { defaultValue?: string }) => dict[key] ?? opts?.defaultValue ?? key) as unknown as TFunction

describe('auditFormat', () => {
  it('разворачивает changes в «было → стало»', () => {
    const entries = getVisibleDetails({ changes: { status: ['ACTIVE', 'DISABLED'] }, name: 'n1' })
    expect(entries[0][0]).toBe('status')
    expect(formatDetailValue(t, 'status', entries[0][1])).toBe('ACTIVE → DISABLED')
    expect(entries.find(([k]) => k === 'changes')).toBeUndefined()
  })

  it('старое значение настройки показывается рядом с новым', () => {
    const entries = getVisibleDetails({ key: 'k', value: '5', old: '3' })
    const value = entries.find(([k]) => k === 'value')
    expect(formatDetailValue(t, 'value', value?.[1])).toBe('3 → 5')
    expect(entries.find(([k]) => k === 'old')).toBeUndefined()
  })

  it('длинный список обрезается', () => {
    expect(formatDetailValue(t, 'uuids', ['a', 'b', 'c', 'd', 'e', 'f', 'g'])).toBe('a, b, c, d, e … +2')
  })

  it('описание берётся по ключу действия и раздела, цель дописывается', () => {
    expect(getDescription(t, 'users', 'update', 'uuid-1', { username: 'vasya' })).toBe('Изменён пользователь vasya')
  })

  it('user и users — один раздел', () => {
    expect(resourceKey('users')).toBe('user')
    expect(resourceKey('setting')).toBe('settings')
    expect(resourceKey('settings')).toBe('settings')
  })

  it('«s» на конце — не всегда множественное число', () => {
    expect(resourceKey('dns')).toBe('dns')
    expect(resourceKey('analytics')).toBe('analytics')
    expect(resourceKey('blocked_ips')).toBe('blocked_ip')
  })
})

describe('translateAuditAction', () => {
  it('готовая строка ленты — первой', () => {
    expect(translateAuditAction(t, 'users.sync_hwid')).toBe('Синхронизация HWID')
  })

  it('раздел во множественном числе находит описание в единственном', () => {
    expect(translateAuditAction(t, 'users.enable')).toBe('Включён пользователь')
  })

  it('без описания собирается из действия и раздела', () => {
    expect(translateAuditAction(t, 'finance.create')).toBe('Создание: Финансы')
  })

  it('без перевода — глагол без подчёркиваний, а не ключ с разделом', () => {
    expect(translateAuditAction(t, 'violations.notify_violation_user')).toBe('notify violation user')
  })
})

// Наличие ключей стережёт test_every_audit_action_is_translated на бэкенде;
// здесь — что по ним находит сама цепочка поиска фронта
describe('журнал на настоящих локалях', () => {
  const ru = i18n.getFixedT('ru')
  const en = i18n.getFixedT('en')

  it('тост и лента — описание действия', () => {
    expect(translateAuditAction(ru, 'finance.create_payment')).toBe('Добавлен платёж')
    expect(translateAuditAction(ru, 'violations.notify_violation_user')).toBe('Предупреждение клиенту не отправлено')
    expect(translateAuditAction(ru, 'support_events.create_support_event')).toBe('Получено событие внешней поддержки')
    expect(translateAuditAction(en, 'dns.record.delete')).toBe('DNS record deleted')
  })

  it('строка журнала: раздел, действие, описание с целью', () => {
    const { resource, action } = parseAction('dns.record.delete')
    expect(getResourceLabel(ru, resource)).toBe('DNS')
    expect(getActionLabelT(ru, action)).toBe('Удаление записи')
    expect(getDescription(ru, resource, action, 'r1', null)).toBe('Удалена DNS-запись r1')
  })
})
