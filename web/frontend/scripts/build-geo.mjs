#!/usr/bin/env node
/**
 * Геоданные карты «Аналитика → География» из Natural Earth 10m admin-1 (public domain).
 *
 * 1. src/components/geo/geo-data.json — страны мира и субъекты РФ одной
 *    TopoJSON-топологией (общие дуги: границы стран и субъектов совпадают).
 *    Страны собираются слиянием субъектов по ISO-коду страны, а не берутся
 *    из admin-0, — так у них одни и те же границы.
 * 2. src/components/geo/countries/<CC>.json — регионы остальных стран, по файлу
 *    на страну (фронт грузит нужный по требованию). Детальность подбирается под
 *    страну: у маленьких вершин и так мало, у больших упрощаем до ~TARGET_VERTICES.
 * 3. shared/assets/geo_regions.json — написания регионов для бэкенда: по ним
 *    название региона из GeoIP сводится к id области на карте. Россия — отдельно,
 *    вручную в shared/geo_regions.py.
 *
 * Принадлежность территорий — по ISO 3166: Крым и Севастополь (UA-43, UA-40) — Украина.
 *
 * Правки поверх Natural Earth:
 * - перепутаны коды Москвы и Московской области (там RU-MOW — область) — меняем местами;
 * - безымянный фрагмент RU-X01~ остаётся в контуре России, но не субъект;
 * - у части территорий нет ISO-кода страны (-1) — сопоставляем вручную;
 * - заморские департаменты Франции, Шпицберген, Бонайре/Саба/Синт-Эстатиус и Буве
 *   у NE внутри FR/NO/NL, а в ISO 3166-1 (и у GeoIP) — свои страны: выделяем;
 * - у региона без годного ISO 3166-2 (пусто, «~», повтор) id — внутренний код NE (adm1_code);
 * - столица и одноимённая область у NE делят названия (Киев, Минск, Алматы, Ташкент,
 *   Вашингтон и округ Колумбия, Мехико) — написания и подписи для них заданы явно,
 *   остальные совпадающие подписи внутри страны различаем автоматически.
 *
 * Запуск (нужны интернет и npm): node scripts/build-geo.mjs
 */
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const NE_TAG = 'v5.1.2'
const MAPSHAPER = 'mapshaper@0.6.121'
const LAYER = 'ne_10m_admin_1_states_provinces'
const BASE = `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/${NE_TAG}/10m_cultural/${LAYER}`
// Карта мира и РФ: доля вершин, которую оставляет упрощение. Москва и Петербург
// крошечные на общем плане, но в них большинство юзеров и их разглядывают с зумом.
const SIMPLIFY = '2%'
const SIMPLIFY_CITIES = '40%'
// Регионы остальных стран: примерно столько вершин на страну
const TARGET_VERTICES = 3000

const frontend = join(dirname(fileURLToPath(import.meta.url)), '..')
const geoDir = join(frontend, 'src/components/geo')
const countriesDir = join(geoDir, 'countries')
const aliasesOut = join(frontend, '../../shared/assets/geo_regions.json')

// Функции для выражений mapshaper (-require): логика не прячется в строках команд
const FIELDS = `
// Территории без ISO-кода страны в NE (iso_a2 = -1) → код по ISO 3166
const NO_ISO = { KAB: 'KZ', SOL: 'SO', CYN: 'CY', USG: 'CU', CSI: 'AU' }
// Регионы NE, которые в ISO 3166-1 — отдельные страны или другая страна
const OWN_ISO = {
  'UA-40': 'UA', 'UA-43': 'UA',
  'FR-GF': 'GF', 'FR-GP': 'GP', 'FR-MQ': 'MQ', 'FR-RE': 'RE', 'FR-YT': 'YT',
  'NO-21': 'SJ', 'NL-BQ1': 'BQ', 'NL-BQ2': 'BQ', 'NL-BQ3': 'BQ',
}
exports.country = (iso, adm0, name, sub, code) => {
  if (OWN_ISO[sub]) return OWN_ISO[sub]
  if (code === 'BVT+00?') return 'BV'
  if (iso !== '-1') return iso
  if (adm0 === 'IOA') return name === 'Christmas Island' ? 'CX' : 'CC'
  return NO_ISO[adm0] || null
}
exports.land = (cc) => cc !== 'AQ'
const SWAP = { 'RU-MOW': 'RU-MOS', 'RU-MOS': 'RU-MOW' }
exports.region = (cc, sub) => (cc === 'RU' && /^RU-[A-Z]+$/.test(sub) ? SWAP[sub] || sub : null)
exports.isRegion = (rid) => rid != null
exports.detail = (rid) => (rid === 'RU-MOW' || rid === 'RU-SPE' ? '${SIMPLIFY_CITIES}' : '${SIMPLIFY}')
exports.foreign = (cc) => cc != null && cc !== 'RU'
`

