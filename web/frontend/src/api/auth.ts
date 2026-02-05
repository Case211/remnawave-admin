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
}

export interface AdminInfo {
  telegram_id: number
  username: string
  role: string
}

export const authApi = {
  /**
   * Login with Telegram Login Widget data
   */
  telegramLogin: async (data: TelegramUser): Promise<TokenResponse> => {
    const response = await client.post<TokenResponse>('/auth/telegram', data)
    return response.data
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
