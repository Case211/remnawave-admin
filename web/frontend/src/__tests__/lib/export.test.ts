import { describe, it, expect, vi, beforeEach } from 'vitest'
import { formatBytesForExport, exportCSV, exportJSON } from '@/lib/export'

describe('formatBytesForExport', () => {
  it('returns "0" for null', () => {
    expect(formatBytesForExport(null)).toBe('0')
  })

  it('returns "0" for undefined', () => {
    expect(formatBytesForExport(undefined)).toBe('0')
  })

  it('returns "0" for 0', () => {
    expect(formatBytesForExport(0)).toBe('0')
  })

  it('formats kilobytes', () => {
    expect(formatBytesForExport(512 * 1024)).toBe('512.00 KB')
  })

  it('formats megabytes', () => {
    expect(formatBytesForExport(50 * 1024 * 1024)).toBe('50.00 MB')
  })

  it('formats gigabytes', () => {
    expect(formatBytesForExport(2.5 * 1024 * 1024 * 1024)).toBe('2.50 GB')
  })

  it('formats small bytes as KB', () => {
    expect(formatBytesForExport(100)).toBe('0.10 KB')
  })

  it('handles exactly 1 GB', () => {
    expect(formatBytesForExport(1024 * 1024 * 1024)).toBe('1.00 GB')
  })

  it('handles exactly 1 MB', () => {
    expect(formatBytesForExport(1024 * 1024)).toBe('1.00 MB')
  })
})

describe('exportCSV', () => {
  let appendChildSpy: ReturnType<typeof vi.spyOn>
  let removeChildSpy: ReturnType<typeof vi.spyOn>
  let clickSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    clickSpy = vi.fn()
    appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node)
    removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node)
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickSpy,
    } as unknown as HTMLAnchorElement)
  })

  it('creates and clicks a download link', () => {
    exportCSV([{ name: 'test', value: 1 }], 'export')
    expect(clickSpy).toHaveBeenCalled()
    expect(appendChildSpy).toHaveBeenCalled()
    expect(removeChildSpy).toHaveBeenCalled()
  })
})

describe('exportJSON', () => {
  let clickSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    clickSpy = vi.fn()
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node)
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node)
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickSpy,
    } as unknown as HTMLAnchorElement)
  })

  it('creates and clicks a download link', () => {
    exportJSON({ key: 'value' }, 'data')
    expect(clickSpy).toHaveBeenCalled()
  })
})
