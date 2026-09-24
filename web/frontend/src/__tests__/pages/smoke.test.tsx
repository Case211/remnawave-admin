/**
 * Smoke tests for all pages — verifies each page renders without throwing.
 *
 * All API calls are mocked to return empty/default data so that pages
 * can mount without a running backend.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { usePermissionStore } from '@/store/permissionStore'
import { useAuthStore } from '@/store/authStore'
import { TooltipProvider } from '@/components/ui/tooltip'

// ── Mock API client ──────────────────────────────────────────
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    defaults: { baseURL: '/api/v2' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

// Mock auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    getMe: vi.fn().mockResolvedValue({
      telegram_id: null,
      username: 'admin',
      role: 'superadmin',
      role_id: 1,
      account_id: 1,
      unlimited_traffic_policy: 'allowed',
      auth_method: 'password',
      password_is_generated: false,
      permissions: [],
    }),
    getSetupStatus: vi.fn().mockResolvedValue({ needs_setup: false }),
    getAuthMethods: vi.fn().mockResolvedValue({ telegram: true, password: true, totp_required: false }),
    telegramLogin: vi.fn(),
    passwordLogin: vi.fn(),
    register: vi.fn(),
    refreshToken: vi.fn(),
    changePassword: vi.fn(),
    logout: vi.fn(),
    listPasskeys: vi.fn().mockResolvedValue([]),
    registerPasskey: vi.fn(),
    deletePasskey: vi.fn(),
    loginPasskey: vi.fn(),
    oauthProviders: vi.fn().mockResolvedValue([]),
    oauthLinks: vi.fn().mockResolvedValue([]),
    oauthLoginUrl: vi.fn(),
    oauthLinkUrl: vi.fn(),
    oauthCallback: vi.fn(),
    deleteOauthLink: vi.fn(),
    setOauthProvider: vi.fn(),
    deleteOauthProvider: vi.fn(),
    listSessions: vi.fn().mockResolvedValue([]),
    revokeSession: vi.fn(),
    revokeOtherSessions: vi.fn(),
    setup2fa: vi.fn(),
    enable2fa: vi.fn(),
    disable2fa: vi.fn(),
    regenBackupCodes: vi.fn(),
  },
}))

// Mock automations API
vi.mock('@/api/automations', () => ({
  automationsApi: {
    listRules: vi.fn().mockResolvedValue([]),
    listLogs: vi.fn().mockResolvedValue([]),
    getTemplates: vi.fn().mockResolvedValue([]),
  },
  // Re-export types as empty
  AutomationRule: {},
  AutomationTemplate: {},
}))

// Mock notifications API
vi.mock('@/api/notifications', () => ({
  notificationsApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    unreadCount: vi.fn().mockResolvedValue({ count: 0 }),
    markRead: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
    deleteOld: vi.fn().mockResolvedValue(undefined),
    create: vi.fn().mockResolvedValue(undefined),
    listChannels: vi.fn().mockResolvedValue([]),
    createChannel: vi.fn(),
    updateChannel: vi.fn(),
    deleteChannel: vi.fn(),
    getSmtpConfig: vi.fn().mockResolvedValue({}),
    updateSmtpConfig: vi.fn(),
    testSmtp: vi.fn(),
    listAlertRules: vi.fn().mockResolvedValue([]),
    createAlertRule: vi.fn(),
    updateAlertRule: vi.fn(),
    deleteAlertRule: vi.fn(),
    toggleAlertRule: vi.fn(),
    listAlertLogs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    acknowledgeAlerts: vi.fn(),
  },
}))

// Mock mailserver API
vi.mock('@/api/mailserver', () => ({
  mailserverApi: {
    listDomains: vi.fn().mockResolvedValue([]),
    getDomain: vi.fn(),
    createDomain: vi.fn(),
    updateDomain: vi.fn(),
    deleteDomain: vi.fn(),
    checkDns: vi.fn(),
    getDnsRecords: vi.fn().mockResolvedValue([]),
    listQueue: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    retryMessage: vi.fn(),
    cancelMessage: vi.fn(),
    listInbox: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getInboxItem: vi.fn(),
    deleteInboxItem: vi.fn(),
    sendEmail: vi.fn(),
    listCredentials: vi.fn().mockResolvedValue([]),
    createCredential: vi.fn(),
    deleteCredential: vi.fn(),
  },
}))

// Mock WebSocket hook
vi.mock('@/store/useWebSocket', () => ({
  useRealtimeUpdates: vi.fn(),
}))

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
  Toaster: () => null,
}))

// Mock Leaflet CSS import
vi.mock('leaflet/dist/leaflet.css', () => ({}))

// Mock Leaflet (used by Analytics page)
vi.mock('leaflet', () => ({
  default: {
    map: vi.fn(),
    tileLayer: vi.fn(),
    marker: vi.fn(),
    Icon: { Default: { mergeOptions: vi.fn() } },
    icon: vi.fn(() => ({})),
  },
  Icon: { Default: { mergeOptions: vi.fn() } },
  icon: vi.fn(() => ({})),
}))

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div />,
  Marker: () => <div />,
  Popup: () => <div />,
  CircleMarker: () => <div />,
  useMap: vi.fn(() => ({ setView: vi.fn(), invalidateSize: vi.fn() })),
}))

// Mock Recharts (used by Dashboard and Analytics)
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Area: () => <div />,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  Cell: () => <div />,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: () => <div />,
}))

// Mock html-to-image
vi.mock('html-to-image', () => ({
  toPng: vi.fn().mockResolvedValue(''),
}))

// ── Helpers ──────────────────────────────────────────────────

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderPage(ui: React.ReactElement, { route = '/' } = {}) {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[route]}>
          {ui}
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

// ── Setup ────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()

  // Set auth state for protected pages
  useAuthStore.setState({
    user: { username: 'admin', firstName: 'Admin', authMethod: 'password' },
    accessToken: 'test-token',
    refreshToken: 'test-refresh',
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })

  // Set permissions — superadmin sees everything
  usePermissionStore.setState({
    permissions: [],
    role: 'superadmin',
    roleId: 1,
    isLoaded: true,
  })
})

// ── Page imports ─────────────────────────────────────────────
// Import pages after mocks are set up

// ── Tests ────────────────────────────────────────────────────

describe('Page smoke tests', () => {
  it('Dashboard renders without errors', async () => {
    const Dashboard = (await import('@/pages/Dashboard')).default
    const { container } = renderPage(<Dashboard />)
    expect(container).toBeTruthy()
  })

  it('Users renders without errors', async () => {
    const Users = (await import('@/pages/Users')).default
    const { container } = renderPage(<Users />)
    expect(container).toBeTruthy()
  })

  it('UserDetail renders without errors', async () => {
    const UserDetail = (await import('@/pages/UserDetail')).default
    const { container } = renderPage(
      <Routes>
        <Route path="/users/:uuid" element={<UserDetail />} />
      </Routes>,
      { route: '/users/test-uuid-123' }
    )
    expect(container).toBeTruthy()
  })

  it('Nodes renders without errors', async () => {
    const Nodes = (await import('@/pages/Nodes')).default
    const { container } = renderPage(<Nodes />)
    expect(container).toBeTruthy()
  })

  it('Fleet renders without errors', async () => {
    const Fleet = (await import('@/pages/Fleet')).default
    const { container } = renderPage(<Fleet />)
    expect(container).toBeTruthy()
  })

  it('Servers renders without errors', async () => {
    const Servers = (await import('@/pages/Servers')).default
    const { container } = renderPage(<Servers />)
    expect(container).toBeTruthy()
  })

  it('Nodes и Fleet встраиваются во вкладки без своего заголовка', async () => {
    const Nodes = (await import('@/pages/Nodes')).default
    const Fleet = (await import('@/pages/Fleet')).default
    const nodes = renderPage(<Nodes embedded />)
    expect(nodes.container.querySelector('.page-header-title')).toBeNull()
    const fleet = renderPage(<Fleet embedded tab="monitoring" />)
    expect(fleet.container.querySelector('.page-header-title')).toBeNull()
  })

  it('Хосты и сквады встраиваются во вкладки «Ресурсов» без своего заголовка', async () => {
    const { HostsPanel } = await import('@/components/hosts/HostsPanel')
    const { SquadsPanel } = await import('@/components/squads/SquadsPanel')
    const hosts = renderPage(<HostsPanel />)
    expect(hosts.container.querySelector('.page-header-title')).toBeNull()
    const squads = renderPage(<SquadsPanel />)
    expect(squads.container.querySelector('.page-header-title')).toBeNull()
  })

  it('Violations renders without errors', async () => {
    const Violations = (await import('@/pages/Violations')).default
    const { container } = renderPage(<Violations />)
    expect(container).toBeTruthy()
  })

  it('Settings renders without errors', async () => {
    const Settings = (await import('@/pages/Settings')).default
    const { container } = renderPage(<Settings />)
    expect(container).toBeTruthy()
  })

  it('Admins renders without errors', async () => {
    const Admins = (await import('@/pages/Admins')).default
    const { container } = renderPage(<Admins />)
    expect(container).toBeTruthy()
  })

  it('AuditLog renders without errors', async () => {
    const AuditLog = (await import('@/pages/AuditLog')).default
    const { container } = renderPage(<AuditLog />)
    expect(container).toBeTruthy()
  })

  it('SystemLogs renders without errors', async () => {
    const SystemLogs = (await import('@/pages/SystemLogs')).default
    const { container } = renderPage(<SystemLogs />)
    expect(container).toBeTruthy()
  })

  it('Analytics renders without errors', async () => {
    const Analytics = (await import('@/pages/Analytics')).default
    const { container } = renderPage(<Analytics />)
    expect(container).toBeTruthy()
  })

  it('Automations renders without errors', async () => {
    const Automations = (await import('@/pages/automations')).default
    const { container } = renderPage(<Automations />)
    expect(container).toBeTruthy()
  })

  it('Notifications renders without errors', async () => {
    const Notifications = (await import('@/pages/Notifications')).default
    const { container } = renderPage(<Notifications />)
    expect(container).toBeTruthy()
  })

  it('MailServer renders without errors', async () => {
    const MailServer = (await import('@/pages/MailServer')).default
    const { container } = renderPage(<MailServer />)
    expect(container).toBeTruthy()
  })

  it('Reports renders without errors', async () => {
    const Reports = (await import('@/pages/Reports')).default
    const { container } = renderPage(<Reports />)
    expect(container).toBeTruthy()
  })

  it('Resources renders without errors', async () => {
    const Resources = (await import('@/pages/Resources')).default
    const { container } = renderPage(<Resources />)
    expect(container).toBeTruthy()
  })

  it('Finance renders without errors', async () => {
    const Finance = (await import('@/pages/Finance')).default
    const { container } = renderPage(<Finance />)
    expect(container).toBeTruthy()
  })

  it('BsCheck renders without errors', async () => {
    const client = (await import('@/api/client')).default as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockImplementation((url: string) => {
      if (url === '/bscheck/status') return Promise.resolve({ data: { configured: true, account: { balance_total: 1000, tier: 'bronze' } } })
      if (url === '/bscheck/operators') return Promise.resolve({ data: { items: [{ id: 'mts', name: 'МТС', op_key: 'ufo1:mts', channel_state: 'DPI_ON', alive: true, region_label: 'Урал' }] } })
      if (url === '/bscheck/nodes') return Promise.resolve({ data: { items: [{ uuid: 'n1', name: 'Node 1', ip: '1.2.3.4', address: '100.0.0.1', agent_ip: '1.2.3.4' }] } })
      if (url === '/bscheck/summary') return Promise.resolve({ data: { items: {} } })
      return Promise.resolve({ data: { items: [], total: 0 } })
    })
    const BsCheck = (await import('@/pages/BsCheck')).default
    const { container } = renderPage(<BsCheck />)
    expect(container).toBeTruthy()
    client.get.mockResolvedValue({ data: { items: [], total: 0 } })
  })

  it('Login renders without errors', async () => {
    // Login page doesn't require auth
    useAuthStore.setState({ isAuthenticated: false, accessToken: null })
    const Login = (await import('@/pages/Login')).default
    const { container } = renderPage(<Login />)
    expect(container).toBeTruthy()
  })
})
