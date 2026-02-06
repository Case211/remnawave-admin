import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { TelegramUser } from '../api/auth'

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
  const { login, isAuthenticated, isLoading, error, clearError } = useAuthStore()

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

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{
        background: 'linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
      }}
    >
      <div className="w-full max-w-md animate-fade-in">
        <div
          className="rounded-2xl p-8 border border-dark-400/20"
          style={{
            background: 'linear-gradient(135deg, rgba(22, 27, 34, 0.95) 0%, rgba(13, 17, 23, 0.95) 100%)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4), 0 0 60px -10px rgba(13, 148, 136, 0.15)',
            backdropFilter: 'blur(12px)',
          }}
        >
          {/* Logo */}
          <div className="flex justify-center mb-8">
            <div className="flex items-center gap-3">
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
                <h1 className="text-2xl font-display font-bold text-white">Remnawave</h1>
                <p className="text-sm text-dark-200">Панель администратора</p>
              </div>
            </div>
          </div>

          {/* Description */}
          <p className="text-center text-dark-200 mb-8">
            Войдите через Telegram для доступа к панели управления
          </p>

          {/* Error */}
          {error && (
            <div
              className="mb-6 p-4 rounded-lg border"
              style={{
                background: 'linear-gradient(135deg, rgba(250, 82, 82, 0.15) 0%, rgba(239, 68, 68, 0.1) 100%)',
                borderColor: 'rgba(250, 82, 82, 0.3)',
              }}
            >
              <p className="text-sm text-red-400 text-center whitespace-pre-wrap">{error}</p>
              <button
                onClick={clearError}
                className="mt-2 text-xs text-red-400 hover:text-red-300 mx-auto block transition-all duration-200"
              >
                Закрыть
              </button>
            </div>
          )}

          {/* Loading */}
          {isLoading && (
            <div className="flex flex-col items-center mb-6">
              <div
                className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
                style={{ borderColor: '#0d9488', borderTopColor: 'transparent' }}
              ></div>
              <p className="mt-2 text-sm text-dark-200">Авторизация...</p>
            </div>
          )}

          {/* Telegram Login Widget */}
          {!isLoading && (
            <div ref={containerRef} className="flex justify-center" />
          )}

          {/* Footer */}
          <p className="mt-8 text-center text-xs text-dark-300">
            Доступ только для авторизованных администраторов
          </p>
        </div>
      </div>
    </div>
  )
}
