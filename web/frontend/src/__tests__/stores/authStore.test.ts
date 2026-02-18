import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAuthStore } from '@/store/authStore'

// Mock auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    telegramLogin: vi.fn(),
    passwordLogin: vi.fn(),
    register: vi.fn(),
    refreshToken: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    getSetupStatus: vi.fn(),
    changePassword: vi.fn(),
  },
}))

// Mock authBridge (imported by authStore at module level)
vi.mock('@/store/authBridge', () => ({
  registerAuthGetter: vi.fn(),
}))

// Helper: create a JWT-like token with given exp
function makeToken(exp: number): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(JSON.stringify({ exp, sub: 'test' }))
  return `${header}.${payload}.signature`
}

describe('authStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset store to initial state
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    })
  })

  describe('initial state', () => {
    it('starts unauthenticated', () => {
      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.isLoading).toBe(false)
      expect(state.error).toBeNull()
    })
  })

  describe('login (telegram)', () => {
    it('sets user and tokens on success', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.telegramLogin).mockResolvedValue({
        access_token: 'acc-123',
        refresh_token: 'ref-456',
        token_type: 'bearer',
        expires_in: 3600,
      })

      await useAuthStore.getState().login({
        id: 1001,
        first_name: 'Alice',
        last_name: 'Smith',
        username: 'alice',
        photo_url: 'https://example.com/photo.jpg',
        auth_date: 1700000000,
        hash: 'abc123',
      })

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.accessToken).toBe('acc-123')
      expect(state.refreshToken).toBe('ref-456')
      expect(state.user?.username).toBe('alice')
      expect(state.user?.authMethod).toBe('telegram')
      expect(state.user?.telegramId).toBe(1001)
      expect(state.isLoading).toBe(false)
    })

    it('sets error and throws on failure', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.telegramLogin).mockRejectedValue(new Error('Invalid hash'))

      await expect(
        useAuthStore.getState().login({
          id: 1001,
          first_name: 'Alice',
          auth_date: 1700000000,
          hash: 'bad',
        })
      ).rejects.toThrow('Invalid hash')

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(false)
      expect(state.error).toBe('Invalid hash')
      expect(state.isLoading).toBe(false)
    })
  })

  describe('loginWithPassword', () => {
    it('sets user and tokens on success', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.passwordLogin).mockResolvedValue({
        access_token: 'acc-pw',
        refresh_token: 'ref-pw',
        token_type: 'bearer',
        expires_in: 3600,
      })

      await useAuthStore.getState().loginWithPassword({
        username: 'admin',
        password: 'secret',
      })

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.accessToken).toBe('acc-pw')
      expect(state.user?.username).toBe('admin')
      expect(state.user?.authMethod).toBe('password')
    })

    it('sets error and throws on failure', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.passwordLogin).mockRejectedValue(new Error('Wrong password'))

      await expect(
        useAuthStore.getState().loginWithPassword({ username: 'admin', password: 'wrong' })
      ).rejects.toThrow('Wrong password')

      expect(useAuthStore.getState().error).toBe('Wrong password')
    })
  })

  describe('register', () => {
    it('sets user and tokens on success', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.register).mockResolvedValue({
        access_token: 'acc-reg',
        refresh_token: 'ref-reg',
        token_type: 'bearer',
        expires_in: 3600,
      })

      await useAuthStore.getState().register({
        username: 'newadmin',
        password: 'strongpass',
      })

      const state = useAuthStore.getState()
      expect(state.isAuthenticated).toBe(true)
      expect(state.accessToken).toBe('acc-reg')
      expect(state.user?.username).toBe('newadmin')
      expect(state.user?.authMethod).toBe('password')
    })

    it('sets error and throws on failure', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.register).mockRejectedValue(new Error('Username taken'))

      await expect(
        useAuthStore.getState().register({ username: 'taken', password: 'pass' })
      ).rejects.toThrow('Username taken')

      expect(useAuthStore.getState().error).toBe('Username taken')
    })
  })

  describe('logout', () => {
    it('clears state immediately', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.logout).mockResolvedValue()

      // Set authenticated state first
      useAuthStore.setState({
        user: { username: 'admin', firstName: 'Admin', authMethod: 'password' },
        accessToken: 'token-123',
        refreshToken: 'refresh-123',
        isAuthenticated: true,
      })

      useAuthStore.getState().logout()

      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.accessToken).toBeNull()
      expect(state.refreshToken).toBeNull()
      expect(state.isAuthenticated).toBe(false)
    })

    it('calls API logout (fire-and-forget) when token exists', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.logout).mockResolvedValue()

      useAuthStore.setState({
        accessToken: 'token-123',
        isAuthenticated: true,
      })

      useAuthStore.getState().logout()

      expect(authApi.logout).toHaveBeenCalled()
    })

    it('does not call API logout when no token', async () => {
      const { authApi } = await import('@/api/auth')

      useAuthStore.setState({ accessToken: null, isAuthenticated: true })
      useAuthStore.getState().logout()

      expect(authApi.logout).not.toHaveBeenCalled()
    })
  })

  describe('setTokens', () => {
    it('updates tokens in state', () => {
      useAuthStore.getState().setTokens('new-access', 'new-refresh')

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('new-access')
      expect(state.refreshToken).toBe('new-refresh')
    })
  })

  describe('clearError', () => {
    it('clears the error', () => {
      useAuthStore.setState({ error: 'Something went wrong' })
      useAuthStore.getState().clearError()
      expect(useAuthStore.getState().error).toBeNull()
    })
  })

  describe('validateSession', () => {
    it('does nothing when not authenticated', async () => {
      useAuthStore.setState({ isAuthenticated: false })
      await useAuthStore.getState().validateSession()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('clears session when no tokens at all', async () => {
      useAuthStore.setState({
        isAuthenticated: true,
        accessToken: null,
        refreshToken: null,
      })

      await useAuthStore.getState().validateSession()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('keeps session when access token is valid', async () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600 // 1 hour from now
      useAuthStore.setState({
        isAuthenticated: true,
        accessToken: makeToken(futureExp),
        refreshToken: 'ref-token',
      })

      await useAuthStore.getState().validateSession()
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })

    it('refreshes when access token expired but refresh token valid', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.refreshToken).mockResolvedValue({
        access_token: 'new-access',
        refresh_token: 'new-refresh',
        token_type: 'bearer',
        expires_in: 3600,
      })

      const pastExp = Math.floor(Date.now() / 1000) - 60 // expired 1 min ago
      const futureExp = Math.floor(Date.now() / 1000) + 3600 // valid refresh
      useAuthStore.setState({
        isAuthenticated: true,
        accessToken: makeToken(pastExp),
        refreshToken: makeToken(futureExp),
      })

      await useAuthStore.getState().validateSession()

      const state = useAuthStore.getState()
      expect(state.accessToken).toBe('new-access')
      expect(state.refreshToken).toBe('new-refresh')
      expect(state.isAuthenticated).toBe(true)
    })

    it('clears session when refresh also fails', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.refreshToken).mockRejectedValue(new Error('Expired'))

      const pastExp = Math.floor(Date.now() / 1000) - 60
      const futureRefresh = Math.floor(Date.now() / 1000) + 3600
      useAuthStore.setState({
        isAuthenticated: true,
        accessToken: makeToken(pastExp),
        refreshToken: makeToken(futureRefresh),
      })

      await useAuthStore.getState().validateSession()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('clears session when both tokens expired', async () => {
      const pastExp = Math.floor(Date.now() / 1000) - 60
      useAuthStore.setState({
        isAuthenticated: true,
        accessToken: makeToken(pastExp),
        refreshToken: makeToken(pastExp),
      })

      await useAuthStore.getState().validateSession()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })
})
