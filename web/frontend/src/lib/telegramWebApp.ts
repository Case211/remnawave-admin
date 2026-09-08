/**
 * Определение Telegram Mini App и извлечение подписанных initData.
 *
 * Внешний SDK (telegram-web-app.js) сознательно не подключается: для входа
 * нужен только параметр `tgWebAppData`, который Telegram кладёт в хеш URL
 * при открытии мини-приложения. Так фронт не тянет сторонний скрипт —
 * ровно та же причина, по которой Login Widget вендорится в public/vendor.
 *
 * Хеш живёт недолго: роутер и любая навигация его затирают, а перезагрузка
 * страницы внутри Telegram может прийти уже без него. Поэтому значение
 * снимается один раз как можно раньше (см. вызов captureTelegramInitData
 * в main.tsx) и кладётся в sessionStorage — так авто-вход переживает
 * перезагрузку вкладки, но не утекает в другие вкладки и сессии.
 */

const STORAGE_KEY = 'rw_tg_init_data'

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

/** Достать tgWebAppData из хеша вида `#tgWebAppData=...&tgWebAppVersion=...`. */
function parseHash(hash: string): string | null {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  if (!raw) return null
  const params = new URLSearchParams(raw)
  const initData = params.get('tgWebAppData')
  return initData && initData.trim() ? initData : null
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

  // Telegram кладёт параметры в хеш; часть клиентов дублирует их в query.
  const fromHash = parseHash(window.location.hash) || parseHash(window.location.search)
  if (fromHash) {
    captured = fromHash
    writeStorage(fromHash)
    return captured
  }

  return null
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
