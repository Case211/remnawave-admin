import { useEffect, useState, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { usePermissionStore } from './store/permissionStore'
import { AppearanceProvider } from './components/AppearanceProvider'
import { ErrorBoundary } from './components/ErrorBoundary'

// Layout (always loaded — shell of the app)
import Layout from './components/layout/Layout'

// Lazy-loaded pages — each becomes a separate chunk
const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
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
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* Public routes */}
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
          </Suspense>
        </BrowserRouter>
      </AppearanceProvider>
    </ErrorBoundary>
  )
}
