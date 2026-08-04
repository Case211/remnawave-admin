import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColumnFilterCell } from '@/components/table/ColumnFilterCell'
import type { ColumnFilterProps } from '@/components/table/ColumnFilter'

const OPTIONS = [
  { value: 'active', label: 'Активен' },
  { value: 'disabled', label: 'Отключён' },
]

function textFilter(value: string[], onChange = vi.fn()): ColumnFilterProps {
  return { type: 'text', value, onChange, placeholder: 'Имя' }
}

function singleFilter(value: string[], onChange = vi.fn()): ColumnFilterProps {
  return { type: 'single', options: OPTIONS, value, onChange }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('ColumnFilterCell', () => {
  describe('text', () => {
    it('отдаёт значение после паузы, а не на каждую букву', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()
      render(<ColumnFilterCell filter={textFilter([], onChange)} label="Имя" />)

      await user.type(screen.getByPlaceholderText('Имя'), 'abc')
      expect(onChange).not.toHaveBeenCalled()

      await waitFor(() => expect(onChange).toHaveBeenCalledWith(['abc']), { timeout: 1500 })
      expect(onChange).toHaveBeenCalledTimes(1)
    })

    it('крестик очищает поле', async () => {
      const onChange = vi.fn()
      const user = userEvent.setup()
      render(<ColumnFilterCell filter={textFilter(['abc'], onChange)} label="Имя" />)

      await user.click(screen.getByRole('button', { name: /сбросить/i }))
      expect(screen.getByPlaceholderText('Имя')).toHaveValue('')
      await waitFor(() => expect(onChange).toHaveBeenCalledWith(null), { timeout: 1500 })
    })

    it('подхватывает значение, изменённое снаружи', () => {
      const { rerender } = render(<ColumnFilterCell filter={textFilter([])} label="Имя" />)
      expect(screen.getByPlaceholderText('Имя')).toHaveValue('')

      rerender(<ColumnFilterCell filter={textFilter(['извне'])} label="Имя" />)
      expect(screen.getByPlaceholderText('Имя')).toHaveValue('извне')
    })
  })

  describe('single', () => {
    it('показывает выбранное значение', () => {
      render(<ColumnFilterCell filter={singleFilter(['active'])} label="Статус" />)
      expect(screen.getByText('Активен')).toBeInTheDocument()
    })

    it('без выбора показывает подсказку с названием столбца', () => {
      render(<ColumnFilterCell filter={singleFilter([])} label="Статус" />)
      expect(screen.getByText(/фильтр по/i)).toBeInTheDocument()
    })
  })

  it('для попап-режимов в шапке ничего не рисует', () => {
    const { container } = render(
      <ColumnFilterCell
        filter={{ type: 'select', options: OPTIONS, value: [], onChange: vi.fn() }}
        label="Статус"
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
