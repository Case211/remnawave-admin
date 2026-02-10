import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, formatDistanceToNow, subDays } from 'date-fns'
import { ru } from 'date-fns/locale'
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
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
  Zap,
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
import { auditApi, type AuditLogEntry, type AuditLogParams } from '@/api/audit'

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
  automation: Zap,
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
  automation: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
}

const RESOURCE_LABELS: Record<string, string> = {
  users: 'Пользователи',
  nodes: 'Ноды',
  hosts: 'Хосты',
  violations: 'Нарушения',
  settings: 'Настройки',
  admins: 'Админы',
  roles: 'Роли',
  auth: 'Авторизация',
  fleet: 'Флот',
  automation: 'Автоматизация',
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
  toggle: 'Переключение',
  template_activate: 'Активация шаблона',
}

// Human-readable descriptions: resource -> action -> (details) => string
const DESCRIPTIONS: Record<string, Record<string, (target: string, details: Record<string, unknown> | null) => string>> = {
  users: {
    create: (t) => `Создал пользователя ${t}`,
    update: (t) => `Изменил пользователя ${t}`,
    delete: (t) => `Удалил пользователя ${t}`,
    enable: (t) => `Включил пользователя ${t}`,
    disable: (t) => `Отключил пользователя ${t}`,
    reset_traffic: (t) => `Сбросил трафик пользователя ${t}`,
    revoke: (t) => `Отозвал подписку пользователя ${t}`,
    sync_hwid: (t) => `Синхронизировал HWID пользователя ${t}`,
    bulk_enable: () => 'Массово включил пользователей',
    bulk_disable: () => 'Массово отключил пользователей',
    bulk_delete: () => 'Массово удалил пользователей',
    'bulk_reset-traffic': () => 'Массово сбросил трафик',
  },
  nodes: {
    create: (t) => `Создал ноду ${t}`,
    update: (t) => `Изменил ноду ${t}`,
    delete: (t) => `Удалил ноду ${t}`,
    enable: (t) => `Включил ноду ${t}`,
    disable: (t) => `Отключил ноду ${t}`,
    restart: (t) => `Перезапустил ноду ${t}`,
    generate_token: (t) => `Сгенерировал токен для ноды ${t}`,
    revoke_token: (t) => `Отозвал токен ноды ${t}`,
  },
  hosts: {
    create: (t) => `Создал хост ${t}`,
    update: (t) => `Изменил хост ${t}`,
    delete: (t) => `Удалил хост ${t}`,
    enable: (t) => `Включил хост ${t}`,
    disable: (t) => `Отключил хост ${t}`,
  },
  settings: {
    update: (_t, d) => `Изменил настройку ${d?.setting || _t}`,
    reset: (_t, d) => `Сбросил настройку ${d?.setting || _t}`,
    trigger_sync: () => 'Запустил синхронизацию',
    update_ip_whitelist: () => 'Обновил IP-список',
  },
  admins: {
    create: (_t, d) => `Создал админа ${d?.username || _t}`,
    update: (_t, d) => `Изменил админа ${d?.username || _t}`,
    delete: (_t, d) => `Удалил админа ${d?.deleted_username || _t}`,
  },
  roles: {
    create: (_t, d) => `Создал роль ${d?.name || _t}`,
    update: (t) => `Изменил роль ${t}`,
    delete: (_t, d) => `Удалил роль ${d?.deleted_role || _t}`,
  },
  violations: {
    resolve: (t) => `Разрешил нарушение ${t}`,
  },
  auth: {
    login: () => 'Вошёл в систему',
    logout: () => 'Вышел из системы',
    login_telegram: () => 'Вошёл через Telegram',
    change_password: () => 'Сменил пароль',
  },
  automation: {
    create: (_t, d) => `Создал правило ${d?.name || _t}`,
    update: (t) => `Изменил правило ${t}`,
    delete: (_t, d) => `Удалил правило ${d?.name || _t}`,
    toggle: (_t, d) => `${d?.new_state === 'enabled' ? 'Включил' : 'Отключил'} правило ${d?.name || _t}`,
    template_activate: (_t, d) => `Активировал шаблон ${d?.name || _t}`,
  },
}

