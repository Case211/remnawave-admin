/**
 * BS-Check — проверка через операторов РФ (bschekbot/bsbord).
 *
 * Три инструмента (вкладки):
 *   • Ноды — проба реального IP ноды (agent_ip, не туннель NetBird); клик по
 *     проверенной ноде показывает историю проверок.
 *   • Проверка IP — до 10 произвольных целей или скан всей /24 (async-поллинг).
 *   • Тест конфига — прогон VLESS/Reality ссылок/подписки через операторов.
 *
 * Всё платное (кредиты bsbord): для пробы/скана есть «Узнать цену» (preview),
 * vless-тест списывает при запуске (кнопка помечена «платно»). Операторы
 * показываются брендовыми бейджами с человеческими именами и регионом.
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient, UseQueryResult } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  bscheckApi, BsOperator, BsSummary, BsTargetSummary, BsNode, BsCheckRecord, BsHistoryRow, BsJob,
} from '@/api/bscheck'
import { usePermissionStore } from '@/store/permissionStore'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  ShieldCheck, RefreshCw, Loader2, Check, X, Key, History,
  Crosshair, Network, FileCode, Gauge, Wifi, AlertTriangle,
  Clock, Plus, Pencil, Trash2, ChevronRight, ShieldAlert,
} from '@/components/brand/icons'
import { cn } from '@/lib/utils'
import ReputationTab, { RepCard } from '@/components/bscheck/ReputationTab'
import { reputationApi } from '@/api/reputation'

// ── Бренды операторов (цвет = фон бейджа, fg = текст) ─────────────

const OP_BRAND: Record<string, { bg: string; fg: string }> = {
  mts: { bg: '#E30611', fg: '#ffffff' },
  beeline: { bg: '#FFCC00', fg: '#1a1a1a' },
  megafon: { bg: '#00B956', fg: '#ffffff' },
  tele2: { bg: '#1F1A4D', fg: '#5AC8FA' },
  t2: { bg: '#1F1A4D', fg: '#5AC8FA' },
  yota: { bg: '#00B6FF', fg: '#0a0a0a' },
  't-mobile': { bg: '#E20074', fg: '#ffffff' },
  tmobile: { bg: '#E20074', fg: '#ffffff' },
  tinkoff: { bg: '#FFDD2D', fg: '#1a1a1a' },
  'tinkoff-mobile': { bg: '#FFDD2D', fg: '#1a1a1a' },
  sber: { bg: '#21A038', fg: '#ffffff' },
  sbermobile: { bg: '#21A038', fg: '#ffffff' },
  rostelecom: { bg: '#7700FF', fg: '#ffffff' },
  motiv: { bg: '#FF6600', fg: '#ffffff' },
  gpn: { bg: '#004C97', fg: '#ffffff' },
  gazprom: { bg: '#004C97', fg: '#ffffff' },
  megaf2: { bg: '#00B956', fg: '#ffffff' },
}

function opBrand(id: string): { bg: string; fg: string } {
  return OP_BRAND[(id || '').toLowerCase()] || { bg: 'rgba(148,163,184,0.25)', fg: '#e2e8f0' }
}

/** Разбор op_key без справочника операторов.
 *
 *  Контракт 1.1: "оператор|округ|бс" ("mts|цфо|on"). До него ключ выглядел как
 *  "воркер:оператор" ("dfo1:beeline") — такие лежат в журнале проверок и должны
 *  читаться дальше, поэтому поддерживаются оба вида. */
function parseOpKey(opKey: string): { operator: string; region: string; dpi: string | null } {
  if (opKey.includes('|')) {
    const [operator = '', region = '', dpi = ''] = opKey.split('|')
    const clean = (v: string) => (v === '*' ? '' : v)
    return { operator: clean(operator), region: clean(region), dpi: clean(dpi) || null }
  }
  if (opKey.includes(':')) {
    const [worker = '', operator = ''] = opKey.split(':')
    return { operator: operator || worker, region: operator ? worker : '', dpi: null }
  }
  return { operator: opKey, region: '', dpi: null }
}

/** op_key → человекочитаемые имя/регион/бренд, через список операторов. */
function resolveOp(opKey: string, operators: BsOperator[]) {
  const found = operators.find((o) => o.op_key === opKey)
  const parsed = parseOpKey(opKey)
  return {
    id: (found?.operator || found?.id || parsed.operator || opKey).toLowerCase(),
    name: found?.name || (parsed.operator || opKey).toUpperCase(),
    region: found?.region || found?.region_label || parsed.region,
    dpi: found?.dpi ?? parsed.dpi,
    channel_state: found?.channel_state ?? null,
  }
}

function OperatorTag({ opKey, operators, region = true }: {
  opKey: string; operators: BsOperator[]; region?: boolean
}) {
  const info = resolveOp(opKey, operators)
  const b = opBrand(info.id)
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold leading-none"
        style={{ backgroundColor: b.bg, color: b.fg }}>{info.name}</span>
      {region && info.region && <span className="text-[10px] text-muted-foreground">{info.region}</span>}
    </span>
  )
}

// ── Конфиг пробы (общий для нод/IP/скана) ────────────────────────

interface Cfg {
  probes: Record<string, boolean>
  dpi: string
  sni: string
  ops: string[]
}

const DEFAULT_CFG: Cfg = { probes: { icmp: true, tcp: true, sni: false }, dpi: 'on', sni: '', ops: [] }

function cfgFields(c: Cfg) {
  return {
    operators: c.ops,
    probes: c.probes,
    sni_hosts: c.probes.sni && c.sni.trim()
      ? c.sni.split(',').map((s) => s.trim()).filter(Boolean) : [],
    dpi: c.dpi,
  }
}

/** Живой набор op_key единиц, у которых БС сейчас выключен.
 *  Контракт 1.1 отдаёт это отдельным полем dpi; channel_state остаётся
 *  запасным признаком для ответов, снятых раньше. */
function offKeySet(operators: BsOperator[]): Set<string> {
  return new Set(operators
    .filter((o) => o.dpi === 'off' || (!o.dpi && o.channel_state === 'DPI_OFF'))
    .map((o) => o.op_key))
}

/** Единицы с включённым БС — нужны, чтобы гасить их в режиме «только без БС». */
function onKeySet(operators: BsOperator[]): Set<string> {
  return new Set(operators
    .filter((o) => o.dpi === 'on' || (!o.dpi && o.channel_state === 'DPI_ON'))
    .map((o) => o.op_key))
}

/** Единицы, недоступные выбору при текущем режиме фильтра. */
function lockedKeys(dpi: string, operators: BsOperator[]): Set<string> {
  if (dpi === 'on') return offKeySet(operators)
  if (dpi === 'off') return onKeySet(operators)
  return new Set()
}

const DPI_MODES = ['on', 'any', 'off'] as const

/** Режим фильтра единиц по белому списку: только с БС / любые / только без БС.
 *  Раньше был двухпозиционный переключатель — режима «только без БС» в API
 *  не существовало до контракта 1.1. */
function BsDpiSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1 rounded-md border border-border/60 p-0.5">
      {DPI_MODES.map((mode) => (
        <button key={mode} type="button" onClick={() => onChange(mode)}
          className={cn('px-2 py-1 text-[11px] rounded transition-colors',
            value === mode ? 'bg-primary/20 text-primary-200' : 'text-muted-foreground hover:text-foreground')}>
          {mode === 'on' && <ShieldCheck className="w-3 h-3 inline mr-1" />}
          {t(`bscheck.dpiShort.${mode}`)}
        </button>
      ))}
    </div>
  )
}

