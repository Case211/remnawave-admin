import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { GeoData } from '@/api/advancedAnalytics'
import { ArrowUpRight, ChevronRight, MapPin, Server, Users, X } from '@/components/brand/icons'
import { countryFlag } from '@/components/nodes/nodeShared'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useOpenUser } from '@/lib/useOpenUser'
import { cn } from '@/lib/utils'
import { WORLD, areaName, hasRegionMap, metricOf, type AreaNames, type AreaStat, type GeoMetric, type GeoView } from './geoModel'

const TOP = 10
const USERS_SHOWN = 15

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-green-500/20 text-green-400',
  DISABLED: 'bg-red-500/20 text-red-400',
  EXPIRED: 'bg-yellow-500/20 text-yellow-400',
  LIMITED: 'bg-orange-500/20 text-orange-400',
}

interface GeoPanelProps {
  view: GeoView
  metric: GeoMetric
  stats: Map<string, AreaStat>
  data: GeoData
  /** Названия регионов из карты страны */
  names?: AreaNames
  /** Карта страны ещё грузится — вместо кодов регионов заглушки */
  namesReady: boolean
  selected: string | null
  onSelect: (id: string | null) => void
  onOpenCountry: (code: string) => void
}

/**
 * Справа от карты: топ областей, а по клику — карточка выбранной. Фокус
 * клавиатуры переходит в карточку и возвращается к строке списка при закрытии.
 */
export function GeoPanel(props: GeoPanelProps) {
  const [returnTo, setReturnTo] = useState<string | null>(null)
  const previous = useRef(props.selected)
  useEffect(() => {
    if (previous.current && !props.selected) setReturnTo(previous.current)
    previous.current = props.selected
  }, [props.selected])
  return props.selected
    ? <AreaDetails {...props} id={props.selected} />
    : <TopAreas {...props} focusId={returnTo} />
}

function Section({ title, children, extra }: { title: string; children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg-hover)]/20 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</h4>
        {extra}
      </div>
      {children}
    </div>
  )
}

function Bar({ value, max }: { value: number; max: number }) {
  return (
    <span className="h-1.5 w-14 shrink-0 overflow-hidden rounded-full bg-[var(--glass-border)]">
      <span className="block h-full rounded-full bg-primary" style={{ width: `${max > 0 ? Math.max(4, (value / max) * 100) : 0}%` }} />
    </span>
  )
}

