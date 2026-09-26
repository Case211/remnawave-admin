import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ViolationCard } from '@/pages/Violations'
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

const renderCard = (violation: Violation, onWarn = vi.fn()) => {
  render(
    <TooltipProvider>
      <ViolationCard
        violation={violation}
        canResolve
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
    renderCard({ ...baseViolation, notified: true })

    expect(screen.getByRole('button', { name: 'Предупредить' })).toBeDisabled()
  })
})
