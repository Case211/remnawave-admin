import { afterEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_TIME_ZONE,
  fromZonedInputValue,
  getDisplayTimeZone,
  setDisplayTimeZone,
  timeZoneLabel,
  toZonedDate,
  toZonedInputValue,
  zonedTimestamp,
} from '@/lib/timezone'
import { formatDateUtil } from '@/lib/useFormatters'

// 21:30 UTC 23 сентября = 00:30 МСК 24 сентября
const MOMENT = new Date('2026-09-23T21:30:00Z')

afterEach(() => setDisplayTimeZone(DEFAULT_TIME_ZONE))

describe('зона отображения', () => {
  it('по умолчанию Москва', () => {
    expect(getDisplayTimeZone()).toBe('Europe/Moscow')
  })

  it('неизвестная зона — UTC, как на сервере', () => {
    setDisplayTimeZone('Mars/Olympus')
    expect(getDisplayTimeZone()).toBe('UTC')
  })

  it('подписи', () => {
    expect(timeZoneLabel('Europe/Moscow')).toBe('МСК')
    expect(timeZoneLabel('UTC')).toBe('UTC')
    expect(timeZoneLabel('Asia/Yekaterinburg', MOMENT)).toBe('UTC+5')
    expect(timeZoneLabel('Asia/Kolkata', MOMENT)).toBe('UTC+5:30')
    expect(timeZoneLabel('America/New_York', MOMENT)).toBe('UTC-4')
  })
})

describe('поля даты и времени', () => {
  it('момент показывается на часах зоны, а не браузера', () => {
    expect(toZonedInputValue(MOMENT)).toBe('2026-09-24T00:30')
    expect(toZonedDate(MOMENT)).toBe('2026-09-24')
  })

  it('введённое время читается на часах зоны', () => {
    expect(fromZonedInputValue('2026-09-24T00:30')?.toISOString()).toBe('2026-09-23T21:30:00.000Z')
  })

  it('туда и обратно без потерь', () => {
    for (const tz of ['Europe/Moscow', 'Asia/Kolkata', 'America/New_York', 'UTC']) {
      expect(fromZonedInputValue(toZonedInputValue(MOMENT, tz), tz)?.toISOString()).toBe(MOMENT.toISOString())
    }
  })

  it('зона с летним временем: смещение берётся на сам момент', () => {
    // Берлин: зимой UTC+1, летом UTC+2
    expect(fromZonedInputValue('2026-01-15T12:00', 'Europe/Berlin')?.toISOString()).toBe('2026-01-15T11:00:00.000Z')
    expect(fromZonedInputValue('2026-07-15T12:00', 'Europe/Berlin')?.toISOString()).toBe('2026-07-15T10:00:00.000Z')
  })

  it('мусор не превращается в дату', () => {
    expect(fromZonedInputValue('завтра')).toBeNull()
    expect(toZonedInputValue('не дата')).toBe('')
  })

  it('выгрузка', () => {
    expect(zonedTimestamp(MOMENT)).toBe('2026-09-24 00:30:00')
  })
})

describe('форматтер', () => {
  it('время без пояса от API — это UTC, показывается в зоне панели', () => {
    expect(formatDateUtil('2026-09-23T21:30:00')).toBe(formatDateUtil('2026-09-23T21:30:00Z'))
    expect(formatDateUtil('2026-09-23T21:30:00Z')).toContain('00:30')
  })

  it('смена зоны меняет показ', () => {
    setDisplayTimeZone('UTC')
    expect(formatDateUtil('2026-09-23T21:30:00Z')).toContain('21:30')
  })
})