/**
 * Написания региона для бэкенда: GeoIP (MaxMind, ip-api) пишет по-английски, имена
 * у MaxMind — из GeoNames (gn_name). woe_name не берём: у NE там часто имя соседа
 * или родителя (27 регионов Латвии с «Riga»), и настоящая Рига переставала находиться.
 */
const NAME_FIELDS = ['name', 'name_en', 'name_alt', 'gn_name', 'gns_name']
const PRIMARY_FIELDS = new Set(['name', 'name_en'])
const VALID_ISO = /^[A-Z]{2}-[A-Z0-9]{1,3}$/

// Написания GeoIP для столиц и одноимённых областей: у NE они общие, и без этого
// не узнавались бы ни город, ни область
const ALIAS_OVERRIDES = {
  UA: {
    'Kyiv City': 'UA-30', 'Kyiv': 'UA-30', 'Kiev': 'UA-30', 'Киев': 'UA-30',
    'Kyiv Oblast': 'UA-32', 'Kiev Oblast': 'UA-32', 'Киевская область': 'UA-32',
  },
  BY: {
    'Minsk City': 'BY-HM', 'Horad Minsk': 'BY-HM', 'Минск': 'BY-HM',
    'Minsk': 'BY-MI', 'Minsk Oblast': 'BY-MI', "Minskaya Voblasts'": 'BY-MI', 'Минская область': 'BY-MI',
  },
  KZ: {
    'Almaty': 'KAZ-4829', 'Almaty City': 'KAZ-4829', 'Алматы': 'KAZ-4829', 'Алма-Ата': 'KAZ-4829',
    'Almaty Oblast': 'KAZ-3207', 'Almaty Oblysy': 'KAZ-3207', 'Алматинская область': 'KAZ-3207',
  },
  UZ: {
    'Tashkent': 'UZ-TK', 'Toshkent Shahri': 'UZ-TK',
    'Tashkent Region': 'UZ-TO', 'Tashkent Province': 'UZ-TO', 'Toshkent Viloyati': 'UZ-TO',
  },
  AE: { 'Dubai': 'AE-DU' },
  MX: { 'Mexico City': 'MX-DIF', 'Ciudad de México': 'MX-DIF', 'México': 'MX-MEX', 'State of Mexico': 'MX-MEX' },
  US: { 'Washington': 'US-WA', 'District of Columbia': 'US-DC', 'Washington, D.C.': 'US-DC' },
}
// Подписи тех же регионов: у NE обе половины пары называются одинаково
const LABEL_OVERRIDES = {
  'UA-30': ['Киев', 'Kyiv'], 'UA-32': ['Киевская область', 'Kyiv Oblast'],
  'BY-HM': ['Минск', 'Minsk'], 'BY-MI': ['Минская область', 'Minsk Oblast'],
  'KAZ-4829': ['Алматы', 'Almaty'], 'KAZ-3207': ['Алматинская область', 'Almaty Oblast'],
  'UZ-TK': ['Ташкент', 'Tashkent'], 'UZ-TO': ['Ташкентская область', 'Tashkent Region'],
  'US-WA': ['Вашингтон', 'Washington'], 'US-DC': ['Округ Колумбия', 'District of Columbia'],
  'MX-DIF': ['Мехико', 'Mexico City'], 'MX-MEX': ['Штат Мехико', 'State of Mexico'],
}

/** Написания региона: [имя, основное ли]. «X, Y» у GNS — перевёрнутая форма, её не берём. */
function namesOf(p) {
  return NAME_FIELDS.flatMap((f) => String(p[f] ?? '')
    .split('|')
    .flatMap((s) => (f === 'name_alt' ? s.split(',') : f === 'gns_name' && s.includes(',') ? [] : [s]))
    .map((s) => s.trim())
    .filter((s) => s && s !== '-99')
    .map((s) => [s, PRIMARY_FIELDS.has(f)]))
}

