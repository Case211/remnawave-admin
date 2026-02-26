import { useSearchParams } from 'react-router-dom'
import { useCallback } from 'react'

/**
 * Persist active tab in URL search params so it survives page refresh.
 * Usage: const [tab, setTab] = useTabParam('all', ['all', 'pending', 'resolved'])
 */
export function useTabParam<T extends string>(
  defaultTab: T,
  validTabs?: T[],
  paramName = 'tab',
): [T, (tab: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const raw = searchParams.get(paramName) as T | null
  const tab = raw && (!validTabs || validTabs.includes(raw)) ? raw : defaultTab

  const setTab = useCallback(
    (value: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (value === defaultTab) {
            next.delete(paramName)
          } else {
            next.set(paramName, value)
          }
          return next
        },
        { replace: true },
      )
    },
    [defaultTab, paramName, setSearchParams],
  )

  return [tab, setTab]
}
