import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi, TelegramUser } from '../api/auth'

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
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
