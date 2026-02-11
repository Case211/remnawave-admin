import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialog } from '@/components/ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title and description when open', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Удалить пользователя?"
        description="Это действие необратимо."
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText('Удалить пользователя?')).toBeInTheDocument()
    expect(screen.getByText('Это действие необратимо.')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(
      <ConfirmDialog
        open={false}
        onOpenChange={vi.fn()}
        title="Hidden"
        onConfirm={vi.fn()}
      />
    )

    expect(screen.queryByText('Hidden')).not.toBeInTheDocument()
  })

  it('uses default button labels', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm"
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText('Подтвердить')).toBeInTheDocument()
    expect(screen.getByText('Отмена')).toBeInTheDocument()
  })

  it('uses custom button labels', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm"
        confirmLabel="Да, удалить"
        cancelLabel="Нет"
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText('Да, удалить')).toBeInTheDocument()
    expect(screen.getByText('Нет')).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button is clicked', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm action"
        onConfirm={onConfirm}
      />
    )

    await user.click(screen.getByText('Подтвердить'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('applies destructive styling for destructive variant', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Delete"
        variant="destructive"
        onConfirm={vi.fn()}
      />
    )

    const confirmButton = screen.getByText('Подтвердить')
    expect(confirmButton.className).toContain('bg-red-600')
  })

  it('does not render description when not provided', () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Simple confirm"
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText('Simple confirm')).toBeInTheDocument()
    // AlertDialogDescription is not rendered
    const descriptions = screen.queryAllByRole('paragraph')
    // Only the title should be present, no extra description
    expect(descriptions).toHaveLength(0)
  })
})
