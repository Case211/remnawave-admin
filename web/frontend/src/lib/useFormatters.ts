import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'
import i18n from '../i18n'
import { getDisplayTimeZone, useDisplayTimeZone } from './timezone'

/**
 * Get current locale string based on i18n language.
 */
export function getLocale(): string {
  return (i18n.language || '').toLowerCase().startsWith('ru') ? 'ru-RU' : 'en-US'
}

/**
 * Дата из API как Date. Бэкенд может отдавать ISO без таймзоны (naive UTC) —
 * JS парсит такое как ЛОКАЛЬНОЕ время, и всё, что показано или посчитано от
 * такой строки, врёт на часовой пояс браузера. Явное смещение не трогаем.
 */
export function parseApiDate(dateStr: string): Date {
  const normalized =
    /T\d{2}:\d{2}/.test(dateStr) && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(dateStr)
      ? `${dateStr}Z`
      : dateStr
  return new Date(normalized)
}

/**
 * Standalone date formatter — for use outside React components (helpers, utils).
 * For React components, prefer the `useFormatters` hook.
 */
export function formatDateUtil(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = parseApiDate(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString(getLocale(), {
    timeZone: getDisplayTimeZone(),
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Standalone short date formatter — for use outside React components.
 */
export function formatDateShortUtil(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = parseApiDate(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(getLocale(), { timeZone: getDisplayTimeZone() })
}

/**
 * Returns locale-aware formatting functions for dates, numbers, bytes, and time intervals.
 */
export function useFormatters() {
  const { t, i18n } = useTranslation()
  const locale = (i18n.language || '').toLowerCase().startsWith('ru') ? 'ru-RU' : 'en-US'
  // Время показываем в зоне панели, а не браузера; смена зоны перерисует компонент
  const timeZone = useDisplayTimeZone()

  const formatDate = useCallback(
    (dateStr: string | null | undefined) => {
      if (!dateStr) return '—'
      const d = parseApiDate(dateStr)
      if (isNaN(d.getTime())) return '—'
      return d.toLocaleString(locale, {
        timeZone,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    },
    [locale, timeZone],
  )

  const formatDateShort = useCallback(
    (dateStr: string | null | undefined) => {
      if (!dateStr) return '—'
      const d = parseApiDate(dateStr)
      if (isNaN(d.getTime())) return '—'
      return d.toLocaleDateString(locale, { timeZone })
    },
    [locale, timeZone],
  )

  const formatTimeAgo = useCallback(
    (dateStr: string): string => {
      const date = parseApiDate(dateStr)
      const now = new Date()
      // лёгкий рассинхрон часов сервера/клиента не должен давать «из будущего»
      const diffMs = Math.max(0, now.getTime() - date.getTime())
      const diffSec = Math.floor(diffMs / 1000)
      const diffMin = Math.floor(diffSec / 60)
      const diffHour = Math.floor(diffMin / 60)
      const diffDay = Math.floor(diffHour / 24)

      if (diffSec < 60) return t('common.justNow')
      if (diffMin < 60) return t('common.minutesAgo', { count: diffMin })
      if (diffHour < 24) return t('common.hoursAgo', { count: diffHour })
      if (diffDay < 30) return t('common.daysAgo', { count: diffDay })
      return formatDateShort(dateStr)
    },
    [t, formatDateShort],
  )

  const formatNumber = useCallback(
    (num: number) => {
      return new Intl.NumberFormat(locale).format(num)
    },
    [locale],
  )

  const formatBytes = useCallback(
    (bytes: number): string => {
      if (bytes === 0) return `0 ${t('common.bytes.b')}`
      const k = 1024
      const sizes = [
        t('common.bytes.b'),
        t('common.bytes.kb'),
        t('common.bytes.mb'),
        t('common.bytes.gb'),
        t('common.bytes.tb'),
        t('common.bytes.pb'),
      ]
      const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
      const value = bytes / Math.pow(k, i)
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value)} ${sizes[i]}`
    },
    [locale, t],
  )

  const formatSpeed = useCallback(
    (bytesPerSec: number): string => {
      if (bytesPerSec === 0) return `0 ${t('common.speed.bps')}`
      const k = 1024
      const sizes = [
        t('common.speed.bps'),
        t('common.speed.kbps'),
        t('common.speed.mbps'),
        t('common.speed.gbps'),
      ]
      const i = Math.min(Math.floor(Math.log(bytesPerSec) / Math.log(k)), sizes.length - 1)
      const value = bytesPerSec / Math.pow(k, i)
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} ${sizes[i]}`
    },
    [locale, t],
  )

  const formatCurrency = useCallback(
    (amount: number, currency = 'USD'): string => {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(amount)
    },
    [locale],
  )

  return {
    formatDate,
    formatDateShort,
    formatTimeAgo,
    formatNumber,
    formatBytes,
    formatSpeed,
    formatCurrency,
    locale,
    timeZone,
  }
}
