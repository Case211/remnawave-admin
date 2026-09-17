import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThrottleDialog } from '@/components/ThrottleDialog'

const post = vi.fn()
vi.mock('@/api/client', () => ({
  default: {
    post: (...args: unknown[]) => post(...args),
    get: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const SUBMIT = /Урезать скорость|violations\.throttles\.add/

function renderDialog(props: { userUuid?: string } = {}) {
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ThrottleDialog open onOpenChange={onOpenChange} {...props} />
    </QueryClientProvider>,
  )
  return { onOpenChange }
}

describe('ThrottleDialog', () => {
  beforeEach(() => {
    post.mockReset()
    post.mockResolvedValue({ data: { success: true } })
  })

  it('с заданным пользователем не спрашивает UUID и шлёт его в запрос', async () => {
    const user = userEvent.setup()
    const { onOpenChange } = renderDialog({ userUuid: 'u-1' })
    expect(screen.queryByPlaceholderText('uuid')).toBeNull()
    await user.type(screen.getAllByRole('spinbutton')[0], '512')
    await user.click(screen.getByRole('button', { name: SUBMIT }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/violations/throttle', {
      user_uuid: 'u-1', rate_kbit: 512, expires_in_hours: undefined, reason: undefined,
    }))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('без пользователя просит UUID и не даёт отправить пустой', () => {
    renderDialog()
    expect(screen.getByPlaceholderText('uuid')).toBeTruthy()
    const submit = screen.getByRole('button', { name: SUBMIT }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })
})
