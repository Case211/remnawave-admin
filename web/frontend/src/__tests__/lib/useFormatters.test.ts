import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useFormatters } from '@/lib/useFormatters'

// i18n is already initialized in setup.ts (language=ru)
// The hook uses useTranslation from react-i18next

describe('useFormatters', () => {
  describe('formatBytes', () => {
    it('formats 0 bytes', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(0)
      // Should contain "0" and a unit
      expect(output).toMatch(/^0\s/)
    })

    it('formats bytes (< 1 KB)', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(500)
      expect(output).toContain('500')
    })

    it('formats kilobytes', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(1024)
      expect(output).toContain('1')
    })

    it('formats megabytes', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(1024 * 1024 * 5.5)
      expect(output).toContain('5')
    })

    it('formats gigabytes', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(1024 * 1024 * 1024 * 2)
      expect(output).toContain('2')
    })

    it('formats terabytes', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatBytes(1024 * 1024 * 1024 * 1024 * 1.5)
      expect(output).toContain('1')
    })
  })

  describe('formatSpeed', () => {
    it('formats 0 speed', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatSpeed(0)
      expect(output).toMatch(/^0\s/)
    })

    it('formats bytes per second', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatSpeed(500)
      expect(output).toContain('500')
    })

    it('formats kilobytes per second', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatSpeed(1024 * 50)
      expect(output).toContain('50')
    })

    it('formats megabytes per second', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatSpeed(1024 * 1024 * 10)
      expect(output).toContain('10')
    })
  })

  describe('formatNumber', () => {
    it('formats a simple number', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatNumber(1000)
      // Locale-formatted — for ru-RU it uses non-breaking space as thousands separator
      expect(output).toBeTruthy()
    })

    it('formats zero', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatNumber(0)).toBe('0')
    })

    it('formats negative number', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatNumber(-1234)
      expect(output).toContain('1')
    })
  })

  describe('formatDate', () => {
    it('formats ISO date string', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatDate('2026-01-15T10:30:00Z')
      // Should contain day and year parts
      expect(output).toContain('15')
      expect(output).toContain('2026')
    })
  })

  describe('formatDateShort', () => {
    it('formats ISO date to short format', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatDateShort('2026-06-20T00:00:00Z')
      expect(output).toContain('20')
    })
  })

  describe('formatTimeAgo', () => {
    it('returns "just now" for very recent dates', () => {
      const { result } = renderHook(() => useFormatters())
      const now = new Date().toISOString()
      const output = result.current.formatTimeAgo(now)
      // Should return the i18n key result for "just now"
      expect(output).toBeTruthy()
    })

    it('returns minutes ago', () => {
      const { result } = renderHook(() => useFormatters())
      const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString()
      const output = result.current.formatTimeAgo(tenMinAgo)
      expect(output).toBeTruthy()
    })

    it('returns hours ago', () => {
      const { result } = renderHook(() => useFormatters())
      const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
      const output = result.current.formatTimeAgo(twoHoursAgo)
      expect(output).toBeTruthy()
    })

    it('falls back to short date for old dates', () => {
      const { result } = renderHook(() => useFormatters())
      const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()
      const output = result.current.formatTimeAgo(thirtyDaysAgo)
      expect(output).toBeTruthy()
    })
  })

  describe('locale', () => {
    it('returns a locale string', () => {
      const { result } = renderHook(() => useFormatters())
      expect(['ru-RU', 'en-US']).toContain(result.current.locale)
    })
  })
})
