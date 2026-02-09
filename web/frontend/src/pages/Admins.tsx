import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Pencil,
  Trash2,
  MoreVertical,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Eye,
  UserCheck,
  UserX,
  RefreshCw,
} from 'lucide-react'
import { adminsApi, rolesApi, AdminAccount, AdminAccountCreate, AdminAccountUpdate, Role } from '../api/admins'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { PermissionGate } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'

// ── Helpers ────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
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
      <div className="flex items-center justify-between text-xs">
        <span className="text-dark-300">{label}</span>
        <span className="text-dark-100">
          {used} / {isUnlimited ? '\u221E' : limit}
        </span>
      </div>
      <div className="h-1.5 bg-dark-600 rounded-full overflow-hidden">
        {!isUnlimited && percent > 0 && (
          <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${percent}%` }} />
        )}
      </div>
    </div>
  )
}

// ── Create/Edit Dialog ─────────────────────────────────────────

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
          <DialogTitle>{editingAdmin ? 'Редактирование администратора' : 'Создание администратора'}</DialogTitle>
          <DialogDescription>
            {editingAdmin ? 'Измените данные администратора' : 'Заполните данные нового администратора'}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label>Имя пользователя *</Label>
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
            <p className="text-xs text-dark-300 mt-1">Для входа через Telegram Login Widget</p>
          </div>

          <div>
            <Label>Роль *</Label>
            <select
              value={form.role_id}
              onChange={(e) => setForm({ ...form, role_id: e.target.value })}
              className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1.5"
            >
              <option value="">Выберите роль</option>
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
            <p className="text-sm font-medium text-dark-100 mb-3">Лимиты (пусто = безлимитно)</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Макс. пользователей</Label>
                <Input
                  type="number"
                  min="0"
                  value={form.max_users}
                  onChange={(e) => setForm({ ...form, max_users: e.target.value })}
                  placeholder="\u221E"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs">Макс. трафик (GB)</Label>
                <Input
                  type="number"
                  min="0"
                  value={form.max_traffic_gb}
                  onChange={(e) => setForm({ ...form, max_traffic_gb: e.target.value })}
                  placeholder="\u221E"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs">Макс. нод</Label>
                <Input
                  type="number"
                  min="0"
                  value={form.max_nodes}
                  onChange={(e) => setForm({ ...form, max_nodes: e.target.value })}
                  placeholder="\u221E"
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs">Макс. хостов</Label>
                <Input
                  type="number"
                  min="0"
                  value={form.max_hosts}
                  onChange={(e) => setForm({ ...form, max_hosts: e.target.value })}
                  placeholder="\u221E"
                  className="mt-1"
                />
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={isPending}>Отмена</Button>
          <Button onClick={handleSubmit} disabled={isPending || !form.username || !form.role_id}>
            {isPending ? 'Сохранение...' : editingAdmin ? 'Сохранить' : 'Создать'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main component ─────────────────────────────────────────────

export default function Admins() {
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [editingAdmin, setEditingAdmin] = useState<AdminAccount | null>(null)
  const [formError, setFormError] = useState('')

  const { data: adminsData, isLoading, refetch } = useQuery({
    queryKey: ['admins'],
    queryFn: adminsApi.list,
  })

  const { data: roles = [] } = useQuery({
    queryKey: ['roles'],
    queryFn: rolesApi.list,
  })

  const createMutation = useMutation({
    mutationFn: (data: AdminAccountCreate) => adminsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      setShowDialog(false)
      setFormError('')
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: AdminAccountUpdate }) => adminsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admins'] })
      setShowDialog(false)
      setEditingAdmin(null)
      setFormError('')
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Ошибка обновления')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admins'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      adminsApi.update(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admins'] })
    },
  })

  const admins = adminsData?.items ?? []

  const handleOpenCreate = () => {
    setEditingAdmin(null)
    setFormError('')
    setShowDialog(true)
  }

  const handleOpenEdit = (admin: AdminAccount) => {
    setEditingAdmin(admin)
    setFormError('')
    setShowDialog(true)
  }

  const handleSave = (data: AdminAccountCreate | AdminAccountUpdate) => {
    if (editingAdmin) {
      updateMutation.mutate({ id: editingAdmin.id, data: data as AdminAccountUpdate })
    } else {
      createMutation.mutate(data as AdminAccountCreate)
    }
  }

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Администраторы</h1>
          <p className="text-muted-foreground mt-1 text-sm md:text-base">
            Управление учётными записями и ролями
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="icon" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn("w-5 h-5", isLoading && "animate-spin")} />
          </Button>
          <PermissionGate resource="admins" action="create">
            <Button onClick={handleOpenCreate}>
              <Plus className="w-4 h-4 mr-2" />
              <span className="hidden sm:inline">Создать администратора</span>
              <span className="sm:hidden">Создать</span>
            </Button>
          </PermissionGate>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-32 mb-2" />
                <Skeleton className="h-4 w-24 mb-3" />
                <Skeleton className="h-2 w-full" />
              </CardContent>
            </Card>
          ))
        ) : admins.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground">
              Нет администраторов
            </CardContent>
          </Card>
        ) : (
          admins.map((admin) => (
            <Card key={admin.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-medium text-white">{admin.username}</p>
                    {admin.telegram_id && (
                      <p className="text-xs text-dark-300">TG: {admin.telegram_id}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {admin.is_active ? (
                      <Badge variant="success">Активен</Badge>
                    ) : (
                      <Badge variant="destructive">Отключён</Badge>
                    )}
                    <AdminActions
                      admin={admin}
                      onEdit={() => handleOpenEdit(admin)}
                      onToggle={() => toggleMutation.mutate({ id: admin.id, is_active: !admin.is_active })}
                      onDelete={() => { if (confirm('Удалить администратора?')) deleteMutation.mutate(admin.id) }}
                    />
                  </div>
                </div>
                <div className="mb-3">
                  <RoleBadge name={admin.role_name} displayName={admin.role_display_name} />
                </div>
                <div className="space-y-2">
                  <QuotaBar used={admin.users_created} limit={admin.max_users} label="Пользователи" />
                  <QuotaBar used={admin.nodes_created} limit={admin.max_nodes} label="Ноды" />
                  <QuotaBar used={admin.hosts_created} limit={admin.max_hosts} label="Хосты" />
                </div>
                <p className="text-xs text-dark-300 mt-3">Создан: {formatDate(admin.created_at)}</p>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Desktop table */}
      <Card className="p-0 overflow-hidden hidden md:block animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Администратор</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Пользователи</th>
                <th>Ноды</th>
                <th>Хосты</th>
                <th>Создан</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td><Skeleton className="h-4 w-28" /></td>
                    <td><Skeleton className="h-5 w-24" /></td>
                    <td><Skeleton className="h-5 w-20" /></td>
                    <td><Skeleton className="h-4 w-16" /></td>
                    <td><Skeleton className="h-4 w-16" /></td>
                    <td><Skeleton className="h-4 w-16" /></td>
                    <td><Skeleton className="h-4 w-20" /></td>
                    <td></td>
                  </tr>
                ))
              ) : admins.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-muted-foreground">
                    Нет администраторов
                  </td>
                </tr>
              ) : (
                admins.map((admin) => (
                  <tr key={admin.id}>
                    <td>
                      <div>
                        <span className="font-medium text-white">{admin.username}</span>
                        {admin.telegram_id && (
                          <p className="text-xs text-dark-300">TG: {admin.telegram_id}</p>
                        )}
                      </div>
                    </td>
                    <td>
                      <RoleBadge name={admin.role_name} displayName={admin.role_display_name} />
                    </td>
                    <td>
                      {admin.is_active ? (
                        <Badge variant="success">Активен</Badge>
                      ) : (
                        <Badge variant="destructive">Отключён</Badge>
                      )}
                    </td>
                    <td>
                      <div className="min-w-[100px]">
                        <QuotaBar used={admin.users_created} limit={admin.max_users} label="" />
                      </div>
                    </td>
                    <td>
                      <div className="min-w-[80px]">
                        <QuotaBar used={admin.nodes_created} limit={admin.max_nodes} label="" />
                      </div>
                    </td>
                    <td>
                      <div className="min-w-[80px]">
                        <QuotaBar used={admin.hosts_created} limit={admin.max_hosts} label="" />
                      </div>
                    </td>
                    <td className="text-dark-200 text-sm">{formatDate(admin.created_at)}</td>
                    <td>
                      <AdminActions
                        admin={admin}
                        onEdit={() => handleOpenEdit(admin)}
                        onToggle={() => toggleMutation.mutate({ id: admin.id, is_active: !admin.is_active })}
                        onDelete={() => { if (confirm('Удалить администратора?')) deleteMutation.mutate(admin.id) }}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create/Edit Dialog */}
      {showDialog && (
        <AdminFormDialog
          open={showDialog}
          onClose={() => { setShowDialog(false); setEditingAdmin(null); setFormError('') }}
          onSave={handleSave}
          isPending={createMutation.isPending || updateMutation.isPending}
          error={formError}
          roles={roles}
          editingAdmin={editingAdmin}
        />
      )}
    </div>
  )
}

// ── Admin actions dropdown ─────────────────────────────────────

function AdminActions({
  admin,
  onEdit,
  onToggle,
  onDelete,
}: {
  admin: AdminAccount
  onEdit: () => void
  onToggle: () => void
  onDelete: () => void
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
            <Pencil className="w-4 h-4 mr-2" /> Редактировать
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onToggle}>
            {admin.is_active ? (
              <><UserX className="w-4 h-4 mr-2" /> Отключить</>
            ) : (
              <><UserCheck className="w-4 h-4 mr-2" /> Включить</>
            )}
          </DropdownMenuItem>
        </PermissionGate>
        <PermissionGate resource="admins" action="delete">
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onDelete} className="text-red-400 focus:text-red-400">
            <Trash2 className="w-4 h-4 mr-2" /> Удалить
          </DropdownMenuItem>
        </PermissionGate>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
