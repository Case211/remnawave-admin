import '@testing-library/jest-dom'
import { vi } from 'vitest'

// ── Mock window.__ENV ────────────────────────────────────────
declare global {
  interface Window {
    __ENV?: { API_URL?: string }
  }
}

window.__ENV = { API_URL: '' }

// ── Mock import.meta.env ─────────────────────────────────────
// Vitest handles import.meta.env natively, no extra setup needed.

// ── Mock matchMedia ──────────────────────────────────────────
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// ── Mock ResizeObserver ──────────────────────────────────────
class ResizeObserverMock {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver

// ── Mock IntersectionObserver ────────────────────────────────
class IntersectionObserverMock {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
window.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver

// ── Mock Element.prototype.scrollIntoView ─────────────────────
Element.prototype.scrollIntoView = vi.fn()

// ── Mock HTMLElement.prototype.hasPointerCapture ──────────────
HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
HTMLElement.prototype.setPointerCapture = vi.fn()
HTMLElement.prototype.releasePointerCapture = vi.fn()

// ── Mock URL.createObjectURL / revokeObjectURL ───────────────
URL.createObjectURL = vi.fn(() => 'blob:mock-url')
URL.revokeObjectURL = vi.fn()

// ── Mock crypto.randomUUID ───────────────────────────────────
if (!globalThis.crypto?.randomUUID) {
  Object.defineProperty(globalThis, 'crypto', {
    value: {
      ...globalThis.crypto,
      randomUUID: () =>
        'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0
          const v = c === 'x' ? r : (r & 0x3) | 0x8
          return v.toString(16)
        }),
    },
    writable: true,
  })
}

// ── Catch unhandled rejections from jsdom (e.g. Leaflet tile fetch) ──
process.on('unhandledRejection', () => {
  // Suppress jsdom/undici unhandled rejections in test env
})

// ── Suppress console.error noise from React in tests ─────────
const originalError = console.error
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    // Suppress React DOM nesting warnings and act() warnings in test output
    const msg = typeof args[0] === 'string' ? args[0] : ''
    if (
      msg.includes('Warning: An update to') ||
      msg.includes('act()')
    ) {
      return
    }
    originalError(...args)
  }
})

afterAll(() => {
  console.error = originalError
})
