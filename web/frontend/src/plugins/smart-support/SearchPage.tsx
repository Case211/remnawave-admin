import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, History, Search, SearchX, Sliders } from 'lucide-react'

import { Input } from '@/components/ui/input'

import LicenseBanner from './LicenseBanner'
import { asLicenseError, searchUsers } from './api'
import { EmptyState, Skeleton } from './primitives'
import type { SearchHit } from './types'

/**
 * /plugins/smart-support — operator types whatever the customer told them
 * (UUID, email, ник, IP, TG-id…), gets a list of candidate users to
 * jump into. ``q`` is debounced to keep the panel from hammering the DB.
 */
export default function SearchPage() {
  const { t } = useTranslation()
  const [raw, setRaw] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(raw.trim()), 300)
    return () => clearTimeout(handle)
  }, [raw])

  const enabled = debounced.length > 0
  const { data, isLoading, error } = useQuery({
    queryKey: ['smart-support-search', debounced],
    queryFn: () => searchUsers(debounced),
    enabled,
    retry: false,
    staleTime: 5_000,
  })

  const licenseError = useMemo(() => (error ? asLicenseError(error) : null), [error])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-white">
            {t('plugins.smart_support.search.title')}
          </h1>
          <p className="mt-1 text-sm text-dark-300">{t('plugins.smart_support.search.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* On phones we collapse to icon-only buttons; the text label
              stays as accessibility name + tooltip via title. */}
          <Link
            to="/plugins/smart-support/audit"
            title={t('plugins.smart_support.audit.open')}
            aria-label={t('plugins.smart_support.audit.open')}
            className="inline-flex items-center justify-center gap-1.5 min-h-[36px] text-xs text-dark-300 hover:text-white transition-colors px-3 py-1.5 rounded-lg border border-[var(--glass-border)] hover:bg-[var(--glass-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/40"
          >
            <History className="w-3.5 h-3.5" aria-hidden />
            <span className="hidden sm:inline">{t('plugins.smart_support.audit.open')}</span>
          </Link>
          <Link
            to="/plugins/smart-support/settings"
            title={t('plugins.smart_support.settings.open')}
            aria-label={t('plugins.smart_support.settings.open')}
            className="inline-flex items-center justify-center gap-1.5 min-h-[36px] text-xs text-dark-300 hover:text-white transition-colors px-3 py-1.5 rounded-lg border border-[var(--glass-border)] hover:bg-[var(--glass-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/40"
          >
            <Sliders className="w-3.5 h-3.5" aria-hidden />
            <span className="hidden sm:inline">{t('plugins.smart_support.settings.open')}</span>
          </Link>
        </div>
      </div>

      {licenseError && <LicenseBanner error={licenseError} />}

      <div className="glass-card p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300" />
          <Input
            autoFocus
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder={t('plugins.smart_support.search.placeholder')}
            className="pl-10 h-11 text-base"
          />
        </div>
        <p className="mt-2 text-xs text-dark-400">
          {t('plugins.smart_support.search.hint')}
        </p>
      </div>

      {!licenseError && enabled && (
        <ResultsList loading={isLoading} hits={data?.hits ?? []} matchedBy={data?.matched_by} />
      )}
    </div>
  )
}

function ResultsList({
  loading,
  hits,
  matchedBy,
}: {
  loading: boolean
  hits: SearchHit[]
  matchedBy?: string
}) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="glass-card overflow-hidden">
        <Skeleton className="h-7 w-48 m-4" />
        <ul className="divide-y divide-[var(--glass-border)]">
          {Array.from({ length: 4 }).map((_, i) => (
            <li key={i} className="flex items-center justify-between px-4 py-3 gap-3">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3 w-40" />
                <Skeleton className="h-2.5 w-64" />
              </div>
              <Skeleton className="h-4 w-4 rounded" />
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (hits.length === 0) {
    return (
      <div className="glass-card">
        <EmptyState
          icon={SearchX}
          message={t('plugins.smart_support.search.empty')}
          hint={t('plugins.smart_support.search.empty_hint', { defaultValue: '' })}
        />
      </div>
    )
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-4 py-2 text-xs uppercase tracking-wider text-dark-400 border-b border-[var(--glass-border)]">
        {t('plugins.smart_support.search.matched_by', { kind: matchedBy ?? '—' })}
        {' · '}
        {t('plugins.smart_support.search.count', { n: hits.length })}
      </div>
      <ul className="divide-y divide-[var(--glass-border)]">
        {hits.map((h) => (
          <li key={h.uuid}>
            <Link
              to={`/plugins/smart-support/report/${h.uuid}`}
              className="flex items-center justify-between gap-3 px-4 py-3 min-h-[56px] hover:bg-[var(--glass-bg)] transition-colors focus-visible:outline-none focus-visible:bg-[var(--glass-bg)]"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-white truncate">
                    {h.username || h.email || h.uuid}
                  </span>
                  {h.status && (
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200 shrink-0">
                      {h.status}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-xs text-dark-300 truncate">
                  {[h.email, h.telegram_id, h.last_country, h.last_asn]
                    .filter(Boolean)
                    .join(' · ') || h.uuid}
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-dark-300 shrink-0 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
