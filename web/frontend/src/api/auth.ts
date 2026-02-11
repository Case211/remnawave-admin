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

export interface LoginCredentials {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface PermissionEntry {
  resource: string
  action: string
}

export interface AdminInfo {
  telegram_id: number | null
  username: string
  role: string
  role_id: number | null
  auth_method: string
  password_is_generated: boolean
  permissions: PermissionEntry[]
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export interface RegisterCredentials {
  username: string
  password: string
}

export interface SetupStatus {
  needs_setup: boolean
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
    if (axiosError.response?.status === 429) {
      return axiosError.response.data?.detail || 'Too many attempts. Please wait and try again.'
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
   * Check if initial setup (first admin registration) is needed
   */
  getSetupStatus: async (): Promise<SetupStatus> => {
    try {
      const response = await client.get<SetupStatus>('/auth/setup-status')
      return response.data
    } catch (error) {
      // If endpoint fails, assume setup is not needed
      return { needs_setup: false }
    }
  },

  /**
   * Register the first admin account (only works during initial setup)
   */
  register: async (data: RegisterCredentials): Promise<TokenResponse> => {
    try {
      const response = await client.post<TokenResponse>('/auth/register', data)
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

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
   * Login with username and password
   */
  passwordLogin: async (data: LoginCredentials): Promise<TokenResponse> => {
    try {
      const response = await client.post<TokenResponse>('/auth/login', data)
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
   * Change admin password
   */
  changePassword: async (data: ChangePasswordRequest): Promise<void> => {
    try {
      await client.post('/auth/change-password', data)
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Logout (invalidate tokens)
   */
  logout: async (): Promise<void> => {
    await client.post('/auth/logout')
  },
}
