import { useTranslation } from 'react-i18next'
import { ShieldAlert } from 'lucide-react'

import type { LicenseError } from './types'

/**
 * Banner shown on plugin pages when the backend returns 402 — i.e. the
 * plugin is installed but the license is missing or expired.
 *
 * Stays a generic component so future plugins can reuse the same layout
 * (move to ``components/`` if a second plugin actually needs it).
 */
export default function LicenseBanner({ error }: { error: LicenseError }) {
  const { t } = useTranslation()
  const isExpired = error.license_state === 'expired'
  const titleKey = isExpired
    ? 'plugins.smart_support.license.expired_title'
    : 'plugins.smart_support.license.missing_title'
  const bodyKey = isExpired
    ? 'plugins.smart_support.license.expired_body'
    : 'plugins.smart_support.license.missing_body'

  return (
    <div className="glass-card p-6 border-l-4 border-amber-500/70">
      <div className="flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 mt-0.5 text-amber-400 shrink-0" />
        <div>
          <h3 className="text-base font-semibold text-white">{t(titleKey)}</h3>
          <p className="mt-1 text-sm text-dark-200">{t(bodyKey)}</p>
        </div>
      </div>
    </div>
  )
}
