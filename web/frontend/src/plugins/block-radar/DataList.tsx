/**
 * Таблица, которая на телефоне превращается в карточки.
 *
 * Раньше таблицы стояли с `w-full` внутри `overflow-x-auto`: ширина
 * подгонялась под экран, колонки схлопывались и содержимое рвалось на узких
 * экранах, а горизонтальный скролл при этом не появлялся — ему нужна таблица
 * шире контейнера. Вместо того чтобы заставлять человека возить страницу
 * вбок, на мобильной ширине показываем по карточке на строку: заглавная
 * ячейка сверху, остальные — парами «поле → значение».
 */
import type { ReactNode } from 'react'

export interface Column<T> {
  /** Заголовок колонки и подпись поля в карточке. */
  title: string
  cell: (row: T) => ReactNode
  /** Заглавная ячейка: в карточке идёт крупно сверху, без подписи. */
  primary?: boolean
  /** Не переносить содержимое в таблице (даты, числа). */
  nowrap?: boolean
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, index: number) => string | number
}

export default function DataList<T>({ columns, rows, rowKey }: Props<T>) {
  const head = columns.find((c) => c.primary) ?? columns[0]
  const rest = columns.filter((c) => c !== head)

  return (
    <>
      <div className="glass-card p-2 overflow-x-auto hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-dark-400">
              {columns.map((c) => (
                <th key={c.title} className="px-3 py-2">
                  {c.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={rowKey(row, i)}
                className="border-t border-[var(--glass-border)] text-dark-200"
              >
                {columns.map((c) => (
                  <td
                    key={c.title}
                    className={`px-3 py-2${c.nowrap ? ' whitespace-nowrap' : ''}`}
                  >
                    {c.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-2 md:hidden">
        {rows.map((row, i) => (
          <div key={rowKey(row, i)} className="glass-card p-3 space-y-2">
            <div className="text-sm text-white font-medium">{head.cell(row)}</div>
            <dl className="space-y-1">
              {rest.map((c) => (
                <div key={c.title} className="flex items-baseline justify-between gap-3">
                  <dt className="text-[11px] uppercase tracking-wider text-dark-400 shrink-0">
                    {c.title}
                  </dt>
                  <dd className="text-xs text-dark-200 text-right">{c.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </>
  )
}
