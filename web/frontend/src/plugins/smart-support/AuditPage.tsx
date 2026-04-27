import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FileSearch, History } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import LicenseBanner from './LicenseBanner'
import { SessionRow } from './ReportPage'
import { asLicenseError, fetchActions, fetchRecentSessions } from './api'
import { EmptyState, Skeleton } from './primitives'

/**
 * /plugins/smart-support/audit — read-only ledger of every action
 * triggered through the plugin. Optional filters by action_id and
 * admin_username; pagination is offset-based because the backend
 * already returns ``total`` and the audit log doesn't change behind
 * the operator's back.
 */
export default function AuditPage() {
  const { t } = useTranslation()
  const [actionId, setActionId] = useState<string>('')
  const [adminUsername, setAdminUsername] = useState<string>('')
  const [offset, setOffset] = useState(0)

  const limit = 50

  const { data: actionsData } = useQuery({
    queryKey: ['smart-support-actions'],
    queryFn: fetchActions,
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['smart-support-audit', { actionId, adminUsername, offset }],
    queryFn: () =>
      fetchRecentSessions({
        limit,
        offset,
        action_id: actionId || undefined,
        admin_username: adminUsername || undefined,
      }),
    retry: false,
    staleTime: 15_000,
  })

  const licenseError = useMemo(() => (error ? asLicenseError(error) : null), [error])

  const total = data?.total ?? 0
  const hasPrev = offset > 0
  const hasNext = offset + limit < total

  return (
    <div className="space-y-6">
      <Link
        to="/plugins/smart-support"
        className="inline-flex items-center gap-2 text-sm text-dark-300 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        {t('plugins.smart_support.report.back_to_search')}
      </Link>

      <div className="flex items-center gap-2">
        <History className="w-5 h-5 text-emerald-400" />
        <h1 className="text-2xl font-bold text-white">
          {t('plugins.smart_support.audit.title')}
        </h1>
      </div>
      <p className="text-sm text-dark-300 -mt-3">
        {t('plugins.smart_support.audit.subtitle')}
      </p>

      {licenseError && <LicenseBanner error={licenseError} />}

      {/* Filter strip. Action filter uses pills (one tap, visible
          choices, room for the count chip) instead of a hidden
          ``<select>`` — operators usually pivot on action id. */}
      <div className="glass-card p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <FilterPill
            active={!actionId}
            onClick={() => {
              setActionId('')
              setOffset(0)
            }}
          >
            {t('plugins.smart_support.audit.filter_action_all')}
          </FilterPill>
          {actionsData?.actions.map((a) => (
            <FilterPill
              key={a.id}
              active={actionId === a.id}
              onClick={() => {
                setActionId(a.id)
                setOffset(0)
              }}
            >
              {t(a.title_i18n)}
            </FilterPill>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 sm:items-end">
          <div className="space-y-1.5">
            <Label className="text-xs text-dark-300">
              {t('plugins.smart_support.audit.filter_admin')}
            </Label>
            <Input
              value={adminUsername}
              onChange={(e) => {
                setAdminUsername(e.target.value)
                setOffset(0)
              }}
              placeholder={t('plugins.smart_support.audit.filter_admin_placeholder')}
              className="h-9"
            />
          </div>
          <div className="text-xs text-dark-400 sm:text-right tabular-nums">
            {t('plugins.smart_support.audit.total', { n: total })}
          </div>
        </div>
      </div>

      <div className="glass-card p-5">
        {!data || isLoading ? (
          <ul className="divide-y divide-[var(--glass-border)]">
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className="py-2.5 flex items-start justify-between gap-3">
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3 w-44" />
                  <Skeleton className="h-2.5 w-64" />
                </div>
                <Skeleton className="h-2.5 w-20 shrink-0" />
              </li>
            ))}
          </ul>
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={FileSearch}
            message={t('plugins.smart_support.audit.empty')}
          />
        ) : (
          <ul className="divide-y divide-[var(--glass-border)]">
            {data.items.map((s) => {
              const targetUuid = s.target_user_uuid
              return (
                <li key={s.id}>
                  {targetUuid ? (
                    <Link
                      to={`/plugins/smart-support/report/${targetUuid}`}
                      className="block hover:bg-[var(--glass-bg)] rounded px-2 -mx-2 transition-colors focus-visible:outline-none focus-visible:bg-[var(--glass-bg)]"
                    >
                      <SessionRow entry={s} showUser />
                    </Link>
                  ) : (
                    <SessionRow entry={s} showUser />
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {(hasPrev || hasNext) && (
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPrev}
            onClick={() => setOffset(Math.max(0, offset - limit))}
          >
            {t('plugins.smart_support.audit.prev')}
          </Button>
          <span className="text-xs text-dark-400 tabular-nums">
            {offset + 1}–{Math.min(offset + limit, total)} / {total}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasNext}
            onClick={() => setOffset(offset + limit)}
          >
            {t('plugins.smart_support.audit.next')}
          </Button>
        </div>
      )}
    </div>
  )
}


function FilterPill({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        'inline-flex items-center text-xs px-3 min-h-[32px] rounded-full border transition-colors ' +
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/40 ' +
        (active
          ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
          : 'bg-transparent border-[var(--glass-border)] text-dark-200 hover:bg-[var(--glass-bg)] hover:text-white')
      }
    >
      {children}
    </button>
  )
}
