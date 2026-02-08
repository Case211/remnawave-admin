import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { TelegramUser } from '../api/auth'
import { User, Lock, AlertCircle, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
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
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{
        background: 'linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
      }}
    >
      <div className="w-full max-w-md animate-fade-in">
        <Card
          className="rounded-2xl border-dark-400/20"
          style={{
            background: 'linear-gradient(135deg, rgba(22, 27, 34, 0.95) 0%, rgba(13, 17, 23, 0.95) 100%)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4), 0 0 60px -10px rgba(13, 148, 136, 0.15)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <CardHeader className="items-center pb-2">
            {/* Logo */}
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{
                  background: 'linear-gradient(135deg, #0d9488 0%, #06b6d4 100%)',
                  boxShadow: '0 0 30px -5px rgba(13, 148, 136, 0.4)',
                }}
              >
                <span className="text-white font-bold text-xl">R</span>
              </div>
              <div>
                <CardTitle className="text-2xl font-display font-bold">Remnawave</CardTitle>
                <CardDescription className="text-dark-200">
                  Панель администратора
                </CardDescription>
              </div>
            </div>

            {/* Description */}
            <CardDescription className="text-center text-dark-200">
              Войдите для доступа к панели управления
            </CardDescription>
          </CardHeader>

          <CardContent className="pt-4">
            {/* Error */}
            {error && (
              <div
                className="mb-6 p-4 rounded-lg border"
                style={{
                  background: 'linear-gradient(135deg, rgba(250, 82, 82, 0.15) 0%, rgba(239, 68, 68, 0.1) 100%)',
                  borderColor: 'rgba(250, 82, 82, 0.3)',
                }}
              >
                <div className="flex items-center justify-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
                  <p className="text-sm text-red-400 text-center whitespace-pre-wrap">{error}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearError}
                  className={cn(
                    "mt-2 mx-auto flex items-center gap-1 text-xs text-red-400",
                    "hover:text-red-300 hover:bg-transparent h-auto py-1"
                  )}
                >
                  <X className="h-3 w-3" />
                  Закрыть
                </Button>
              </div>
            )}

            {/* Loading */}
            {isLoading && (
              <div className="flex flex-col items-center mb-6">
                <Loader2
                  className="h-8 w-8 animate-spin text-teal-500"
                />
                <p className="mt-2 text-sm text-dark-200">Авторизация...</p>
              </div>
            )}

            {!isLoading && (
              <>
                {/* Password login form */}
                {showPasswordForm ? (
                  <form onSubmit={handlePasswordLogin} className="space-y-4 mb-6">
                    <div className="space-y-1.5">
                      <Label htmlFor="username" className="text-dark-200">
                        <User className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
                        Логин
                      </Label>
                      <Input
                        id="username"
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="admin"
                        autoComplete="username"
                        autoFocus
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="password" className="text-dark-200">
                        <Lock className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />
                        Пароль
                      </Label>
                      <Input
                        id="password"
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="********"
                        autoComplete="current-password"
                      />
                    </div>
                    <Button
                      type="submit"
                      variant="default"
                      className="w-full"
                      disabled={!username.trim() || !password.trim()}
                    >
                      Войти
                    </Button>
                  </form>
                ) : (
                  /* Telegram Login Widget */
                  <div ref={containerRef} className="flex justify-center mb-6" />
                )}

                {/* Toggle auth method */}
                <div className="text-center">
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => { setShowPasswordForm(!showPasswordForm); clearError() }}
                    className="text-xs text-dark-300 hover:text-primary-400 h-auto p-0"
                  >
                    {showPasswordForm ? 'Войти через Telegram' : 'Войти по логину и паролю'}
                  </Button>
                </div>
              </>
            )}

            {/* Footer */}
            <p className="mt-8 text-center text-xs text-dark-300">
              Доступ только для авторизованных администраторов
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
