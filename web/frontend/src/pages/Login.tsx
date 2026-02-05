import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { TelegramUser } from '../api/auth'

// Extend window for Telegram widget
declare global {
  interface Window {
    TelegramLoginWidget: {
      dataOnauth: (user: TelegramUser) => void
    }
  }
}

const IS_DEV = import.meta.env.DEV || import.meta.env.VITE_DEBUG === 'true'

export default function Login() {
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { login, isAuthenticated, isLoading, error, clearError } = useAuthStore()
  const [devTelegramId, setDevTelegramId] = useState('')
  const [devUsername, setDevUsername] = useState('dev_admin')
  const [showDevBypass, setShowDevBypass] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/')
      return
    }

    // Telegram Login Widget callback
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

    // Add Telegram Login Widget script
    const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME
    if (!botUsername) {
      console.error('VITE_TELEGRAM_BOT_USERNAME is not set')
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

  const handleDevBypass = async () => {
    if (!devTelegramId) {
      return
    }

    const telegramId = parseInt(devTelegramId, 10)
    if (isNaN(telegramId)) {
      return
    }

    // Create fake TelegramUser with dev_bypass hash
    const devUser: TelegramUser = {
      id: telegramId,
      first_name: devUsername || 'Dev',
      username: devUsername || 'dev_admin',
      auth_date: Math.floor(Date.now() / 1000),
      hash: 'dev_bypass',
    }

    try {
      await login(devUser)
      navigate('/')
    } catch (err) {
      console.error('Dev login failed:', err)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 p-4">
      <div className="w-full max-w-md">
        <div className="bg-dark-900 rounded-2xl border border-dark-700 p-8 shadow-xl">
          {/* Logo */}
          <div className="flex justify-center mb-8">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-primary-600 rounded-xl flex items-center justify-center">
                <span className="text-white font-bold text-xl">R</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Remnawave</h1>
                <p className="text-sm text-gray-500">Admin Panel</p>
              </div>
            </div>
          </div>

          {/* Description */}
          <p className="text-center text-gray-400 mb-8">
            Sign in with your Telegram account to access the admin panel
          </p>

          {/* Error message */}
          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-sm text-red-400 text-center whitespace-pre-wrap">{error}</p>
              <button
                onClick={clearError}
                className="mt-2 text-xs text-red-400 hover:text-red-300 mx-auto block"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex flex-col items-center mb-6">
              <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
              <p className="mt-2 text-sm text-gray-400">Authenticating...</p>
            </div>
          )}

          {/* Telegram Login Widget container */}
          {!isLoading && (
            <div ref={containerRef} className="flex justify-center" />
          )}

          {/* Dev Bypass (only in development) */}
          {IS_DEV && (
            <div className="mt-8 pt-6 border-t border-dark-700">
              <button
                onClick={() => setShowDevBypass(!showDevBypass)}
                className="w-full text-xs text-gray-500 hover:text-gray-400 flex items-center justify-center gap-2"
              >
                <span>{showDevBypass ? 'Hide' : 'Show'} Development Bypass</span>
                <svg
                  className={`w-4 h-4 transform transition-transform ${showDevBypass ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {showDevBypass && (
                <div className="mt-4 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                  <p className="text-xs text-yellow-400 mb-3 text-center">
                    Development only! Bypasses Telegram signature verification.
                  </p>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Telegram ID</label>
                      <input
                        type="text"
                        value={devTelegramId}
                        onChange={(e) => setDevTelegramId(e.target.value)}
                        placeholder="Enter your Telegram ID"
                        className="w-full px-3 py-2 bg-dark-800 border border-dark-600 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Username (optional)</label>
                      <input
                        type="text"
                        value={devUsername}
                        onChange={(e) => setDevUsername(e.target.value)}
                        placeholder="Username"
                        className="w-full px-3 py-2 bg-dark-800 border border-dark-600 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
                      />
                    </div>
                    <button
                      onClick={handleDevBypass}
                      disabled={!devTelegramId || isLoading}
                      className="w-full py-2 px-4 bg-yellow-600 hover:bg-yellow-500 disabled:bg-yellow-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      {isLoading ? 'Logging in...' : 'Dev Login'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Footer */}
          <p className="mt-8 text-center text-xs text-gray-600">
            Only authorized administrators can access this panel
          </p>
        </div>
      </div>
    </div>
  )
}
