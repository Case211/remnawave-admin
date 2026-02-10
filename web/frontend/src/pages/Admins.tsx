import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus,
  Pencil,
  Trash2,
  MoreVertical,
  Shield,
  ShieldCheck,
  UserCheck,
  UserX,
  RefreshCw,
  Check,
  Lock,
  Users as UsersIcon,
  History,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import {
  adminsApi, rolesApi,
  AdminAccount, AdminAccountCreate, AdminAccountUpdate,
  Role, RoleCreate, RoleUpdate, Permission, AvailableResources,
  AuditLogEntry,
} from '../api/admins'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { cn } from '@/lib/utils'

// ── Helpers ────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

const RESOURCE_LABELS: Record<string, string> = {
  users: '\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438',
  nodes: '\u041d\u043e\u0434\u044b',
  hosts: '\u0425\u043e\u0441\u0442\u044b',
  violations: '\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0438\u044f',
  settings: '\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438',
  analytics: '\u0410\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0430',
  admins: '\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u044b',
  roles: '\u0420\u043e\u043b\u0438',
  audit: '\u0410\u0443\u0434\u0438\u0442',
}

const ACTION_LABELS: Record<string, string> = {
  view: '\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440',
  create: '\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435',
  edit: '\u0420\u0435\u0434\u0430\u043a\u0442.',
  delete: '\u0423\u0434\u0430\u043b\u0435\u043d\u0438\u0435',
  resolve: '\u0420\u0430\u0437\u0440\u0435\u0448.',
}

function RoleBadge({ name, displayName }: { name: string | null; displayName: string | null }) {
  const label = displayName || name || 'No role'
  const colorMap: Record<string, string> = {
    superadmin: 'bg-red-500/15 text-red-400 border-red-500/20',
    manager: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    operator: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
    viewer: 'bg-gray-500/15 text-gray-400 border-gray-500/20',
  }
  const cls = colorMap[name || ''] || 'bg-purple-500/15 text-purple-400 border-purple-500/20'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${cls}`}>
      <Shield className="w-3 h-3" />
      {label}
    </span>
  )
}

function QuotaBar({ used, limit, label }: { used: number; limit: number | null; label: string }) {
  const isUnlimited = limit === null || limit === undefined
  const percent = isUnlimited ? 0 : Math.min(100, Math.round((used / limit) * 100))
  const barColor = percent >= 90 ? 'bg-red-500' : percent >= 70 ? 'bg-yellow-500' : 'bg-primary-500'

  return (
    <div className="space-y-1">
      {label && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-dark-300">{label}</span>
          <span className="text-dark-100">
            {used} / {isUnlimited ? '\u221e' : limit}
          </span>
        </div>
      )}
      {!label && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-dark-100">
            {used} / {isUnlimited ? '\u221e' : limit}
          </span>
        </div>
      )}
      <div className="h-1.5 bg-dark-600 rounded-full overflow-hidden">
        {!isUnlimited && percent > 0 && (
          <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${percent}%` }} />
        )}
      </div>
    </div>
  )
}

