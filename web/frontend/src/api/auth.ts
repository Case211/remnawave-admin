import axios, { AxiosError } from 'axios'
import { startRegistration, startAuthentication } from '@simplewebauthn/browser'
import client from './client'

export interface Passkey {
  id: number
  name: string | null
  created_at: string | null
  last_used_at: string | null
  transports: string | null
}

export interface OauthProvider {
  slug: string
  name: string
  configured: boolean
}

export interface OauthLink {
  id: number
  provider: string
  email: string | null
  name: string | null
  created_at: string | null
  last_used_at: string | null
}

export interface AdminSession {
  id: string
  auth_method: string | null
  ip: string | null
  user_agent: string | null
  created_at: string | null
  last_seen_at: string | null
  current: boolean
}

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
  account_id: number | null
  max_users: number | null
  max_traffic_gb: number | null
  max_nodes: number | null
  max_hosts: number | null
  users_created: number
  traffic_used_bytes: number
  nodes_created: number
  hosts_created: number
  unlimited_traffic_policy: string
  auth_method: string
  password_is_generated: boolean
  totp_enabled: boolean
  unrestricted_user_access: boolean
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
      const d = axiosError.response.data.detail as unknown
      // detail может прийти объектом {detail, code} — не показываем [object Object]
      if (typeof d === 'string') return d
      if (typeof d === 'object' && d !== null) {
        const nested = (d as { detail?: unknown }).detail
        if (typeof nested === 'string') return nested
      }
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
   * Refresh access token.
   * Без аргумента сервер берёт refresh из HttpOnly cookie rw_refresh;
   * с аргументом — легаси-путь (токен из старого localStorage).
   */
  refreshToken: async (refreshToken?: string | null): Promise<TokenResponse> => {
    const response = await client.post<TokenResponse>(
      '/auth/refresh',
      refreshToken ? { refresh_token: refreshToken } : {}
    )
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

  // ── Passkeys / WebAuthn ──────────────────────────────────────
  /** Зарегистрировать passkey (требует активной сессии) */
  registerPasskey: async (name: string): Promise<void> => {
    const { data } = await client.post('/auth/webauthn/register/begin', {})
    const credential = await startRegistration({ optionsJSON: JSON.parse(data.options) })
    await client.post('/auth/webauthn/register/finish', { token: data.token, credential, name })
  },
  /** Вход по passkey (Face ID / отпечаток / ключ) */
  loginPasskey: async (username?: string): Promise<LoginResponse> => {
    const { data } = await client.post('/auth/webauthn/login/begin', { username: username || null })
    const credential = await startAuthentication({ optionsJSON: JSON.parse(data.options) })
    const res = await client.post<LoginResponse>('/auth/webauthn/login/finish', { token: data.token, credential })
    return res.data
  },
  listPasskeys: async (): Promise<Passkey[]> => {
    const { data } = await client.get('/auth/webauthn/credentials'); return data.items
  },
  deletePasskey: async (id: number): Promise<void> => {
    await client.delete(`/auth/webauthn/credentials/${id}`)
  },

  // ── OAuth2 SSO (Google / GitHub) ─────────────────────────────
  oauthProviders: async (): Promise<OauthProvider[]> => {
    const { data } = await client.get('/auth/oauth/providers'); return data.items
  },
  oauthLoginUrl: async (provider: string): Promise<string> => {
    const { data } = await client.post(`/auth/oauth/${provider}/login-url`); return data.url
  },
  oauthLinkUrl: async (provider: string): Promise<string> => {
    const { data } = await client.post(`/auth/oauth/${provider}/link-url`); return data.url
  },
  oauthCallback: async (code: string, state: string): Promise<{ mode: string; access_token?: string; provider?: string }> => {
    const { data } = await client.post('/auth/oauth/callback', { code, state }); return data
  },
  oauthLinks: async (): Promise<OauthLink[]> => {
    const { data } = await client.get('/auth/oauth/links'); return data.items
  },
  deleteOauthLink: async (id: number): Promise<void> => {
    await client.delete(`/auth/oauth/links/${id}`)
  },
  setOauthProvider: async (
    provider: string, clientId: string, clientSecret: string,
    extra?: { issuer?: string; display_name?: string },
  ): Promise<void> => {
    await client.put(`/auth/oauth/providers/${provider}`, {
      client_id: clientId, client_secret: clientSecret, ...(extra || {}),
    })
  },
  deleteOauthProvider: async (provider: string): Promise<void> => {
    await client.delete(`/auth/oauth/providers/${provider}`)
  },

  // ── Активные сессии ──────────────────────────────────────────
  listSessions: async (): Promise<AdminSession[]> => {
    const { data } = await client.get('/auth/sessions'); return data.items
  },
  revokeSession: async (sid: string): Promise<void> => {
    await client.delete(`/auth/sessions/${sid}`)
  },
  revokeOtherSessions: async (): Promise<void> => {
    await client.post('/auth/sessions/revoke-others')
  },

  // ── 2FA (TOTP) — управление из сессии ────────────────────────
  setup2fa: async (): Promise<TotpSetupResponse> => {
    const { data } = await client.post<TotpSetupResponse>('/auth/2fa/setup'); return data
  },
  enable2fa: async (code: string): Promise<void> => {
    await client.post('/auth/2fa/enable', { code })
  },
  disable2fa: async (code: string): Promise<void> => {
    await client.post('/auth/2fa/disable', { code })
  },
  regenBackupCodes: async (code: string): Promise<string[]> => {
    const { data } = await client.post<TotpSetupResponse>('/auth/2fa/backup-codes', { code })
    return data.backup_codes
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