/** Ключ сравнения как у бэкенда (shared/geo_regions.py): без регистра и диакритики. */
const foldKey = (name) => name.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()

/**
 * Написания по регионам страны без двусмысленности: имя, которое есть у нескольких
 * регионов, остаётся только у того, для кого оно основное (и если такой один).
 */
function countryAliases(cc, regions) {
  const owners = new Map()
  for (const { id, names } of regions) {
    for (const [name, primary] of names) {
      const key = foldKey(name)
      const o = owners.get(key) ?? { all: new Set(), primary: new Set() }
      o.all.add(id)
      if (primary) o.primary.add(id)
      owners.set(key, o)
    }
  }
  const overrides = new Map(Object.entries(ALIAS_OVERRIDES[cc] ?? {}).map(([n, id]) => [foldKey(n), [n, id]]))
  const byId = {}
  for (const { id, names } of regions) {
    const seen = new Set()
    byId[id] = names.map(([name]) => name).filter((name) => {
      const key = foldKey(name)
      if (seen.has(key) || overrides.has(key)) return false
      seen.add(key)
      const o = owners.get(key)
      return o.all.size === 1 || (o.primary.size === 1 && o.primary.has(id))
    })
  }
  for (const [name, id] of overrides.values()) {
    if (!byId[id]) throw new Error(`${cc}: нет региона ${id} для написания «${name}»`)
    byId[id].unshift(name)
  }
  return byId
}

/** Подписи регионов страны: [ru, en], без повторов внутри страны. */
function countryLabels(cc, regions) {
  const labels = new Map(regions.map(({ id, p }) => {
    const en = p.name_en || p.name || id
    return [id, LABEL_OVERRIDES[id] ?? [p.name_ru || en, en]]
  }))
  const dups = (i) => {
    const count = new Map()
    for (const l of labels.values()) count.set(l[i], (count.get(l[i]) ?? 0) + 1)
    return (label) => count.get(label) > 1
  }
  // en: местное имя NE, потом тип региона, потом id
  const fallbacks = [(r) => r.p.name, (r, en) => `${en} (${r.p.type_en || r.id})`, (r, en) => `${en} (${r.id})`]
  for (const fallback of fallbacks) {
    const isDup = dups(1)
    for (const r of regions) {
      const [ru, en] = labels.get(r.id)
      if (isDup(en) && !LABEL_OVERRIDES[r.id]) labels.set(r.id, [ru, fallback(r, en) || en])
    }
  }
  // ru: совпала — берём уже уникальную английскую
  const isDupRu = dups(0)
  for (const r of regions) {
    const [ru, en] = labels.get(r.id)
    if (isDupRu(ru) && !LABEL_OVERRIDES[r.id]) labels.set(r.id, [en, en])
  }
  for (const i of [0, 1]) {
    const isDup = dups(i)
    const bad = [...labels.values()].filter((l) => isDup(l[i]))
    if (bad.length) throw new Error(`${cc}: повторяются подписи ${bad.map((l) => l[i]).join(', ')}`)
  }
  return labels
}

async function loadMapshaper(tmp) {
  const prefix = join(tmp, 'mapshaper')
  // Windows запускает npm.cmd только через оболочку — путь в кавычках, остальное без спецсимволов
  const win = process.platform === 'win32'
  execFileSync(win ? 'npm.cmd' : 'npm',
    ['install', '--no-save', '--no-audit', '--no-fund', '--prefix', win ? `"${prefix}"` : prefix, MAPSHAPER],
    { stdio: 'inherit', shell: win })
  const entry = join(prefix, 'node_modules/mapshaper/mapshaper.js')
  return (await import(pathToFileURL(entry).href)).default
}

const countVertices = (topo) => topo.arcs.reduce((sum, arc) => sum + arc.length, 0)

