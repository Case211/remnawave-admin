import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bot, Save, Sliders } from '@/components/brand/icons'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

import LicenseBanner from '@/components/plugins/license'
import {
  asLicenseError,
  fetchAISettings,
  fetchAIStatus,
  fetchSettings,
  updateAISettings,
  updateSettings,
} from './api'
import { CardSkeleton, Skeleton } from './primitives'
import type { ThresholdSettings } from './types'

/**
 * /plugins/smart-support/settings — operator-tunable thresholds.
 *
 * GET returns the *resolved* settings (defaults merged with DB overrides),
 * so empty inputs never appear: the operator always sees the active value
 * for every knob. PUT sends only fields the user actually edited so we
 * don't tread on values someone else changed in another tab.
 */
export default function SettingsPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['smart-support-settings'],
    queryFn: fetchSettings,
    retry: false,
    staleTime: 10_000,
  })

  const licenseError = useMemo(() => (error ? asLicenseError(error) : null), [error])

  // Local edits — populated on first successful load.
  const [draft, setDraft] = useState<ThresholdSettings>({})
  const [touched, setTouched] = useState<Set<keyof ThresholdSettings>>(new Set())

  useEffect(() => {
    if (data && touched.size === 0) {
      setDraft(data)
    }
  }, [data, touched.size])

  const mutation = useMutation({
    mutationFn: (patch: Partial<ThresholdSettings>) => updateSettings(patch),
    onSuccess: (fresh) => {
      setDraft(fresh)
      setTouched(new Set())
      qc.setQueryData(['smart-support-settings'], fresh)
      toast.success(t('plugins.smart_support.settings.saved'))
    },
    onError: () => {
      toast.error(t('plugins.smart_support.settings.save_error'))
    },
  })

  const onChange = (key: keyof ThresholdSettings, raw: string) => {
    setDraft((d) => ({ ...d, [key]: raw === '' ? null : Number(raw) }))
    setTouched((s) => new Set(s).add(key))
  }

  const onSave = () => {
    if (touched.size === 0) return
    const patch: Partial<ThresholdSettings> = {}
    for (const key of touched) {
      const v = draft[key]
      if (v === null || v === undefined || Number.isNaN(v as number)) continue
      ;(patch as Record<string, number>)[key as string] = v as number
    }
    mutation.mutate(patch)
  }

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
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-6">
          <CardSkeleton rows={4} />
          <CardSkeleton rows={4} />
          <CardSkeleton rows={3} />
        </div>
      </div>
    )
  }

  const dirty = touched.size > 0

  return (
    <div className="space-y-6">
      <BackLink />

      {/* Sticky strip — keeps the Save button reachable while the
          operator scrolls through threshold sections. ``backdrop-blur``
          lets sections show through faintly so the strip doesn't feel
          like a wall. */}
      <div className="flex items-center justify-between gap-3 sticky top-0 z-20 -mx-1 px-1 py-2 bg-[var(--bg,transparent)] backdrop-blur-md">
        <div className="flex items-center gap-2 min-w-0">
          <Sliders className="w-5 h-5 text-emerald-400 shrink-0" aria-hidden />
          <h1 className="text-xl sm:text-2xl font-bold text-white truncate">
            {t('plugins.smart_support.settings.title')}
          </h1>
          {dirty && (
            <span className="hidden sm:inline-flex items-center text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 shrink-0">
              {t('plugins.smart_support.settings.dirty', { defaultValue: 'unsaved' })}
            </span>
          )}
        </div>
        <Button onClick={onSave} disabled={!dirty || mutation.isPending} className="shrink-0">
          <Save className="w-4 h-4 mr-2" aria-hidden />
          {t('plugins.smart_support.settings.save')}
        </Button>
      </div>
      <p className="text-sm text-dark-300 -mt-3">
        {t('plugins.smart_support.settings.subtitle')}
      </p>

      <SettingsSection
        title={t('plugins.smart_support.settings.sections.node')}
        keys={['node_cpu_high', 'node_cpu_critical', 'node_memory_high', 'node_metrics_stale_seconds']}
        draft={draft}
        onChange={onChange}
      />
      <SettingsSection
        title={t('plugins.smart_support.settings.sections.traffic')}
        keys={['traffic_high', 'traffic_full', 'traffic_high_confidence', 'traffic_full_confidence']}
        draft={draft}
        onChange={onChange}
      />
      <SettingsSection
        title={t('plugins.smart_support.settings.sections.cluster_node')}
        keys={[
          'cluster_node_window_minutes',
          'cluster_node_reconnects_per_user',
          'cluster_node_min_affected',
        ]}
        draft={draft}
        onChange={onChange}
      />
      <SettingsSection
        title={t('plugins.smart_support.settings.sections.cluster_asn')}
        keys={['cluster_asn_window_minutes', 'cluster_asn_min_affected']}
        draft={draft}
        onChange={onChange}
      />
      <SettingsSection
        title={t('plugins.smart_support.settings.sections.worker')}
        keys={['correlation_recompute_seconds', 'correlation_max_age_minutes']}
        draft={draft}
        onChange={onChange}
      />

      <AISettingsSection />
    </div>
  )
}


