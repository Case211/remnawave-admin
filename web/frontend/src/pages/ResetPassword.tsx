import { useState, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authApi } from '../api/auth'
import {
  Mail,
  Lock,
  AlertCircle,
  Check,
  X,
  Loader2,
  Eye,
  EyeOff,
  ArrowLeft,
  KeyRound,
} from '@/components/brand/icons'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const CYRILLIC_RE = /[\u0400-\u04FF]/

interface PasswordStrength {
  score: number
  checks: {
    length: boolean
    lower: boolean
    upper: boolean
    digit: boolean
    special: boolean
    noCyrillic: boolean
  }
}

function getPasswordStrength(password: string): PasswordStrength {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`"()]/.test(password),
    noCyrillic: !CYRILLIC_RE.test(password),
  }
  const { noCyrillic, ...coreChecks } = checks
  const passedCount = Object.values(coreChecks).filter(Boolean).length
  let score = passedCount * 16
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10
  return { score: Math.min(100, score), checks }
}

/**
 * Step 1: Request reset email
 */
function ForgotPasswordForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return

    setLoading(true)
    setError('')
    try {
      await authApi.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('resetPassword.error'))
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] p-4">
        <Card className="w-full max-w-md bg-[var(--glass-bg)] border-[var(--glass-border)] shadow-2xl">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
              <Check className="h-6 w-6 text-green-400" />
            </div>
            <h2 className="text-lg font-semibold text-white">{t('resetPassword.emailSent')}</h2>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-dark-300 text-center">
              {t('resetPassword.emailSentDescription')}
            </p>
            <Button
              onClick={() => navigate('/login')}
              variant="outline"
              className="w-full text-sm border-[var(--glass-border)] text-dark-300 hover:text-white"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('resetPassword.backToLogin')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] p-4">
      <Card className="w-full max-w-md bg-[var(--glass-bg)] border-[var(--glass-border)] shadow-2xl">
        <CardHeader className="text-center pb-2">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-500/10">
            <Mail className="h-6 w-6 text-primary-400" />
          </div>
          <h2 className="text-lg font-semibold text-white">{t('resetPassword.title')}</h2>
          <p className="text-xs text-dark-300 mt-1">{t('resetPassword.description')}</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="reset-email" className="text-xs font-medium text-dark-300">
                {t('resetPassword.email')}
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
                <Input
                  id="reset-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t('resetPassword.emailPlaceholder')}
                  autoComplete="email"
                  autoFocus
                  className="pl-9"
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={!email.trim() || loading}
              className="w-full text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <Mail className="w-4 h-4 mr-2" />
              )}
              {t('resetPassword.sendLink')}
            </Button>

            <Button
              type="button"
              onClick={() => navigate('/login')}
              variant="ghost"
              className="w-full text-sm text-dark-300 hover:text-white"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('resetPassword.backToLogin')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Step 2: Set new password (with token from email link)
 */
function ResetPasswordForm({ token }: { token: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const strength = useMemo(() => getPasswordStrength(password), [password])
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0
  const allChecks = Object.values(strength.checks).every(Boolean)
  const canSubmit = allChecks && passwordsMatch && !loading

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return

    setLoading(true)
    setError('')
    try {
      await authApi.resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('resetPassword.error'))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] p-4">
        <Card className="w-full max-w-md bg-[var(--glass-bg)] border-[var(--glass-border)] shadow-2xl">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
              <Check className="h-6 w-6 text-green-400" />
            </div>
            <h2 className="text-lg font-semibold text-white">{t('resetPassword.success')}</h2>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-dark-300 text-center">
              {t('resetPassword.successDescription')}
            </p>
            <Button
              onClick={() => navigate('/login')}
              className="w-full text-sm bg-primary-600 text-white hover:bg-primary-700"
            >
              {t('resetPassword.goToLogin')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const barColor = strength.score < 30 ? '#ef4444' : strength.score < 60 ? '#f59e0b' : strength.score < 80 ? '#22c55e' : '#10b981'

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] p-4">
      <Card className="w-full max-w-md bg-[var(--glass-bg)] border-[var(--glass-border)] shadow-2xl">
        <CardHeader className="text-center pb-2">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-500/10">
            <KeyRound className="h-6 w-6 text-primary-400" />
          </div>
          <h2 className="text-lg font-semibold text-white">{t('resetPassword.newPasswordTitle')}</h2>
          <p className="text-xs text-dark-300 mt-1">{t('resetPassword.newPasswordDescription')}</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 rounded-md bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="new-password" className="text-xs font-medium text-dark-300">
                {t('resetPassword.newPassword')}
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
                <Input
                  id="new-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  autoFocus
                  className="pl-9 pr-9"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Strength bar */}
              {password && (
                <div className="h-1.5 rounded-full bg-[var(--glass-bg)] overflow-hidden mt-1">
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{ width: `${strength.score}%`, backgroundColor: barColor }}
                  />
                </div>
              )}

              {/* Cyrillic warning */}
              {password && !strength.checks.noCyrillic && (
                <div className="text-[11px] flex items-center gap-1 text-amber-400 mt-1">
                  <X className="w-3 h-3 shrink-0" />
                  {t('login.passwordChecks.noCyrillic')}
                </div>
              )}

              {/* Requirement checks */}
              {password && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5 mt-1">
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
                        c.ok ? 'text-green-400' : 'text-dark-300'
                      )}
                    >
                      {c.ok ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                      {c.text}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm-password" className="text-xs font-medium text-dark-300">
                {t('resetPassword.confirmPassword')}
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
                <Input
                  id="confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  className="pl-9"
                />
              </div>
              {confirmPassword.length > 0 && !passwordsMatch && (
                <p className="text-[11px] text-red-400">{t('login.passwordsDoNotMatch')}</p>
              )}
              {passwordsMatch && (
                <p className="text-[11px] text-green-400 flex items-center gap-1">
                  <Check className="w-3 h-3" /> {t('login.passwordsMatch')}
                </p>
              )}
            </div>

            <Button
              type="submit"
              disabled={!canSubmit}
              className="w-full text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <KeyRound className="w-4 h-4 mr-2" />
              )}
              {t('resetPassword.resetButton')}
            </Button>

            <Button
              type="button"
              onClick={() => navigate('/login')}
              variant="ghost"
              className="w-full text-sm text-dark-300 hover:text-white"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('resetPassword.backToLogin')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Password reset page — shows either the "enter email" form
 * or the "enter new password" form depending on URL params.
 */
export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  if (token) {
    return <ResetPasswordForm token={token} />
  }

  return <ForgotPasswordForm />
}
