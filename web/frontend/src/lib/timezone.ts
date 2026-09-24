import { useSyncExternalStore } from 'react'

/**
 * Часовой пояс, в котором админка показывает время.
 *
 * В базе и в API время ходит в UTC, а человеку показывается в одной зоне из
 * настройки панели display_timezone — не в зоне браузера: у админов в разных
 * городах одно и то же событие иначе выглядело бы по-разному, а в Telegram
 * пришло бы третье время. Зону подтягивает useTimeZoneSync() в Layout, до
 * ответа сервера действует зона по умолчанию.
 */
export const DEFAULT_TIME_ZONE = 'Europe/Moscow'

let current = DEFAULT_TIME_ZONE
const listeners = new Set<() => void>()

export function isValidTimeZone(tz: string): boolean {
  if (!tz) return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

export function getDisplayTimeZone(): string {
  return current
}

/** Поменять зону. Неизвестная зона — UTC, как и на сервере. */
export function setDisplayTimeZone(tz: string | null | undefined): void {
  const next = tz && isValidTimeZone(tz) ? tz : 'UTC'
  if (next === current) return
  current = next
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Текущая зона с перерисовкой компонента при её смене. */
export function useDisplayTimeZone(): string {
  return useSyncExternalStore(subscribe, getDisplayTimeZone, getDisplayTimeZone)
}

type Parts = { year: number; month: number; day: number; hour: number; minute: number; second: number }

function partsIn(date: Date, tz: string): Parts {
  const raw = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(date)
  const get = (type: string) => Number(raw.find((p) => p.type === type)?.value ?? 0)
  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: get('hour'),
    minute: get('minute'),
    second: get('second'),
  }
}

/** Смещение зоны от UTC в минутах в данный момент. */
export function zoneOffsetMinutes(date: Date, tz: string = current): number {
  const p = partsIn(date, tz)
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
  return Math.round((asUtc - Math.floor(date.getTime() / 1000) * 1000) / 60000)
}

/** Подпись зоны: «МСК», «UTC» или «UTC+5». */
export function timeZoneLabel(tz: string = current, date: Date = new Date()): string {
  if (tz === 'Europe/Moscow') return 'МСК'
  const offset = zoneOffsetMinutes(date, tz)
  if (!offset) return 'UTC'
  const sign = offset > 0 ? '+' : '-'
  const hours = Math.floor(Math.abs(offset) / 60)
  const minutes = Math.abs(offset) % 60
  return `UTC${sign}${hours}${minutes ? `:${String(minutes).padStart(2, '0')}` : ''}`
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Момент → «YYYY-MM-DDTHH:mm» в зоне — значение для <input type="datetime-local">. */
export function toZonedInputValue(value: Date | string | null | undefined, tz: string = current): string {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  if (isNaN(date.getTime())) return ''
  const p = partsIn(date, tz)
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

/** Момент → «YYYY-MM-DD» в зоне. */
export function toZonedDate(value: Date | string, tz: string = current): string {
  return toZonedInputValue(value, tz).slice(0, 10)
}

/**
 * «YYYY-MM-DDTHH:mm» или «YYYY-MM-DD» — время на часах зоны → момент (Date).
 * Смещение берём на сам этот момент, поэтому переходы на летнее время
 * в зонах, где они есть, не сдвигают результат.
 */
export function fromZonedInputValue(value: string, tz: string = current): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value.trim())
  if (!m) return null
  const [, y, mo, d, h = '0', mi = '0', s = '0'] = m
  const wall = Date.UTC(+y, +mo - 1, +d, +h, +mi, +s)
  let guess = wall - zoneOffsetMinutes(new Date(wall), tz) * 60000
  // Второй проход: смещение на найденный момент могло отличаться от первого
  guess = wall - zoneOffsetMinutes(new Date(guess), tz) * 60000
  return new Date(guess)
}

/** Момент → «YYYY-MM-DD HH:mm:ss» в зоне — для выгрузок (CSV и т. п.). */
export function zonedTimestamp(value: Date | string, tz: string = current): string {
  const date = value instanceof Date ? value : new Date(value)
  if (isNaN(date.getTime())) return ''
  const p = partsIn(date, tz)
  return `${p.year}-${pad(p.month)}-${pad(p.day)} ${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`
}
