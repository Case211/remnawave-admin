import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  AlertTriangle,
  CheckCircle2,
  Gauge,
  Info,
  Loader2,
  WifiOff,
  XCircle,
} from '@/components/brand/icons'
import { nodeShaperApi, type ShaperSettings, type ShaperState } from '@/api/nodeShaper'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useFormatters } from '@/lib/useFormatters'
import { cn } from '@/lib/utils'

/** Форма держит строки: поле можно стереть целиком, а число — нет. Скорости в Мбит/с. */
export interface ShaperForm {
  enabled: boolean
  ports: string
  down: string
  up: string
  penaltyEnabled: boolean
  penaltyMb: string
  penaltyWindow: string
  penaltyRate: string
  penaltyMinutes: string
}

export type ShaperFormError =
  | 'portsInvalid'
  | 'portsRequired'
  | 'ratesInvalid'
  | 'nothingToLimit'
  | 'penaltyInvalid'

const toMbit = (kbit: number) => String(kbit / 1000)
const toNumber = (value: string) => Number(value.trim().replace(',', '.'))

export function toForm(s: ShaperSettings): ShaperForm {
  return {
    enabled: s.enabled,
    ports: s.ports.join(', '),
    down: toMbit(s.down_kbit),
    up: toMbit(s.up_kbit),
    penaltyEnabled: s.penalty.enabled,
    penaltyMb: String(s.penalty.mb),
    penaltyWindow: String(s.penalty.window_sec),
    penaltyRate: toMbit(s.penalty.kbit),
    penaltyMinutes: String(s.penalty.minutes),
  }
}

/** «443, 8443» → [443, 8443]; null — есть не порт. */
export function parsePorts(value: string): number[] | null {
  const parts = value.split(/[\s,;]+/).filter(Boolean)
  const ports = parts.map(Number)
  if (ports.some((p) => !Number.isInteger(p) || p < 1 || p > 65535)) return null
  return [...new Set(ports)].sort((a, b) => a - b)
}

/** Проверка формы теми же правилами, что у панели и агента. */
export function toSettings(form: ShaperForm): { settings: ShaperSettings | null; error: ShaperFormError | null } {
  const ports = parsePorts(form.ports)
  if (ports === null) return { settings: null, error: 'portsInvalid' }
  if (form.enabled && ports.length === 0) return { settings: null, error: 'portsRequired' }

  const down = toNumber(form.down || '0')
  const up = toNumber(form.up || '0')
  if (![down, up].every((v) => Number.isFinite(v) && v >= 0)) {
    return { settings: null, error: 'ratesInvalid' }
  }

  const mb = toNumber(form.penaltyMb)
  const windowSec = toNumber(form.penaltyWindow)
  const rate = toNumber(form.penaltyRate)
  const minutes = toNumber(form.penaltyMinutes)
  const penaltyOk =
    Number.isInteger(mb) && mb >= 1 &&
    Number.isInteger(windowSec) && windowSec >= 10 &&
    Number.isFinite(rate) && rate * 1000 >= 64 &&
    Number.isInteger(minutes) && minutes >= 1
  if (form.penaltyEnabled && !penaltyOk) return { settings: null, error: 'penaltyInvalid' }

  if (form.enabled && down === 0 && up === 0 && !form.penaltyEnabled) {
    return { settings: null, error: 'nothingToLimit' }
  }

  return {
    settings: {
      enabled: form.enabled,
      ports,
      down_kbit: Math.round(down * 1000),
      up_kbit: Math.round(up * 1000),
      // Выключенный штраф хранит введённое, чтобы при включении не набирать заново
      penalty: penaltyOk
        ? { enabled: form.penaltyEnabled, mb, window_sec: windowSec, kbit: Math.round(rate * 1000), minutes }
        : { enabled: false, mb: 0, window_sec: 0, kbit: 0, minutes: 0 },
    },
    error: null,
  }
}

type Tone = 'ok' | 'warn' | 'error' | 'muted' | 'pending'

function describeStatus(state: ShaperState, t: (key: string, opts?: Record<string, unknown>) => string) {
  const { agent, status, settings, configured } = state
  let tone: Tone = 'muted'
  let text: string
  let detail: string | null = null

  if (!agent.connected) {
    text = t('nodes.shaper.status.offline')
  } else if (!agent.supported) {
    tone = 'warn'
    text = t('nodes.shaper.status.unsupported', {
      min: agent.min_version,
      version: agent.version || t('nodes.shaper.status.unknownVersion'),
    })
  } else if (!status) {
    if (configured && settings.enabled) {
      tone = 'pending'
      text = t('nodes.shaper.status.waiting')
    } else {
      text = t('nodes.shaper.status.off')
    }
  } else if (status.error) {
    tone = 'error'
    text = t('nodes.shaper.status.error', { error: status.error })
  } else if (status.active) {
    const kind = status.root?.split(':')[1] ?? ''
    if (status.download_exact === false) {
      tone = 'warn'
      text = t('nodes.shaper.status.activeRough', { kind })
    } else {
      tone = 'ok'
      text = t('nodes.shaper.status.active')
      if (status.root?.startsWith('installed:')) detail = t('nodes.shaper.status.rootInstalled', { kind })
      else if (status.root?.startsWith('kept:')) detail = t('nodes.shaper.status.rootKept', { kind })
    }
  } else {
    text = t('nodes.shaper.status.off')
    if (status.root === 'restored') detail = t('nodes.shaper.status.rootRestored')
  }
  return { tone, text, detail }
}

