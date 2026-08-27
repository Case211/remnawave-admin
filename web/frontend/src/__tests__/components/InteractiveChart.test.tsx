/**
 * Легенда графика: свёртка хвоста и клик-фильтр.
 *
 * Живой случай: на панели с сорока нодами легенда Recharts делила с графиком
 * фиксированную высоту и съедала её целиком — данные были, а рисовать их было
 * негде. Здесь проверяется поведение, которое это чинит.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InteractiveChart } from '@/components/charts/InteractiveChart'

/** N серий, где вес убывает с номером: series-0 — самая тяжёлая. */
function makeSeries(count: number) {
  return Array.from({ length: count }, (_, i) => ({ key: `s${i}`, name: `Нода ${i}` }))
}

function makeData(count: number, points = 3) {
  return Array.from({ length: points }, (_, p) => {
    const row: Record<string, unknown> = { name: `t${p}` }
    for (let i = 0; i < count; i++) row[`s${i}`] = (count - i) * 100
    return row
  })
}

function legendButtons() {
  return screen.getAllByRole('button').filter((b) => b.getAttribute('aria-pressed') !== null)
}

describe('InteractiveChart — легенда', () => {
  it('до порога показывает все серии и ничего не сворачивает', () => {
    render(<InteractiveChart data={makeData(4)} xKey="name" series={makeSeries(4)} maxSeries={10} />)

    expect(legendButtons()).toHaveLength(4)
    expect(screen.queryByText(/Прочие/)).not.toBeInTheDocument()
  })

  it('за порогом оставляет топ поимённо, а хвост сворачивает', () => {
    render(<InteractiveChart data={makeData(14)} xKey="name" series={makeSeries(14)} maxSeries={10} />)

    // Десять самых тяжёлых + одна свёрнутая.
    expect(legendButtons()).toHaveLength(11)
    expect(screen.getByText('Прочие (4)')).toBeInTheDocument()
    // Тяжёлые остались поимённо, лёгкие ушли в свёртку.
    expect(screen.getByText('Нода 0')).toBeInTheDocument()
    expect(screen.queryByText('Нода 13')).not.toBeInTheDocument()
    expect(screen.getByText(/Показано 10 из 14/)).toBeInTheDocument()
  })

  it('клик по серии гасит её, повторный — возвращает', async () => {
    const user = userEvent.setup()
    render(<InteractiveChart data={makeData(4)} xKey="name" series={makeSeries(4)} />)

    const first = legendButtons()[0]
    expect(first).toHaveAttribute('aria-pressed', 'true')

    await user.click(first)
    expect(legendButtons()[0]).toHaveAttribute('aria-pressed', 'false')

    await user.click(legendButtons()[0])
    expect(legendButtons()[0]).toHaveAttribute('aria-pressed', 'true')
  })

  it('alt-клик оставляет одну серию, второй такой же — возвращает все', () => {
    render(<InteractiveChart data={makeData(4)} xKey="name" series={makeSeries(4)} />)

    fireEvent.click(legendButtons()[1], { altKey: true })
    const pressed = legendButtons().map((b) => b.getAttribute('aria-pressed'))
    expect(pressed).toEqual(['false', 'true', 'false', 'false'])

    fireEvent.click(legendButtons()[1], { altKey: true })
    expect(legendButtons().every((b) => b.getAttribute('aria-pressed') === 'true')).toBe(true)
  })

  it('последнюю видимую серию погасить нельзя', async () => {
    const user = userEvent.setup()
    render(<InteractiveChart data={makeData(3)} xKey="name" series={makeSeries(3)} />)

    // Гасим по одной; на третьей клик обязан остаться без последствий —
    // пустой график читается как поломка, а не как выбор пользователя.
    for (const btn of legendButtons()) await user.click(btn)

    const visible = legendButtons().filter((b) => b.getAttribute('aria-pressed') === 'true')
    expect(visible).toHaveLength(1)
  })

  it('«Показать все» возвращает погашенные серии', async () => {
    const user = userEvent.setup()
    render(<InteractiveChart data={makeData(4)} xKey="name" series={makeSeries(4)} />)

    await user.click(legendButtons()[0])
    await user.click(screen.getByText('Показать все'))

    expect(legendButtons().every((b) => b.getAttribute('aria-pressed') === 'true')).toBe(true)
  })
})
