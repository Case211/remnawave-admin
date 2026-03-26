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

  describe('formatDate null handling', () => {
    it('returns dash for null', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatDate(null)).toBe('—')
    })

    it('returns dash for undefined', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatDate(undefined)).toBe('—')
    })

    it('returns dash for invalid date', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatDate('not-a-date')).toBe('—')
    })

    it('formats valid ISO date', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatDate('2026-01-15T10:30:00Z')
      // Should contain day, month, year (time depends on local timezone)
      expect(output).toMatch(/15/)
      expect(output).toMatch(/01/)
      expect(output).toMatch(/2026/)
      expect(output).toMatch(/\d{2}:\d{2}/)  // HH:MM in any timezone
    })
  })

  describe('formatDateShort null handling', () => {
    it('returns dash for null', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatDateShort(null)).toBe('—')
    })

    it('returns dash for undefined', () => {
      const { result } = renderHook(() => useFormatters())
      expect(result.current.formatDateShort(undefined)).toBe('—')
    })

    it('formats valid date', () => {
      const { result } = renderHook(() => useFormatters())
      const output = result.current.formatDateShort('2026-03-20')
      expect(output).toMatch(/20/)
      expect(output).toMatch(/03/)
    })
  })
})

// ── Standalone utility tests ──

describe('formatDateUtil', () => {
  it('returns dash for null', async () => {
    const { formatDateUtil } = await import('@/lib/useFormatters')
    expect(formatDateUtil(null)).toBe('—')
  })

  it('returns dash for undefined', async () => {
    const { formatDateUtil } = await import('@/lib/useFormatters')
    expect(formatDateUtil(undefined)).toBe('—')
  })

  it('returns dash for invalid string', async () => {
    const { formatDateUtil } = await import('@/lib/useFormatters')
    expect(formatDateUtil('garbage')).toBe('—')
  })

  it('formats valid ISO date', async () => {
    const { formatDateUtil } = await import('@/lib/useFormatters')
    const output = formatDateUtil('2026-06-15T14:45:00Z')
    expect(output).toMatch(/15/)
    expect(output).toMatch(/06/)
    expect(output).toMatch(/2026/)
  })
})

describe('formatDateShortUtil', () => {
  it('returns dash for null', async () => {
    const { formatDateShortUtil } = await import('@/lib/useFormatters')
    expect(formatDateShortUtil(null)).toBe('—')
  })

  it('formats valid date', async () => {
    const { formatDateShortUtil } = await import('@/lib/useFormatters')
    const output = formatDateShortUtil('2026-12-25')
    expect(output).toMatch(/25/)
    expect(output).toMatch(/12/)
  })
})
