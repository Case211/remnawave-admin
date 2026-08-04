import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useTableColumns, type TableColumn } from '@/lib/useTableColumns'

const COLUMNS: TableColumn[] = [
  { key: 'username', labelKey: 'a', locked: true },
  { key: 'status', labelKey: 'b' },
  { key: 'created_at', labelKey: 'c' },
  { key: 'tag', labelKey: 'd', optional: true },
]

const keys = (cols: TableColumn[]) => cols.map((c) => c.key)

describe('useTableColumns', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('скрывает optional-колонки по умолчанию', () => {
    const { result } = renderHook(() => useTableColumns('t1', COLUMNS))
    expect(keys(result.current.visible)).toEqual(['username', 'status', 'created_at'])
    expect(result.current.isCustomized).toBe(false)
  })

  it('включает optional-колонку по требованию', () => {
    const { result } = renderHook(() => useTableColumns('t2', COLUMNS))
    act(() => result.current.toggle('tag'))
    expect(keys(result.current.visible)).toContain('tag')
  })

  it('не даёт спрятать locked-колонку', () => {
    const { result } = renderHook(() => useTableColumns('t3', COLUMNS))
    act(() => result.current.toggle('username'))
    expect(keys(result.current.visible)).toContain('username')
    expect(result.current.isVisible('username')).toBe(true)
  })

  it('переживает перемонтирование', () => {
    const first = renderHook(() => useTableColumns('t6', COLUMNS))
    act(() => {
      first.result.current.toggle('status')
      first.result.current.reorder('tag', 'created_at')
    })
    first.unmount()

    const second = renderHook(() => useTableColumns('t6', COLUMNS))
    expect(second.result.current.isVisible('status')).toBe(false)
    expect(keys(second.result.current.ordered)).toEqual(['username', 'status', 'tag', 'created_at'])
    expect(second.result.current.isCustomized).toBe(true)
  })

  it('настройки таблиц не пересекаются', () => {
    const users = renderHook(() => useTableColumns('users', COLUMNS))
    act(() => users.result.current.toggle('status'))

    const nodes = renderHook(() => useTableColumns('nodes', COLUMNS))
    expect(nodes.result.current.isVisible('status')).toBe(true)
  })

  it('сброс возвращает исходный вид', () => {
    const { result } = renderHook(() => useTableColumns('t7', COLUMNS))
    act(() => {
      result.current.toggle('tag')
      result.current.reorder('created_at', 'username')
    })
    act(() => result.current.reset())
    expect(keys(result.current.ordered)).toEqual(keys(COLUMNS))
    expect(keys(result.current.visible)).toEqual(['username', 'status', 'created_at'])
    expect(result.current.isCustomized).toBe(false)
  })

  it('новая колонка приезжает в конец, не ломая сохранённый порядок', () => {
    const first = renderHook(() => useTableColumns('t8', COLUMNS))
    act(() => first.result.current.reorder('created_at', 'status'))
    first.unmount()

    const extended = [...COLUMNS, { key: 'email', labelKey: 'e' }]
    const second = renderHook(() => useTableColumns('t8', extended))
    expect(keys(second.result.current.ordered)).toEqual([
      'username', 'created_at', 'status', 'tag', 'email',
    ])
  })
})

describe('useTableColumns.reorder', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('ставит колонку на место другой (перетаскивание)', () => {
    const { result } = renderHook(() => useTableColumns('d1', COLUMNS))
    act(() => result.current.reorder('tag', 'username'))
    expect(keys(result.current.ordered)).toEqual(['tag', 'username', 'status', 'created_at'])
  })

  it('перетаскивание вниз сохраняет остальной порядок', () => {
    const { result } = renderHook(() => useTableColumns('d2', COLUMNS))
    act(() => result.current.reorder('username', 'created_at'))
    expect(keys(result.current.ordered)).toEqual(['status', 'created_at', 'username', 'tag'])
  })

  it('бросок на себя ничего не меняет', () => {
    const { result } = renderHook(() => useTableColumns('d3', COLUMNS))
    act(() => result.current.reorder('status', 'status'))
    expect(keys(result.current.ordered)).toEqual(keys(COLUMNS))
    expect(result.current.isCustomized).toBe(false)
  })

  it('неизвестный ключ игнорируется', () => {
    const { result } = renderHook(() => useTableColumns('d4', COLUMNS))
    act(() => result.current.reorder('nope', 'status'))
    expect(keys(result.current.ordered)).toEqual(keys(COLUMNS))
  })
})
