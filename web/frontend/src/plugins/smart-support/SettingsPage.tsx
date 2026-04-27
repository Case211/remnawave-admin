import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, Sliders } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import LicenseBanner from './LicenseBanner'
import { asLicenseError, fetchSettings, updateSettings } from './api'
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
        <div className="glass-card p-6 text-sm text-dark-300">{t('common.loading')}</div>
      </div>
    )
  }

  const dirty = touched.size > 0

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sliders className="w-5 h-5 text-emerald-400" />
          <h1 className="text-2xl font-bold text-white">
            {t('plugins.smart_support.settings.title')}
          </h1>
        </div>
        <Button onClick={onSave} disabled={!dirty || mutation.isPending}>
          <Save className="w-4 h-4 mr-2" />
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
