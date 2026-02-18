import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ErrorBoundary } from '@/components/ErrorBoundary'

// Component that throws an error for testing
function ThrowingComponent({ error }: { error?: Error }) {
  if (error) {
    throw error
  }
  return <div>Child content works</div>
}

describe('ErrorBoundary', () => {
  let originalConsoleError: typeof console.error

  beforeEach(() => {
    // Suppress React error boundary console output during tests
    originalConsoleError = console.error
    console.error = vi.fn()
  })

  afterEach(() => {
    console.error = originalConsoleError
  })

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello World</div>
      </ErrorBoundary>
    )

    expect(screen.getByText('Hello World')).toBeTruthy()
  })

  it('renders fallback UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Test crash')} />
      </ErrorBoundary>
    )

    // Should show error message
    expect(screen.getByText('Test crash')).toBeTruthy()
  })

  it('shows reload button in error state', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Boom')} />
      </ErrorBoundary>
    )

    // There should be a button (reload)
    const button = screen.getByRole('button')
    expect(button).toBeTruthy()
  })

  it('calls window.location.reload on button click', async () => {
    const user = userEvent.setup()

    // Mock window.location.reload
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
    })

    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Need reload')} />
      </ErrorBoundary>
    )

    const button = screen.getByRole('button')
    await user.click(button)

    expect(reloadMock).toHaveBeenCalled()
  })

  it('calls componentDidCatch with error info', () => {
    const spy = vi.spyOn(ErrorBoundary.prototype, 'componentDidCatch')

    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Caught error')} />
      </ErrorBoundary>
    )

    expect(spy).toHaveBeenCalled()
    expect(spy.mock.calls[0][0].message).toBe('Caught error')
    spy.mockRestore()
  })
})
