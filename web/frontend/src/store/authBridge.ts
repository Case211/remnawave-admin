/**
 * Auth bridge — breaks circular dependency between client.ts and authStore.ts.
 *
 * Problem: client.ts needs access token from authStore, but authStore imports auth.ts
 * which imports client.ts → circular dependency.
 *
 * Solution: authStore registers a getter here, client.ts reads from here.
 */

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  setTokens: (accessToken: string, refreshToken: string) => void
  logout: () => void
}

type AuthGetter = () => AuthState | null

let _getAuth: AuthGetter = () => null

/**
 * Called by authStore.ts after store creation to register the getter.
 */
export function registerAuthGetter(getter: AuthGetter) {
  _getAuth = getter
}

/**
 * Called by client.ts to read current auth state from Zustand (in-memory).
 */
export function getAuthState(): AuthState | null {
  return _getAuth()
}
