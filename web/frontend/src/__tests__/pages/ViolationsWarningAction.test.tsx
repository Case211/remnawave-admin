import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ViolationCard, noticeFeedback } from '@/pages/Violations'
import type { Violation } from '@/types/violations'

const baseViolation: Violation = {
  id: 42,
  user_uuid: '00000000-0000-0000-0000-000000000042',
  username: 'test-user',
  email: null,
  telegram_id: 123456,
  score: 75,
  severity: 'high',
  recommended_action: 'warn',
  confidence: 0.8,
  action_taken: null,
  notified: false,
  detected_at: '2026-01-01T00:00:00Z',
  reasons: ['Test reason'],
}

const renderCard = (violation: Violation, onWarn = vi.fn(), isWarning = false) => {
  render(
    <TooltipProvider>
      <ViolationCard
        violation={violation}
        canResolve
        isWarning={isWarning}
        onWarn={onWarn}
        onBlock={vi.fn()}
        onDismiss={vi.fn()}
        onAnnul={vi.fn()}
        onWhitelist={vi.fn()}
        onViewDetail={vi.fn()}
        onViewUser={vi.fn()}
      />
    </TooltipProvider>,
  )
  return onWarn
}

describe('ViolationCard warning action', () => {
  it('calls the warning action for a pending violation', () => {
    const onWarn = renderCard(baseViolation)

    fireEvent.click(screen.getByRole('button', { name: 'Предупредить' }))

    expect(onWarn).toHaveBeenCalledOnce()
  })

  it('disables duplicate warnings already recorded by the backend', () => {
    renderCard({ ...baseViolation, client_notified_at: '2026-01-01T01:00:00Z' })

    expect(screen.getByRole('button', { name: 'Предупредить' })).toBeDisabled()
  })

  it('keeps the button enabled when only admins were alerted', () => {
    // notified — оповещение админов о нарушении, клиенту при этом ничего не уходило
    renderCard({ ...baseViolation, notified: true, client_notified_at: null })

    expect(screen.getByRole('button', { name: 'Предупредить' })).toBeEnabled()
  })

  it('blocks repeated clicks while the warning is being sent', () => {
    renderCard(baseViolation, vi.fn(), true)

    expect(screen.getByRole('button', { name: 'Предупредить' })).toBeDisabled()
  })
})

describe('noticeFeedback', () => {
  it('reports success only when the backend actually sent the warning', () => {
    expect(noticeFeedback({ sent: true })).toEqual({ ok: true, key: 'violations.toast.warned' })
  })

  it('explains a known refusal reason', () => {
    expect(noticeFeedback({ sent: false, reason: 'already_notified' }))
      .toEqual({ ok: false, key: 'violations.warnReasons.already_notified' })
  })

  it('falls back for unknown reasons and empty answers', () => {
    expect(noticeFeedback({ sent: false, reason: 'something_new' }).key).toBe('violations.warnReasons.unknown')
    expect(noticeFeedback(undefined)).toEqual({ ok: false, key: 'violations.warnReasons.unknown' })
  })
})
