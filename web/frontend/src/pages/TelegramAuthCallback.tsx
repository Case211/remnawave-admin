import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

/**
 * Handles the token fragment injected by the backend after Telegram OAuth2.
 *
 * Flow:
 *   1. User clicks "Login with Telegram"
 *   2. Frontend calls POST /api/v2/auth/oauth2/authorize -> gets authorizationUrl
 *   3. Browser redirects to oauth.telegram.org
 *   4. Telegram redirects to /oauth2/callback/telegram?code=...&state=...
 *   5. Traefik routes that to our frontend nginx (priority=15)
 *   6. nginx proxies to backend GET /api/v2/auth/oauth2/callback/telegram
 *   7. Backend exchanges code+state with panel, issues JWT,
 *      redirects to /admin/auth/callback/telegram#access_token=...&refresh_token=...
 *   8. This component reads tokens from the URL fragment and stores them.
 *      We wait for isAuthenticated to become true before navigating to /
 *      to avoid ProtectedRoute seeing stale state.
 */
export default function TelegramAuthCallback() {
  const navigate = useNavigate()
  const setTokens = useAuthStore((s) => s.setTokens)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [didSetTokens, setDidSetTokens] = useState(false)
  const called = useRef(false)

  // Step 1: read fragment and store tokens once
  useEffect(() => {
    if (called.current) return
    called.current = true

    const fragment = window.location.hash.slice(1)
    const params = new URLSearchParams(fragment)

    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')

    if (accessToken && refreshToken) {
      // Clear fragment from URL bar before doing anything else
      window.history.replaceState(null, '', window.location.pathname)
      setTokens(accessToken, refreshToken)
      setDidSetTokens(true)
      return
    }

    // Error or missing tokens - redirect to login
    const qp = new URLSearchParams(window.location.search)
    const err = qp.get('tg_error')
    if (err) {
      console.error('Telegram auth error:', err)
    }
    navigate('/login', { replace: true })
  }, [navigate, setTokens])

  // Step 2: navigate to dashboard only after isAuthenticated is true
  useEffect(() => {
    if (didSetTokens && isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [didSetTokens, isAuthenticated, navigate])

  return null
}
