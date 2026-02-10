import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, formatDistanceToNow, subDays } from 'date-fns'
import { ru } from 'date-fns/locale'
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Clock,
  User,
  Shield,
  Server,
  Globe,
  Settings,
  ShieldAlert,
  Users,
  UserCog,
  Activity,
  FileText,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Skeleton } from '@/components/ui/skeleton'
import { ExportDropdown } from '@/components/ExportDropdown'
import { exportCSV, exportJSON } from '@/lib/export'
import { auditApi, type AuditLogParams } from '@/api/audit'

// ── Constants ───────────────────────────────────────────────────

const PER_PAGE = 30

const RESOURCE_ICONS: Record<string, typeof Users> = {
  users: Users,
  nodes: Server,
  hosts: Globe,
  violations: ShieldAlert,
  settings: Settings,
  admins: UserCog,
  roles: Shield,
  auth: User,
  fleet: Activity,
}

const RESOURCE_COLORS: Record<string, string> = {
  users: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  nodes: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  hosts: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  violations: 'bg-red-500/20 text-red-400 border-red-500/30',
  settings: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  admins: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  roles: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
  auth: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
}

const ACTION_LABELS: Record<string, string> = {
  create: 'Создание',
  update: 'Изменение',
  delete: 'Удаление',
  enable: 'Включение',
  disable: 'Отключение',
  restart: 'Перезапуск',
  login: 'Вход',
  logout: 'Выход',
  login_telegram: 'Вход (Telegram)',
  change_password: 'Смена пароля',
  resolve: 'Разрешение',
  reset_traffic: 'Сброс трафика',
  revoke: 'Отзыв подписки',
  sync_hwid: 'Синхр. HWID',
  bulk_enable: 'Массовое включение',
  bulk_disable: 'Массовое отключение',
  bulk_delete: 'Массовое удаление',
  'bulk_reset-traffic': 'Массовый сброс трафика',
  generate_token: 'Генерация токена',
  revoke_token: 'Отзыв токена',
  trigger_sync: 'Запуск синхронизации',
  update_ip_whitelist: 'Обн. IP-списка',
  reset: 'Сброс настройки',
}

const PERIOD_OPTIONS = [
  { value: 'all', label: 'Все время' },
  { value: '24h', label: 'Последние 24ч' },
  { value: '7d', label: 'Последние 7 дней' },
  { value: '30d', label: 'Последние 30 дней' },
]

// ── Helpers ──────────────────────────────────────────────────────

function parseAction(fullAction: string): { resource: string; action: string } {
  const dot = fullAction.indexOf('.')
  if (dot === -1) return { resource: '', action: fullAction }
  return { resource: fullAction.slice(0, dot), action: fullAction.slice(dot + 1) }
}

function getActionLabel(action: string): string {
  return ACTION_LABELS[action] || action
}

function getActionColor(action: string): string {
  if (action.includes('delete') || action === 'disable' || action.includes('revoke'))
    return 'bg-red-500/20 text-red-400 border-red-500/30'
  if (action === 'create' || action === 'enable')
    return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
  if (action.includes('login') || action === 'change_password')
    return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
  if (action === 'logout')
    return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
}

// ── Component ───────────────────────────────────────────────────

