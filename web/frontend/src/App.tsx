import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { usePermissionStore } from './store/permissionStore'

// Layout
import Layout from './components/layout/Layout'

// Pages
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import UserDetail from './pages/UserDetail'
import Nodes from './pages/Nodes'
import Fleet from './pages/Fleet'
import Hosts from './pages/Hosts'
import Violations from './pages/Violations'
import Settings from './pages/Settings'
import Admins from './pages/Admins'
import AuditLog from './pages/AuditLog'
import SystemLogs from './pages/SystemLogs'
import Analytics from './pages/Analytics'

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
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/users" element={<Users />} />
                  <Route path="/users/:uuid" element={<UserDetail />} />
                  <Route path="/nodes" element={<Nodes />} />
                  <Route path="/fleet" element={<Fleet />} />
                  <Route path="/hosts" element={<Hosts />} />
                  <Route path="/violations" element={<Violations />} />
                  <Route path="/admins" element={<Admins />} />
                  <Route path="/audit" element={<AuditLog />} />
                  <Route path="/logs" element={<SystemLogs />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
