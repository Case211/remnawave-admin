import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Pencil,
  Trash2,
  Shield,
  ShieldCheck,
  Users,
  RefreshCw,
  Check,
  X,
  Lock,
} from 'lucide-react'
import { rolesApi, Role, RoleCreate, RoleUpdate, Permission, AvailableResources } from '../api/admins'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { PermissionGate } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'

// ── Resource labels ────────────────────────────────────────────

const RESOURCE_LABELS: Record<string, string> = {
  users: 'Пользователи',
  nodes: 'Ноды',
  hosts: 'Хосты',
  violations: 'Нарушения',
  settings: 'Настройки',
  analytics: 'Аналитика',
  admins: 'Администраторы',
  roles: 'Роли',
  audit: 'Аудит',
}

const ACTION_LABELS: Record<string, string> = {
  view: 'Просмотр',
  create: 'Создание',
  edit: 'Редактирование',
  delete: 'Удаление',
  resolve: 'Разрешение',
}

// ── Permission Matrix Component ────────────────────────────────

function PermissionMatrix({
  resources,
  selected,
  onChange,
  disabled,
}: {
  resources: AvailableResources
  selected: Permission[]
  onChange: (perms: Permission[]) => void
  disabled?: boolean
}) {
  const isChecked = (resource: string, action: string) =>
    selected.some((p) => p.resource === resource && p.action === action)

  const toggle = (resource: string, action: string) => {
    if (disabled) return
    if (isChecked(resource, action)) {
      onChange(selected.filter((p) => !(p.resource === resource && p.action === action)))
    } else {
      onChange([...selected, { resource, action }])
    }
  }

  const toggleAllResource = (resource: string) => {
    if (disabled) return
    const actions = resources[resource] || []
    const allChecked = actions.every((a) => isChecked(resource, a))
    if (allChecked) {
      onChange(selected.filter((p) => p.resource !== resource))
    } else {
      const others = selected.filter((p) => p.resource !== resource)
      onChange([...others, ...actions.map((a) => ({ resource, action: a }))])
    }
  }

  const toggleAllAction = (action: string) => {
    if (disabled) return
    const resourcesWithAction = Object.entries(resources)
      .filter(([, actions]) => actions.includes(action))
      .map(([r]) => r)
    const allChecked = resourcesWithAction.every((r) => isChecked(r, action))
    if (allChecked) {
      onChange(selected.filter((p) => p.action !== action))
    } else {
      const others = selected.filter((p) => p.action !== action)
      const added = resourcesWithAction.map((r) => ({ resource: r, action }))
      onChange([...others, ...added])
    }
  }

  // Collect all unique actions
  const allActions = Array.from(new Set(Object.values(resources).flat()))

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="text-left py-2 px-3 text-dark-200 font-medium border-b border-dark-400/20">
              Ресурс
            </th>
            {allActions.map((action) => (
              <th
                key={action}
                className="text-center py-2 px-2 text-dark-200 font-medium border-b border-dark-400/20 cursor-pointer hover:text-white transition-colors"
                onClick={() => toggleAllAction(action)}
              >
                {ACTION_LABELS[action] || action}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(resources).map(([resource, actions]) => (
            <tr key={resource} className="border-b border-dark-400/10 hover:bg-dark-700/30">
              <td
                className="py-2.5 px-3 text-dark-50 font-medium cursor-pointer hover:text-primary-400 transition-colors"
                onClick={() => toggleAllResource(resource)}
              >
                {RESOURCE_LABELS[resource] || resource}
              </td>
              {allActions.map((action) => {
                const available = actions.includes(action)
                const checked = isChecked(resource, action)
                return (
                  <td key={action} className="text-center py-2.5 px-2">
                    {available ? (
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => toggle(resource, action)}
                        className={cn(
                          "w-6 h-6 rounded border transition-all mx-auto flex items-center justify-center",
                          checked
                            ? "bg-primary-500/20 border-primary-500 text-primary-400"
                            : "border-dark-400/30 hover:border-dark-300/50",
                          disabled && "opacity-50 cursor-not-allowed"
                        )}
                      >
                        {checked && <Check className="w-3.5 h-3.5" />}
                      </button>
                    ) : (
                      <span className="text-dark-500 text-xs">\u2014</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Role Form Dialog ───────────────────────────────────────────

function RoleFormDialog({
  open,
  onClose,
  onSave,
  isPending,
  error,
  resources,
  editingRole,
}: {
  open: boolean
  onClose: () => void
  onSave: (data: RoleCreate | RoleUpdate) => void
  isPending: boolean
  error: string
  resources: AvailableResources
  editingRole: Role | null
}) {
  const [name, setName] = useState(editingRole?.name || '')
  const [displayName, setDisplayName] = useState(editingRole?.display_name || '')
  const [description, setDescription] = useState(editingRole?.description || '')
  const [permissions, setPermissions] = useState<Permission[]>(editingRole?.permissions || [])

  const isSystem = editingRole?.is_system || false

  const handleSubmit = () => {
    if (editingRole) {
      const update: RoleUpdate = {
        display_name: displayName,
        description: description || null,
        permissions,
      }
      onSave(update)
    } else {
      const create: RoleCreate = {
        name: name.trim().toLowerCase().replace(/\s+/g, '_'),
        display_name: displayName.trim(),
        description: description || null,
        permissions,
      }
      onSave(create)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editingRole ? 'Редактирование роли' : 'Создание роли'}
            {isSystem && (
              <Badge variant="secondary" className="ml-2">
                <Lock className="w-3 h-3 mr-1" /> Системная
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            {editingRole
              ? 'Настройте отображаемое имя и набор прав для этой роли'
              : 'Задайте имя и набор прав для новой роли'}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          {!editingRole && (
            <div>
              <Label>Системное имя *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="custom_role"
                className="mt-1.5"
                disabled={isSystem}
              />
              <p className="text-xs text-dark-300 mt-1">Латиница, нижнее подчёркивание. Нельзя изменить после создания.</p>
            </div>
          )}

          <div>
            <Label>Отображаемое имя *</Label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Custom Role"
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>Описание</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание роли..."
              className="mt-1.5"
            />
          </div>

          <div>
            <Label className="mb-3 block">Матрица прав</Label>
            <Card>
              <CardContent className="p-3">
                <PermissionMatrix
                  resources={resources}
                  selected={permissions}
                  onChange={setPermissions}
                />
              </CardContent>
            </Card>
            <p className="text-xs text-dark-300 mt-2">
              Выбрано: {permissions.length} прав.
              Клик на заголовок столбца/строки переключает все права в группе.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>Отмена</Button>
          <Button
            onClick={handleSubmit}
            disabled={isPending || !displayName || (!editingRole && !name)}
          >
            {isPending ? 'Сохранение...' : editingRole ? 'Сохранить' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main component ─────────────────────────────────────────────

export default function Roles() {
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [formError, setFormError] = useState('')

  const { data: roles = [], isLoading, refetch } = useQuery({
    queryKey: ['roles'],
    queryFn: rolesApi.list,
  })

  const { data: resources = {} } = useQuery({
    queryKey: ['roles-resources'],
    queryFn: rolesApi.getResources,
  })

  const createMutation = useMutation({
    mutationFn: (data: RoleCreate) => rolesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setShowDialog(false)
      setFormError('')
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RoleUpdate }) => rolesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      setShowDialog(false)
      setEditingRole(null)
      setFormError('')
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Ошибка обновления')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => rolesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['roles'] })
    },
  })

  const handleOpenCreate = () => {
    setEditingRole(null)
    setFormError('')
    setShowDialog(true)
  }

  const handleOpenEdit = (role: Role) => {
    setEditingRole(role)
    setFormError('')
    setShowDialog(true)
  }

  const handleSave = (data: RoleCreate | RoleUpdate) => {
    if (editingRole) {
      updateMutation.mutate({ id: editingRole.id, data: data as RoleUpdate })
    } else {
      createMutation.mutate(data as RoleCreate)
    }
  }

  const roleColorMap: Record<string, string> = {
    superadmin: 'border-l-red-500',
    manager: 'border-l-blue-500',
    operator: 'border-l-yellow-500',
    viewer: 'border-l-gray-500',
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Роли</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">
            Управление ролями и правами доступа
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn("w-5 h-5", isLoading && "animate-spin")} />
          </Button>
          <PermissionGate resource="roles" action="create">
            <Button onClick={handleOpenCreate}>
              <Plus className="w-4 h-4 mr-2" />
              <span className="hidden sm:inline">Создать роль</span>
              <span className="sm:hidden">Создать</span>
            </Button>
          </PermissionGate>
        </div>
      </div>

      {/* Role cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="h-5 w-32 mb-2" />
                <Skeleton className="h-4 w-48 mb-4" />
                <Skeleton className="h-3 w-20" />
              </CardContent>
            </Card>
          ))
        ) : roles.length === 0 ? (
          <Card className="col-span-full">
            <CardContent className="p-8 text-center text-muted-foreground">
              Нет ролей
            </CardContent>
          </Card>
        ) : (
          roles.map((role) => (
            <Card
              key={role.id}
              className={cn(
                "border-l-[3px] transition-all hover:border-dark-300/50",
                roleColorMap[role.name] || 'border-l-purple-500'
              )}
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Shield className={cn(
                      "w-5 h-5",
                      role.name === 'superadmin' ? 'text-red-400' :
                      role.name === 'manager' ? 'text-blue-400' :
                      role.name === 'operator' ? 'text-yellow-400' :
                      role.name === 'viewer' ? 'text-gray-400' :
                      'text-purple-400'
                    )} />
                    <h3 className="text-white font-semibold">{role.display_name}</h3>
                  </div>
                  <div className="flex items-center gap-1">
                    {role.is_system && (
                      <Badge variant="secondary" className="text-[10px]">
                        <Lock className="w-2.5 h-2.5 mr-0.5" /> Системная
                      </Badge>
                    )}
                  </div>
                </div>

                {role.description && (
                  <p className="text-sm text-dark-200 mb-3">{role.description}</p>
                )}

                <div className="flex items-center gap-4 text-xs text-dark-300 mb-4">
                  <span className="flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    {role.permissions_count ?? role.permissions?.length ?? 0} прав
                  </span>
                  <span className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5" />
                    {role.admins_count ?? 0} админов
                  </span>
                </div>

                {/* Permission summary */}
                <div className="flex flex-wrap gap-1 mb-4">
                  {role.permissions?.slice(0, 8).map((p) => (
                    <span
                      key={`${p.resource}:${p.action}`}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-dark-600/50 text-dark-200"
                    >
                      {p.resource}:{p.action}
                    </span>
                  ))}
                  {(role.permissions?.length || 0) > 8 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-600/50 text-dark-300">
                      +{(role.permissions?.length || 0) - 8}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-3 border-t border-dark-400/20">
                  <PermissionGate resource="roles" action="edit">
                    <Button variant="secondary" size="sm" onClick={() => handleOpenEdit(role)}>
                      <Pencil className="w-3.5 h-3.5 mr-1.5" /> Редактировать
                    </Button>
                  </PermissionGate>
                  {!role.is_system && (
                    <PermissionGate resource="roles" action="delete">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => { if (confirm('Удалить роль?')) deleteMutation.mutate(role.id) }}
                        className="text-red-400 hover:text-red-300"
                      >
                        <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Удалить
                      </Button>
                    </PermissionGate>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Create/Edit Dialog */}
      {showDialog && (
        <RoleFormDialog
          open={showDialog}
          onClose={() => { setShowDialog(false); setEditingRole(null); setFormError('') }}
          onSave={handleSave}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={formError}
          resources={resources}
          editingRole={editingRole}
        />
      )}
    </div>
  )
}
