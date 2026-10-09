import { create } from 'zustand'
import { authApi, AdminInfo } from '../api/auth'

interface Permission {
  resource: string
  action: string
}

interface PermissionState {
  permissions: Permission[]
  role: string | null
  roleId: number | null
  accountId: number | null
  // Quota limits (null = unlimited)
  maxUsers: number | null
  maxTrafficGb: number | null
  maxNodes: number | null
  maxHosts: number | null
  // Quota counters
  usersCreated: number
  trafficUsedBytes: number
  nodesCreated: number
  hostsCreated: number
  unlimitedTrafficPolicy: string
  unrestrictedUserAccess: boolean
  userScopeRestricted: boolean
  isLoaded: boolean
  mustChangePassword: boolean
  loadError: string | null

  // Actions
  loadPermissions: () => Promise<void>
  refreshAdmin: () => Promise<void>
  hasPermission: (resource: string, action: string) => boolean
  clearPermissions: () => void
  setMustChangePassword: (v: boolean) => void
}

export const usePermissionStore = create<PermissionState>((set, get) => ({
  permissions: [],
  role: null,
  roleId: null,
  accountId: null,
  maxUsers: null,
  maxTrafficGb: null,
  maxNodes: null,
  maxHosts: null,
  usersCreated: 0,
  trafficUsedBytes: 0,
  nodesCreated: 0,
  hostsCreated: 0,
  unlimitedTrafficPolicy: 'allowed',
  unrestrictedUserAccess: false,
  userScopeRestricted: false,
  isLoaded: false,
  mustChangePassword: false,
  loadError: null,

  loadPermissions: async () => {
    set({ loadError: null })
    try {
      const info: AdminInfo = await authApi.getMe()
      set({
        permissions: info.permissions || [],
        role: info.role,
        roleId: info.role_id ?? null,
        accountId: info.account_id ?? null,
        maxUsers: info.max_users ?? null,
        maxTrafficGb: info.max_traffic_gb ?? null,
        maxNodes: info.max_nodes ?? null,
        maxHosts: info.max_hosts ?? null,
        usersCreated: info.users_created ?? 0,
        trafficUsedBytes: info.traffic_used_bytes ?? 0,
        nodesCreated: info.nodes_created ?? 0,
        hostsCreated: info.hosts_created ?? 0,
        unlimitedTrafficPolicy: info.unlimited_traffic_policy || 'allowed',
        unrestrictedUserAccess: info.unrestricted_user_access === true,
        userScopeRestricted: info.user_scope_restricted === true,
        isLoaded: true,
        mustChangePassword: info.password_is_generated === true,
        loadError: null,
      })
    } catch (error) {
      // On failure, keep isLoaded=false so ProtectedRoute keeps showing
      // the loading spinner and can retry. Don't set role=null with
      // isLoaded=true, which would silently strand the user with no
      // permissions and require a page reload to recover.
      const message = error instanceof Error ? error.message : 'Failed to load permissions'
      set({ isLoaded: false, loadError: message })
    }
  },

  refreshAdmin: async () => {
    try {
      const info: AdminInfo = await authApi.getMe()
      set({
        maxUsers: info.max_users ?? null,
        maxTrafficGb: info.max_traffic_gb ?? null,
        maxNodes: info.max_nodes ?? null,
        maxHosts: info.max_hosts ?? null,
        usersCreated: info.users_created ?? 0,
        trafficUsedBytes: info.traffic_used_bytes ?? 0,
        nodesCreated: info.nodes_created ?? 0,
        hostsCreated: info.hosts_created ?? 0,
        unlimitedTrafficPolicy: info.unlimited_traffic_policy || 'allowed',
        unrestrictedUserAccess: info.unrestricted_user_access === true,
        userScopeRestricted: info.user_scope_restricted === true,
      })
    } catch {
      // Silent failure: keep current values
    }
  },

  hasPermission: (resource: string, action: string) => {
    const { isLoaded, role, permissions, userScopeRestricted } = get()
    // Before permissions are loaded, deny everything
    if (!isLoaded) return false
    // Superadmin bypass
    if (role === 'superadmin') return true
    // Legacy admins have no role assigned — treat as full access
    // (mirrors the backend fallback for old accounts predating RBAC).
    if (!role) return true
    // Клиентов Bedolaga под скоуп юзеров не отфильтровать — админу, который
    // видит не всех, разделы Bedolaga закрыты (так же решает бэкенд)
    if (userScopeRestricted && resource.startsWith('bedolaga')) return false
    return permissions.some((p) => p.resource === resource && p.action === action)
  },

  clearPermissions: () => {
    set({
      permissions: [],
      role: null,
      roleId: null,
      accountId: null,
      maxUsers: null,
      maxTrafficGb: null,
      maxNodes: null,
      maxHosts: null,
      usersCreated: 0,
      trafficUsedBytes: 0,
      nodesCreated: 0,
      hostsCreated: 0,
      unlimitedTrafficPolicy: 'allowed',
      unrestrictedUserAccess: false,
      userScopeRestricted: false,
      isLoaded: false,
      mustChangePassword: false,
      loadError: null,
    })
  },

  setMustChangePassword: (v: boolean) => {
    set({ mustChangePassword: v })
  },
}))
