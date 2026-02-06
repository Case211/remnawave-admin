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
    <div className="min-h-screen flex items-center justify-center bg-dark-950 p-4">
      <div className="w-full max-w-md">
        <div className="bg-dark-900 rounded-2xl border border-dark-700 p-8 shadow-xl">
          {/* Логотип */}
          <div className="flex justify-center mb-8">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-primary-600 rounded-xl flex items-center justify-center">
                <span className="text-white font-bold text-xl">R</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Remnawave</h1>
                <p className="text-sm text-gray-500">Панель администратора</p>
              </div>
            </div>
          </div>

          {/* Описание */}
          <p className="text-center text-gray-400 mb-8">
            Войдите через Telegram для доступа к панели управления
          </p>

          {/* Ошибка */}
          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-sm text-red-400 text-center whitespace-pre-wrap">{error}</p>
              <button
                onClick={clearError}
                className="mt-2 text-xs text-red-400 hover:text-red-300 mx-auto block"
              >
                Закрыть
              </button>
            </div>
          )}

          {/* Загрузка */}
          {isLoading && (
            <div className="flex flex-col items-center mb-6">
              <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
              <p className="mt-2 text-sm text-gray-400">Авторизация...</p>
            </div>
          )}

          {/* Telegram Login Widget */}
          {!isLoading && (
            <div ref={containerRef} className="flex justify-center" />
          )}

          {/* Футер */}
          <p className="mt-8 text-center text-xs text-gray-600">
            Доступ только для авторизованных администраторов
          </p>
        </div>
      </div>
    </div>
  )
}
