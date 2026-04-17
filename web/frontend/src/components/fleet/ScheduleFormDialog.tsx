import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Clock, Plus, Trash2, ShieldCheck, FileCode } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import {
  listScripts,
  createScheduledTask,
  updateScheduledTask,
  type ScheduledTask,
} from '@/api/fleet'

// Quick cron presets — covers the most common schedules
const CRON_PRESETS: Array<{ key: string; expr: string }> = [
  { key: 'every5m', expr: '*/5 * * * *' },
  { key: 'every15m', expr: '*/15 * * * *' },
  { key: 'everyHour', expr: '0 * * * *' },
  { key: 'every6h', expr: '0 */6 * * *' },
  { key: 'dailyMidnight', expr: '0 0 * * *' },
  { key: 'daily3am', expr: '0 3 * * *' },
  { key: 'weeklyMonday', expr: '0 0 * * 1' },
  { key: 'monthlyFirst', expr: '0 0 1 * *' },
]

// Standard 5-field cron validation: minute hour day month weekday
// Each field: *, */N, ranges a-b, lists a,b,c, or specific numbers
const CRON_RE = /^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$/
function isValidCron(expr: string): boolean {
  return CRON_RE.test(expr.trim())
}

interface FleetNodeOption {
  uuid: string
  name: string
}

interface ScheduleFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodes: FleetNodeOption[]
  existingTask?: ScheduledTask | null
}

