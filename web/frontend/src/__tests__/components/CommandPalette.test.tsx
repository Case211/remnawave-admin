import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CommandPalette } from '@/components/CommandPalette'

// Mock the API client
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { items: [] } }),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders navigation items when open', () => {
    renderWithProviders(
      <CommandPalette open={true} onOpenChange={vi.fn()} />
    )

    expect(screen.getByText('Дашборд')).toBeInTheDocument()
    expect(screen.getByText('Пользователи')).toBeInTheDocument()
    expect(screen.getByText('Ноды')).toBeInTheDocument()
    expect(screen.getByText('Хосты')).toBeInTheDocument()
    expect(screen.getByText('Нарушения')).toBeInTheDocument()
    expect(screen.getByText('Настройки')).toBeInTheDocument()
  })

  it('renders administration section', () => {
    renderWithProviders(
      <CommandPalette open={true} onOpenChange={vi.fn()} />
    )

    expect(screen.getByText('Администраторы и роли')).toBeInTheDocument()
    expect(screen.getByText('Журнал аудита')).toBeInTheDocument()
    expect(screen.getByText('Системные логи')).toBeInTheDocument()
  })

  it('renders quick actions section', () => {
    renderWithProviders(
      <CommandPalette open={true} onOpenChange={vi.fn()} />
    )

    expect(screen.getByText('Создать пользователя')).toBeInTheDocument()
    expect(screen.getByText('Поиск пользователей')).toBeInTheDocument()
  })

  it('renders search input with placeholder', () => {
    renderWithProviders(
      <CommandPalette open={true} onOpenChange={vi.fn()} />
    )

    const input = screen.getByPlaceholderText('Поиск страниц, пользователей, действий...')
    expect(input).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    renderWithProviders(
      <CommandPalette open={false} onOpenChange={vi.fn()} />
    )

    expect(screen.queryByText('Дашборд')).not.toBeInTheDocument()
  })
})
