import { useCallback, useMemo, useState } from 'react'

import {
  isNavGroup,
  isNavSection,
  type NavGroup,
  type NavigationEntry,
} from '@/components/layout/navigation'

export const SIDEBAR_ORDER_KEY = 'remnawave-sidebar-order'

const SECTION_PREFIX = 'section:'

/**
 * Пользовательская расстановка меню.
 *
 * `top` — ключи верхнего уровня (секции, пункты, группы) в нужном порядке;
 * `groups` — порядок подпунктов внутри каждой раскрывающейся группы, по её
 * ключу. Пустой объект означает «всё по умолчанию».
 */
export interface SidebarOrder {
  top: string[]
  groups: Record<string, string[]>
}

export const EMPTY_ORDER: SidebarOrder = { top: [], groups: {} }

/**
 * Стабильный ключ записи меню. Пункты опознаются по маршруту, а не по
 * подписи: подпись переводится и меняется, маршрут — нет.
 */
export function entryKey(entry: NavigationEntry): string {
  if (isNavSection(entry)) return `${SECTION_PREFIX}${entry.name}`
  if (isNavGroup(entry)) return `group:${entry.name}`
  return `item:${entry.href}`
}

export function isSectionKey(key: string): boolean {
  return key.startsWith(SECTION_PREFIX)
}

/**
 * Наложить сохранённый порядок на актуальный список ключей.
 *
 * Исчезнувшее (выключенный плагин, отобранное право) выпадает само, а вот
 * появившееся нельзя просто дописать в конец: новый пункт уехал бы под все
 * секции и остался бы без заголовка. Поэтому новичок встаёт сразу за своим
 * соседом слева из списка по умолчанию — то есть внутрь родной секции.
 */
export function mergeOrder(current: string[], saved: string[]): string[] {
  if (saved.length === 0) return [...current]

  const known = new Set(current)
  const placed = new Set<string>()
  const result: string[] = []
  for (const key of saved) {
    if (known.has(key) && !placed.has(key)) {
      result.push(key)
      placed.add(key)
    }
  }

  for (let i = 0; i < current.length; i++) {
    const key = current[i]
    if (placed.has(key)) continue
    // Ближайший предшественник, который уже занял своё место. Идём по
    // исходному списку слева направо, поэтому только что вставленный новичок
    // сам становится якорем для следующего — цепочка новых пунктов не
    // рассыпается.
    let anchor = -1
    for (let j = i - 1; j >= 0; j--) {
      const at = result.indexOf(current[j])
      if (at >= 0) {
        anchor = at
        break
      }
    }
    result.splice(anchor + 1, 0, key)
    placed.add(key)
  }

  return result
}

/**
 * Разрезать плоский список на блоки «заголовок секции + всё до следующего
 * заголовка». Пункты, оказавшиеся выше первой секции, образуют свой блок
 * без заголовка — так меню умеет держать «избранное» над всеми секциями.
 */
export function splitBlocks(keys: string[]): string[][] {
  const blocks: string[][] = []
  let current: string[] = []
  blocks.push(current)
  for (const key of keys) {
    if (isSectionKey(key)) {
      current = [key]
      blocks.push(current)
    } else {
      current.push(key)
    }
  }
  return blocks.filter((block) => block.length > 0)
}

/**
 * Поставить запись `activeKey` на место `overKey`.
 *
 * Секция переезжает вместе со своими пунктами: тащить заголовок отдельно от
 * содержимого бессмысленно — он бы просто разрезал чужую секцию пополам.
 * Обычный пункт двигается сам по себе и может уйти в любую другую секцию.
 */
export function moveTopLevel(keys: string[], activeKey: string, overKey: string): string[] {
  if (activeKey === overKey) return keys

  if (isSectionKey(activeKey)) {
    const blocks = splitBlocks(keys)
    const from = blocks.findIndex((block) => block[0] === activeKey)
    const to = blocks.findIndex((block) => block.includes(overKey))
    if (from < 0 || to < 0 || from === to) return keys
    const next = [...blocks]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    return next.flat()
  }

  const from = keys.indexOf(activeKey)
  const to = keys.indexOf(overKey)
  if (from < 0 || to < 0) return keys
  const next = [...keys]
  next.splice(from, 1)
  next.splice(to, 0, activeKey)
  return next
}

