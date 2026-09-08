import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const HASH_INIT_DATA =
  'user=%7B%22id%22%3A777%2C%22username%22%3A%22admin777%22%7D&auth_date=1700000000&hash=abc123'

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
    value: { ...window.location, hash, search, pathname: '/dashboard' },
  })
}

/** Мобильный клиент Telegram: в WebView проброшен мост. */
function insideTelegramClient() {
  Object.defineProperty(window, 'TelegramWebviewProxy', {
    configurable: true,
    value: { postEvent: () => {} },
  })
}

function miniAppHash(initData = HASH_INIT_DATA, platform = 'ios') {
  return `#tgWebAppData=${encodeURIComponent(initData)}&tgWebAppVersion=7.0&tgWebAppPlatform=${platform}`
}

describe('telegramWebApp', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setLocation('', '')
    // @ts-expect-error — чистим глобал между тестами
    delete window.TelegramWebviewProxy
    vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
  })

  afterEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('извлекает tgWebAppData из хеша внутри клиента Telegram', async () => {
    insideTelegramClient()
    setLocation(miniAppHash())
    const { captureTelegramInitData, isTelegramMiniApp } = await loadModule()

    expect(captureTelegramInitData()).toBe(HASH_INIT_DATA)
    expect(isTelegramMiniApp()).toBe(true)
  })

  it('вычищает из адреса только tgWebAppData, оставляя параметры платформы', async () => {
    // Версия и платформа нужны SDK Telegram (lib/telegramViewport) и
    // определению окружения — вычищать хеш целиком нельзя.
    insideTelegramClient()
    setLocation(miniAppHash())
    const { captureTelegramInitData } = await loadModule()

    captureTelegramInitData()

    const url = vi.mocked(window.history.replaceState).mock.calls[0][2] as string
    expect(url).not.toContain('tgWebAppData')
    expect(url).toContain('tgWebAppVersion=7.0')
    expect(url).toContain('tgWebAppPlatform=ios')
    expect(url.startsWith('/dashboard#')).toBe(true)
  })

  it('stripTelegramInitDataFromUrl чистит адрес и без захвата', async () => {
    setLocation(miniAppHash())
    const { stripTelegramInitDataFromUrl } = await loadModule()

    stripTelegramInitDataFromUrl()

    const url = vi.mocked(window.history.replaceState).mock.calls[0][2] as string
    expect(url).not.toContain('tgWebAppData')
  })

  it('stripTelegramInitDataFromUrl не трогает адрес без tgWebAppData', async () => {
    setLocation('#tgWebAppVersion=7.0')
    const { stripTelegramInitDataFromUrl } = await loadModule()

    stripTelegramInitDataFromUrl()

    expect(window.history.replaceState).not.toHaveBeenCalled()
  })

  it('не берёт initData из обычной вкладки браузера', async () => {
    // Ровно тот вектор, ради которого нужна проверка окружения: ссылка,
    // присланная админу, не должна отравлять его вкладку чужими initData.
    setLocation(miniAppHash())
    const { captureTelegramInitData, isTelegramMiniApp } = await loadModule()

    expect(captureTelegramInitData()).toBeNull()
    expect(isTelegramMiniApp()).toBe(false)
  })

  it('не берёт initData из query-строки', async () => {
    insideTelegramClient()
    setLocation('', `?tgWebAppData=${encodeURIComponent(HASH_INIT_DATA)}`)
    const { getTelegramInitData } = await loadModule()

    expect(getTelegramInitData()).toBeNull()
  })

  it('сохраняет initData в sessionStorage и переживает потерю хеша', async () => {
    insideTelegramClient()
    setLocation(miniAppHash())
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
    insideTelegramClient()
    setLocation('#tgWebAppData=&tgWebAppVersion=7.0&tgWebAppPlatform=ios')
    const { isTelegramMiniApp } = await loadModule()
    expect(isTelegramMiniApp()).toBe(false)
  })

  it('во фрейме Telegram Web признаёт окружение по tgWebAppPlatform', async () => {
    const parentSpy = vi.spyOn(window, 'parent', 'get')
    parentSpy.mockReturnValue({} as Window)
    setLocation(miniAppHash(HASH_INIT_DATA, 'weba'))
    const { getTelegramInitData } = await loadModule()

    expect(getTelegramInitData()).toBe(HASH_INIT_DATA)
  })

  it('clearTelegramInitData стирает и память, и sessionStorage', async () => {
    insideTelegramClient()
    setLocation(miniAppHash())
    const mod = await loadModule()
    mod.captureTelegramInitData()

    setLocation('')
    mod.clearTelegramInitData()

    expect(mod.getTelegramInitData()).toBeNull()
    expect(sessionStorage.getItem('rw_tg_init_data')).toBeNull()
  })

  it('переживает недоступный sessionStorage', async () => {
    insideTelegramClient()
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    setLocation(miniAppHash())
    const { getTelegramInitData } = await loadModule()

    expect(getTelegramInitData()).toBe(HASH_INIT_DATA)
    spy.mockRestore()
  })

  it('parseTelegramUser достаёт пользователя для показа в интерфейсе', async () => {
    const { parseTelegramUser } = await loadModule()

    expect(parseTelegramUser(HASH_INIT_DATA)).toEqual({ id: 777, username: 'admin777' })
    expect(parseTelegramUser('auth_date=1&hash=x')).toBeNull()
    expect(parseTelegramUser('user=%7Bnot-json')).toBeNull()
  })
})
