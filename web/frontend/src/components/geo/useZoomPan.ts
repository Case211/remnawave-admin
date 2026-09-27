import {
  useCallback, useEffect, useRef, useState,
  type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent,
} from 'react'

/** Масштаб и сдвиг слоя карты в координатах viewBox */
export interface ZoomState {
  k: number
  x: number
  y: number
}

/** Где на слое что-то нарисовано: [x0, y0, x1, y1] в координатах viewBox, не меньше кадра */
export type Bounds = readonly [number, number, number, number]

export const IDENTITY: ZoomState = { k: 1, x: 0, y: 0 }
export const MAX_ZOOM = 12

/**
 * Карта не уезжает из кадра: край нарисованного не отходит от края кадра.
 * Если что-то нарисовано за кадром (Канары у Испании), до него можно доехать.
 */
export function clampZoom(t: ZoomState, width: number, height: number, bounds?: Bounds): ZoomState {
  const [x0, y0, x1, y1] = bounds ?? [0, 0, width, height]
  const k = Math.min(MAX_ZOOM, Math.max(1, t.k))
  // `|| 0`: без -0 от «-k * 0» — для сравнения состояний и тестов это другое число
  return {
    k,
    x: Math.min(-k * x0, Math.max(width - k * x1, t.x)) || 0,
    y: Math.min(-k * y0, Math.max(height - k * y1, t.y)) || 0,
  }
}

/** Масштаб ×factor с неподвижной точкой (px, py) — точка под курсором остаётся под курсором. */
export function zoomAround(
  t: ZoomState, factor: number, px: number, py: number, width: number, height: number, bounds?: Bounds,
): ZoomState {
  const k = Math.min(MAX_ZOOM, Math.max(1, t.k * factor))
  const ratio = k / t.k
  return clampZoom({ k, x: px - (px - t.x) * ratio, y: py - (py - t.y) * ratio }, width, height, bounds)
}

const same = (a: ZoomState, b: ZoomState) => a.k === b.k && a.x === b.x && a.y === b.y

/** Порог в пикселях экрана: меньше — клик, больше — перетаскивание. */
const DRAG_THRESHOLD = 4

/**
 * Зум и панорама SVG-карты: перетаскивание, щипок двумя пальцами, двойной клик,
 * колесо. Колесо масштабирует с Ctrl/⌘ (и щипок тачпада — это тоже Ctrl+колесо)
 * или после клика по карте; иначе листает страницу — карта не ловит прокрутку
 * длинной страницы аналитики.
 */
