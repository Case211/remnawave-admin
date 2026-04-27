import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, History } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import LicenseBanner from './LicenseBanner'
import { SessionRow } from './ReportPage'
import { asLicenseError, fetchActions, fetchRecentSessions } from './api'

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

      <div className="glass-card p-4 grid gap-3 sm:grid-cols-3 sm:items-end">
        <div className="space-y-1.5">
          <Label className="text-xs text-dark-300">
            {t('plugins.smart_support.audit.filter_action')}
          </Label>
          <select
            value={actionId}
            onChange={(e) => {
              setActionId(e.target.value)
              setOffset(0)
            }}
            className="h-9 w-full bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-lg px-3 text-sm text-white"
          >
            <option value="">{t('plugins.smart_support.audit.filter_action_all')}</option>
            {actionsData?.actions.map((a) => (
              <option key={a.id} value={a.id}>
                {t(a.title_i18n)}
              </option>
            ))}
          </select>
        </div>
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
        <div className="text-xs text-dark-400 sm:text-right">
          {t('plugins.smart_support.audit.total', { n: total })}
        </div>
      </div>

      <div className="glass-card p-5">
        {!data || isLoading ? (
          <p className="text-sm text-dark-300">{t('common.loading')}</p>
        ) : data.items.length === 0 ? (
          <p className="text-sm text-dark-400">
            {t('plugins.smart_support.audit.empty')}
          </p>
        ) : (
          <ul className="divide-y divide-[var(--glass-border)]">
            {data.items.map((s) => {
              const targetUuid = s.target_user_uuid
              return (
                <li key={s.id}>
                  {targetUuid ? (
                    <Link
                      to={`/plugins/smart-support/report/${targetUuid}`}
                      className="block hover:bg-[var(--glass-bg)] rounded px-2 -mx-2 transition-colors"
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
          <span className="text-xs text-dark-400">
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
