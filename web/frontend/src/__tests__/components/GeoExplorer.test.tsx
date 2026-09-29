import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { geoContains } from 'd3-geo'
import { feature } from 'topojson-client'
import type { FeatureCollection, Geometry } from 'geojson'
import type { GeometryCollection, Topology } from 'topojson-specification'
import type { GeoData } from '@/api/advancedAnalytics'
import geoData from '@/components/geo/geo-data.json'
import GeoExplorer from '@/components/geo/GeoExplorer'
import { mainland } from '@/components/geo/geoLayout'
import {
  REGION_MAP_COUNTRIES, areaName, defaultView, fillFor, intensity, loadCountryTopology, parseView, statsFor,
} from '@/components/geo/geoModel'
import { RU_REGION_NAMES } from '@/components/geo/regions'
import { clampZoom, zoomAround } from '@/components/geo/useZoomPan'

type Props = { id: string | null }
const topo = geoData as unknown as Topology<{ countries: GeometryCollection<Props>; regions: GeometryCollection<Props> }>
const countries = feature(topo, topo.objects.countries) as FeatureCollection<Geometry, Props>
const regions = feature(topo, topo.objects.regions) as FeatureCollection<Geometry, Props>
const country = (id: string) => countries.features.find((f) => f.properties.id === id)!
const region = (id: string) => regions.features.find((f) => f.properties.id === id)!

describe('geo-data.json', () => {
  it('has the 83 federal subjects the names table knows', () => {
    const ids = regions.features.map((f) => f.properties.id)
    expect(new Set(ids).size).toBe(83)
    expect([...ids].sort()).toEqual(Object.keys(RU_REGION_NAMES).sort())
  })

  it('has unique country codes', () => {
    const ids = countries.features.map((f) => f.properties.id).filter(Boolean)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids).toContain('RU')
    expect(ids).toContain('US')
  })

  it('places Crimea and Sevastopol in Ukraine (ISO 3166)', () => {
    for (const point of [[34.1, 44.95], [33.52, 44.6]] as [number, number][]) {
      expect(geoContains(country('UA'), point)).toBe(true)
      expect(geoContains(country('RU'), point)).toBe(false)
      expect(regions.features.some((f) => geoContains(f, point))).toBe(false)
    }
  })

  it('keeps Moscow and Moscow Oblast apart (Natural Earth swaps their codes)', () => {
    expect(geoContains(region('RU-MOW'), [37.62, 55.75])).toBe(true)
    expect(geoContains(region('RU-MOS'), [38.22, 55.57])).toBe(true)
    expect(geoContains(region('RU-MOS'), [37.62, 55.75])).toBe(false)
  })
})

describe('geoModel', () => {
  it('intensity is 0 without data and grows on a log scale', () => {
    expect(intensity(0, 50)).toBe(0)
    expect(intensity(50, 50)).toBe(1)
    const one = intensity(1, 50)
    expect(one).toBeGreaterThan(0.15)
    expect(intensity(5, 50)).toBeGreaterThan(one)
    expect(fillFor(0)).toBe('hsl(var(--muted))')
    expect(fillFor(1)).toContain('100%')
  })

  it('merges countries that GeoIP names differently but codes the same', () => {
    const stats = statsFor('world', [
      { country: 'Russia', country_code: 'RU', count: 5, unique_ips: 7 },
      { country: 'Russian Federation', country_code: 'ru', count: 2, unique_ips: 3 },
    ], [])
    expect(stats.get('RU')).toEqual({ id: 'RU', users: 7, ips: 10 })
  })

  it('uses the regions of the chosen country', () => {
    const regions = [
      { code: 'RU-MOW', country_code: 'RU', count: 40, unique_ips: 4000, cities: [], nodes: [], users: [] },
      { code: 'DE-BY', country_code: 'DE', count: 2, unique_ips: 3, cities: [], nodes: [], users: [] },
    ]
    expect([...statsFor('RU', [], regions).keys()]).toEqual(['RU-MOW'])
    expect([...statsFor('DE', [], regions).keys()]).toEqual(['DE-BY'])
  })

  it('names regions and countries in the interface language', () => {
    expect(areaName('RU-SPE', 'ru')).toBe('Санкт-Петербург')
    expect(areaName('RU-SPE', 'en-GB')).toBe('Saint Petersburg')
    expect(areaName('DE', 'en')).toBe('Germany')
    expect(areaName('DE-BY', 'ru', new Map([['DE-BY', ['Бавария', 'Bavaria']]]))).toBe('Бавария')
    expect(areaName('QQ', 'en', undefined, 'Somewhere')).toBe('Somewhere')
  })

  it('opens the regions of the country that has most users', () => {
    const c = (country_code: string, count: number) => ({ country: country_code, country_code, count })
    expect(defaultView([c('RU', 9), c('IR', 3)])).toBe('RU')
    expect(defaultView([c('IR', 9), c('RU', 3)])).toBe('IR')
    expect(defaultView([c('RU', 5), c('NL', 4), c('DE', 3)])).toBe('world')
    expect(defaultView([])).toBe('world')
  })

  it('reads the view from the URL', () => {
    const countries = [{ country: 'Russia', country_code: 'RU', count: 9 }]
    expect(parseView('world', countries)).toBe('world')
    expect(parseView('de', countries)).toBe('DE')
    expect(parseView('ru', countries)).toBe('RU')
    expect(parseView('', countries)).toBe('RU')
    expect(parseView('XX', countries)).toBe('RU')
  })

  it('has region maps for Russia and the rest of the world', () => {
    expect(REGION_MAP_COUNTRIES.size).toBeGreaterThan(150)
    for (const code of ['RU', 'UA', 'DE', 'US', 'KZ', 'IR']) expect(REGION_MAP_COUNTRIES.has(code)).toBe(true)
  })

  it('keeps far overseas regions out of the frame, but not a big second landmass', async () => {
    const ids = async (code: string) => {
      const topo = (await loadCountryTopology(code)) as Topology<{ regions: GeometryCollection<Props> }>
      const regions = feature(topo, topo.objects.regions) as FeatureCollection<Geometry, Props>
      return mainland(regions).features.map((f) => f.properties.id)
    }
    const es = await ids('ES')
    expect(es).toContain('ES-M')
    expect(es).not.toContain('ES-TF')   // Канары
    const my = await ids('MY')
    expect(my).toContain('MY-14')       // Куала-Лумпур на полуострове
    expect(my).toContain('MY-12')       // Сабах на Борнео
  })

  it('treats French overseas departments as separate countries (ISO 3166-1)', () => {
    const ids = countries.features.map((f) => f.properties.id)
    for (const code of ['GF', 'RE', 'GP', 'MQ', 'YT', 'SJ', 'BQ']) expect(ids).toContain(code)
  })
})