export function useZoomPan(width: number, height: number, frame = '', bounds?: Bounds) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [transform, setTransform] = useState<ZoomState>(IDENTITY)
  // Плавность только у кнопок: при перетаскивании анимация отстаёт от пальца
  const [animate, setAnimate] = useState(false)
  const current = useRef(transform)
  current.current = transform

  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const origin = useRef({ x: 0, y: 0 })
  const dragged = useRef(false)
  // С карты кликнули и курсор ещё на ней — колесо масштабирует и без Ctrl
  const engaged = useRef(false)

  const apply = useCallback((next: ZoomState, smooth = false) => {
    if (same(next, current.current)) return
    current.current = next
    setAnimate(smooth)
    setTransform(next)
  }, [])

  /** Экранная точка → координаты viewBox; и сколько единиц viewBox в пикселе. */
  const toView = useCallback((clientX: number, clientY: number): [number, number, number] => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || !rect.width || !rect.height) return [width / 2, height / 2, 1]
    const scale = width / rect.width
    return [(clientX - rect.left) * scale, (clientY - rect.top) * scale, scale]
  }, [width, height])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      const pinch = e.ctrlKey || e.metaKey
      if (!pinch && !engaged.current) return
      const [px, py] = toView(e.clientX, e.clientY)
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.002))
      const next = zoomAround(current.current, factor, px, py, width, height, bounds)
      // Упёрлись в предел масштаба — прокрутка уходит странице (Ctrl+колесо — нет: иначе зум всей страницы)
      if (!pinch && same(next, current.current)) return
      e.preventDefault()
      apply(next)
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [toView, apply, width, height, bounds])

  // Другой вид (мир, другая страна) — новый кадр
  useEffect(() => {
    current.current = IDENTITY
    setAnimate(false)
    setTransform(IDENTITY)
  }, [width, height, frame, bounds])

  const onPointerDown = useCallback((e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    engaged.current = true
    // Мышь одна: запись от нажатия, отпущенного за картой, не должна мешать новому
    if (e.pointerType === 'mouse' || pointers.current.size === 0) {
      pointers.current.clear()
      origin.current = { x: e.clientX, y: e.clientY }
      dragged.current = false
    }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }, [])

  const onPointerMove = useCallback((e: ReactPointerEvent<SVGSVGElement>) => {
    const prev = pointers.current.get(e.pointerId)
    if (!prev) return
    // Кнопку отпустили за картой — pointerup сюда не пришёл
    if (e.pointerType !== 'touch' && e.buttons === 0) {
      pointers.current.delete(e.pointerId)
      return
    }
    const next = { x: e.clientX, y: e.clientY }
    const t = current.current

    if (pointers.current.size === 1) {
      // До порога позиция не обновляется: первый шаг сдвига заберёт всё смещение
      if (!dragged.current && Math.hypot(next.x - origin.current.x, next.y - origin.current.y) < DRAG_THRESHOLD) return
      if (!dragged.current) {
        dragged.current = true
        // Захват только после начала перетаскивания: иначе клик по области
        // ушёл бы самому <svg>, а не пути под курсором
        e.currentTarget.setPointerCapture(e.pointerId)
      }
      pointers.current.set(e.pointerId, next)
      const [, , scale] = toView(e.clientX, e.clientY)
      apply(clampZoom({ k: t.k, x: t.x + (next.x - prev.x) * scale, y: t.y + (next.y - prev.y) * scale }, width, height, bounds))
      return
    }

    // Щипок: масштаб по расстоянию между пальцами, сдвиг — по их середине
    const other = [...pointers.current.entries()].find(([id]) => id !== e.pointerId)?.[1]
    pointers.current.set(e.pointerId, next)
    if (!other) return
    dragged.current = true
    const before = Math.hypot(prev.x - other.x, prev.y - other.y)
    const after = Math.hypot(next.x - other.x, next.y - other.y)
    if (!before) return
    const [px, py, scale] = toView((next.x + other.x) / 2, (next.y + other.y) / 2)
    const zoomed = zoomAround(t, after / before, px, py, width, height, bounds)
    apply(clampZoom({
      ...zoomed,
      x: zoomed.x + ((next.x - prev.x) / 2) * scale,
      y: zoomed.y + ((next.y - prev.y) / 2) * scale,
    }, width, height, bounds))
  }, [toView, apply, width, height, bounds])

  const onPointerUp = useCallback((e: ReactPointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId)
  }, [])

  const onPointerLeave = useCallback(() => {
    if (pointers.current.size === 0) engaged.current = false
  }, [])

  const onDoubleClick = useCallback((e: ReactMouseEvent<SVGSVGElement>) => {
    const [px, py] = toView(e.clientX, e.clientY)
    apply(zoomAround(current.current, 2, px, py, width, height, bounds), true)
  }, [toView, apply, width, height, bounds])

  const zoomBy = useCallback((factor: number) => {
    apply(zoomAround(current.current, factor, width / 2, height / 2, width, height, bounds), true)
  }, [apply, width, height, bounds])

  const reset = useCallback(() => apply(IDENTITY, true), [apply])

  /** Точка слоя за кадром (регион выбрали из списка) — сдвинуть кадр к ней. */
  const reveal = useCallback((cx: number, cy: number) => {
    const t = current.current
    const sx = t.x + t.k * cx
    const sy = t.y + t.k * cy
    if (sx >= 0 && sx <= width && sy >= 0 && sy <= height) return
    apply(clampZoom({ k: t.k, x: width / 2 - t.k * cx, y: height / 2 - t.k * cy }, width, height, bounds), true)
  }, [apply, width, height, bounds])

  /** Было ли последнее нажатие перетаскиванием — тогда клик не выбирает область. */
  const wasDrag = useCallback(() => dragged.current, [])

  return {
    svgRef,
    transform,
    animate,
    zoomBy,
    reset,
    reveal,
    wasDrag,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
      onPointerLeave,
      onDoubleClick,
    },
  }
}

export type ZoomPan = ReturnType<typeof useZoomPan>