function TopAreas({ view, metric, stats, data, names, namesReady, onSelect, focusId }: GeoPanelProps & { focusId: string | null }) {
  const { t, i18n } = useTranslation()
  const [all, setAll] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!focusId) return
    const row = listRef.current?.querySelector<HTMLElement>(`[data-area="${CSS.escape(focusId)}"]`)
    ;(row ?? listRef.current)?.focus({ preventScroll: true })
  }, [focusId])
  const rows = useMemo(
    () => [...stats.values()]
      .filter((s) => metricOf(s, metric) > 0)
      .sort((a, b) => metricOf(b, metric) - metricOf(a, metric)),
    [stats, metric],
  )
  const max = rows.length ? metricOf(rows[0], metric) : 0
  const shown = all ? rows : rows.slice(0, TOP)
  const unknown = view !== WORLD ? data.regions_unknown?.find((u) => u.country_code?.toUpperCase() === view) : undefined

  return (
    <Section
      title={view === WORLD ? t('analytics.geo.map.topCountries') : view === 'RU' ? t('analytics.geo.map.topRegionsRu') : t('analytics.geo.map.topRegions')}
      extra={<span className="text-[11px] text-muted-foreground">{metric === 'users' ? t('analytics.geo.map.metricUsers') : t('analytics.geo.map.metricIps')}</span>}
    >
      {rows.length === 0 ? (
        <p className="py-2 text-xs text-muted-foreground">
          {unknown && unknown.count > 0 ? t('analytics.geo.map.noKnownRegions') : t('analytics.geo.map.noAreaData')}
        </p>
      ) : !namesReady ? (
        <div className="space-y-2 py-1">
          {rows.slice(0, 5).map((s) => <Skeleton key={s.id} className="h-5 w-full" />)}
        </div>
      ) : (
        <div ref={listRef} tabIndex={-1} className="space-y-0.5 outline-none">
          {shown.map((s) => (
            <button
              key={s.id}
              type="button"
              data-area={s.id}
              onClick={() => onSelect(s.id)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-[var(--glass-bg-hover)]"
            >
              {view === WORLD && <span className="w-5 shrink-0 text-base leading-none">{countryFlag(s.id)}</span>}
              <span className="min-w-0 flex-1 truncate text-white">{areaName(s.id, i18n.language, names)}</span>
              <Bar value={metricOf(s, metric)} max={max} />
              <span className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-white">
                {metricOf(s, metric).toLocaleString()}
              </span>
            </button>
          ))}
          {rows.length > TOP && (
            <button
              type="button"
              onClick={() => setAll((v) => !v)}
              className="w-full pt-1 text-center text-[11px] text-primary-400 transition-colors hover:text-primary-300"
            >
              {all ? t('analytics.geo.map.showTop', { count: TOP }) : t('analytics.geo.map.showAll', { count: rows.length })}
            </button>
          )}
        </div>
      )}
      {unknown && unknown.count > 0 && (
        <p className="mt-2 border-t border-[var(--glass-border)] pt-2 text-[11px] leading-relaxed text-muted-foreground">
          {t('analytics.geo.map.unknownRegion', { count: unknown.count, ips: unknown.unique_ips.toLocaleString() })}
        </p>
      )}
    </Section>
  )
}