describe('zoom', () => {
  it('keeps the point under the cursor in place', () => {
    const t = zoomAround({ k: 1, x: 0, y: 0 }, 2, 300, 200, 1000, 500)
    expect(t.k).toBe(2)
    // Точка карты под курсором: (p - сдвиг) / масштаб — до и после одна и та же
    expect((300 - t.x) / t.k).toBeCloseTo(300)
    expect((200 - t.y) / t.k).toBeCloseTo(200)
  })

  it('does not let the map leave the frame', () => {
    expect(clampZoom({ k: 0.5, x: 100, y: 100 }, 1000, 500)).toEqual({ k: 1, x: 0, y: 0 })
    expect(clampZoom({ k: 2, x: -5000, y: 50 }, 1000, 500)).toEqual({ k: 2, x: -1000, y: 0 })
  })

  it('lets you pan to what is drawn outside the frame', () => {
    // Канары ниже кадра: при k = 1 до них можно доехать вниз, но не дальше
    expect(clampZoom({ k: 1, x: 0, y: -900 }, 1000, 500, [0, 0, 1000, 800])).toEqual({ k: 1, x: 0, y: -300 })
  })
})

const DATA: GeoData = {
  countries: [
    { country: 'Russia', country_code: 'RU', count: 12, unique_ips: 40 },
    { country: 'Netherlands', country_code: 'NL', count: 2, unique_ips: 2 },
  ],
  cities: [],
  regions: [
    {
      code: 'RU-KHA', country_code: 'RU', count: 9, unique_ips: 11,
      cities: [{ city: 'Khabarovsk', count: 9 }],
      nodes: [{ uuid: 'n1', name: 'Москва — вход', count: 3 }],
      users: [{ uuid: 'u1', username: 'alice', status: 'ACTIVE', connections: 42 }],
    },
  ],
  regions_unknown: [{ country_code: 'RU', count: 3, unique_ips: 5 }],
}

function renderExplorer(view = 'RU') {
  return render(
    <MemoryRouter>
      <GeoExplorer data={DATA} view={view} onViewChange={() => {}} metric="users" onMetricChange={() => {}} />
    </MemoryRouter>,
  )
}

describe('GeoExplorer', () => {
  afterEach(cleanup)

  it('draws every subject and lists the regions with data', () => {
    const { container } = renderExplorer('RU')
    expect(container.querySelectorAll('path[data-id^="RU-"]').length).toBe(83)
    expect(screen.getByRole('button', { name: /Хабаровский край/ })).toBeInTheDocument()
    expect(screen.getByText(/У 3 пользователей \(5 IP\) есть адреса без региона/)).toBeInTheDocument()
  })

  it('opens region details on click and closes them', () => {
    const { container } = renderExplorer('RU')
    fireEvent.click(container.querySelector('path[data-id="RU-KHA"]')!)
    const panel = screen.getByRole('heading', { name: 'Хабаровский край' }).closest('div.space-y-3') as HTMLElement
    expect(within(panel).getByText('Khabarovsk')).toBeInTheDocument()
    expect(within(panel).getByText('Москва — вход')).toBeInTheDocument()
    expect(within(panel).getByText('alice')).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: 'Сбросить выбор' }))
    expect(screen.queryByRole('heading', { name: 'Хабаровский край' })).not.toBeInTheDocument()
  })

  it('shows countries in the world view', () => {
    const { container } = renderExplorer('world')
    expect(container.querySelector('path[data-id="NL"]')).not.toBeNull()
    fireEvent.click(container.querySelector('path[data-id="RU"]')!)
    expect(screen.getByRole('button', { name: /Регионы страны/ })).toBeInTheDocument()
  })

  it('loads the regions of another country on demand', async () => {
    const data: GeoData = {
      countries: [{ country: 'Germany', country_code: 'DE', count: 4, unique_ips: 6 }],
      cities: [],
      regions: [{ code: 'DE-BY', country_code: 'DE', count: 4, unique_ips: 6, cities: [], nodes: [], users: [] }],
    }
    const { container } = render(
      <MemoryRouter>
        <GeoExplorer data={data} view="DE" onViewChange={() => {}} metric="users" onMetricChange={() => {}} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('button', { name: /Бавария/ })).toBeInTheDocument()
    expect(container.querySelectorAll('path[data-id^="DE-"]').length).toBe(16)
  })
})
