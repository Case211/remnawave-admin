/**
 * Запуск скрипта: когда нод десятки, их ищут по имени или адресу, а «выбрать
 * все» относится только к найденным.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import RunScriptDialog from '@/components/fleet/RunScriptDialog'
import type { Script } from '@/components/fleet/ScriptCatalog'

const { NODES } = vi.hoisted(() => ({
  NODES: Array.from({ length: 7 }, (_, i) => ({
    uuid: `u${i}`,
    name: i < 2 ? `Germany-${i}` : `Node-${i}`,
    address: `10.0.0.${i}`,
    agent_v2_connected: true,
    agent_v2_last_ping: null,
  })),
}))

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { script_content: 'echo hi' } }),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

vi.mock('@/api/fleet', () => ({
  getFleetAgents: vi.fn().mockResolvedValue({ nodes: NODES, connected_count: NODES.length }),
  execScriptBulk: vi.fn(),
}))

const SCRIPT = { id: 's1', display_name: 'Ping' } as unknown as Script

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <RunScriptDialog open onOpenChange={() => {}} script={SCRIPT} />
    </QueryClientProvider>,
  )
}

const searchBox = () => screen.getByPlaceholderText(/поиск по имени или адресу/i)

describe('RunScriptDialog: поиск по нодам', () => {
  it('фильтрует список по имени и по адресу', async () => {
    const user = userEvent.setup()
    renderDialog()
    await screen.findByText('Germany-0')
    expect(screen.getByText('Node-5')).toBeInTheDocument()

    await user.type(searchBox(), 'germ')
    expect(screen.getByText('Germany-0')).toBeInTheDocument()
    expect(screen.getByText('Germany-1')).toBeInTheDocument()
    expect(screen.queryByText('Node-5')).toBeNull()

    await user.clear(searchBox())
    await user.type(searchBox(), '10.0.0.6')
    expect(screen.getByText('Node-6')).toBeInTheDocument()
    expect(screen.queryByText('Germany-0')).toBeNull()
  })

  it('«выбрать все» берёт только найденные ноды', async () => {
    const user = userEvent.setup()
    renderDialog()
    await screen.findByText('Germany-0')

    await user.type(searchBox(), 'germany')
    await user.click(screen.getByRole('button', { name: /выбрать все/i }))
    expect(screen.getByText('(2)')).toBeInTheDocument()
  })

  it('без совпадений пишет «ничего не найдено»', async () => {
    const user = userEvent.setup()
    renderDialog()
    await screen.findByText('Germany-0')

    await user.type(searchBox(), 'zzz')
    expect(screen.getByText(/ничего не найдено/i)).toBeInTheDocument()
  })
})
