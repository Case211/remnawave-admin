import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColumnFilter } from '@/components/table/ColumnFilter'

const OPTIONS = [
  { value: 'active', label: 'Активен' },
  { value: 'disabled', label: 'Отключён' },
]

async function open(ui: React.ReactElement) {
  const user = userEvent.setup()
  render(ui)
  await user.click(screen.getByRole('button', { name: /фильтр/i }))
  return user
}

describe('ColumnFilter', () => {
  describe('single', () => {
    it('выбирает одно значение', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="single" options={OPTIONS} value={[]} onChange={onChange} />,
      )
      await user.click(screen.getByText('Активен'))
      expect(onChange).toHaveBeenCalledWith(['active'])
    })

    it('заменяет выбранное, а не копит его', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="single" options={OPTIONS} value={['active']} onChange={onChange} />,
      )
      await user.click(screen.getByText('Отключён'))
      expect(onChange).toHaveBeenCalledWith(['disabled'])
    })

    it('повторный клик снимает фильтр', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="single" options={OPTIONS} value={['active']} onChange={onChange} />,
      )
      await user.click(screen.getByText('Активен'))
      expect(onChange).toHaveBeenCalledWith(null)
    })
  })

  describe('select', () => {
    it('копит значения — поведение не изменилось', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="select" options={OPTIONS} value={['active']} onChange={onChange} />,
      )
      await user.click(screen.getByText('Отключён'))
      expect(onChange).toHaveBeenCalledWith(['active', 'disabled'])
    })
  })

  describe('text', () => {
    it('отдаёт введённое значение', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="text" value={[]} onChange={onChange} placeholder="Имя" />,
      )
      await user.type(screen.getByPlaceholderText('Имя'), 'ab')
      expect(onChange).toHaveBeenLastCalledWith(['b'])
    })

    it('пустая строка снимает фильтр', async () => {
      const onChange = vi.fn()
      const user = await open(
        <ColumnFilter type="text" value={['abc']} onChange={onChange} placeholder="Имя" />,
      )
      await user.clear(screen.getByPlaceholderText('Имя'))
      expect(onChange).toHaveBeenCalledWith(null)
    })
  })

  it('отмечает активный фильтр на кнопке', () => {
    const { container } = render(
      <ColumnFilter type="single" options={OPTIONS} value={['active']} onChange={vi.fn()} />,
    )
    expect(container.querySelector('.text-primary-400')).not.toBeNull()
  })
})
