/**
 * InteractiveChart — переиспользуемый график в стиле панели с «графана-фишками»:
 * переключение вида (область/линия/столбцы), zoom-brush, экспорт CSV,
 * мультисерии, единая тема (useChartTheme).
 *
 * Период/диапазон дат остаётся за вызывающим (данные приходят готовыми) —
 * компонент отвечает за визуализацию и интерактив над данными.
 */
import { useMemo, useState, useRef, useEffect, ReactElement } from 'react'
import {
  ResponsiveContainer, ComposedChart, Area, Line, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip as RechartsTooltip, Brush, ReferenceArea,
} from 'recharts'
import { useChartTheme } from '@/lib/useChartTheme'
import { useTranslation } from 'react-i18next'
import { Activity, BarChart3, TrendingUp, Download, Maximize2 } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

export type ChartType = 'area' | 'line' | 'bar'

export interface ChartSeries {
  key: string
  name: string
  color?: string
  dashed?: boolean
}

interface InteractiveChartProps {
  data: Record<string, any>[]
  xKey: string
  series: ChartSeries[]
  height?: number
  defaultType?: ChartType
  allowedTypes?: ChartType[]
  yFormatter?: (v: number) => string
  /** форматтер подписей оси X (напр. ISO-дата -> dd.mm) */
  xFormatter?: (v: string) => string
  tooltip?: ReactElement
  /** форматтер значений в дефолтном тултипе (если tooltip-элемент не задан) */
  tooltipFormatter?: (value: number, name: string) => [React.ReactNode, React.ReactNode] | React.ReactNode
  /** форматтер имени серии в легенде */
  legendFormatter?: (name: string) => string
  brush?: boolean
  /** стек серий (area/bar) — для «трафик по нодам» и т.п. */
  stacked?: boolean
  /** сколько серий рисовать поимённо; хвост сворачивается в «Прочие».
   *  На сорока нодах линии сливаются в кашу, а легенда съедает всю высоту. */
  maxSeries?: number
  exportName?: string
  className?: string
  /** ключ с «сырым» значением X (напр. ISO-дата) — для onRangeSelect/перезапроса */
  rawKey?: string
  /** протянул интервал на графике -> сюда прилетают границы (raw, если есть rawKey) */
  onRangeSelect?: (from: string, to: string) => void
}

const TYPE_ICONS: Record<ChartType, typeof Activity> = {
  area: TrendingUp,
  line: Activity,
  bar: BarChart3,
}

function toCsv(rows: Record<string, any>[], xKey: string, series: ChartSeries[]): string {
  const cols = [xKey, ...series.map((s) => s.key)]
  const header = [xKey, ...series.map((s) => s.name)].join(',')
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = rows.map((r) => cols.map((c) => escape(r[c])).join(','))
  return [header, ...lines].join('\n')
}

/** Ключ свёрнутого хвоста серий. С двух подчёркиваний — чтобы не столкнуться
 *  с настоящим полем данных. */
const REST_KEY = '__rest'

