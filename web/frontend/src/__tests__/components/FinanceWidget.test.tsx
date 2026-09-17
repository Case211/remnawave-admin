import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { FinanceItem } from '@/api/finance'
import { FinanceWidget, nextPayment, paymentUrgency } from '@/components/dashboard/ExtraWidgets'

const getSummary = vi.fn()
const getUpcoming = vi.fn()
vi.mock('@/api/finance', () => ({
  financeApi: {
    getSummary: (...args: unknown[]) => getSummary(...args),
    getUpcoming: (...args: unknown[]) => getUpcoming(...args),
  },
}))
vi.mock('@/api/backup', () => ({ backupApi: { getStatus: vi.fn() } }))
vi.mock('@/api/client', () => ({ default: { get: vi.fn() } }))

function item(over: Partial<FinanceItem>): FinanceItem {
  return {
    id: 1, kind: 'expense', name: 'Сервер', category_id: null, category_name: null, category_color: null,
    category_icon: null, provider_id: 1, provider_name: 'Hostkey', node_uuid: 'n1', node_name: 'Germany W',
    currency: 'EUR', amount: 12, billing_cycle: 'monthly', cycle_days: null, next_due_at: '2026-09-20',
    url: null, notes: null, status: 'active', monthly_equivalent: 12, days_left: 3, is_overdue: false,
    ...over,
  }
}

async function renderWidget(items: FinanceItem[]) {
  getSummary.mockResolvedValue({
    base_currency: 'RUB', this_month: { expense: 8880, income: 26557, net: 17677 },
  })
  getUpcoming.mockResolvedValue({ items })
  const { container } = render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter><FinanceWidget /></MemoryRouter>
    </QueryClientProvider>,
  )
  await screen.findByText('Расходы')
  return container.querySelector('.glass-card') as HTMLElement
}

describe('paymentUrgency', () => {
  it('неделя и дальше — обычная, до 5 дней — жёлтая, меньше дня — красная', () => {
    expect(paymentUrgency(7)).toBe('none')
    expect(paymentUrgency(6)).toBe('none')
    expect(paymentUrgency(5)).toBe('soon')
    expect(paymentUrgency(1)).toBe('soon')
    expect(paymentUrgency(0)).toBe('now')
    expect(paymentUrgency(-2)).toBe('now')
    expect(paymentUrgency(null)).toBe('none')
  })
})

describe('nextPayment', () => {
  it('берёт самый ранний расход и не смотрит на доходы', () => {
    const soonIncome = item({ id: 9, kind: 'income', days_left: 0 })
    const later = item({ id: 2, days_left: 9 })
    const soonest = item({ id: 3, days_left: 2 })
    expect(nextPayment([later, soonIncome, soonest])?.id).toBe(3)
    expect(nextPayment([soonIncome])).toBeNull()
    expect(nextPayment(undefined)).toBeNull()
  })
})

describe('FinanceWidget', () => {
  it('показывает ноду, хостера и сумму ближайшего платежа, плитка обычная за неделю', async () => {
    const card = await renderWidget([item({ days_left: 7 })])
    expect(screen.getByText('Germany W')).toBeTruthy()
    expect(screen.getByText(/Hostkey/)).toBeTruthy()
    expect(screen.getByText('12 EUR')).toBeTruthy()
    expect(screen.getByText('через 7 дн.')).toBeTruthy()
    expect(card.className).not.toMatch(/amber|red-500/)
    expect(getUpcoming).toHaveBeenCalledWith(30)
  })

  it('за 5 дней плитка жёлтая', async () => {
    const card = await renderWidget([item({ days_left: 5 })])
    expect(card.className).toContain('border-amber-400/35')
  })

  it('сегодня — красная, просроченный платёж тоже', async () => {
    const card = await renderWidget([item({ days_left: -1, is_overdue: true })])
    expect(card.className).toContain('border-red-500/45')
    expect(screen.getByText('просрочен 1 дн.')).toBeTruthy()
  })

  it('без платежей в горизонте — подпись вместо строки', async () => {
    await renderWidget([])
    expect(screen.getByText('Платежей в ближайшие 30 дн. нет')).toBeTruthy()
  })
})
