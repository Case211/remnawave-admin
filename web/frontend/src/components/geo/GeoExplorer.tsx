import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { GeoData } from '@/api/advancedAnalytics'
import { Minus, Plus, RotateCcw } from '@/components/brand/icons'
import { countryFlag } from '@/components/nodes/nodeShared'
import {
  Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { GeoMap } from './GeoMap'
import { GeoPanel } from './GeoPanel'
import { useMapLayout } from './geoLayout'
import {
  REGION_MAP_COUNTRIES, WORLD, countryName, defaultView, legendGradient, metricOf, parseView, statsFor,
  type GeoMetric, type GeoView,
} from './geoModel'
import { useZoomPan } from './useZoomPan'

interface GeoExplorerProps {
  data: GeoData
  /** Вид из URL: 'world', код страны или пусто — выбрать по данным */
  view: string
  onViewChange: (view: GeoView) => void
  metric: GeoMetric
  onMetricChange: (metric: GeoMetric) => void
}

/**
 * Векторная карта подключений: страны мира или регионы выбранной страны,
 * заливка по числу юзеров или адресов, наведение — подсказка, клик — карточка
 * справа. Геометрия своя (Natural Earth), без тайлов и внешних сервисов.
 */
export default function GeoExplorer({ data, view: rawView, onViewChange, metric, onMetricChange }: GeoExplorerProps) {
  const { t } = useTranslation()
  // Вид по умолчанию выбирается один раз: данные обновляются каждую минуту,
  // и карта не должна прыгать между страной и миром, пока на неё смотрят
  const fallback = useRef<GeoView>()
  if (!fallback.current && data.countries.length > 0) fallback.current = defaultView(data.countries)
  const view = parseView(rawView, data.countries, fallback.current)
  const [selected, setSelected] = useState<string | null>(null)
  const { layout, failed } = useMapLayout(view)
  const zoom = useZoomPan(layout?.width ?? 1000, layout?.height ?? 500, view, layout?.bounds)

  const stats = useMemo(
    () => statsFor(view, data.countries, data.regions ?? []),
    [view, data.countries, data.regions],
  )
  const max = useMemo(() => Math.max(0, ...[...stats.values()].map((s) => metricOf(s, metric))), [stats, metric])

  useEffect(() => setSelected(null), [view])

  useEffect(() => {
    if (!selected) return
    // Escape, которым закрыли список стран или другое всплывающее окно, выбор не сбрасывает
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !e.defaultPrevented && setSelected(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected])

  // Регион выбрали в списке, а он за кадром (Канары, Азоры) — подвинуть карту к нему
  const { reveal } = zoom
  useEffect(() => {
    const shape = selected ? layout?.shapes.find((s) => s.id === selected) : undefined
    if (shape) reveal(shape.cx, shape.cy)
  }, [selected, layout, reveal])

  const openCountry = useCallback((code: string) => onViewChange(code), [onViewChange])

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.75fr)_minmax(280px,1fr)]">
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg bg-[var(--glass-bg)] p-0.5">
            <SegmentButton active={view === WORLD} onClick={() => onViewChange(WORLD)}>
              {t('analytics.geo.map.world')}
            </SegmentButton>
            <CountryPicker data={data} view={view} onChange={openCountry} />
          </div>
          <div className="flex items-center gap-1 rounded-lg bg-[var(--glass-bg)] p-0.5">
            <SegmentButton active={metric === 'users'} onClick={() => onMetricChange('users')}>
              {t('analytics.geo.map.metricUsers')}
            </SegmentButton>
            <SegmentButton active={metric === 'ips'} onClick={() => onMetricChange('ips')}>
              {t('analytics.geo.map.metricIps')}
            </SegmentButton>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <ZoomButton label={t('analytics.geo.map.zoomOut')} onClick={() => zoom.zoomBy(1 / 1.6)} disabled={zoom.transform.k <= 1}>
              <Minus className="h-3.5 w-3.5" />
            </ZoomButton>
            <span className="w-11 text-center font-mono text-[11px] tabular-nums text-muted-foreground">
              {Math.round(zoom.transform.k * 100)}%
            </span>
            <ZoomButton label={t('analytics.geo.map.zoomIn')} onClick={() => zoom.zoomBy(1.6)}>
              <Plus className="h-3.5 w-3.5" />
            </ZoomButton>
            <ZoomButton label={t('analytics.geo.map.reset')} onClick={zoom.reset} disabled={zoom.transform.k <= 1}>
              <RotateCcw className="h-3.5 w-3.5" />
            </ZoomButton>
          </div>
        </div>

        {layout ? (
          <GeoMap layout={layout} metric={metric} stats={stats} selected={selected} onSelect={setSelected} zoom={zoom} />
        ) : failed ? (
          <div className="flex aspect-[2/1] items-center justify-center rounded-lg border border-[var(--glass-border)]/50 text-xs text-muted-foreground">
            {t('analytics.geo.map.loadFailed')}
          </div>
        ) : (
          <Skeleton className="aspect-[2/1] w-full rounded-lg" />
        )}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {max > 0 && (
            <span className="inline-flex items-center gap-1.5">
              1
              <span className="h-2 w-24 rounded-full" style={{ background: legendGradient() }} />
              {max.toLocaleString()}
              <span>{metric === 'users' ? t('analytics.geo.map.legendUsers') : t('analytics.geo.map.legendIps')}</span>
            </span>
          )}
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-muted" />
            {t('analytics.geo.map.noConnections')}
          </span>
          <span className="ml-auto hidden sm:inline">{t('analytics.geo.map.hint')}</span>
        </div>
      </div>

      <GeoPanel
        view={view}
        metric={metric}
        stats={stats}
        data={data}
        names={layout?.names}
        namesReady={view === WORLD || view === 'RU' || Boolean(layout?.names) || failed}
        selected={selected}
        onSelect={setSelected}
        onOpenCountry={openCountry}
      />
    </div>
  )
}

