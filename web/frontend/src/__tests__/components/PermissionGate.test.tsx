import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { usePermissionStore } from '@/store/permissionStore'

describe('PermissionGate', () => {
  beforeEach(() => {
    usePermissionStore.setState({
      permissions: [],
      role: null,
      roleId: null,
      isLoaded: true,
    })
  })

  it('renders children when user has permission (superadmin)', () => {
    usePermissionStore.setState({ role: 'superadmin' })

    render(
      <PermissionGate resource="users" action="create">
        <button>Create User</button>
      </PermissionGate>
    )

    expect(screen.getByText('Create User')).toBeInTheDocument()
  })

  it('renders children when user has specific permission', () => {
    usePermissionStore.setState({
      role: 'operator',
      permissions: [{ resource: 'users', action: 'read' }],
    })

    render(
      <PermissionGate resource="users" action="read">
        <span>Visible content</span>
      </PermissionGate>
    )

    expect(screen.getByText('Visible content')).toBeInTheDocument()
  })

  it('hides children when user lacks permission', () => {
    usePermissionStore.setState({
      role: 'viewer',
      permissions: [{ resource: 'users', action: 'read' }],
    })

    render(
      <PermissionGate resource="users" action="delete">
        <span>Secret content</span>
      </PermissionGate>
    )

    expect(screen.queryByText('Secret content')).not.toBeInTheDocument()
  })

  it('renders fallback when user lacks permission', () => {
    usePermissionStore.setState({
      role: 'viewer',
      permissions: [],
    })

    render(
      <PermissionGate
        resource="settings"
        action="update"
        fallback={<span>No access</span>}
      >
        <span>Settings form</span>
      </PermissionGate>
    )

    expect(screen.queryByText('Settings form')).not.toBeInTheDocument()
    expect(screen.getByText('No access')).toBeInTheDocument()
  })
})

describe('useHasPermission', () => {
  function TestComponent({ resource, action }: { resource: string; action: string }) {
    const has = useHasPermission(resource, action)
    return <span>{has ? 'yes' : 'no'}</span>
  }

  beforeEach(() => {
    usePermissionStore.setState({
      permissions: [{ resource: 'users', action: 'read' }],
      role: 'operator',
      roleId: null,
      isLoaded: true,
    })
  })

  it('returns true for granted permission', () => {
    render(<TestComponent resource="users" action="read" />)
    expect(screen.getByText('yes')).toBeInTheDocument()
  })

  it('returns false for denied permission', () => {
    render(<TestComponent resource="users" action="delete" />)
    expect(screen.getByText('no')).toBeInTheDocument()
  })
})
