import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

/**
 * Axios client with interceptors for auth
 */
const client = axios.create({
  baseURL: `${API_URL}/api/v2`,
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
            // Try to refresh
            const response = await axios.post(`${API_URL}/api/v2/auth/refresh`, {
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