/**
 * Выбор страны: сначала те, откуда подключались, потом остальные с картой регионов.
 * memo: двести пунктов не перерисовываются на каждом кадре перетаскивания карты.
 */
const CountryPicker = memo(function CountryPicker({ data, view, onChange }: {
  data: GeoData
  view: GeoView
  onChange: (code: string) => void
}) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { withData, rest } = useMemo(() => {
    const users = new Map<string, number>()
    for (const c of data.countries) {
      const code = c.country_code?.toUpperCase()
      if (code && REGION_MAP_COUNTRIES.has(code)) users.set(code, (users.get(code) ?? 0) + c.count)
    }
    const byName = (a: string, b: string) => countryName(a, lang).localeCompare(countryName(b, lang), lang)
    return {
      withData: [...users.entries()].sort((a, b) => b[1] - a[1]).map(([code]) => code),
      rest: [...REGION_MAP_COUNTRIES].filter((code) => !users.has(code)).sort(byName),
    }
  }, [data.countries, lang])

  const item = (code: string) => (
    <SelectItem key={code} value={code} className="text-xs">
      <span className="mr-1.5">{countryFlag(code)}</span>
      {countryName(code, lang)}
    </SelectItem>
  )

  return (
    <Select value={view === WORLD ? '' : view} onValueChange={onChange}>
      <SelectTrigger
        aria-label={t('analytics.geo.map.pickCountry')}
        className={cn(
          'h-auto w-auto gap-1.5 border-0 px-2.5 py-1 text-xs shadow-none focus:ring-0 focus-visible:ring-2 focus-visible:ring-primary/50',
          view !== WORLD ? 'bg-primary/20 font-medium text-primary-400' : 'bg-transparent text-muted-foreground hover:text-white',
        )}
      >
        <SelectValue placeholder={t('analytics.geo.map.pickCountry')} />
      </SelectTrigger>
      <SelectContent>
        {withData.length > 0 && (
          <SelectGroup>
            <SelectLabel className="text-[11px]">{t('analytics.geo.map.withConnections')}</SelectLabel>
            {withData.map(item)}
          </SelectGroup>
        )}
        {withData.length > 0 && rest.length > 0 && <SelectSeparator />}
        {rest.length > 0 && (
          <SelectGroup>
            <SelectLabel className="text-[11px]">{t('analytics.geo.allCountries')}</SelectLabel>
            {rest.map(item)}
          </SelectGroup>
        )}
      </SelectContent>
    </Select>
  )
})

function SegmentButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs transition-all duration-200',
        active ? 'bg-primary/20 font-medium text-primary-400' : 'text-muted-foreground hover:text-white',
      )}
    >
      {children}
    </button>
  )
}

function ZoomButton({ label, onClick, disabled, children }: {
  label: string
  onClick: () => void
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] text-muted-foreground transition-colors hover:text-white disabled:opacity-40 disabled:hover:text-muted-foreground"
    >
      {children}
    </button>
  )
}
