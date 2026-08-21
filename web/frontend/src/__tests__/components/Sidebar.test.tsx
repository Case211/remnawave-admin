/**
 * Боковое меню: порядок пунктов и вход в его настройку.
 *
 * Логика расстановки проверена отдельно (lib/sidebarOrder), здесь важно
 * другое — что сохранённый порядок доезжает до отрисованного меню и что
 * настройку вообще можно открыть.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { usePermissionStore } from '@/store/permissionStore'
import { useAuthStore } from '@/store/authStore'
import { TooltipProvider } from '@/components/ui/tooltip'
import { SIDEBAR_ORDER_KEY } from '@/lib/sidebarOrder'
import Sidebar from '@/components/layout/Sidebar'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { panel_name: 'Test Panel' } }),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

vi.mock('@/lib/plugins', () => ({
  useActivePlugins: () => ({ data: [] }),
  resolvePluginIcon: () => () => null,
}))

function renderSidebar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter>
          <Sidebar />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

/** Маршруты пунктов меню в том порядке, в каком они отрисованы. */
function menuRoutes(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('nav a')).map((a) => a.getAttribute('href') ?? '')
}

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({
    user: { username: 'admin', firstName: 'Admin', authMethod: 'password' },
    accessToken: 'test-token',
    refreshToken: 'test-refresh',
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })
  usePermissionStore.setState({ permissions: [], role: 'superadmin', roleId: 1, isLoaded: true })
})

describe('Sidebar', () => {
  it('по умолчанию меню идёт в исходном порядке', () => {
    const { container } = renderSidebar()
    // Плагины сразу после аналитики: они в «Обзоре», а не в «Администрировании»
    expect(menuRoutes(container).slice(0, 4)).toEqual(['/', '/analytics', '/admin/plugins', '/users'])
  })

  it('акцентный пункт выделен цветом, обычные — нет', () => {
    const { container } = renderSidebar()
    const cls = (href: string) =>
      container.querySelector(`a[href="${href}"]`)?.getAttribute('class') ?? ''
    expect(cls('/admin/plugins')).toMatch(/amber/)
    expect(cls('/users')).not.toMatch(/amber/)
    expect(cls('/analytics')).not.toMatch(/amber/)
  })

  it('сохранённый порядок применяется к отрисованному меню', () => {
    localStorage.setItem(
      SIDEBAR_ORDER_KEY,
      JSON.stringify({
        top: [
          'section:nav.sections.infrastructure',
          'item:/nodes',
          'item:/fleet',
          'item:/hosts',
          'section:nav.sections.overview',
          'item:/',
          'item:/analytics',
        ],
        groups: {},
      }),
    )
    const { container } = renderSidebar()
    const routes = menuRoutes(container)
    expect(routes.slice(0, 3)).toEqual(['/nodes', '/fleet', '/hosts'])
    expect(routes.indexOf('/')).toBeGreaterThan(routes.indexOf('/hosts'))
    // Пункты, которых не было в сохранённом порядке, никуда не делись — и
    // остались в родной секции, а не съехали в конец меню
    expect(routes.indexOf('/dns')).toBeGreaterThan(routes.indexOf('/hosts'))
    expect(routes.indexOf('/dns')).toBeLessThan(routes.indexOf('/'))
    expect(routes).toContain('/settings')
  })

  it('порядок внутри группы применяется к её подпунктам', () => {
    localStorage.setItem(
      SIDEBAR_ORDER_KEY,
      JSON.stringify({ top: [], groups: { 'group:nav.administration': ['/logs', '/admins'] } }),
    )
    const { container } = renderSidebar()
    const routes = menuRoutes(container).filter((href) => ['/logs', '/admins', '/audit'].includes(href))
    expect(routes).toEqual(['/logs', '/admins', '/audit'])
  })

  it('кнопка открывает диалог настройки со списком пунктов', async () => {
    const user = userEvent.setup()
    renderSidebar()

    await user.click(screen.getByRole('button', { name: 'Настроить меню' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeTruthy()
    // Тот же набор пунктов, что и в меню, — включая подпункты групп
    const labels = Array.from(dialog.querySelectorAll('li')).map((li) => li.textContent)
    expect(labels.some((text) => text?.includes('Дашборд'))).toBe(true)
    expect(labels.some((text) => text?.includes('Системные логи'))).toBe(true)
  })

  it('на нетронутом меню сброс недоступен', async () => {
    const user = userEvent.setup()
    renderSidebar()
    await user.click(screen.getByRole('button', { name: 'Настроить меню' }))

    const reset = await screen.findByRole('button', { name: /Сбросить/ })
    expect(reset).toHaveProperty('disabled', true)
  })
})
