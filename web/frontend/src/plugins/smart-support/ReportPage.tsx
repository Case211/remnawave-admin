import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  ChevronDown,
  ChevronUp,
  Cpu,
  Globe2,
  Lightbulb,
  ShieldAlert,
  Smartphone,
  Sparkles,
  Users as UsersIcon,
} from 'lucide-react'

import LicenseBanner from './LicenseBanner'
import { asLicenseError, fetchReport } from './api'
import type { Hypothesis, ReportResponse } from './types'

/**
 * /plugins/smart-support/report/:uuid — single-page diagnostic.
 *
 * Step 1 layout: simple stack of section cards. The richer 4-column
 * layout from the roadmap lands when more sections actually have data
 * (rule engine + correlations); for now an honest stack avoids empty
 * "decoration" columns on a sparse panel.
 */
export default function ReportPage() {
  const { t } = useTranslation()
  const { uuid = '' } = useParams<{ uuid: string }>()

  const { data, isLoading, error } = useQuery({
    queryKey: ['smart-support-report', uuid],
    queryFn: () => fetchReport(uuid),
    enabled: uuid.length === 36,
    retry: false,
    staleTime: 30_000,
  })

  const licenseError = useMemo(() => (error ? asLicenseError(error) : null), [error])

  if (licenseError) {
    return (
      <div className="space-y-6">
        <BackLink />
        <LicenseBanner error={licenseError} />
      </div>
    )
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="glass-card p-6 text-sm text-dark-300">{t('common.loading')}</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="glass-card p-6 text-sm text-amber-300">
          {t('plugins.smart_support.report.error')}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <ReportHeader report={data} />
      <div className="grid gap-6 lg:grid-cols-2">
        <HypothesesCard report={data} />
        <AIAnalysisCard report={data} />
        <UserCard report={data} />
        <ClientCard report={data} />
        <NodesCard report={data} />
        <CorrelationsCard report={data} />
        <HistoryCard report={data} />
        <ViolationsCard report={data} />
      </div>
    </div>
  )
}


function BackLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/plugins/smart-support"
      className="inline-flex items-center gap-2 text-sm text-dark-300 hover:text-white transition-colors"
    >
      <ArrowLeft className="w-4 h-4" />
      {t('plugins.smart_support.report.back_to_search')}
    </Link>
  )
}


function ReportHeader({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const u = report.user
  return (
    <div className="glass-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">
            {u.username || u.email || u.uuid}
          </h1>
          <p className="mt-1 text-xs text-dark-400 font-mono">{u.uuid}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-dark-300">
          <span>
            {t('plugins.smart_support.report.generated_at', {
              ts: new Date(report.generated_at).toLocaleString(),
            })}
          </span>
        </div>
      </div>
    </div>
  )
}


function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: typeof UsersIcon
  children: React.ReactNode
}) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-dark-300" />
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">{title}</h2>
      </div>
      {children}
    </div>
  )
}


function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-dark-400 shrink-0">{label}</span>
      <span className="text-white text-right truncate">{value ?? '—'}</span>
    </div>
  )
}


/**
 * Top-of-page card with the rule engine's ranked guesses. We show the
 * top 3 prominently and tuck the rest behind a "show more" toggle so a
 * busy operator sees the most likely cause without scanning every rule.
 */
function HypothesesCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const items = report.hypotheses
  if (items.length === 0) return null

  const top = items.slice(0, 3)
  const rest = items.slice(3)

  return (
    <div className="glass-card p-5 lg:col-span-2">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-4 h-4 text-emerald-400" />
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.smart_support.report.sections.hypotheses')}
        </h2>
      </div>
      <ul className="space-y-2">
        {top.map((h) => (
          <HypothesisRow key={h.rule_id} h={h} />
        ))}
        {expanded &&
          rest.map((h) => <HypothesisRow key={h.rule_id} h={h} />)}
      </ul>
      {rest.length > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 inline-flex items-center gap-1 text-xs text-dark-300 hover:text-white transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-3 h-3" />
              {t('plugins.smart_support.report.hypotheses.show_less')}
            </>
          ) : (
            <>
              <ChevronDown className="w-3 h-3" />
              {t('plugins.smart_support.report.hypotheses.show_more', { n: rest.length })}
            </>
          )}
        </button>
      )}
    </div>
  )
}


/**
 * AI summary + extra hypotheses. Renders nothing if AI is disabled or
 * the call fell through (no provider answered) — silently downgrading
 * is the right move because the rest of the report is still useful.
 */
function AIAnalysisCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const a = report.ai_analysis
  if (!a) return null
  return (
    <div className="glass-card p-5 lg:col-span-2">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
            {t('plugins.smart_support.report.sections.ai_analysis')}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200">
            {a.provider_used}
            {a.model ? ` · ${a.model}` : ''}
          </span>
          <span className="text-[10px] uppercase tracking-wider text-dark-300">
            {t(`plugins.smart_support.report.ai_confidence.${a.confidence}`)}
          </span>
        </div>
      </div>
      <p className="text-sm text-dark-100 leading-relaxed whitespace-pre-line">{a.summary}</p>
      {a.extra_hypotheses.length > 0 && (
        <ul className="mt-4 space-y-2">
          {a.extra_hypotheses.map((h) => (
            <HypothesisRow
              key={h.rule_id}
              h={{
                rule_id: h.rule_id,
                title: h.title,
                detail: h.detail,
                severity: h.severity,
                confidence: h.confidence,
                suggested_action: h.suggested_action,
              }}
            />
          ))}
        </ul>
      )}
    </div>
  )
}


function HypothesisRow({ h }: { h: Hypothesis }) {
  const { t } = useTranslation()
  const palette = severityPalette(h.severity)
  // Prefer the localised title/detail if the rule has a translation key,
  // otherwise fall back to whatever the backend provided. This lets us
  // ship new rules from the plugin without a frontend release while the
  // i18n catch-up.
  const title = t(`plugins.smart_support.rules.${h.rule_id}.title`, { defaultValue: h.title })
  const detailKey = `plugins.smart_support.rules.${h.rule_id}.detail`
  const localisedDetail = t(detailKey, { defaultValue: '' })
  const detail = h.detail || localisedDetail
  const action = h.suggested_action
    ? t(`plugins.smart_support.report.hypotheses.suggested.${h.suggested_action}`, {
        defaultValue: h.suggested_action,
      })
    : null
  const confidencePct = Math.round(h.confidence * 100)

  return (
    <li
      className={`flex items-start gap-3 rounded-lg border-l-2 px-3 py-2 ${palette.bg} ${palette.border}`}
    >
      <AlertCircle className={`w-4 h-4 mt-0.5 shrink-0 ${palette.icon}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span className="text-sm font-medium text-white">{title}</span>
          <span className="text-[11px] text-dark-300">
            {t('plugins.smart_support.report.hypotheses.confidence', { pct: confidencePct })}
          </span>
        </div>
        {detail && <p className="mt-0.5 text-xs text-dark-200">{detail}</p>}
        {action && (
          <span className="mt-1 inline-block text-[11px] text-emerald-300">→ {action}</span>
        )}
      </div>
    </li>
  )
}


function severityPalette(severity: Hypothesis['severity']) {
  switch (severity) {
    case 'high':
      return {
        bg: 'bg-red-500/5',
        border: 'border-red-500/60',
        icon: 'text-red-400',
      }
    case 'medium':
      return {
        bg: 'bg-amber-500/5',
        border: 'border-amber-500/60',
        icon: 'text-amber-400',
      }
    default:
      return {
        bg: 'bg-dark-700/30',
        border: 'border-dark-500/60',
        icon: 'text-dark-300',
      }
  }
}


function UserCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const u = report.user
  return (
    <Section title={t('plugins.smart_support.report.sections.user')} icon={UsersIcon}>
      <KV label={t('plugins.smart_support.report.fields.status')} value={u.status} />
      <KV label={t('plugins.smart_support.report.fields.expire_at')} value={fmtDate(u.expire_at)} />
      <KV
        label={t('plugins.smart_support.report.fields.days_left')}
        value={u.days_until_expire ?? '—'}
      />
      <KV
        label={t('plugins.smart_support.report.fields.traffic')}
        value={
          u.traffic.percent !== null && u.traffic.percent !== undefined
            ? `${fmtBytes(u.traffic.used_bytes)} / ${fmtBytes(u.traffic.limit_bytes)} (${u.traffic.percent}%)`
            : fmtBytes(u.traffic.used_bytes)
        }
      />
      <KV
        label={t('plugins.smart_support.report.fields.hwid')}
        value={`${u.hwid_devices.length}/${u.hwid_limit ?? '∞'}`}
      />
      {u.hwid_devices.some((d) => d.is_blacklisted) && (
        <div className="mt-2 text-xs text-amber-400">
          {t('plugins.smart_support.report.fields.hwid_blacklisted')}
        </div>
      )}
      {u.active_squads.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-dark-400 mb-1">
            {t('plugins.smart_support.report.fields.squads')}
          </div>
          <div className="flex flex-wrap gap-1">
            {u.active_squads.map((s) => (
              <span
                key={s}
                className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </Section>
  )
}


function ClientCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const c = report.client
  if (!c.last_app && !c.raw_user_agent) {
    return (
      <Section title={t('plugins.smart_support.report.sections.client')} icon={Smartphone}>
        <p className="text-sm text-dark-400">{t('plugins.smart_support.report.client_unknown')}</p>
      </Section>
    )
  }
  return (
    <Section title={t('plugins.smart_support.report.sections.client')} icon={Smartphone}>
      <KV label={t('plugins.smart_support.report.fields.app')} value={c.last_app} />
      <KV label={t('plugins.smart_support.report.fields.version')} value={c.last_version} />
      <KV
        label={t('plugins.smart_support.report.fields.last_request')}
        value={fmtDate(c.last_request_at)}
      />
      {c.is_outdated && (
        <div className="mt-2 text-xs text-amber-400">
          {t('plugins.smart_support.report.fields.outdated_warning')}
        </div>
      )}
    </Section>
  )
}


function NodesCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  if (report.nodes.length === 0) {
    return (
      <Section title={t('plugins.smart_support.report.sections.nodes')} icon={Cpu}>
        <p className="text-sm text-dark-400">{t('plugins.smart_support.report.nodes_empty')}</p>
      </Section>
    )
  }
  return (
    <Section title={t('plugins.smart_support.report.sections.nodes')} icon={Cpu}>
      <ul className="divide-y divide-[var(--glass-border)]">
        {report.nodes.map((n) => (
          <li key={n.uuid} className="py-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-white">{n.name || n.uuid}</span>
              <span className="text-[10px] uppercase tracking-wider text-dark-300">
                {n.user_active_here
                  ? t('plugins.smart_support.report.nodes_active')
                  : n.is_connected
                    ? t('plugins.smart_support.report.nodes_online')
                    : t('plugins.smart_support.report.nodes_offline')}
              </span>
            </div>
            <div className="mt-0.5 text-xs text-dark-300">
              CPU {fmtPct(n.cpu_usage)} · RAM {fmtPct(n.memory_usage)} · Disk {fmtPct(n.disk_usage)}
            </div>
          </li>
        ))}
      </ul>
    </Section>
  )
}


function HistoryCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  const h = report.history_24h
  return (
    <Section title={t('plugins.smart_support.report.sections.history')} icon={Globe2}>
      <KV label={t('plugins.smart_support.report.fields.connections')} value={h.total_connections} />
      <KV label={t('plugins.smart_support.report.fields.unique_ips')} value={h.unique_ips} />
      <KV
        label={t('plugins.smart_support.report.fields.unique_countries')}
        value={h.unique_countries}
      />
      <KV label={t('plugins.smart_support.report.fields.unique_asns')} value={h.unique_asns} />
      {h.anomalies.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-amber-400 mb-1">
            {t('plugins.smart_support.report.fields.anomalies')}
          </div>
          <ul className="text-xs text-dark-200 list-disc pl-4">
            {h.anomalies.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  )
}


function CorrelationsCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  if (report.correlations.length === 0) {
    return (
      <Section title={t('plugins.smart_support.report.sections.correlations')} icon={Sparkles}>
        <p className="text-sm text-dark-400">
          {t('plugins.smart_support.report.correlations_empty')}
        </p>
      </Section>
    )
  }
  return (
    <Section title={t('plugins.smart_support.report.sections.correlations')} icon={Sparkles}>
      <ul className="divide-y divide-[var(--glass-border)]">
        {report.correlations.map((c) => {
          const minutes = Math.max(
            1,
            Math.round(
              (new Date(c.window_end).getTime() - new Date(c.window_start).getTime()) / 60000,
            ),
          )
          return (
            <li key={`${c.kind}:${c.key}`} className="py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200 mr-2">
                    {c.kind}
                  </span>
                  <span className="text-white font-mono text-xs">{c.label || c.key}</span>
                </div>
                <span className="text-amber-400 text-xs whitespace-nowrap">
                  {t('plugins.smart_support.report.correlations_affected', { n: c.affected_users })}
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-dark-400">
                {t('plugins.smart_support.report.correlations_window', { minutes })}
              </div>
            </li>
          )
        })}
      </ul>
    </Section>
  )
}


function ViolationsCard({ report }: { report: ReportResponse }) {
  const { t } = useTranslation()
  if (report.violations_recent.length === 0) {
    return (
      <Section title={t('plugins.smart_support.report.sections.violations')} icon={ShieldAlert}>
        <p className="text-sm text-dark-400">{t('plugins.smart_support.report.violations_empty')}</p>
      </Section>
    )
  }
  return (
    <Section title={t('plugins.smart_support.report.sections.violations')} icon={ShieldAlert}>
      <ul className="divide-y divide-[var(--glass-border)]">
        {report.violations_recent.map((v) => (
          <li key={v.id} className="py-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-white">{v.reason || `#${v.id}`}</span>
              <span className="text-xs text-dark-300">{fmtDate(v.created_at)}</span>
            </div>
            <div className="text-xs text-dark-400">
              {v.action ?? '—'} · score {v.score?.toFixed(2) ?? '—'}
            </div>
          </li>
        ))}
      </ul>
    </Section>
  )
}


// ── small formatters ────────────────────────────────────────────────────

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function fmtBytes(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = value
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`
}

function fmtPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(0)}%`
}
