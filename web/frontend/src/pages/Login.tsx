import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { authApi, TelegramUser } from '../api/auth'
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
  }
}

function getPasswordStrength(password: string): PasswordStrength {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`"()]/.test(password),
  }

  const passedCount = Object.values(checks).filter(Boolean).length
  let score = passedCount * 16 // max 80

  // Bonus for length
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10

  score = Math.min(100, score)

  if (password.length === 0) return { score: 0, level: 'none', label: '', color: '', checks }
  if (score < 30) return { score, level: 'weak', label: 'Слабый', color: '#ef4444', checks }
  if (score < 60) return { score, level: 'fair', label: 'Средний', color: '#f59e0b', checks }
  if (score < 80) return { score, level: 'good', label: 'Хороший', color: '#22c55e', checks }
  return { score, level: 'strong', label: 'Надёжный', color: '#10b981', checks }
}

// Password strength bar component
function PasswordStrengthBar({ password }: { password: string }) {
  const strength = useMemo(() => getPasswordStrength(password), [password])

  if (password.length === 0) return null

  return (
    <div className="space-y-2 animate-fade-in">
      {/* Strength bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-dark-600/50 overflow-hidden">
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
          {strength.label}
        </span>
      </div>

      {/* Requirement checks */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {[
          { ok: strength.checks.length, text: '8+ символов' },
          { ok: strength.checks.lower, text: 'Строчная (a-z)' },
          { ok: strength.checks.upper, text: 'Заглавная (A-Z)' },
          { ok: strength.checks.digit, text: 'Цифра (0-9)' },
          { ok: strength.checks.special, text: 'Спецсимвол' },
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
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { login, loginWithPassword, register, isAuthenticated, isLoading, error, clearError } =
    useAuthStore()

  // Setup check
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [setupChecked, setSetupChecked] = useState(false)

  // Login form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPasswordForm, setShowPasswordForm] = useState(false)

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

    authApi.getSetupStatus().then((status) => {
      setNeedsSetup(status.needs_setup)
      setSetupChecked(true)
    })
  }, [isAuthenticated, navigate])

  // Setup Telegram widget
  useEffect(() => {
    if (isAuthenticated || needsSetup) return

    window.TelegramLoginWidget = {
      dataOnauth: async (user: TelegramUser) => {
        try {
          await login(user)
          navigate('/')
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

    containerRef.current?.appendChild(script)

    return () => {
      if (containerRef.current?.contains(script)) {
        containerRef.current.removeChild(script)
      }
    }
  }, [isAuthenticated, navigate, login, needsSetup])

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    try {
      await loginWithPassword({ username: username.trim(), password })
      navigate('/')
    } catch (err) {
      console.error('Password login failed:', err)
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
        setTimeout(() => setCopiedPassword(false), 2000)
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
      {/* Decorative background orbs */}
      <div
        className="login-orb"
        style={{
          width: 400,
          height: 400,
          background: 'radial-gradient(circle, #0d9488 0%, transparent 70%)',
          top: '-10%',
          right: '-5%',
          animationDelay: '0s',
        }}
      />
      <div
        className="login-orb"
        style={{
          width: 350,
          height: 350,
          background: 'radial-gradient(circle, #06b6d4 0%, transparent 70%)',
          bottom: '-8%',
          left: '-5%',
          animationDelay: '-3s',
          animationDuration: '10s',
        }}
      />
      <div
        className="login-orb"
        style={{
          width: 200,
          height: 200,
          background: 'radial-gradient(circle, #0891b2 0%, transparent 70%)',
          top: '40%',
          left: '15%',
          animationDelay: '-5s',
          animationDuration: '12s',
          opacity: 0.08,
        }}
      />

      {/* Main card */}
      <div
        className={cn(
          'w-full login-card-enter relative z-10',
          needsSetup ? 'max-w-[480px]' : 'max-w-[420px]'
        )}
      >
        <Card
          className="rounded-2xl border-dark-400/15 overflow-hidden"
          style={{
            background:
              'linear-gradient(160deg, rgba(22, 27, 34, 0.92) 0%, rgba(13, 17, 23, 0.96) 100%)',
            boxShadow:
              '0 0 0 1px rgba(255, 255, 255, 0.04), ' +
              '0 20px 60px -10px rgba(0, 0, 0, 0.5), ' +
              '0 0 80px -20px rgba(13, 148, 136, 0.12)',
            backdropFilter: 'blur(20px)',
          }}
        >
          {/* Top accent line */}
          <div
            className="h-[2px] w-full"
            style={{
              background:
                'linear-gradient(90deg, transparent 0%, #0d9488 30%, #06b6d4 70%, transparent 100%)',
            }}
          />

          <CardHeader className="items-center pt-8 pb-2 px-8">
            <div className="flex flex-col items-center gap-4 mb-2">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center relative"
                style={{
                  background: 'linear-gradient(135deg, #0d9488 0%, #06b6d4 100%)',
                  boxShadow: '0 0 40px -5px rgba(13, 148, 136, 0.35)',
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
                  {needsSetup ? 'Первоначальная настройка' : 'Панель администратора'}
                </p>
              </div>
            </div>
          </CardHeader>

          <CardContent className="px-8 pb-8 pt-4">
            {/* Separator */}
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 h-px bg-dark-400/20" />
              <span className="text-xs text-dark-300 font-medium uppercase tracking-wider">
                {needsSetup
                  ? 'Создание администратора'
                  : showPasswordForm
                    ? 'Вход по паролю'
                    : 'Авторизация'}
              </span>
              <div className="flex-1 h-px bg-dark-400/20" />
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
                  {needsSetup ? 'Создание аккаунта...' : 'Авторизация...'}
                </p>
              </div>
            )}

            {!isLoading && (
              <>
                {/* Registration form (first-time setup) */}
                {needsSetup ? (
                  <form onSubmit={handleRegister} className="space-y-4 mb-5">
                    <div
                      className="p-3 rounded-lg border border-teal-500/20 mb-4"
                      style={{
                        background:
                          'linear-gradient(135deg, rgba(13, 148, 136, 0.06) 0%, rgba(6, 182, 212, 0.04) 100%)',
                      }}
                    >
                      <p className="text-xs text-teal-300/80 leading-relaxed">
                        Добро пожаловать! Для начала работы создайте учётную запись администратора.
                        Сохраните пароль в надёжном месте.
                      </p>
                    </div>

                    {/* Username */}
                    <div className="space-y-2">
                      <Label htmlFor="reg-username" className="text-dark-100 text-sm font-medium">
                        Логин
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
                        <p className="text-[11px] text-red-400">Минимум 3 символа</p>
                      )}
                    </div>

                    {/* Password */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label
                          htmlFor="reg-password"
                          className="text-dark-100 text-sm font-medium"
                        >
                          Пароль
                        </Label>
                        <div className="flex items-center gap-1">
                          {regPassword && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={handleCopyPassword}
                              className="h-6 px-1.5 text-dark-300 hover:text-teal-400"
                              title="Скопировать пароль"
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
                            title="Сгенерировать пароль"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            <span className="text-[11px]">Генератор</span>
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
                        Подтвердите пароль
                      </Label>
                      <PasswordInput
                        id="reg-confirm-password"
                        value={regConfirmPassword}
                        onChange={setRegConfirmPassword}
                        autoComplete="new-password"
                        placeholder="Повторите пароль"
                      />
                      {regConfirmPassword.length > 0 && !regPasswordsMatch && (
                        <p className="text-[11px] text-red-400">Пароли не совпадают</p>
                      )}
                      {regPasswordsMatch && (
                        <p className="text-[11px] text-green-400 flex items-center gap-1">
                          <Check className="w-3 h-3" /> Пароли совпадают
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
                      Создать аккаунт
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
                            Логин
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
                            Пароль
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
                          Войти
                        </Button>
                      </form>
                    ) : (
                      /* Telegram Login Widget */
                      <div ref={containerRef} className="flex justify-center mb-5 min-h-[40px]" />
                    )}

                    {/* Toggle auth method */}
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
                          <>Войти через Telegram</>
                        ) : (
                          <>
                            <Lock className="h-3 w-3" />
                            Войти по логину и паролю
                          </>
                        )}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}

            {/* Footer */}
            <div className="mt-8 pt-5 border-t border-dark-400/10">
              <p className="text-center text-[11px] text-dark-300/80 leading-relaxed">
                {needsSetup
                  ? 'Пароль должен содержать минимум 8 символов, заглавные и строчные буквы, цифру и спецсимвол'
                  : 'Доступ только для авторизованных администраторов'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