function AreaDetails({ view, metric, stats, data, names, namesReady, onSelect, onOpenCountry, id }: GeoPanelProps & { id: string }) {
  const { t, i18n } = useTranslation()
  const openUser = useOpenUser()
  const [allUsers, setAllUsers] = useState(false)
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => headingRef.current?.focus({ preventScroll: true }), [id])
  const stat = stats.get(id)
  const region = view !== WORLD ? data.regions?.find((r) => r.code === id) : undefined

  // Доля — от всех юзеров страны (для субъекта) или всех стран (для страны)
  const total = view !== WORLD
    ? data.countries.filter((c) => c.country_code?.toUpperCase() === view).reduce((sum, c) => sum + c.count, 0)
    : data.countries.reduce((sum, c) => sum + c.count, 0)
  const share = stat && total > 0 ? Math.round((stat.users / total) * 1000) / 10 : null

  const cities = useMemo(() => {
    if (region) return region.cities
    if (view !== WORLD) return []
    const names = new Set(data.countries.filter((c) => c.country_code?.toUpperCase() === id).map((c) => c.country))
    return data.cities
      .filter((c) => names.has(c.country))
      .map((c) => ({ city: c.city, count: c.unique_users }))
      .slice(0, TOP)
  }, [region, view, data, id])
  const maxCity = Math.max(0, ...cities.map((c) => c.count))
  const users = region?.users ?? []
  const shownUsers = allUsers ? users : users.slice(0, USERS_SHOWN)

  return (
    <div className="space-y-3">
      <Section
        title={view === WORLD ? t('analytics.geo.map.country') : view === 'RU' ? t('analytics.geo.map.regionRu') : t('analytics.geo.map.region')}
        extra={(
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-[var(--glass-bg-hover)] hover:text-white"
            aria-label={t('analytics.geo.map.clearSelection')}
            title={t('analytics.geo.map.clearSelection')}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      >
        <div className="flex items-center gap-2">
          {view === WORLD && <span className="text-xl leading-none">{countryFlag(id)}</span>}
          {namesReady ? (
            <h3 ref={headingRef} tabIndex={-1} className="text-base font-semibold text-white outline-none">
              {areaName(id, i18n.language, names)}
            </h3>
          ) : (
            <Skeleton className="h-5 w-40" />
          )}
        </div>
        {stat ? (
          // Плитка не уже подписи «ПОЛЬЗОВАТЕЛИ»: три в ряд — только когда влезают,
          // иначе третья уходит строкой ниже во всю ширину, а не наезжает на соседку
          <div className="mt-3 flex flex-wrap gap-2">
            <Fact label={t('analytics.geo.map.metricUsers')} value={stat.users.toLocaleString()} accent={metric === 'users'} />
            <Fact label={t('analytics.geo.map.metricIps')} value={stat.ips.toLocaleString()} accent={metric === 'ips'} />
            {share !== null && <Fact label={t('analytics.geo.map.share')} value={`${share}%`} />}
          </div>
        ) : (
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('analytics.geo.map.emptyArea')}</p>
        )}
        {view === WORLD && hasRegionMap(id) && (
          <button
            type="button"
            onClick={() => onOpenCountry(id)}
            className="mt-3 inline-flex items-center gap-1 rounded-md bg-primary/15 px-2.5 py-1.5 text-xs font-medium text-primary-400 transition-colors hover:bg-primary/25"
          >
            {t('analytics.geo.map.openRegions')}
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        )}
      </Section>

      {cities.length > 0 && (
        <Section title={t('analytics.geo.map.cities')}>
          <div className="space-y-1">
            {cities.map((c) => (
              <div key={c.city} className="flex items-center gap-2 px-1 text-sm">
                <MapPin className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-white">{c.city}</span>
                <Bar value={c.count} max={maxCity} />
                <span className="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-white">{c.count}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {region && region.nodes.length > 0 && (
        <Section title={t('analytics.geo.map.nodes')}>
          <div className="space-y-1">
            {region.nodes.map((n) => (
              <div key={n.uuid} className="flex items-center gap-2 px-1 text-sm">
                <Server className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-white">{n.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t('analytics.geo.uniqueUsers', { count: n.count })}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {users.length > 0 && (
        <Section title={t('analytics.geo.users')} extra={<span className="text-[11px] text-muted-foreground">{t('analytics.geo.connectionsColumn')}</span>}>
          <div className="max-h-[320px] space-y-0.5 overflow-y-auto pr-1">
            {shownUsers.map((u) => (
              <div
                key={u.uuid}
                className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-[var(--glass-bg-hover)]"
                {...openUser(u.uuid)}
              >
                <Users className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm text-white">{u.username || u.uuid.slice(0, 8)}</span>
                <Badge variant="secondary" className={cn('px-1 py-0 text-[10px]', STATUS_COLORS[u.status] || '')}>
                  {t(`analytics.status.${u.status}`, { defaultValue: u.status })}
                </Badge>
                <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
                  {u.connections.toLocaleString()}
                </span>
                <ArrowUpRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              </div>
            ))}
          </div>
          {users.length > USERS_SHOWN && !allUsers && (
            <button
              type="button"
              onClick={() => setAllUsers(true)}
              className="mt-1 w-full text-center text-[11px] text-primary-400 transition-colors hover:text-primary-300"
            >
              {t('analytics.geo.showAll', { count: users.length })}
            </button>
          )}
          {stat && stat.users > users.length && (
            <p className="mt-1 text-center text-[10px] text-muted-foreground">
              {t('analytics.geo.map.topUsersOnly', { count: users.length })}
            </p>
          )}
        </Section>
      )}
    </div>
  )
}

function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="min-w-0 flex-1 basis-[108px] rounded-md bg-[var(--glass-bg)] px-2 py-1.5">
      <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground" title={label}>{label}</p>
      <p className={cn('font-mono text-base font-semibold tabular-nums', accent ? 'text-primary-400' : 'text-white')}>{value}</p>
    </div>
  )
}