export function InteractiveChart({
  data, xKey, series, height = 260, defaultType = 'area',
  allowedTypes = ['area', 'line', 'bar'], yFormatter, xFormatter, tooltip, tooltipFormatter, legendFormatter,
  brush, stacked, maxSeries = 10, exportName, className, rawKey, onRangeSelect,
}: InteractiveChartProps) {
  const chart = useChartTheme()
  const { t } = useTranslation()
  const [type, setType] = useState<ChartType>(defaultType)
  const gradId = useRef(`icg-${Math.round(performance.now())}-${Math.random().toString(36).slice(2, 7)}`)
  const [hidden, setHidden] = useState<Set<string>>(() => new Set())

  // ── drag-select интервала прямо на графике (как в Grafana) ──────
  const [dragA, setDragA] = useState<string | null>(null)
  const [dragB, setDragB] = useState<string | null>(null)
  const [zoom, setZoom] = useState<[number, number] | null>(null)

  // при смене данных (напр. родитель перезапросил) — сбрасываем зум
  useEffect(() => { setZoom(null); setDragA(null); setDragB(null) }, [data])

  // ── топ-N поимённо, остальное — одной серией ────────────────────
  // Вес серии считаем по сумме модулей: у трафика значения только
  // положительные, а у дельт хвост важен по величине, а не по знаку.
  const { plotSeries, plotData, restCount } = useMemo(() => {
    if (series.length <= maxSeries) {
      return { plotSeries: series, plotData: data, restCount: 0 }
    }
    const weight = new Map<string, number>()
    for (const s of series) {
      let sum = 0
      for (const row of data) sum += Math.abs(Number(row[s.key]) || 0)
      weight.set(s.key, sum)
    }
    const ordered = [...series].sort(
      (a, b) => (weight.get(b.key) ?? 0) - (weight.get(a.key) ?? 0),
    )
    const top = ordered.slice(0, maxSeries)
    const rest = ordered.slice(maxSeries)
    const merged = data.map((row) => {
      let sum = 0
      for (const s of rest) sum += Number(row[s.key]) || 0
      return { ...row, [REST_KEY]: sum }
    })
    const restSeries: ChartSeries = {
      key: REST_KEY,
      name: t('charts.otherSeries', { count: rest.length }),
      color: chart.tick,
    }
    return { plotSeries: [...top, restSeries], plotData: merged, restCount: rest.length }
  }, [series, data, maxSeries, t, chart.tick])

  // Состав серий сменился (другой период, другой набор нод) — прячущее
  // состояние больше не про эти данные.
  const seriesFingerprint = plotSeries.map((s) => s.key).join('|')
  useEffect(() => { setHidden(new Set()) }, [seriesFingerprint])

  const viewData = useMemo(
    () => (zoom ? plotData.slice(zoom[0], zoom[1] + 1) : plotData),
    [plotData, zoom],
  )

  const applyDrag = () => {
    if (dragA != null && dragB != null && dragA !== dragB) {
      const iA = data.findIndex((d) => String(d[xKey]) === dragA)
      const iB = data.findIndex((d) => String(d[xKey]) === dragB)
      if (iA >= 0 && iB >= 0) {
        const lo = Math.min(iA, iB)
        const hi = Math.max(iA, iB)
        if (hi > lo) {
          setZoom([lo, hi])
          if (onRangeSelect) {
            const pick = (i: number) => String((rawKey && data[i]?.[rawKey]) ?? data[i]?.[xKey] ?? '')
            onRangeSelect(pick(lo), pick(hi))
          }
        }
      }
    }
    setDragA(null); setDragB(null)
  }

  const colorOf = (s: ChartSeries, i: number) =>
    s.color || (i === 0 ? chart.accentColor : ['#8b5cf6', '#f59e0b', '#10b981', '#ef4444'][(i - 1) % 4])

  // Цвет закреплён за ключом, а не за позицией среди видимых: иначе график
  // перекрашивался бы каждый раз, когда серию прячут.
  const colors = useMemo(
    () => new Map(plotSeries.map((s, i) => [s.key, colorOf(s, i)])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [plotSeries, chart.accentColor],
  )

  const toggleSeries = (key: string, isolate: boolean) => {
    setHidden((prev) => {
      if (isolate) {
        const others = plotSeries.filter((s) => s.key !== key).map((s) => s.key)
        // Повторный alt-клик по уже одинокой серии возвращает всё обратно.
        const alone = !prev.has(key) && others.every((k) => prev.has(k))
        return alone ? new Set() : new Set(others)
      }
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      // Погасить последнюю видимую не даём: пустой график читается как поломка.
      return next.size >= plotSeries.length ? prev : next
    })
  }

  const exportCsv = () => {
    const blob = new Blob([toCsv(data, xKey, series)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${exportName || 'chart'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const renderSeries = useMemo(() => plotSeries.map((s, i) => {
    const color = colors.get(s.key) as string
    const stackId = stacked ? 'stack' : undefined
    // Скрытую серию не выкидываем из разметки, а гасим: так у остальных не
    // едут ни цвета, ни порядок в стеке.
    const off = hidden.has(s.key)
    if (type === 'bar') {
      return <Bar key={s.key} dataKey={s.key} name={s.name} fill={color} stackId={stackId} hide={off}
        radius={stacked ? undefined : [3, 3, 0, 0]} fillOpacity={s.dashed ? 0.4 : 0.85} />
    }
    if (type === 'line') {
      return <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={color} hide={off}
        strokeWidth={s.dashed ? 1.5 : 2} strokeDasharray={s.dashed ? '5 5' : undefined}
        dot={false} activeDot={{ r: 4, fill: color }} />
    }
    // area
    return <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={color} stackId={stackId}
      strokeWidth={s.dashed ? 1.5 : 2} strokeDasharray={s.dashed ? '5 5' : undefined} hide={off}
      fill={s.dashed ? 'none' : `url(#${gradId.current}-${i})`} dot={false}
      activeDot={{ r: 4, fill: color }} />
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [plotSeries, colors, hidden, type, stacked])

  return (
    <div className={className}>
      {/* тулбар: сброс зума + вид графика + экспорт */}
      <div className="flex items-center justify-end gap-1 mb-1.5">
        {zoom && (
          <button type="button" onClick={() => setZoom(null)} title={t('charts.resetZoom')}
            className="px-2 py-1 rounded-lg border border-primary-500/40 text-primary-300 hover:bg-primary-500/10 transition-colors flex items-center gap-1 text-[11px]">
            <Maximize2 className="w-3.5 h-3.5" /> {t('charts.resetZoom')}
          </button>
        )}
        <div className="flex items-center rounded-lg border border-[var(--glass-border)] overflow-hidden">
          {allowedTypes.map((tp) => {
            const Icon = TYPE_ICONS[tp]
            return (
              <button key={tp} type="button" onClick={() => setType(tp)}
                title={t(`charts.type.${tp}`)}
                className={cn('px-2 py-1 transition-colors', type === tp
                  ? 'bg-primary-500/20 text-primary-300' : 'text-muted-foreground hover:text-white')}>
                <Icon className="w-3.5 h-3.5" />
              </button>
            )
          })}
        </div>
        {exportName && (
          <button type="button" onClick={exportCsv} title={t('charts.exportCsv')}
            className="px-2 py-1 rounded-lg border border-[var(--glass-border)] text-muted-foreground hover:text-white transition-colors">
            <Download className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div style={{ height, userSelect: dragA ? 'none' : undefined }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={viewData} margin={{ top: 5, right: 8, bottom: 0, left: 0 }}
            onMouseDown={(e) => { const l = e?.activeLabel; if (l != null) { setDragA(String(l)); setDragB(String(l)) } }}
            onMouseMove={(e) => { const l = e?.activeLabel; if (dragA && l != null) setDragB(String(l)) }}
            onMouseUp={applyDrag}
            onMouseLeave={() => { if (dragA) applyDrag() }}>
            <defs>
              {plotSeries.map((s, i) => (
                <linearGradient key={s.key} id={`${gradId.current}-${i}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={colors.get(s.key)} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={colors.get(s.key)} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} vertical={false} />
            <XAxis dataKey={xKey} tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false}
              tickFormatter={xFormatter ? (v: string) => xFormatter(v) : undefined} />
            <YAxis tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} width={50}
              tickFormatter={yFormatter ? (v: number) => yFormatter(v) : undefined} />
            <RechartsTooltip
              content={tooltip}
              contentStyle={tooltip ? undefined : chart.tooltipStyle}
              formatter={tooltip ? undefined : (tooltipFormatter as never)}
              cursor={{ stroke: `${chart.accentColor}4D` }}
            />
            {renderSeries}
            {/* подсветка протягиваемого интервала */}
            {dragA && dragB && dragA !== dragB && (
              <ReferenceArea x1={dragA} x2={dragB} strokeOpacity={0}
                fill={chart.accentColor} fillOpacity={0.12} />
            )}
            {brush && !zoom && viewData.length > 8 && (
              <Brush dataKey={xKey} height={18} travellerWidth={8}
                stroke={chart.accentColor} fill="transparent"
                tickFormatter={() => ''} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {/* Легенда живёт СНАРУЖИ графика: встроенная в Recharts делит с ним
          фиксированную высоту, и на сорока нодах от графика не остаётся
          ничего. Здесь она своя — со скроллом и кликом-фильтром. */}
      {plotSeries.length > 1 && (
        <div className="mt-2">
          <div className="max-h-[4.5rem] overflow-y-auto pr-1 flex flex-wrap gap-x-3 gap-y-1">
            {plotSeries.map((s) => {
              const off = hidden.has(s.key)
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={(e) => toggleSeries(s.key, e.altKey || e.metaKey)}
                  aria-pressed={!off}
                  title={t('charts.legendHint')}
                  className={cn(
                    'flex items-center gap-1.5 text-[11px] rounded px-1 py-0.5 transition-colors',
                    'hover:bg-white/5 focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary-400',
                    off ? 'text-muted-foreground/50' : 'text-muted-foreground',
                  )}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: colors.get(s.key), opacity: off ? 0.35 : 1 }}
                  />
                  <span className={cn('truncate max-w-[11rem]', off && 'line-through')}>
                    {legendFormatter ? legendFormatter(s.name) : s.name}
                  </span>
                </button>
              )
            })}
          </div>
          {(hidden.size > 0 || restCount > 0) && (
            <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
              {restCount > 0 && <span>{t('charts.seriesTrimmed', { shown: maxSeries, total: series.length })}</span>}
              {hidden.size > 0 && (
                <button type="button" onClick={() => setHidden(new Set())}
                  className="underline underline-offset-2 hover:text-white transition-colors">
                  {t('charts.showAll')}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      <p className="text-[10px] text-muted-foreground text-center mt-1">{t('charts.dragHint')}</p>
    </div>
  )
}