// Labels for detail fields (for human-readable key-value display)
const DETAIL_LABELS: Record<string, string> = {
  username: 'Пользователь',
  name: 'Название',
  remark: 'Примечание',
  data_limit: 'Лимит трафика',
  expire_date: 'Срок действия',
  status: 'Статус',
  note: 'Заметка',
  data_limit_reset_strategy: 'Стратегия сброса',
  on_hold_expire_duration: 'Длительность удержания',
  on_hold_timeout: 'Таймаут удержания',
  address: 'Адрес',
  port: 'Порт',
  sni: 'SNI',
  host: 'Хост',
  alpn: 'ALPN',
  fingerprint: 'Отпечаток',
  is_disabled: 'Отключён',
  role_id: 'Роль (ID)',
  value: 'Значение',
  setting: 'Настройка',
  deleted_username: 'Удалённый пользователь',
  deleted_role: 'Удалённая роль',
  template_id: 'Шаблон',
  action_type: 'Тип действия',
  new_state: 'Новое состояние',
  updated_fields: 'Изменённые поля',
  inbound_tags: 'Входящие теги',
  telegram_id: 'Telegram ID',
  max_users: 'Макс. пользователей',
  max_traffic_gb: 'Макс. трафик (ГБ)',
  max_nodes: 'Макс. нод',
  max_hosts: 'Макс. хостов',
  is_active: 'Активен',
  is_generated_password: 'Сгенерированный пароль',
  display_name: 'Отображаемое имя',
  description: 'Описание',
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

function tryParseJSON(str: string | null): Record<string, unknown> | null {
  if (!str) return null
  try {
    const parsed = JSON.parse(str)
    return typeof parsed === 'object' && parsed !== null ? parsed : null
  } catch {
    return null
  }
}

function formatBytes(bytes: unknown): string {
  const num = Number(bytes)
  if (isNaN(num) || num === 0) return '0'
  if (num >= 1099511627776) return `${(num / 1099511627776).toFixed(1)} ТБ`
  if (num >= 1073741824) return `${(num / 1073741824).toFixed(1)} ГБ`
  if (num >= 1048576) return `${(num / 1048576).toFixed(1)} МБ`
  return `${(num / 1024).toFixed(0)} КБ`
}

function formatDetailValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (key === 'data_limit' && typeof value === 'number') return formatBytes(value)
  if (key === 'expire_date' && typeof value === 'string') {
    try {
      return format(new Date(value), 'dd.MM.yyyy HH:mm')
    } catch { return String(value) }
  }
  if (key === 'new_state') return value === 'enabled' ? 'Включено' : 'Отключено'
  if (key === 'is_disabled') return value ? 'Да' : 'Нет'
  if (key === 'is_active') return value ? 'Да' : 'Нет'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function getDescription(
  resource: string,
  action: string,
  resourceId: string | null,
  details: Record<string, unknown> | null,
): string {
  const target = (details?.username as string)
    || (details?.name as string)
    || (details?.remark as string)
    || (details?.setting as string)
    || resourceId
    || ''

  const resourceDescs = DESCRIPTIONS[resource]
  if (resourceDescs) {
    const descFn = resourceDescs[action]
    if (descFn) return descFn(target, details)
  }

  // Fallback: generate a generic description
  const actionLabel = getActionLabel(action).toLowerCase()
  const resourceLabel = (RESOURCE_LABELS[resource] || resource).toLowerCase()
  return `${actionLabel} ${resourceLabel}${target ? ` ${target}` : ''}`
}

/** Get top N detail entries, excluding keys already used in description */
function getVisibleDetails(details: Record<string, unknown> | null): [string, unknown][] {
  if (!details) return []
  // Keys that are already shown in description text or not useful
  const skipKeys = new Set(['setting'])
  return Object.entries(details).filter(([k]) => !skipKeys.has(k))
}

// ── Component ───────────────────────────────────────────────────

export default function AuditLog() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [resourceFilter, setResourceFilter] = useState<string>('all')
  const [actionFilter, setActionFilter] = useState<string>('all')
  const [periodFilter, setPeriodFilter] = useState<string>('all')
  const [searchInput, setSearchInput] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  // Build query params
  const params = useMemo<AuditLogParams>(() => {
    const p: AuditLogParams = {
      limit: PER_PAGE,
      offset: (page - 1) * PER_PAGE,
    }
    if (search) p.search = search
    if (resourceFilter !== 'all') p.resource = resourceFilter
    if (actionFilter !== 'all') p.action = actionFilter
    if (periodFilter !== 'all') {
      const now = new Date()
      if (periodFilter === '24h') p.date_from = subDays(now, 1).toISOString()
      else if (periodFilter === '7d') p.date_from = subDays(now, 7).toISOString()
      else if (periodFilter === '30d') p.date_from = subDays(now, 30).toISOString()
    }
    return p
  }, [page, search, resourceFilter, actionFilter, periodFilter])

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

  // Unique action types for filter
  const actionTypes = useMemo(() => {
    if (!actions) return []
    const set = new Set<string>()
    actions.forEach((a) => {
      const dot = a.indexOf('.')
      if (dot > 0) set.add(a.slice(dot + 1))
    })
    return Array.from(set).sort()
  }, [actions])

  const handleSearch = () => {
    setSearch(searchInput)
    setPage(1)
  }

  const toggleRow = (id: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Export data
  const exportData = useMemo(
    () =>
      items.map((item) => {
        const { resource, action } = parseAction(item.action)
        const details = tryParseJSON(item.details)
        return {
          id: item.id,
          date: item.created_at ? format(new Date(item.created_at), 'yyyy-MM-dd HH:mm:ss') : '',
          admin: item.admin_username,
          resource,
          action: getActionLabel(action),
          description: getDescription(resource, action, item.resource_id, details),
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
                    {RESOURCE_LABELS[r] || r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={actionFilter} onValueChange={(v) => { setActionFilter(v); setPage(1) }}>
              <SelectTrigger className="w-[180px] bg-dark-900 border-dark-600">
                <Activity className="w-4 h-4 mr-2 text-muted-foreground" />
                <SelectValue placeholder="Действие" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все действия</SelectItem>
                {actionTypes.map((a) => (
                  <SelectItem key={a} value={a}>
                    {getActionLabel(a)}
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
                      <TableHead className="text-dark-200 w-[160px]">Дата</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">Админ</TableHead>
                      <TableHead className="text-dark-200">Действие</TableHead>
                      <TableHead className="text-dark-200">Детали</TableHead>
                      <TableHead className="text-dark-200 w-[120px]">IP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <AuditRow
                        key={item.id}
                        item={item}
                        expanded={expandedRows.has(item.id)}
                        onToggle={() => toggleRow(item.id)}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden p-4 space-y-3">
                {items.map((item) => (
                  <MobileAuditCard key={item.id} item={item} />
                ))}
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

// ── Desktop Row Component ────────────────────────────────────────

function AuditRow({
  item,
  expanded,
  onToggle,
}: {
  item: AuditLogEntry
  expanded: boolean
  onToggle: () => void
}) {
  const parsed = parseAction(item.action)
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const hasDetails = visibleDetails.length > 0

  return (
    <>
      <TableRow
        className={`border-dark-700 ${hasDetails ? 'cursor-pointer hover:bg-dark-700/50' : ''}`}
        onClick={hasDetails ? onToggle : undefined}
      >
        {/* Date */}
        <TableCell className="text-dark-200 whitespace-nowrap align-top">
          <Tooltip>
            <TooltipTrigger>
              <span className="text-sm">
                {item.created_at
                  ? formatDistanceToNow(new Date(item.created_at), {
                      addSuffix: true,
                      locale: ru,
                    })
                  : '—'}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {item.created_at
                ? format(new Date(item.created_at), 'dd.MM.yyyy HH:mm:ss')
                : ''}
            </TooltipContent>
          </Tooltip>
        </TableCell>

        {/* Admin */}
        <TableCell className="align-top">
          <span className="font-medium text-white text-sm">
            {item.admin_username}
          </span>
        </TableCell>

        {/* Action (resource badge + action badge + description) */}
        <TableCell className="align-top">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              {parsed.resource && (
                <Badge
                  variant="outline"
                  className={`${resourceColor} border text-xs gap-1`}
                >
                  <ResourceIcon className="w-3 h-3" />
                  {RESOURCE_LABELS[parsed.resource] || parsed.resource}
                </Badge>
              )}
              <Badge
                variant="outline"
                className={`${actionColor} border text-xs`}
              >
                {getActionLabel(parsed.action)}
              </Badge>
            </div>
            <p className="text-sm text-dark-100">{description}</p>
          </div>
        </TableCell>

        {/* Details preview */}
        <TableCell className="align-top">
          {hasDetails ? (
            <div className="flex items-center gap-2">
              <div className="space-y-0.5 flex-1 min-w-0">
                {visibleDetails.slice(0, 2).map(([key, value]) => (
                  <div key={key} className="text-xs text-dark-300 truncate">
                    <span className="text-dark-400">{DETAIL_LABELS[key] || key}:</span>{' '}
                    <span className="text-dark-200">{formatDetailValue(key, value)}</span>
                  </div>
                ))}
                {visibleDetails.length > 2 && (
                  <span className="text-xs text-dark-500">
                    + ещё {visibleDetails.length - 2}
                  </span>
                )}
              </div>
              <ChevronDown
                className={`w-4 h-4 text-dark-400 shrink-0 transition-transform ${
                  expanded ? 'rotate-180' : ''
                }`}
              />
            </div>
          ) : (
            <span className="text-xs text-dark-500">—</span>
          )}
        </TableCell>

        {/* IP */}
        <TableCell className="text-dark-300 font-mono text-xs align-top">
          {item.ip_address || '—'}
        </TableCell>
      </TableRow>

      {/* Expanded details row */}
      {expanded && hasDetails && (
        <TableRow className="border-dark-700 bg-dark-900/50">
          <TableCell colSpan={5} className="py-3 px-6">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-2">
              {visibleDetails.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <p className="text-xs text-dark-400 mb-0.5">{DETAIL_LABELS[key] || key}</p>
                  <p className="text-sm text-dark-100 break-words">{formatDetailValue(key, value)}</p>
                </div>
              ))}
            </div>
            {item.resource_id && (
              <div className="mt-3 pt-2 border-t border-dark-700">
                <span className="text-xs text-dark-400">ID ресурса: </span>
                <span className="text-xs text-dark-200 font-mono">{item.resource_id}</span>
              </div>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── Mobile Card Component ────────────────────────────────────────

function MobileAuditCard({ item }: { item: AuditLogEntry }) {
  const parsed = parseAction(item.action)
  const ResourceIcon = RESOURCE_ICONS[parsed.resource] || FileText
  const resourceColor = RESOURCE_COLORS[parsed.resource] || 'bg-gray-500/20 text-gray-400'
  const actionColor = getActionColor(parsed.action)
  const details = tryParseJSON(item.details)
  const description = getDescription(parsed.resource, parsed.action, item.resource_id, details)
  const visibleDetails = getVisibleDetails(details)
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="p-3 rounded-lg bg-dark-900 border border-dark-700 space-y-2"
      onClick={visibleDetails.length > 0 ? () => setExpanded(!expanded) : undefined}
    >
      {/* Header: admin + time */}
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

      {/* Badges */}
      <div className="flex items-center gap-2 flex-wrap">
        {parsed.resource && (
          <Badge
            variant="outline"
            className={`${resourceColor} border text-xs gap-1`}
          >
            <ResourceIcon className="w-3 h-3" />
            {RESOURCE_LABELS[parsed.resource] || parsed.resource}
          </Badge>
        )}
        <Badge
          variant="outline"
          className={`${actionColor} border text-xs`}
        >
          {getActionLabel(parsed.action)}
        </Badge>
      </div>

      {/* Description */}
      <p className="text-sm text-dark-100">{description}</p>

      {/* Details preview */}
      {visibleDetails.length > 0 && (
        <div className="space-y-1">
          {(expanded ? visibleDetails : visibleDetails.slice(0, 2)).map(([key, value]) => (
            <div key={key} className="text-xs text-dark-300">
              <span className="text-dark-400">{DETAIL_LABELS[key] || key}:</span>{' '}
              <span className="text-dark-200">{formatDetailValue(key, value)}</span>
            </div>
          ))}
          {!expanded && visibleDetails.length > 2 && (
            <span className="text-xs text-dark-500">
              + ещё {visibleDetails.length - 2}...
            </span>
          )}
        </div>
      )}

      {/* Footer: IP + resource ID */}
      <div className="flex items-center justify-between pt-1 border-t border-dark-700/50">
        {item.ip_address && (
          <span className="text-xs text-muted-foreground font-mono">
            {item.ip_address}
          </span>
        )}
        {item.resource_id && (
          <span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
            ID: {item.resource_id}
          </span>
        )}
      </div>
    </div>
  )
}
