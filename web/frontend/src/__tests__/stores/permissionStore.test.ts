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
    it('grants all permissions to superadmin', () => {
      usePermissionStore.setState({ role: 'superadmin', permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'create')).toBe(true)
      expect(hasPermission('nodes', 'delete')).toBe(true)
      expect(hasPermission('anything', 'everything')).toBe(true)
    })

    it('grants all permissions to legacy admin role', () => {
      usePermissionStore.setState({ role: 'admin', permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'create')).toBe(true)
    })

    it('grants all permissions when role is null (legacy)', () => {
      usePermissionStore.setState({ role: null, permissions: [] })
      const { hasPermission } = usePermissionStore.getState()
      expect(hasPermission('users', 'read')).toBe(true)
    })

    it('checks specific permissions for non-superadmin roles', () => {
      usePermissionStore.setState({
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
        auth_method: 'password',
        password_is_generated: false,
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
    })

    it('falls back to superadmin on API failure', async () => {
      const { authApi } = await import('@/api/auth')
      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Network error'))

      await usePermissionStore.getState().loadPermissions()

      const state = usePermissionStore.getState()
      expect(state.role).toBe('superadmin')
      expect(state.isLoaded).toBe(true)
    })
  })

  describe('clearPermissions', () => {
    it('resets state', () => {
      usePermissionStore.setState({
        permissions: [{ resource: 'users', action: 'read' }],
        role: 'manager',
        roleId: 2,
        isLoaded: true,
      })

      usePermissionStore.getState().clearPermissions()

      const state = usePermissionStore.getState()
      expect(state.permissions).toEqual([])
      expect(state.role).toBeNull()
      expect(state.roleId).toBeNull()
      expect(state.isLoaded).toBe(false)
    })
  })
})
