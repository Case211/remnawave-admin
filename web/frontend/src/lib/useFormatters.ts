import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'
import i18n from '../i18n'

/**
 * Get current locale string based on i18n language.
 */
export function getLocale(): string {
  return (i18n.language || '').toLowerCase().startsWith('ru') ? 'ru-RU' : 'en-US'
}

/**
 * Standalone date formatter — for use outside React components (helpers, utils).
 * For React components, prefer the `useFormatters` hook.
 */
export function formatDateUtil(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString(getLocale(), {
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
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(getLocale())
}

/**
 * Returns locale-aware formatting functions for dates, numbers, bytes, and time intervals.
 */
export function useFormatters() {
  const { t, i18n } = useTranslation()
  const locale = (i18n.language || '').toLowerCase().startsWith('ru') ? 'ru-RU' : 'en-US'

  const formatDate = useCallback(
    (dateStr: string | null | undefined) => {
      if (!dateStr) return '—'
      const d = new Date(dateStr)
      if (isNaN(d.getTime())) return '—'
      return d.toLocaleString(locale, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    },
    [locale],
  )

  const formatDateShort = useCallback(
    (dateStr: string | null | undefined) => {
      if (!dateStr) return '—'
      const d = new Date(dateStr)
      if (isNaN(d.getTime())) return '—'
      return d.toLocaleDateString(locale)
    },
    [locale],
  )

  const formatTimeAgo = useCallback(
    (dateStr: string): string => {
      const date = new Date(dateStr)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffSec = Math.floor(diffMs / 1000)
      const diffMin = Math.floor(diffSec / 60)
      const diffHour = Math.floor(diffMin / 60)
      const diffDay = Math.floor(diffHour / 24)

      if (diffSec < 60) return t('common.justNow')
      if (diffMin < 60) return t('common.minutesAgo', { count: diffMin })
      if (diffHour < 24) return t('common.hoursAgo', { count: diffHour })
      if (diffDay < 7) return t('common.daysAgo', { count: diffDay })
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
      ]
      const i = Math.floor(Math.log(bytes) / Math.log(k))
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
      const i = Math.floor(Math.log(bytesPerSec) / Math.log(k))
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
  }
}
