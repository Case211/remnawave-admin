import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, X } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

/** Требования те же, что проверяет бэкенд (validate_password_strength). */
export interface PasswordStrength {
  score: number
  level: 'none' | 'weak' | 'fair' | 'good' | 'strong'
  label: string
  color: string
  checks: {
    length: boolean
    lower: boolean
    upper: boolean
    digit: boolean
    special: boolean
    noCyrillic: boolean
  }
  /** Пароль примет бэкенд */
  ok: boolean
}

// Кириллица, неотличимая от латиницы (С/C, А/A, Е/E…), ломает вход с другой раскладки
const CYRILLIC_RE = /[Ѐ-ӿ]/

export function getPasswordStrength(password: string): PasswordStrength {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`"()]/.test(password),
    noCyrillic: !CYRILLIC_RE.test(password),
  }
  const ok = Object.values(checks).every(Boolean)

  const { noCyrillic: _noCyrillic, ...coreChecks } = checks
  const passedCount = Object.values(coreChecks).filter(Boolean).length
  let score = passedCount * 16 // max 80
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10
  score = Math.min(100, score)

  if (password.length === 0) return { score: 0, level: 'none', label: '', color: '', checks, ok }
  if (score < 30) return { score, level: 'weak', label: 'login.passwordStrength.weak', color: '#ef4444', checks, ok }
  if (score < 60) return { score, level: 'fair', label: 'login.passwordStrength.fair', color: '#f59e0b', checks, ok }
  if (score < 80) return { score, level: 'good', label: 'login.passwordStrength.good', color: '#22c55e', checks, ok }
  return { score, level: 'strong', label: 'login.passwordStrength.strong', color: '#10b981', checks, ok }
}

/** Полоса надёжности и список требований; для пустого пароля не рисуется. */
export function PasswordStrengthBar({ password, className }: { password: string; className?: string }) {
  const { t } = useTranslation()
  const strength = useMemo(() => getPasswordStrength(password), [password])

  if (password.length === 0) return null

  return (
    <div className={cn('space-y-2 animate-fade-in', className)}>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-[var(--glass-bg)] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${strength.score}%`,
              backgroundColor: strength.color,
              boxShadow: `0 0 8px ${strength.color}40`,
            }}
          />
        </div>
        <span
          className="text-[11px] font-medium min-w-[60px] text-right transition-colors duration-300"
          style={{ color: strength.color }}
        >
          {strength.label ? t(strength.label) : ''}
        </span>
      </div>

      {!strength.checks.noCyrillic && (
        <div className="text-[11px] flex items-center gap-1 text-amber-400 animate-fade-in">
          <X className="w-3 h-3 shrink-0" />
          {t('login.passwordChecks.noCyrillic')}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5">
        {[
          { ok: strength.checks.length, text: t('login.passwordChecks.length') },
          { ok: strength.checks.lower, text: t('login.passwordChecks.lower') },
          { ok: strength.checks.upper, text: t('login.passwordChecks.upper') },
          { ok: strength.checks.digit, text: t('login.passwordChecks.digit') },
          { ok: strength.checks.special, text: t('login.passwordChecks.special') },
        ].map((c) => (
          <div
            key={c.text}
            className={cn(
              'text-[11px] flex items-center gap-1 transition-colors duration-200',
              c.ok ? 'text-green-400' : 'text-dark-300',
            )}
          >
            {c.ok ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
            {c.text}
          </div>
        ))}
      </div>
    </div>
  )
}
