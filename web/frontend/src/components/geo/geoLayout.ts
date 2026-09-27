import { useEffect, useState } from 'react'
import {
  geoAlbersUsa, geoArea, geoBounds, geoCentroid, geoConicEqualArea, geoDistance, geoNaturalEarth1, geoPath,
  type GeoProjection,
} from 'd3-geo'
import { feature } from 'topojson-client'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { GeometryCollection, Topology } from 'topojson-specification'
import geoData from './geo-data.json'
import { WORLD, loadCountryTopology, type AreaNames, type GeoView } from './geoModel'
import type { Bounds } from './useZoomPan'

type AreaProps = { id: string | null; ru?: string; en?: string }
type Area = Feature<Geometry, AreaProps>
type Areas = FeatureCollection<Geometry, AreaProps>

export interface Shape {
  id: string
  d: string
  /** Рамка области в координатах viewBox */
  box: Bounds
  /** Центр области в координатах viewBox — для метки мелких областей */
  cx: number
  cy: number
  /** Область на общем плане меньше пары пикселей — её рисуем ещё и кружком */
  small: boolean
}

export interface MapLayout {
  width: number
  height: number
  /** Неинтерактивная подложка: соседи России, спорные клочки на карте мира */
  background: string[]
  shapes: Shape[]
  /** Кадр плюс всё нарисованное за ним (заморские регионы) — докуда можно сдвинуть карту */
  bounds: Bounds
  /** Названия регионов из карты страны (у субъектов РФ и стран — свои источники) */
  names?: AreaNames
}

const WIDTH = 1000
const PAD = 8
const MIN_HEIGHT = 360
const MAX_HEIGHT = 700
const SMALL_PX = 9
const EARTH_KM = 6371
// Заморские куски дальше этого от основного массива страны кадр не растягивают
const OFFSHORE_GAP_KM = 800
const MAIN_SHARE = 0.25

type Projector = ReturnType<typeof geoPath>

/** Проекция по ширине кадра; высота — по форме страны, но в разумных пределах. */
function fit(projection: GeoProjection, target: Areas): { height: number; path: Projector } {
  projection.fitWidth(WIDTH - 2 * PAD, target)
  const [[, y0], [, y1]] = geoPath(projection).bounds(target)
  const height = Math.round(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, y1 - y0 + 2 * PAD)))
  projection.fitExtent([[PAD, PAD], [WIDTH - PAD, height - PAD]], target)
  return { height, path: geoPath(projection) }
}

function toShape(f: Area, path: Projector): Shape | null {
  const d = path(f)
  if (!f.properties.id || !d) return null
  const [[x0, y0], [x1, y1]] = path.bounds(f)
  const [cx, cy] = path.centroid(f)
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null
  return { id: f.properties.id, d, box: [x0, y0, x1, y1], cx, cy, small: Math.max(x1 - x0, y1 - y0) < SMALL_PX }
}

function boundsOf(shapes: Shape[], height: number): Bounds {
  let [x0, y0, x1, y1] = [0, 0, WIDTH, height]
  for (const { box } of shapes) {
    x0 = Math.min(x0, box[0]); y0 = Math.min(y0, box[1])
    x1 = Math.max(x1, box[2]); y1 = Math.max(y1, box[3])
  }
  return [x0, y0, x1, y1]
}

const shapesOf = (areas: Areas, path: Projector) =>
  areas.features.map((f) => toShape(f, path)).filter((s): s is Shape => s !== null)

/**
 * Основной массив страны: регионы, между которыми меньше OFFSHORE_GAP_KM,
 * собираются в группы; в кадр идут группы не меньше MAIN_SHARE от крупнейшей.
 * Так у Малайзии в кадре и полуостров, и Борнео, а Канары, Азоры и Галапагосы
 * кадр не растягивают — до них можно доехать, сдвинув карту.
 */
export function mainland(areas: Areas): Areas {
  const items = areas.features.map((f) => {
    const area = geoArea(f) * EARTH_KM * EARTH_KM
    return { f, c: geoCentroid(f), area, radius: Math.sqrt(area / Math.PI) }
  })
  if (items.length < 2) return areas
  const group = items.map((_, i) => i)
  const root = (i: number): number => (group[i] === i ? i : (group[i] = root(group[i])))
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      const gap = geoDistance(items[i].c, items[j].c) * EARTH_KM - items[i].radius - items[j].radius
      if (gap < OFFSHORE_GAP_KM) group[root(i)] = root(j)
    }
  }
  const total = new Map<number, number>()
  items.forEach((it, i) => total.set(root(i), (total.get(root(i)) ?? 0) + it.area))
  const largest = Math.max(...total.values())
  const main = new Set([...total.entries()].filter(([, area]) => area >= largest * MAIN_SHARE).map(([g]) => g))
  return { type: 'FeatureCollection', features: items.filter((_, i) => main.has(root(i))).map((it) => it.f) }
}

