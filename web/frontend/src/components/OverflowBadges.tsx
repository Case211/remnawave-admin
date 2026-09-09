import { useLayoutEffect, useRef, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** gap-1 между бейджами, в пикселях */
const GAP = 4

interface OverflowBadgesProps {
  items: string[]
  /** Подпись хвоста по числу спрятанных бейджей: «… ещё 3» */
  more: (hidden: number) => string
  className?: string
}

/**
 * Ряд бейджей в одну строку: показываем столько, сколько влезает по ширине
 * контейнера, остальное сворачиваем в бейдж «… ещё N» с полным списком в title.
 *
 * Ширины бейджей меряем один раз и кэшируем по подписи: спрятанных бейджей в
 * DOM нет, а раскладка считается заново на каждый ресайз контейнера.
 */
export function OverflowBadges({ items, more, className }: OverflowBadgesProps) {
  const ref = useRef<HTMLDivElement>(null)
  const widths = useRef(new Map<string, number>())
  const [visible, setVisible] = useState(items.length)

  const fit = () => {
    const el = ref.current
    if (!el) return
    for (const badge of el.querySelectorAll<HTMLElement>('[data-item]')) {
      if (badge.offsetWidth) widths.current.set(badge.dataset.item ?? '', badge.offsetWidth)
    }
    // Ширина известна не для всех — показываем всё, после рендера перемерим
    if (items.some((it) => !widths.current.has(it))) {
      setVisible(items.length)
      return
    }
    const total = el.clientWidth
    if (!total) return
    const tail = el.querySelector<HTMLElement>('[data-probe]')?.offsetWidth ?? 0
    let used = 0
    let n = items.length
    for (let i = 0; i < items.length; i++) {
      const withItem = used + (i ? GAP : 0) + (widths.current.get(items[i]) ?? 0)
      const rest = items.length - i - 1
      if (withItem + (rest ? GAP + tail : 0) > total) {
        n = i
        break
      }
      used = withItem
    }
    // Хотя бы один бейдж показываем всегда, пусть и обрезанный
    setVisible(Math.max(1, n))
  }
  const fitRef = useRef(fit)
  fitRef.current = fit

  useLayoutEffect(fit)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(() => fitRef.current())
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const shown = items.slice(0, visible)
  const hidden = items.slice(visible)

  return (
    <div
      ref={ref}
      data-badges-root
      className={cn('relative flex items-center gap-1 overflow-hidden whitespace-nowrap', className)}
    >
      {shown.map((item, i) => (
        <Badge key={`${item}-${i}`} data-item={item} variant="outline" className="min-w-0 shrink-0 max-w-full">
          <span className="truncate">{item}</span>
        </Badge>
      ))}
      {hidden.length > 0 && (
        <Badge data-tail variant="secondary" className="shrink-0" title={hidden.join(', ')}>
          {more(hidden.length)}
        </Badge>
      )}
      <Badge data-probe aria-hidden="true" variant="secondary" className="absolute invisible pointer-events-none">
        {more(items.length)}
      </Badge>
    </div>
  )
}
