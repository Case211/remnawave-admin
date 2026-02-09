import { usePermissionStore } from '../store/permissionStore'

interface PermissionGateProps {
  resource: string
  action: string
  children: React.ReactNode
  /** What to render when permission is denied (default: nothing) */
  fallback?: React.ReactNode
}

/**
 * Conditionally renders children only if the current admin has the required permission.
 *
 * Usage:
 *   <PermissionGate resource="users" action="create">
 *     <Button>Create User</Button>
 *   </PermissionGate>
 */
export function PermissionGate({ resource, action, children, fallback = null }: PermissionGateProps) {
  const hasPermission = usePermissionStore((s) => s.hasPermission)

  if (!hasPermission(resource, action)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}

/**
 * Hook variant for more complex permission checks.
 */
export function useHasPermission(resource: string, action: string): boolean {
  return usePermissionStore((s) => s.hasPermission)(resource, action)
}
