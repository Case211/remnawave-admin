import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, Eye, EyeOff, KeyRound, Check } from 'lucide-react'
import { authApi } from '@/api/auth'
import { usePermissionStore } from '@/store/permissionStore'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

// Password charsets
const PW_LOWER = 'abcdefghijklmnopqrstuvwxyz'
const PW_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
const PW_DIGITS = '0123456789'
const PW_SPECIAL = '!@#$%^&*_+-='
const PW_ALL = PW_LOWER + PW_UPPER + PW_DIGITS + PW_SPECIAL

function generatePassword(length = 16): string {
  const arr = new Uint32Array(length)
  crypto.getRandomValues(arr)
  const pick = (charset: string, rnd: number) => charset[rnd % charset.length]
  const chars = [pick(PW_LOWER, arr[0]), pick(PW_UPPER, arr[1]), pick(PW_DIGITS, arr[2]), pick(PW_SPECIAL, arr[3])]
  for (let i = 4; i < length; i++) chars.push(pick(PW_ALL, arr[i]))
  for (let i = chars.length - 1; i > 0; i--) {
    const j = arr[i] % (i + 1)
    ;[chars[i], chars[j]] = [chars[j], chars[i]]
  }
  return chars.join('')
}

function getPasswordStrength(password: string) {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`"()]/.test(password),
  }
  const passedCount = Object.values(checks).filter(Boolean).length
  let score = passedCount * 16
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10
  score = Math.min(100, score)
  const allChecks = Object.values(checks).every(Boolean)
  return { score, checks, allChecks }
}

function PasswordInput({ value, onChange, placeholder, autoComplete, disabled }: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        disabled={disabled}
        className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 pr-10 text-sm text-white placeholder:text-dark-300 focus:outline-none focus:ring-2 focus:ring-primary-500/50 disabled:opacity-50"
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setShow(!show)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-300 hover:text-dark-100"
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  )
}

export function ForcePasswordChange() {
  const { t } = useTranslation()
  const setMustChangePassword = usePermissionStore((s) => s.setMustChangePassword)
  const logout = useAuthStore((s) => s.logout)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const strength = useMemo(() => getPasswordStrength(newPassword), [newPassword])
  const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0
  const canSubmit = currentPassword.length > 0 && strength.allChecks && passwordsMatch && !saving

  const handleGenerate = () => {
    const pw = generatePassword(16)
    setNewPassword(pw)
    setConfirmPassword(pw)
  }

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSaving(true)
    setError('')
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setMustChangePassword(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('settings.password.error', 'Error'))
    } finally {
      setSaving(false)
    }
  }

  const barColor = strength.score < 30 ? '#ef4444' : strength.score < 60 ? '#f59e0b' : strength.score < 80 ? '#22c55e' : '#10b981'

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-900 p-4">
      <Card className="w-full max-w-md">
        <CardContent className="p-6 space-y-5">
          <div className="text-center space-y-2">
            <ShieldAlert className="w-10 h-10 mx-auto text-yellow-400" />
            <h1 className="text-lg font-semibold text-white">
              {t('forcePassword.title', 'Смена пароля обязательна')}
            </h1>
            <p className="text-sm text-dark-200">
              {t('forcePassword.description', 'Ваш пароль был задан администратором. Для безопасности установите собственный пароль.')}
            </p>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-dark-300">
              {t('settings.password.currentPassword', 'Текущий пароль')}
            </label>
            <PasswordInput
              value={currentPassword}
              onChange={setCurrentPassword}
              placeholder={t('settings.password.enterCurrentPassword', 'Введите текущий пароль')}
              autoComplete="current-password"
              disabled={saving}
            />
          </div>

          <div className="border-t border-dark-700/50" />

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-dark-300">
                {t('settings.password.newPassword', 'Новый пароль')}
              </label>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleGenerate}
                disabled={saving}
                className="h-6 px-2 text-[11px] text-primary-400 hover:text-primary-300"
              >
                <KeyRound className="w-3 h-3 mr-1" />
                {t('settings.password.generator', 'Генератор')}
              </Button>
            </div>
            <PasswordInput
              value={newPassword}
              onChange={setNewPassword}
              placeholder={t('settings.password.enterNewPassword', 'Введите новый пароль')}
              autoComplete="new-password"
              disabled={saving}
            />
            {newPassword && (
              <div className="h-1.5 rounded-full bg-dark-700 overflow-hidden mt-1">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{ width: `${strength.score}%`, backgroundColor: barColor }}
                />
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-dark-300">
              {t('settings.password.confirmNewPassword', 'Подтвердите новый пароль')}
            </label>
            <PasswordInput
              value={confirmPassword}
              onChange={setConfirmPassword}
              placeholder={t('settings.password.repeatNewPassword', 'Повторите новый пароль')}
              autoComplete="new-password"
              disabled={saving}
            />
            {confirmPassword.length > 0 && !passwordsMatch && (
              <p className="text-[11px] text-red-400 mt-1">{t('settings.password.passwordsDoNotMatch', 'Пароли не совпадают')}</p>
            )}
            {confirmPassword.length > 0 && passwordsMatch && (
              <p className="text-[11px] text-green-400 mt-1 flex items-center gap-1">
                <Check className="w-3 h-3" /> {t('settings.password.passwordsMatch', 'Пароли совпадают')}
              </p>
            )}
          </div>

          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-40"
          >
            {saving ? t('common.saving', 'Сохранение...') : t('settings.password.changePassword', 'Сменить пароль')}
          </Button>

          <Button
            variant="ghost"
            onClick={logout}
            className="w-full text-dark-300 hover:text-dark-100 text-xs"
          >
            {t('common.logout', 'Выйти')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