function ProbeConfig({ cfg, onChange, operators, showOperators = true }: {
  cfg: Cfg; onChange: (c: Cfg) => void; operators: BsOperator[]; showOperators?: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const set = (patch: Partial<Cfg>) => onChange({ ...cfg, ...patch })
  const locked = cfg.dpi === 'on'
  const offKeys = offKeySet(operators)
  const offCount = offKeys.size
  // смена режима гасит из выбора единицы, которые под него не подходят,
  // иначе запрос уедет с набором, где всё уйдёт в skipped_dpi_off
  const setDpiMode = (v: string) =>
    set({ dpi: v, ops: cfg.ops.filter((k) => !lockedKeys(v, operators).has(k)) })
  const toggleOp = (op: string) => set({
    ops: cfg.ops.includes(op) ? cfg.ops.filter((x) => x !== op) : [...cfg.ops, op],
  })
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        {(['icmp', 'tcp', 'sni'] as const).map((p) => (
          <label key={p} className="flex items-center gap-2 text-sm cursor-pointer">
            <Switch checked={cfg.probes[p]} onCheckedChange={(v) => set({ probes: { ...cfg.probes, [p]: v } })} />
            {p.toUpperCase()}
          </label>
        ))}
        <div className="ml-auto"><BsDpiSelect value={cfg.dpi} onChange={setDpiMode} /></div>
      </div>
      <p className={cn('text-[11px]', locked ? 'text-muted-foreground' : 'text-amber-400')}>
        {locked ? t('bscheck.lockBsHint') : t(cfg.dpi === 'off' ? 'bscheck.bsOffWarn' : 'bscheck.bsAnyWarn')}
      </p>

      {cfg.probes.sni && (
        <div>
          <Label>{t('bscheck.sniHosts')}</Label>
          <Input value={cfg.sni} className="mt-1 font-mono" placeholder="example.com, www.microsoft.com"
            onChange={(e) => set({ sni: e.target.value })} />
        </div>
      )}

      {showOperators && operators.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-2">
            <Label>{t('bscheck.operators')}</Label>
            <div className="flex items-center gap-2">
              {offCount > 0 && <span className="text-[11px] text-amber-400">{t('bscheck.bsOffCount', { count: offCount })}</span>}
              <Button type="button" variant="ghost" size="sm" className="h-6 gap-1 text-[11px]"
                onClick={() => qc.invalidateQueries({ queryKey: ['bscheck-operators'] })}>
                <RefreshCw className="w-3 h-3" />{t('bscheck.refreshOps')}
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mt-1">
            {operators.map((op) => {
              const b = opBrand(op.id)
              const sel = cfg.ops.includes(op.op_key)
              const isOff = op.channel_state === 'DPI_OFF'
              const disabled = lockedKeys(cfg.dpi, operators).has(op.op_key)
              return (
                <button key={op.op_key} type="button" disabled={disabled}
                  onClick={() => !disabled && toggleOp(op.op_key)}
                  className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                    sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200'
                      : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                    disabled && 'opacity-40 cursor-not-allowed hover:text-muted-foreground')}
                  title={`${op.op_key} · ${op.channel_state}${op.region_label ? ' · ' + op.region_label : ''}`}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.bg }} />
                  {op.name}
                  {op.region_label && <span className="text-muted-foreground">· {op.region_label}</span>}
                  {isOff && <span className="text-amber-400">· {t('bscheck.bsOff')}</span>}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.operatorsHint')}</p>
        </div>
      )}
    </div>
  )
}

// ── Результаты пробы (общий рендер) ──────────────────────────────

function channelLabel(state: string | null | undefined, t: (k: string) => string): string {
  if (state === 'DPI_ON') return t('bscheck.chDpiOn')
  if (state === 'DPI_OFF') return t('bscheck.chDpiOff')
  return state || ''
}

function passClass(passed: number, total: number): string {
  if (total === 0) return 'text-muted-foreground'
  if (passed === total) return 'text-green-400'
  if (passed === 0) return 'text-red-400'
  return 'text-amber-400'
}

function OperatorResults({ summary, operators, title }: {
  summary: BsSummary; operators: BsOperator[]; title?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
      <div className="px-3 py-2 text-xs flex items-center justify-between gap-2">
        <span className="truncate">
          {title && <span className="font-mono text-muted-foreground mr-2">{title}</span>}
          {t('bscheck.passed')}: <b className={passClass(summary.passed, summary.total)}>{summary.passed}/{summary.total}</b>
        </span>
        {summary.cost_credits != null && <span className="text-muted-foreground shrink-0">◈ {summary.cost_credits}</span>}
      </div>
      {(summary.operators || []).map((o) => (
        <div key={o.op} className="px-3 py-1.5 flex items-center gap-2 text-xs">
          {o.ok ? <Check className="w-4 h-4 text-green-400 shrink-0" /> : <X className="w-4 h-4 text-red-400 shrink-0" />}
          <OperatorTag opKey={o.op} operators={operators} />
          {o.channel_state && (
            <Badge variant="outline" className={cn('text-[9px]', o.channel_state === 'DPI_OFF' && 'text-amber-300 border-amber-500/40')}>
              {channelLabel(o.channel_state, t)}
            </Badge>
          )}
          {o.latency_ms != null && <span className="ml-auto text-muted-foreground tabular-nums shrink-0">{o.latency_ms} ms</span>}
          {o.error && <span className="text-red-300 truncate">{o.error}</span>}
        </div>
      ))}
      {(summary.skipped_dpi_off?.length ?? 0) > 0 && (
        <div className="px-3 py-1.5 text-[11px] text-amber-300">
          {t('bscheck.skippedDpiOff')}: {summary.skipped_dpi_off.join(', ')}
        </div>
      )}
    </div>
  )
}

/** Клиентская сводка by_operator → BsSummary (для скана/произвольных ответов). */
function sumByOp(byOp: Record<string, any>): BsSummary {
  const ops = Object.entries(byOp || {}).map(([op, leg]: [string, any]) => ({
    op, ok: !!leg?.ok, channel_state: leg?.channel_state ?? null,
    latency_ms: leg?.latency_ms ?? null, tcp_is_tls: leg?.tcp_is_tls ?? null,
    error: leg?.error || null,
  })).sort((a, b) => a.op.localeCompare(b.op))
  return { passed: ops.filter((o) => o.ok).length, total: ops.length, operators: ops, cost_credits: null, skipped_dpi_off: [] }
}

// ── Хелперы UI ───────────────────────────────────────────────────

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return iso.slice(0, 16).replace('T', ' ')
}

function useErrToast() {
  const { t } = useTranslation()
  return (e: any) => toast.error(e?.response?.data?.detail || t('common.error'))
}

/** Записать результат ad-hoc проверки в общий журнал (тихо, без тостов). */
function useSaveHistory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: Parameters<typeof bscheckApi.saveHistory>[0]) => bscheckApi.saveHistory(p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bscheck-history'] }),
  })
}

function kindLabel(kind: string, t: (k: string, opts?: Record<string, unknown>) => string): string {
  return t(`bscheck.kind_${kind}`, { defaultValue: kind })
}

function ResultBadge({ passed, total }: { passed: number; total: number }) {
  return (
    <Badge className={cn('text-[10px] gap-1',
      total > 0 && passed === total ? 'bg-green-500/20 text-green-300'
        : passed === 0 ? 'bg-red-500/20 text-red-300'
          : 'bg-amber-500/20 text-amber-300')}>
      {passed}/{total}
    </Badge>
  )
}

function PollStatus({ state, kind }: { state?: string; kind: 'scan' | 'vless' }) {
  const { t } = useTranslation()
  const running = !state || ['running', 'queued', 'pending', 'processing'].includes(state)
  const failed = ['failed', 'error', 'cancelled'].includes(state || '')
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      {running ? <Loader2 className="w-4 h-4 animate-spin" />
        : failed ? <X className="w-4 h-4 text-red-400" /> : <Check className="w-4 h-4 text-green-400" />}
      {running ? t(kind === 'scan' ? 'bscheck.scanRunning' : 'bscheck.vlessRunning')
        : failed ? t('bscheck.statusFailed') : t('bscheck.statusDone')}
    </div>
  )
}

// ── Страница ─────────────────────────────────────────────────────

export default function BsCheck() {
  const { t } = useTranslation()
  const { data: status, isLoading } = useQuery({ queryKey: ['bscheck-status'], queryFn: bscheckApi.status })

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-primary-400" />
        <h1 className="text-lg font-semibold">{t('bscheck.title')}</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-2">{t('bscheck.subtitle')}</p>

      {isLoading ? <Skeleton className="h-64 w-full" />
        : !status?.configured ? <TokenSetup />
          : <Shell account={status.account} />}
    </div>
  )
}

// ── Подключение токена ───────────────────────────────────────────

