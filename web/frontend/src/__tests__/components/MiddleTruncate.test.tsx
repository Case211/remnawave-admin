import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MiddleTruncate } from '@/components/MiddleTruncate'

afterEach(cleanup)

describe('MiddleTruncate', () => {
  it('оставляет хвост нетронутым — по нему узнают ноду', () => {
    const { container } = render(<MiddleTruncate text="Финляндия_6" />)
    const [head, tail] = Array.from(container.querySelectorAll('span > span'))
    expect(head.textContent).toBe('Финлянди')
    expect(tail.textContent).toBe('я_6')
    // Сжимается только голова, хвост остаётся целиком
    expect(head.className).toContain('truncate')
    expect(tail.className).toContain('shrink-0')
  })

  it('полное имя доступно подсказкой', () => {
    render(<MiddleTruncate text="Foreign Netherlands 2" />)
    expect(screen.getByTitle('Foreign Netherlands 2')).toBeTruthy()
  })

  it('короткое имя не режет — половина текста это уже слишком', () => {
    const { container } = render(<MiddleTruncate text="NL1" tailChars={3} />)
    const spans = container.querySelectorAll('span > span')
    expect(spans).toHaveLength(2)
    expect(spans[0].textContent).toBe('NL')
    expect(spans[1].textContent).toBe('1')
  })

  it('вырожденный случай: пустая строка не роняет рендер', () => {
    const { container } = render(<MiddleTruncate text="" />)
    expect(container.querySelectorAll('span > span')).toHaveLength(1)
  })
})
