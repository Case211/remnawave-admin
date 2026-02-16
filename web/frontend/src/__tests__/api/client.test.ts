import { describe, it, expect, beforeEach, vi } from 'vitest'

// We need to test the client module which creates an axios instance and sets up interceptors.
// Since the module has side effects (interceptors registered at import time),
// we test the exported functions and behavior by re-importing with controlled mocks.

// Mock authBridge
const mockGetAuthState = vi.fn()
vi.mock('@/store/authBridge', () => ({
  getAuthState: (...args: unknown[]) => mockGetAuthState(...args),
  registerAuthGetter: vi.fn(),
}))

// Mock authStore (imported by authBridge transitively)
vi.mock('@/store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    })),
    setState: vi.fn(),
  },
}))

// Mock auth API (may be imported by authStore)
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

describe('API client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetAuthState.mockReturnValue(null)
  })

  describe('getApiBaseUrl', () => {
    it('returns relative /api/v2 when no env URL', async () => {
      // The client module reads env at import time, so we verify the client baseURL
      const client = (await import('@/api/client')).default
      // In test env, window.__ENV.API_URL is '' (set in setup.ts), so baseURL is /api/v2
      expect(client.defaults.baseURL).toBe('/api/v2')
    })
  })

  describe('request interceptor', () => {
    it('adds Authorization header when token exists', async () => {
      const client = (await import('@/api/client')).default

      mockGetAuthState.mockReturnValue({
        accessToken: 'my-jwt-token',
        refreshToken: 'ref',
        setTokens: vi.fn(),
        logout: vi.fn(),
      })

      // Get the request interceptor and test it
      // The interceptor is registered on the axios instance
      // We can test by checking the interceptors manager
      const interceptors = (client.interceptors.request as any).handlers
      const requestInterceptor = interceptors.find((h: any) => h?.fulfilled)

      if (requestInterceptor) {
        const config = { headers: {} as Record<string, string> } as any
        const result = requestInterceptor.fulfilled(config)
        expect(result.headers.Authorization).toBe('Bearer my-jwt-token')
      }
    })

    it('does not add Authorization header when no token', async () => {
      const client = (await import('@/api/client')).default

      mockGetAuthState.mockReturnValue(null)

      const interceptors = (client.interceptors.request as any).handlers
      const requestInterceptor = interceptors.find((h: any) => h?.fulfilled)

      if (requestInterceptor) {
        const config = { headers: {} as Record<string, string> } as any
        const result = requestInterceptor.fulfilled(config)
        expect(result.headers.Authorization).toBeUndefined()
      }
    })

    it('does not add Authorization header when token is null', async () => {
      const client = (await import('@/api/client')).default

      mockGetAuthState.mockReturnValue({
        accessToken: null,
        refreshToken: 'ref',
        setTokens: vi.fn(),
        logout: vi.fn(),
      })

      const interceptors = (client.interceptors.request as any).handlers
      const requestInterceptor = interceptors.find((h: any) => h?.fulfilled)

      if (requestInterceptor) {
        const config = { headers: {} as Record<string, string> } as any
        const result = requestInterceptor.fulfilled(config)
        expect(result.headers.Authorization).toBeUndefined()
      }
    })
  })

  describe('client configuration', () => {
    it('has correct default headers', async () => {
      const client = (await import('@/api/client')).default
      expect(client.defaults.headers['Content-Type']).toBe('application/json')
    })

    it('has 30s timeout', async () => {
      const client = (await import('@/api/client')).default
      expect(client.defaults.timeout).toBe(30000)
    })
  })

  describe('response interceptor', () => {
    it('has response interceptors registered', async () => {
      const client = (await import('@/api/client')).default
      const interceptors = (client.interceptors.response as any).handlers
      expect(interceptors.length).toBeGreaterThan(0)
    })
  })
})
