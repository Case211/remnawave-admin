/**
 * Хлебные крошки: подписи и куда они ведут.
 *
 * Регрессия, из-за которой тест и появился: сегмент `plugins` рисовался
 * ссылкой на `/plugins`, а такой страницы нет — клик по крошке уводил в
 * 404. Заодно ловим мёртвые ключи локали: `nav.billing` не существовал ни
 * в ru, ни в en, и крошка показывала бы сам ключ вместо подписи.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ru from '@/locales/ru/translation.json'
import en from '@/locales/en/translation.json'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

const { default: PageBreadcrumbs, ROUTE_LABEL_KEYS, VIRTUAL_SEGMENTS } = await import(
  '@/components/layout/PageBreadcrumbs'
)

function lookup(tree: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      tree,
    )
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <PageBreadcrumbs />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PageBreadcrumbs', () => {
  it('каждый ключ подписи существует в обеих локалях', () => {
    for (const [segment, key] of Object.entries(ROUTE_LABEL_KEYS)) {
      expect(typeof lookup(ru, key), `ru: ${segment} → ${key}`).toBe('string')
      expect(typeof lookup(en, key), `en: ${segment} → ${key}`).toBe('string')
    }
  })

  it('сегмент без своей страницы не становится ссылкой', () => {
    const { container } = renderAt('/plugins/smart-support/clients')
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).not.toContain('/plugins')
    // а раздел плагина — обычная ссылка: страница у него есть
    expect(hrefs).toContain('/plugins/smart-support')
  })

  it('группирующий сегмент подписан, а не показан как есть', () => {
    renderAt('/admin/plugins')
    expect(screen.queryByText('admin')).toBeNull()
    expect(VIRTUAL_SEGMENTS.has('admin')).toBe(true)
  })

  it('раздел плагина подписан его собственным именем', () => {
    renderAt('/plugins/smart-support/clients')
    expect(screen.getByText('Smart Support')).toBeTruthy()
    expect(screen.getByText('Справочник клиентов')).toBeTruthy()
  })
})