/**
 * Cloud AI block: a single on/off toggle plus subscription and quota
 * state from entitlements. Provider keys and chains live on the
 * licensing server — the operator has nothing to configure here.
 */
function AISettingsSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['smart-support-ai-settings'],
    queryFn: fetchAISettings,
    retry: false,
    staleTime: 10_000,
  })

  const { data: status } = useQuery({
    queryKey: ['smart-support-ai-status'],
    queryFn: fetchAIStatus,
    retry: false,
    staleTime: 10_000,
    refetchInterval: 60_000,
  })

  const mutation = useMutation({
    mutationFn: (enabled: boolean) => updateAISettings({ enabled }),
    onSuccess: (fresh) => {
      qc.setQueryData(['smart-support-ai-settings'], fresh)
      qc.invalidateQueries({ queryKey: ['smart-support-ai-status'] })
      toast.success(t('plugins.smart_support.settings.saved'))
    },
    onError: () => {
      toast.error(t('plugins.smart_support.settings.save_error'))
    },
  })

  if (isLoading || !data) {
    return (
      <div className="glass-card p-5">
        <div className="text-sm text-dark-300">{t('common.loading')}</div>
      </div>
    )
  }

  const sub = status?.subscription_state ?? 'missing'
  const subStyles: Record<string, string> = {
    active: 'bg-emerald-500/15 text-emerald-300',
    grace: 'bg-amber-500/15 text-amber-300',
    expired: 'bg-red-500/15 text-red-300',
    missing: 'bg-[var(--glass-bg)] text-dark-300',
  }
  const quota = status?.quota
  const quotaPct =
    quota && quota.period_limit > 0 ? Math.min(100, (quota.used / quota.period_limit) * 100) : 0
  const quotaColor =
    quotaPct < 75 ? 'bg-emerald-400' : quotaPct < 95 ? 'bg-amber-400' : 'bg-red-400'

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Bot className="w-4 h-4 text-cyan-400" />
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.smart_support.settings.sections.ai')}
        </h2>
      </div>

      <p className="text-xs text-dark-400">{t('plugins.smart_support.settings.ai.cloud_hint')}</p>

      <div className="flex items-center gap-3">
        <Switch
          id="ai-enabled"
          checked={data.enabled}
          disabled={mutation.isPending}
          onCheckedChange={(v) => mutation.mutate(v)}
        />
        <Label htmlFor="ai-enabled" className="text-sm text-white">
          {t('plugins.smart_support.settings.ai.enabled')}
        </Label>
      </div>

      <div className="rounded-lg border border-[var(--glass-border)] p-3 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase tracking-wider text-dark-400">
            {t('plugins.smart_support.settings.ai.subscription')}
          </span>
          <span
            className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${subStyles[sub]}`}
          >
            {t(`plugins.smart_support.settings.ai.sub_state.${sub}`)}
          </span>
        </div>

        {quota && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-dark-300">{t('plugins.smart_support.settings.ai.quota')}</span>
              <span className="text-white font-mono">
                {quota.used} / {quota.period_limit}
                {quota.topup_left > 0 && (
                  <span className="text-emerald-300">
                    {' '}
                    {t('plugins.smart_support.settings.ai.quota_topup', { n: quota.topup_left })}
                  </span>
                )}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-[var(--glass-bg)] overflow-hidden">
              <div
                className={`h-full rounded-full ${quotaColor}`}
                style={{ width: `${quotaPct}%` }}
              />
            </div>
          </div>
        )}

        <Link
          to="/admin/plugins"
          className="inline-flex items-center gap-1.5 text-xs text-dark-300 hover:text-white transition-colors"
        >
          {t('plugins.smart_support.settings.ai.manage')}
        </Link>
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


function SettingsSection({
  title,
  keys,
  draft,
  onChange,
}: {
  title: string
  keys: (keyof ThresholdSettings)[]
  draft: ThresholdSettings
  onChange: (key: keyof ThresholdSettings, raw: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="glass-card p-5 space-y-4">
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider">{title}</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        {keys.map((k) => {
          const value = draft[k]
          return (
            <div key={k as string} className="space-y-1.5">
              <Label htmlFor={k as string} className="text-xs text-dark-300">
                {t(`plugins.smart_support.settings.fields.${k}.label`)}
              </Label>
              <Input
                id={k as string}
                type="number"
                step="any"
                value={value === null || value === undefined ? '' : String(value)}
                onChange={(e) => onChange(k, e.target.value)}
                className="h-9"
              />
              <p className="text-[11px] text-dark-400">
                {t(`plugins.smart_support.settings.fields.${k}.help`)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
