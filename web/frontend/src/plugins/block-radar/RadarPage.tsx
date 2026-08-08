import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, CheckCircle, Server, Settings, ShieldBan, Zap } from '@/components/brand/icons'

import LicenseBanner from '@/components/plugins/license'

import { asLicenseError, fetchAlerts, fetchHosters, fetchStatus } from './api'
import type { RadarAlert, RadarNodeDip, RadarStatus, RadarTick } from './types'

const TRANSPORT_LABELS: Record<string, string> = {
  reality: 'Reality',
  ws: 'WebSocket',
  xhttp: 'XHTTP',
  tls: 'TLS',
  grpc: 'gRPC',
  trojan: 'Trojan',
  ss: 'Shadowsocks',
}

function transportLabel(t: (k: string) => string, transport: string): string {
  if (transport === 'mixed') return t('plugins.block_radar.transport_mixed')
  if (transport === 'other') return t('plugins.block_radar.transport_other')
  return TRANSPORT_LABELS[transport] ?? transport
}

function asnLabel(org: string | null | undefined, asn: number): string {
  return org ? `${org} (AS${asn})` : `AS${asn}`
}

/** Оператор алерта: у агрегата по хостеру его нет, там нулевой ASN. */
function opLabel(t: (k: string) => string, alert: RadarAlert): string {
  if (alert.scope === 'hoster' || !alert.op_asn) {
    return t('plugins.block_radar.all_operators')
  }
  return asnLabel(alert.op_org, alert.op_asn)
}

/**
 * /plugins/block-radar — сеть панелей и её инциденты.
 *
 * Данные локальные (таблица плагина + статус последнего тика), поэтому
 * страница дешёвая и обновляется каждые 30 секунд. 402 от бэка — плагин
 * куплен, но подписка неактивна — показываем общий баннер лицензии.
 */
