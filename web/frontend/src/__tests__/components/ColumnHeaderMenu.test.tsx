import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColumnHeaderMenu } from '@/components/table/ColumnHeaderMenu'

async function openMenu(ui: React.ReactElement) {
  const user = userEvent.setup()
  render(ui)
  await user.click(screen.getByRole('button', { name: /меню столбца/i }))
  return user
}

describe('ColumnHeaderMenu', () => {
  it('задаёт направление сортировки явно', async () => {
    const onSort = vi.fn()
    const user = await openMenu(<ColumnHeaderMenu label="Статус" onSort={onSort} />)
    await user.click(screen.getByText(/по возрастанию/i))
    expect(onSort).toHaveBeenCalledWith('asc')
  })

  it('не предлагает то направление, что уже выбрано', async () => {
    await openMenu(<ColumnHeaderMenu label="Статус" sortDir="asc" onSort={vi.fn()} />)
    expect(screen.getByText(/по возрастанию/i).closest('[role="menuitem"]')).toHaveAttribute(
      'aria-disabled',
      'true',
    )
  })

  it('сбрасывает сортировку', async () => {
    const onClearSort = vi.fn()
    const user = await openMenu(
      <ColumnHeaderMenu label="Статус" sortDir="desc" onSort={vi.fn()} onClearSort={onClearSort} />,
    )
    await user.click(screen.getByText(/сбросить сортировку/i))
    expect(onClearSort).toHaveBeenCalled()
  })

  it('сброс фильтра неактивен, пока фильтра нет', async () => {
    await openMenu(<ColumnHeaderMenu label="Тег" onClearFilter={vi.fn()} hasFilter={false} />)
    expect(screen.getByText(/сбросить фильтр/i).closest('[role="menuitem"]')).toHaveAttribute(
      'aria-disabled',
      'true',
    )
  })

  it('скрывает столбец и показывает все', async () => {
    const onHide = vi.fn()
    const onShowAll = vi.fn()
    const user = await openMenu(
      <ColumnHeaderMenu label="Тег" onHide={onHide} onShowAll={onShowAll} />,
    )
    await user.click(screen.getByText(/скрыть столбец/i))
    expect(onHide).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /меню столбца/i }))
    await user.click(screen.getByText(/показать все столбцы/i))
    expect(onShowAll).toHaveBeenCalled()
  })

  it('без onHide пункта скрытия нет — столбец несокрываемый', async () => {
    await openMenu(<ColumnHeaderMenu label="Имя" onSort={vi.fn()} />)
    expect(screen.queryByText(/скрыть столбец/i)).toBeNull()
  })

  it('без onSort пунктов сортировки нет', async () => {
    await openMenu(<ColumnHeaderMenu label="Трафик" onHide={vi.fn()} />)
    expect(screen.queryByText(/по возрастанию/i)).toBeNull()
  })
})
