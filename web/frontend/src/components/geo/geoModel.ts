import type { GeoCountry, GeoRegion } from '@/api/advancedAnalytics'
import { RU_REGION_NAMES } from './regions'

/** Что показывает карта: 'world' — страны мира, иначе ISO-код страны — её регионы */
export type GeoView = string
export const WORLD: GeoView = 'world'

/** Чем закрашивать: уникальные юзеры или адреса */
export type GeoMetric = 'users' | 'ips'

/** Названия областей вида: id → [по-русски, по-английски] */
export type AreaNames = ReadonlyMap<string, readonly [string, string]>

export interface AreaStat {
  /** ISO 3166-1 alpha-2 страны или id региона (ISO 3166-2, если он есть) */
  id: string
  users: number
  ips: number
}

// Регионы стран, кроме России (она в geo-data.json вместе с картой мира):
// файл на страну, грузится только когда страну открыли
const countryFiles = import.meta.glob<{ default: unknown }>('./countries/*.json')
const COUNTRY_LOADERS = new Map(
  Object.entries(countryFiles).map(([path, load]) => [path.replace(/^.*\/|\.json$/g, ''), load] as const),
)

/** Страны, у которых есть карта регионов */
export const REGION_MAP_COUNTRIES: ReadonlySet<string> = new Set(['RU', ...COUNTRY_LOADERS.keys()])

export function hasRegionMap(code: string | null | undefined): boolean {
  return Boolean(code) && REGION_MAP_COUNTRIES.has(code!.toUpperCase())
}

export function loadCountryTopology(code: string): Promise<unknown> {
  const load = COUNTRY_LOADERS.get(code)
  if (!load) return Promise.reject(new Error(`no region map for ${code}`))
  return load().then((m) => m.default)
}

/** Вид из URL: 'world', код страны с картой регионов или пусто — выбрать самим. */
export function parseView(raw: string | null | undefined, countries: GeoCountry[], fallback?: GeoView): GeoView {
  const value = (raw || '').trim()
  if (value.toLowerCase() === WORLD) return WORLD
  if (hasRegionMap(value)) return value.toUpperCase()
  return fallback ?? defaultView(countries)
}

/**
 * Вид по умолчанию: регионы страны, где больше половины юзеров (обычно Россия),
 * иначе — мир.
 */
export function defaultView(countries: GeoCountry[]): GeoView {
  const total = countries.reduce((sum, c) => sum + c.count, 0)
  const top = [...countries].sort((a, b) => b.count - a.count)[0]
  const code = top?.country_code?.toUpperCase()
  return code && total > 0 && top.count * 2 > total && hasRegionMap(code) ? code : WORLD
}

/** Цифры по областям текущего вида; ключ — id области на карте. */
export function statsFor(view: GeoView, countries: GeoCountry[], regions: GeoRegion[]): Map<string, AreaStat> {
  const stats = new Map<string, AreaStat>()
  if (view !== WORLD) {
    for (const r of regions) {
      if (r.country_code?.toUpperCase() === view) stats.set(r.code, { id: r.code, users: r.count, ips: r.unique_ips })
    }
    return stats
  }
  for (const c of countries) {
    const id = (c.country_code || '').toUpperCase()
    if (!id) continue
    const prev = stats.get(id)
    stats.set(id, {
      id,
      users: (prev?.users ?? 0) + c.count,
      ips: (prev?.ips ?? 0) + (c.unique_ips ?? 0),
    })
  }
  return stats
}

export function metricOf(stat: AreaStat | undefined, metric: GeoMetric): number {
  if (!stat) return 0
  return metric === 'users' ? stat.users : stat.ips
}

/**
 * Насыщенность 0…1 по логарифмической шкале: столица с сотнями юзеров
 * не должна гасить области, где их единицы.
 */
export function intensity(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0
  return Math.min(1, Math.log1p(value) / Math.log1p(max))
}

/** Нижняя граница насыщенности у областей с данными: одиночный юзер виден сразу. */
const MIN_MIX = 22

/** Заливка области: без данных — фон карты, дальше смесь с цветом акцента темы. */
export function fillFor(t: number): string {
  if (t <= 0) return 'hsl(var(--muted))'
  const pct = Math.round(MIN_MIX + (100 - MIN_MIX) * t)
  return `color-mix(in oklab, hsl(var(--primary)) ${pct}%, hsl(var(--muted)))`
}

/** Градиент для легенды — те же крайние точки, что у заливки. */
export function legendGradient(): string {
  return `linear-gradient(to right, ${fillFor(0.001)}, ${fillFor(1)})`
}

const displayNames = new Map<string, Intl.DisplayNames | null>()

function regionDisplayNames(lang: string): Intl.DisplayNames | null {
  if (!displayNames.has(lang)) {
    try {
      displayNames.set(lang, new Intl.DisplayNames([lang], { type: 'region', fallback: 'none' }))
    } catch {
      displayNames.set(lang, null)
    }
  }
  return displayNames.get(lang) ?? null
}

export function isRu(lang: string | undefined): boolean {
  return (lang || '').toLowerCase().startsWith('ru')
}

/** Название страны на языке интерфейса; fallback — имя от GeoIP. */
export function countryName(code: string, lang: string, fallback?: string): string {
  try {
    const name = regionDisplayNames(isRu(lang) ? 'ru' : 'en')?.of(code)
    if (name && name !== code) return name
  } catch {
    // не ISO-код — ниже fallback
  }
  return fallback || code
}

/** Название области: субъекты РФ — свои, регионы других стран — из их карты, страны — из Intl. */
export function areaName(id: string, lang: string, names?: AreaNames, fallback?: string): string {
  const pair = RU_REGION_NAMES[id] ?? names?.get(id)
  if (pair) return isRu(lang) ? pair[0] : pair[1]
  return countryName(id, lang, fallback)
}
