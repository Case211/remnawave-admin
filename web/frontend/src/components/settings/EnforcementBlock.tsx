import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import client from '@/api/client'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useHasPermission } from '@/components/PermissionGate'
import { AlertTriangle, Power, PowerOff, Search, ShieldCheck, X } from '@/components/brand/icons'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

interface User { uuid: string; username: string; status?: string; tag?: string }
interface Status {
  enabled: boolean; mode: string; scope: string; grace_hours: number; min_score: number; final_action: string; notice_suffix: string
  pause_for_support: boolean; delivery_failure: string; delivery_attempts: number
  throttle_kbit: number; throttle_hours: number; pilot_user_uuids: string[]; pilot_users: User[]
  pilot_config_valid: boolean; case_counts: Record<string, number>
}
interface Simulation {
  user: User; violation_id?: number; signal?: string; reasons: string[]; eligible: boolean
  in_pilot: boolean; mode: string; final_action: string; grace_hours: number
  would_send_notice: boolean; would_apply_action: boolean
}
interface EnforcementCase {
  id: number; username?: string; user_uuid: string; status: string; mode: string
  final_action: string; deadline_at: string; resolution?: string; last_error?: string
}

function errorText(error: unknown): string {
  const value = error as { response?: { data?: { detail?: string } }; message?: string }
  return value.response?.data?.detail || value.message || 'Request failed'
}

