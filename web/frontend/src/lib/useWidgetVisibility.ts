import { useCallback, useState } from 'react'

/**
 * Хранит скрытые виджеты дашборда в localStorage (по умолчанию все видимы).
 * Возвращает helpers для проверки/переключения видимости.
 */
export function useWidgetVisibility(storageKey: string, defaultHidden: string[] = []) {
  const [hidden, setHiddenState] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      // нет сохранённого выбора -> дефолтно-скрытые (напр. новые виджеты)
      if (!raw) return new Set(defaultHidden)
      const parsed = JSON.parse(raw)
      return new Set(Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : [])
    } catch {
      return new Set(defaultHidden)
    }
  })

  const persist = useCallback((next: Set<string>) => {
    setHiddenState(next)
    try {
      if (next.size === 0) localStorage.removeItem(storageKey)
      else localStorage.setItem(storageKey, JSON.stringify([...next]))
    } catch {
      /* quota/disabled — ignore */
    }
  }, [storageKey])

  const isVisible = useCallback((id: string) => !hidden.has(id), [hidden])

  const toggle = useCallback((id: string) => {
    const next = new Set(hidden)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    persist(next)
  }, [hidden, persist])

  const reset = useCallback(() => persist(new Set()), [persist])

  /**
   * Вернуть дефолтный набор скрытых, а не «показать всё»: там, где часть
   * элементов спрятана по умолчанию (необязательные колонки таблиц),
   * обычный reset делал их видимыми — это не сброс, а другая настройка.
   */
  const resetToDefaults = useCallback(
    () => persist(new Set(defaultHidden)),
    [persist, defaultHidden],
  )

  return { hidden, isVisible, toggle, reset, resetToDefaults, isCustomized: hidden.size > 0 }
}
