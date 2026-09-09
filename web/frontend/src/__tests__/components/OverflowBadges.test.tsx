import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { OverflowBadges } from '@/components/OverflowBadges'

const more = (n: number) => `ещё ${n}`
const ITEMS = ['Standard', 'Family', 'VIP']

const original = {
  offsetWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth'),
  clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth'),
}

/** jsdom не считает раскладку — подсовываем ширины по data-атрибутам. */
function mockWidths(root: number, item: number, tail: number) {
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get(this: HTMLElement) {
      if (this.hasAttribute('data-item')) return item
      if (this.hasAttribute('data-probe') || this.hasAttribute('data-tail')) return tail
      return 0
    },
  })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get(this: HTMLElement) {
      return this.hasAttribute('data-badges-root') ? root : 0
    },
  })
}

afterEach(() => {
  cleanup()
  for (const [key, descriptor] of Object.entries(original)) {
    if (descriptor) Object.defineProperty(HTMLElement.prototype, key, descriptor)
    else Reflect.deleteProperty(HTMLElement.prototype, key)
  }
})

describe('OverflowBadges', () => {
  it('без известных ширин показывает все бейджи и не рисует хвост', () => {
    const { container } = render(<OverflowBadges items={ITEMS} more={more} />)
    for (const name of ITEMS) expect(screen.getByText(name)).toBeInTheDocument()
    expect(container.querySelector('[data-tail]')).toBeNull()
  })

  it('сворачивает не влезающие бейджи в «ещё N» со списком в title', () => {
    // 250px: первый бейдж (100) + хвост (60) влезают, второй уже нет
    mockWidths(250, 100, 60)
    render(<OverflowBadges items={ITEMS} more={more} />)
    expect(screen.getByText('Standard')).toBeInTheDocument()
    expect(screen.queryByText('Family')).toBeNull()
    expect(screen.queryByText('VIP')).toBeNull()
    const tail = screen.getByText('ещё 2')
    expect(tail).toHaveAttribute('title', 'Family, VIP')
  })

  it('когда всё влезает, хвоста нет', () => {
    mockWidths(400, 100, 60)
    const { container } = render(<OverflowBadges items={ITEMS} more={more} />)
    for (const name of ITEMS) expect(screen.getByText(name)).toBeInTheDocument()
    expect(container.querySelector('[data-tail]')).toBeNull()
  })

  it('первый бейдж остаётся даже в слишком узком контейнере', () => {
    mockWidths(50, 100, 60)
    render(<OverflowBadges items={ITEMS} more={more} />)
    expect(screen.getByText('Standard')).toBeInTheDocument()
    expect(screen.getByText('ещё 2')).toBeInTheDocument()
  })
})
