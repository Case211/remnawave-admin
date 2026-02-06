import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

/**
 * Get the API base URL.
 * If VITE_API_URL is empty, use relative path (recommended for same-domain nginx proxy).
 * If VITE_API_URL is set to http:// but page is on https://, auto-upgrade to https://
 * to prevent Mixed Content browser errors.
 */
function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL || ''
  if (!envUrl) return '/api/v2'

  // Auto-fix Mixed Content: upgrade http:// to https:// if page is served over HTTPS
  if (
    typeof window !== 'undefined' &&
    window.location.protocol === 'https:' &&
    envUrl.startsWith('http://')
  ) {
    return envUrl.replace('http://', 'https://') + '/api/v2'
  }

  return `${envUrl}/api/v2`
}

/**
 * Axios client with interceptors for auth
 */
const client = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

/**
 * Request interceptor - add auth token
 */
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Get token from localStorage (zustand persist)
    const authData = localStorage.getItem('remnawave-auth')
    if (authData) {
      try {
        const { state } = JSON.parse(authData)
        if (state?.accessToken) {
          config.headers.Authorization = `Bearer ${state.accessToken}`
        }
      } catch {
        // Ignore parse errors
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

/**
 * Response interceptor - handle errors and token refresh
 */
client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // If 401 and not already retrying, try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const authData = localStorage.getItem('remnawave-auth')
      if (authData) {
        try {
          const { state } = JSON.parse(authData)
          if (state?.refreshToken) {
            // Try to refresh (use same baseURL as the main client)
            const response = await axios.post(`${getApiBaseUrl()}/auth/refresh`, {
              refresh_token: state.refreshToken,
            })

            const { access_token, refresh_token } = response.data

            // Update tokens in localStorage
            const newState = {
              ...state,
              accessToken: access_token,
              refreshToken: refresh_token,
            }
            localStorage.setItem('remnawave-auth', JSON.stringify({ state: newState }))

            // Retry original request
            originalRequest.headers.Authorization = `Bearer ${access_token}`
            return client(originalRequest)
          }
        } catch {
          // Refresh failed - clear auth and redirect to login
          localStorage.removeItem('remnawave-auth')
          window.location.href = '/login'
        }
      }
    }

    return Promise.reject(error)
  }
)

export default client
