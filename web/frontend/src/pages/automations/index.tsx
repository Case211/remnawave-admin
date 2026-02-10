import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus,
  Zap,
  Activity,
  Clock,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PermissionGate, useHasPermission } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { automationsApi, type AutomationRule, type AutomationTestResult } from '../../api/automations'
import { RuleCard } from './RuleCard'
import { RuleConstructor } from './RuleConstructor'
import { TemplatesGallery } from './TemplatesGallery'
import { LogsTimeline } from './LogsTimeline'
import { TestResultDialog } from './TestResultDialog'
import { CATEGORIES, formatDateTime } from './helpers'

export default function Automations() {
  const queryClient = useQueryClient()
  const canCreate = useHasPermission('automation', 'create')
  const canEdit = useHasPermission('automation', 'edit')
  const canDelete = useHasPermission('automation', 'delete')
  const canRun = useHasPermission('automation', 'run')

  // State
  const [page, setPage] = useState(1)
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [triggerFilter, setTriggerFilter] = useState<string>('')
  const [enabledFilter, setEnabledFilter] = useState<string>('')

  const [constructorOpen, setConstructorOpen] = useState(false)
  const [editRule, setEditRule] = useState<AutomationRule | null>(null)

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AutomationRule | null>(null)

  const [testResultOpen, setTestResultOpen] = useState(false)
  const [testResult, setTestResult] = useState<AutomationTestResult | null>(null)

  // Queries
  const { data, isLoading } = useQuery({
    queryKey: ['automations', page, categoryFilter, triggerFilter, enabledFilter],
    queryFn: () =>
      automationsApi.list({
        page,
        per_page: 18,
        category: categoryFilter || undefined,
        trigger_type: triggerFilter || undefined,
        is_enabled: enabledFilter === '' ? undefined : enabledFilter === 'true',
      }),
  })

  // Mutations
  const toggleMutation = useMutation({
    mutationFn: automationsApi.toggle,
    onSuccess: (rule) => {
      toast.success(`"${rule.name}" ${rule.is_enabled ? 'включено' : 'выключено'}`)
      queryClient.invalidateQueries({ queryKey: ['automations'] })
    },
    onError: () => toast.error('Не удалось переключить правило'),
  })

  const deleteMutation = useMutation({
    mutationFn: automationsApi.delete,
    onSuccess: () => {
      toast.success('Правило удалено')
      queryClient.invalidateQueries({ queryKey: ['automations'] })
      setDeleteDialogOpen(false)
      setDeleteTarget(null)
    },
    onError: () => toast.error('Не удалось удалить правило'),
  })

  const testMutation = useMutation({
    mutationFn: automationsApi.test,
    onSuccess: (result) => {
      setTestResult(result)
      setTestResultOpen(true)
    },
    onError: () => toast.error('Не удалось выполнить тест'),
  })

  // Handlers
  const handleEdit = (rule: AutomationRule) => {
    setEditRule(rule)
    setConstructorOpen(true)
  }

  const handleCreate = () => {
    setEditRule(null)
    setConstructorOpen(true)
  }

  const handleDeleteClick = (rule: AutomationRule) => {
    setDeleteTarget(rule)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = () => {
    if (deleteTarget) deleteMutation.mutate(deleteTarget.id)
  }

  // Stats
  const totalRules = data?.total ?? 0
  const activeRules = data?.items?.filter((r) => r.is_enabled).length ?? 0
  const lastTriggered = data?.items
    ?.filter((r) => r.last_triggered_at)
    ?.sort((a, b) =>
      new Date(b.last_triggered_at!).getTime() - new Date(a.last_triggered_at!).getTime()
    )?.[0]?.last_triggered_at ?? null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Automations</h1>
          <p className="text-sm text-dark-400 mt-1">
            Правила автоматизации для управления инфраструктурой
          </p>
        </div>
        <PermissionGate resource="automation" action="create">
          <Button
            onClick={handleCreate}
            className="bg-accent-teal text-white hover:bg-accent-teal/90"
          >
            <Plus className="w-4 h-4 mr-2" /> Новое правило
          </Button>
        </PermissionGate>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Всего правил" value={totalRules} icon={Zap} />
        <StatCard label="Активных" value={activeRules} icon={Activity} />
        <StatCard
          label="Всего триггеров"
          value={data?.items?.reduce((s, r) => s + r.trigger_count, 0) ?? 0}
          icon={Zap}
        />
        <StatCard
          label="Последний триггер"
          value={lastTriggered ? formatDateTime(lastTriggered) : '\u2014'}
          icon={Clock}
          isText
        />
      </div>

      {/* Tabs */}
      <Tabs defaultValue="rules" className="space-y-4">
        <TabsList className="bg-dark-800/50 border border-dark-700">
          <TabsTrigger value="rules">Правила</TabsTrigger>
          <TabsTrigger value="templates">Шаблоны</TabsTrigger>
          <TabsTrigger value="logs">Логи</TabsTrigger>
        </TabsList>

        {/* Rules tab */}
        <TabsContent value="rules" className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={categoryFilter}
              onValueChange={(v) => { setCategoryFilter(v === 'all' ? '' : v); setPage(1) }}
            >
              <SelectTrigger className="w-40 h-8 text-xs bg-dark-800 border-dark-700">
                <SelectValue placeholder="Категория" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все категории</SelectItem>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={triggerFilter}
              onValueChange={(v) => { setTriggerFilter(v === 'all' ? '' : v); setPage(1) }}
            >
              <SelectTrigger className="w-36 h-8 text-xs bg-dark-800 border-dark-700">
                <SelectValue placeholder="Триггер" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все триггеры</SelectItem>
                <SelectItem value="event">Событие</SelectItem>
                <SelectItem value="schedule">Расписание</SelectItem>
                <SelectItem value="threshold">Порог</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={enabledFilter}
              onValueChange={(v) => { setEnabledFilter(v === 'all' ? '' : v); setPage(1) }}
            >
              <SelectTrigger className="w-32 h-8 text-xs bg-dark-800 border-dark-700">
                <SelectValue placeholder="Статус" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все</SelectItem>
                <SelectItem value="true">Активные</SelectItem>
                <SelectItem value="false">Выключенные</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Rules grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-48 bg-dark-800" />
              ))}
            </div>
          ) : !data?.items?.length ? (
            <div className="text-center py-16">
              <Zap className="w-12 h-12 text-dark-600 mx-auto mb-4" />
              <p className="text-dark-400">Нет правил автоматизации</p>
              {canCreate && (
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={handleCreate}
                >
                  <Plus className="w-4 h-4 mr-2" /> Создать первое правило
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {data.items.map((rule) => (
                  <RuleCard
                    key={rule.id}
                    rule={rule}
                    canEdit={canEdit}
                    canDelete={canDelete}
                    canRun={canRun}
                    onToggle={(id) => toggleMutation.mutate(id)}
                    onEdit={handleEdit}
                    onDelete={handleDeleteClick}
                    onTest={(id) => testMutation.mutate(id)}
                    toggleLoading={toggleMutation.isPending}
                  />
                ))}
              </div>

              {/* Pagination */}
              {data.pages > 1 && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-dark-400">
                    Стр. {data.page} из {data.pages} ({data.total} правил)
                  </span>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                      disabled={page >= data.pages}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* Templates tab */}
        <TabsContent value="templates">
          <TemplatesGallery canCreate={canCreate} />
        </TabsContent>

        {/* Logs tab */}
        <TabsContent value="logs">
          <LogsTimeline />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <RuleConstructor
        open={constructorOpen}
        onOpenChange={setConstructorOpen}
        editRule={editRule}
      />

      <TestResultDialog
        open={testResultOpen}
        onOpenChange={setTestResultOpen}
        result={testResult}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Удалить правило?"
        description={`Правило "${deleteTarget?.name}" и все его логи будут удалены.`}
        confirmLabel="Удалить"
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  )
}

// ── StatCard helper ─────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  isText = false,
}: {
  label: string
  value: number | string
  icon: React.ElementType
  isText?: boolean
}) {
  return (
    <div className="p-4 rounded-xl bg-dark-800/50 border border-dark-700">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4 text-dark-400" />
        <span className="text-xs text-dark-400">{label}</span>
      </div>
      <p className={`${isText ? 'text-sm' : 'text-2xl'} font-semibold text-white`}>
        {value}
      </p>
    </div>
  )
}