export default function RadarPage() {
  const { t } = useTranslation()

  const status = useQuery({
    queryKey: ['block-radar-status'],
    queryFn: fetchStatus,
    retry: false,
    refetchInterval: 30_000,
  })
  const open = useQuery({
    queryKey: ['block-radar-alerts-open'],
    queryFn: () => fetchAlerts({ active: true, limit: 100 }),
    retry: false,
    refetchInterval: 30_000,
  })
  const history = useQuery({
    queryKey: ['block-radar-alerts-history'],
    queryFn: () => fetchAlerts({ active: false, limit: 25 }),
    retry: false,
    refetchInterval: 60_000,
  })

  const licenseError = useMemo(
    () => (status.error ? asLicenseError(status.error) : null),
    [status.error],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Activity className="w-6 h-6 text-emerald-400 shrink-0" aria-hidden />
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-white truncate">
              {t('plugins.block_radar.title')}
            </h1>
            <p className="text-sm text-dark-300">{t('plugins.block_radar.subtitle')}</p>
          </div>
        </div>
        <Link
          to="/plugins/block-radar/settings"
          className="inline-flex items-center gap-2 text-sm text-dark-300 hover:text-white transition-colors shrink-0"
        >
          <Settings className="w-4 h-4" aria-hidden />
          {t('plugins.block_radar.settings_link')}
        </Link>
      </div>

      {licenseError && <LicenseBanner error={licenseError} />}

      {!licenseError && <ExpiryNotice status={status.data ?? null} />}

      {!licenseError && <StatusCard tick={status.data?.last_tick ?? null} />}

      {(status.data?.open_dips?.length ?? 0) > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
            <ShieldBan className="w-4 h-4 text-amber-400" aria-hidden />
            {t('plugins.block_radar.dips_title')}
          </h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {(status.data?.open_dips ?? []).map((dip) => (
              <NodeDipCard key={dip.node_uuid} dip={dip} />
            ))}
          </div>
        </section>
      )}

      {!licenseError && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
            <ShieldBan className="w-4 h-4 text-red-400" aria-hidden />
            {t('plugins.block_radar.open_title')}
            {open.data && open.data.total > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">
                {open.data.total}
              </span>
            )}
          </h2>
          {open.data && open.data.items.length === 0 && (
            <div className="glass-card p-5 flex items-center gap-3">
              <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" aria-hidden />
              <p className="text-sm text-dark-200">{t('plugins.block_radar.all_quiet')}</p>
            </div>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {(open.data?.items ?? []).map((a) => (
              <AlertCard key={a.id} alert={a} />
            ))}
          </div>
        </section>
      )}

      {!licenseError && (history.data?.items.length ?? 0) > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
            {t('plugins.block_radar.history_title')}
          </h2>
          <div className="glass-card p-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-dark-400">
                  <th className="px-3 py-2">{t('plugins.block_radar.col_link')}</th>
                  <th className="px-3 py-2">{t('plugins.block_radar.col_kind')}</th>
                  <th className="px-3 py-2">{t('plugins.block_radar.col_since')}</th>
                  <th className="px-3 py-2">{t('plugins.block_radar.col_resolved')}</th>
                </tr>
              </thead>
              <tbody>
                {history.data!.items.map((a) => (
                  <tr key={a.id} className="border-t border-[var(--glass-border)] text-dark-200">
                    <td className="px-3 py-2">
                      {opLabel(t, a)} → {asnLabel(a.host_org, a.host_asn)} ·{' '}
                      {transportLabel(t, a.transport)}
                    </td>
                    <td className="px-3 py-2">
                      {t(
                        a.kind === 'operator_outage'
                          ? 'plugins.block_radar.kind_outage'
                          : 'plugins.block_radar.kind_block',
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{formatTs(a.since)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {a.resolved_at ? formatTs(a.resolved_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!licenseError && <HosterRating />}
    </div>
  )
}


/**
 * Рейтинг хостеров по данным всей сети панелей.
 *
 * Показываем только тех, кого достаточно долго видят несколько независимых
 * панелей. Пока сеть копится, таблица пуста — и тогда важнее показать, что
 * данные идут, чем нарисовать рейтинг из одного наблюдателя.
 */
function HosterRating() {
  const { t } = useTranslation()

  const rating = useQuery({
    queryKey: ['block-radar-hosters'],
    queryFn: fetchHosters,
    retry: false,
    refetchInterval: 300_000,
  })

  if (rating.isError || rating.data?.locked) return null

  const data = rating.data
  const items = data?.hosters ?? []

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
        <Server className="w-4 h-4 text-sky-400" aria-hidden />
        {t('plugins.block_radar.hosters_title')}
      </h2>

      {items.length === 0 ? (
        <div className="glass-card p-5">
          <p className="text-sm text-dark-300">
            {t('plugins.block_radar.hosters_pending', {
              count: data?.pending ?? 0,
              panels: data?.min_panels ?? 3,
            })}
          </p>
        </div>
      ) : (
        <div className="glass-card p-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-dark-400">
                <th className="px-3 py-2">{t('plugins.block_radar.col_hoster')}</th>
                <th className="px-3 py-2">{t('plugins.block_radar.col_panels')}</th>
                <th className="px-3 py-2">{t('plugins.block_radar.col_outages')}</th>
                <th className="px-3 py-2">{t('plugins.block_radar.col_blocks')}</th>
                <th className="px-3 py-2">{t('plugins.block_radar.col_recovery')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((h) => (
                <tr
                  key={h.asn}
                  className={`border-t border-[var(--glass-border)] text-dark-200 ${
                    h.mine ? 'bg-emerald-500/5' : ''
                  }`}
                >
                  <td className="px-3 py-2">
                    {asnLabel(h.org, h.asn)}
                    {h.mine && (
                      <span className="ml-2 text-[10px] uppercase tracking-wider text-emerald-400">
                        {t('plugins.block_radar.hoster_mine')}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{h.panels}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {h.outages_per_month.toFixed(1)}
                    <span className="text-dark-400 text-xs"> /мес</span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {h.blocks_per_month.toFixed(1)}
                    <span className="text-dark-400 text-xs"> /мес</span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {h.median_recovery_minutes != null
                      ? t('plugins.block_radar.minutes', { count: h.median_recovery_minutes })
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-xs text-dark-400">
            {t('plugins.block_radar.hosters_note', {
              days: data?.window_days ?? 30,
              panels: data?.min_panels ?? 3,
            })}
          </p>
        </div>
      )}
    </section>
  )
}


function StatusCard({ tick }: { tick: RadarTick | null }) {
  const { t } = useTranslation()

  if (!tick) {
    return (
      <div className="glass-card p-5">
        <p className="text-sm text-dark-300">{t('plugins.block_radar.status.never')}</p>
      </div>
    )
  }

  const items: Array<{ label: string; value: string }> = [
    { label: t('plugins.block_radar.status.last_tick'), value: formatTs(tick.at) },
    { label: t('plugins.block_radar.status.cells'), value: String(tick.cells ?? 0) },
    {
      label: t('plugins.block_radar.status.links'),
      value: `${tick.links_active ?? 0} / ${tick.links_zero ?? 0}`,
    },
    {
      label: t('plugins.block_radar.status.nodes'),
      value: `${(tick.nodes_total ?? 0) - (tick.nodes_skipped ?? 0)} / ${tick.nodes_total ?? 0}`,
    },
  ]

  return (
    <div className="glass-card p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Zap className="w-4 h-4 text-cyan-400" aria-hidden />
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.block_radar.status.title')}
        </h2>
        <span
          className={`ml-auto text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
            tick.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'
          }`}
        >
          {tick.ok
            ? t('plugins.block_radar.status.ok')
            : t(`plugins.block_radar.status.errors.${tick.error ?? 'exception'}`, {
                defaultValue: tick.error ?? 'error',
              })}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {items.map((it) => (
          <div key={it.label}>
            <div className="text-[11px] uppercase tracking-wider text-dark-400">{it.label}</div>
            <div className="text-white font-mono text-sm mt-0.5">{it.value}</div>
          </div>
        ))}
      </div>
      {tick.alerts_locked && (
        <p className="text-xs text-amber-300">{t('plugins.block_radar.status.alerts_locked')}</p>
      )}
    </div>
  )
}


function AlertCard({ alert }: { alert: RadarAlert }) {
  const { t } = useTranslation()
  const isOutage = alert.kind === 'operator_outage'

  return (
    <div
      className={`glass-card p-4 border-l-4 ${
        isOutage ? 'border-amber-500/70' : 'border-red-500/70'
      } space-y-2`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
            isOutage ? 'bg-amber-500/15 text-amber-300' : 'bg-red-500/15 text-red-300'
          }`}
        >
          {t(isOutage ? 'plugins.block_radar.kind_outage' : 'plugins.block_radar.kind_block')}
        </span>
        <span className="text-xs text-dark-400 ml-auto whitespace-nowrap">
          {formatTs(alert.since)}
        </span>
      </div>
      <div className="text-sm text-white font-medium">
        {transportLabel(t, alert.transport)} · {opLabel(t, alert)}
      </div>
      <div className="text-xs text-dark-300">
        {t('plugins.block_radar.card_host')}: {asnLabel(alert.host_org, alert.host_asn)}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-dark-300">
        {alert.online != null && alert.baseline != null && (
          <span>
            {t('plugins.block_radar.card_online')}:{' '}
            <span className="text-white font-mono">
              {alert.online} / {Math.round(alert.baseline)}
            </span>
          </span>
        )}
        {alert.panels != null && (
          <span>
            {t('plugins.block_radar.card_panels')}:{' '}
            <span className="text-white font-mono">{alert.panels}</span>
          </span>
        )}
      </div>
      {isOutage && alert.outage_summary && (
        <p className="text-xs text-dark-400">{alert.outage_summary}</p>
      )}
      {(alert.affected.nodes?.length ?? 0) > 0 && (
        <p className="text-xs text-dark-300">
          {t('plugins.block_radar.card_affected')}:{' '}
          <span className="text-white">{alert.affected.nodes!.join(', ')}</span>
        </p>
      )}
    </div>
  )
}


/**
 * Плашка «подписка на исходе». Загорается за неделю до конца, чтобы
 * владелец успел продлить — иначе радар просто однажды замолкает.
 */
function ExpiryNotice({ status }: { status: RadarStatus | null }) {
  const { t } = useTranslation()
  if (!status?.license_paid_until) return null

  const days = Math.floor((status.license_paid_until * 1000 - Date.now()) / 86_400_000)
  if (days > 7) return null

  const trial = status.license_tier === 'trial'
  const urgent = days <= 1
  const key =
    days > 1 ? 'expiry_days' : days === 1 ? 'expiry_tomorrow' : days === 0 ? 'expiry_today' : 'expiry_over'

  return (
    <div
      className={`glass-card p-4 flex items-start gap-3 border-l-4 ${
        urgent ? 'border-red-500/70' : 'border-amber-500/70'
      }`}
    >
      <Zap className={`w-5 h-5 shrink-0 ${urgent ? 'text-red-400' : 'text-amber-400'}`} aria-hidden />
      <div className="space-y-1">
        <p className="text-sm text-white font-medium">
          {t(`plugins.block_radar.${key}`, {
            days,
            what: t(trial ? 'plugins.block_radar.expiry_trial' : 'plugins.block_radar.expiry_sub'),
          })}
        </p>
        <p className="text-xs text-dark-300">{t('plugins.block_radar.expiry_hint')}</p>
      </div>
    </div>
  )
}


function NodeDipCard({ dip }: { dip: RadarNodeDip }) {
  const { t } = useTranslation()
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`

  return (
    <div className="glass-card p-4 border-l-4 border-amber-500/70 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">
          {t('plugins.block_radar.dip_badge')}
        </span>
        <span className="text-xs text-dark-400 ml-auto whitespace-nowrap">
          {formatTs(dip.since)}
        </span>
      </div>
      <div className="text-sm text-white font-medium">
        {dip.node_name || dip.node_uuid.slice(0, 8)}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-dark-300">
        <span>
          {t('plugins.block_radar.card_online')}:{' '}
          <span className="text-white font-mono">
            {dip.online} / {Math.round(dip.baseline_online)}
          </span>
        </span>
        <span>
          {t('plugins.block_radar.dip_share')}:{' '}
          <span className="text-white font-mono">
            {pct(dip.share)} / {pct(dip.baseline_share)}
          </span>
        </span>
      </div>
      <p className="text-xs text-dark-300">
        {t(dip.node_alive ? 'plugins.block_radar.dip_alive' : 'plugins.block_radar.dip_offline')}
      </p>
    </div>
  )
}


function formatTs(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}
