import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { TelegramUser } from '../api/auth'
import { User, Lock, AlertCircle, X, Loader2, Shield, KeyRound } from 'lucide-react'
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

export default function Login() {
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { login, loginWithPassword, isAuthenticated, isLoading, error, clearError } = useAuthStore()

  // Password form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPasswordForm, setShowPasswordForm] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/')
      return
    }

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

    const botUsername = (window as any).__ENV?.TELEGRAM_BOT_USERNAME || import.meta.env.VITE_TELEGRAM_BOT_USERNAME
    if (!botUsername) {
      console.error('TELEGRAM_BOT_USERNAME is not set')
      // If no bot username, show password form by default
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
  }, [isAuthenticated, navigate, login])

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

      {/* Login card */}
      <div className="w-full max-w-[420px] login-card-enter relative z-10">
        <Card
          className="rounded-2xl border-dark-400/15 overflow-hidden"
          style={{
            background: 'linear-gradient(160deg, rgba(22, 27, 34, 0.92) 0%, rgba(13, 17, 23, 0.96) 100%)',
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
              background: 'linear-gradient(90deg, transparent 0%, #0d9488 30%, #06b6d4 70%, transparent 100%)',
            }}
          />

          <CardHeader className="items-center pt-8 pb-2 px-8">
            {/* Logo */}
            <div className="flex flex-col items-center gap-4 mb-2">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center relative"
                style={{
                  background: 'linear-gradient(135deg, #0d9488 0%, #06b6d4 100%)',
                  boxShadow: '0 0 40px -5px rgba(13, 148, 136, 0.35)',
                }}
              >
                <Shield className="w-8 h-8 text-white" strokeWidth={1.8} />
              </div>
              <div className="text-center">
                <h1 className="text-2xl font-display font-bold text-white tracking-tight">
                  Remnawave
                </h1>
                <p className="text-sm text-dark-200 mt-1">
                  Панель администратора
                </p>
              </div>
            </div>
          </CardHeader>

          <CardContent className="px-8 pb-8 pt-4">
            {/* Separator */}
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 h-px bg-dark-400/20" />
              <span className="text-xs text-dark-300 font-medium uppercase tracking-wider">
                {showPasswordForm ? 'Вход по паролю' : 'Авторизация'}
              </span>
              <div className="flex-1 h-px bg-dark-400/20" />
            </div>

            {/* Error */}
            {error && (
              <div
                className="mb-5 p-3.5 rounded-xl border animate-fade-in"
                style={{
                  background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.04) 100%)',
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
                      background: 'radial-gradient(circle, rgba(13, 148, 136, 0.2) 0%, transparent 70%)',
                      transform: 'scale(2)',
                    }}
                  />
                  <Loader2 className="h-8 w-8 animate-spin text-teal-500 relative" />
                </div>
                <p className="mt-3 text-sm text-dark-200">Авторизация...</p>
              </div>
            )}

            {!isLoading && (
              <>
                {/* Password login form */}
                {showPasswordForm ? (
                  <form onSubmit={handlePasswordLogin} className="space-y-4 mb-5">
                    <div className="space-y-2">
                      <Label htmlFor="username" className="text-dark-100 text-sm font-medium">
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
                      <Label htmlFor="password" className="text-dark-100 text-sm font-medium">
                        Пароль
                      </Label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-300" />
                        <Input
                          id="password"
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="••••••••"
                          autoComplete="current-password"
                          className="pl-10"
                        />
                      </div>
                    </div>
                    <Button
                      type="submit"
                      className={cn(
                        "w-full h-11 font-medium text-sm",
                        "bg-gradient-to-r from-teal-600 to-cyan-600",
                        "hover:from-teal-500 hover:to-cyan-500",
                        "shadow-lg shadow-teal-900/20",
                        "transition-all duration-200",
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
                    onClick={() => { setShowPasswordForm(!showPasswordForm); clearError() }}
                    className={cn(
                      "text-xs text-dark-300 hover:text-teal-400",
                      "transition-colors duration-200",
                      "inline-flex items-center gap-1.5",
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

            {/* Footer */}
            <div className="mt-8 pt-5 border-t border-dark-400/10">
              <p className="text-center text-[11px] text-dark-300/80 leading-relaxed">
                Доступ только для авторизованных администраторов
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
