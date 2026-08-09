import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Activity } from '@/components/brand/icons'

import LicenseBanner from '@/components/plugins/license'

import { asLicenseError, fetchFlow } from './api'
import type { FlowData, FlowNode, FlowSink } from './types'

/**
 * /plugins/live-flow — живая схема трафика «пользователи → ноды → выход».
 *
 * Толщина пунктира и число в кружке — сколько пользователей сейчас на ноде
 * (``nodes.users_online`` от панели), бегущий пунктир — на ноде есть исходящий
 * трафик. Блоки выходов берутся из конфиг-профилей, поэтому WARP или цепочка
 * появляются на схеме сами, как только добавлены в профиль. Чисел по таким
 * веткам у панели нет (выбор аутбаунда живёт только в access.log ядра) —
 * они помечены как «нет измерений».
 */

const NH = 56
const STEP = 72
const TOP = 34
const NODE_X = 470
const NODE_W = 240
const USER_X = 40
const USER_W = 170
const SINK_X = 962
const SINK_W = 178

function widthFor(users: number, max: number): number {
  return users ? 1.6 + (users / Math.max(max, 1)) * 6.4 : 1.2
}

function FlowSvg({ data }: { data: FlowData }) {
  const { t } = useTranslation()
  const nodes = data.nodes
  const maxUsers = Math.max(1, ...nodes.map((n) => n.users))

  const cy = (i: number) => TOP + i * STEP + NH / 2
  const stackCy = nodes.length ? (cy(0) + cy(nodes.length - 1)) / 2 : 200
  const height = TOP + Math.max(nodes.length, 2) * STEP + 34

  const ordered = [
    ...data.sinks.filter((s) => s.kind === 'internet'),
    ...data.sinks.filter((s) => s.kind !== 'internet'),
  ]
  const sinkTop = stackCy - (ordered.length * NH + (ordered.length - 1) * 24) / 2
  const sinkCy = (i: number) => sinkTop + i * (NH + 24) + NH / 2
  const hasInternet = ordered.length > 0 && ordered[0].kind === 'internet'
  const internetCy = hasInternet ? sinkCy(0) : stackCy

  const sinkSub = (sink: FlowSink) =>
    sink.kind === 'internet' ? t('plugins.live_flow.sink_internet') : t('plugins.live_flow.sink_no_data')

  const nodeSub = (n: FlowNode) =>
    n.users
      ? `↑ ${n.tx_mbps.toFixed(2)} · ↓ ${n.rx_mbps.toFixed(2)} ${t('plugins.live_flow.mbps')}`
      : t('plugins.live_flow.node_idle')

  return (
    <svg viewBox={`0 0 1180 ${height}`} className="block w-full h-auto" role="img">
      <title>{t('plugins.live_flow.title')}</title>
      <style>{`
        .lf-flow { fill: none; stroke-linecap: round; stroke-dasharray: 10 8; }
        .lf-flow-live { stroke: rgb(99 102 241 / .75); animation: lf-dash 1.1s linear infinite; }
        .lf-flow-idle { stroke: rgb(148 163 184 / .3); }
        @keyframes lf-dash { to { stroke-dashoffset: -36; } }
        @media (prefers-reduced-motion: reduce) { .lf-flow-live { animation: none; } }
      `}</style>

      <text x={USER_X} y={18} className="fill-dark-400 text-[11px] tracking-widest">
        {t('plugins.live_flow.col_users').toUpperCase()}
      </text>
      <text x={NODE_X} y={18} className="fill-dark-400 text-[11px] tracking-widest">
        {t('plugins.live_flow.col_nodes').toUpperCase()}
      </text>
      <text x={SINK_X} y={18} className="fill-dark-400 text-[11px] tracking-widest">
        {t('plugins.live_flow.col_sink').toUpperCase()}
      </text>

      {nodes.map((n, i) => {
        if (!n.users) return null
        const y = cy(i)
        const w = widthFor(n.users, maxUsers)
        const live = n.tx_mbps > 0
        const cls = `lf-flow ${live ? 'lf-flow-live' : 'lf-flow-idle'}`
        return (
          <g key={`fl-${n.uuid}`}>
            <path
              className={cls}
              strokeWidth={w}
              d={`M ${USER_X + USER_W} ${stackCy} C 340 ${stackCy}, 340 ${y}, ${NODE_X} ${y}`}
            />
            {hasInternet && (
              <path
                className={cls}
                strokeWidth={w}
                d={`M ${NODE_X + NODE_W} ${y} C 840 ${y}, 840 ${internetCy}, ${SINK_X} ${internetCy}`}
              />
            )}
          </g>
        )
      })}

      {nodes.map((n, i) => {
        if (!n.users) return null
        const by = (stackCy + cy(i)) / 2
        return (
          <g key={`bd-${n.uuid}`}>
            <circle cx={340} cy={by} r={14} className="fill-dark-800 stroke-primary-500/50" strokeWidth={1} />
            <text
              x={340}
              y={by}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-white text-xs font-medium"
            >
              {n.users}
            </text>
          </g>
        )
      })}

      <g>
        <rect
          x={USER_X}
          y={stackCy - 33}
          width={USER_W}
          height={66}
          rx={8}
          className="fill-dark-800 stroke-dark-600"
          strokeWidth={1}
        />
        <text
          x={USER_X + USER_W / 2}
          y={stackCy - 10}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-white text-sm font-medium"
        >
          {t('plugins.live_flow.users_box')}
        </text>
        <text
          x={USER_X + USER_W / 2}
          y={stackCy + 12}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-dark-300 text-xs"
        >
          {t('plugins.live_flow.users_online', { count: data.total_users })}
        </text>
      </g>

      {nodes.map((n, i) => {
        const y = TOP + i * STEP
        return (
          <g key={n.uuid} opacity={n.users ? 1 : 0.45}>
            <rect
              x={NODE_X}
              y={y}
              width={NODE_W}
              height={NH}
              rx={8}
              className="fill-dark-800 stroke-dark-600"
              strokeWidth={1}
            />
            <text
              x={NODE_X + NODE_W / 2}
              y={y + 21}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-white text-sm font-medium"
            >
              {n.name}
            </text>
            <text
              x={NODE_X + NODE_W / 2}
              y={y + 39}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-dark-300 text-xs"
            >
              {nodeSub(n)}
            </text>
          </g>
        )
      })}

      {ordered.map((sink, i) => {
        const y = sinkCy(i) - NH / 2
        return (
          <g key={sink.tag} opacity={sink.kind === 'internet' ? 1 : 0.45}>
            <rect
              x={SINK_X}
              y={y}
              width={SINK_W}
              height={NH}
              rx={8}
              className="fill-dark-800 stroke-dark-600"
              strokeWidth={1}
            />
            {sink.kind === 'internet' && (
              <g
                transform={`translate(${SINK_X + 16}, ${y + 12}) scale(0.75)`}
                className="stroke-dark-300"
                fill="none"
                strokeWidth={1.6}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx={12} cy={12} r={10} />
                <path d="M2 12h20" />
                <path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
              </g>
            )}
            <text
              x={SINK_X + SINK_W / 2}
              y={y + 21}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-white text-sm font-medium"
            >
              {sink.title}
            </text>
            <text
              x={SINK_X + SINK_W / 2}
              y={y + 39}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-dark-300 text-xs"
            >
              {sinkSub(sink)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function FlowPage() {
  const { t } = useTranslation()

  const flow = useQuery({
    queryKey: ['live-flow-data'],
    queryFn: fetchFlow,
    refetchInterval: 5000,
    retry: false,
  })

  const licenseError = asLicenseError(flow.error)
  const data = flow.data ?? null
  const extraSinks = data?.sinks.filter((s) => s.kind !== 'internet' && s.kind !== 'block') ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-primary-500/15 flex items-center justify-center shrink-0">
            <Activity className="w-5 h-5 text-primary-400" aria-hidden />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-white truncate">
              {t('plugins.live_flow.title')}
            </h1>
            <p className="text-sm text-dark-300">{t('plugins.live_flow.subtitle')}</p>
          </div>
        </div>
        {data && (
          <div className="text-sm text-dark-300 shrink-0">
            <span className="text-primary-400 font-medium">
              {t('plugins.live_flow.users_online', { count: data.total_users })}
            </span>
            {' · '}
            {t('plugins.live_flow.nodes_count', { count: data.nodes.length })}
          </div>
        )}
      </div>

      {licenseError && <LicenseBanner error={licenseError} />}

      {!licenseError && flow.isError && (
        <p className="text-sm text-red-400">{t('plugins.live_flow.load_error')}</p>
      )}

      {!licenseError && data && (
        <div className="rounded-2xl border border-dark-600 bg-dark-900/60 p-4">
          <FlowSvg data={data} />
          <div className="flex flex-wrap gap-x-5 gap-y-2 mt-3 text-xs text-dark-300">
            <span className="flex items-center gap-2">
              <span className="inline-block w-6 border-t-2 border-dashed border-primary-400" aria-hidden />
              {t('plugins.live_flow.legend_live')}
            </span>
            <span className="flex items-center gap-2">
              <span className="inline-block w-6 border-t-2 border-dashed border-dark-400" aria-hidden />
              {t('plugins.live_flow.legend_idle')}
            </span>
            <span>{t('plugins.live_flow.legend_badge')}</span>
            {extraSinks.length > 0 && (
              <span>
                {t('plugins.live_flow.legend_no_numbers', {
                  sinks: extraSinks.map((s) => s.title).join(', '),
                })}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
