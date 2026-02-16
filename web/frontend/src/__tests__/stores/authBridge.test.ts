import { describe, it, expect, beforeEach } from 'vitest'
import { registerAuthGetter, getAuthState } from '@/store/authBridge'

describe('authBridge', () => {
  beforeEach(() => {
    // Reset to default getter (returns null)
    registerAuthGetter(() => null)
  })

  it('returns null by default before registration', () => {
    expect(getAuthState()).toBeNull()
  })

  it('returns auth state after registering getter', () => {
    const mockAuth = {
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      setTokens: () => {},
      logout: () => {},
    }

    registerAuthGetter(() => mockAuth)
    expect(getAuthState()).toBe(mockAuth)
  })

  it('returns updated state on subsequent calls', () => {
    let token = 'token-1'

    registerAuthGetter(() => ({
      accessToken: token,
      refreshToken: 'refresh',
      setTokens: () => {},
      logout: () => {},
    }))

    expect(getAuthState()?.accessToken).toBe('token-1')

    token = 'token-2'
    expect(getAuthState()?.accessToken).toBe('token-2')
  })

  it('can override getter with new registration', () => {
    registerAuthGetter(() => ({
      accessToken: 'first',
      refreshToken: 'r1',
      setTokens: () => {},
      logout: () => {},
    }))

    registerAuthGetter(() => ({
      accessToken: 'second',
      refreshToken: 'r2',
      setTokens: () => {},
      logout: () => {},
    }))

    expect(getAuthState()?.accessToken).toBe('second')
  })
})