export default function EnforcementBlock({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const canResolve = useHasPermission('violations', 'resolve')
  const [identifier, setIdentifier] = useState('')
  const [simulation, setSimulation] = useState<Simulation | null>(null)
  const [toggleOpen, setToggleOpen] = useState(false)
  const [pendingAction, setPendingAction] = useState<{ id: number; action: string } | null>(null)

  const statusQuery = useQuery<Status>({
    queryKey: ['enforcementStatus'],
    queryFn: async () => (await client.get('/enforcement/status')).data,
  })
  const casesQuery = useQuery<{ items: EnforcementCase[] }>({
    queryKey: ['enforcementCases'],
    queryFn: async () => (await client.get('/enforcement/cases')).data,
  })
  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['enforcementStatus'] }),
    queryClient.invalidateQueries({ queryKey: ['enforcementCases'] }),
    queryClient.invalidateQueries({ queryKey: ['settings'] }),
  ])
  const settingMutation = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => client.put(`/settings/${key}`, { value }),
    onSuccess: async () => { await refresh(); toast.success(t('settings.enforcement.saved')) },
    onError: (error) => toast.error(errorText(error)),
  })
  const simulationMutation = useMutation({
    mutationFn: async () => (await client.get('/enforcement/simulate', { params: { user: identifier.trim() } })).data as Simulation,
    onSuccess: setSimulation,
    onError: (error) => { setSimulation(null); toast.error(errorText(error)) },
  })
  const caseMutation = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: string }) => client.post(`/enforcement/cases/${id}/action`, { action, confirm: true }),
    onSuccess: async () => { setPendingAction(null); await refresh(); toast.success(t('settings.enforcement.caseUpdated')) },
    onError: (error) => toast.error(errorText(error)),
  })

  const status = statusQuery.data
  const set = (key: string, value: string | number | boolean) => settingMutation.mutate({ key: `enforcement_${key}`, value: String(value) })
  const updatePilot = (uuid: string, add: boolean) => {
    const current = status?.pilot_user_uuids || []
    const next = add ? Array.from(new Set([...current, uuid])) : current.filter((item) => item !== uuid)
    settingMutation.mutate({ key: 'enforcement_pilot_user_uuids', value: JSON.stringify(next) })
  }

  return (
    <div className="space-y-5">
      <Card className="p-5 space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-primary-400 mt-0.5" />
            <div>
              <h2 className="font-semibold text-white">{t('settings.enforcement.title')}</h2>
              <p className="text-xs text-dark-200 mt-1">{t('settings.enforcement.description')}</p>
            </div>
          </div>
          {canEdit && <Button variant={status?.enabled ? 'outline' : 'destructive'} onClick={() => setToggleOpen(true)} className="gap-2">
            {status?.enabled ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
            {t(status?.enabled ? 'settings.enforcement.disable' : 'settings.enforcement.enable')}
          </Button>}
        </div>

        <div className={`rounded-lg border p-3 text-sm ${status?.enabled ? 'border-red-500/30 bg-red-500/5' : 'border-green-500/20 bg-green-500/5'}`}>
          {t(status?.enabled ? 'settings.enforcement.enabledHint' : 'settings.enforcement.disabledHint')}
        </div>

        <div className="grid md:grid-cols-5 gap-3">
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.mode')}</span>
            <Select value={status?.mode || 'dry_run'} disabled={!canEdit} onValueChange={(v) => set('mode', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
              {['dry_run', 'deliver_only', 'enforce'].map((v) => <SelectItem key={v} value={v}>{t(`settings.enforcement.modes.${v}`)}</SelectItem>)}
            </SelectContent></Select>
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.scope')}</span>
            <Select value={status?.scope || 'trial_only'} disabled={!canEdit} onValueChange={(v) => set('scope', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
              {['trial_only', 'all_hard_blocks'].map((v) => <SelectItem key={v} value={v}>{t(`settings.enforcement.scopes.${v}`)}</SelectItem>)}
            </SelectContent></Select>
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.grace')}</span>
            <Input type="number" min={1} max={720} defaultValue={status?.grace_hours || 12} disabled={!canEdit} onBlur={(e) => set('grace_hours', Math.max(1, Math.min(720, Number(e.target.value) || 12)))} />
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.minScore')}</span>
            <Input type="number" min={0} max={100} defaultValue={status?.min_score || 0} disabled={!canEdit} onBlur={(e) => set('min_score', Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.action')}</span>
            <Select value={status?.final_action || 'manual_review'} disabled={!canEdit} onValueChange={(v) => set('final_action', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
              {['manual_review', 'disable', 'throttle', 'none'].map((v) => <SelectItem key={v} value={v}>{t(`settings.enforcement.actions.${v}`)}</SelectItem>)}
            </SelectContent></Select>
          </label>
        </div>

        <div className="grid md:grid-cols-4 gap-3">
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.deliveryFailure')}</span>
            <Select value={status?.delivery_failure || 'manual_review'} disabled={!canEdit} onValueChange={(v) => set('delivery_failure', v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
              {['manual_review', 'continue', 'fail'].map((v) => <SelectItem key={v} value={v}>{t(`settings.enforcement.failures.${v}`)}</SelectItem>)}
            </SelectContent></Select>
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.attempts')}</span>
            <Input type="number" min={1} max={20} defaultValue={status?.delivery_attempts || 3} disabled={!canEdit} onBlur={(e) => set('delivery_attempts', Math.max(1, Math.min(20, Number(e.target.value) || 3)))} />
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.throttle')}</span>
            <Input type="number" min={1} defaultValue={status?.throttle_kbit || 1024} disabled={!canEdit} onBlur={(e) => set('throttle_kbit', Math.max(1, Number(e.target.value) || 1024))} />
          </label>
          <label className="text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.throttleHours')}</span>
            <Input type="number" min={0} defaultValue={status?.throttle_hours || 0} disabled={!canEdit} onBlur={(e) => set('throttle_hours', Math.max(0, Number(e.target.value) || 0))} />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm text-dark-100">
          <input type="checkbox" checked={status?.pause_for_support ?? true} disabled={!canEdit} onChange={(e) => set('pause_for_support', e.target.checked)} />
          {t('settings.enforcement.pauseSupport')}
        </label>
        <label className="block text-xs text-dark-200 space-y-1.5"><span>{t('settings.enforcement.noticeSuffix')}</span>
          <Textarea key={status?.notice_suffix} defaultValue={status?.notice_suffix || ''} disabled={!canEdit} onBlur={(e) => { if (e.target.value !== status?.notice_suffix) set('notice_suffix', e.target.value) }} />
          <span className="text-dark-300">{t('settings.enforcement.noticeSuffixHint')}</span>
        </label>
        <div className="rounded-lg bg-dark-950/60 px-3 py-2 text-xs font-mono text-dark-100">POST /api/v3/enforcement/support-events</div>
      </Card>

      <Card className="p-5 space-y-4">
        <div><h3 className="font-medium text-white">{t('settings.enforcement.pilot')}</h3><p className="text-xs text-dark-200 mt-1">{t('settings.enforcement.pilotHint')}</p></div>
        {!status?.pilot_user_uuids.length && <div className="flex gap-2 text-xs text-yellow-200"><AlertTriangle className="w-4 h-4" />{t('settings.enforcement.emptyPilot')}</div>}
        <div className="flex flex-wrap gap-2">{status?.pilot_users.map((user) => <Badge key={user.uuid} variant="secondary" className="gap-1">{user.username}{canEdit && <button onClick={() => updatePilot(user.uuid, false)}><X className="w-3 h-3" /></button>}</Badge>)}</div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (identifier.trim()) simulationMutation.mutate() }}>
          <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder={t('settings.enforcement.userPlaceholder')} />
          <Button type="submit" variant="outline" disabled={!identifier.trim()} className="gap-2"><Search className="w-4 h-4" />{t('settings.enforcement.simulate')}</Button>
        </form>
        {simulation && <div className="rounded-lg border border-dark-700 p-4 space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-white">{simulation.user.username}</span><Badge variant={simulation.eligible ? 'success' : 'secondary'}>{t(simulation.eligible ? 'settings.enforcement.eligible' : 'settings.enforcement.notEligible')}</Badge></div>
          <p className="font-mono text-xs text-dark-300">{simulation.user.uuid}</p>
          <p className="text-dark-100">{t('settings.enforcement.simulationResult', { mode: simulation.mode, hours: simulation.grace_hours, action: simulation.final_action })}</p>
          {canEdit && <Button size="sm" variant="outline" onClick={() => updatePilot(simulation.user.uuid, !simulation.in_pilot)}>{t(simulation.in_pilot ? 'settings.enforcement.removePilot' : 'settings.enforcement.addPilot')}</Button>}
        </div>}
      </Card>

      <Card className="p-5 space-y-3">
        <div className="flex justify-between"><h3 className="font-medium text-white">{t('settings.enforcement.queue')}</h3><div className="flex gap-1">{Object.entries(status?.case_counts || {}).map(([key, count]) => <Badge key={key} variant="secondary">{key}: {count}</Badge>)}</div></div>
        {!casesQuery.data?.items.length && <p className="text-sm text-dark-300">{t('settings.enforcement.noCases')}</p>}
        {casesQuery.data?.items.map((item) => <div key={item.id} className="rounded-lg border border-dark-700 p-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div><div className="flex gap-2"><span className="text-sm text-white">#{item.id} {item.username || item.user_uuid.slice(0, 8)}</span><Badge variant="secondary">{item.status}</Badge><Badge variant="outline">{item.mode}</Badge></div><p className="text-xs text-dark-300 mt-1">{item.final_action} · {new Date(item.deadline_at).toLocaleString()}</p>{item.last_error && <p className="text-xs text-red-300 mt-1">{item.last_error}</p>}</div>
          {canResolve && !['enforced', 'resolved', 'cancelled'].includes(item.status) && <div className="flex gap-2">{['run_now', 'manual_review', 'cancel'].map((action) => <Button key={action} size="sm" variant="outline" onClick={() => setPendingAction({ id: item.id, action })}>{t(`settings.enforcement.caseActions.${action}`)}</Button>)}</div>}
        </div>)}
      </Card>

      <ConfirmDialog open={toggleOpen} onOpenChange={setToggleOpen} title={t(status?.enabled ? 'settings.enforcement.disableConfirm' : 'settings.enforcement.enableConfirm')} description={t(status?.enabled ? 'settings.enforcement.disableConfirmHint' : 'settings.enforcement.enableConfirmHint', { mode: status?.mode || 'dry_run', count: status?.pilot_user_uuids.length || 0 })} confirmLabel={t(status?.enabled ? 'settings.enforcement.disable' : 'settings.enforcement.enable')} variant={status?.enabled ? 'default' : 'destructive'} onConfirm={() => { set('enabled', !status?.enabled); setToggleOpen(false) }} />
      <ConfirmDialog open={!!pendingAction} onOpenChange={(open) => { if (!open) setPendingAction(null) }} title={t('settings.enforcement.caseConfirm')} description={t('settings.enforcement.caseConfirmHint')} confirmLabel={pendingAction ? t(`settings.enforcement.caseActions.${pendingAction.action}`) : ''} variant="destructive" onConfirm={() => pendingAction && caseMutation.mutate(pendingAction)} />
    </div>
  )
}
