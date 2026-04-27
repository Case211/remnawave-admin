import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { usePermissionStore } from './store/permissionStore'
import { AppearanceProvider } from './components/AppearanceProvider'
import { ErrorBoundary } from './components/ErrorBoundary'
import { clientLogger } from './lib/clientLogger'
import { ForcePasswordChange } from './components/ForcePasswordChange'

// Normalize SECRET_PATH: ensure leading slash for BrowserRouter basename
const rawSecretPath = window.__ENV?.SECRET_PATH || '/'
const routerBasename = rawSecretPath.startsWith('/') ? rawSecretPath : `/${rawSecretPath}`

// Layout
import Layout from './components/layout/Layout'

// Login, Dashboard, ResetPassword loaded eagerly (critical path)
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ResetPassword from './pages/ResetPassword'

// Lazy-loaded pages
const Users = lazy(() => import('./pages/Users'))
const UserDetail = lazy(() => import('./pages/UserDetail'))
const Nodes = lazy(() => import('./pages/Nodes'))
const Fleet = lazy(() => import('./pages/Fleet'))
const Hosts = lazy(() => import('./pages/Hosts'))
const Violations = lazy(() => import('./pages/Violations'))
const Blocking = lazy(() => import('./pages/Blocking'))
const Settings = lazy(() => import('./pages/Settings'))
const Admins = lazy(() => import('./pages/Admins'))
const AuditLog = lazy(() => import('./pages/AuditLog'))
const AdminPlugins = lazy(() => import('./pages/AdminPlugins'))
const SystemLogs = lazy(() => import('./pages/SystemLogs'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Automations = lazy(() => import('./pages/automations'))
const Notifications = lazy(() => import('./pages/Notifications'))
const MailServer = lazy(() => import('./pages/MailServer'))
const Billing = lazy(() => import('./pages/Billing'))
const Backup = lazy(() => import('./pages/Backup'))
const ApiKeys = lazy(() => import('./pages/ApiKeys'))
const Squads = lazy(() => import('./pages/Squads'))
const BedolagaDashboard = lazy(() => import('./pages/bedolaga/BedolagaDashboard'))
const BedolagaCustomers = lazy(() => import('./pages/bedolaga/BedolagaCustomers'))
const BedolagaCustomerDetail = lazy(() => import('./pages/bedolaga/BedolagaCustomerDetail'))
const BedolagaPromo = lazy(() => import('./pages/bedolaga/BedolagaPromo'))
const BedolagaMarketing = lazy(() => import('./pages/bedolaga/BedolagaMarketing'))
const BedolagaReferrals = lazy(() => import('./pages/bedolaga/BedolagaReferrals'))
const NotFound = lazy(() => import('./pages/NotFound'))

// Plugin UI route registry — see web/frontend/src/plugins/registry.tsx
import { PLUGIN_ROUTES } from './plugins/registry'
import { useActivePlugins } from './lib/plugins'

/**
 * Inner shell that renders all protected routes, including any contributed
 * by installed plugins. Lives in its own component so we can call
 * ``useActivePlugins`` (a query hook) inside the authenticated tree.
 *
 * Plugin pages render even when the plugin's license is expired or missing
 * — the page itself reacts to the resulting HTTP 402 from the plugin's API
 * by showing a "buy/renew license" banner.
 */
function ProtectedShell() {
  const { data: activePlugins } = useActivePlugins()
  const pluginRouteEntries = (activePlugins ?? []).flatMap((p) =>
    (PLUGIN_ROUTES[p.id] ?? []).map((r) => ({ key: `${p.id}:${r.path}`, ...r })),
  )

  return (
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
            <Route path="/blocking" element={<Blocking />} />
            <Route path="/automations" element={<Automations />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/mailserver" element={<MailServer />} />
            <Route path="/admins" element={<Admins />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/admin/plugins" element={<AdminPlugins />} />
            <Route path="/logs" element={<SystemLogs />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/billing" element={<Billing />} />
            <Route path="/backups" element={<Backup />} />
            <Route path="/api-keys" element={<ApiKeys />} />
            <Route path="/squads" element={<Squads />} />
            <Route path="/bedolaga" element={<BedolagaDashboard />} />
            <Route path="/bedolaga/customers" element={<BedolagaCustomers />} />
            <Route path="/bedolaga/customers/:id" element={<BedolagaCustomerDetail />} />
            <Route path="/bedolaga/promo" element={<BedolagaPromo />} />
            <Route path="/bedolaga/marketing" element={<BedolagaMarketing />} />
            <Route path="/bedolaga/referrals" element={<BedolagaReferrals />} />
            <Route path="/settings" element={<Settings />} />
            {pluginRouteEntries.map(({ key, path, Component }) => (
              <Route key={key} path={path} element={<Component />} />
            ))}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </Layout>
    </ProtectedRoute>
  )
}

/**
 * Protected route wrapper - redirects to login if not authenticated.
 * Also loads RBAC permissions on first mount.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  const { isLoaded, loadPermissions, mustChangePassword } = usePermissionStore()

  useEffect(() => {
    if (isAuthenticated && !isLoaded) {
      loadPermissions()
    }
  }, [isAuthenticated, isLoaded, loadPermissions])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (isLoaded && mustChangePassword) {
    return <ForcePasswordChange />
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
        <BrowserRouter basename={routerBasename}>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            {/* Protected routes */}
            <Route path="/*" element={<ProtectedShell />} />
          </Routes>
        </BrowserRouter>
      </AppearanceProvider>
    </ErrorBoundary>
  )
}