export default function AuditLog() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [resourceFilter, setResourceFilter] = useState<string>('all')
  const [periodFilter, setPeriodFilter] = useState<string>('all')
  const [searchInput, setSearchInput] = useState('')

  // Build query params
  const params = useMemo<AuditLogParams>(() => {
    const p: AuditLogParams = {
      limit: PER_PAGE,
      offset: (page - 1) * PER_PAGE,
    }
    if (search) p.search = search
    if (resourceFilter !== 'all') p.resource = resourceFilter
    if (periodFilter !== 'all') {
      const now = new Date()
      if (periodFilter === '24h') p.date_from = subDays(now, 1).toISOString()
      else if (periodFilter === '7d') p.date_from = subDays(now, 7).toISOString()
      else if (periodFilter === '30d') p.date_from = subDays(now, 30).toISOString()
    }
    return p
  }, [page, search, resourceFilter, periodFilter])

  const { data, isLoading } = useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => auditApi.list(params),
    refetchInterval: 15000,
  })

  const { data: stats } = useQuery({
    queryKey: ['audit-stats'],
    queryFn: () => auditApi.stats(),
    staleTime: 30000,
  })

  const { data: actions } = useQuery({
    queryKey: ['audit-actions'],
    queryFn: () => auditApi.actions(),
    staleTime: 60000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  // Unique resources from actions
  const resources = useMemo(() => {
    if (!actions) return []
    const set = new Set<string>()
    actions.forEach((a) => {
      const dot = a.indexOf('.')
      if (dot > 0) set.add(a.slice(0, dot))
    })
    return Array.from(set).sort()
  }, [actions])

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(1)
  }

  // Export data
  const exportData = useMemo(
    () =>
      items.map((item) => {
        const { resource, action } = parseAction(item.action)
        return {
          id: item.id,
          date: item.created_at ? format(new Date(item.created_at), 'yyyy-MM-dd HH:mm:ss') : '',
          admin: item.admin_username,
          resource,
          action: getActionLabel(action),
          resource_id: item.resource_id || '',
          details: item.details || '',
          ip: item.ip_address || '',
        }
      }),
    [items],
  )

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Журнал аудита</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Все действия администраторов в системе
          </p>
        </div>
        <ExportDropdown
          onExportCSV={() => exportCSV(exportData, 'audit-log')}
          onExportJSON={() => exportJSON(exportData, 'audit-log')}
          disabled={items.length === 0}
        />
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-cyan-500/20">
                <FileText className="w-4 h-4 text-cyan-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Всего записей</p>
                <p className="text-lg font-bold text-white">{stats?.total?.toLocaleString() ?? '—'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/20">
                <Clock className="w-4 h-4 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Сегодня</p>
                <p className="text-lg font-bold text-white">{stats?.today ?? '—'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-500/20">
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Активных админов</p>
                <p className="text-lg font-bold text-white">{stats?.by_admin?.length ?? '—'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-dark-800 border-dark-700">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-500/20">
                <Activity className="w-4 h-4 text-purple-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Типов ресурсов</p>
                <p className="text-lg font-bold text-white">
                  {stats?.by_resource ? Object.keys(stats.by_resource).length : '—'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="bg-dark-800 border-dark-700">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по админу, действию, ресурсу..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="pl-9 bg-dark-900 border-dark-600"
              />
            </div>
            <Select value={resourceFilter} onValueChange={(v) => { setResourceFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-dark-900 border-dark-600">
                <Filter className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue placeholder="Ресурс" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все ресурсы</SelectItem>
                {resources.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={periodFilter} onValueChange={(v) => { setPeriodFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[160px] bg-dark-900 border-dark-600">
                <Clock className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIOD_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={handleSearch}
              className="border-dark-600"
            >
              <Search className="w-4 h-4 mr-2" />
              Найти
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card className="bg-dark-800 border-dark-700">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>Записей не найдено</p>
            </div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden md:block overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-dark-700 hover:bg-transparent">
                      <TableHead className="text-dark-200 w-[180px]">Дата</TableHead>
                      <TableHead className="text-dark-200 w-[140px]">Админ</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">Ресурс</TableHead>
                      <TableHead className="text-dark-200 w-[160px]">Действие</TableHead>
                      <TableHead className="text-dark-200">ID ресурса</TableHead>
                      <TableHead className="text-dark-200">Детали</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">IP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => {
                      const parsed = parseAction(item.action)
                      const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
                      const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                      const actionColor = getActionColor(parsed.action)

                      return (
                        <TableRow key={item.id} className="border-dark-700">
                          <TableCell className="text-dark-200 whitespace-nowrap">
                            <Tooltip>
                              <TooltipTrigger>
                                {item.created_at
                                  ? formatDistanceToNow(new Date(item.created_at), {
                                      addSuffix: true,
                                      locale: ru,
                                    })
                                  : '—'}
                              </TooltipTrigger>
                              <TooltipContent>
                                {item.created_at
                                  ? format(new Date(item.created_at), 'dd.MM.yyyy HH:mm:ss')
                                  : ''}
                              </TooltipContent>
                            </Tooltip>
                          </TableCell>
                          <TableCell>
                            <span className="font-medium text-white">
                              {item.admin_username}
                            </span>
                          </TableCell>
                          <TableCell>
                            {parsed.resource && (
                              <Badge
                                variant="outline"
                                className={`${resourceColor} border text-xs gap-1`}
                              >
                                <ResourceIcon className="w-3 h-3" />
                                {parsed.resource}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={`${actionColor} border text-xs`}
                            >
                              {getActionLabel(parsed.action)}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-dark-200 font-mono text-xs max-w-[200px] truncate">
                            {item.resource_id || '—'}
                          </TableCell>
                          <TableCell className="text-dark-300 text-xs max-w-[200px] truncate">
                            {item.details || '—'}
                          </TableCell>
                          <TableCell className="text-dark-300 font-mono text-xs">
                            {item.ip_address || '—'}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden p-4 space-y-3">
                {items.map((item) => {
                  const parsed = parseAction(item.action)
                  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
                  const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400'
                  const actionColor = getActionColor(parsed.action)

                  return (
                    <div
                      key={item.id}
                      className="p-3 rounded-lg bg-dark-900 border border-dark-700 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-white text-sm">
                          {item.admin_username}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {item.created_at
                            ? formatDistanceToNow(new Date(item.created_at), {
                                addSuffix: true,
                                locale: ru,
                              })
                            : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {parsed.resource && (
                          <Badge
                            variant="outline"
                            className={`${resourceColor} border text-xs gap-1`}
                          >
                            <ResourceIcon className="w-3 h-3" />
                            {parsed.resource}
                          </Badge>
                        )}
                        <Badge
                          variant="outline"
                          className={`${actionColor} border text-xs`}
                        >
                          {getActionLabel(parsed.action)}
                        </Badge>
                      </div>
                      {item.resource_id && (
                        <p className="text-xs text-muted-foreground font-mono truncate">
                          ID: {item.resource_id}
                        </p>
                      )}
                      {item.ip_address && (
                        <p className="text-xs text-muted-foreground">
                          IP: {item.ip_address}
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between p-4 border-t border-dark-700">
                <p className="text-sm text-muted-foreground">
                  {total} {total === 1 ? 'запись' : total < 5 ? 'записи' : 'записей'}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="border-dark-600"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-dark-200">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                    className="border-dark-600"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
