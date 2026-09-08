import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

async function loadModule() {
  vi.resetModules()
  return import('@/lib/telegramViewport')
}

function setHash(hash: string) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, hash, search: '', pathname: '/dashboard' },
  })
}

function insideTelegramClient() {
  Object.defineProperty(window, 'TelegramWebviewProxy', {
    configurable: true,
    value: { postEvent: () => {} },
  })
}

describe('telegramViewport', () => {
  beforeEach(() => {
    setHash('')
    document.documentElement.className = ''
    document.head.querySelectorAll('script').forEach((s) => s.remove())
    // @ts-expect-error — чистим глобалы между тестами
    delete window.TelegramWebviewProxy
    delete window.Telegram
    window.__ENV = {}
  })

  afterEach(() => {
    document.documentElement.className = ''
    window.__ENV = {}
  })

  it('вне Telegram не грузит SDK и не трогает разметку', async () => {
    const { initTelegramViewport } = await loadModule()

    initTelegramViewport()

    expect(document.documentElement.classList.contains('tg-miniapp')).toBe(false)
    expect(document.head.querySelector('script')).toBeNull()
  })

  it('внутри Telegram ставит класс и подключает вендоренный SDK', async () => {
    insideTelegramClient()
    const { initTelegramViewport } = await loadModule()

    initTelegramViewport()

    expect(document.documentElement.classList.contains('tg-miniapp')).toBe(true)
    const script = document.head.querySelector('script')
    expect(script?.getAttribute('src')).toBe('/vendor/telegram-web-app.js?v=8.0')
  })

  it('учитывает секретный префикс панели в пути к SDK', async () => {
    insideTelegramClient()
    window.__ENV = { SECRET_PATH: '/s3cret/' }
    const { initTelegramViewport } = await loadModule()

    initTelegramViewport()

    expect(document.head.querySelector('script')?.getAttribute('src')).toBe(
      '/s3cret/vendor/telegram-web-app.js?v=8.0',
    )
  })

  it('после загрузки SDK помечает полноэкранный режим и подписывается на события', async () => {
    insideTelegramClient()
    const onEvent = vi.fn()
    const ready = vi.fn()
    window.Telegram = { WebApp: { ready, isFullscreen: true, onEvent } }

    const { initTelegramViewport } = await loadModule()
    initTelegramViewport()

    expect(ready).toHaveBeenCalled()
    expect(document.documentElement.classList.contains('tg-fullscreen')).toBe(true)
    expect(onEvent.mock.calls.map((c) => c[0])).toEqual([
      'fullscreenChanged',
      'viewportChanged',
      'safeAreaChanged',
      'contentSafeAreaChanged',
    ])
  })

  it('не помечает fullscreen, когда мини-апп открыт обычным листом', async () => {
    insideTelegramClient()
    window.Telegram = { WebApp: { ready: vi.fn(), isFullscreen: false, onEvent: vi.fn() } }

    const { initTelegramViewport } = await loadModule()
    initTelegramViewport()

    expect(document.documentElement.classList.contains('tg-fullscreen')).toBe(false)
  })

  it('не загружает SDK повторно', async () => {
    insideTelegramClient()
    const { initTelegramViewport } = await loadModule()

    initTelegramViewport()
    initTelegramViewport()

    expect(document.head.querySelectorAll('script')).toHaveLength(1)
  })

  it('снимает режим мини-аппа, если SDK не загрузился', async () => {
    insideTelegramClient()
    const { initTelegramViewport } = await loadModule()

    initTelegramViewport()
    const script = document.head.querySelector('script') as HTMLScriptElement
    script.onerror?.(new Event('error'))

    expect(document.documentElement.classList.contains('tg-miniapp')).toBe(false)
  })
})
