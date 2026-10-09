import {
  memo, useCallback, useMemo, useRef, useState,
  type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import type { MapLayout, Shape } from './geoLayout'
import { areaName, fillFor, intensity, metricOf, type AreaStat, type GeoMetric } from './geoModel'
import type { ZoomPan } from './useZoomPan'

const BORDER = 'hsl(var(--background))'

interface GeoMapProps {
  layout: MapLayout
  metric: GeoMetric
  stats: Map<string, AreaStat>
  selected: string | null
  onSelect: (id: string | null) => void
  zoom: ZoomPan
}

interface Hover {
  id: string
  x: number
  y: number
  /** Ширина карты — подсказка у краёв сдвигается внутрь, а не обрезается */
  width: number
}

export const GeoMap = memo(function GeoMap({ layout, metric, stats, selected, onSelect, zoom }: GeoMapProps) {
  const { t, i18n } = useTranslation()
  const wrapRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<Hover | null>(null)

  const fills = useMemo(() => {
    const max = Math.max(0, ...[...stats.values()].map((s) => metricOf(s, metric)))
    const map = new Map<string, string>()
    for (const s of stats.values()) map.set(s.id, fillFor(intensity(metricOf(s, metric), max)))
    return map
  }, [stats, metric])

  const byId = useMemo(() => new Map(layout.shapes.map((s) => [s.id, s])), [layout])

  // Слои с тысячами вершин не перерисовываются при наведении и зуме
  const areas = useMemo(() => (
    <>
      <g aria-hidden>
        {layout.background.map((d, i) => (
          <path key={i} d={d} fill="hsl(var(--muted) / 0.45)" stroke={BORDER} strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
      <g>
        {layout.shapes.map((s) => (
          <path
            key={s.id}
            d={s.d}
            data-id={s.id}
            style={{ fill: fills.get(s.id) ?? fillFor(0) }}
            stroke={BORDER}
            strokeWidth={0.6}
            vectorEffect="non-scaling-stroke"
            className="cursor-pointer"
          />
        ))}
      </g>
    </>
  ), [layout, fills])

  const onMove = useCallback((e: ReactPointerEvent<SVGSVGElement>) => {
    zoom.handlers.onPointerMove(e)
    if (e.pointerType !== 'mouse') return
    const id = (e.target as Element).getAttribute?.('data-id')
    const rect = wrapRef.current?.getBoundingClientRect()
    if (!id || !rect) {
      setHover(null)
      return
    }
    setHover({ id, x: e.clientX - rect.left, y: e.clientY - rect.top, width: rect.width })
  }, [zoom.handlers])

  const onClick = useCallback((e: ReactMouseEvent<SVGSVGElement>) => {
    if (zoom.wasDrag()) return
    onSelect((e.target as Element).getAttribute?.('data-id') ?? null)
  }, [zoom, onSelect])

  const { k, x, y } = zoom.transform
  // Крошечные области с подключениями (Москва, Берлин, Сингапур) — ещё и кружком, чтобы попасть курсором
  const markers = layout.shapes.filter((s) => s.small && metricOf(stats.get(s.id), metric) > 0)
  const hovered = hover ? byId.get(hover.id) : undefined
  const chosen = selected ? byId.get(selected) : undefined
  const hoverStat = hover ? stats.get(hover.id) : undefined
  const lang = i18n.language

  return (
    <div ref={wrapRef} className="relative overflow-hidden rounded-lg border border-[var(--glass-border)]/50 bg-[var(--glass-bg)]">
      <svg
        ref={zoom.svgRef}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="block w-full h-auto select-none cursor-grab active:cursor-grabbing"
        style={{ touchAction: k > 1 ? 'none' : 'pan-y' }}
        role="img"
        aria-label={t('analytics.geo.map.aria')}
        {...zoom.handlers}
        onPointerMove={onMove}
        onPointerLeave={() => {
          zoom.handlers.onPointerLeave()
          setHover(null)
        }}
        onClick={onClick}
      >
        <g
          style={{
            transform: `translate(${x}px, ${y}px) scale(${k})`,
            transition: zoom.animate ? 'transform 0.25s ease-out' : undefined,
          }}
        >
          {areas}
          {markers.map((s) => (
            <circle
              key={s.id}
              data-id={s.id}
              cx={s.cx}
              cy={s.cy}
              r={5 / k}
              style={{ fill: fills.get(s.id) ?? fillFor(0) }}
              stroke="hsl(var(--foreground) / 0.7)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
              className="cursor-pointer"
            />
          ))}
          {chosen && (
            <Outline shape={chosen} k={k} stroke="hsl(var(--primary))" width={2} />
          )}
          {hovered && hovered !== chosen && (
            <Outline shape={hovered} k={k} stroke="hsl(var(--foreground))" width={1.5} fill={fills.get(hovered.id) ?? fillFor(0)} />
          )}
        </g>
      </svg>

      {hover && hovered && (
        <div
          className="pointer-events-none absolute z-10 whitespace-nowrap rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg-solid)] px-3 py-1 text-xs font-medium text-white shadow-lg"
          style={{
            left: hover.x,
            top: hover.y,
            // У левого края подсказка висит правее курсора, у правого — левее, в середине — по центру
            transform: `translate(${-Math.min(100, Math.max(0, (hover.x / (hover.width || 1)) * 100))}%, ${
              hover.y < 48 ? '18px' : 'calc(-100% - 12px)'})`,
          }}
        >
          {areaName(hover.id, lang, layout.names)}
          <span className="ml-2 text-muted-foreground">
            {hoverStat
              ? `${t('analytics.geo.uniqueUsers', { count: hoverStat.users })} · ${t('analytics.geo.ipsCount', { count: hoverStat.ips, formatted: hoverStat.ips.toLocaleString() })}`
              : t('analytics.geo.map.noConnections')}
          </span>
        </div>
      )}
    </div>
  )
})

/**
 * Контур поверх соседей: у общего пути обводку перекрыли бы соседние области.
 * Под цветной обводкой — тёмная подложка, иначе акцент теряется на заливке того же цвета.
 */
function Outline({ shape, k, stroke, width, fill }: { shape: Shape; k: number; stroke: string; width: number; fill?: string }) {
  const ring = (color: string, w: number) => (
    <>
      <path d={shape.d} fill="none" stroke={color} strokeWidth={w} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {shape.small && (
        <circle cx={shape.cx} cy={shape.cy} r={9 / k} fill="none" stroke={color} strokeWidth={w} vectorEffect="non-scaling-stroke" />
      )}
    </>
  )
  return (
    <g className="pointer-events-none">
      {fill && (
        <path d={shape.d} style={{ fill, filter: 'brightness(1.25) saturate(1.1)' }} stroke="none" />
      )}
      {ring(BORDER, width + 2.5)}
      {ring(stroke, width)}
    </g>
  )
}
