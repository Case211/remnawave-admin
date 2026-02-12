import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'

/**
 * Returns locale-aware formatting functions for dates, numbers, bytes, and time intervals.
 */
export function useFormatters() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language === 'ru' ? 'ru-RU' : 'en-US'

  const formatDate = useCallback(
    (dateStr: string) => {
      return new Date(dateStr).toLocaleString(locale, {
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
    (dateStr: string) => {
      return new Date(dateStr).toLocaleDateString(locale)
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

  return {
    formatDate,
    formatDateShort,
    formatTimeAgo,
    formatNumber,
    formatBytes,
    formatSpeed,
    locale,
  }
}
