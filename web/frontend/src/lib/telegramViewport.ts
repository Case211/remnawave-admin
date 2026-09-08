/**
 * Раскладка панели внутри Telegram Mini App.
 *
 * В полноэкранном режиме клиент Telegram рисует свои кнопки («Закрыть»,
 * «свернуть», «···») ПОВЕРХ страницы, внутри вьюпорта. `env(safe-area-inset-*)`
 * про них ничего не знает — их высоту отдаёт только сам Telegram, через
 * события `safeAreaChanged` / `contentSafeAreaChanged` (Bot API 8.0). Поэтому
 * здесь подключается официальный telegram-web-app.js: он выставляет на
 * :root переменные `--tg-safe-area-inset-*`, `--tg-content-safe-area-inset-*`
 * и `--tg-viewport-stable-height`, а вёрстка живёт по ним (см. index.css,
 * секция «Telegram Mini App»).
 *
 * Скрипт вендорится в public/vendor — как и telegram-widget.js, чтобы не
 * зависеть от CDN Telegram. В критическом пути входа он не участвует:
 * авторизация читает initData сама (см. lib/telegramWebApp), так что
 * незагрузившийся SDK ломает максимум отступы, но не вход.
 *
 * Вне Telegram не загружается вовсе — обычный браузер не платит за него.
 */
import { isTelegramEnvironment } from './telegramWebApp'

interface TelegramWebApp {
  ready: () => void
  isFullscreen?: boolean
  onEvent: (event: string, handler: () => void) => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

// ?v= — cache-busting: при обновлении вендоренной копии поднять версию,
// иначе браузеры и прокси держат старый скрипт в кэше.
const SDK_PATH = '/vendor/telegram-web-app.js?v=8.0'

const MINIAPP_CLASS = 'tg-miniapp'
const FULLSCREEN_CLASS = 'tg-fullscreen'

let started = false

/** Путь к вендоренному скрипту с учётом секретного префикса панели. */
function sdkUrl(): string {
  const secretPath = window.__ENV?.SECRET_PATH || ''
  const prefix = secretPath ? `/${secretPath.replace(/^\/|\/$/g, '')}` : ''
  return `${prefix}${SDK_PATH}`
}

function syncFullscreenClass(webApp: TelegramWebApp): void {
  document.documentElement.classList.toggle(
    FULLSCREEN_CLASS,
    Boolean(webApp.isFullscreen),
  )
}

function attach(): void {
  const webApp = window.Telegram?.WebApp
  if (!webApp) return

  webApp.ready()
  syncFullscreenClass(webApp)

  // Кнопки клиента и высота вьюпорта меняются на лету: разворот экрана,
  // вход и выход из полноэкранного режима, появление клавиатуры.
  const resync = () => syncFullscreenClass(webApp)
  for (const event of ['fullscreenChanged', 'viewportChanged', 'safeAreaChanged',
    'contentSafeAreaChanged']) {
    try {
      webApp.onEvent(event, resync)
    } catch {
      // Старый клиент не знает события — отступы просто останутся нулевыми
    }
  }
}

/**
 * Подключить SDK и включить режим мини-аппа для вёрстки.
 * Идемпотентна; вне Telegram ничего не делает.
 */
export function initTelegramViewport(): void {
  if (started || typeof window === 'undefined') return
  if (!isTelegramEnvironment()) return
  started = true

  // Класс ставим сразу: переменные Telegram имеют запасные нули, поэтому
  // раскладка корректна и до того, как скрипт догрузится.
  document.documentElement.classList.add(MINIAPP_CLASS)

  if (window.Telegram?.WebApp) {
    attach()
    return
  }

  const script = document.createElement('script')
  script.src = sdkUrl()
  script.async = true
  script.onload = attach
  script.onerror = () => {
    // Без SDK остаются нулевые отступы — панель работает, просто в
    // полноэкранном режиме шапка может уйти под кнопки Telegram.
    document.documentElement.classList.remove(MINIAPP_CLASS)
  }
  document.head.appendChild(script)
}
