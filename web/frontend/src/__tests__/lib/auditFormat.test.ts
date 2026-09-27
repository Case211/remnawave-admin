import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'
import { formatDetailValue, getDescription, getVisibleDetails, resourceKey, translateAuditAction } from '@/lib/auditFormat'

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
