/**
 * Определение Telegram Mini App и извлечение подписанных initData.
 *
 * Внешний SDK для входа сознательно не используется: нужен только параметр
 * `tgWebAppData`, который Telegram кладёт в хеш URL при открытии
 * мини-приложения. Вендоренный telegram-web-app.js (см. lib/telegramViewport)
 * отвечает только за раскладку и в критическом пути входа не участвует.
 *
 * Хеш живёт недолго: роутер и любая навигация его затирают, а перезагрузка
 * страницы внутри Telegram может прийти уже без него. Поэтому значение
 * снимается один раз как можно раньше (см. вызов captureTelegramInitData
 * в main.tsx) и кладётся в sessionStorage — так авто-вход переживает
 * перезагрузку вкладки, но не утекает в другие вкладки и сессии.
 *
 * Безопасность: initData — это учётные данные, действительные сутки, поэтому
 * снимаем их только внутри настоящего клиента Telegram и только из хеша.
 * Иначе ссылка вида `https://panel/users#tgWebAppData=...`, присланная
 * администратору, отравляла бы его вкладку чужими учётными данными и при
 * следующем истечении сессии молча логинила бы его в аккаунт отправителя
 * (login CSRF / фиксация сессии). Из query-строки не читаем вовсе: Telegram
 * туда ничего не кладёт, а вот в логи прокси и заголовок Referer попало бы.
 * Захваченный хеш сразу вычищаем из адреса — чтобы он не осел в истории.
 */

const STORAGE_KEY = 'rw_tg_init_data'

interface TelegramWebViewGlobals {
  TelegramWebviewProxy?: unknown
  TelegramWebviewProxyProto?: unknown
  external?: { notify?: unknown }
}

export interface TelegramMiniAppUser {
  id: number
  username?: string
  first_name?: string
  last_name?: string
}

let captured: string | null = null

function readStorage(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStorage(value: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Приватный режим / переполненное хранилище — работаем из памяти
  }
}

/**
 * Запущены ли мы внутри клиента Telegram.
 *
 * Мобильные клиенты и Telegram Desktop прокидывают в WebView мост
 * (`TelegramWebviewProxy`, на Windows — `external.notify`). Telegram Web
 * открывает мини-апп во фрейме, там моста нет — признаком служит сам фрейм
 * вместе с параметрами платформы в хеше. Чужой сайт тоже может обернуть
 * панель во фрейм, но в стороннем фрейме браузер не отдаёт куки сессии
 * (SameSite=Lax), так что подменить личность в рабочей вкладке админа этим
 * нельзя — а верхнеуровневая вкладка обычного браузера сюда не попадает.
 */
export function isTelegramEnvironment(): boolean {
  if (typeof window === 'undefined') return false

  const w = window as Window & TelegramWebViewGlobals
  if (w.TelegramWebviewProxy || w.TelegramWebviewProxyProto) return true
  if (typeof w.external?.notify === 'function') return true

  const inFrame = window.parent !== window
  return inFrame && Boolean(hashParams().get('tgWebAppPlatform'))
}

function hashParams(): URLSearchParams {
  const raw = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  return new URLSearchParams(raw)
}

/**
 * Убрать из адреса только `tgWebAppData` — сами учётные данные.
 *
 * Остальные tgWebApp-параметры (версия, платформа, тема) остаются: по ним
 * работает определение окружения, и их читает при загрузке официальный SDK
 * (см. lib/telegramViewport) — вычистив хеш целиком, мы сломали бы отступы
 * в Telegram Web.
 */
export function stripTelegramInitDataFromUrl(): void {
  if (typeof window === 'undefined') return

  const params = hashParams()
  if (!params.has('tgWebAppData')) return
  params.delete('tgWebAppData')

  const rest = params.toString()
  const url = window.location.pathname + window.location.search + (rest ? `#${rest}` : '')
  try {
    window.history.replaceState(null, '', url)
  } catch {
    // Ignore — адрес останется как есть, на работу это не влияет
  }
}

/**
 * Снять initData из текущего URL и запомнить на время вкладки.
 * Идемпотентна: повторные вызовы не затирают уже снятое значение.
 */
export function captureTelegramInitData(): string | null {
  if (captured) return captured

  const fromStorage = readStorage()
  if (fromStorage) {
    captured = fromStorage
    return captured
  }

  if (typeof window === 'undefined') return null
  if (!isTelegramEnvironment()) return null

  const initData = hashParams().get('tgWebAppData')
  if (!initData || !initData.trim()) return null

  captured = initData
  writeStorage(initData)
  stripTelegramInitDataFromUrl()
  return captured
}

/** Подписанные initData текущего мини-приложения либо null. */
export function getTelegramInitData(): string | null {
  return captured ?? captureTelegramInitData()
}

/** Открыта ли панель внутри Telegram Mini App. */
export function isTelegramMiniApp(): boolean {
  return Boolean(getTelegramInitData())
}

/**
 * Пользователь из initData — только для показа в интерфейсе.
 * Подпись здесь не проверяется: кто вошёл на самом деле, решает сервер.
 */
export function parseTelegramUser(initData: string): TelegramMiniAppUser | null {
  try {
    const raw = new URLSearchParams(initData).get('user')
    if (!raw) return null
    const user = JSON.parse(raw) as TelegramMiniAppUser
    return typeof user?.id === 'number' ? user : null
  } catch {
    return null
  }
}

/**
 * Забыть initData — вызывается при выходе, чтобы «Выйти» внутри мини-аппа
 * не приводил к мгновенному авто-входу обратно.
 */
export function clearTelegramInitData(): void {
  captured = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Ignore
  }
}