const TONE_STYLES: Record<Tone, string> = {
  ok: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  warn: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  error: 'border-red-500/30 bg-red-500/10 text-red-300',
  muted: 'border-[var(--glass-border)] bg-[var(--glass-bg)] text-dark-200',
  pending: 'border-primary-500/30 bg-primary-500/10 text-primary-300',
}

function StatusIcon({ tone, offline }: { tone: Tone; offline: boolean }) {
  const cls = 'w-4 h-4 mt-0.5 shrink-0'
  if (offline) return <WifiOff className={cls} />
  if (tone === 'ok') return <CheckCircle2 className={cls} />
  if (tone === 'warn') return <AlertTriangle className={cls} />
  if (tone === 'error') return <XCircle className={cls} />
  if (tone === 'pending') return <Loader2 className={cn(cls, 'animate-spin')} />
  return <Info className={cls} />
}

function apiErrorText(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string }
    if (first?.msg) return first.msg
  }
  return (err as Error)?.message || fallback
}

interface NodeShaperDialogProps {
  node: { uuid: string; name: string }
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Шейпер клиентов ноды: потолок скорости на каждый адрес и режим штрафа. */
export function NodeShaperDialog({ node, open, onOpenChange }: NodeShaperDialogProps) {
  const { t } = useTranslation()
  const { formatTimeAgo, formatBytes } = useFormatters()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ShaperForm | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [formError, setFormError] = useState<ShaperFormError | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['node-shaper', node.uuid],
    queryFn: () => nodeShaperApi.get(node.uuid),
    enabled: open,
    // Пока агент не ответил на сохранённые настройки — спрашиваем чаще
    refetchInterval: (query) => {
      const d = query.state.data
      return d && d.configured && d.agent.connected && !d.status ? 2000 : false
    },
  })

  // Форма заполняется один раз на открытие: опрос состояния не должен затирать ввод
  useEffect(() => {
    if (open && data && form === null) setForm(toForm(data.settings))
    if (!open) {
      setForm(null)
      setConfirming(false)
      setFormError(null)
    }
  }, [open, data, form])

  const save = useMutation({
    mutationFn: (settings: ShaperSettings) => nodeShaperApi.save(node.uuid, settings),
    onSuccess: (res) => {
      toast.success(res.pushed ? t('nodes.shaper.toast.saved') : t('nodes.shaper.toast.savedOffline'))
      setConfirming(false)
      queryClient.invalidateQueries({ queryKey: ['node-shaper', node.uuid] })
    },
    onError: (err) => toast.error(apiErrorText(err, t('common.error'))),
  })

  const update = (patch: Partial<ShaperForm>) => {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev))
    setFormError(null)
  }

  const submit = () => {
    if (!form || !data) return
    const { settings, error } = toSettings(form)
    if (!settings) {
      setFormError(error)
      return
    }
    // Включение меняет ноду — сначала показываем, что именно
    if (settings.enabled && !data.settings.enabled && !confirming) {
      setConfirming(true)
      return
    }
    save.mutate(settings)
  }

  const status = data ? describeStatus(data, t) : null
  const ports = form ? parsePorts(form.ports) : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Gauge className="w-5 h-5 text-primary-400" />
            {t('nodes.shaper.title')}
            <span className="text-dark-200 font-normal truncate">· {node.name}</span>
          </DialogTitle>
          <DialogDescription>{t('nodes.shaper.description')}</DialogDescription>
        </DialogHeader>

        {isLoading || !form ? (
          <div className="flex items-center justify-center py-10 text-dark-200">
            {isError ? t('common.error') : <Loader2 className="w-5 h-5 animate-spin" />}
          </div>
        ) : confirming ? (
          <div className="space-y-3 text-sm">
            <p className="text-white font-medium">{t('nodes.shaper.confirm.intro')}</p>
            <ul className="space-y-2 text-dark-100">
              {(['itemRoot', 'itemFilters', 'itemCaps', 'itemRevert'] as const).map((key) => (
                <li key={key} className="flex gap-2">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-400" />
                  <span>{t(`nodes.shaper.confirm.${key}`, { ports: (ports ?? []).join(', ') })}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="space-y-4">
            {status && data && (
              <div className={cn('rounded-lg border px-3 py-2.5 text-sm flex gap-2', TONE_STYLES[status.tone])}>
                <StatusIcon tone={status.tone} offline={!data.agent.connected} />
                <div className="min-w-0">
                  <p>{status.text}</p>
                  {status.detail && <p className="mt-0.5 text-xs opacity-80">{status.detail}</p>}
                  {data.updated_at && (
                    <p className="mt-0.5 text-xs opacity-60">
                      {t('nodes.shaper.status.updated', {
                        time: formatTimeAgo(data.updated_at),
                        who: data.updated_by || '—',
                      })}
                    </p>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="shaper-enabled" className="text-white">{t('nodes.shaper.enable')}</Label>
              <Switch
                id="shaper-enabled"
                checked={form.enabled}
                onCheckedChange={(v) => update({ enabled: v })}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="shaper-ports">{t('nodes.shaper.ports')}</Label>
              <Input
                id="shaper-ports"
                value={form.ports}
                onChange={(e) => update({ ports: e.target.value })}
                placeholder="443, 8443"
              />
              <p className="text-xs text-dark-200">{t('nodes.shaper.portsHint')}</p>
            </div>

            <div className="space-y-1.5">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="shaper-down">{t('nodes.shaper.down')}</Label>
                  <Input id="shaper-down" inputMode="decimal" value={form.down}
                    onChange={(e) => update({ down: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="shaper-up">{t('nodes.shaper.up')}</Label>
                  <Input id="shaper-up" inputMode="decimal" value={form.up}
                    onChange={(e) => update({ up: e.target.value })} />
                </div>
              </div>
              <p className="text-xs text-dark-200">{t('nodes.shaper.capsHint')}</p>
            </div>

            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Label htmlFor="shaper-penalty" className="text-white">{t('nodes.shaper.penalty')}</Label>
                  <p className="text-xs text-dark-200 mt-0.5">{t('nodes.shaper.penaltyHint')}</p>
                </div>
                <Switch
                  id="shaper-penalty"
                  checked={form.penaltyEnabled}
                  onCheckedChange={(v) => update({ penaltyEnabled: v })}
                />
              </div>
              {form.penaltyEnabled && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="shaper-pen-mb">{t('nodes.shaper.penaltyMb')}</Label>
                    <Input id="shaper-pen-mb" inputMode="numeric" value={form.penaltyMb}
                      onChange={(e) => update({ penaltyMb: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="shaper-pen-window">{t('nodes.shaper.penaltyWindow')}</Label>
                    <Input id="shaper-pen-window" inputMode="numeric" value={form.penaltyWindow}
                      onChange={(e) => update({ penaltyWindow: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="shaper-pen-rate">{t('nodes.shaper.penaltyRate')}</Label>
                    <Input id="shaper-pen-rate" inputMode="decimal" value={form.penaltyRate}
                      onChange={(e) => update({ penaltyRate: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="shaper-pen-minutes">{t('nodes.shaper.penaltyMinutes')}</Label>
                    <Input id="shaper-pen-minutes" inputMode="numeric" value={form.penaltyMinutes}
                      onChange={(e) => update({ penaltyMinutes: e.target.value })} />
                  </div>
                </div>
              )}
            </div>

            {!!data?.penalties?.length && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-dark-200 uppercase tracking-wider">
                  {t('nodes.shaper.penalties.title')}
                </p>
                <ul className="max-h-40 overflow-y-auto space-y-1 text-xs">
                  {data.penalties.map((p) => (
                    <li key={`${p.ip}-${p.started_at}`} className="flex items-center gap-2 text-dark-100">
                      <span className="text-white truncate">
                        {p.users.length
                          ? p.users.map((u) => u.username || u.uuid.slice(0, 8)).join(', ')
                          : t('nodes.shaper.penalties.unknownUser', { ip: p.ip })}
                      </span>
                      <span className="text-dark-200 shrink-0">{formatBytes(p.bytes)}</span>
                      <span className="text-dark-300 ml-auto shrink-0">{formatTimeAgo(p.started_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="space-y-1 text-xs text-dark-200">
              <p>{t('nodes.shaper.noteCgnat')}</p>
              <p>{t('nodes.shaper.noteCdn')}</p>
            </div>

            {formError && <p className="text-sm text-red-400">{t(`nodes.shaper.errors.${formError}`)}</p>}
          </div>
        )}

        <DialogFooter>
          {confirming ? (
            <>
              <Button variant="outline" onClick={() => setConfirming(false)} disabled={save.isPending}>
                {t('nodes.shaper.confirm.back')}
              </Button>
              <Button onClick={submit} disabled={save.isPending}>
                {save.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {t('nodes.shaper.confirm.confirm')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>{t('common.cancel')}</Button>
              <Button onClick={submit} disabled={!form || save.isPending}>
                {save.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {t('common.save')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