/** Пересобрать меню по сохранённому порядку — верхний уровень и группы. */
export function applySidebarOrder(
  entries: NavigationEntry[],
  order: SidebarOrder,
): NavigationEntry[] {
  const byKey = new Map(entries.map((entry) => [entryKey(entry), entry]))
  const ordered = mergeOrder(entries.map(entryKey), order.top)

  const result: NavigationEntry[] = []
  for (const key of ordered) {
    const entry = byKey.get(key)
    if (!entry) continue
    if (!isNavGroup(entry)) {
      result.push(entry)
      continue
    }
    const saved = order.groups[key]
    if (!saved || saved.length === 0) {
      result.push(entry)
      continue
    }
    const byHref = new Map(entry.items.map((item) => [item.href, item]))
    const items = mergeOrder(entry.items.map((item) => item.href), saved)
      .map((href) => byHref.get(href))
      .filter((item): item is NavGroup['items'][number] => Boolean(item))
    result.push({ ...entry, items })
  }
  return result
}

function loadOrder(): SidebarOrder {
  try {
    const raw = localStorage.getItem(SIDEBAR_ORDER_KEY)
    if (!raw) return EMPTY_ORDER
    const parsed = JSON.parse(raw) as Partial<SidebarOrder>
    const top = Array.isArray(parsed.top)
      ? parsed.top.filter((key): key is string => typeof key === 'string')
      : []
    const groups: Record<string, string[]> = {}
    if (parsed.groups && typeof parsed.groups === 'object') {
      for (const [group, items] of Object.entries(parsed.groups)) {
        if (Array.isArray(items)) {
          groups[group] = items.filter((key): key is string => typeof key === 'string')
        }
      }
    }
    return { top, groups }
  } catch {
    return EMPTY_ORDER
  }
}

/**
 * Порядок пунктов бокового меню, переживающий перезагрузку.
 *
 * Хранится в браузере, а не на сервере: это личная привычка смотреть, а не
 * настройка панели — ровно как тема, плотность вёрстки и набор колонок в
 * таблицах рядом.
 */
export function useSidebarOrder() {
  const [order, setOrder] = useState<SidebarOrder>(loadOrder)

  const persist = useCallback((next: SidebarOrder) => {
    setOrder(next)
    try {
      if (next.top.length === 0 && Object.keys(next.groups).length === 0) {
        localStorage.removeItem(SIDEBAR_ORDER_KEY)
      } else {
        localStorage.setItem(SIDEBAR_ORDER_KEY, JSON.stringify(next))
      }
    } catch {
      /* приватный режим или переполненное хранилище — не повод падать */
    }
  }, [])

  /**
   * `keys` — полный текущий порядок верхнего уровня, включая невидимые по
   * правам записи: сохраняем расстановку целиком, иначе соседи, которых этот
   * админ не видит, теряли бы своё место.
   */
  const moveTop = useCallback(
    (keys: string[], activeKey: string, overKey: string) => {
      const next = moveTopLevel(keys, activeKey, overKey)
      if (next === keys) return
      persist({ ...order, top: next })
    },
    [order, persist],
  )

  const moveInGroup = useCallback(
    (groupKey: string, hrefs: string[], activeHref: string, overHref: string) => {
      const from = hrefs.indexOf(activeHref)
      const to = hrefs.indexOf(overHref)
      if (from < 0 || to < 0 || from === to) return
      const next = [...hrefs]
      next.splice(from, 1)
      next.splice(to, 0, activeHref)
      persist({ ...order, groups: { ...order.groups, [groupKey]: next } })
    },
    [order, persist],
  )

  const reset = useCallback(() => persist(EMPTY_ORDER), [persist])

  const isCustomized = useMemo(
    () => order.top.length > 0 || Object.keys(order.groups).length > 0,
    [order],
  )

  return { order, moveTop, moveInGroup, reset, isCustomized }
}
