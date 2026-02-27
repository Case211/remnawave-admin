import { describe, it, expect, beforeEach, vi } from 'vitest'
import { AxiosError } from 'axios'

// Mock the client module
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

// Mock authBridge (imported transitively via client -> authStore)
vi.mock('@/store/authBridge', () => ({
  registerAuthGetter: vi.fn(),
  getAuthState: vi.fn(() => null),
}))

import { authApi } from '@/api/auth'
import client from '@/api/client'

describe('authApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getSetupStatus', () => {
    it('returns setup status on success', async () => {
      vi.mocked(client.get).mockResolvedValue({ data: { needs_setup: true } })

      const result = await authApi.getSetupStatus()
      expect(result.needs_setup).toBe(true)
      expect(client.get).toHaveBeenCalledWith('/auth/setup-status')
    })

    it('returns needs_setup: false on error', async () => {
      vi.mocked(client.get).mockRejectedValue(new Error('Network error'))

      const result = await authApi.getSetupStatus()
      expect(result.needs_setup).toBe(false)
    })
  })

  describe('register', () => {
    it('returns tokens on success', async () => {
      const tokenResponse = {
        access_token: 'acc',
        refresh_token: 'ref',
        token_type: 'bearer',
        expires_in: 3600,
      }
      vi.mocked(client.post).mockResolvedValue({ data: tokenResponse })

      const result = await authApi.register({ username: 'admin', password: 'pass' })
      expect(result.access_token).toBe('acc')
      expect(client.post).toHaveBeenCalledWith('/auth/register', { username: 'admin', password: 'pass' })
    })

    it('throws with error message on failure', async () => {
      const axiosError = new AxiosError('Request failed')
      axiosError.response = {
        data: { detail: 'Username already taken' },
        status: 409,
        statusText: 'Conflict',
        headers: {},
        config: {} as any,
      }
      vi.mocked(client.post).mockRejectedValue(axiosError)

      await expect(authApi.register({ username: 'taken', password: 'pass' })).rejects.toThrow(
        'Username already taken'
      )
    })
  })

  describe('telegramLogin', () => {
    it('sends telegram user data and returns tokens', async () => {
      const tokenResponse = {
        access_token: 'tg-acc',
        refresh_token: 'tg-ref',
        token_type: 'bearer',
        expires_in: 3600,
      }
      vi.mocked(client.post).mockResolvedValue({ data: tokenResponse })

      const telegramUser = {
        id: 1234,
        first_name: 'Test',
        auth_date: 1700000000,
        hash: 'abc',
      }

      const result = await authApi.telegramLogin(telegramUser)
      expect(result.access_token).toBe('tg-acc')
      expect(client.post).toHaveBeenCalledWith('/auth/telegram', telegramUser)
    })
  })

  describe('passwordLogin', () => {
    it('sends credentials and returns tokens', async () => {
      const tokenResponse = {
        access_token: 'pw-acc',
        refresh_token: 'pw-ref',
        token_type: 'bearer',
        expires_in: 3600,
      }
      vi.mocked(client.post).mockResolvedValue({ data: tokenResponse })

      const result = await authApi.passwordLogin({ username: 'admin', password: 'pass' })
      expect(result.access_token).toBe('pw-acc')
      expect(client.post).toHaveBeenCalledWith('/auth/login', { username: 'admin', password: 'pass' })
    })

    it('throws friendly message for 401', async () => {
      const axiosError = new AxiosError('Unauthorized')
      axiosError.response = {
        data: {},
        status: 401,
        statusText: 'Unauthorized',
        headers: {},
        config: {} as any,
      }
      vi.mocked(client.post).mockRejectedValue(axiosError)

      await expect(authApi.passwordLogin({ username: 'admin', password: 'wrong' })).rejects.toThrow(
        'Authentication failed'
      )
    })

    it('throws friendly message for 403', async () => {
      const axiosError = new AxiosError('Forbidden')
      axiosError.response = {
        data: {},
        status: 403,
        statusText: 'Forbidden',
        headers: {},
        config: {} as any,
      }
      vi.mocked(client.post).mockRejectedValue(axiosError)

      await expect(authApi.passwordLogin({ username: 'user', password: 'pass' })).rejects.toThrow(
        'Access denied'
      )
    })

    it('throws friendly message for 429', async () => {
      const axiosError = new AxiosError('Too Many Requests')
      axiosError.response = {
        data: { detail: 'Slow down' },
        status: 429,
        statusText: 'Too Many Requests',
        headers: {},
        config: {} as any,
      }
      vi.mocked(client.post).mockRejectedValue(axiosError)

      await expect(authApi.passwordLogin({ username: 'admin', password: 'pass' })).rejects.toThrow(
        'Slow down'
      )
    })
  })

  describe('refreshToken', () => {
    it('sends refresh token and returns new tokens', async () => {
      vi.mocked(client.post).mockResolvedValue({
        data: {
          access_token: 'new-acc',
          refresh_token: 'new-ref',
          token_type: 'bearer',
          expires_in: 3600,
        },
      })

      const result = await authApi.refreshToken('old-refresh')
      expect(result.access_token).toBe('new-acc')
      expect(client.post).toHaveBeenCalledWith('/auth/refresh', { refresh_token: 'old-refresh' })
    })
  })

  describe('getMe', () => {
    it('returns admin info', async () => {
      const adminInfo = {
        telegram_id: null,
        username: 'admin',
        role: 'superadmin',
        role_id: 1,
        auth_method: 'password',
        password_is_generated: false,
        permissions: [],
      }
      vi.mocked(client.get).mockResolvedValue({ data: adminInfo })

      const result = await authApi.getMe()
      expect(result.username).toBe('admin')
      expect(client.get).toHaveBeenCalledWith('/auth/me')
    })
  })

  describe('changePassword', () => {
    it('sends change password request', async () => {
      vi.mocked(client.post).mockResolvedValue({ data: {} })

      await authApi.changePassword({ current_password: 'old', new_password: 'new' })
      expect(client.post).toHaveBeenCalledWith('/auth/change-password', {
        current_password: 'old',
        new_password: 'new',
      })
    })

    it('throws on error', async () => {
      const axiosError = new AxiosError('Bad request')
      axiosError.response = {
        data: { detail: 'Current password is incorrect' },
        status: 400,
        statusText: 'Bad Request',
        headers: {},
        config: {} as any,
      }
      vi.mocked(client.post).mockRejectedValue(axiosError)

      await expect(
        authApi.changePassword({ current_password: 'wrong', new_password: 'new' })
      ).rejects.toThrow('Current password is incorrect')
    })
  })

  describe('logout', () => {
    it('sends logout request', async () => {
      vi.mocked(client.post).mockResolvedValue({ data: {} })

      await authApi.logout()
      expect(client.post).toHaveBeenCalledWith('/auth/logout')
    })
  })
})

describe('getErrorMessage (via API methods)', () => {
  it('extracts detail from AxiosError response', async () => {
    const axiosError = new AxiosError('Fail')
    axiosError.response = {
      data: { detail: 'Custom API error' },
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as any,
    }
    vi.mocked(client.post).mockRejectedValue(axiosError)

    await expect(authApi.register({ username: 'x', password: 'y' })).rejects.toThrow('Custom API error')
  })

  it('uses error.message for non-Axios errors', async () => {
    vi.mocked(client.post).mockRejectedValue(new Error('Network offline'))

    await expect(authApi.register({ username: 'x', password: 'y' })).rejects.toThrow('Network offline')
  })

  it('uses generic message for unknown errors', async () => {
    vi.mocked(client.post).mockRejectedValue('something weird')

    await expect(authApi.register({ username: 'x', password: 'y' })).rejects.toThrow(
      'An unexpected error occurred'
    )
  })
})
