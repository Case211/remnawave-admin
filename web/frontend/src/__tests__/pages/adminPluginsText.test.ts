/**
 * pickText — выбор локали для текстов каталога плагинов.
 *
 * Регрессия: каталог отдал features строками вместо словарей локалей, и
 * ветка Object.values разобрала строку на символы — в карточке block_radar
 * буллеты выглядели как «✓ r», «✓ r», «✓ t».
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

const { pickText, saleMode } = await import('@/pages/AdminPlugins')

describe('pickText', () => {
  it('берёт нужную локаль', () => {
    expect(pickText({ ru: 'Радар', en: 'Radar' }, 'ru')).toBe('Радар')
    expect(pickText({ ru: 'Радар', en: 'Radar' }, 'en-US')).toBe('Radar')
  })

  it('откатывается на другую локаль, когда нужной нет', () => {
    expect(pickText({ en: 'Radar' }, 'ru')).toBe('Radar')
  })

  it('возвращает простую строку целиком, а не первый символ', () => {
    expect(pickText('radar_ingest', 'ru')).toBe('radar_ingest')
  })

  it('пустой ввод даёт пустую строку', () => {
    expect(pickText(undefined, 'ru')).toBe('')
  })
})

describe('saleMode', () => {
  it('бесплатный плагин отличается от снятого с продажи', () => {
    // У обоих purchasable=false и пустые тарифы, но для оператора это
    // противоположные вещи: одно ставится сразу, другое нельзя вообще.
    expect(saleMode({ free: true, purchasable: false })).toBe('free')
    expect(saleMode({ purchasable: false })).toBe('paused')
  })

  it('обычный платный плагин продаётся', () => {
    expect(saleMode({ purchasable: true })).toBe('sale')
  })

  it('сервер старой версии не знает про free — значит продаётся', () => {
    expect(saleMode({})).toBe('sale')
  })
})
