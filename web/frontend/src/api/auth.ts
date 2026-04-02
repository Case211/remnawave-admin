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

export interface LoginResponse {
  access_token?: string
  refresh_token?: string
  token_type?: string
  expires_in?: number
  requires_2fa: boolean
  totp_enabled: boolean
  temp_token?: string
}

export interface TotpSetupResponse {
  secret: string
  qr_code: string
  provisioning_uri: string
  backup_codes: string[]
}

export interface TotpVerifyRequest {
  code: string
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

export interface AuthMethods {
  telegram: boolean
  password: boolean
  totp_required: boolean
}

interface ApiError {
  detail: string
  code?: string
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
   * Get available auth methods (public endpoint)
   */
  getAuthMethods: async (): Promise<AuthMethods> => {
    try {
      const response = await client.get<AuthMethods>('/auth/methods')
      return response.data
    } catch {
      return { telegram: true, password: true, totp_required: false }
    }
  },

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
  telegramLogin: async (data: TelegramUser): Promise<LoginResponse> => {
    try {
      const response = await client.post<LoginResponse>('/auth/telegram', data)
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Login with username and password
   */
  passwordLogin: async (data: LoginCredentials): Promise<LoginResponse> => {
    try {
      const response = await client.post<LoginResponse>('/auth/login', data)
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * TOTP setup — get QR code and backup codes (requires temp token)
   */
  totpSetup: async (tempToken: string): Promise<TotpSetupResponse> => {
    try {
      const response = await client.post<TotpSetupResponse>(
        '/auth/totp/setup',
        {},
        { headers: { Authorization: `Bearer ${tempToken}` } }
      )
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Confirm TOTP setup with first code (requires temp token)
   */
  totpConfirmSetup: async (tempToken: string, code: string): Promise<TokenResponse> => {
    try {
      const response = await client.post<TokenResponse>(
        '/auth/totp/confirm-setup',
        { code },
        { headers: { Authorization: `Bearer ${tempToken}` } }
      )
      return response.data
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Verify TOTP code (requires temp token)
   */
  totpVerify: async (tempToken: string, code: string): Promise<TokenResponse> => {
    try {
      const response = await client.post<TokenResponse>(
        '/auth/totp/verify',
        { code },
        { headers: { Authorization: `Bearer ${tempToken}` } }
      )
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

  /**
   * Request password reset email
   */
  forgotPassword: async (email: string): Promise<void> => {
    try {
      await client.post('/auth/forgot-password', { email })
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },

  /**
   * Get Telegram OAuth2 authorization URL
   */
  oauth2Authorize: async (): Promise<string> => {
    const response = await client.post<{ authorizationUrl: string }>('/auth/oauth2/authorize')
    return response.data.authorizationUrl
  },

  /**
   * Reset password using token from email
   */
  resetPassword: async (token: string, newPassword: string): Promise<void> => {
    try {
      await client.post('/auth/reset-password', { token, new_password: newPassword })
    } catch (error) {
      throw new Error(getErrorMessage(error))
    }
  },
}
