import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Search, Sliders } from 'lucide-react'

import { Input } from '@/components/ui/input'

import LicenseBanner from './LicenseBanner'
import { asLicenseError, searchUsers } from './api'
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
        <div>
          <h1 className="text-2xl font-bold text-white">{t('plugins.smart_support.search.title')}</h1>
          <p className="mt-1 text-sm text-dark-300">{t('plugins.smart_support.search.subtitle')}</p>
        </div>
        <Link
          to="/plugins/smart-support/settings"
          className="inline-flex items-center gap-1.5 text-xs text-dark-300 hover:text-white transition-colors px-3 py-1.5 rounded-lg border border-[var(--glass-border)]"
        >
          <Sliders className="w-3.5 h-3.5" />
          {t('plugins.smart_support.settings.open')}
        </Link>
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
    return <div className="glass-card p-6 text-sm text-dark-300">{t('common.loading')}</div>
  }
  if (hits.length === 0) {
    return (
      <div className="glass-card p-6 text-sm text-dark-300">
        {t('plugins.smart_support.search.empty')}
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
              className="flex items-center justify-between px-4 py-3 hover:bg-[var(--glass-bg)] transition-colors"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white truncate">
                    {h.username || h.email || h.uuid}
                  </span>
                  {h.status && (
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200">
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
              <ArrowRight className="w-4 h-4 text-dark-300 shrink-0" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
