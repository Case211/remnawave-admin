import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { usePermissionStore } from './store/permissionStore'
import { AppearanceProvider } from './components/AppearanceProvider'
import { ErrorBoundary } from './components/ErrorBoundary'
import { clientLogger } from './lib/clientLogger'

// Layout
import Layout from './components/layout/Layout'

// Login and Dashboard loaded eagerly (critical path)
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'

// Lazy-loaded pages
const Users = lazy(() => import('./pages/Users'))
const UserDetail = lazy(() => import('./pages/UserDetail'))
const Nodes = lazy(() => import('./pages/Nodes'))
const Fleet = lazy(() => import('./pages/Fleet'))
const Hosts = lazy(() => import('./pages/Hosts'))
const Violations = lazy(() => import('./pages/Violations'))
const Settings = lazy(() => import('./pages/Settings'))
const Admins = lazy(() => import('./pages/Admins'))
const AuditLog = lazy(() => import('./pages/AuditLog'))
const SystemLogs = lazy(() => import('./pages/SystemLogs'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Automations = lazy(() => import('./pages/automations'))
const Notifications = lazy(() => import('./pages/Notifications'))
const MailServer = lazy(() => import('./pages/MailServer'))

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

  // Initialize frontend error collection
  useEffect(() => {
    clientLogger.init()
    return () => clientLogger.destroy()
  }, [])

  // Validate persisted session on app startup
  useEffect(() => {
    validateSession().finally(() => setIsValidating(false))
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
            {/* Public routes */}
            <Route path="/login" element={<Login />} />

            {/* Protected routes */}
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Suspense fallback={null}>
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
