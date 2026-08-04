import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, Sliders } from '@/components/brand/icons'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import LicenseBanner from '@/components/plugins/license'

import { asLicenseError, fetchSettings, updateSettings } from './api'
import type { RadarSettings, RadarSettingsPatch } from './types'

const TOGGLES: Array<keyof RadarSettings> = [
  'notify_enabled',
  'notify_resolved',
  'send_org_names',
  'dip_enabled',
  'dip_notify_offline',
]

/**
 * /plugins/block-radar/settings — тумблеры радара.
 *
 * GET отдаёт эффективные значения (дефолты + переопределения), PUT
 * принимает только изменённые ключи.
 */
export default function SettingsPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['block-radar-settings'],
    queryFn: fetchSettings,
    retry: false,
    staleTime: 10_000,
  })

  const licenseError = useMemo(() => (error ? asLicenseError(error) : null), [error])

  const [draft, setDraft] = useState<RadarSettings | null>(null)
  const [touched, setTouched] = useState<Set<keyof RadarSettings>>(new Set())

  useEffect(() => {
    if (data && touched.size === 0) setDraft(data)
  }, [data, touched.size])

  const mutation = useMutation({
    mutationFn: (patch: RadarSettingsPatch) => updateSettings(patch),
    onSuccess: (fresh) => {
      setDraft(fresh)
      setTouched(new Set())
      qc.setQueryData(['block-radar-settings'], fresh)
      toast.success(t('plugins.block_radar.settings.saved'))
    },
    onError: () => {
      toast.error(t('plugins.block_radar.settings.save_error'))
    },
  })

  const setValue = <K extends keyof RadarSettings>(key: K, value: RadarSettings[K]) => {
    setDraft((d) => (d ? { ...d, [key]: value } : d))
    setTouched((s) => new Set(s).add(key))
  }

  const onSave = () => {
    if (!draft || touched.size === 0) return
    const patch: RadarSettingsPatch = {}
    for (const key of touched) {
      ;(patch as Record<string, unknown>)[key] = draft[key]
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

  if (isLoading || !draft) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="glass-card p-5">
          <div className="text-sm text-dark-300">{t('common.loading')}</div>
        </div>
      </div>
    )
  }

  const dirty = touched.size > 0

  return (
    <div className="space-y-6">
      <BackLink />

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Sliders className="w-5 h-5 text-emerald-400 shrink-0" aria-hidden />
          <h1 className="text-xl sm:text-2xl font-bold text-white truncate">
            {t('plugins.block_radar.settings.title')}
          </h1>
        </div>
        <Button onClick={onSave} disabled={!dirty || mutation.isPending} className="shrink-0">
          <Save className="w-4 h-4 mr-2" aria-hidden />
          {t('plugins.block_radar.settings.save')}
        </Button>
      </div>

      <div className="glass-card p-5 space-y-5">
        {TOGGLES.map((key) => (
          <div key={key} className="flex items-start gap-3">
            <Switch
              id={key}
              checked={Boolean(draft[key])}
              disabled={mutation.isPending}
              onCheckedChange={(v) => setValue(key, v as RadarSettings[typeof key])}
            />
            <div>
              <Label htmlFor={key} className="text-sm text-white">
                {t(`plugins.block_radar.settings.fields.${key}.label`)}
              </Label>
              <p className="text-[11px] text-dark-400 mt-0.5">
                {t(`plugins.block_radar.settings.fields.${key}.help`)}
              </p>
            </div>
          </div>
        ))}

        <div className="space-y-1.5 max-w-xs">
          <Label htmlFor="online_window_minutes" className="text-xs text-dark-300">
            {t('plugins.block_radar.settings.fields.online_window_minutes.label')}
          </Label>
          <Input
            id="online_window_minutes"
            type="number"
            min={1}
            max={60}
            value={String(draft.online_window_minutes)}
            onChange={(e) => {
              const v = Number(e.target.value)
              if (!Number.isNaN(v)) setValue('online_window_minutes', v)
            }}
            className="h-9"
          />
          <p className="text-[11px] text-dark-400">
            {t('plugins.block_radar.settings.fields.online_window_minutes.help')}
          </p>
        </div>
      </div>
    </div>
  )
}


function BackLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/plugins/block-radar"
      className="inline-flex items-center gap-2 text-sm text-dark-300 hover:text-white transition-colors"
    >
      <ArrowLeft className="w-4 h-4" />
      {t('plugins.block_radar.settings.back')}
    </Link>
  )
}
