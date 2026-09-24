import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ShaperBadge } from '@/components/nodes/ShaperBadge'

describe('ShaperBadge', () => {
  it('не рисуется, когда шейпер выключен', () => {
    const { container } = render(<ShaperBadge state={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('не рисуется на незнакомом состоянии', () => {
    const { container } = render(<ShaperBadge state="whatever" />)
    expect(container.firstChild).toBeNull()
  })

  it('показывает бейдж с подсказкой о состоянии', () => {
    render(<ShaperBadge state="rough" />)
    const badge = screen.getByText(/Шейпер|nodes\.shaper\.badge\.label/)
    expect(badge.closest('span')?.getAttribute('title')).toBeTruthy()
  })
})
