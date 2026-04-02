import { create } from 'zustand'
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware'
import {
  authApi,
  TelegramUser,
  LoginCredentials,
  RegisterCredentials,
  TotpSetupResponse,
} from '../api/auth'
import { registerAuthGetter } from './authBridge'

// Safe localStorage wrapper to prevent quota errors
const safeLocalStorage: StateStorage = {
  getItem: (name) => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  },
  setItem: (name, value) => {
    try {
      localStorage.setItem(name, value)
    } catch {
      try {
        localStorage.removeItem(name)
        localStorage.setItem(name, value)
      } catch {
        // Storage full — ignore
      }
    }
  },
  removeItem: (name) => {
    try {
      localStorage.removeItem(name)
    } catch {
      // Ignore
    }
  },
}

interface User {
  telegramId?: number
  username: string
  firstName: string
  lastName?: string
  photoUrl?: string
  authMethod: string
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // 2FA state (transient, not persisted)
  requires2fa: boolean
  totpEnabled: boolean
  tempToken: string | null
  totpSetupData: TotpSetupResponse | null

  // Actions
  login: (telegramUser: TelegramUser) => Promise<void>
  loginWithPassword: (credentials: LoginCredentials) => Promise<void>
  register: (credentials: RegisterCredentials) => Promise<void>
  totpSetup: () => Promise<void>
  totpConfirmSetup: (code: string) => Promise<void>
  totpVerify: (code: string) => Promise<void>
  cancel2fa: () => void
  logout: () => void
  setTokens: (accessToken: string, refreshToken: string) => void
  clearError: () => void
  validateSession: () => Promise<void>
}

/**
 * Check if a JWT token is expired by decoding its payload.
 * Returns true if the token is expired or cannot be decoded.
 */
function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return true
    const payload = JSON.parse(atob(parts[1]))
    if (!payload.exp) return true
    // Add 30s buffer to avoid edge cases where token expires mid-request
    return Date.now() >= (payload.exp - 30) * 1000
  } catch {
    return true
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      requires2fa: false,
      totpEnabled: false,
      tempToken: null,
      totpSetupData: null,

      login: async (telegramUser: TelegramUser) => {
        set({ isLoading: true, error: null })

        try {
          const response = await authApi.telegramLogin(telegramUser)

          if (response.requires_2fa) {
            set({
              requires2fa: true,
              totpEnabled: response.totp_enabled,
              tempToken: response.temp_token || null,
              user: {
                telegramId: telegramUser.id,
                username: telegramUser.username || telegramUser.first_name,
                firstName: telegramUser.first_name,
                lastName: telegramUser.last_name,
                photoUrl: telegramUser.photo_url,
                authMethod: 'telegram',
              },
              isLoading: false,
            })
            return
          }

          set({
            user: {
              telegramId: telegramUser.id,
              username: telegramUser.username || telegramUser.first_name,
              firstName: telegramUser.first_name,
              lastName: telegramUser.last_name,
              photoUrl: telegramUser.photo_url,
              authMethod: 'telegram',
            },
            accessToken: response.access_token || null,
            refreshToken: response.refresh_token || null,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Login failed',
          })
          throw error
        }
      },

      loginWithPassword: async (credentials: LoginCredentials) => {
        set({ isLoading: true, error: null })

        try {
          const response = await authApi.passwordLogin(credentials)

          if (response.requires_2fa) {
            set({
              requires2fa: true,
              totpEnabled: response.totp_enabled,
              tempToken: response.temp_token || null,
              user: {
                username: credentials.username,
                firstName: credentials.username,
                authMethod: 'password',
              },
              isLoading: false,
            })
            return
          }

          set({
            user: {
              username: credentials.username,
              firstName: credentials.username,
              authMethod: 'password',
            },
            accessToken: response.access_token || null,
            refreshToken: response.refresh_token || null,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Login failed',
          })
          throw error
        }
      },

      register: async (credentials: RegisterCredentials) => {
        set({ isLoading: true, error: null })

        try {
          const response = await authApi.register(credentials)

          set({
            user: {
              username: credentials.username,
              firstName: credentials.username,
              authMethod: 'password',
            },
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Registration failed',
          })
          throw error
        }
      },

      totpSetup: async () => {
        const { tempToken } = get()
        if (!tempToken) throw new Error('No temp token')
        set({ isLoading: true, error: null })
        try {
          const data = await authApi.totpSetup(tempToken)
          set({ totpSetupData: data, isLoading: false })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'TOTP setup failed',
          })
          throw error
        }
      },

      totpConfirmSetup: async (code: string) => {
        const { tempToken } = get()
        if (!tempToken) throw new Error('No temp token')
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.totpConfirmSetup(tempToken, code)
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
            requires2fa: false,
            tempToken: null,
            totpSetupData: null,
          })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'TOTP verification failed',
          })
          throw error
        }
      },

      totpVerify: async (code: string) => {
        const { tempToken } = get()
        if (!tempToken) throw new Error('No temp token')
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.totpVerify(tempToken, code)
          set({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
            requires2fa: false,
            tempToken: null,
          })
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'TOTP verification failed',
          })
          throw error
        }
      },

      cancel2fa: () => {
        set({
          requires2fa: false,
          totpEnabled: false,
          tempToken: null,
          totpSetupData: null,
          user: null,
          error: null,
        })
      },

      logout: () => {
        const { accessToken } = get()

        // Clear state immediately for responsive UX
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })

        // Notify backend to blacklist the token (fire-and-forget)
        if (accessToken) {
          authApi.logout().catch(() => {
            // Ignore errors — token will expire naturally
          })
        }
      },

      setTokens: (accessToken: string, refreshToken: string) => {
        set({ accessToken, refreshToken, isAuthenticated: true })
      },

      clearError: () => {
        set({ error: null })
      },

      validateSession: async () => {
        const { accessToken, refreshToken, isAuthenticated } = get()

        // Not authenticated — nothing to validate
        if (!isAuthenticated) return

        // No tokens at all — invalid session
        if (!accessToken && !refreshToken) {
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            error: null,
          })
          return
        }

        // Access token still valid — session OK
        if (accessToken && !isTokenExpired(accessToken)) {
          return
        }

        // Access token expired but refresh token available — try to refresh
        if (refreshToken && !isTokenExpired(refreshToken)) {
          try {
            const response = await authApi.refreshToken(refreshToken)
            set({
              accessToken: response.access_token,
              refreshToken: response.refresh_token,
            })
            return
          } catch {
            // Refresh failed — session is dead
          }
        }

        // Both tokens expired or refresh failed — clear session
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },
    }),
    {
      name: 'remnawave-auth',
      storage: createJSONStorage(() => safeLocalStorage),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Register auth getter for axios interceptor (avoids circular dependency)
registerAuthGetter(() => useAuthStore.getState())
