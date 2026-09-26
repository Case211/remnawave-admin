import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const get = vi.fn()
const patch = vi.fn()
vi.mock('@/api/client', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    patch: (...args: unknown[]) => patch(...args),
  },
}))
vi.mock('@/components/PermissionGate', () => ({ useHasPermission: () => true }))

import { NoticeTemplatesTab } from '@/components/violations/NoticeTemplatesTab'

const template = (over: Record<string, unknown> = {}) => ({
  kind: 'default',
  enabled: true,
  min_score: 60,
  send_telegram: true,
  send_email: true,
  subject_ru: 'Использование подписки',
  body_ru: 'Здравствуйте!',
  email_html_ru: null,
  updated_at: '2026-09-26T00:00:00Z',
  updated_by: null,
  ...over,
})

async function renderTab(items: ReturnType<typeof template>[]) {
  get.mockResolvedValue({ data: { items, kinds: ['default'] } })
  patch.mockResolvedValue({ data: items[0] })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NoticeTemplatesTab />
    </QueryClientProvider>,
  )
  return screen.findByRole('checkbox', { name: /Telegram/ })
}

describe('NoticeTemplatesTab', () => {
  // jsdom не считает геометрию текста, а CodeMirror её меряет — отдаём пустую
  beforeAll(() => {
    Range.prototype.getClientRects = () => [] as unknown as DOMRectList
    Range.prototype.getBoundingClientRect = () => new DOMRect()
  })
  beforeEach(() => vi.clearAllMocks())

  it('keeps at least one delivery channel on', async () => {
    const telegram = await renderTab([template()])
    const email = screen.getByRole('checkbox', { name: /Email/ })

    fireEvent.click(email)

    expect(email).not.toBeChecked()
    expect(telegram).toBeDisabled()
  })

  it('blocks saving text Telegram would reject, and escapes special characters in one click', async () => {
    await renderTab([template({ body_ru: 'Скидка 50% & бонус' })])
    expect(screen.getByText('Telegram не примет этот текст')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /Предупреждать/ }))
    const save = screen.getByRole('button', { name: /Сохранить/ })
    expect(save).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Заменить спецсимволы' }))
    expect(screen.queryByText('Telegram не примет этот текст')).not.toBeInTheDocument()
    expect(save).toBeEnabled()

    fireEvent.click(save)
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/violations/notice-templates/default', {
        enabled: false,
        body_ru: 'Скидка 50% &amp; бонус',
      }),
    )
  })

  it('previews the email built from the Telegram text in a sandbox', async () => {
    await renderTab([template({ body_ru: '<b>Важно</b>\nтекст' })])

    fireEvent.mouseDown(screen.getByRole('tab', { name: /Email/ }))

    const frame = screen.getByTitle('Так выглядит письмо')
    expect(frame.getAttribute('srcdoc')).toContain('<b>Важно</b><br>')
    expect(frame.getAttribute('sandbox')).toBe('')
  })

  it('opens the email editor first when only email is on', async () => {
    await renderTab([template({ send_telegram: false, email_html_ru: '<h1>Своё письмо</h1>' })])

    expect(screen.getByTitle('Так выглядит письмо').getAttribute('srcdoc')).toContain('<h1>Своё письмо</h1>')
  })
})
