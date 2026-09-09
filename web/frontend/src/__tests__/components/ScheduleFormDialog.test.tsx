/**
 * Расписание: нода выбирается из списка с поиском по имени и адресу —
 * обычный Select при десятках нод не годится.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ScheduleFormDialog from '@/components/fleet/ScheduleFormDialog'

vi.mock('@/api/fleet', () => ({
  listScripts: vi.fn().mockResolvedValue([]),
  createScheduledTask: vi.fn(),
  updateScheduledTask: vi.fn(),
}))

const NODES = Array.from({ length: 7 }, (_, i) => ({
  uuid: `u${i}`,
  name: i < 2 ? `Germany-${i}` : `Node-${i}`,
  address: `10.0.0.${i}`,
}))

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ScheduleFormDialog open onOpenChange={() => {}} nodes={NODES} />
    </QueryClientProvider>,
  )
}

describe('ScheduleFormDialog: выбор ноды с поиском', () => {
  it('ищет по имени и по адресу, выбор попадает в поле', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('combobox', { name: /выберите ноду/i }))
    const search = await screen.findByPlaceholderText(/поиск по имени или адресу/i)
    expect(screen.getByRole('option', { name: /Node-5/ })).toBeInTheDocument()

    await user.type(search, 'germ')
    expect(screen.getByRole('option', { name: /Germany-0/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Germany-1/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Node-5/ })).toBeNull()

    await user.clear(search)
    await user.type(search, '10.0.0.6')
    expect(screen.queryByRole('option', { name: /Germany-0/ })).toBeNull()

    await user.click(screen.getByRole('option', { name: /Node-6/ }))
    expect(screen.getByRole('combobox', { name: /выберите ноду/i })).toHaveTextContent('Node-6')
  })

  it('без совпадений пишет «ничего не найдено»', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('combobox', { name: /выберите ноду/i }))
    await user.type(await screen.findByPlaceholderText(/поиск по имени или адресу/i), 'zzz')
    expect(screen.getByText(/ничего не найдено/i)).toBeInTheDocument()
  })
})
