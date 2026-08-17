import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bot, ChevronDown, ChevronUp, Save, Sliders } from '@/components/brand/icons'
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
import type {
  AIProviderName,
  AIProviderStatus,
  AISettingsIn,
  ThresholdSettings,
} from './types'

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


/** Как провайдер называется у себя дома — сюда оператор и пойдёт за ключом. */
const PROVIDER_LABELS: Record<AIProviderName, string> = {
  gemini: 'Google Gemini',
  groq: 'Groq',
  openrouter: 'OpenRouter',
  anthropic: 'Anthropic Claude',
}

/**
 * Блок ИИ: ключи оператора, порядок фолбэка и готовность провайдеров.
 *
 * Тумблеры и порядок сохраняются сразу — это один щелчок и его результат
 * виден. Ключи и модели ждут кнопки «Сохранить»: ключ вставляют целиком,
 * и промежуточные состояния поля отправлять нельзя.
 *
 * Поле ключа всегда пустое: сервер его не возвращает. Пустое поле значит
 * «оставить как есть», а стереть можно кнопкой рядом — иначе очистка
 * была бы неотличима от «я просто не трогал».
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

  const [keys, setKeys] = useState<Record<string, string>>({})
  const [models, setModels] = useState<Record<string, string>>({})
  const [modelsTouched, setModelsTouched] = useState(false)

  useEffect(() => {
    if (data && !modelsTouched) {
      setModels(
        Object.fromEntries(data.providers.map((p) => [p.provider, p.model ?? ''])),
      )
    }
  }, [data, modelsTouched])

  const mutation = useMutation({
    mutationFn: (patch: AISettingsIn) => updateAISettings(patch),
    onSuccess: (fresh) => {
      qc.setQueryData(['smart-support-ai-settings'], fresh)
      qc.invalidateQueries({ queryKey: ['smart-support-ai-status'] })
      setKeys({})
      setModelsTouched(false)
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

  const chain = data.provider_chain
  const byProvider = new Map(data.providers.map((p) => [p.provider, p]))
  const statusOf = new Map((status?.providers ?? []).map((s) => [s.provider, s]))
  const dirty = Object.keys(keys).length > 0 || modelsTouched

  const move = (provider: AIProviderName, delta: number) => {
    const from = chain.indexOf(provider)
    const to = from + delta
    if (from < 0 || to < 0 || to >= chain.length) return
    const next = [...chain]
    next.splice(from, 1)
    next.splice(to, 0, provider)
    mutation.mutate({ provider_chain: next })
  }

  const save = () => {
    const patch: AISettingsIn = {}
    if (Object.keys(keys).length > 0) patch.keys = keys
    if (modelsTouched) patch.models = models
    if (Object.keys(patch).length > 0) mutation.mutate(patch)
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Bot className="w-4 h-4 text-cyan-400" />
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.smart_support.settings.sections.ai')}
        </h2>
      </div>

      <p className="text-xs text-dark-400">{t('plugins.smart_support.settings.ai.own_key_hint')}</p>

      <div className="flex items-center gap-3">
        <Switch
          id="ai-enabled"
          checked={data.enabled}
          disabled={mutation.isPending}
          onCheckedChange={(v) => mutation.mutate({ enabled: v })}
        />
        <Label htmlFor="ai-enabled" className="text-sm text-white">
          {t('plugins.smart_support.settings.ai.enabled')}
        </Label>
      </div>

      {data.enabled && !status?.configured && (
        <p className="text-xs text-amber-300">
          {t('plugins.smart_support.settings.ai.no_keys_warning')}
        </p>
      )}

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wider text-dark-400">
          {t('plugins.smart_support.settings.ai.chain_hint')}
        </p>

        {chain.map((provider, idx) => {
          const settings = byProvider.get(provider)
          const state = statusOf.get(provider)
          return (
            <div
              key={provider}
              className="rounded-lg border border-[var(--glass-border)] p-3 space-y-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-dark-400">{idx + 1}</span>
                <span className="text-sm text-white flex-1">{PROVIDER_LABELS[provider]}</span>
                <ProviderBadge state={state} />
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={idx === 0 || mutation.isPending}
                    onClick={() => move(provider, -1)}
                    aria-label={t('plugins.smart_support.settings.ai.move_up')}
                  >
                    <ChevronUp className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={idx === chain.length - 1 || mutation.isPending}
                    onClick={() => move(provider, 1)}
                    aria-label={t('plugins.smart_support.settings.ai.move_down')}
                  >
                    <ChevronDown className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[11px] text-dark-300">
                    {t('plugins.smart_support.settings.ai.key')}
                  </Label>
                  <div className="flex items-center gap-1.5">
                    <Input
                      type="password"
                      autoComplete="off"
                      value={keys[provider] ?? ''}
                      placeholder={
                        settings?.key_set
                          ? t('plugins.smart_support.settings.ai.key_set')
                          : t('plugins.smart_support.settings.ai.key_empty')
                      }
                      onChange={(e) => setKeys((prev) => ({ ...prev, [provider]: e.target.value }))}
                      className="h-8 text-xs"
                    />
                    {settings?.key_set && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-2 text-xs text-dark-300 hover:text-red-300"
                        disabled={mutation.isPending}
                        onClick={() => mutation.mutate({ keys: { [provider]: '' } })}
                      >
                        {t('plugins.smart_support.settings.ai.clear')}
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-1">
                  <Label className="text-[11px] text-dark-300">
                    {t('plugins.smart_support.settings.ai.model')}
                  </Label>
                  <Input
                    value={models[provider] ?? ''}
                    placeholder={t('plugins.smart_support.settings.ai.model_default')}
                    onChange={(e) => {
                      setModelsTouched(true)
                      setModels((prev) => ({ ...prev, [provider]: e.target.value }))
                    }}
                    className="h-8 text-xs"
                  />
                </div>
              </div>

              {state?.last_error && (
                <p className="text-[11px] text-dark-400 truncate" title={state.last_error}>
                  {state.last_error}
                </p>
              )}
            </div>
          )
        })}
      </div>

      <div className="flex items-center gap-3">
        <Switch
          id="ai-outage-lookup"
          checked={data.outage_lookup_enabled}
          disabled={mutation.isPending}
          onCheckedChange={(v) => mutation.mutate({ outage_lookup_enabled: v })}
        />
        <Label htmlFor="ai-outage-lookup" className="text-sm text-white">
          {t('plugins.smart_support.settings.ai.outage_lookup')}
        </Label>
      </div>
      <p className="text-xs text-dark-400">
        {t('plugins.smart_support.settings.ai.outage_hint')}
      </p>

      <div className="flex justify-end">
        <Button size="sm" onClick={save} disabled={!dirty || mutation.isPending}>
          <Save className="w-3.5 h-3.5 mr-1.5" />
          {t('plugins.smart_support.settings.save')}
        </Button>
      </div>
    </div>
  )
}

/** Готов / нет ключа / пауза после отказа — одним чипом. */
function ProviderBadge({ state }: { state?: AIProviderStatus }) {
  const { t } = useTranslation()
  if (!state || !state.configured) {
    return (
      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-300">
        {t('plugins.smart_support.settings.ai.state.no_key')}
      </span>
    )
  }
  if (state.available) {
    return (
      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
        {t('plugins.smart_support.settings.ai.state.ready')}
      </span>
    )
  }
  return (
    <span
      className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300"
      title={state.last_error ?? undefined}
    >
      {t('plugins.smart_support.settings.ai.state.cooldown', {
        n: state.cooldown_seconds_remaining,
      })}
    </span>
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
