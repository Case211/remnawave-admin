/**
 * Клик по уведомлению гасит «непрочитанное» и открывает ссылку, а без ссылки —
 * то, что передал вызывающий (колокольчик — список уведомлений). Раньше клик
 * по уведомлению без ссылки не делал ничего.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useOpenNotification } from '@/lib/useOpenNotification'
import { notificationsApi } from '@/api/notifications'
import type { Notification } from '@/api/notifications'

vi.mock('@/api/notifications', () => ({ notificationsApi: { markRead: vi.fn() } }))

const base: Notification = {
  id: 7, admin_id: null, type: 'torrent', severity: 'critical', title: 'Торрент трафик обнаружен',
  body: null, link: null, is_read: false, source: 'collector', source_id: 'u1', group_key: null,
  created_at: null,
}

function Probe({ n, fallback }: { n: Notification; fallback?: string }) {
  const open = useOpenNotification()
  const location = useLocation()
  return (
    <>
      <button onClick={() => open(n, fallback)}>open</button>
      <span data-testid="path">{location.pathname}</span>
    </>
  )
}

function renderProbe(n: Notification, fallback?: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <Probe n={n} fallback={fallback} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('useOpenNotification', () => {
  beforeEach(() => {
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue(undefined)
  })

  it('marks it read and follows the link', async () => {
    renderProbe({ ...base, link: '/users/u1' }, '/notifications')
    await userEvent.click(screen.getByText('open'))
    expect(notificationsApi.markRead).toHaveBeenCalledWith([7])
    expect(screen.getByTestId('path').textContent).toBe('/users/u1')
  })

  it('without a link opens the fallback instead of doing nothing', async () => {
    renderProbe(base, '/notifications')
    await userEvent.click(screen.getByText('open'))
    expect(notificationsApi.markRead).toHaveBeenCalledWith([7])
    expect(screen.getByTestId('path').textContent).toBe('/notifications')
  })

  it('does not mark an already read one again', async () => {
    renderProbe({ ...base, is_read: true, link: '/finance' })
    await userEvent.click(screen.getByText('open'))
    expect(notificationsApi.markRead).not.toHaveBeenCalled()
    expect(screen.getByTestId('path').textContent).toBe('/finance')
  })
})