export default function ScheduleFormDialog({
  open,
  onOpenChange,
  nodes,
  existingTask,
}: ScheduleFormDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const isEditing = Boolean(existingTask)

  // Form state
  const [scriptId, setScriptId] = useState<string>('')
  const [nodeUuid, setNodeUuid] = useState<string>('')
  const [cronExpression, setCronExpression] = useState<string>('0 3 * * *')
  const [isEnabled, setIsEnabled] = useState<boolean>(true)
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>([])

  // Reset/hydrate when opening
  useEffect(() => {
    if (!open) return
    if (existingTask) {
      setScriptId(String(existingTask.script_id))
      setNodeUuid(existingTask.node_uuid)
      setCronExpression(existingTask.cron_expression)
      setIsEnabled(existingTask.is_enabled)
      setEnvVars(
        existingTask.env_vars
          ? Object.entries(existingTask.env_vars).map(([key, value]) => ({ key, value }))
          : [],
      )
    } else {
      setScriptId('')
      setNodeUuid('')
      setCronExpression('0 3 * * *')
      setIsEnabled(true)
      setEnvVars([])
    }
  }, [open, existingTask])

  const { data: scripts = [] } = useQuery({
    queryKey: ['fleet-scripts-schedule'],
    queryFn: () => listScripts(),
    enabled: open,
    staleTime: 60_000,
  })

  const validCron = isValidCron(cronExpression)
  const canSubmit = scriptId && nodeUuid && validCron

  const createMutation = useMutation({
    mutationFn: () =>
      createScheduledTask({
        script_id: Number(scriptId),
        node_uuid: nodeUuid,
        cron_expression: cronExpression.trim(),
        is_enabled: isEnabled,
        env_vars: envVars.reduce<Record<string, string>>((acc, { key, value }) => {
          if (key.trim()) acc[key.trim()] = value
          return acc
        }, {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] })
      toast.success(t('fleet.scheduled.toast.created'))
      onOpenChange(false)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!existingTask) throw new Error('no task')
      return updateScheduledTask(existingTask.id, {
        cron_expression: cronExpression.trim(),
        is_enabled: isEnabled,
        env_vars: envVars.reduce<Record<string, string>>((acc, { key, value }) => {
          if (key.trim()) acc[key.trim()] = value
          return acc
        }, {}),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] })
      toast.success(t('fleet.scheduled.toast.updated'))
      onOpenChange(false)
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message)
    },
  })

  const pending = createMutation.isPending || updateMutation.isPending

  const handleAddEnvVar = () => setEnvVars((prev) => [...prev, { key: '', value: '' }])
  const handleUpdateEnvVar = (idx: number, field: 'key' | 'value', v: string) =>
    setEnvVars((prev) => prev.map((e, i) => (i === idx ? { ...e, [field]: v } : e)))
  const handleRemoveEnvVar = (idx: number) =>
    setEnvVars((prev) => prev.filter((_, i) => i !== idx))

  const humanPreview = useMemo(() => describeCron(cronExpression, t), [cronExpression, t])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? t('fleet.scheduled.edit') : t('fleet.scheduled.create')}
          </DialogTitle>
          <DialogDescription>{t('fleet.scheduled.formHint')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Script */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-dark-100">
              {t('fleet.scheduled.script')}
            </Label>
            <Select value={scriptId} onValueChange={setScriptId} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue placeholder={t('fleet.scheduled.scriptPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                {scripts.length === 0 && (
                  <div className="px-2 py-4 text-center text-xs text-muted-foreground">
                    {t('fleet.scheduled.noScripts')}
                  </div>
                )}
                {scripts.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    <div className="flex items-center gap-2">
                      <FileCode className="w-3.5 h-3.5 text-dark-300" />
                      <span>{s.display_name}</span>
                      {s.is_builtin && (
                        <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">
                          <ShieldCheck className="w-2.5 h-2.5 mr-0.5" />
                          {t('fleet.scheduled.builtin')}
                        </Badge>
                      )}
                      {s.requires_root && (
                        <span className="text-[10px] text-amber-400">root</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Node */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-dark-100">
              {t('fleet.scheduled.node')}
            </Label>
            <Select value={nodeUuid} onValueChange={setNodeUuid} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue placeholder={t('fleet.scheduled.nodePlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((n) => (
                  <SelectItem key={n.uuid} value={n.uuid}>
                    {n.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Cron presets */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-dark-100">
              {t('fleet.scheduled.preset')}
            </Label>
            <div className="grid grid-cols-2 gap-1.5">
              {CRON_PRESETS.map((p) => (
                <Button
                  key={p.expr}
                  type="button"
                  variant={cronExpression === p.expr ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCronExpression(p.expr)}
                  className="justify-start h-8 text-xs"
                >
                  <Clock className="w-3 h-3 mr-1.5" />
                  {t(`fleet.scheduled.presets.${p.key}`)}
                </Button>
              ))}
            </div>
          </div>

          {/* Cron expression input */}
          <div className="space-y-1.5">
            <Label htmlFor="cron-expr" className="text-xs font-medium text-dark-100">
              {t('fleet.scheduled.cron')}
            </Label>
            <Input
              id="cron-expr"
              value={cronExpression}
              onChange={(e) => setCronExpression(e.target.value)}
              placeholder="0 3 * * *"
              className={cn('font-mono', !validCron && cronExpression && 'border-red-500/50')}
            />
            <p
              className={cn(
                'text-[11px] leading-relaxed',
                validCron ? 'text-dark-200' : 'text-red-400',
              )}
            >
              {validCron
                ? humanPreview
                : t('fleet.scheduled.cronInvalid')}
            </p>
          </div>

          {/* Env vars */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-dark-100">
                {t('fleet.scheduled.envVars')}
              </Label>
              <Button type="button" size="sm" variant="ghost" onClick={handleAddEnvVar} className="h-7 gap-1">
                <Plus className="w-3 h-3" />
                <span className="text-xs">{t('fleet.scheduled.addEnv')}</span>
              </Button>
            </div>
            {envVars.length === 0 ? (
              <p className="text-[11px] text-dark-300">{t('fleet.scheduled.noEnvVars')}</p>
            ) : (
              <div className="space-y-1.5">
                {envVars.map((e, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <Input
                      placeholder="KEY"
                      value={e.key}
                      onChange={(ev) => handleUpdateEnvVar(i, 'key', ev.target.value)}
                      className="flex-1 h-8 text-xs font-mono"
                    />
                    <Input
                      placeholder="value"
                      value={e.value}
                      onChange={(ev) => handleUpdateEnvVar(i, 'value', ev.target.value)}
                      className="flex-1 h-8 text-xs font-mono"
                    />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      onClick={() => handleRemoveEnvVar(i)}
                      className="h-8 w-8 text-red-400"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Enabled toggle */}
          <div className="flex items-center justify-between rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)]/40 px-3 py-2">
            <div className="space-y-0.5">
              <Label htmlFor="task-enabled" className="text-xs font-medium text-dark-100 cursor-pointer">
                {t('fleet.scheduled.enable')}
              </Label>
              <p className="text-[11px] text-dark-300">{t('fleet.scheduled.enableHint')}</p>
            </div>
            <Switch id="task-enabled" checked={isEnabled} onCheckedChange={setIsEnabled} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => (isEditing ? updateMutation.mutate() : createMutation.mutate())}
            disabled={!canSubmit || pending}
          >
            {pending
              ? t('common.saving')
              : isEditing
                ? t('common.save')
                : t('fleet.scheduled.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Human-readable cron preview — covers the 8 presets and falls back to the raw expr
function describeCron(expr: string, t: (k: string, o?: Record<string, unknown>) => string): string {
  const match = CRON_PRESETS.find((p) => p.expr === expr.trim())
  if (match) return t(`fleet.scheduled.presets.${match.key}`)
  return t('fleet.scheduled.cronCustom', { expr: expr.trim() })
}
