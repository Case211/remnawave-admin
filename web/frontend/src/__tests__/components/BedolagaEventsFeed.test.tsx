import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from '@/i18n'
import client from '@/api/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  EventsFeed,
  customerLabel,
  eventDetails,
  eventTitle,
  type SubscriptionEvent,
} from '@/components/bedolaga/EventsFeed'

vi.mock('@/api/client', () => ({ default: { get: vi.fn() } }))

const t = i18n.t.bind(i18n)
const get = vi.mocked(client.get)

function event(over: Partial<SubscriptionEvent>): SubscriptionEvent {
  return {
    id: 1, event_type: 'purchase', user_id: 7, user_full_name: 'Иван Петров',
    occurred_at: new Date().toISOString(), ...over,
  }
}

describe('eventDetails', () => {
  it('покупка: срок, переход с триала и способ оплаты', () => {
    expect(eventDetails('purchase', { period_days: 30, was_trial_conversion: true, payment_method: 'yookassa' }, t))
      .toEqual(['30 дн.', 'после триала', 'yookassa'])
  })

  it('продление и промокод показывают прибавку дней', () => {
    expect(eventDetails('renewal', { extended_days: 90, payment_method: 'balance' }, t)).toEqual(['+90 дн.', 'balance'])
    expect(eventDetails('promocode_activation', { code: 'SPRING', subscription_days: 7 }, t)).toEqual(['SPRING', '+7 дн.'])
  })

  it('смена промогруппы: откуда, куда и автоматически ли', () => {
    expect(eventDetails('promo_group_change', { old_group_name: 'Базовая', new_group_name: 'VIP', automatic: true }, t))
      .toEqual(['Базовая → VIP', 'автоматически'])
  })

  it('пустые поля и незнакомый тип не дают мусора', () => {
    expect(eventDetails('purchase', { period_days: null, payment_method: '  ' }, t)).toEqual([])
    expect(eventDetails('purchase', null, t)).toEqual([])
    expect(eventDetails('something_new', { period_days: 30 }, t)).toEqual([])
  })
})

describe('eventTitle и customerLabel', () => {
  it('незнакомый тип бота показывается как есть', () => {
    expect(eventTitle('balance_topup', t)).toBe('Пополнение баланса')
    expect(eventTitle('something_new', t)).toBe('something_new')
  })

  it('имя, иначе @username, иначе Telegram ID, иначе id в Bedolaga', () => {
    expect(customerLabel(event({}))).toBe('Иван Петров')
    expect(customerLabel(event({ user_full_name: '', user_username: 'ivan' }))).toBe('@ivan')
    expect(customerLabel(event({ user_full_name: '', user_telegram_id: 123 }))).toBe('123')
    expect(customerLabel(event({ user_full_name: null }))).toBe('#7')
  })
})

describe('EventsFeed', () => {
  // В скобках: mockReset() возвращает сам мок, а функцию из beforeEach vitest вызывает как очистку после теста
  beforeEach(() => {
    get.mockReset()
  })

  function renderFeed() {
    return render(
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <MemoryRouter><EventsFeed /></MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    )
  }

  it('показывает событие со ссылкой на клиента и фильтрует по группе типов', async () => {
    get.mockResolvedValue({ data: { items: [event({ amount_kopeks: 19900 })], total: 1 } })
    renderFeed()

    expect(await screen.findByText('Покупка подписки')).toBeInTheDocument()
    expect(screen.getByText('Иван Петров').closest('a')).toHaveAttribute('href', '/bedolaga/customers/7')
    expect(screen.getByText('199 ₽')).toBeInTheDocument()
    expect(get).toHaveBeenLastCalledWith('/bedolaga/customers/events?limit=20')

    fireEvent.click(screen.getByRole('button', { name: 'Оплаты' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith(
      '/bedolaga/customers/events?limit=20&event_type=purchase&event_type=renewal&event_type=balance_topup',
    ))
  })

  it('бонус клиенту не выдаётся за оплату', async () => {
    get.mockResolvedValue({
      data: { items: [event({ event_type: 'promocode_activation', amount_kopeks: 5000, extra: { code: 'GIFT' } })], total: 1 },
    })
    renderFeed()
    expect(await screen.findByText('+50 ₽')).toHaveClass('text-violet-300')
  })

  it('«Показать ещё» — пока бот отдал не всё', async () => {
    get.mockResolvedValue({ data: { items: [event({})], total: 45 } })
    renderFeed()
    fireEvent.click(await screen.findByRole('button', { name: 'Показать ещё' }))
    await waitFor(() => expect(get).toHaveBeenLastCalledWith('/bedolaga/customers/events?limit=40'))
  })

  it('пустая лента и ошибка бота различимы', async () => {
    get.mockResolvedValueOnce({ data: { items: [], total: 0 } })
    const { unmount } = renderFeed()
    expect(await screen.findByText('Событий пока нет')).toBeInTheDocument()
    unmount()

    get.mockRejectedValue(new Error('502'))
    renderFeed()
    // одна повторная попытка с паузой ~1 с — ждём дольше умолчания
    expect(await screen.findByText('Не удалось загрузить события', {}, { timeout: 4000 })).toBeInTheDocument()
  })
})
