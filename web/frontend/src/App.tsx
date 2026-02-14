import { useEffect, useState, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { usePermissionStore } from './store/permissionStore'
import { AppearanceProvider } from './components/AppearanceProvider'
import { ErrorBoundary } from './components/ErrorBoundary'

// Layout (always loaded — shell of the app)
import Layout from './components/layout/Layout'

// Critical pages — direct import (first thing users see, must load instantly)
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'

// Helper: retry dynamic import on failure (handles stale SW cache / network hiccups)
function lazyRetry<T extends { default: React.ComponentType }>(
  factory: () => Promise<T>,
): React.LazyExoticComponent<T['default']> {
  return lazy(() =>
    factory().catch(() =>
      // First failure — retry once after a short delay
      new Promise<T>((resolve) => setTimeout(resolve, 1500)).then(() =>
        factory().catch(() => {
          // Second failure — force reload to get fresh assets
          window.location.reload()
          // Return a never-resolving promise so we don't render stale content
          return new Promise<T>(() => {})
        }),
      ),
    ),
  )
}

// Lazy-loaded pages — each becomes a separate chunk
const Users = lazyRetry(() => import('./pages/Users'))
const UserDetail = lazyRetry(() => import('./pages/UserDetail'))
const Nodes = lazyRetry(() => import('./pages/Nodes'))
const Fleet = lazyRetry(() => import('./pages/Fleet'))
const Hosts = lazyRetry(() => import('./pages/Hosts'))
const Violations = lazyRetry(() => import('./pages/Violations'))
const Settings = lazyRetry(() => import('./pages/Settings'))
const Admins = lazyRetry(() => import('./pages/Admins'))
const AuditLog = lazyRetry(() => import('./pages/AuditLog'))
const SystemLogs = lazyRetry(() => import('./pages/SystemLogs'))
const Analytics = lazyRetry(() => import('./pages/Analytics'))
const Automations = lazyRetry(() => import('./pages/automations'))
const Notifications = lazyRetry(() => import('./pages/Notifications'))
const MailServer = lazyRetry(() => import('./pages/MailServer'))

/** Lightweight loading skeleton shown while a page chunk is loading */
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
      </div>
    </div>
  )
}

/**
 * Protected route wrapper - redirects to login if not authenticated.
 * Also loads RBAC permissions on first mount.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  const { isLoaded, loadPermissions } = usePermissionStore()

  useEffect(() => {
    if (isAuthenticated && !isLoaded) {
      loadPermissions()
    }
  }, [isAuthenticated, isLoaded, loadPermissions])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

/**
 * Main App component with routing.
 * Validates the persisted session on startup to clear expired tokens
 * before rendering protected routes.
 */
export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const validateSession = useAuthStore((s) => s.validateSession)
  const clearPermissions = usePermissionStore((s) => s.clearPermissions)
  const [isValidating, setIsValidating] = useState(true)

  // Validate persisted session on app startup (with safety timeout)
  useEffect(() => {
    const timeout = setTimeout(() => setIsValidating(false), 5000)
    validateSession().finally(() => {
      clearTimeout(timeout)
      setIsValidating(false)
    })
    return () => clearTimeout(timeout)
  }, [validateSession])

  // Clear permissions on logout
  useEffect(() => {
    if (!isAuthenticated) {
      clearPermissions()
    }
  }, [isAuthenticated, clearPermissions])

  // Show nothing while validating to prevent flash of protected content
  if (isValidating) {
    return null
  }

  return (
    <ErrorBoundary>
      <AppearanceProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes — Login is direct import, loads instantly */}
            <Route path="/login" element={<Login />} />

            {/* Protected routes */}
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Suspense fallback={<PageLoader />}>
                      <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/users" element={<Users />} />
                        <Route path="/users/:uuid" element={<UserDetail />} />
                        <Route path="/nodes" element={<Nodes />} />
                        <Route path="/fleet" element={<Fleet />} />
                        <Route path="/hosts" element={<Hosts />} />
                        <Route path="/violations" element={<Violations />} />
                        <Route path="/automations" element={<Automations />} />
                        <Route path="/notifications" element={<Notifications />} />
                        <Route path="/mailserver" element={<MailServer />} />
                        <Route path="/admins" element={<Admins />} />
                        <Route path="/audit" element={<AuditLog />} />
                        <Route path="/logs" element={<SystemLogs />} />
                        <Route path="/analytics" element={<Analytics />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                      </Routes>
                    </Suspense>
                  </Layout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
      </AppearanceProvider>
    </ErrorBoundary>
  )
}
