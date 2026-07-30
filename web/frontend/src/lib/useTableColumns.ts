import { useCallback, useMemo } from 'react'

import { useOrderPreference } from './useOrderPreference'
import { useWidgetVisibility } from './useWidgetVisibility'

export interface TableColumn {
  key: string
  /** i18n-ключ подписи — показывается в меню выбора колонок. */
  labelKey: string
  /** Колонку нельзя скрыть: без неё строка перестаёт читаться (имя, действия). */
  locked?: boolean
  /** Скрыта, пока пользователь сам не включит (иначе таблица сразу широкая). */
  optional?: boolean
}

/**
 * Видимость и порядок колонок таблицы, переживающие перезагрузку.
 *
 * Собран из уже существующих кирпичей: useWidgetVisibility хранит скрытые
 * ключи, useOrderPreference — расстановку. Здесь только склейка и правила
 * колонок (locked нельзя спрятать, optional спрятана по умолчанию), чтобы
 * любая таблица подключалась одной строкой:
 *
 *   const cols = useTableColumns('users', USER_COLUMNS)
 *   cols.visible.map((c) => ...)
 *
 * `storageKey` намеренно включает id таблицы: настройки витрины юзеров и,
 * скажем, списка нод не должны затирать друг друга.
 */
export function useTableColumns(tableId: string, columns: TableColumn[]) {
  const defaultHidden = useMemo(
    () => columns.filter((c) => c.optional && !c.locked).map((c) => c.key),
    [columns],
  )

  const visibility = useWidgetVisibility(`tablecols:${tableId}`, defaultHidden)
  const order = useOrderPreference(`tablecolorder:${tableId}`)

  /** Все колонки в пользовательском порядке; новые попадают в конец. */
  const ordered = useMemo(() => {
    const byKey = new Map(columns.map((c) => [c.key, c]))
    return order
      .applyOrder(columns.map((c) => c.key))
      .map((key) => byKey.get(key))
      .filter((c): c is TableColumn => Boolean(c))
  }, [columns, order])

  const isVisible = useCallback(
    (key: string) => {
      const column = columns.find((c) => c.key === key)
      return column?.locked ? true : visibility.isVisible(key)
    },
    [columns, visibility],
  )

  const visible = useMemo(() => ordered.filter((c) => isVisible(c.key)), [ordered, isVisible])

  const toggle = useCallback(
    (key: string) => {
      const column = columns.find((c) => c.key === key)
      if (column?.locked) return
      visibility.toggle(key)
    },
    [columns, visibility],
  )

  /**
   * Поставить колонку `activeKey` на место `overKey` — то, что нужно
   * перетаскиванию: dnd-kit сообщает ключи, а не индексы.
   */
  const reorder = useCallback(
    (activeKey: string, overKey: string) => {
      if (activeKey === overKey) return
      const keys = ordered.map((c) => c.key)
      const from = keys.indexOf(activeKey)
      const to = keys.indexOf(overKey)
      if (from < 0 || to < 0) return
      const next = [...keys]
      next.splice(from, 1)
      next.splice(to, 0, activeKey)
      order.setCustomOrder(next)
    },
    [ordered, order],
  )

  /** Показать все колонки, включая скрытые по умолчанию (пункт меню столбца). */
  const showAll = useCallback(() => visibility.reset(), [visibility])

  const reset = useCallback(() => {
    // Именно к дефолту: часть колонок скрыта изначально, и «показать всё»
    // сбросом не является.
    visibility.resetToDefaults()
    order.reset()
  }, [visibility, order])

  // «Настроено» — это когда пользователь отклонился от дефолта. Скрытая по
  // умолчанию колонка сама по себе настройкой не считается, иначе кнопка
  // сброса горит активной на свежей таблице.
  const visibilityCustomized = useMemo(() => {
    const defaults = new Set(defaultHidden)
    if (visibility.hidden.size !== defaults.size) return true
    for (const key of visibility.hidden) if (!defaults.has(key)) return true
    return false
  }, [visibility.hidden, defaultHidden])

  return {
    /** Все колонки в текущем порядке — для меню настройки. */
    ordered,
    /** Только показываемые — для отрисовки таблицы. */
    visible,
    isVisible,
    toggle,
    reorder,
    showAll,
    reset,
    isCustomized: visibilityCustomized || order.isCustomized,
  }
}
