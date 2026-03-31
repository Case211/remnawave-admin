import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/authStore'
import { authApi, TelegramUser, AuthMethods } from '../api/auth'
import {
  User,
  Lock,
  AlertCircle,
  X,
  Loader2,
  Shield,
  KeyRound,
  Eye,
  EyeOff,
  RefreshCw,
  Copy,
  Check,
  UserPlus,
  Heart,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

declare global {
  interface Window {
    TelegramLoginWidget: {
      dataOnauth: (user: TelegramUser) => void
    }
  }
}

// Password generation
const PW_LOWER = 'abcdefghjkmnpqrstuvwxyz'
const PW_UPPER = 'ABCDEFGHJKMNPQRSTUVWXYZ'
const PW_DIGITS = '23456789'
const PW_SPECIAL = '!@#$%^&*_+-='
const PW_ALL = PW_LOWER + PW_UPPER + PW_DIGITS + PW_SPECIAL

function generatePassword(length = 16): string {
  const arr = new Uint32Array(length)
  crypto.getRandomValues(arr)
  const pick = (charset: string, rnd: number) => charset[rnd % charset.length]
  const chars = [
    pick(PW_LOWER, arr[0]),
    pick(PW_UPPER, arr[1]),
    pick(PW_DIGITS, arr[2]),
    pick(PW_SPECIAL, arr[3]),
  ]
  for (let i = 4; i < length; i++) {
    chars.push(pick(PW_ALL, arr[i]))
  }
  // Fisher-Yates shuffle
  for (let i = chars.length - 1; i > 0; i--) {
    const j = arr[i] % (i + 1)
    ;[chars[i], chars[j]] = [chars[j], chars[i]]
  }
  return chars.join('')
}

// Password strength calculation
interface PasswordStrength {
  score: number // 0-100
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
}

// Cyrillic characters that look identical to Latin (С/C, А/A, Е/E, etc.)
const CYRILLIC_RE = /[\u0400-\u04FF]/

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
  let score = passedCount * 16 // max 80

  // Bonus for length
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10

  score = Math.min(100, score)

  if (password.length === 0) return { score: 0, level: 'none', label: '', color: '', checks }
  if (score < 30) return { score, level: 'weak', label: 'login.passwordStrength.weak', color: '#ef4444', checks }
  if (score < 60) return { score, level: 'fair', label: 'login.passwordStrength.fair', color: '#f59e0b', checks }
  if (score < 80) return { score, level: 'good', label: 'login.passwordStrength.good', color: '#22c55e', checks }
  return { score, level: 'strong', label: 'login.passwordStrength.strong', color: '#10b981', checks }
}

