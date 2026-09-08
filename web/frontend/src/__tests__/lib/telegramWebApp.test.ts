import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const HASH_INIT_DATA =
  'user=%7B%22id%22%3A777%7D&auth_date=1700000000&hash=abc123'

/**
 * Модуль кэширует снятое значение в переменной, поэтому каждый тест
 * импортирует его заново через vi.resetModules().
 */
async function loadModule() {
  vi.resetModules()
  return import('@/lib/telegramWebApp')
}

function setLocation(hash: string, search = '') {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, hash, search },
  })
}

describe('telegramWebApp', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setLocation('', '')
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  it('извлекает tgWebAppData из хеша', async () => {
    setLocation(`#tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}&tgWebAppVersion=7.0`)
    const { captureTelegramInitData, isTelegramMiniApp } = await loadModule()

    expect(captureTelegramInitData()).toBe(HASH_INIT_DATA)
    expect(isTelegramMiniApp()).toBe(true)
  })

  it('сохраняет initData в sessionStorage и переживает потерю хеша', async () => {
    setLocation(`#tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}`)
    const first = await loadModule()
    first.captureTelegramInitData()

    // Роутер затёр хеш, страница перезагрузилась — модуль загружается заново
    setLocation('')
    const second = await loadModule()
    expect(second.getTelegramInitData()).toBe(HASH_INIT_DATA)
  })

  it('вне Telegram возвращает null', async () => {
    const { getTelegramInitData, isTelegramMiniApp } = await loadModule()
    expect(getTelegramInitData()).toBeNull()
    expect(isTelegramMiniApp()).toBe(false)
  })

  it('игнорирует пустой tgWebAppData', async () => {
    setLocation('#tgWebAppData=&tgWebAppVersion=7.0')
    const { isTelegramMiniApp } = await loadModule()
    expect(isTelegramMiniApp()).toBe(false)
  })

  it('читает параметры из query, если клиент положил их туда', async () => {
    setLocation('', `?tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}`)
    const { getTelegramInitData } = await loadModule()
    expect(getTelegramInitData()).toBe(HASH_INIT_DATA)
  })

  it('clearTelegramInitData стирает и память, и sessionStorage', async () => {
    setLocation(`#tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}`)
    const mod = await loadModule()
    mod.captureTelegramInitData()

    setLocation('')
    mod.clearTelegramInitData()

    expect(mod.getTelegramInitData()).toBeNull()
    expect(sessionStorage.getItem('rw_tg_init_data')).toBeNull()
  })

  it('переживает недоступный sessionStorage', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    setLocation(`#tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}`)
    const { getTelegramInitData } = await loadModule()

    expect(getTelegramInitData()).toBe(HASH_INIT_DATA)
    spy.mockRestore()
  })
})
