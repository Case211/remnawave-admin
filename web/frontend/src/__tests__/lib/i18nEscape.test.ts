import { describe, expect, it } from 'vitest'
import i18n from '@/i18n'

describe('i18n interpolation', () => {
  it('не экранирует значения повторно — React экранирует сам', async () => {
    await i18n.changeLanguage('ru')
    const text = i18n.t('automations.constructor.quiet.hint', { tz: 'Europe/Moscow' })
    expect(text).toContain('Europe/Moscow')
    expect(text).not.toContain('&#x2F;')
  })
})