// Password strength bar component
function PasswordStrengthBar({ password }: { password: string }) {
  const { t } = useTranslation()
  const strength = useMemo(() => getPasswordStrength(password), [password])

  if (password.length === 0) return null

  return (
    <div className="space-y-2 animate-fade-in">
      {/* Strength bar */}
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

      {/* Cyrillic warning */}
      {!strength.checks.noCyrillic && (
        <div className="text-[11px] flex items-center gap-1 text-amber-400 animate-fade-in">
          <X className="w-3 h-3 shrink-0" />
          {t('login.passwordChecks.noCyrillic')}
        </div>
      )}

      {/* Requirement checks */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
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
    </div>
  )
}

// TOTP code input form (shared between setup and verify)
function TotpCodeForm({
  onSubmit,
  totpCode,
  onCodeChange,
  disabled,
  buttonLabel,
  buttonIcon: ButtonIcon,
  hint,
  onCancel,
}: {
  onSubmit: (e: React.FormEvent) => void
  totpCode: string
  onCodeChange: (code: string) => void
  disabled: boolean
  buttonLabel: string
  buttonIcon: typeof Shield
  hint?: string
  onCancel: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="totp-code" className="text-dark-100 text-sm font-medium">
            {t('login.totp.enterCode')}
          </Label>
          <div className="relative">
            <Shield className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-300" />
            <Input
              id="totp-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              value={totpCode}
              onChange={(e) => onCodeChange(e.target.value.replace(/\s/g, ''))}
              placeholder="000000"
              autoFocus
              className="pl-10 text-center font-mono tracking-widest text-lg"
            />
          </div>
          {hint && <p className="text-[11px] text-dark-300">{hint}</p>}
        </div>
        <Button
          type="submit"
          className={cn(
            'w-full h-11 font-medium text-sm',
            'bg-gradient-to-r from-teal-600 to-cyan-600',
            'hover:from-teal-500 hover:to-cyan-500',
            'shadow-lg shadow-teal-900/20',
            'transition-all duration-200'
          )}
          disabled={disabled}
        >
          <ButtonIcon className="w-4 h-4 mr-2" />
          {buttonLabel}
        </Button>
      </form>
      <div className="text-center">
        <button
          onClick={onCancel}
          className="text-xs text-dark-300 hover:text-red-400 transition-colors"
        >
          {t('login.totp.cancel')}
        </button>
      </div>
    </div>
  )
}

// Password input with toggle visibility
function PasswordInput({
  id,
  value,
  onChange,
  placeholder,
  autoComplete,
  autoFocus,
  disabled,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
  autoFocus?: boolean
  disabled?: boolean
}) {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="relative">
      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-300" />
      <Input
        id={id}
        type={showPassword ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || '••••••••'}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        disabled={disabled}
        className="pl-10 pr-10"
      />
      <button
        type="button"
        onClick={() => setShowPassword(!showPassword)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-300 hover:text-dark-100 transition-colors"
        tabIndex={-1}
      >
        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  )
}

export default function Login() {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const {
    login,
    loginWithPassword,
    register,
    totpSetup,
    totpConfirmSetup,
    totpVerify,
    cancel2fa,
    isAuthenticated,
    isLoading,
    error,
    clearError,
    requires2fa,
    totpEnabled,
    totpSetupData,
  } = useAuthStore()

  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>()

  // Auth methods
  const [authMethods, setAuthMethods] = useState<AuthMethods>({ telegram: true, password: true, totp_required: false })

  // Setup check
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [setupChecked, setSetupChecked] = useState(false)

  // Login form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPasswordForm, setShowPasswordForm] = useState(false)

  // TOTP state
  const [totpCode, setTotpCode] = useState('')
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [copiedBackupCodes, setCopiedBackupCodes] = useState(false)
  const [backupCodesSaved, setBackupCodesSaved] = useState(false)

  // Registration form state
  const [regUsername, setRegUsername] = useState('admin')
  const [regPassword, setRegPassword] = useState('')
  const [regConfirmPassword, setRegConfirmPassword] = useState('')
  const [copiedPassword, setCopiedPassword] = useState(false)

  const regStrength = useMemo(() => getPasswordStrength(regPassword), [regPassword])
  const regAllChecks = Object.values(regStrength.checks).every(Boolean)
  const regPasswordsMatch = regPassword === regConfirmPassword && regConfirmPassword.length > 0
  const canRegister =
    regUsername.trim().length >= 3 && regAllChecks && regPasswordsMatch && !isLoading

  // Check setup status on mount
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/')
      return
    }

    Promise.all([
      authApi.getSetupStatus(),
      authApi.getAuthMethods(),
    ]).then(([status, methods]) => {
      setNeedsSetup(status.needs_setup)
      setAuthMethods(methods)
      // If telegram is disabled, show password form by default
      if (!methods.telegram && methods.password) {
        setShowPasswordForm(true)
      }
      setSetupChecked(true)
    }).catch(() => {
      // If API is unreachable, fall back to login form
      setNeedsSetup(false)
      setSetupChecked(true)
    })
  }, [isAuthenticated, navigate])

  // Auto-trigger TOTP setup when 2FA is required but not yet configured
  useEffect(() => {
    if (requires2fa && !totpEnabled && !totpSetupData && !isLoading) {
      totpSetup().catch(() => {})
    }
  }, [requires2fa, totpEnabled, totpSetupData, isLoading, totpSetup])

  // Setup Telegram widget
  useEffect(() => {
    if (isAuthenticated || needsSetup || !authMethods.telegram) return

    window.TelegramLoginWidget = {
      dataOnauth: async (user: TelegramUser) => {
        try {
          await login(user)
          if (!useAuthStore.getState().requires2fa) {
            navigate('/')
          }
        } catch (err) {
          console.error('Login failed:', err)
        }
      },
    }

    const botUsername =
      window.__ENV?.TELEGRAM_BOT_USERNAME || import.meta.env.VITE_TELEGRAM_BOT_USERNAME
    if (!botUsername) {
      setShowPasswordForm(true)
      return
    }

    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.setAttribute('data-telegram-login', botUsername)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '8')
    script.setAttribute('data-onauth', 'TelegramLoginWidget.dataOnauth(user)')
    script.setAttribute('data-request-access', 'write')
    script.async = true

    script.onerror = () => {
      if (authMethods.password) setShowPasswordForm(true)
    }

    const timeout = setTimeout(() => {
      if (authMethods.password) setShowPasswordForm(true)
    }, 5000)

    script.onload = () => clearTimeout(timeout)

    containerRef.current?.appendChild(script)

    return () => {
      clearTimeout(timeout)
      if (containerRef.current?.contains(script)) {
        containerRef.current.removeChild(script)
      }
    }
  }, [isAuthenticated, navigate, login, needsSetup, authMethods.telegram])

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    try {
      await loginWithPassword({ username: username.trim(), password })
      // If requires2fa was set, stay on Login page (2FA view will show)
      if (!useAuthStore.getState().requires2fa) {
        navigate('/')
      }
    } catch (err) {
      console.error('Password login failed:', err)
    }
  }

  const handleTotpVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!totpCode.trim()) return
    try {
      if (totpEnabled) {
        await totpVerify(totpCode.trim())
      } else {
        await totpConfirmSetup(totpCode.trim())
      }
      navigate('/')
    } catch (err) {
      setTotpCode('')
      console.error('TOTP verification failed:', err)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canRegister) return

    try {
      await register({ username: regUsername.trim(), password: regPassword })
      navigate('/')
    } catch (err) {
      console.error('Registration failed:', err)
    }
  }

  const handleGeneratePassword = useCallback(() => {
    const pw = generatePassword(16)
    setRegPassword(pw)
    setRegConfirmPassword(pw)
  }, [])

  const handleCopyPassword = useCallback(() => {
    if (regPassword) {
      navigator.clipboard.writeText(regPassword).then(() => {
        setCopiedPassword(true)
        clearTimeout(copyTimerRef.current)
        copyTimerRef.current = setTimeout(() => setCopiedPassword(false), 2000)
      })
    }
  }, [regPassword])

  // Show loading while checking setup status
  if (!setupChecked) {
    return (
      <div className="login-bg min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
      </div>
    )
  }

  return (
    <div className="login-bg min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Mesh gradient background */}
      <div className="mesh-bg">
        <div className="mesh-layer mesh-layer--1" />
        <div className="mesh-layer mesh-layer--2" />
        <div className="mesh-layer mesh-layer--3" />
        <div className="mesh-layer mesh-layer--4" />
      </div>

      {/* Main card */}
      <div
        className={cn(
          'w-full login-card-enter relative z-10',
          needsSetup ? 'max-w-[480px]' : 'max-w-[420px]'
        )}
      >
        <Card
          className="rounded-2xl overflow-hidden glass-heavy"
          style={{
            boxShadow:
              '0 0 0 1px var(--glass-highlight), ' +
              '0 20px 60px -10px rgba(0, 0, 0, 0.5), ' +
              '0 0 80px -20px rgba(var(--glow-rgb), 0.12)',
          }}
        >
          {/* Top accent line */}
          <div
            className="h-[2px] w-full"
            style={{
              background:
                'linear-gradient(90deg, transparent 0%, var(--accent-from) 30%, var(--accent-to) 70%, transparent 100%)',
            }}
          />

          <CardHeader className="items-center pt-6 sm:pt-8 pb-2 px-4 sm:px-8">
            <div className="flex flex-col items-center gap-4 mb-2">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center relative login-logo-glow"
                style={{
                  background: 'linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)',
                }}
              >
                {needsSetup ? (
                  <UserPlus className="w-8 h-8 text-white" strokeWidth={1.8} />
                ) : (
                  <Shield className="w-8 h-8 text-white" strokeWidth={1.8} />
                )}
              </div>
              <div className="text-center">
                <h1 className="text-2xl font-display font-bold text-white tracking-tight">
                  Remnawave
                </h1>
                <p className="text-sm text-dark-200 mt-1">
                  {needsSetup ? t('login.initialSetup') : t('login.subtitle')}
                </p>
              </div>
            </div>
          </CardHeader>

          <CardContent className="px-4 sm:px-8 pb-6 sm:pb-8 pt-4">
            {/* Separator */}
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 h-px bg-[var(--glass-border)]" />
              <span className="text-xs text-dark-300 font-medium uppercase tracking-wider">
                {requires2fa
                  ? (totpEnabled ? t('login.totp.verify') : t('login.totp.setup'))
                  : needsSetup
                    ? t('login.createAdmin')
                    : showPasswordForm
                      ? t('login.passwordLogin')
                      : t('login.authorization')}
              </span>
              <div className="flex-1 h-px bg-[var(--glass-border)]" />
            </div>

            {/* Error */}
            {error && (
              <div
                className="mb-5 p-3.5 rounded-xl border animate-fade-in"
                style={{
                  background:
                    'linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.04) 100%)',
                  borderColor: 'rgba(239, 68, 68, 0.2)',
                }}
              >
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                  <p className="text-sm text-red-400 leading-relaxed flex-1">{error}</p>
                  <button
                    onClick={clearError}
                    className="text-red-400/60 hover:text-red-400 transition-colors shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* Loading */}
            {isLoading && (
              <div className="flex flex-col items-center py-6 animate-fade-in">
                <div className="relative">
                  <div
                    className="absolute inset-0 rounded-full"
                    style={{
                      background:
                        'radial-gradient(circle, rgba(13, 148, 136, 0.2) 0%, transparent 70%)',
                      transform: 'scale(2)',
                    }}
                  />
                  <Loader2 className="h-8 w-8 animate-spin text-teal-500 relative" />
                </div>
                <p className="mt-3 text-sm text-dark-200">
                  {needsSetup ? t('login.creatingAccount') : t('login.loggingIn')}
                </p>
              </div>
            )}

            {!isLoading && (
              <>
                {/* TOTP 2FA flow */}
                {requires2fa ? (
                  <>
                    {/* TOTP Setup (first-time) */}
                    {!totpEnabled && totpSetupData && (
                      <div className="space-y-4 mb-5 animate-fade-in">
                        <div
                          className="p-3 rounded-lg border border-teal-500/20"
                          style={{
                            background:
                              'linear-gradient(135deg, rgba(13, 148, 136, 0.06) 0%, rgba(6, 182, 212, 0.04) 100%)',
                          }}
                        >
                          <p className="text-xs text-teal-300/80 leading-relaxed">
                            {t('login.totp.setupHint')}
                          </p>
                        </div>

                        {/* QR Code */}
                        <div className="flex justify-center">
                          <div className="p-3 bg-white rounded-xl">
                            <img
                              src={`data:image/png;base64,${totpSetupData.qr_code}`}
                              alt="TOTP QR Code"
                              className="w-36 h-36 sm:w-48 sm:h-48"
                              onError={(e) => { e.currentTarget.style.display = 'none' }}
                            />
                          </div>
                        </div>

                        {/* Secret key */}
                        <div className="space-y-1">
                          <Label className="text-dark-200 text-xs">{t('login.totp.secretKey')}</Label>
                          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--glass-bg)]/40 border border-[var(--glass-border)]">
                            <code className="text-xs text-teal-300 font-mono flex-1 select-all break-all">
                              {totpSetupData.secret}
                            </code>
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(totpSetupData.secret)
                                setCopiedSecret(true)
                                setTimeout(() => setCopiedSecret(false), 2000)
                              }}
                              className="text-dark-300 hover:text-teal-400 transition-colors shrink-0"
                            >
                              {copiedSecret ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                        </div>

                        {/* Backup codes */}
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <Label className="text-dark-200 text-xs">{t('login.totp.backupCodes')}</Label>
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(totpSetupData.backup_codes.join('\n'))
                                setCopiedBackupCodes(true)
                                setTimeout(() => setCopiedBackupCodes(false), 2000)
                              }}
                              className="text-dark-300 hover:text-teal-400 transition-colors"
                            >
                              {copiedBackupCodes ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
                            </button>
                          </div>
                          <div className="grid grid-cols-2 gap-1.5 p-2.5 rounded-lg bg-[var(--glass-bg)]/40 border border-[var(--glass-border)]">
                            {totpSetupData.backup_codes.map((code, i) => (
                              <code key={i} className="text-xs text-dark-100 font-mono text-center py-0.5">
                                {code}
                              </code>
                            ))}
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <input
                              type="checkbox"
                              id="backup-saved"
                              checked={backupCodesSaved}
                              onChange={(e) => setBackupCodesSaved(e.target.checked)}
                              className="w-3.5 h-3.5 rounded border-dark-400 text-teal-500 focus:ring-teal-500/30"
                            />
                            <Label htmlFor="backup-saved" className="text-dark-200 text-xs cursor-pointer">
                              {t('login.totp.backupSaved')}
                            </Label>
                          </div>
                        </div>

                        {/* Confirm code */}
                        <TotpCodeForm
                          onSubmit={handleTotpVerify}
                          totpCode={totpCode}
                          onCodeChange={setTotpCode}
                          disabled={totpCode.length < 6 || !backupCodesSaved}
                          buttonLabel={t('login.totp.confirmSetup')}
                          buttonIcon={Shield}
                          onCancel={cancel2fa}
                        />
                      </div>
                    )}

                    {/* TOTP Verify (returning user) */}
                    {totpEnabled && (
                      <div className="space-y-4 mb-5 animate-fade-in">
                        <div
                          className="p-3 rounded-lg border border-teal-500/20"
                          style={{
                            background:
                              'linear-gradient(135deg, rgba(13, 148, 136, 0.06) 0%, rgba(6, 182, 212, 0.04) 100%)',
                          }}
                        >
                          <p className="text-xs text-teal-300/80 leading-relaxed">
                            {t('login.totp.verifyHint')}
                          </p>
                        </div>

                        <TotpCodeForm
                          onSubmit={handleTotpVerify}
                          totpCode={totpCode}
                          onCodeChange={setTotpCode}
                          disabled={totpCode.length < 6}
                          buttonLabel={t('login.totp.verifyButton')}
                          buttonIcon={KeyRound}
                          hint={t('login.totp.orBackupCode')}
                          onCancel={cancel2fa}
                        />
                      </div>
                    )}
                  </>
                ) : needsSetup ? (
                  <form onSubmit={handleRegister} className="space-y-4 mb-5">
                    <div
                      className="p-3 rounded-lg border border-teal-500/20 mb-4"
                      style={{
                        background:
                          'linear-gradient(135deg, rgba(13, 148, 136, 0.06) 0%, rgba(6, 182, 212, 0.04) 100%)',
                      }}
                    >
                      <p className="text-xs text-teal-300/80 leading-relaxed">
                        {t('login.setupWelcome')}
                      </p>
                    </div>

                    {/* Username */}
                    <div className="space-y-2">
                      <Label htmlFor="reg-username" className="text-dark-100 text-sm font-medium">
                        {t('login.username')}
                      </Label>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-300" />
                        <Input
                          id="reg-username"
                          type="text"
                          value={regUsername}
                          onChange={(e) => setRegUsername(e.target.value)}
                          placeholder="admin"
                          autoComplete="username"
                          autoFocus
                          className="pl-10"
                          minLength={3}
                          maxLength={100}
                        />
                      </div>
                      {regUsername.length > 0 && regUsername.trim().length < 3 && (
                        <p className="text-[11px] text-red-400">{t('login.minChars', { count: 3 })}</p>
                      )}
                    </div>

                    {/* Password */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label
                          htmlFor="reg-password"
                          className="text-dark-100 text-sm font-medium"
                        >
                          {t('login.passwordLabel')}
                        </Label>
                        <div className="flex items-center gap-1">
                          {regPassword && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={handleCopyPassword}
                              className="h-6 px-1.5 text-dark-300 hover:text-teal-400"
                              title={t('login.copyPassword')}
                            >
                              {copiedPassword ? (
                                <Check className="h-3.5 w-3.5 text-green-400" />
                              ) : (
                                <Copy className="h-3.5 w-3.5" />
                              )}
                            </Button>
                          )}
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={handleGeneratePassword}
                            className="h-6 px-1.5 text-dark-300 hover:text-teal-400 gap-1"
                            title={t('login.generatePassword')}
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            <span className="text-[11px]">{t('login.generator')}</span>
                          </Button>
                        </div>
                      </div>
                      <PasswordInput
                        id="reg-password"
                        value={regPassword}
                        onChange={setRegPassword}
                        autoComplete="new-password"
                      />
                      <PasswordStrengthBar password={regPassword} />
                    </div>

                    {/* Confirm password */}
                    <div className="space-y-2">
                      <Label
                        htmlFor="reg-confirm-password"
                        className="text-dark-100 text-sm font-medium"
                      >
                        {t('login.confirmPassword')}
                      </Label>
                      <PasswordInput
                        id="reg-confirm-password"
                        value={regConfirmPassword}
                        onChange={setRegConfirmPassword}
                        autoComplete="new-password"
                        placeholder={t('login.repeatPassword')}
                      />
                      {regConfirmPassword.length > 0 && !regPasswordsMatch && (
                        <p className="text-[11px] text-red-400">{t('login.passwordsDoNotMatch')}</p>
                      )}
                      {regPasswordsMatch && (
                        <p className="text-[11px] text-green-400 flex items-center gap-1">
                          <Check className="w-3 h-3" /> {t('login.passwordsMatch')}
                        </p>
                      )}
                    </div>

                    <Button
                      type="submit"
                      className={cn(
                        'w-full h-11 font-medium text-sm',
                        'bg-gradient-to-r from-teal-600 to-cyan-600',
                        'hover:from-teal-500 hover:to-cyan-500',
                        'shadow-lg shadow-teal-900/20',
                        'transition-all duration-200'
                      )}
                      disabled={!canRegister}
                    >
                      <UserPlus className="w-4 h-4 mr-2" />
                      {t('login.createAccount')}
                    </Button>
                  </form>
                ) : (
                  <>
                    {/* Password login form */}
                    {showPasswordForm ? (
                      <form onSubmit={handlePasswordLogin} className="space-y-4 mb-5">
                        <div className="space-y-2">
                          <Label
                            htmlFor="username"
                            className="text-dark-100 text-sm font-medium"
                          >
                            {t('login.username')}
                          </Label>
                          <div className="relative">
                            <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-300" />
                            <Input
                              id="username"
                              type="text"
                              value={username}
                              onChange={(e) => setUsername(e.target.value)}
                              placeholder="admin"
                              autoComplete="username"
                              autoFocus
                              className="pl-10"
                            />
                          </div>
                        </div>
                        <div className="space-y-2">
                          <Label
                            htmlFor="password"
                            className="text-dark-100 text-sm font-medium"
                          >
                            {t('login.passwordLabel')}
                          </Label>
                          <PasswordInput
                            id="password"
                            value={password}
                            onChange={setPassword}
                            autoComplete="current-password"
                          />
                        </div>
                        <Button
                          type="submit"
                          className={cn(
                            'w-full h-11 font-medium text-sm',
                            'bg-gradient-to-r from-teal-600 to-cyan-600',
                            'hover:from-teal-500 hover:to-cyan-500',
                            'shadow-lg shadow-teal-900/20',
                            'transition-all duration-200'
                          )}
                          disabled={!username.trim() || !password.trim()}
                        >
                          <KeyRound className="w-4 h-4 mr-2" />
                          {t('login.loginButton')}
                        </Button>
                        <div className="text-center mt-2">
                          <button
                            type="button"
                            onClick={() => navigate('/reset-password')}
                            className="text-xs text-dark-300 hover:text-teal-400 transition-colors duration-200"
                          >
                            {t('login.forgotPassword')}
                          </button>
                        </div>
                      </form>
                    ) : (
                      /* Telegram Login Widget */
                      <div ref={containerRef} className="flex justify-center mb-5 min-h-[40px]" />
                    )}

                    {/* Toggle auth method — only show if both methods are enabled */}
                    {authMethods.telegram && authMethods.password && (
                      <div className="text-center">
                        <button
                          onClick={() => {
                            setShowPasswordForm(!showPasswordForm)
                            clearError()
                          }}
                          className={cn(
                            'text-xs text-dark-300 hover:text-teal-400',
                            'transition-colors duration-200',
                            'inline-flex items-center gap-1.5'
                          )}
                        >
                          {showPasswordForm ? (
                            <>{t('login.telegram')}</>
                          ) : (
                            <>
                              <Lock className="h-3 w-3" />
                              {t('login.password')}
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {/* Footer */}
            <div className="mt-8 pt-5 border-t border-[var(--glass-border)]">
              <p className="text-center text-[11px] text-dark-300/80 leading-relaxed">
                {needsSetup
                  ? t('login.passwordRequirements')
                  : t('login.authorizedOnly')}
              </p>
            </div>

            {/* Donation */}
            <div className="mt-4 pt-4 border-t border-[var(--glass-border)]">
              <div className="flex items-center justify-center gap-1.5 mb-2">
                <Heart className="w-3 h-3 text-pink-400" />
                <span className="text-[11px] font-medium text-dark-200">
                  {t('login.donationTitle')}
                </span>
              </div>
              <p className="text-center text-[10px] text-dark-300/70 leading-relaxed mb-2.5">
                {t('login.donationNote')}
              </p>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-[var(--glass-bg)]/40 border border-[var(--glass-border)]">
                  <span className="text-[10px] font-medium text-dark-200 shrink-0">TON</span>
                  <span className="text-[9px] text-dark-300 truncate font-mono flex-1">UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC</span>
                </div>
                <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-[var(--glass-bg)]/40 border border-[var(--glass-border)]">
                  <span className="text-[10px] font-medium text-dark-200 shrink-0">USDT</span>
                  <span className="text-[9px] text-dark-300 truncate font-mono flex-1">TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP</span>
                </div>
                <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-[var(--glass-bg)]/40 border border-[var(--glass-border)]">
                  <span className="text-[10px] font-medium text-dark-200 shrink-0">BTC</span>
                  <span className="text-[9px] text-dark-300 truncate font-mono flex-1">1J6Zz7XcrpFkchwFmuU5WTFYTxziBdSwRz</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