function TokenSetup({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [token, setToken] = useState('')

  const save = useMutation({
    mutationFn: () => bscheckApi.setToken(token.trim()),
    onSuccess: () => {
      toast.success(t('bscheck.tokenSaved'))
      qc.invalidateQueries({ queryKey: ['bscheck-status'] })
      setToken(''); onDone?.()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('bscheck.tokenInvalid')),
  })

  return (
    <Card className="p-5 max-w-xl space-y-3">
      <div className="flex items-center gap-2"><Key className="w-4 h-4 text-primary-400" />
        <h2 className="text-sm font-medium">{t('bscheck.connectTitle')}</h2></div>
      <p className="text-xs text-muted-foreground">{t('bscheck.connectHint')}</p>
      <div>
        <Label htmlFor="bs-token">{t('bscheck.tokenLabel')}</Label>
        <Input id="bs-token" type="password" value={token} className="mt-1 font-mono"
          placeholder="bsk_live_…" disabled={!canCheck}
          onChange={(e) => setToken(e.target.value)} />
      </div>
      <div className="flex justify-end">
        <Button onClick={() => save.mutate()} disabled={!canCheck || token.trim().length < 10 || save.isPending}>
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.connect')}
        </Button>
      </div>
    </Card>
  )
}

// ── Каркас: баланс + вкладки ─────────────────────────────────────

function Shell({ account }: { account: { balance_credits?: number; balance_total?: number; tier?: string } | null }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tokenOpen, setTokenOpen] = useState(false)
  const { data: operators } = useQuery({ queryKey: ['bscheck-operators'], queryFn: bscheckApi.operators })
  const ops = operators || []

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-primary-500/15 text-primary-300 gap-1.5">
          {t('bscheck.balance')}: <b>◈ {account?.balance_total ?? account?.balance_credits ?? '—'}</b>
          {account?.tier && <span className="text-muted-foreground">· {account.tier}</span>}
        </Badge>
        <Button variant="outline" size="sm" className="gap-1.5"
          onClick={() => {
            qc.invalidateQueries({ queryKey: ['bscheck-status'] })
            qc.invalidateQueries({ queryKey: ['bscheck-summary'] })
            qc.invalidateQueries({ queryKey: ['bscheck-operators'] })
          }}>
          <RefreshCw className="w-4 h-4" /> {t('common.refresh')}
        </Button>
        <Button variant="outline" size="sm" className="ml-auto gap-1.5" onClick={() => setTokenOpen(true)}>
          <Key className="w-4 h-4" /> {t('bscheck.tokenChange')}
        </Button>
      </div>

      <Tabs defaultValue="nodes">
        <TabsList>
          <TabsTrigger value="nodes" className="gap-1.5"><ShieldCheck className="w-4 h-4" />{t('bscheck.tabsNodes')}</TabsTrigger>
          <TabsTrigger value="ip" className="gap-1.5"><Crosshair className="w-4 h-4" />{t('bscheck.tabsIp')}</TabsTrigger>
          <TabsTrigger value="config" className="gap-1.5"><FileCode className="w-4 h-4" />{t('bscheck.tabsConfig')}</TabsTrigger>
          <TabsTrigger value="reputation" className="gap-1.5"><ShieldAlert className="w-4 h-4" />{t('bscheck.tabsReputation')}</TabsTrigger>
          <TabsTrigger value="schedule" className="gap-1.5"><Clock className="w-4 h-4" />{t('bscheck.tabsSchedule')}</TabsTrigger>
          <TabsTrigger value="history" className="gap-1.5"><History className="w-4 h-4" />{t('bscheck.tabsHistory')}</TabsTrigger>
        </TabsList>
        <TabsContent value="nodes"><NodesTab operators={ops} /></TabsContent>
        <TabsContent value="ip"><IpTab operators={ops} /></TabsContent>
        <TabsContent value="config"><ConfigTab operators={ops} /></TabsContent>
        <TabsContent value="reputation"><ReputationTab /></TabsContent>
        <TabsContent value="schedule"><ScheduleTab operators={ops} /></TabsContent>
        <TabsContent value="history"><HistoryTab operators={ops} /></TabsContent>
      </Tabs>

      <Dialog open={tokenOpen} onOpenChange={(o) => !o && setTokenOpen(false)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle className="text-base">{t('bscheck.tokenChange')}</DialogTitle></DialogHeader>
          <TokenSetup onDone={() => setTokenOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Вкладка «Расписание» (сохранённые авто-тесты) ────────────────

function jobTargetSummary(job: BsJob, t: (k: string, o?: Record<string, unknown>) => string): string {
  const c = job.config || {}
  if (job.kind === 'node') return c.nodes?.length ? t('bscheck.jobNodesN', { n: c.nodes.length }) : t('bscheck.jobAllNodes')
  if (job.kind === 'probe') return (c.targets || []).join(', ') || '—'
  if (job.kind === 'scan') return c.cidr || '—'
  if (job.kind === 'vless') return t('bscheck.jobLinksN', { n: String(c.raw_input || '').split(/\s+/).filter(Boolean).length })
  if (job.kind === 'reputation') {
    const n = (c.nodes?.length || 0) + (c.targets?.length || 0)
    const p = (c.providers || []).length
    const who = n ? t('bscheck.jobTargetsN', { n }) : t('bscheck.jobAllNodes')
    return p ? `${who} · ${p} пров.` : who
  }
  return '—'
}

function ScheduleTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const onErr = useErrToast()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const { data, isLoading } = useQuery({ queryKey: ['bscheck-jobs'], queryFn: bscheckApi.jobs })
  const { data: nodesData } = useQuery({ queryKey: ['bscheck-nodes'], queryFn: bscheckApi.nodes })
  const [editing, setEditing] = useState<BsJob | 'new' | null>(null)
  const [confirmDel, setConfirmDel] = useState<number | null>(null)
  const jobs = data || []
  const nodes = nodesData || []

  const toggle = useMutation({
    mutationFn: ({ job, enabled }: { job: BsJob; enabled: boolean }) => bscheckApi.updateJob(job.id, {
      name: job.name, kind: job.kind, enabled, interval_minutes: job.interval_minutes,
      config: job.config, budget_daily: job.budget_daily, alert: job.alert,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bscheck-jobs'] }), onError: onErr,
  })
  const del = useMutation({
    mutationFn: (id: number) => bscheckApi.deleteJob(id),
    onSuccess: () => { toast.success(t('bscheck.jobDeleted')); qc.invalidateQueries({ queryKey: ['bscheck-jobs'] }) },
    onError: onErr,
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-amber-400">{t('bscheck.autoWarn')}</p>
        {canCheck && (
          <Button size="sm" className="gap-1.5 shrink-0" onClick={() => setEditing('new')}>
            <Plus className="w-4 h-4" />{t('bscheck.jobNew')}
          </Button>
        )}
      </div>

      {isLoading ? <Skeleton className="h-24 w-full" />
        : !jobs.length ? <Card className="p-6 text-center text-sm text-muted-foreground">{t('bscheck.jobsEmpty')}</Card>
          : jobs.map((job) => (
            <Card key={job.id} className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Switch checked={job.enabled} disabled={!canCheck} onCheckedChange={(v) => toggle.mutate({ job, enabled: v })} />
                <span className="font-medium text-sm">{job.name}</span>
                <Badge variant="outline" className="text-[10px]">{kindLabel(job.kind, t)}</Badge>
                <span className="text-[11px] text-muted-foreground">{t('bscheck.jobEvery', { m: job.interval_minutes })}</span>
                {job.budget_daily > 0 && <span className="text-[11px] text-muted-foreground">≤ {job.budget_daily} ◈</span>}
                <span className="ml-auto text-[11px] text-muted-foreground">{job.last_run_at ? fmtDate(job.last_run_at) : t('bscheck.autoNever')}</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[11px] font-mono text-muted-foreground truncate flex-1">{jobTargetSummary(job, t)}</span>
                {canCheck && (
                  <>
                    <Button size="sm" variant="outline" className="gap-1.5 min-h-[36px]" onClick={() => { setEditing(job); setConfirmDel(null) }}>
                      <Pencil className="w-3.5 h-3.5" /> {t('bscheck.jobEdit')}
                    </Button>
                    <Button size="sm" variant="outline"
                      className={cn('gap-1.5 min-h-[36px]', confirmDel === job.id ? 'bg-red-600 text-white hover:bg-red-500' : 'text-red-400 hover:text-red-300')}
                      onClick={() => { if (confirmDel === job.id) { del.mutate(job.id); setConfirmDel(null) } else setConfirmDel(job.id) }}>
                      <Trash2 className="w-3.5 h-3.5" /> {confirmDel === job.id ? t('bscheck.jobConfirmDel') : t('common.delete')}
                    </Button>
                  </>
                )}
              </div>
            </Card>
          ))}

      {editing && (
        <JobDialog job={editing === 'new' ? null : editing} operators={operators} nodes={nodes}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); qc.invalidateQueries({ queryKey: ['bscheck-jobs'] }) }} />
      )}
    </div>
  )
}

function JobDialog({ job, operators, nodes, onClose, onSaved }: {
  job: BsJob | null; operators: BsOperator[]; nodes: BsNode[]; onClose: () => void; onSaved: () => void
}) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const c = job?.config || {}
  const [name, setName] = useState(job?.name || '')
  const [kind, setKind] = useState(job?.kind || 'node')
  const [enabled, setEnabled] = useState(job?.enabled ?? true)
  const [intervalMin, setIntervalMin] = useState(job?.interval_minutes || 360)
  const [budget, setBudget] = useState(job?.budget_daily || 0)
  const [alert, setAlert] = useState(job?.alert ?? true)
  const [dpi, setDpi] = useState<string>(c.dpi || 'on')
  const [ops, setOps] = useState<string[]>(c.operators || [])
  const [selNodes, setSelNodes] = useState<string[]>(c.nodes || [])
  const [targets, setTargets] = useState<string>((c.targets || []).join('\n'))
  const [cidr, setCidr] = useState<string>(c.cidr || '')
  const [raw, setRaw] = useState<string>(c.raw_input || '')
  const [repProviders, setRepProviders] = useState<string[]>(c.providers || [])
  const [batch, setBatch] = useState<number>(c.batch || 0)
  const { data: repProvs } = useQuery({ queryKey: ['rep-providers'], queryFn: reputationApi.providers, enabled: kind === 'reputation' })

  const validScan = /^\d{1,3}(\.\d{1,3}){3}\/24$/.test(cidr.trim())
  const canSave = !!name.trim()
    && (kind !== 'scan' || validScan)
    && (kind !== 'vless' || !!raw.trim())
    && (kind !== 'probe' || !!targets.trim())

  const buildConfig = () => {
    if (kind === 'reputation') {
      return {
        nodes: selNodes,
        targets: targets.split(/[\n,]/).map((s) => s.trim()).filter(Boolean),
        providers: repProviders, batch: Number(batch) || 0,
      }
    }
    const base: any = { dpi, operators: ops }
    if (kind === 'node') base.nodes = selNodes
    if (kind === 'probe') base.targets = targets.split(/[\n,]/).map((s) => s.trim()).filter(Boolean).slice(0, 10)
    if (kind === 'scan') { const m = cidr.trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}\/24$/); base.cidr = m ? `${m[1]}.${m[2]}.${m[3]}.0/24` : cidr.trim() }
    if (kind === 'vless') base.raw_input = raw
    return base
  }

  const save = useMutation({
    mutationFn: () => {
      const payload = { name: name.trim(), kind, enabled, interval_minutes: intervalMin, config: buildConfig(), budget_daily: budget, alert }
      return job ? bscheckApi.updateJob(job.id, payload) : bscheckApi.createJob(payload)
    },
    onSuccess: () => { toast.success(t('bscheck.jobSaved')); onSaved() },
    onError: onErr,
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="text-base">{job ? t('bscheck.jobEdit') : t('bscheck.jobNew')}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3">
            <div className="flex-1 min-w-[180px]">
              <Label>{t('bscheck.jobName')}</Label>
              <Input value={name} className="mt-1" onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="w-40">
              <Label>{t('bscheck.jobKind')}</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger className="mt-1 h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="node">{t('bscheck.kind_node')}</SelectItem>
                  <SelectItem value="probe">{t('bscheck.kind_probe')}</SelectItem>
                  <SelectItem value="scan">{t('bscheck.kind_scan')}</SelectItem>
                  <SelectItem value="vless">{t('bscheck.kind_vless')}</SelectItem>
                  <SelectItem value="reputation">{t('bscheck.kind_reputation')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {(kind === 'node' || kind === 'reputation') && (
            <div>
              <Label>{t('bscheck.autoNodes')}</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {nodes.map((n) => {
                  const sel = selNodes.includes(n.uuid)
                  return (
                    <button key={n.uuid} type="button"
                      onClick={() => setSelNodes((p) => p.includes(n.uuid) ? p.filter((x) => x !== n.uuid) : [...p, n.uuid])}
                      className={cn('px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                        sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200' : 'border-[var(--glass-border)] text-muted-foreground hover:text-white')}>
                      {n.name}
                    </button>
                  )
                })}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.autoNodesHint')}</p>
            </div>
          )}
          {kind === 'probe' && (
            <div>
              <Label>{t('bscheck.targetsLabel')}</Label>
              <Textarea value={targets} rows={3} className="mt-1 font-mono text-xs" placeholder={'1.2.3.4:443\n5.6.7.8:443'} onChange={(e) => setTargets(e.target.value)} />
            </div>
          )}
          {kind === 'scan' && (
            <div>
              <Label>{t('bscheck.cidrLabel')}</Label>
              <Input value={cidr} className="mt-1 font-mono" placeholder="1.2.3.0/24" onChange={(e) => setCidr(e.target.value)} />
              <p className={cn('text-[11px] mt-1', cidr.trim() && !validScan ? 'text-amber-400' : 'text-muted-foreground')}>
                {cidr.trim() && !validScan ? t('bscheck.cidrInvalid') : t('bscheck.cidrHint')}
              </p>
            </div>
          )}
          {kind === 'vless' && (
            <div>
              <Label>{t('bscheck.rawInput')}</Label>
              <Textarea value={raw} rows={4} className="mt-1 font-mono text-xs" placeholder={'vless://…\nvless://…'} onChange={(e) => setRaw(e.target.value)} />
              <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.rawInputHint')}</p>
            </div>
          )}
          {kind === 'reputation' && (
            <>
              <div>
                <Label>{t('bscheck.jobRepTargets')}</Label>
                <Textarea value={targets} rows={2} className="mt-1 font-mono text-xs" placeholder={'1.2.3.4\nexample.com'} onChange={(e) => setTargets(e.target.value)} />
                <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.jobRepTargetsHint')}</p>
              </div>
              <div>
                <Label>{t('bscheck.jobProviders')}</Label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {(repProvs || []).map((p) => {
                    const sel = repProviders.includes(p.slug)
                    return (
                      <button key={p.slug} type="button"
                        onClick={() => setRepProviders((prev) => prev.includes(p.slug) ? prev.filter((x) => x !== p.slug) : [...prev, p.slug])}
                        className={cn('px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                          sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200' : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                          p.needs_token && !p.configured && 'opacity-50')}>
                        {p.name}
                      </button>
                    )
                  })}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.jobProvidersHint')}</p>
              </div>
            </>
          )}

          <div className="flex flex-wrap gap-3">
            <div className="w-40">
              <Label>{t('bscheck.jobInterval')}</Label>
              <Input type="number" min={5} value={intervalMin} className="mt-1 h-9" onChange={(e) => setIntervalMin(Math.max(5, Number(e.target.value) || 5))} />
            </div>
            {kind === 'reputation' ? (
              <div className="w-44">
                <Label>{t('bscheck.jobBatch')}</Label>
                <Input type="number" min={0} value={batch} className="mt-1 h-9" onChange={(e) => setBatch(Math.max(0, Number(e.target.value) || 0))} />
                <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.jobBatchHint')}</p>
              </div>
            ) : (
              <div className="w-44">
                <Label>{t('bscheck.autoBudget')}</Label>
                <Input type="number" min={0} value={budget} className="mt-1 h-9" onChange={(e) => setBudget(Math.max(0, Number(e.target.value) || 0))} />
              </div>
            )}
          </div>

          {kind !== 'reputation' && operators.length > 0 && (
            <div>
              <Label>{t('bscheck.operators')}</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {operators.map((op) => {
                  const b = opBrand(op.id)
                  const sel = ops.includes(op.op_key)
                  const isOff = op.channel_state === 'DPI_OFF'
                  const off = dpi === 'on' && isOff
                  return (
                    <button key={op.op_key} type="button" disabled={off}
                      onClick={() => !off && setOps((p) => p.includes(op.op_key) ? p.filter((x) => x !== op.op_key) : [...p, op.op_key])}
                      className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                        sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200' : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                        off && 'opacity-40 cursor-not-allowed hover:text-muted-foreground')}>
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.bg }} />
                      {op.name}{op.region_label && <span className="text-muted-foreground">· {op.region_label}</span>}
                      {isOff && <span className="text-amber-400">· {t('bscheck.bsOff')}</span>}
                    </button>
                  )
                })}
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.operatorsHint')}</p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-4">
            {kind !== 'reputation' && (
              <BsDpiSelect value={dpi} onChange={(v) => { setDpi(v); setOps((p) => p.filter((k) => !lockedKeys(v, operators).has(k))) }} />
            )}
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Switch checked={alert} onCheckedChange={setAlert} />{kind === 'reputation' ? t('bscheck.autoAlertRkn') : t('bscheck.autoAlert')}</label>
            <label className="flex items-center gap-2 text-sm cursor-pointer"><Switch checked={enabled} onCheckedChange={setEnabled} />{t('bscheck.autoEnable')}</label>
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
          <Button disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Вкладка «Ноды» ───────────────────────────────────────────────

function NodesTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [checkNode, setCheckNode] = useState<BsNode | null>(null)
  const [detailNode, setDetailNode] = useState<BsNode | null>(null)

  const { data: nodes, isLoading } = useQuery({ queryKey: ['bscheck-nodes'], queryFn: bscheckApi.nodes })
  const { data: summary } = useQuery({ queryKey: ['bscheck-summary'], queryFn: bscheckApi.summary })
  const rows = nodes || []

  return (
    <div className="space-y-3">
      <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
              <th className="px-3 py-2">{t('bscheck.node')}</th>
              <th className="px-3 py-2">{t('bscheck.realIp')}</th>
              <th className="px-3 py-2">{t('bscheck.lastResult')}</th>
              <th className="px-3 py-2 w-40"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={4} className="px-3 py-6"><Skeleton className="h-8 w-full" /></td></tr>
            ) : !rows.length ? (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">{t('bscheck.noNodes')}</td></tr>
            ) : rows.map((n) => {
              const s = summary?.[n.uuid]
              const tunnelOnly = !n.agent_ip
              const clickable = !!s
              return (
                <tr key={n.uuid}
                  className={cn('border-b border-[var(--glass-border)]/50 hover:bg-white/5', clickable && 'cursor-pointer')}
                  onClick={() => clickable && setDetailNode(n)}>
                  <td className="px-3 py-2 font-medium">{n.name}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs">{n.ip || '—'}</span>
                      {tunnelOnly ? (
                        <span title={t('bscheck.tunnelOnly')} className="text-amber-400"><AlertTriangle className="w-3.5 h-3.5" /></span>
                      ) : n.address && n.address !== n.ip ? (
                        <span title={`${t('bscheck.tunnelNote')}: ${n.address}`} className="text-muted-foreground"><Wifi className="w-3.5 h-3.5" /></span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    {s ? (
                      <span className="flex items-center gap-1.5">
                        <ResultBadge passed={s.passed} total={s.total} />
                        <span className="text-[10px] text-muted-foreground">{fmtDate(s.checked_at)}</span>
                      </span>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1.5">
                      {s && (
                        <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => setDetailNode(n)}>
                          <History className="w-3.5 h-3.5" /> {t('bscheck.details')}
                        </Button>
                      )}
                      {canCheck && (
                        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setCheckNode(n)}>
                          <ShieldCheck className="w-3.5 h-3.5" /> {t('bscheck.check')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      </Card>

      {checkNode && (
        <CheckDialog node={checkNode} operators={operators}
          onClose={() => setCheckNode(null)}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ['bscheck-summary'] })
            qc.invalidateQueries({ queryKey: ['bscheck-status'] })
          }} />
      )}
      {detailNode && (
        <NodeDetailDialog node={detailNode} operators={operators} onClose={() => setDetailNode(null)} />
      )}
    </div>
  )
}

// ── Диалог проверки ноды ─────────────────────────────────────────

function CheckDialog({ node, operators, onClose, onDone }: {
  node: BsNode; operators: BsOperator[]; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [target, setTarget] = useState(node.ip ? `${node.ip}:443` : '')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<number | null>(null)
  const [result, setResult] = useState<BsSummary | null>(null)

  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  const body = () => ({ target: target.trim(), ...cfgFields(cfg) })

  const preview = useMutation({
    mutationFn: () => bscheckApi.preview(body()),
    onSuccess: (d) => setCost(d.cost_credits), onError: onErr,
  })
  const run = useMutation({
    mutationFn: () => bscheckApi.checkNode(node.uuid, body()),
    onSuccess: (d) => { setResult(d.summary); onDone() }, onError: onErr,
  })

  const canRun = !!target.trim() && (cfg.probes.icmp || cfg.probes.tcp || cfg.probes.sni)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle className="text-base">{t('bscheck.checkTitle', { node: node.name })}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>{t('bscheck.target')}</Label>
            <Input value={target} className="mt-1 font-mono" placeholder="1.2.3.4:443"
              onChange={(e) => { setTarget(e.target.value); setCost(null) }} />
            <p className="text-[11px] text-muted-foreground mt-1">
              {t('bscheck.targetHint')}
              {!node.agent_ip && <span className="text-amber-400"> · {t('bscheck.tunnelOnly')}</span>}
            </p>
          </div>
          <ProbeConfig cfg={cfg} onChange={change} operators={operators} />
          {result && <OperatorResults summary={result} operators={operators} />}
        </div>
        <DialogFooter className="flex-wrap gap-2 sm:justify-between">
          <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
          <div className="flex items-center gap-2">
            <Button variant="outline" disabled={!canRun || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
            </Button>
            <Button disabled={!canRun || cost === null || run.isPending} onClick={() => run.mutate()}
              title={cost === null ? t('bscheck.previewFirst') : ''}>
              {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
                : cost !== null ? t('bscheck.runCost', { cost }) : t('bscheck.run')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Диалог истории проверок ──────────────────────────────────────

function NodeDetailDialog({ node, operators, onClose }: {
  node: BsNode; operators: BsOperator[]; onClose: () => void
}) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({ queryKey: ['bscheck-history', node.uuid], queryFn: () => bscheckApi.nodeHistory(node.uuid) })
  const [selected, setSelected] = useState<BsCheckRecord | null>(null)
  const history = data?.history || []
  const shown = selected || data?.last || null
  const shownSummary = shown?.result?.summary || null

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <History className="w-4 h-4 text-primary-400" /> {t('bscheck.detailsTitle', { node: node.name })}
          </DialogTitle>
        </DialogHeader>
        {isLoading ? <Skeleton className="h-40 w-full" /> : (
          <div className="space-y-3">
            <p className="text-[11px] text-muted-foreground font-mono">{node.ip}</p>

            {shownSummary
              ? <OperatorResults summary={shownSummary} operators={operators}
                  title={shown ? fmtDate(shown.checked_at) : undefined} />
              : <p className="text-sm text-muted-foreground">{t('bscheck.noHistory')}</p>}

            {history.length > 1 && (
              <div>
                <Label className="text-xs">{t('bscheck.history')}</Label>
                <div className="mt-1 rounded-lg border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]/50">
                  {history.map((h) => {
                    const active = (selected?.id ?? data?.last?.id) === h.id
                    return (
                      <button key={h.id} type="button" onClick={() => setSelected(h)}
                        className={cn('w-full px-3 py-1.5 flex items-center gap-2 text-xs text-left hover:bg-white/5',
                          active && 'bg-primary-500/10')}>
                        <ResultBadge passed={h.passed} total={h.total} />
                        <span className="text-muted-foreground">{fmtDate(h.checked_at)}</span>
                        {h.cost_credits != null && <span className="text-muted-foreground">◈ {h.cost_credits}</span>}
                        {h.created_by && <span className="ml-auto text-muted-foreground truncate">{h.created_by}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>{t('common.close')}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Вкладка «Проверка IP» (мульти-цель / скан /24) ───────────────

function IpTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [mode, setMode] = useState<'targets' | 'scan'>('targets')

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Button size="sm" variant={mode === 'targets' ? 'default' : 'outline'} className="gap-1.5" onClick={() => setMode('targets')}>
          <Crosshair className="w-4 h-4" /> {t('bscheck.modeTargets')}
        </Button>
        <Button size="sm" variant={mode === 'scan' ? 'default' : 'outline'} className="gap-1.5" onClick={() => setMode('scan')}>
          <Network className="w-4 h-4" /> {t('bscheck.modeScan')}
        </Button>
      </div>
      {!canCheck && <p className="text-xs text-amber-400">{t('bscheck.noCheckPerm')}</p>}
      {mode === 'targets' ? <TargetsMode operators={operators} disabled={!canCheck} />
        : <ScanMode operators={operators} disabled={!canCheck} />}
    </Card>
  )
}

function TargetsMode({ operators, disabled }: { operators: BsOperator[]; disabled: boolean }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [raw, setRaw] = useState('')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<number | null>(null)
  const [rows, setRows] = useState<BsTargetSummary[] | null>(null)

  const targets = () => raw.split(/[\n,]/).map((s) => s.trim()).filter(Boolean).slice(0, 10)
  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  const body = () => ({ targets: targets(), ...cfgFields(cfg) })

  const saveHist = useSaveHistory()
  const preview = useMutation({
    mutationFn: () => bscheckApi.preview(body()),
    onSuccess: (d) => setCost(d.cost_credits), onError: onErr,
  })
  const run = useMutation({
    mutationFn: () => bscheckApi.probeMulti(body()),
    onSuccess: (d) => {
      setRows(d.targets)
      const passed = d.targets.reduce((a, r) => a + r.passed, 0)
      const total = d.targets.reduce((a, r) => a + r.total, 0)
      const tg = d.targets.map((r) => r.target)
      saveHist.mutate({
        kind: 'probe',
        target: tg.length > 1 ? `${tg[0]} +${tg.length - 1}` : (tg[0] || ''),
        passed, total, cost_credits: d.cost_credits, result: { targets: d.targets },
      })
    }, onError: onErr,
  })

  const n = targets().length
  const canRun = n > 0 && (cfg.probes.icmp || cfg.probes.tcp || cfg.probes.sni)

  return (
    <div className="space-y-3">
      <div>
        <Label>{t('bscheck.targetsLabel')}</Label>
        <Textarea value={raw} rows={4} className="mt-1 font-mono text-xs"
          placeholder={'1.2.3.4:443\n5.6.7.8:443'}
          onChange={(e) => { setRaw(e.target.value); setCost(null) }} />
        <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.targetsHint', { count: n })}</p>
      </div>
      <ProbeConfig cfg={cfg} onChange={change} operators={operators} />

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" disabled={disabled || !canRun || preview.isPending} onClick={() => preview.mutate()}>
          {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
        </Button>
        <Button disabled={disabled || !canRun || cost === null || run.isPending} onClick={() => run.mutate()}
          title={cost === null ? t('bscheck.previewFirst') : ''}>
          {run.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
            : cost !== null ? t('bscheck.runCost', { cost }) : t('bscheck.run')}
        </Button>
      </div>

      {rows && (
        <div className="space-y-2">
          {rows.length === 0 && <p className="text-sm text-muted-foreground">{t('bscheck.noResults')}</p>}
          {rows.map((r) => (
            <OperatorResults key={r.target} summary={r} operators={operators} title={r.target} />
          ))}
        </div>
      )}
    </div>
  )
}

function ScanMode({ operators, disabled }: { operators: BsOperator[]; disabled: boolean }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const [cidr, setCidr] = useState('')
  const [cfg, setCfg] = useState<Cfg>(DEFAULT_CFG)
  const [cost, setCost] = useState<{ cost_credits: number; total_ips?: number } | null>(null)
  const [scanId, setScanId] = useState<number | null>(null)

  const change = (c: Cfg) => { setCfg(c); setCost(null) }
  // bsbord поддерживает РОВНО /24 — нормализуем host-биты в .0/24
  const normCidr = () => {
    const m = cidr.trim().match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}\/24$/)
    return m ? `${m[1]}.${m[2]}.${m[3]}.0/24` : cidr.trim()
  }
  const body = () => ({ cidr: normCidr(), ...cfgFields(cfg) })

  const preview = useMutation({
    mutationFn: () => bscheckApi.scanPreview(body()),
    onSuccess: (d) => setCost(d), onError: onErr,
  })
  const submit = useMutation({
    mutationFn: () => bscheckApi.scanSubmit(body()),
    onSuccess: (d) => setScanId(d.scan_id), onError: onErr,
  })
  const poll: UseQueryResult<any> = useQuery({
    queryKey: ['bscheck-scan', scanId], enabled: scanId != null,
    queryFn: () => bscheckApi.scanStatus(scanId as number),
    refetchInterval: (q) => {
      const d: any = q.state.data
      if (!d) return 4000
      return ['done', 'failed', 'error', 'cancelled'].includes(d.state) ? false : 4000
    },
  })
  // Остановка гасит непройденную часть целиком и списывает пропорционально
  // проверенным адресам. Сумму отдаёт уже следующий статус, поэтому поллинг
  // продолжаем, а не гасим сразу.
  const cancel = useMutation({
    mutationFn: () => bscheckApi.scanCancel(scanId as number),
    onSuccess: (d) => toast.success(t('bscheck.scanCancelled', { done: d.done_ips ?? 0, total: d.total_ips ?? 0 })),
    onError: onErr,
  })

  const octetsOk = (s: string) => s.replace(/\/.*/, '').split('.').every((o) => o !== '' && Number(o) >= 0 && Number(o) <= 255)
  const validCidr = /^\d{1,3}(\.\d{1,3}){3}\/24$/.test(cidr.trim()) && octetsOk(cidr.trim())
  const scanData: any = poll.data

  const saveHist = useSaveHistory()
  const savedRef = useRef<number | null>(null)
  useEffect(() => {
    if (scanId == null) return
    if (scanData?.state === 'done' && savedRef.current !== scanId) {
      savedRef.current = scanId
      const r = scanData?.result ?? scanData
      const byTarget: Record<string, any> = r?.by_target || (scanData?.by_target ?? {})
      const entries = Object.entries(byTarget).filter(([, v]: [string, any]) => v?.by_operator)
      const alive = entries.filter(([, v]: [string, any]) => sumByOp(v.by_operator).passed > 0).length
      saveHist.mutate({
        kind: 'scan', target: cidr.trim(), passed: alive, total: entries.length,
        cost_credits: cost?.cost_credits ?? null, result: scanData,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId, scanData])

  return (
    <div className="space-y-3">
      <div>
        <Label>{t('bscheck.cidrLabel')}</Label>
        <Input value={cidr} className="mt-1 font-mono" placeholder="1.2.3.0/24"
          onChange={(e) => { setCidr(e.target.value); setCost(null); setScanId(null) }} />
        <p className={cn('text-[11px] mt-1', cidr.trim() && !validCidr ? 'text-amber-400' : 'text-muted-foreground')}>
          {cidr.trim() && !validCidr ? t('bscheck.cidrInvalid') : t('bscheck.cidrHint')}
        </p>
      </div>
      <ProbeConfig cfg={cfg} onChange={change} operators={operators} />

      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          {cost && <>◈ {cost.cost_credits}{cost.total_ips != null && <> · {t('bscheck.scanTotalIps', { count: cost.total_ips })}</>}</>}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={disabled || !validCidr || preview.isPending} onClick={() => preview.mutate()}>
            {preview.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
          </Button>
          <Button disabled={disabled || !validCidr || cost === null || submit.isPending || (scanId != null && poll.isLoading)}
            onClick={() => submit.mutate()} title={cost === null ? t('bscheck.previewFirst') : ''}>
            {submit.isPending ? <Loader2 className="w-4 h-4 animate-spin" />
              : cost !== null ? t('bscheck.runScanCost', { cost: cost.cost_credits }) : t('bscheck.runScan')}
          </Button>
        </div>
      </div>

      {scanId != null && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <PollStatus state={scanData?.state} kind="scan" />
            {scanData && !['done', 'failed', 'error', 'cancelled'].includes(scanData.state) && (
              <Button size="sm" variant="outline" className="h-7 text-xs"
                disabled={disabled || cancel.isPending} onClick={() => cancel.mutate()}>
                {t('bscheck.cancelScan')}
              </Button>
            )}
          </div>
          {scanData && ['done', 'cancelled'].includes(scanData.state) && <ScanResult data={scanData} operators={operators} />}
        </div>
      )}
    </div>
  )
}

/** Гибкий рендер результата скана: by_target (как probe) либо raw-фолбэк. */
function ScanResult({ data, operators }: { data: any; operators: BsOperator[] }) {
  const { t } = useTranslation()
  const r = data?.result ?? data
  const byTarget: Record<string, any> = r?.by_target || (data?.by_target ?? {})
  const entries = Object.entries(byTarget).filter(([, v]: [string, any]) => v && v.by_operator)

  if (entries.length > 0) {
    const alive = entries.filter(([, v]: [string, any]) => sumByOp(v.by_operator).passed > 0).length
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">{t('bscheck.scanFound', { alive, total: entries.length })}</p>
        {entries
          .map(([ip, v]: [string, any]) => ({ ip, s: sumByOp(v.by_operator) }))
          .sort((a, b) => b.s.passed - a.s.passed)
          .map(({ ip, s }) => <OperatorResults key={ip} summary={s} operators={operators} title={ip} />)}
      </div>
    )
  }

  // Фолбэк: числовые поля + сырой JSON
  const stats = Object.entries(r || {}).filter(([, v]) => typeof v === 'number')
  return (
    <div className="space-y-2">
      {stats.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          {stats.map(([k, v]) => <Badge key={k} variant="outline">{k}: {String(v)}</Badge>)}
        </div>
      )}
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">{t('bscheck.raw')}</summary>
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-black/30 p-2 text-[10px]">{JSON.stringify(r, null, 2)}</pre>
      </details>
    </div>
  )
}

// ── Рендер результата VLESS-теста (по серверам → по модемам) ─────

function vlessServers(data: any): any[] {
  if (Array.isArray(data?.result)) return data.result
  if (Array.isArray(data?.results)) return data.results
  if (Array.isArray(data?.servers)) return data.servers
  return []
}

function vlessLegs(server: any): Array<{ op: string; leg: any }> {
  const bo = server?.by_operator ?? server?.operators ?? server?.modems ?? server?.results
  if (bo && typeof bo === 'object' && !Array.isArray(bo)) {
    return Object.entries(bo).map(([op, leg]) => ({ op, leg: leg as any }))
  }
  if (Array.isArray(bo)) {
    return bo.map((leg: any) => ({ op: String(leg.op || leg.op_key || leg.operator || leg.modem || ''), leg }))
  }
  return []
}

function VlessServers({ data, operators }: { data: any; operators: BsOperator[] }) {
  const { t } = useTranslation()
  const servers = vlessServers(data)
  if (!servers.length) {
    return (
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">{t('bscheck.raw')}</summary>
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-black/30 p-2 text-[10px]">{JSON.stringify(data?.result ?? data, null, 2)}</pre>
      </details>
    )
  }
  return (
    <div className="space-y-2">
      {servers.map((s, i) => {
        const legs = vlessLegs(s)
        const name = s.server_name || s.name || s.remark || `#${i + 1}`
        const addr = s.address || s.host || ''
        const okCnt = legs.filter(({ leg }) => (leg.tunnel_up ?? leg.ok ?? leg.tcp?.ok)).length
        const total = legs.length || (s.total ?? 0)
        const passed = total ? okCnt : (s.passed ?? (s.ok ? 1 : 0))
        return (
          <div key={i} className="rounded-lg border border-[var(--glass-border)]">
            <div className="flex items-center gap-2 px-3 py-2 text-xs border-b border-[var(--glass-border)]/50">
              <span className="font-medium">{name}</span>
              {addr && <span className="font-mono text-muted-foreground truncate">{addr}</span>}
              <Badge className={cn('ml-auto text-[10px]',
                total > 0 && passed === total ? 'bg-green-500/20 text-green-300'
                  : passed === 0 ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300')}>
                {total ? `${passed}/${total}` : (s.ok ? 'ok' : '—')}
              </Badge>
            </div>
            {legs.length > 0 ? (
              <div className="divide-y divide-[var(--glass-border)]/40">
                {legs.map(({ op, leg }, j) => {
                  const tcpOk = leg.tcp?.ok ?? leg.tcp_ok ?? leg.ok
                  const tcpMs = leg.tcp?.latency_ms ?? leg.latency_ms ?? leg.tcp_ms
                  const tunnel = leg.tunnel_up ?? leg.tunnel?.up ?? (typeof leg.tunnel === 'boolean' ? leg.tunnel : undefined)
                  const sitesOk = leg.sites?.passed ?? leg.sites?.ok ?? leg.sites_ok ?? leg.websites_ok
                  const sitesTotal = leg.sites?.total ?? leg.sites_total ?? leg.websites_total
                  const timeMs = leg.time_ms ?? leg.duration_ms ?? leg.elapsed_ms
                  const timeS = leg.time_s ?? (typeof timeMs === 'number' ? Math.round(timeMs / 100) / 10 : undefined)
                  const speed = leg.speed_mbps ?? leg.speed ?? leg.mbps
                  return (
                    <div key={j} className="px-3 py-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <OperatorTag opKey={op} operators={operators} />
                      {tcpOk != null && <span className={tcpOk ? 'text-green-400' : 'text-red-400'}>TCP {tcpOk ? 'ok' : 'fail'}{tcpMs != null ? ` · ${tcpMs}ms` : ''}</span>}
                      {tunnel != null && <span className={tunnel ? 'text-green-400' : 'text-red-400'}>{t('bscheck.tunnelUp')}: {tunnel ? t('bscheck.up') : t('bscheck.down')}</span>}
                      {sitesTotal != null && <span className="text-muted-foreground">{t('bscheck.sites')}: {sitesOk ?? 0}/{sitesTotal}</span>}
                      {speed != null && <span className="text-muted-foreground inline-flex items-center gap-1"><Gauge className="w-3 h-3" />{speed} Mbps</span>}
                      {timeS != null && <span className="ml-auto text-muted-foreground tabular-nums">{timeS}s</span>}
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="px-3 py-2 text-xs flex items-center gap-2">
                {(s.tunnel_up ?? s.ok) ? <Check className="w-4 h-4 text-green-400" /> : <X className="w-4 h-4 text-red-400" />}
                {s.speed_mbps != null && <span className="inline-flex items-center gap-1"><Gauge className="w-3.5 h-3.5" />{s.speed_mbps} Mbps</span>}
                {s.error && <span className="text-red-300">{s.error}</span>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Вкладка «Тест конфига» (VLESS/Reality) ───────────────────────

function ConfigTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const onErr = useErrToast()
  const canCheck = usePermissionStore((s) => s.hasPermission)('bscheck', 'check')
  const [raw, setRaw] = useState('')
  const [dpi, setDpi] = useState('on')
  const [core, setCore] = useState('')   // '' = Авто
  const [modems, setModems] = useState<string[]>([])
  const [testId, setTestId] = useState<number | null>(null)
  const [est, setEst] = useState<{ cost: number; n: number } | null>(null)

  // Хосты из vless://…@host:port (для оценки через probe/preview — у vless превью нет)
  const vlessHosts = (): string[] => {
    const out: string[] = []
    const re = /vless:\/\/[^@\s]+@([^:/?#\s]+)(?::(\d+))?/gi
    let m: RegExpExecArray | null
    while ((m = re.exec(raw)) && out.length < 10) {
      const h = m[2] ? `${m[1]}:${m[2]}` : m[1]
      if (!out.includes(h)) out.push(h)
    }
    return out
  }

  const body = () => ({ raw_input: raw, selected_modems: modems, dpi, core })
  const submit = useMutation({
    mutationFn: () => bscheckApi.vlessSubmit(body()),
    onSuccess: (d) => { setTestId(d.test_id); toast.success(t('bscheck.vlessCost', { cost: d.cost_credits })) },
    onError: onErr,
  })
  const estimate = useMutation({
    mutationFn: () => bscheckApi.preview({
      targets: vlessHosts(), operators: modems,
      probes: { icmp: false, tcp: true, sni: true }, sni_hosts: [], dpi,
    }),
    onSuccess: (d) => setEst({ cost: d.cost_credits, n: vlessHosts().length }),
    onError: onErr,
  })
  const poll: UseQueryResult<any> = useQuery({
    queryKey: ['bscheck-vless', testId], enabled: testId != null,
    queryFn: () => bscheckApi.vlessStatus(testId as number),
    refetchInterval: (q) => {
      const d: any = q.state.data
      if (!d) return 4000
      return (d.result_ready || ['done', 'failed', 'error', 'cancelled'].includes(d.state)) ? false : 4000
    },
  })

  const locked = dpi === 'on'
  const setDpiMode = (v: string) => {
    setEst(null)
    setDpi(v)
    setModems((m) => m.filter((k) => !lockedKeys(v, operators).has(k)))
  }
  // Ждал очереди — возврат полный; уже шёл — гасится несделанная часть, а
  // полученные вердикты остаются платными, включая «режется оператором».
  const cancel = useMutation({
    mutationFn: () => bscheckApi.vlessCancel(testId as number),
    onSuccess: (d) => toast.success(t('bscheck.vlessCancelled', { refunded: d.refunded_credits ?? 0 })),
    onError: onErr,
  })
  const toggleModem = (op: string) => { setEst(null); setModems((m) => m.includes(op) ? m.filter((x) => x !== op) : [...m, op]) }
  const data: any = poll.data
  const servers: any[] = vlessServers(data)

  const saveHist = useSaveHistory()
  const savedRef = useRef<number | null>(null)
  useEffect(() => {
    if (testId == null) return
    const done = data?.result_ready || data?.state === 'done'
    if (done && savedRef.current !== testId) {
      savedRef.current = testId
      const passed = servers.filter((s) => (s.ok ?? s.tunnel_up) || vlessLegs(s).some(({ leg }) => leg.tunnel_up ?? leg.ok)).length
      saveHist.mutate({
        kind: 'vless',
        target: servers[0]?.server_name || servers[0]?.name || servers[0]?.remark || `${servers.length} серв.`,
        passed, total: servers.length, cost_credits: null, result: data,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testId, data])

  return (
    <Card className="p-4 space-y-4">
      {!canCheck && <p className="text-xs text-amber-400">{t('bscheck.noCheckPerm')}</p>}
      <div>
        <Label>{t('bscheck.rawInput')}</Label>
        <Textarea value={raw} rows={5} className="mt-1 font-mono text-xs"
          placeholder={'vless://…\nvless://…'}
          onChange={(e) => { setRaw(e.target.value); setTestId(null); setEst(null) }} />
        <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.rawInputHint')}</p>
      </div>

      <div className="space-y-1">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t('bscheck.dpiMode')}</Label>
            <div className="h-8 flex items-center"><BsDpiSelect value={dpi} onChange={setDpiMode} /></div>
          </div>
          <div className="w-44">
            <Label className="text-xs">{t('bscheck.core')}</Label>
            <Select value={core || 'auto'} onValueChange={(v) => setCore(v === 'auto' ? '' : v)}>
              <SelectTrigger className="h-8 mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">{t('bscheck.coreAuto')}</SelectItem>
                <SelectItem value="stable">{t('bscheck.coreStable')}</SelectItem>
                <SelectItem value="prerelease">{t('bscheck.coreNew')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <p className={cn('text-[11px]', locked ? 'text-muted-foreground' : 'text-amber-400')}>
          {locked ? t('bscheck.lockBsHint') : t(dpi === 'off' ? 'bscheck.bsOffWarn' : 'bscheck.bsAnyWarn')}
        </p>
      </div>

      {operators.length > 0 && (
        <div>
          <Label>{t('bscheck.selectedModems')}</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {operators.map((op) => {
              const b = opBrand(op.id)
              const sel = modems.includes(op.op_key)
              const isOff = op.channel_state === 'DPI_OFF'
              const off = lockedKeys(dpi, operators).has(op.op_key)
              return (
                <button key={op.op_key} type="button" disabled={off}
                  onClick={() => !off && toggleModem(op.op_key)}
                  className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                    sel ? 'border-primary-500/50 bg-primary-500/15 text-primary-200'
                      : 'border-[var(--glass-border)] text-muted-foreground hover:text-white',
                    off && 'opacity-40 cursor-not-allowed hover:text-muted-foreground')}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.bg }} />
                  {op.name}{op.region_label && <span className="text-muted-foreground">· {op.region_label}</span>}
                  {isOff && <span className="text-amber-400">· {t('bscheck.bsOff')}</span>}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">{t('bscheck.modemsHint')}</p>
        </div>
      )}

      <div className="space-y-1">
        <div className="flex flex-wrap items-center justify-end gap-2">
          {est != null && (
            <span className="mr-auto text-xs text-amber-300">{t('bscheck.vlessEst', { cost: est.cost, n: est.n })}</span>
          )}
          <Button variant="outline" disabled={!canCheck || vlessHosts().length === 0 || estimate.isPending}
            onClick={() => estimate.mutate()} title={t('bscheck.vlessEstHint')}>
            {estimate.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.preview')}
          </Button>
          <Button disabled={!canCheck || !raw.trim() || submit.isPending || (testId != null && poll.isLoading && !servers.length)}
            onClick={() => submit.mutate()}>
            {submit.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('bscheck.runVless')}
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground text-right">{t('bscheck.vlessEstNote')}</p>
      </div>

      {testId != null && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <PollStatus state={data?.result_ready ? 'done' : data?.state} kind="vless" />
            {/* used_core — ядро, на котором реально прогнали. В режиме Авто
                расхождение с заказанным нормально, при форсе его быть не должно */}
            {data?.used_core && (
              <Badge variant="outline" className="text-[10px]">
                {t('bscheck.usedCore', { core: data.used_core })}
                {data.core_requested && data.core_requested !== 'auto' && data.core_requested !== data.used_core
                  ? ` (${t('bscheck.coreRequested', { core: data.core_requested })})` : ''}
              </Badge>
            )}
            {data && !data.result_ready && !['done', 'cancelled', 'not_found'].includes(data.state) && (
              <Button size="sm" variant="outline" className="h-7 text-xs"
                disabled={!canCheck || cancel.isPending} onClick={() => cancel.mutate()}>
                {t('bscheck.cancelVless')}
              </Button>
            )}
          </div>
          {(servers.length > 0 || data?.result_ready) && <VlessServers data={data} operators={operators} />}
        </div>
      )}
    </Card>
  )
}

// ── Вкладка «История» (журнал всех проверок) ─────────────────────

function RawBlock({ data }: { data: any }) {
  const { t } = useTranslation()
  return (
    <details className="text-xs" open>
      <summary className="cursor-pointer text-muted-foreground">{t('bscheck.raw')}</summary>
      <pre className="mt-1 max-h-72 overflow-auto rounded bg-black/30 p-2 text-[10px]">{JSON.stringify(data, null, 2)}</pre>
    </details>
  )
}

function HistoryResult({ row, operators }: { row: BsHistoryRow; operators: BsOperator[] }) {
  const r: any = row.result || {}
  if (row.kind === 'vless') return <VlessServers data={r} operators={operators} />
  if (row.kind === 'scan') return <ScanResult data={r} operators={operators} />
  if (row.kind === 'reputation') {
    const results = Array.isArray(r.results) ? r.results : []
    if (!results.length) return <RawBlock data={r} />
    return <div className="grid gap-2 sm:grid-cols-2">{results.map((x: any, i: number) => <RepCard key={i} r={x} />)}</div>
  }
  if (row.kind === 'probe') {
    const targets: BsTargetSummary[] = Array.isArray(r.targets) ? r.targets : []
    if (targets.length) return <div className="space-y-2">{targets.map((s) => <OperatorResults key={s.target} summary={s} operators={operators} title={s.target} />)}</div>
    return <RawBlock data={r} />
  }
  if (r.summary) return <OperatorResults summary={r.summary} operators={operators} />
  return <RawBlock data={r} />
}

function HistoryDetailDialog({ row, operators, onClose }: {
  row: BsHistoryRow; operators: BsOperator[]; onClose: () => void
}) {
  const { t } = useTranslation()
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <History className="w-4 h-4 text-primary-400" />
            <Badge variant="outline" className="text-[10px]">{kindLabel(row.kind, t)}</Badge>
            <span className="font-mono text-sm truncate">{row.target || '—'}</span>
          </DialogTitle>
        </DialogHeader>
        <p className="text-[11px] text-muted-foreground">
          {fmtDate(row.checked_at)}{row.cost_credits != null && ` · ◈ ${row.cost_credits}`}{row.created_by && ` · ${row.created_by}`}
        </p>
        <HistoryResult row={row} operators={operators} />
      </DialogContent>
    </Dialog>
  )
}

function HistoryTab({ operators }: { operators: BsOperator[] }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({ queryKey: ['bscheck-history'], queryFn: () => bscheckApi.history() })
  const [detail, setDetail] = useState<BsHistoryRow | null>(null)
  const items = data || []
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground border-b border-[var(--glass-border)]">
              <th className="px-3 py-2">{t('bscheck.histTime')}</th>
              <th className="px-3 py-2">{t('bscheck.histKind')}</th>
              <th className="px-3 py-2">{t('bscheck.histTarget')}</th>
              <th className="px-3 py-2">{t('bscheck.passed')}</th>
              <th className="px-3 py-2 w-16 text-right">◈</th>
              <th className="px-2 py-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="px-3 py-6"><Skeleton className="h-8 w-full" /></td></tr>
            ) : !items.length ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">{t('bscheck.histEmpty')}</td></tr>
            ) : items.map((row) => (
              <tr key={row.id} className="border-b border-[var(--glass-border)]/50 hover:bg-white/5 cursor-pointer" onClick={() => setDetail(row)}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{fmtDate(row.checked_at)}</td>
                <td className="px-3 py-2"><Badge variant="outline" className="text-[10px]">{kindLabel(row.kind, t)}</Badge></td>
                <td className="px-3 py-2 font-mono text-xs truncate max-w-[220px]">{row.target || '—'}</td>
                <td className="px-3 py-2"><ResultBadge passed={row.passed} total={row.total} /></td>
                <td className="px-3 py-2 text-right text-xs text-muted-foreground">{row.cost_credits ?? '—'}</td>
                <td className="px-2 py-2 text-muted-foreground"><ChevronRight className="w-4 h-4" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail && <HistoryDetailDialog row={detail} operators={operators} onClose={() => setDetail(null)} />}
    </Card>
  )
}