// ── Permission Matrix ──────────────────────────────────────────

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

  const allActions = Array.from(new Set(Object.values(resources).flat()))

  return (
    <div className="overflow-x-auto -mx-3">
      <table className="w-full border-collapse text-sm" style={{ minWidth: '500px' }}>
        <thead>
          <tr>
            <th className="text-left py-2 px-3 text-dark-200 font-medium border-b border-dark-400/20 sticky left-0 bg-dark-800 z-10 min-w-[120px]">
              Ресурс
            </th>
            {allActions.map((action) => (
              <th
                key={action}
                className="text-center py-2 px-1.5 text-dark-200 font-medium border-b border-dark-400/20 cursor-pointer hover:text-white transition-colors min-w-[60px]"
                onClick={() => toggleAllAction(action)}
              >
                <span className="text-xs">{ACTION_LABELS[action] || action}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(resources).map(([resource, actions]) => (
            <tr key={resource} className="border-b border-dark-400/10 hover:bg-dark-700/30">
              <td
                className="py-2 px-3 text-dark-50 font-medium cursor-pointer hover:text-primary-400 transition-colors sticky left-0 bg-dark-800 z-10 text-xs"
                onClick={() => toggleAllResource(resource)}
              >
                {RESOURCE_LABELS[resource] || resource}
              </td>
              {allActions.map((action) => {
                const available = actions.includes(action)
                const checked = isChecked(resource, action)
                return (
                  <td key={action} className="text-center py-2 px-1.5">
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
                      <span className="text-dark-600">{'\u2014'}</span>
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

// ── Admin Form Dialog ──────────────────────────────────────────

interface AdminFormData {
  username: string
  telegram_id: string
  role_id: string
  password: string
  max_users: string
  max_traffic_gb: string
  max_nodes: string
  max_hosts: string
}

const emptyForm: AdminFormData = {
  username: '',
  telegram_id: '',
  role_id: '',
  password: '',
  max_users: '',
  max_traffic_gb: '',
  max_nodes: '',
  max_hosts: '',
}

function AdminFormDialog({
  open,
  onClose,
  onSave,
  isPending,
  error,
  roles,
  editingAdmin,
}: {
  open: boolean
  onClose: () => void
  onSave: (data: AdminAccountCreate | AdminAccountUpdate) => void
  isPending: boolean
  error: string
  roles: Role[]
  editingAdmin: AdminAccount | null
}) {
  const [form, setForm] = useState<AdminFormData>(() => {
    if (editingAdmin) {
      return {
        username: editingAdmin.username,
        telegram_id: editingAdmin.telegram_id?.toString() || '',
        role_id: editingAdmin.role_id?.toString() || '',
        password: '',
        max_users: editingAdmin.max_users?.toString() || '',
        max_traffic_gb: editingAdmin.max_traffic_gb?.toString() || '',
        max_nodes: editingAdmin.max_nodes?.toString() || '',
        max_hosts: editingAdmin.max_hosts?.toString() || '',
      }
    }
    return { ...emptyForm }
  })

  const handleSubmit = () => {
    if (editingAdmin) {
      const update: AdminAccountUpdate = {}
      if (form.username && form.username !== editingAdmin.username) update.username = form.username
      const tgId = form.telegram_id ? parseInt(form.telegram_id) : null
      if (tgId !== editingAdmin.telegram_id) update.telegram_id = tgId
      const roleId = form.role_id ? parseInt(form.role_id) : undefined
      if (roleId && roleId !== editingAdmin.role_id) update.role_id = roleId
      if (form.password) update.password = form.password
      const mu = form.max_users ? parseInt(form.max_users) : null
      if (mu !== editingAdmin.max_users) update.max_users = mu
      const mt = form.max_traffic_gb ? parseInt(form.max_traffic_gb) : null
      if (mt !== editingAdmin.max_traffic_gb) update.max_traffic_gb = mt
      const mn = form.max_nodes ? parseInt(form.max_nodes) : null
      if (mn !== editingAdmin.max_nodes) update.max_nodes = mn
      const mh = form.max_hosts ? parseInt(form.max_hosts) : null
      if (mh !== editingAdmin.max_hosts) update.max_hosts = mh
      onSave(update)
    } else {
      const create: AdminAccountCreate = {
        username: form.username.trim(),
        role_id: parseInt(form.role_id),
      }
      if (form.telegram_id) create.telegram_id = parseInt(form.telegram_id)
      if (form.password) create.password = form.password
      if (form.max_users) create.max_users = parseInt(form.max_users)
      if (form.max_traffic_gb) create.max_traffic_gb = parseInt(form.max_traffic_gb)
      if (form.max_nodes) create.max_nodes = parseInt(form.max_nodes)
      if (form.max_hosts) create.max_hosts = parseInt(form.max_hosts)
      onSave(create)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editingAdmin ? '\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430' : '\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430'}</DialogTitle>
          <DialogDescription>
            {editingAdmin ? '\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430' : '\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u043d\u043e\u0432\u043e\u0433\u043e \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430'}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label>{'Имя пользователя *'}</Label>
            <Input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              placeholder="admin_username"
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>Telegram ID</Label>
            <Input
              type="number"
              value={form.telegram_id}
              onChange={(e) => setForm({ ...form, telegram_id: e.target.value })}
              placeholder="123456789"
              className="mt-1.5"
            />
            <p className="text-xs text-dark-300 mt-1">{'Для входа через Telegram Login Widget'}</p>
          </div>

          <div>
            <Label>{'Роль *'}</Label>
            <select
              value={form.role_id}
              onChange={(e) => setForm({ ...form, role_id: e.target.value })}
              className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1.5"
            >
              <option value="">{'Выберите роль'}</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>{r.display_name}</option>
              ))}
            </select>
          </div>

          <div>
            <Label>{editingAdmin ? 'Новый пароль' : 'Пароль'}</Label>
            <Input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder={editingAdmin ? 'Оставьте пустым, чтобы не менять' : 'Минимум 8 символов'}
              className="mt-1.5"
            />
          </div>

          <div className="pt-2 border-t border-dark-400/20">
            <p className="text-sm font-medium text-dark-100 mb-3">{'Лимиты (пусто = безлимитно)'}</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">{'Макс. пользователей'}</Label>
                <Input type="number" min="0" value={form.max_users}
                  onChange={(e) => setForm({ ...form, max_users: e.target.value })}
                  placeholder={'\u221e'} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs">{'Макс. трафик (GB)'}</Label>
                <Input type="number" min="0" value={form.max_traffic_gb}
                  onChange={(e) => setForm({ ...form, max_traffic_gb: e.target.value })}
                  placeholder={'\u221e'} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs">{'Макс. нод'}</Label>
                <Input type="number" min="0" value={form.max_nodes}
                  onChange={(e) => setForm({ ...form, max_nodes: e.target.value })}
                  placeholder={'\u221e'} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs">{'Макс. хостов'}</Label>
                <Input type="number" min="0" value={form.max_hosts}
                  onChange={(e) => setForm({ ...form, max_hosts: e.target.value })}
                  placeholder={'\u221e'} className="mt-1" />
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>{'Отмена'}</Button>
          <Button onClick={handleSubmit} disabled={isPending || !form.username || !form.role_id}>
            {isPending ? 'Сохранение...' : editingAdmin ? 'Сохранить' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
      onSave({ display_name: displayName, description: description || null, permissions } as RoleUpdate)
    } else {
      onSave({
        name: name.trim().toLowerCase().replace(/\s+/g, '_'),
        display_name: displayName.trim(),
        description: description || null,
        permissions,
      } as RoleCreate)
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
                <Lock className="w-3 h-3 mr-1" /> {'Системная'}
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
              <Label>{'Системное имя *'}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)}
                placeholder="custom_role" className="mt-1.5" disabled={isSystem} />
              <p className="text-xs text-dark-300 mt-1">{'Латиница, нижнее подчёркивание. Нельзя изменить после создания.'}</p>
            </div>
          )}
          <div>
            <Label>{'Отображаемое имя *'}</Label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Custom Role" className="mt-1.5" />
          </div>
          <div>
            <Label>{'Описание'}</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание роли..." className="mt-1.5" />
          </div>
          <div>
            <Label className="mb-3 block">{'Матрица прав'}</Label>
            <Card>
              <CardContent className="p-3">
                <PermissionMatrix resources={resources} selected={permissions} onChange={setPermissions} />
              </CardContent>
            </Card>
            <p className="text-xs text-dark-300 mt-2">
              {'Выбрано: '}{permissions.length}{' прав. Клик на заголовок столбца/строки переключает все права в группе.'}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>{'Отмена'}</Button>
          <Button onClick={handleSubmit} disabled={isPending || !displayName || (!editingRole && !name)}>
            {isPending ? 'Сохранение...' : editingRole ? 'Сохранить' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Admin actions dropdown ─────────────────────────────────────

function AdminActions({ admin, onEdit, onToggle, onDelete }: {
  admin: AdminAccount; onEdit: () => void; onToggle: () => void; onDelete: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <MoreVertical className="w-4 h-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <PermissionGate resource="admins" action="edit">
          <DropdownMenuItem onClick={onEdit}>
            <Pencil className="w-4 h-4 mr-2" /> {'Редактировать'}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onToggle}>
            {admin.is_active
              ? <><UserX className="w-4 h-4 mr-2" /> {'Отключить'}</>
              : <><UserCheck className="w-4 h-4 mr-2" /> {'Включить'}</>
            }
          </DropdownMenuItem>
        </PermissionGate>
        <PermissionGate resource="admins" action="delete">
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onDelete} className="text-red-400 focus:text-red-400">
            <Trash2 className="w-4 h-4 mr-2" /> {'Удалить'}
          </DropdownMenuItem>
        </PermissionGate>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// ── Admins Tab ─────────────────────────────────────────────────

function AdminsTab({ roles }: { roles: Role[] }) {
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [editingAdmin, setEditingAdmin] = useState<AdminAccount | null>(null)
  const [formError, setFormError] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const { data: adminsData, isLoading, refetch } = useQuery({ queryKey: ['admins'], queryFn: adminsApi.list })

  const createMutation = useMutation({
    mutationFn: (data: AdminAccountCreate) => adminsApi.create(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admins'] }); setShowDialog(false); setFormError(''); toast.success('Администратор создан') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { setFormError(err.response?.data?.detail || err.message || 'Ошибка'); toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: AdminAccountUpdate }) => adminsApi.update(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admins'] }); setShowDialog(false); setEditingAdmin(null); setFormError(''); toast.success('Администратор обновлён') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { setFormError(err.response?.data?.detail || err.message || 'Ошибка'); toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminsApi.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admins'] }); toast.success('Администратор удалён') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => adminsApi.update(id, { is_active }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admins'] }); toast.success('Статус администратора обновлён') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const admins = adminsData?.items ?? []

  const handleSave = (data: AdminAccountCreate | AdminAccountUpdate) => {
    if (editingAdmin) updateMutation.mutate({ id: editingAdmin.id, data: data as AdminAccountUpdate })
    else createMutation.mutate(data as AdminAccountCreate)
  }

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <div />
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
          </Button>
          <PermissionGate resource="admins" action="create">
            <Button size="sm" onClick={() => { setEditingAdmin(null); setFormError(''); setShowDialog(true) }}>
              <Plus className="w-4 h-4 mr-1.5" />
              <span className="hidden sm:inline">{'Создать администратора'}</span>
              <span className="sm:hidden">{'Создать'}</span>
            </Button>
          </PermissionGate>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-5 w-32 mb-2" /><Skeleton className="h-4 w-24 mb-3" /><Skeleton className="h-2 w-full" /></CardContent></Card>
          ))
        ) : admins.length === 0 ? (
          <Card><CardContent className="p-8 text-center text-muted-foreground">{'Нет администраторов'}</CardContent></Card>
        ) : (
          admins.map((admin) => (
            <Card key={admin.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-medium text-white">{admin.username}</p>
                    {admin.telegram_id && <p className="text-xs text-dark-300">TG: {admin.telegram_id}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {admin.is_active ? <Badge variant="success">{'Активен'}</Badge> : <Badge variant="destructive">{'Отключён'}</Badge>}
                    <AdminActions admin={admin}
                      onEdit={() => { setEditingAdmin(admin); setFormError(''); setShowDialog(true) }}
                      onToggle={() => toggleMutation.mutate({ id: admin.id, is_active: !admin.is_active })}
                      onDelete={() => setDeleteConfirm(admin.id)} />
                  </div>
                </div>
                <div className="mb-3"><RoleBadge name={admin.role_name} displayName={admin.role_display_name} /></div>
                <div className="space-y-2">
                  <QuotaBar used={admin.users_created} limit={admin.max_users} label="Пользователи" />
                  <QuotaBar used={admin.nodes_created} limit={admin.max_nodes} label="Ноды" />
                  <QuotaBar used={admin.hosts_created} limit={admin.max_hosts} label="Хосты" />
                </div>
                <p className="text-xs text-dark-300 mt-3">{'Создан: '}{formatDate(admin.created_at)}</p>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Desktop table */}
      <Card className="p-0 overflow-hidden hidden md:block">
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>{'Администратор'}</th>
                <th>{'Роль'}</th>
                <th>{'Статус'}</th>
                <th>{'Пользователи'}</th>
                <th>{'Ноды'}</th>
                <th>{'Хосты'}</th>
                <th>{'Создан'}</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}><td><Skeleton className="h-4 w-28" /></td><td><Skeleton className="h-5 w-24" /></td><td><Skeleton className="h-5 w-20" /></td><td><Skeleton className="h-4 w-16" /></td><td><Skeleton className="h-4 w-16" /></td><td><Skeleton className="h-4 w-16" /></td><td><Skeleton className="h-4 w-20" /></td><td></td></tr>
                ))
              ) : admins.length === 0 ? (
                <tr><td colSpan={8} className="text-center py-8 text-muted-foreground">{'Нет администраторов'}</td></tr>
              ) : (
                admins.map((admin) => (
                  <tr key={admin.id}>
                    <td>
                      <div>
                        <span className="font-medium text-white">{admin.username}</span>
                        {admin.telegram_id && <p className="text-xs text-dark-300">TG: {admin.telegram_id}</p>}
                      </div>
                    </td>
                    <td><RoleBadge name={admin.role_name} displayName={admin.role_display_name} /></td>
                    <td>{admin.is_active ? <Badge variant="success">{'Активен'}</Badge> : <Badge variant="destructive">{'Отключён'}</Badge>}</td>
                    <td><div className="min-w-[100px]"><QuotaBar used={admin.users_created} limit={admin.max_users} label="" /></div></td>
                    <td><div className="min-w-[80px]"><QuotaBar used={admin.nodes_created} limit={admin.max_nodes} label="" /></div></td>
                    <td><div className="min-w-[80px]"><QuotaBar used={admin.hosts_created} limit={admin.max_hosts} label="" /></div></td>
                    <td className="text-dark-200 text-sm">{formatDate(admin.created_at)}</td>
                    <td>
                      <AdminActions admin={admin}
                        onEdit={() => { setEditingAdmin(admin); setFormError(''); setShowDialog(true) }}
                        onToggle={() => toggleMutation.mutate({ id: admin.id, is_active: !admin.is_active })}
                        onDelete={() => setDeleteConfirm(admin.id)} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {showDialog && (
        <AdminFormDialog open={showDialog}
          onClose={() => { setShowDialog(false); setEditingAdmin(null); setFormError('') }}
          onSave={handleSave}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={formError} roles={roles} editingAdmin={editingAdmin} />
      )}

      <ConfirmDialog
        open={deleteConfirm !== null}
        onOpenChange={(open) => { if (!open) setDeleteConfirm(null) }}
        title="Удалить администратора?"
        description="Администратор потеряет доступ к панели."
        confirmLabel="Удалить"
        variant="destructive"
        onConfirm={() => {
          if (deleteConfirm !== null) {
            deleteMutation.mutate(deleteConfirm)
            setDeleteConfirm(null)
          }
        }}
      />
    </>
  )
}

// ── Roles Tab ──────────────────────────────────────────────────

function RolesTab({ resources }: { resources: AvailableResources }) {
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [formError, setFormError] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const { data: roles = [], isLoading, refetch } = useQuery({ queryKey: ['roles'], queryFn: rolesApi.list })

  const createMutation = useMutation({
    mutationFn: (data: RoleCreate) => rolesApi.create(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['roles'] }); setShowDialog(false); setFormError(''); toast.success('Роль создана') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { setFormError(err.response?.data?.detail || err.message || 'Ошибка'); toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: RoleUpdate }) => rolesApi.update(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['roles'] }); setShowDialog(false); setEditingRole(null); setFormError(''); toast.success('Роль обновлена') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { setFormError(err.response?.data?.detail || err.message || 'Ошибка'); toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => rolesApi.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['roles'] }); toast.success('Роль удалена') },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => { toast.error(err.response?.data?.detail || err.message || 'Ошибка') },
  })

  const handleSave = (data: RoleCreate | RoleUpdate) => {
    if (editingRole) updateMutation.mutate({ id: editingRole.id, data: data as RoleUpdate })
    else createMutation.mutate(data as RoleCreate)
  }

  const roleColorMap: Record<string, string> = {
    superadmin: 'border-l-red-500', manager: 'border-l-blue-500',
    operator: 'border-l-yellow-500', viewer: 'border-l-gray-500',
  }

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <div />
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
          </Button>
          <PermissionGate resource="roles" action="create">
            <Button size="sm" onClick={() => { setEditingRole(null); setFormError(''); setShowDialog(true) }}>
              <Plus className="w-4 h-4 mr-1.5" />
              <span className="hidden sm:inline">{'Создать роль'}</span>
              <span className="sm:hidden">{'Создать'}</span>
            </Button>
          </PermissionGate>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><CardContent className="p-5"><Skeleton className="h-5 w-32 mb-2" /><Skeleton className="h-4 w-48 mb-4" /><Skeleton className="h-3 w-20" /></CardContent></Card>
          ))
        ) : roles.length === 0 ? (
          <Card className="col-span-full"><CardContent className="p-8 text-center text-muted-foreground">{'Нет ролей'}</CardContent></Card>
        ) : (
          roles.map((role) => (
            <Card key={role.id} className={cn("border-l-[3px] transition-all hover:border-dark-300/50", roleColorMap[role.name] || 'border-l-purple-500')}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Shield className={cn("w-5 h-5",
                      role.name === 'superadmin' ? 'text-red-400' :
                      role.name === 'manager' ? 'text-blue-400' :
                      role.name === 'operator' ? 'text-yellow-400' :
                      role.name === 'viewer' ? 'text-gray-400' : 'text-purple-400'
                    )} />
                    <h3 className="text-white font-semibold">{role.display_name}</h3>
                  </div>
                  {role.is_system && (
                    <Badge variant="secondary" className="text-[10px]">
                      <Lock className="w-2.5 h-2.5 mr-0.5" /> {'Системная'}
                    </Badge>
                  )}
                </div>
                {role.description && <p className="text-sm text-dark-200 mb-3">{role.description}</p>}
                <div className="flex items-center gap-4 text-xs text-dark-300 mb-4">
                  <span className="flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" />{role.permissions_count ?? role.permissions?.length ?? 0}{' прав'}</span>
                  <span className="flex items-center gap-1"><UsersIcon className="w-3.5 h-3.5" />{role.admins_count ?? 0}{' админов'}</span>
                </div>
                <div className="flex flex-wrap gap-1 mb-4">
                  {role.permissions?.slice(0, 8).map((p) => (
                    <span key={`${p.resource}:${p.action}`} className="text-[10px] px-1.5 py-0.5 rounded bg-dark-600/50 text-dark-200">
                      {p.resource}:{p.action}
                    </span>
                  ))}
                  {(role.permissions?.length || 0) > 8 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-600/50 text-dark-300">+{(role.permissions?.length || 0) - 8}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 pt-3 border-t border-dark-400/20">
                  <PermissionGate resource="roles" action="edit">
                    <Button variant="secondary" size="sm" onClick={() => { setEditingRole(role); setFormError(''); setShowDialog(true) }}>
                      <Pencil className="w-3.5 h-3.5 mr-1.5" /> {'Редактировать'}
                    </Button>
                  </PermissionGate>
                  {!role.is_system && (
                    <PermissionGate resource="roles" action="delete">
                      <Button variant="secondary" size="sm" onClick={() => setDeleteConfirm(role.id)} className="text-red-400 hover:text-red-300">
                        <Trash2 className="w-3.5 h-3.5 mr-1.5" /> {'Удалить'}
                      </Button>
                    </PermissionGate>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {showDialog && (
        <RoleFormDialog open={showDialog}
          onClose={() => { setShowDialog(false); setEditingRole(null); setFormError('') }}
          onSave={handleSave}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={formError} resources={resources} editingRole={editingRole} />
      )}

      <ConfirmDialog
        open={deleteConfirm !== null}
        onOpenChange={(open) => { if (!open) setDeleteConfirm(null) }}
        title="Удалить роль?"
        description="Роль будет удалена. Администраторы с этой ролью потеряют права."
        confirmLabel="Удалить"
        variant="destructive"
        onConfirm={() => {
          if (deleteConfirm !== null) {
            deleteMutation.mutate(deleteConfirm)
            setDeleteConfirm(null)
          }
        }}
      />
    </>
  )
}

// ── Audit Log Tab ──────────────────────────────────────────────

const ACTION_DISPLAY: Record<string, string> = {
  'admin.create': 'Создание админа',
  'admin.update': 'Обновление админа',
  'admin.delete': 'Удаление админа',
  'role.create': 'Создание роли',
  'role.update': 'Обновление роли',
  'role.delete': 'Удаление роли',
  'login': 'Вход в систему',
  'logout': 'Выход из системы',
}

function AuditTab() {
  const [page, setPage] = useState(1)
  const perPage = 30

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['audit-log', page],
    queryFn: () => adminsApi.auditLog({ limit: perPage, offset: (page - 1) * perPage }),
    refetchInterval: 30000,
  })

  const logs = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))

  function formatDateTime(dateStr: string | null): string {
    if (!dateStr) return '\u2014'
    return new Date(dateStr).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  }

  function parseDetails(details: string | null): Record<string, string> | null {
    if (!details) return null
    try { return JSON.parse(details) } catch { return null }
  }

  return (
    <div className="space-y-4 mt-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {'Всего записей: '}{total}
        </p>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" />
          {'Обновить'}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : logs.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <History className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>{'Записи отсутствуют'}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dark-400/20">
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium">{'Дата'}</th>
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium">{'Администратор'}</th>
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium">{'Действие'}</th>
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium hidden md:table-cell">{'Ресурс'}</th>
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium hidden lg:table-cell">{'Детали'}</th>
                    <th className="text-left py-3 px-4 text-xs text-muted-foreground font-medium hidden lg:table-cell">{'IP'}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log: AuditLogEntry) => {
                    const details = parseDetails(log.details)
                    return (
                      <tr key={log.id} className="border-b border-dark-400/10 hover:bg-dark-700/30 transition-colors">
                        <td className="py-2.5 px-4 text-xs text-dark-100 whitespace-nowrap">
                          {formatDateTime(log.created_at)}
                        </td>
                        <td className="py-2.5 px-4">
                          <span className="text-white font-medium">{log.admin_username}</span>
                        </td>
                        <td className="py-2.5 px-4">
                          <Badge variant={
                            log.action.includes('delete') ? 'destructive' :
                            log.action.includes('create') ? 'success' :
                            'secondary'
                          } className="text-xs">
                            {ACTION_DISPLAY[log.action] || log.action}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-4 hidden md:table-cell">
                          {log.resource && (
                            <span className="text-dark-100 text-xs">
                              {RESOURCE_LABELS[log.resource] || log.resource}
                              {log.resource_id && <span className="text-dark-300 ml-1">#{log.resource_id}</span>}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 hidden lg:table-cell max-w-[200px]">
                          {details && (
                            <span className="text-dark-200 text-xs truncate block" title={log.details || ''}>
                              {Object.entries(details).map(([k, v]) => `${k}: ${v}`).join(', ')}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 hidden lg:table-cell">
                          <span className="text-dark-300 text-xs font-mono">{log.ip_address || '\u2014'}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="secondary" size="icon" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button variant="secondary" size="icon" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────

export default function Admins() {
  const { data: roles = [] } = useQuery({ queryKey: ['roles'], queryFn: rolesApi.list })
  const { data: resources = {} } = useQuery({ queryKey: ['roles-resources'], queryFn: rolesApi.getResources })
  const canViewAudit = useHasPermission('audit', 'view')

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{'Администрирование'}</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">
            {'Управление учётными записями и ролями'}
          </p>
        </div>
      </div>

      <Tabs defaultValue="admins">
        <TabsList>
          <TabsTrigger value="admins">{'Администраторы'}</TabsTrigger>
          <TabsTrigger value="roles">{'Роли'}</TabsTrigger>
          {canViewAudit && (
            <TabsTrigger value="audit">
              <History className="w-4 h-4 mr-1.5" />
              {'Журнал'}
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="admins">
          <AdminsTab roles={roles} />
        </TabsContent>
        <TabsContent value="roles">
          <RolesTab resources={resources} />
        </TabsContent>
        {canViewAudit && (
          <TabsContent value="audit">
            <AuditTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
