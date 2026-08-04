/**
 * Shared licensing UI for paid plugins.
 *
 * Every paid plugin's backend routes are dynamically gated by
 * entitlements and answer 402 with the same structured payload —
 * the banner and the decoder live here so each plugin page can react
 * to "license blocked" without copying boilerplate.
 */
import { useTranslation } from 'react-i18next'
import { ShieldAlert } from '@/components/brand/icons'

/**
 * 402 payload shape returned by the panel's plugin license gate.
 */
export interface LicenseError {
  plugin: string
  license_state: 'expired' | 'missing'
  code: 'license_expired' | 'license_required'
}

/**
 * Decode a 402 axios error into the plugin's structured payload, if it
 * matches. Returns ``null`` for other error shapes so callers can tell
 * "license blocked" apart from "user not found" or network errors.
 */
export function asLicenseError(err: unknown): LicenseError | null {
  if (typeof err !== 'object' || err === null) return null
  const anyErr = err as { response?: { status?: number; data?: { detail?: unknown } } }
  if (anyErr.response?.status !== 402) return null
  const detail = anyErr.response.data?.detail
  if (typeof detail !== 'object' || detail === null) return null
  const d = detail as Partial<LicenseError>
  if (typeof d.plugin !== 'string' || typeof d.license_state !== 'string') return null
  return detail as LicenseError
}

/**
 * Banner shown on plugin pages when the backend returns 402 — i.e. the
 * plugin is installed but the license is missing or expired.
 */
export default function LicenseBanner({ error }: { error: LicenseError }) {
  const { t } = useTranslation()
  const isExpired = error.license_state === 'expired'
  const titleKey = isExpired
    ? 'plugins.license.expired_title'
    : 'plugins.license.missing_title'
  const bodyKey = isExpired
    ? 'plugins.license.expired_body'
    : 'plugins.license.missing_body'

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