const tmp = mkdtempSync(join(tmpdir(), 'rwa-geo-'))
try {
  const mapshaper = await loadMapshaper(tmp)
  const input = {}
  for (const ext of ['shp', 'shx', 'dbf', 'prj', 'cpg']) {
    const res = await fetch(`${BASE}.${ext}`)
    if (!res.ok) throw new Error(`${BASE}.${ext}: HTTP ${res.status}`)
    input[`adm1.${ext}`] = Buffer.from(await res.arrayBuffer())
  }
  const fields = join(tmp, 'fields.cjs')
  writeFileSync(fields, FIELDS)
  const prepare = `-require ${JSON.stringify(fields)} alias=geo -i adm1.shp name=adm1`
    + ` -each 'cc=geo.country(iso_a2,adm0_a3,name,iso_3166_2,adm1_code)' -filter 'geo.land(cc)'`

  // ── 1. Мир и субъекты РФ ─────────────────────────────────────────────
  // Упрощаем исходный слой до слияния: дуги общие, страны и субъекты совпадут
  const world = await mapshaper.applyCommands(`${prepare}
    -each 'rid=geo.region(cc,iso_3166_2)'
    -simplify variable percentage='geo.detail(rid)' weighted keep-shapes
    -dissolve cc + name=countries
    -filter target=adm1 'geo.isRegion(rid)' + name=regions
    -rename-fields target=countries id=cc
    -rename-fields target=regions id=rid
    -filter-fields target=countries id
    -filter-fields target=regions id
    -o target=countries,regions format=topojson quantization=20000 geo-data.json`, input)
  const topo = JSON.parse(world['geo-data.json'])
  const ruRegions = topo.objects.regions.geometries.map((g) => g.properties?.id)
  if (ruRegions.length !== 83 || new Set(ruRegions).size !== 83) {
    throw new Error(`ожидалось 83 субъекта РФ с уникальными кодами, получено ${ruRegions.length}`)
  }
  writeFileSync(join(geoDir, 'geo-data.json'), JSON.stringify(topo))

  // ── 2. Регионы остальных стран ───────────────────────────────────────
  const split = await mapshaper.applyCommands(`${prepare}
    -filter 'geo.foreign(cc)'
    -filter-fields cc,iso_3166_2,adm1_code,type_en,name_ru,${NAME_FIELDS.join(',')}
    -split cc
    -o format=topojson singles`, input)

  rmSync(countriesDir, { recursive: true, force: true })
  mkdirSync(countriesDir, { recursive: true })
  const aliases = {}
  for (const [file, raw] of Object.entries(split)) {
    const cc = file.replace(/\.json$/, '')
    const source = JSON.parse(raw)
    if (Object.values(source.objects)[0].geometries.length < 2) continue   // регионов нет — только страна целиком

    const pct = Math.min(100, (TARGET_VERTICES / countVertices(source)) * 100)
    const simplified = await mapshaper.applyCommands(
      `-i in.json -simplify ${pct.toFixed(3)}% weighted keep-shapes -o format=topojson quantization=10000 out.json`,
      { 'in.json': raw },
    )
    const out = JSON.parse(simplified['out.json'])
    const object = Object.values(out.objects)[0]

    const isoCount = {}
    for (const g of object.geometries) isoCount[g.properties.iso_3166_2] = (isoCount[g.properties.iso_3166_2] || 0) + 1
    const regions = object.geometries.map((g) => {
      const p = g.properties
      const id = VALID_ISO.test(p.iso_3166_2) && isoCount[p.iso_3166_2] === 1 ? p.iso_3166_2 : p.adm1_code
      return { g, p, id, names: namesOf(p) }
    })
    const labels = countryLabels(cc, regions)
    for (const { g, id } of regions) {
      const [ru, en] = labels.get(id)
      g.properties = { id, ru, en }
    }
    out.objects = { regions: object }
    writeFileSync(join(countriesDir, `${cc}.json`), JSON.stringify(out))
    aliases[cc] = countryAliases(cc, regions)
  }
  const sorted = Object.fromEntries(Object.keys(aliases).sort().map((cc) => [cc, aliases[cc]]))
  writeFileSync(aliasesOut, JSON.stringify(sorted) + '\n')

  const kb = (bytes) => `${(bytes / 1024).toFixed(0)} KB`
  const files = readdirSync(countriesDir)
  const total = files.reduce((s, f) => s + statSync(join(countriesDir, f)).size, 0)
  console.log(`geo-data.json: ${kb(statSync(join(geoDir, 'geo-data.json')).size)}, `
    + `субъектов РФ ${ruRegions.length}, стран ${topo.objects.countries.geometries.length}`)
  console.log(`countries/: ${files.length} стран, ${kb(total)}; geo_regions.json: ${kb(statSync(aliasesOut).size)}`)
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
