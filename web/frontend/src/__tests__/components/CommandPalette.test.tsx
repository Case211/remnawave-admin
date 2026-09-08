/**
 * Быстрый поиск (Cmd+K): результаты приходят с сервера, а cmdk дополнительно
 * фильтрует их на клиенте по своему `value`. Если в value не попало поле, по
 * которому нашёл сервер (Telegram ID, email, UUID, описание), пользователь
 * пропадает из выдачи — сервер его вернул, а список показывает «ничего».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { CommandPalette } from '@/components/CommandPalette'
import client from '@/api/client'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

const USER = {
  uuid: '344ddd21-fead-483a-ae23-8c49e6b83ddb',
  short_uuid: '6U7X4Pn47FSb7JbumQJk',
  username: 'GeologVPN_192647_6487',
  email: null,
  telegram_id: 127192647,
  description: 'Тестовый ключ для пользователя 127192647',
  status: 'active',
}

function renderPalette() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CommandPalette open onOpenChange={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function search(text: string) {
  const user = userEvent.setup()
  renderPalette()
  await user.type(screen.getByRole('combobox'), text)
  // debounce поиска — 300 мс
  await waitFor(() => expect(client.get).toHaveBeenCalled(), { timeout: 2000 })
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(client.get).mockResolvedValue({ data: { items: [USER] } })
  })

  it('находит пользователя по username', async () => {
    await search('geolog')

    expect(await screen.findByText('GeologVPN_192647_6487')).toBeInTheDocument()
  })

  it('находит пользователя по Telegram ID', async () => {
    await search('127192647')

    expect(await screen.findByText('GeologVPN_192647_6487')).toBeInTheDocument()
  })

  it('находит пользователя по short UUID', async () => {
    await search('6U7X4Pn47FSb7JbumQJk')

    expect(await screen.findByText('GeologVPN_192647_6487')).toBeInTheDocument()
  })

  it('находит пользователя по фрагменту описания', async () => {
    await search('тестовый ключ')

    expect(await screen.findByText('GeologVPN_192647_6487')).toBeInTheDocument()
  })

  it('передаёт запрос на сервер как есть', async () => {
    await search('127192647')

    expect(client.get).toHaveBeenCalledWith('/users', {
      params: { search: '127192647', page: 1, per_page: 5 },
    })
  })
})
