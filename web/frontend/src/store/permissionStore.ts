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
  isLoaded: boolean

  // Actions
  loadPermissions: () => Promise<void>
  hasPermission: (resource: string, action: string) => boolean
  clearPermissions: () => void
}

export const usePermissionStore = create<PermissionState>((set, get) => ({
  permissions: [],
  role: null,
  roleId: null,
  isLoaded: false,

  loadPermissions: async () => {
    try {
      const info: AdminInfo = await authApi.getMe()
      set({
        permissions: info.permissions || [],
        role: info.role,
        roleId: info.role_id ?? null,
        isLoaded: true,
      })
    } catch {
      // If the endpoint fails (e.g. old backend), grant full access
      set({
        permissions: [],
        role: 'superadmin',
        roleId: null,
        isLoaded: true,
      })
    }
  },

  hasPermission: (resource: string, action: string) => {
    const { role, permissions } = get()
    // Superadmin bypass
    if (role === 'superadmin') return true
    // Legacy admins without role info — treat as superadmin
    if (!role || role === 'admin') return true
    return permissions.some((p) => p.resource === resource && p.action === action)
  },

  clearPermissions: () => {
    set({ permissions: [], role: null, roleId: null, isLoaded: false })
  },
}))
