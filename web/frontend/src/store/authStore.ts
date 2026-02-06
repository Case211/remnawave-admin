import { create } from 'zustand'
import { persist, type StateStorage } from 'zustand/middleware'
import { authApi, TelegramUser } from '../api/auth'

// Safe localStorage wrapper to prevent kQuotaBytesPerItem errors
const safeStorage: StateStorage = {
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
      // Quota exceeded — clear stale data and retry
      try {
        localStorage.removeItem(name)
        localStorage.setItem(name, value)
      } catch {
        // Storage completely full — ignore
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
  telegramId: number
  username: string
  firstName: string
  lastName?: string
  photoUrl?: string
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  login: (telegramUser: TelegramUser) => Promise<void>
  logout: () => void
  setTokens: (accessToken: string, refreshToken: string) => void
  clearError: () => void
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

      login: async (telegramUser: TelegramUser) => {
        set({ isLoading: true, error: null })

        try {
          const response = await authApi.telegramLogin(telegramUser)

          set({
            user: {
              telegramId: telegramUser.id,
              username: telegramUser.username || telegramUser.first_name,
              firstName: telegramUser.first_name,
              lastName: telegramUser.last_name,
              photoUrl: telegramUser.photo_url,
            },
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
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

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },

      setTokens: (accessToken: string, refreshToken: string) => {
        set({ accessToken, refreshToken })
      },

      clearError: () => {
        set({ error: null })
      },
    }),
    {
      name: 'remnawave-auth',
      storage: safeStorage,
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
