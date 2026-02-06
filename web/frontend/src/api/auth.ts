import axios, { AxiosError } from 'axios'
import client from './client'

export interface TelegramUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AdminInfo {
  telegram_id: number
  username: string
  role: string
}

interface ApiError {
  detail: string
}

/**
 * Extract error message from API response
 */
function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>
    if (axiosError.response?.data?.detail) {
      return axiosError.response.data.detail
    }
    if (axiosError.response?.status === 401) {
      return 'Authentication failed. Please try again.'
    }
    if (axiosError.response?.status === 403) {
      return 'Access denied. You are not authorized to access this panel.'
    }
    if (axiosError.message) {
      return axiosError.message
    }
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}

export const authApi = {
  /**
   * Login with Telegram Login Widget data
   */
  telegramLogin: async (data: TelegramUser): Promise<TokenResponse> => {
    try {
      const response = await client.post<TokenResponse>('/auth/telegram', data)
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Refresh access token
   */
  refreshToken: async (refreshToken: string): Promise<TokenResponse> => {
    const response = await client.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return response.data
  },

  /**
   * Get current admin info
   */
  getMe: async (): Promise<AdminInfo> => {
    const response = await client.get<AdminInfo>('/auth/me')
    return response.data
  },

  /**
   * Logout (invalidate tokens)
   */
  logout: async (): Promise<void> => {
    await client.post('/auth/logout')
  },
}
