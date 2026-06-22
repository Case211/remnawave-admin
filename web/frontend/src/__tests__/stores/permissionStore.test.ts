import { describe, it, expect, beforeEach, vi } from 'vitest'
import { usePermissionStore } from '@/store/permissionStore'

// Mock the auth API
vi.mock('@/api/auth', () => ({
  authApi: {
    getMe: vi.fn(),
  },
}))

describe('usePermissionStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    usePermissionStore.setState({
      permissions: [],
      role: null,
      roleId: null,
      isLoaded: false,
    })
  })

  describe('hasPermission', () => {
    it('denies all before permissions are loaded', () => {
      usePermissionStore.setState({ isLoaded: false, role: null, permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'read')).toBe(false)
      expect(hasPermission('anything', 'everything')).toBe(false)
    })

    it('grants all permissions to superadmin', () => {
      usePermissionStore.setState({ isLoaded: true, role: 'superadmin', permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'create')).toBe(true)
      expect(hasPermission('nodes', 'delete')).toBe(true)
      expect(hasPermission('anything', 'everything')).toBe(true)
    })

    it('treats the admin role as RBAC-scoped (no implicit full access)', () => {
      // Since admin-scoping (PR #252) only superadmin and the legacy null role
      // bypass RBAC. A plain 'admin' role is checked against its explicit
      // permission list rather than being granted everything.
      usePermissionStore.setState({
        isLoaded: true,
        role: 'admin',
        permissions: [{ resource: 'users', action: 'create' }],
      })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'create')).toBe(true)
      expect(hasPermission('nodes', 'delete')).toBe(false)
    })

    it('grants all permissions when role is null after load (legacy)', () => {
      usePermissionStore.setState({ isLoaded: true, role: null, permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'read')).toBe(true)
    })

    it('checks specific permissions for non-superadmin roles', () => {
      usePermissionStore.setState({
        isLoaded: true,
        role: 'operator',
        permissions: [
          { resource: 'users', action: 'read' },
          { resource: 'users', action: 'update' },
          { resource: 'nodes', action: 'read' },
        ],
      })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'read')).toBe(true)
      expect(hasPermission('users', 'update')).toBe(true)
      expect(hasPermission('users', 'delete')).toBe(false)
      expect(hasPermission('nodes', 'read')).toBe(true)
      expect(hasPermission('nodes', 'delete')).toBe(false)
      expect(hasPermission('settings', 'read')).toBe(false)
    })

    it('denies permissions not in the list for viewer role', () => {
      usePermissionStore.setState({
        isLoaded: true,
        role: 'viewer',
        permissions: [{ resource: 'users', action: 'read' }],
      })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'read')).toBe(true)
      expect(hasPermission('users', 'create')).toBe(false)
    })
  })

  describe('loadPermissions', () => {
    it('loads permissions from API', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.getMe).mockResolvedValue({
        telegram_id: null,
        username: 'test',
        role: 'manager',
        role_id: 2,
        account_id: 5,
        max_users: 10,
        max_traffic_gb: 50,
        max_nodes: 5,
        max_hosts: 3,
        users_created: 7,
        traffic_used_bytes: 0,
        nodes_created: 2,
        hosts_created: 1,
        unlimited_traffic_policy: 'allowed',
        auth_method: 'password',
        password_is_generated: false,
        unrestricted_user_access: false,
        permissions: [
          { resource: 'users', action: 'read' },
          { resource: 'users', action: 'create' },
        ],
      })

      await usePermissionStore.getState().loadPermissions()

      const state = usePermissionStore.getState()
      expect(state.role).toBe('manager')
      expect(state.roleId).toBe(2)
      expect(state.isLoaded).toBe(true)
      expect(state.permissions).toHaveLength(2)
      // Quota fields are hydrated too
      expect(state.maxUsers).toBe(10)
      expect(state.maxTrafficGb).toBe(50)
      expect(state.usersCreated).toBe(7)
      expect(state.trafficUsedBytes).toBe(0)
    })

    it('keeps isLoaded=false on API failure so the app can retry', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Network error'))

      await usePermissionStore.getState().loadPermissions()

      const state = usePermissionStore.getState()
      // Don't strand the user with empty permissions — keep isLoaded=false
      // so ProtectedRoute can show its loading state and retry.
      expect(state.isLoaded).toBe(false)
      expect(state.loadError).toBe('Network error')
      expect(state.role).toBeNull()
    })

    it('clears loadError on a successful retry', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.getMe)
        .mockRejectedValueOnce(new Error('Transient failure'))
        .mockResolvedValueOnce({
          telegram_id: null,
          username: 'test',
          role: 'manager',
          role_id: 2,
          account_id: 5,
          max_users: null,
          max_traffic_gb: null,
          max_nodes: null,
          max_hosts: null,
          users_created: 0,
          traffic_used_bytes: 0,
          nodes_created: 0,
          hosts_created: 0,
          unlimited_traffic_policy: 'allowed',
          auth_method: 'password',
          password_is_generated: false,
          unrestricted_user_access: false,
          permissions: [{ resource: 'users', action: 'read' }],
        })

      await usePermissionStore.getState().loadPermissions()
      expect(usePermissionStore.getState().loadError).toBe('Transient failure')
      expect(usePermissionStore.getState().isLoaded).toBe(false)

      await usePermissionStore.getState().loadPermissions()
      const state = usePermissionStore.getState()
      expect(state.loadError).toBeNull()
      expect(state.isLoaded).toBe(true)
      expect(state.role).toBe('manager')
    })
  })

  describe('clearPermissions', () => {
    it('resets state', () => {
      usePermissionStore.setState({
        permissions: [{ resource: 'users', action: 'read' }],
        role: 'manager',
        roleId: 2,
        isLoaded: true,
        loadError: 'stale error',
      })

      usePermissionStore.getState().clearPermissions()

      const state = usePermissionStore.getState()
      expect(state.permissions).toEqual([])
      expect(state.role).toBeNull()
      expect(state.roleId).toBeNull()
      expect(state.isLoaded).toBe(false)
      expect(state.loadError).toBeNull()
    })
  })
})