/** Равновеликая коническая проекция вокруг страны: без разрыва на 180° и искажений площадей. */
function countryProjection(code: string, target: Areas): GeoProjection {
  if (code === 'US') return geoAlbersUsa() as unknown as GeoProjection
  const [lon] = geoCentroid(target)
  const [[, lat0], [, lat1]] = geoBounds(target)
  const span = lat1 - lat0
  return geoConicEqualArea().rotate([-lon, 0]).parallels([lat0 + span / 6, lat1 - span / 6])
}

const topo = geoData as unknown as Topology<{ countries: GeometryCollection<AreaProps>; regions: GeometryCollection<AreaProps> }>
const layouts = new Map<GeoView, MapLayout>()

function worldLayout(): MapLayout {
  const countries = feature(topo, topo.objects.countries) as Areas
  const { height, path } = fit(geoNaturalEarth1(), countries)
  const shapes = shapesOf(countries, path)
  return {
    width: WIDTH,
    height,
    background: countries.features.filter((f) => !f.properties.id).map((f) => path(f)).filter((d): d is string => Boolean(d)),
    shapes,
    bounds: boundsOf(shapes, height),
  }
}

function russiaLayout(): MapLayout {
  const countries = feature(topo, topo.objects.countries) as Areas
  const regions = feature(topo, topo.objects.regions) as Areas
  // Соседи — из той же топологии, что и субъекты: границы совпадают без щелей
  const { height, path } = fit(geoConicEqualArea().rotate([-100, 0]).parallels([52, 64]), regions)
  const shapes = shapesOf(regions, path)
  return {
    width: WIDTH,
    height,
    background: countries.features.map((f) => path(f)).filter((d): d is string => Boolean(d)),
    shapes,
    bounds: boundsOf(shapes, height),
  }
}

function countryLayout(code: string, data: unknown): MapLayout {
  const t = data as Topology<{ regions: GeometryCollection<AreaProps> }>
  const regions = feature(t, t.objects.regions) as Areas
  // У США своя составная проекция: Аляска и Гавайи — врезками, кадр по всем штатам
  const target = code === 'US' ? regions : mainland(regions)
  const { height, path } = fit(countryProjection(code, target), target)
  const names = new Map<string, readonly [string, string]>()
  for (const f of regions.features) {
    if (f.properties.id) names.set(f.properties.id, [f.properties.ru || f.properties.en || f.properties.id, f.properties.en || f.properties.id])
  }
  const shapes = shapesOf(regions, path)
  return { width: WIDTH, height, background: [], shapes, bounds: boundsOf(shapes, height), names }
}

/** Раскладка, если она уже есть; мир и Россия всегда под рукой. */
export function cachedLayout(view: GeoView): MapLayout | undefined {
  if (!layouts.has(view) && (view === WORLD || view === 'RU')) {
    layouts.set(view, view === WORLD ? worldLayout() : russiaLayout())
  }
  return layouts.get(view)
}

/** Раскладка вида; карта регионов страны подгружается при первом открытии. */
export function useMapLayout(view: GeoView): { layout?: MapLayout; failed: boolean } {
  const [state, setState] = useState<{ view: GeoView; layout?: MapLayout; failed: boolean }>(
    () => ({ view, layout: cachedLayout(view), failed: false }),
  )
  useEffect(() => {
    const ready = cachedLayout(view)
    if (ready) {
      setState({ view, layout: ready, failed: false })
      return
    }
    let alive = true
    setState({ view, failed: false })
    loadCountryTopology(view)
      .then((data) => {
        const layout = countryLayout(view, data)
        layouts.set(view, layout)
        if (alive) setState({ view, layout, failed: false })
      })
      .catch(() => alive && setState({ view, failed: true }))
    return () => {
      alive = false
    }
  }, [view])
  // Пока грузится новая страна, старую раскладку не показываем
  return state.view === view ? state : { layout: cachedLayout(view), failed: false }
}
